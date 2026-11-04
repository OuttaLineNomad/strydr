"""Derive stage: per-workout facts, load, day classes, records and routes (AD-7)."""
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.pipeline.context import Context
from strydr.pipeline.derive import days as days_mod
from strydr.pipeline.derive import load as load_mod
from strydr.pipeline.derive import conditions, grade, records, sleep, summary, track
from strydr.pipeline.derive.routes import stage as routes_stage
from strydr.pipeline.derive.routes.display import for_display
from strydr.pipeline.hr import active_clock
from strydr.pipeline.profile import Profile, resolve
from strydr.store import generations, models, series, settings

log = logging.getLogger("strydr.derive")
M_PER_MILE = 1609.344
_WEATHER_COLS = ("temp_c", "apparent_c", "dew_point_c", "humidity_pct", "wind_ms", "wind_dir_deg", "gust_ms",
                 "precip_mm_h", "cloud_pct")


def run(ctx: Context, profile: Profile) -> None:
    """Order: summary and workout detail, load, days, records, then routes (each reads only stored tables or the
    previous step's output)."""
    gid, th = ctx.generation_id, ctx.th
    load_params = load_mod.LoadParams.from_mapping(th.section("load"))
    day_params = days_mod.DayParams.from_mapping(th.section("days"))
    with Session(ctx.engine) as s:
        zones = list(s.execute(select(models.PrivacyZone)).scalars())
        s.expunge_all()
        workouts = s.execute(select(models.Workout).where(models.Workout.local_date <= ctx.as_of.isoformat())
                             .order_by(models.Workout.start_utc, models.Workout.workout_id)).scalars().all()
        s.expunge_all()
        rpe = {wid: r for wid, r in s.execute(select(models.WorkoutNote.workout_id, models.WorkoutNote.rpe)) if r}
        carried = {wid for (wid,) in s.execute(select(models.WorkoutCarry.workout_id).where(models.WorkoutCarry.weight_kg > 0))}
        rhr = {d: v for d, v in s.execute(select(models.DailyMetric.local_date, models.DailyMetric.value).where(
            models.DailyMetric.metric == "resting_heart_rate", models.DailyMetric.value.is_not(None)))}
        hrv = {d: v for d, v in s.execute(select(models.DailyMetric.local_date, models.DailyMetric.value).where(
            models.DailyMetric.metric == "heart_rate_variability", models.DailyMetric.value.is_not(None)))}
        nights = [(d, x) for d, x in s.execute(select(models.DailyMetric.local_date, models.DailyMetric.extra).where(
            models.DailyMetric.metric == "sleep_analysis").order_by(models.DailyMetric.local_date)) if x]
        corrections = {d: h for d, h in s.execute(select(models.SleepCorrection.local_date, models.SleepCorrection.hours))}
        weather = {}
        if settings.read_weather_enabled(s):  # fetched weather is only an input while the runner has it on
            weather = {r.workout_id: {c: getattr(r, c) for c in _WEATHER_COLS}
                       for r in s.execute(select(models.WorkoutWeather).where(models.WorkoutWeather.status == "ok")).scalars()}

    nights = sleep.overlay(nights, corrections)  # the runner's hours, before any sleep math (AD-1)
    facts: list[summary.RunFacts] = []
    efforts: dict[str, dict[str, float]] = {}
    inputs: list[load_mod.WorkoutLoadInput] = []
    day_info: dict[str, days_mod.DayWorkout] = {}
    for w in workouts:
        try:
            with Session(ctx.engine) as s:
                cols = series.load_series(s, w.workout_id)
            rows, fact, best = _workout_rows(gid, w, cols, profile, zones, weather.get(w.workout_id),
                                             sleep.before_run(nights, w.start_utc, w.utc_offset_s, rhr, hrv, ctx.tz))
            hr = cols.get("heart_rate")
            samples = list(zip(active_clock(hr), hr["avg"])) if hr and profile.hrmax else None
            inp = load_mod.WorkoutLoadInput(
                w.workout_id, w.type, date.fromisoformat(w.local_date), w.duration_s,
                avg_hr=w.avg_hr if profile.hrmax else None, avg_speed_mps=w.avg_speed_mps, hr_samples=samples,
                rpe=rpe.get(w.workout_id))
            hard_s = days_mod.hard_seconds(samples, w.duration_s, profile.hrmax, load_params, day_params.hard_hr_fraction) if samples else 0.0
            generations.add_rows(ctx.engine, rows)  # a workout's rows commit together or not at all
            inputs.append(inp)
            day_info[w.workout_id] = days_mod.DayWorkout(
                w.type, w.duration_s or 0.0, 0.0, hard_s, fact.is_long_run if fact else False, w.effort_score, w.elevation_gain_m,
                w.workout_id in carried)
            if fact:  # counted in totals only once its rows are stored
                facts.append(fact)
                efforts[w.workout_id] = best
        except Exception as e:
            # AD-5: one bad workout is a data-quality issue and never fails the generation.
            log.warning("derive skipped a workout: %s", type(e).__name__)
            generations.add_rows(ctx.engine, [models.DataQualityIssue(
                generation_id=gid, workout_id=w.workout_id, stage="derive", error=type(e).__name__)])

    periods = summary.period_summaries(facts)
    generations.add_rows(ctx.engine, (models.PeriodSummary(generation_id=gid, **p) for p in periods))

    loads = []
    for inp in inputs:
        loads.append(load_mod.compute_workout_load(
            inp, hr_max=float(profile.hrmax or 0), hr_rest=resolve.window_median(rhr, inp.local_date, 7, resolve.RHR_PLAUSIBLE),
            sex=profile.sex, params=load_params, history=loads))
    generations.add_rows(ctx.engine, (_load_row(gid, wl, rpe.get(wl.workout_id), profile.hrmax) for wl in loads))
    if loads:
        _daily(ctx, th, load_params, loads, day_info)

    generations.add_rows(ctx.engine, (models.Record(generation_id=gid, **r)
                                      for r in records.build_records(facts, efforts, periods)))
    routes_stage.run(ctx, profile, zones)


