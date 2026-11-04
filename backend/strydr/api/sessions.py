"""Home-workout sessions: the saved record of a live run (the taps are the log). User table only; sessions are not
a pipeline input, so no write here enqueues a recompute."""
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.api import schemas as sc
from strydr.api.common import Api, rfc3339
from strydr.store import models
from strydr.store.util import utcnow


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def paused_ms(events: list[sc.SessionEvent], span_ms: int) -> int:
    """Total paused wall time. A pause with no resume lasts to the end; stray resumes and repeats are ignored."""
    paused = 0
    since: int | None = None
    for e in sorted(events, key=lambda e: e.t_ms):
        if e.kind == "pause" and since is None:
            since = min(e.t_ms, span_ms)
        elif e.kind == "resume" and since is not None:
            paused += max(0, min(e.t_ms, span_ms) - since)
            since = None
    if since is not None:
        paused += max(0, span_ms - since)
    return paused


def active_and_overtime_s(body: sc.SessionIn) -> tuple[int, int]:
    """Recomputed from the events and the span, never taken from the client."""
    span_ms = round((_naive_utc(body.end_utc) - _naive_utc(body.start_utc)).total_seconds() * 1000)
    active_ms = max(0, span_ms - paused_ms(body.events, span_ms))
    over_ms = max(0, active_ms - body.plan.cap_min * 60_000) if body.plan.format == "amrap" and body.plan.cap_min else 0
    return round(active_ms / 1000), round(over_ms / 1000)


def session_out(m: models.WorkoutSession) -> sc.SessionOut:
    return sc.SessionOut(id=m.id, plan_id=m.plan_id, plan=sc.PlanIn(**m.plan), weight_kg=m.weight_kg,
                         start_utc=rfc3339(m.start_utc), end_utc=rfc3339(m.end_utc),
                         events=[sc.SessionEvent(**e) for e in m.events], rounds_done=m.rounds_done,
                         partial_moves=m.partial_moves, fell_short=m.fell_short, active_s=m.active_s,
                         overtime_s=m.overtime_s, created_at=rfc3339(m.created_at))


def last_sessions(s: Session, plan_ids: list[int]) -> dict[int, sc.LastSessionOut]:
    """The latest session of each plan (by start), for the library's "Last:" line."""
    out: dict[int, sc.LastSessionOut] = {}
    if not plan_ids:
        return out
    rows = s.execute(select(models.WorkoutSession).where(models.WorkoutSession.plan_id.in_(plan_ids))
                     .order_by(models.WorkoutSession.start_utc.desc(), models.WorkoutSession.id.desc())).scalars()
    for m in rows:
        if m.plan_id not in out:
            out[m.plan_id] = sc.LastSessionOut(rounds=m.rounds_done, partial_moves=m.partial_moves,
                                               date=rfc3339(m.start_utc))
    return out


def router(api: Api) -> APIRouter:
    r = APIRouter(tags=["sessions"], dependencies=api.auth)

    @r.post("/sessions", response_model=sc.SessionOut, status_code=201)
    def add_session(body: sc.SessionIn) -> sc.SessionOut:
        start, end = _naive_utc(body.start_utc), _naive_utc(body.end_utc)
        with Session(api.engine) as s:
            # A retried save (the first reply was lost) must not log the session twice.
            again = s.execute(select(models.WorkoutSession).where(
                models.WorkoutSession.plan_id == body.plan_id, models.WorkoutSession.start_utc == start)).scalars().first()
            if again is not None and body.plan_id is not None:
                return session_out(again)
            active_s, overtime_s = active_and_overtime_s(body)
            m = models.WorkoutSession(
                plan_id=body.plan_id, plan=body.plan.model_dump(), weight_kg=body.weight_kg, start_utc=start,
                end_utc=end, events=[e.model_dump() for e in body.events], rounds_done=body.rounds_done,
                partial_moves=body.partial_moves, fell_short=sorted(set(body.fell_short)), active_s=active_s,
                overtime_s=overtime_s, created_at=utcnow())
            s.add(m)
            s.commit()
            return session_out(m)

    @r.get("/sessions", response_model=list[sc.SessionOut])
    def list_sessions(plan_id: int | None = None, limit: int = Query(50, ge=1, le=200)) -> list[sc.SessionOut]:
        with Session(api.engine) as s:
            q = select(models.WorkoutSession).order_by(models.WorkoutSession.start_utc.desc(), models.WorkoutSession.id.desc())
            if plan_id is not None:
                q = q.where(models.WorkoutSession.plan_id == plan_id)
            return [session_out(m) for m in s.execute(q.limit(limit)).scalars()]

    @r.get("/sessions/{session_id}", response_model=sc.SessionOut)
    def get_session(session_id: int) -> sc.SessionOut:
        with Session(api.engine) as s:
            m = s.get(models.WorkoutSession, session_id)
            if m is None:
                raise HTTPException(status_code=404, detail="session not found")
            return session_out(m)

    return r
