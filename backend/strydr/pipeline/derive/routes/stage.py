"""Routes stage: cluster runs, cut sections and climbs, compare sections, clip display geometry (AD-7, AD-10)."""
import logging
from collections.abc import Iterator
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.pipeline.context import Context
from strydr.pipeline.derive.routes import compare, matching, sections as sec
from strydr.pipeline.derive.routes.climbs import route_climbs
from strydr.pipeline.derive.routes.display import for_display
from strydr.sources.canonical import SampleSeries, Workout
from strydr.store import generations, models, series, settings

log = logging.getLogger("strydr.routes")


def _canonical(engine, w: models.Workout) -> Workout:
    with Session(engine) as s:
        cols = series.load_series(s, w.workout_id)
    return Workout(
        workout_id=w.workout_id, type=w.type, is_indoor=w.is_indoor, start_utc=w.start_utc, end_utc=w.end_utc,
        utc_offset_s=w.utc_offset_s, local_date=w.local_date, duration_s=w.duration_s, distance_m=w.distance_m,
        series={name: SampleSeries(name, c) for name, c in cols.items() if name in ("route", "heart_rate")})


def run(ctx: Context, profile, zones) -> None:
    gid, rt = ctx.generation_id, matching.load_thresholds()
    with Session(ctx.engine) as s:
        overrides = [(o.workout_a, o.workout_b, o.action) for o in s.execute(select(models.RouteOverride)).scalars()]
        units = settings.read(s, ctx.tz.key).units
        has_route = select(models.SampleSeries.id).where(
            models.SampleSeries.workout_id == models.Workout.workout_id, models.SampleSeries.series == "route").exists()
        rows = s.execute(select(models.Workout).where(
            models.Workout.type.in_(rt.workout_types), models.Workout.is_indoor.is_(False), has_route,
            models.Workout.local_date <= ctx.as_of.isoformat()).order_by(models.Workout.start_utc)).scalars().all()
        s.expunge_all()
    by_id = {w.workout_id: w for w in rows}

    def lazy() -> Iterator[Workout]:  # one run's track in memory at a time
        for w in rows:
            yield _canonical(ctx.engine, w)

    try:
        clusters = matching.cluster(lazy(), overrides, rt)  # cluster() iterates its input once
    except Exception as e:
        log.warning("route clustering failed: %s", type(e).__name__)
        generations.add_rows(ctx.engine, [models.DataQualityIssue(
            generation_id=gid, workout_id=None, stage="routes", error=type(e).__name__)])
        return
    for c in clusters:
        try:
            generations.add_rows(ctx.engine, _route_rows(ctx, rt, c, by_id, units, zones))
        except Exception as e:
            log.warning("route skipped: %s", type(e).__name__)
            generations.add_rows(ctx.engine, [models.DataQualityIssue(
                generation_id=gid, workout_id=c.route_key, stage="routes", error=type(e).__name__)])


def _route_rows(ctx: Context, rt, c: matching.RouteCluster, by_id, units: str, zones) -> list:
    gid = ctx.generation_id
    ref_w = _canonical(ctx.engine, by_id[c.reference_id])
    ref = matching.build_path(ref_w, rt)
    splits = sec.fixed_splits(c.route_key, ref.length_m, sec.split_unit_m(units, rt), rt)
    sections = splits + route_climbs(c.route_key, ref, rt)

    obs: dict[str, list[compare.SectionObs]] = {}
    for wid in c.member_ids:
        w = ref_w if wid == c.reference_id else _canonical(ctx.engine, by_id[wid])
        path = ref if wid == c.reference_id else matching.build_path(w, rt)
        if path is None:
            continue
        measures = sec.measure_run(ref, path, sections, sec.hr_from_workout(w), rt)
        obs[wid] = compare.observations(wid, date.fromisoformat(w.local_date), measures.values())
    history = [o for os_ in obs.values() for o in os_]

    dates = [by_id[w].local_date for w in c.member_ids]
    rows: list = [
        models.Route(generation_id=gid, route_key=c.route_key, run_count=len(c.member_ids), reference_id=c.reference_id,
                     sibling_key=c.sibling_key, distance_m=c.reference_length_m, first_date=min(dates), last_date=max(dates),
                     display_geometry=for_display(ref_w.series["route"].columns, zones))]
    rows += [models.WorkoutRoute(generation_id=gid, workout_id=wid, route_key=c.route_key) for wid in c.member_ids]
    rows += [models.RouteSection(generation_id=gid, section_id=s.section_id, route_key=c.route_key, kind=s.kind, idx=s.index,
                                 start_m=s.start_m, end_m=s.end_m, gain_m=s.gain_m) for s in sections]
    for wid, current in obs.items():
        # Each run is compared as of its own date, so the 180-day window and "earlier runs" mean what FR-23a says.
        for cmp in compare.compare_run(current, history, date.fromisoformat(by_id[wid].local_date), rt):
            o = next(x for x in current if x.section_id == cmp.section_id)
            rows.append(models.SectionResult(
                generation_id=gid, section_id=cmp.section_id, workout_id=wid, route_key=c.route_key,
                local_date=by_id[wid].local_date, time_s=o.time_s, avg_hr=o.avg_hr, comparable=o.comparable, n=cmp.n,
                baseline_time_s=cmp.baseline_time_s, baseline_hr=cmp.baseline_hr, gap_s=cmp.gap_s, spread_s=cmp.spread_s,
                z=cmp.z, direction=cmp.direction, fires=cmp.fires, reasons=list(cmp.reasons)))
    return rows