def _load_row(gid: int, wl: load_mod.WorkoutLoad, rpe: int | None, hrmax: int | None) -> models.WorkoutLoad:
    return models.WorkoutLoad(
        generation_id=gid, workout_id=wl.workout_id, type=wl.type, local_date=wl.local_date.isoformat(), trimp=wl.trimp,
        estimated=wl.estimated, source=wl.source, coverage=wl.coverage, rpe=rpe,
        hr_max=wl.hr_max if hrmax else None, hr_rest=wl.hr_rest if hrmax else None, b=wl.b)


def _daily(ctx: Context, th, p: load_mod.LoadParams, loads: list[load_mod.WorkoutLoad],
           day_info: dict[str, days_mod.DayWorkout]) -> None:
    gid = ctx.generation_id
    start = min(wl.local_date for wl in loads)
    dl = load_mod.daily_loads(loads, start, ctx.as_of)
    fit = load_mod.fitness_fatigue(dl, p.tau_fitness_days, p.tau_fatigue_days, p.warmup_days, p.seed_days)
    states = load_mod.training_states(fit, th.section("training-state"))
    rows = []
    for i, (d, f, st) in enumerate(zip(dl, fit, states)):
        rows.append(models.DailyLoad(
            generation_id=gid, local_date=d.local_date.isoformat(), load=d.total, by_type=dict(d.by_type),
            estimated=d.estimated, n_workouts=d.n_workouts, fitness=f.fitness, fatigue=f.fatigue, form=f.form,
            form_pct=f.form_pct, warmup=f.warmup, acwr=load_mod.acwr(dl, i), ramp_pct=st.ramp_pct,
            raw_state=st.raw_state, training_state=st.state,
            state_since=st.since.isoformat() if st.since else None))
    generations.add_rows(ctx.engine, rows)

    by_day: dict[date, list[days_mod.DayWorkout]] = {}
    for wl in loads:
        w = day_info[wl.workout_id]
        by_day.setdefault(wl.local_date, []).append(
            days_mod.DayWorkout(w.type, w.duration_s, wl.trimp, w.hard_s, w.is_long_run, w.effort_score, w.elevation_gain_m, w.carried))
    classes = days_mod.classify_days(by_day, start, ctx.as_of, days_mod.DayParams.from_mapping(th.section("days")))
    generations.add_rows(ctx.engine, (models.DayClass(
        generation_id=gid, local_date=c.local_date.isoformat(), has_run=c.has_run, is_hard=c.is_hard, is_rest=c.is_rest,
        kind=c.kind, load=c.load, hard_seconds=c.hard_seconds, reasons=list(c.reasons)) for c in classes))


