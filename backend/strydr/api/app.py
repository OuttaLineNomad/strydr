"""App-port FastAPI app: /api/v1/* behind a session cookie (AD-11), plus the built SPA. Reads tables only (AD-2)."""
from pathlib import Path
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from strydr import relabel
from strydr.api import calendar, import_api, insights, load, privacy, routes_api, settings_api, shoes, weeks
from strydr.api import schemas as sc
from strydr.api.common import Api, rfc3339, workout_out
from strydr.auth import sessions
from strydr.jobs import queue
from strydr.pipeline.phrasing import summary as summary_mod
from strydr.store import generations, models, settings
from strydr.store.generations import in_current, scoped
from strydr.store.util import utcnow

STALE_AFTER = timedelta(days=7)  # FR-6
MILE_M = 1609.344


def _note_out(n: models.WorkoutNote | None) -> sc.NoteOut | None:
    return sc.NoteOut(text=n.text, rpe=n.rpe, updated_at=rfc3339(n.updated_at)) if n else None


def create_app(engine: Engine | None, default_tz: str = "UTC", web_dist: Path | None = None) -> FastAPI:
    """`engine` may be None only to export the OpenAPI schema. `web_dist` is the built SPA, served on this port."""
    app = FastAPI(title="strydr", docs_url=None, redoc_url=None,
                  generate_unique_id_function=lambda route: route.name)
    router = APIRouter(prefix="/api/v1")

    def require_user(request: Request) -> int:
        uid = sessions.user_for_session(engine, request.cookies.get(sessions.COOKIE))
        if uid is None:
            raise HTTPException(status_code=401, detail="not authenticated")
        return uid

    auth = [Depends(require_user)]

    def recompute_enqueue(s: Session) -> None:
        queue.enqueue_recompute(s, queue.local_today(settings.read(s, default_tz).home_tz))

    @router.get("/health", response_model=sc.HealthOut, tags=["health"])
    def health() -> sc.HealthOut:
        """Liveness for the container healthcheck. Public by design: no DB access, no key, no version, no data."""
        return sc.HealthOut(status="ok")

    @router.post("/auth/login", status_code=204)
    def login(body: sc.LoginIn, response: Response) -> None:
        raw = sessions.login(engine, body.username, body.password)
        if raw is None:
            raise HTTPException(status_code=401, detail="invalid credentials")
        response.set_cookie(sessions.COOKIE, raw, httponly=True, samesite="strict",
                            max_age=int(sessions.TTL.total_seconds()), path="/")

    @router.post("/auth/logout", status_code=204)
    def logout(request: Request, response: Response) -> None:
        sessions.logout(engine, request.cookies.get(sessions.COOKIE))
        response.delete_cookie(sessions.COOKIE, path="/")

    @router.get("/sync-status", response_model=sc.SyncStatus, dependencies=auth)
    def sync_status() -> sc.SyncStatus:
        with Session(engine) as s:
            last = s.execute(select(func.max(models.RawPayload.received_at))
                             .where(models.RawPayload.status == "processed")).scalar_one()  # AD-3
            bad = s.execute(select(models.RawPayload).where(models.RawPayload.status == "quarantined")
                            .order_by(models.RawPayload.received_at.desc())).scalars().all()
            return sc.SyncStatus(
                last_processed_at=rfc3339(last),
                stale=last is None or utcnow() - last > STALE_AFTER,
                stale_after_days=STALE_AFTER.days,
                quarantined=[sc.QuarantinedPayload(id=p.id, received_at=rfc3339(p.received_at),
                                                   size_bytes=p.size_bytes, error=p.error) for p in bad],
            )

    @router.get("/workouts", response_model=list[sc.WorkoutOut], dependencies=auth)
    def workouts(type: str | None = Query(None, description="run, walk or hike; a comma list such as walk,hike"),
                 limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> list[sc.WorkoutOut]:
        with generations.read_snapshot(engine) as s:
            q = select(models.Workout).order_by(models.Workout.start_utc.desc()).limit(limit).offset(offset)
            if type:
                kinds = [x.strip() for x in type.split(",")]
                if not all(k in relabel.TYPES for k in kinds):
                    raise HTTPException(status_code=422, detail="type must be run, walk or hike, or a comma list of them")
                q = q.where(models.Workout.type.in_(kinds))
            rows = s.execute(q).scalars().all()
            ids = [r.workout_id for r in rows]
            names: dict[str, set[str]] = {}
            long_runs: dict[str, bool] = {}
            if ids:
                for wid, name in s.execute(select(models.SampleSeries.workout_id, models.SampleSeries.series)
                                           .where(models.SampleSeries.workout_id.in_(ids))):
                    names.setdefault(wid, set()).add(name)
                long_runs = dict(s.execute(select(models.WorkoutSummary.workout_id, models.WorkoutSummary.is_long_run)
                                           .where(in_current(models.WorkoutSummary), models.WorkoutSummary.workout_id.in_(ids))).all())
            carry: dict[str, float] = {}
            if ids:
                carry = dict(s.execute(select(models.WorkoutCarry.workout_id, models.WorkoutCarry.weight_kg)
                                       .where(models.WorkoutCarry.workout_id.in_(ids))).all())
            return [workout_out(w, names.get(w.workout_id, set()), long_runs.get(w.workout_id), carry.get(w.workout_id))
                    for w in rows]

    @router.get("/workouts/{workout_id}", response_model=sc.WorkoutDetailOut, dependencies=auth)
    def workout_detail(workout_id: str) -> sc.WorkoutDetailOut:
        with generations.read_snapshot(engine) as s:
            w = s.execute(select(models.Workout).where(models.Workout.workout_id == workout_id)).scalar_one_or_none()
            if w is None:
                raise HTTPException(status_code=404, detail="workout not found")
            names = set(s.execute(select(models.SampleSeries.series)
                                  .where(models.SampleSeries.workout_id == workout_id)).scalars())
            summary = s.execute(scoped(models.WorkoutSummary, models.WorkoutSummary.workout_id == workout_id)).scalar_one_or_none()
            detail = s.execute(scoped(models.WorkoutDetail, models.WorkoutDetail.workout_id == workout_id)).scalar_one_or_none()
            display = s.execute(scoped(models.WorkoutDisplay, models.WorkoutDisplay.workout_id == workout_id)).scalar_one_or_none()
            issues = s.execute(select(models.DataQualityIssue.stage).where(
                in_current(models.DataQualityIssue), models.DataQualityIssue.workout_id == workout_id)).scalars().all()
            note = s.get(models.WorkoutNote, workout_id)
            shoe = shoes.shoe_out_for(s, workout_id, w)
            carry = s.get(models.WorkoutCarry, workout_id)
            carry_kg = carry.weight_kg if carry else None
            served = summary_mod.serve(s, workout_id, default_tz)
            fb = s.get(models.InsightFeedback, f"run-summary/{workout_id}")
            # a thumb belongs to the summary it was given on: it resets when the context changes
            thumb = fb.thumb if fb and served and (fb.snapshot or {}).get("context_hash") == served[2] else None
            return sc.WorkoutDetailOut(
                summary=None if served is None else sc.RunSummaryOut(
                    text=served[0], source=served[1], key=f"run-summary/{workout_id}", thumb=thumb),
                workout=workout_out(w, names, summary.is_long_run if summary else None, carry_kg), carry_kg=carry_kg,
                max_speed_mps=w.max_speed_mps, avg_cadence=w.avg_cadence, temperature_c=w.temperature_c,
                humidity_pct=w.humidity_pct, effort_score=w.effort_score, effort_estimated=w.effort_estimated,
                zone_seconds=summary.zone_seconds if summary else None,
                splits_km=detail.splits_km if detail else None, splits_mi=detail.splits_mi if detail else None,
                hr_series=detail.hr_series if detail else None, pace_series=detail.pace_series if detail else None,
                elevation_series=detail.elevation_series if detail else None,
                conditions=detail.conditions if detail else None, gap=detail.gap if detail else None,
                sleep=detail.sleep if detail else None,
                display_geometry=display.display_geometry if display else None,
                quality_flags=w.quality_flags or {}, data_quality_issues=list(issues), note=_note_out(note), shoe=shoe,
                shoe_chosen=s.get(models.WorkoutShoe, workout_id) is not None,
            )

    @router.put("/workouts/{workout_id}/type", response_model=sc.WorkoutTypeOut, dependencies=auth)
    def put_workout_type(workout_id: str, body: sc.WorkoutTypeIn) -> sc.WorkoutTypeOut:
        with Session(engine) as s:
            w = s.execute(select(models.Workout).where(models.Workout.workout_id == workout_id)).scalar_one_or_none()
            if w is None:
                raise HTTPException(status_code=404, detail="workout not found")
            if w.type != body.type:
                relabel.set_type(s, workout_id, body.type, default_tz)  # override, type and recompute job commit together
                s.commit()
        queue.wakeup.set()
        return sc.WorkoutTypeOut(workout_id=workout_id, type=body.type)

    @router.put("/workouts/{workout_id}/carry", response_model=sc.WorkoutCarryOut, dependencies=auth)
    def put_carry(workout_id: str, body: sc.WorkoutCarryIn) -> sc.WorkoutCarryOut:
        with Session(engine) as s:
            if s.execute(select(models.Workout.id).where(models.Workout.workout_id == workout_id)).first() is None:
                raise HTTPException(status_code=404, detail="workout not found")
            row = s.get(models.WorkoutCarry, workout_id) or models.WorkoutCarry(workout_id=workout_id)
            row.weight_kg, row.updated_at = body.weight_kg, utcnow()
            s.add(row)
            recompute_enqueue(s)  # carry is a pipeline input: carried runs are compared only with carried runs
            s.commit()
        queue.wakeup.set()
        return sc.WorkoutCarryOut(carry_kg=body.weight_kg)

    @router.delete("/workouts/{workout_id}/carry", response_model=sc.WorkoutCarryOut, dependencies=auth)
    def delete_carry(workout_id: str) -> sc.WorkoutCarryOut:
        with Session(engine) as s:
            if s.execute(select(models.Workout.id).where(models.Workout.workout_id == workout_id)).first() is None:
                raise HTTPException(status_code=404, detail="workout not found")
            row = s.get(models.WorkoutCarry, workout_id)
            if row is not None:
                s.delete(row)
                recompute_enqueue(s)
                s.commit()
        queue.wakeup.set()
        return sc.WorkoutCarryOut(carry_kg=None)

    @router.put("/workouts/{workout_id}/note", response_model=sc.NoteOut, dependencies=auth)
    def put_note(workout_id: str, body: sc.NoteIn) -> sc.NoteOut:
        with Session(engine) as s:
            if s.execute(select(models.Workout.id).where(models.Workout.workout_id == workout_id)).first() is None:
                raise HTTPException(status_code=404, detail="workout not found")
            note = s.get(models.WorkoutNote, workout_id) or models.WorkoutNote(workout_id=workout_id)
            note.text, note.rpe, note.updated_at = (body.text or "").strip() or None, body.rpe, utcnow()
            s.add(note)
            recompute_enqueue(s)  # RPE is a pipeline input (AD-1); the write and its job commit together (AD-5)
            s.commit()
            out = _note_out(note)
        queue.wakeup.set()
        return out

    @router.delete("/workouts/{workout_id}/note", status_code=204, dependencies=auth)
    def delete_note(workout_id: str) -> None:
        with Session(engine) as s:
            note = s.get(models.WorkoutNote, workout_id)
            if note is not None:
                s.delete(note)
                recompute_enqueue(s)
                s.commit()
        queue.wakeup.set()

    @router.get("/dashboard", response_model=sc.DashboardOut, dependencies=auth)
    def dashboard(weeks: int = Query(12, ge=1, le=520, description="how many ISO weeks to show, ending with as_of's")) -> sc.DashboardOut:
        with generations.read_snapshot(engine) as s:
            gen = s.execute(select(models.Generation).join(
                models.CurrentGeneration, models.CurrentGeneration.generation_id == models.Generation.id)).scalar_one_or_none()
            if gen is None:
                return sc.DashboardOut(as_of=None, weeks=[], one_mile_pace=_tile(None, None),
                                       avg_pace=_tile(None, None))
            monday = date.fromisoformat(gen.as_of) - timedelta(days=date.fromisoformat(gen.as_of).weekday())
            starts = [monday - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
            ids = [d.strftime("%G-W%V") for d in starts]
            have = {p.period_id: p for p in s.execute(scoped(
                models.PeriodSummary, models.PeriodSummary.kind == "week", models.PeriodSummary.period_id.in_(ids))).scalars()}
            totals = [sc.WeekTotal(week_id=i, week_start=d.isoformat(),
                                   distance_m=have[i].distance_m if i in have else 0.0,
                                   duration_s=have[i].duration_s if i in have else 0.0,
                                   run_count=have[i].run_count if i in have else 0) for i, d in zip(ids, starts)]
            recs = {r.key: r for r in s.execute(scoped(models.Record)).scalars()}
            pr_mile = recs.get("best_1mi")
            return sc.DashboardOut(
                as_of=gen.as_of, weeks=totals,
                one_mile_pace=_tile(recs.get("latest_1mi"), pr_mile, MILE_M / pr_mile.value if pr_mile else None),
                avg_pace=_tile(recs.get("latest_avg_pace"), recs.get("best_avg_pace")),
            )

    @router.get("/records", response_model=list[sc.RecordOut], dependencies=auth)
    def records() -> list[sc.RecordOut]:
        with generations.read_snapshot(engine) as s:
            rows = s.execute(scoped(models.Record).order_by(models.Record.key)).scalars().all()
            return [sc.RecordOut(key=r.key, value=r.value, unit=r.unit, workout_id=r.workout_id,
                                 local_date=r.local_date, period_id=r.period_id)
                    for r in rows if not r.key.startswith("latest_")]

    def profile_out(s: Session) -> sc.ProfileOut:
        cfg = settings.read(s, default_tz)
        gen = s.execute(select(models.Generation).join(
            models.CurrentGeneration, models.CurrentGeneration.generation_id == models.Generation.id)).scalar_one_or_none()
        prof = s.execute(scoped(models.ProfileResult)).scalar_one_or_none()
        resolved = sc.ResolvedProfile(
            as_of=gen.as_of, hrmax=prof.hrmax, hrmax_source=prof.hrmax_source, zone_bounds_bpm=prof.zone_bounds_bpm,
            easy_ceiling_bpm=prof.easy_ceiling_bpm, rhr_7d_median=prof.rhr_7d_median,
            rhr_30d_baseline=prof.rhr_30d_baseline, hrv_60d_baseline=prof.hrv_60d_baseline) if gen and prof else None
        pending = s.execute(select(models.Job.id).where(models.Job.type == "recompute",
                                                       models.Job.status.in_(("pending", "running"))).limit(1)).first()
        return sc.ProfileOut(
            settings=sc.ProfileSettings(birth_year=cfg.birth_year, sex=cfg.sex, hrmax_override=cfg.hrmax_override,
                                        zones=cfg.zones, units=cfg.units, home_tz=cfg.home_tz),
            zone_bounds_pct=cfg.zone_bounds_pct, resolved=resolved, recompute_pending=pending is not None)

    @router.get("/profile", response_model=sc.ProfileOut, dependencies=auth)
    def get_profile() -> sc.ProfileOut:
        with generations.read_snapshot(engine) as s:
            return profile_out(s)

    @router.put("/profile", response_model=sc.ProfileOut, dependencies=auth)
    def put_profile(body: sc.ProfileSettings) -> sc.ProfileOut:
        with Session(engine) as s:
            settings.write(s, settings.UserSettings(**body.model_dump()))
            recompute_enqueue(s)  # AD-5: the write and the recompute it implies commit together
            s.commit()
            out = profile_out(s)
        queue.wakeup.set()
        return out

    shared = Api(engine, default_tz, auth)
    for sub in (insights, weeks, calendar, load, routes_api, privacy, settings_api, import_api, shoes):
        router.include_router(sub.router(shared))
    app.include_router(router)
    if web_dist is not None and web_dist.is_dir():
        _serve_spa(app, web_dist.resolve())
    return app


def _serve_spa(app: FastAPI, dist: Path) -> None:
    """Static assets, and every other non-/api GET falls back to index.html for client-side routing."""
    index = dist / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        target = (dist / path).resolve()
        if path and target.is_file() and target.is_relative_to(dist):
            immutable = path.startswith("assets/")  # build output is content-hashed
            return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache"})
        if not index.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


def _tile(latest: models.Record | None, pr: models.Record | None, pr_speed: float | None = None) -> sc.Tile:
    return sc.Tile(
        latest_speed_mps=latest.value if latest else None,
        latest_workout_id=latest.workout_id if latest else None, latest_local_date=latest.local_date if latest else None,
        pr_speed_mps=pr_speed if pr_speed is not None else (pr.value if pr else None),
        pr_workout_id=pr.workout_id if pr else None, pr_local_date=pr.local_date if pr else None,
    )
