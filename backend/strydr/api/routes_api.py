"""Routes, section comparisons and join/split overrides (FR-22, FR-23)."""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.api import schemas as sc
from strydr.api.common import Api, workout_out
from strydr.store import generations, models
from strydr.store.generations import in_current, scoped


def _route_out(r: models.Route) -> dict:
    return dict(route_key=r.route_key, run_count=r.run_count, distance_m=r.distance_m, first_date=r.first_date,
                last_date=r.last_date, sibling_key=r.sibling_key, display_geometry=r.display_geometry)


def router(api: Api) -> APIRouter:
    r = APIRouter(prefix="/routes", tags=["routes"], dependencies=api.auth)

    @r.get("", response_model=list[sc.RouteOut])
    def list_routes() -> list[sc.RouteOut]:
        with generations.read_snapshot(api.engine) as s:
            rows = s.execute(scoped(models.Route).order_by(models.Route.last_date.desc(), models.Route.route_key)).scalars()
            return [sc.RouteOut(**_route_out(x)) for x in rows]

    @r.get("/map", response_model=sc.RouteMapOut)
    def route_map() -> sc.RouteMapOut:
        """Every workout's clipped track on one map. Only `for_display` output is served (AD-10)."""
        with generations.read_snapshot(api.engine) as s:
            rows = s.execute(select(models.Workout.workout_id, models.Workout.type, models.Workout.local_date,
                                    models.WorkoutDisplay.display_geometry)
                             .join(models.WorkoutDisplay, models.WorkoutDisplay.workout_id == models.Workout.workout_id)
                             .where(in_current(models.WorkoutDisplay))
                             .order_by(models.Workout.start_utc)).all()
        return sc.RouteMapOut(lines=[sc.RouteMapLine(workout_id=wid, type=wtype, local_date=day, display_geometry=g)
                                     for wid, wtype, day, g in rows if g])  # JSON null: nothing left after clipping

    # Declared before /{route_key} so "overrides" is never read as a route key.
    @r.get("/overrides", response_model=list[sc.RouteOverrideOut])
    def list_overrides() -> list[sc.RouteOverrideOut]:
        with Session(api.engine) as s:
            return [sc.RouteOverrideOut(workout_a=o.workout_a, workout_b=o.workout_b, action=o.action)
                    for o in s.execute(select(models.RouteOverride).order_by(
                        models.RouteOverride.workout_a, models.RouteOverride.workout_b)).scalars()]

    @r.post("/overrides", response_model=sc.RouteOverrideOut, status_code=201)
    def add_override(body: sc.RouteOverrideIn) -> sc.RouteOverrideOut:
        a, b = sorted((body.workout_a, body.workout_b))  # the pair is unordered (AD-6)
        with Session(api.engine) as s:
            known = set(s.execute(select(models.Workout.workout_id).where(models.Workout.workout_id.in_((a, b)))).scalars())
            if known != {a, b}:
                raise HTTPException(status_code=404, detail="workout not found")
            row = s.get(models.RouteOverride, (a, b)) or models.RouteOverride(workout_a=a, workout_b=b)
            row.action = body.action
            s.add(row)
            api.enqueue_recompute(s)  # AD-1: route_override is a pipeline input
            s.commit()
        api.wake()
        return sc.RouteOverrideOut(workout_a=a, workout_b=b, action=body.action)

    @r.delete("/overrides", status_code=204)
    def delete_override(workout_a: str = Query(), workout_b: str = Query()) -> None:
        a, b = sorted((workout_a, workout_b))
        with Session(api.engine) as s:
            row = s.get(models.RouteOverride, (a, b))
            if row is not None:
                s.delete(row)
                api.enqueue_recompute(s)
                s.commit()
        api.wake()

    @r.get("/{route_key}", response_model=sc.RouteDetailOut)
    def get_route(route_key: str) -> sc.RouteDetailOut:
        with generations.read_snapshot(api.engine) as s:
            route = s.execute(scoped(models.Route, models.Route.route_key == route_key)).scalar_one_or_none()
            if route is None:
                raise HTTPException(status_code=404, detail="route not found")
            sections = s.execute(scoped(models.RouteSection, models.RouteSection.route_key == route_key)
                                 .order_by(models.RouteSection.kind.desc(), models.RouteSection.idx)).scalars().all()
            results = s.execute(scoped(models.SectionResult, models.SectionResult.route_key == route_key)
                                .order_by(models.SectionResult.local_date.desc(), models.SectionResult.section_id)).scalars().all()
            ids = list(s.execute(select(models.WorkoutRoute.workout_id).where(
                in_current(models.WorkoutRoute), models.WorkoutRoute.route_key == route_key)).scalars())
            ws = s.execute(select(models.Workout).where(models.Workout.workout_id.in_(ids))
                           .order_by(models.Workout.start_utc.desc())).scalars().all()
            names: dict[str, set[str]] = {}
            for wid, name in s.execute(select(models.SampleSeries.workout_id, models.SampleSeries.series)
                                       .where(models.SampleSeries.workout_id.in_(ids))):
                names.setdefault(wid, set()).add(name)
            long_runs = dict(s.execute(select(models.WorkoutSummary.workout_id, models.WorkoutSummary.is_long_run).where(
                in_current(models.WorkoutSummary), models.WorkoutSummary.workout_id.in_(ids))).all())
            return sc.RouteDetailOut(
                **_route_out(route),
                sections=[sc.SectionOut(section_id=x.section_id, kind=x.kind, index=x.idx, start_m=x.start_m, end_m=x.end_m,
                                        length_m=x.end_m - x.start_m, gain_m=x.gain_m) for x in sections],
                runs=[workout_out(w, names.get(w.workout_id, set()), long_runs.get(w.workout_id)) for w in ws],
                results=[sc.SectionResultOut(
                    section_id=x.section_id, workout_id=x.workout_id, local_date=x.local_date, time_s=x.time_s, avg_hr=x.avg_hr,
                    comparable=x.comparable, n=x.n, baseline_time_s=x.baseline_time_s, baseline_hr=x.baseline_hr, gap_s=x.gap_s,
                    spread_s=x.spread_s, z=x.z, direction=x.direction, fires=x.fires, reasons=list(x.reasons)) for x in results])

    return r