def _workout_rows(gid, w, cols, profile, zones, weather=None, night=None) -> tuple[list, summary.RunFacts | None, dict[str, float]]:
    hr, route = cols.get("heart_rate"), cols.get("route")
    rows: list = []
    fact = None
    if w.type == "run":
        zone_s = summary.zone_seconds(hr["avg"], profile.zone_bounds_bpm, hr_t=active_clock(hr)) if hr else None
        long_run = summary.is_long_run(w.distance_m, w.duration_s)
        fact = summary.RunFacts(w.workout_id, w.local_date, w.distance_m or 0.0, w.duration_s or 0.0,
                                w.elevation_gain_m, zone_s, long_run)
        mix = summary.intensity_mix(active_clock(hr), hr["avg"], w.duration_s, profile.easy_ceiling_bpm) if hr else None
        rows.append(models.WorkoutSummary(
            generation_id=gid, workout_id=w.workout_id, is_long_run=long_run, zone_seconds=zone_s,
            hr_time_s=mix[0] if mix else None, easy_time_s=mix[1] if mix else None, hr_coverage=mix[2] if mix else None,
            minutes=summary.minute_points(hr, route, w.duration_s)))
    detail = models.WorkoutDetail(generation_id=gid, workout_id=w.workout_id, sleep=night)
    if not w.is_indoor:
        detail.conditions = conditions.conditions(w.temperature_c, w.humidity_pct, weather, w.avg_speed_mps)
    display = None
    best: dict[str, float] = {}
    if hr:
        detail.hr_series = [{"t_s": t, "avg": a, "min": lo, "max": hi}
                            for t, a, lo, hi in zip(hr["t"], hr["avg"], hr["min"], hr["max"])]
    if route:
        # Time is active time (pauses removed) and the GPS distance is scaled to the watch's, so splits,
        # pace and best efforts agree with what the watch shows. An untrusted track keeps its own length.
        rt = active_clock(route)
        raw = track.cumulative_m(route["lat"], route["lon"])
        scale = (w.distance_m / raw[-1]) if w.distance_m and raw[-1] > 0 and records.gps_trustworthy(raw[-1], w.distance_m) else 1.0
        dist = [d * scale for d in raw]
        hr_t, hr_avg = (active_clock(hr), hr["avg"]) if hr else ([], [])
        own = cols.get("splits")
        detail.splits_km = (track.source_splits(own, "km", dist, route["alt"]) if own else None) \
            or track.splits(dist, rt, route["alt"], hr_t, hr_avg, 1000.0)
        detail.splits_mi = (track.source_splits(own, "mi", dist, route["alt"]) if own else None) \
            or track.splits(dist, rt, route["alt"], hr_t, hr_avg, M_PER_MILE)
        grade.add_to_splits(detail.splits_km, dist, route["alt"])
        grade.add_to_splits(detail.splits_mi, dist, route["alt"])
        detail.gap = grade.run_gap(dist, route["alt"], w.avg_speed_mps)
        detail.pace_series = track.pace_series(dist, rt)
        detail.elevation_series = track.elevation_series(dist, route["alt"])
        display = for_display(route, zones)
        if w.type == "run":
            best = records.best_efforts(dist, rt, w.distance_m)
            if own:
                best = records.best_from_splits(own, best)
    rows.append(detail)
    rows.append(models.WorkoutDisplay(generation_id=gid, workout_id=w.workout_id, display_geometry=display))
    rows.extend(models.BestEffort(generation_id=gid, workout_id=w.workout_id, distance_key=k, time_s=v)
                for k, v in best.items())
    return rows, fact, best
