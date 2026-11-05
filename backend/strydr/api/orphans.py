"""Orphan watch workouts: strength workouts from the watch that no session overlaps. Strydr asks once per workout
(with a guess from history) and logs it as a session on the watch's times, or remembers it is not a Strydr workout.
User table only: nothing here enqueues a recompute."""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr import sessions_summary as ss
from strydr.api import schemas as sc
from strydr.api.common import Api, rfc3339
from strydr.api.sessions import session_out
from strydr.jobs import queue
from strydr.store import models, settings
from strydr.store.util import utcnow

WINDOW_DAYS = 14


def _local(dt: datetime, tz: ZoneInfo):
    return dt.replace(tzinfo=UTC).astimezone(tz)


def is_orphan(s: Session, w: models.Workout) -> bool:
    """No session matches the workout by the same rule the summary uses (see `ss.match`)."""
    cands = s.execute(select(models.WorkoutSession).where(
        models.WorkoutSession.start_utc < w.end_utc, models.WorkoutSession.end_utc > w.start_utc)).scalars()
    return not any(ss.match(m.start_utc, m.end_utc, [w]) is not None for m in cands)


def _plan_partial(plan: models.WorkoutPlan, n: int) -> int:
    return max(0, min(n, len(plan.moves) - 1))


def guess_for(s: Session, w: models.Workout, tz: ZoneInfo) -> sc.OrphanGuess | None:
    """The latest session on the same local weekday that started before the workout and whose plan still exists;
    else the latest of any day."""
    rows = s.execute(select(models.WorkoutSession).where(
        models.WorkoutSession.start_utc < w.start_utc, models.WorkoutSession.plan_id.is_not(None))
        .order_by(models.WorkoutSession.start_utc.desc(), models.WorkoutSession.id.desc())).scalars().all()
    plans: dict[int, models.WorkoutPlan | None] = {}
    eligible = []
    for m in rows:
        if m.plan_id not in plans:
            plans[m.plan_id] = s.get(models.WorkoutPlan, m.plan_id)
        if plans[m.plan_id] is not None:
            eligible.append(m)
    if not eligible:
        return None
    wd = _local(w.start_utc, tz).weekday()
    same = next((m for m in eligible if _local(m.start_utc, tz).weekday() == wd), None)
    m = same or eligible[0]
    p = plans[m.plan_id]
    return sc.OrphanGuess(plan_id=p.id, plan_name=p.name, weight_kg=m.weight_kg, rounds_done=m.rounds_done,
                          partial_moves=_plan_partial(p, m.partial_moves), format=p.format,
                          session_date=_local(m.start_utc, tz).date().isoformat(), same_weekday=same is not None)


def orphans(s: Session, tz_name: str) -> list[models.Workout]:
    tz = ZoneInfo(tz_name)
    cutoff = (datetime.fromisoformat(queue.local_today(tz_name)) - timedelta(days=WINDOW_DAYS)).date()
    dismissed = set(s.execute(select(models.OrphanDismissal.workout_id)).scalars())
    floor = datetime.combine(cutoff, datetime.min.time(), tzinfo=tz).astimezone(UTC).replace(tzinfo=None) - timedelta(days=1)
    rows = s.execute(select(models.Workout).where(models.Workout.type == "strength", models.Workout.start_utc >= floor)
                     .order_by(models.Workout.start_utc.desc())).scalars()
    return [w for w in rows if w.workout_id not in dismissed and _local(w.start_utc, tz).date() >= cutoff
            and is_orphan(s, w)]


def router(api: Api) -> APIRouter:
    r = APIRouter(tags=["orphans"], dependencies=api.auth)

    def workout_or_404(s: Session, workout_id: str) -> models.Workout:
        w = s.execute(select(models.Workout).where(
            models.Workout.workout_id == workout_id, models.Workout.type == "strength")).scalars().first()
        if w is None:
            raise HTTPException(status_code=404, detail="workout not found")
        return w

    @r.get("/orphans", response_model=list[sc.OrphanOut])
    def list_orphans() -> list[sc.OrphanOut]:
        with Session(api.engine) as s:
            tz_name = settings.read(s, api.default_tz).home_tz
            tz = ZoneInfo(tz_name)
            return [sc.OrphanOut(workout_id=w.workout_id, start_utc=rfc3339(w.start_utc),
                                 duration_s=w.duration_s if w.duration_s is not None else (w.end_utc - w.start_utc).total_seconds(),
                                 guess=guess_for(s, w, tz)) for w in orphans(s, tz_name)]

    @r.post("/orphans/{workout_id}/log", response_model=sc.SessionOut, status_code=201)
    def log_orphan(workout_id: str, body: sc.OrphanLogIn, response: Response) -> sc.SessionOut:
        with Session(api.engine) as s:
            w = workout_or_404(s, workout_id)
            cands = s.execute(select(models.WorkoutSession).where(
                models.WorkoutSession.start_utc < w.end_utc, models.WorkoutSession.end_utc > w.start_utc)
                .order_by(models.WorkoutSession.id)).scalars().all()
            again = next((m for m in cands if ss.match(m.start_utc, m.end_utc, [w]) is not None), None)
            if again is not None:  # a double tap: the session is already there
                response.status_code = 200
                return session_out(again)
            plan = s.get(models.WorkoutPlan, body.plan_id)
            if plan is None:
                raise HTTPException(status_code=422, detail="plan not found")
            if body.partial_moves >= len(plan.moves) and body.partial_moves != 0:
                raise HTTPException(status_code=422, detail="partial moves must be fewer than the plan's moves")
            snap = sc.PlanIn(name=plan.name, format=plan.format, cap_min=plan.cap_min, emom_min=plan.emom_min,
                             rounds=plan.rounds, tap_per=plan.tap_per, moves=plan.moves, video_url=plan.video_url)
            span_ms = round((w.end_utc - w.start_utc).total_seconds() * 1000)
            m = models.WorkoutSession(
                plan_id=plan.id, plan=snap.model_dump(), weight_kg=body.weight_kg, start_utc=w.start_utc, end_utc=w.end_utc,
                events=[{"t_ms": span_ms, "kind": "end", "move": 0, "round": 0}], rounds_done=body.rounds_done,
                partial_moves=body.partial_moves, fell_short=[], active_s=round(span_ms / 1000),
                overtime_s=0, source="watch", created_at=utcnow())
            s.add(m)
            if s.get(models.OrphanDismissal, workout_id) is None:  # answered: deleting the session must not ask again
                s.add(models.OrphanDismissal(workout_id=workout_id, created_at=utcnow()))
            s.commit()
            response.status_code = 201
            return session_out(m)

    @r.post("/orphans/{workout_id}/dismiss", status_code=204)
    def dismiss_orphan(workout_id: str) -> Response:
        with Session(api.engine) as s:
            workout_or_404(s, workout_id)
            if s.get(models.OrphanDismissal, workout_id) is None:
                s.add(models.OrphanDismissal(workout_id=workout_id, created_at=utcnow()))
                s.commit()
        return Response(status_code=204)

    return r
