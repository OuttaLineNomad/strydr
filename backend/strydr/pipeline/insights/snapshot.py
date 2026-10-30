"""Builds the `DerivedSnapshot` the rules read, from the generation being built plus canonical rows (AD-8).

Reads only stored tables. `gid` is the new generation: it is not the current one yet.
"""
import calendar
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.pipeline.context import Context
from strydr.pipeline.derive import records, summary
from strydr.pipeline.derive.days import DayClass
from strydr.pipeline.derive.load.model import TrainingStateDay
from strydr.pipeline.insights.models import (
    Baseline, BestEffort, DailyValue, DerivedSnapshot, MinutePoint, PeriodVolume, RunSummary,
)
from strydr.pipeline.profile import Profile
from strydr.store import models

MINUTES_WINDOW_DAYS = 84  # per-minute series are only kept for runs the windowed rules can reach (pace-at-fixed-hr: 2 x 28 + margin)
DAILY_WINDOW_DAYS = 120
LABELS = {"1km": "1k", "1mi": "1mi", "5km": "5k", "10km": "10k", "half": "half", "marathon": "marathon"}


def _baseline(mean, sd, n) -> Baseline | None:
    return None if mean is None else Baseline(mean, sd or 0.0, n or 0)


def build(ctx: Context, profile: Profile) -> DerivedSnapshot:
    gid, as_of = ctx.generation_id, ctx.as_of
    iso = as_of.isoformat()
    since_minutes = (as_of - timedelta(days=MINUTES_WINDOW_DAYS)).isoformat()
    since_daily = (as_of - timedelta(days=DAILY_WINDOW_DAYS)).isoformat()
    with Session(ctx.engine) as s:
        first = s.execute(select(models.Workout.local_date).order_by(models.Workout.local_date).limit(1)).scalar_one_or_none()
        workouts = s.execute(select(models.Workout).where(models.Workout.type == "run", models.Workout.local_date <= iso)
                             .order_by(models.Workout.start_utc, models.Workout.workout_id)).scalars().all()
        summ = {r.workout_id: r for r in s.execute(select(models.WorkoutSummary).where(models.WorkoutSummary.generation_id == gid)).scalars()}
        extra = {wid: (c, g, z) for wid, c, g, z in s.execute(select(
            models.WorkoutDetail.workout_id, models.WorkoutDetail.conditions, models.WorkoutDetail.gap,
            models.WorkoutDetail.sleep).where(
            models.WorkoutDetail.generation_id == gid))}
        hard = {d for (d,) in s.execute(select(models.DayClass.local_date).where(
            models.DayClass.generation_id == gid, models.DayClass.is_hard.is_(True)))}
        rpe = {wid: r for wid, r in s.execute(select(models.WorkoutNote.workout_id, models.WorkoutNote.rpe)) if r}
        carry = {wid: kg for wid, kg in s.execute(select(models.WorkoutCarry.workout_id, models.WorkoutCarry.weight_kg)) if kg and kg > 0}
        periods = s.execute(select(models.PeriodSummary).where(models.PeriodSummary.generation_id == gid)).scalars().all()
        effort_rows = s.execute(select(models.BestEffort).where(models.BestEffort.generation_id == gid)).scalars().all()
        day_rows = s.execute(select(models.DayClass).where(models.DayClass.generation_id == gid)
                             .order_by(models.DayClass.local_date)).scalars().all()
        today = s.get(models.DailyLoad, (gid, iso))
        daily = {m: [(d, v) for d, v in s.execute(select(models.DailyMetric.local_date, models.DailyMetric.value).where(
            models.DailyMetric.metric == m, models.DailyMetric.value.is_not(None), models.DailyMetric.local_date >= since_daily,
            models.DailyMetric.local_date <= iso).order_by(models.DailyMetric.local_date))]
            for m in ("resting_heart_rate", "heart_rate_variability")}

    runs = []
    for w in workouts:
        sm = summ.get(w.workout_id)
        if sm is None:  # derive skipped this workout (data-quality issue)
            continue
        mins = None
        if sm.minutes is not None and w.local_date >= since_minutes:
            mins = tuple(MinutePoint(*m) for m in sm.minutes)
        runs.append(RunSummary(
            w.workout_id, date.fromisoformat(w.local_date), w.distance_m, w.duration_s, w.avg_speed_mps, w.avg_hr,
            w.elevation_gain_m, w.temperature_c, w.is_indoor, sm.is_long_run,
            summary.is_easy_intended(sm.is_long_run, w.local_date in hard, rpe.get(w.workout_id)),
            sm.hr_time_s, sm.easy_time_s, sm.hr_coverage, mins, *extra.get(w.workout_id, (None, None, None)),
            carry_kg=carry.get(w.workout_id)))

    vols = {"week": [], "month": []}
    for p in periods:
        start = date.fromisoformat(p.start_date)
        end = start + timedelta(days=6) if p.kind == "week" else start.replace(day=calendar.monthrange(start.year, start.month)[1])
        vols[p.kind].append(PeriodVolume(p.period_id, start, end, p.distance_m, p.duration_s, p.run_count))
    for v in vols.values():
        v.sort(key=lambda x: x.start)

    state = None
    if today is not None:
        state = TrainingStateDay(
            as_of, today.raw_state, today.training_state, date.fromisoformat(today.state_since) if today.state_since else None,
            today.ramp_pct, today.form_pct)

    ceiling = profile.easy_ceiling_bpm
    return DerivedSnapshot(
        as_of=as_of, units="mi" if profile.units == "imperial" else "km",
        hr_max=float(profile.hrmax or 0), easy_ceiling_bpm=float(ceiling) if ceiling is not None else 0.0,
        history_start=date.fromisoformat(first) if first else None, runs=tuple(runs),
        weekly=tuple(vols["week"]), monthly=tuple(vols["month"]), best_efforts=tuple(_best_efforts(workouts, effort_rows)),
        days=tuple(DayClass(date.fromisoformat(d.local_date), d.has_run, d.is_hard, d.is_rest, d.kind, d.load,
                            d.hard_seconds, tuple(d.reasons)) for d in day_rows),
        training_state=state,
        resting_hr=tuple(DailyValue(date.fromisoformat(d), v) for d, v in daily["resting_heart_rate"]),
        rhr_baseline=_baseline(*(getattr(profile.rhr_baseline, f, None) for f in ("mean", "sd", "n_days"))),
        hrv_sdnn_ms=tuple(DailyValue(date.fromisoformat(d), v) for d, v in daily["heart_rate_variability"]),
        hrv_baseline=_baseline(*(getattr(profile.hrv_baseline, f, None) for f in ("mean", "sd", "n_days"))),
        carried_run_dates=frozenset(r.local_date for r in runs if r.carry_kg),
    )


def _best_efforts(workouts, rows) -> list[BestEffort]:
    """`is_record`: faster than every earlier effort at that distance. A first effort has nothing to beat."""
    by_run = {}
    for r in rows:
        by_run.setdefault(r.workout_id, {})[r.distance_key] = r.time_s
    best: dict[str, float] = {}
    out = []
    for w in workouts:
        for key, t in sorted(by_run.get(w.workout_id, {}).items()):
            prev = best.get(key)
            out.append(BestEffort(w.workout_id, date.fromisoformat(w.local_date), LABELS[key], records.DISTANCES_M[key], t,
                                  is_record=prev is not None and t < prev, gps_ok=True))
            best[key] = t if prev is None else min(prev, t)
    return out
