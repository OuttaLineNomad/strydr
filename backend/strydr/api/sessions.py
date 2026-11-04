"""Home-workout sessions: the saved record of a live run (the taps are the log). User table only; sessions are not
a pipeline input, so no write here enqueues a recompute."""
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.api import schemas as sc
from strydr import progress as pg
from strydr import sessions_summary as ss
from strydr.api.common import Api, rfc3339
from strydr.store import models
from strydr.store.generations import scoped
from strydr.store.series import load_series
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
                         partial_moves=m.partial_moves, fell_short=m.fell_short or [], active_s=m.active_s,
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
            out[m.plan_id] = sc.LastSessionOut(id=m.id, rounds=m.rounds_done, partial_moves=m.partial_moves,
                                               date=rfc3339(m.start_utc))
    return out


def match_workout(s: Session, m: models.WorkoutSession) -> models.Workout | None:
    """The strength workout the session overlaps most (see `ss.match`)."""
    cands = s.execute(select(models.Workout).where(
        models.Workout.type == "strength", models.Workout.start_utc < m.end_utc, models.Workout.end_utc > m.start_utc)).scalars().all()
    return ss.match(m.start_utc, m.end_utc, cands)


def session_effort(m: models.WorkoutSession, w: models.Workout | None) -> tuple[float | None, str | None, bool]:
    """(effort, source, estimated). A real watch rating beats a manual pick; a manual pick beats the watch's estimate."""
    watch = w.effort_score if w is not None else None
    estimated = watch is not None and w.effort_estimated is True
    if watch is not None and not estimated:
        return watch, "watch", estimated
    if m.effort is not None:
        return m.effort, "manual", False
    if watch is not None:
        return watch, "watch", estimated
    return None, None, estimated


def session_ladder_sets(m: models.WorkoutSession) -> list[pg.LadderSet]:
    return pg.ladder_sets(m.plan, m.rounds_done, m.partial_moves, m.fell_short, m.short_reps, m.set_rungs)


def build_summary(s: Session, m: models.WorkoutSession) -> sc.SessionSummaryOut:
    """Built on every read from the saved session and the strength workout it overlaps most, so a watch workout that
    syncs later attaches on its own. Nothing here is stored."""
    plan = m.plan
    end_ms = round((m.end_utc - m.start_utc).total_seconds() * 1000)
    w = match_workout(s, m)
    samples = None
    if w is not None:
        hr = load_series(s, w.workout_id).get("heart_rate")
        if hr and hr.get("t") and hr.get("avg"):
            samples = ss.Samples(hr["t"], hr["avg"], (w.start_utc - m.start_utc).total_seconds()) or None
    prof = s.execute(scoped(models.ProfileResult)).scalar_one_or_none()
    bounds = prof.zone_bounds_bpm if prof and prof.hrmax else None
    got = ss.compute(m.events, plan, end_ms, samples, bounds)
    effort, source, estimated = session_effort(m, w)
    moves = plan["moves"]
    short = m.short_reps or {}
    rows = []
    if plan["format"] == "emom" and moves:
        for minute in m.fell_short or []:
            mv = moves[(minute - 1) % len(moves)]
            rows.append(sc.SessionShortRow(minute=minute, move=mv["name"], target_reps=mv.get("reps"), short_reps=short.get(str(minute))))
    lsets = session_ladder_sets(m)
    unlocked = [pg.rung_name(u["ladder"], u["to_rung"]) for u in pg.unlocks(moves, pg.ladder_sets(
        plan, m.rounds_done, m.partial_moves, m.fell_short, m.short_reps, m.set_rungs))]
    return sc.SessionSummaryOut(
        ladder_sets=[sc.LadderSetOut(move_index=x.move, instance=x.instance, move=moves[x.move]["name"], ladder=x.ladder,
                                     planned_rung=x.planned, rung=x.rung, reps=x.reps) for x in lsets],
        unlocked=unlocked,
        session=session_out(m), matched_workout_id=w.workout_id if w is not None else None, avg_hr=got.avg_hr,
        effort=effort, effort_source=source, effort_estimated=estimated,
        moves=[sc.SessionMoveHr(name=x.name, avg_hr=x.avg_hr, instances=x.instances) for x in got.moves],
        rounds=[sc.SessionRoundRow(round=x.round, time_s=x.time_s, moves=x.moves, avg_hr=x.avg_hr) for x in got.rounds],
        zone_seconds=got.zone_seconds, zone_bounds_bpm=list(bounds) if bounds and got.zone_seconds else None,
        fell_short=rows)


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

    @r.delete("/sessions/{session_id}", status_code=204)
    def delete_session(session_id: int) -> Response:
        with Session(api.engine) as s:
            m = s.get(models.WorkoutSession, session_id)
            if m is None:
                raise HTTPException(status_code=404, detail="session not found")
            s.delete(m)
            s.commit()  # user content: no recompute job
        return Response(status_code=204)

    @r.get("/sessions/{session_id}/summary", response_model=sc.SessionSummaryOut)
    def session_summary(session_id: int) -> sc.SessionSummaryOut:
        with Session(api.engine) as s:
            m = s.get(models.WorkoutSession, session_id)
            if m is None:
                raise HTTPException(status_code=404, detail="session not found")
            return build_summary(s, m)

    @r.put("/sessions/{session_id}/effort", response_model=sc.EffortOut)
    def set_effort(session_id: int, body: sc.EffortIn) -> sc.EffortOut:
        with Session(api.engine) as s:
            m = s.get(models.WorkoutSession, session_id)
            if m is None:
                raise HTTPException(status_code=404, detail="session not found")
            m.effort = body.effort
            s.commit()
            return sc.EffortOut(effort=body.effort)

    @r.put("/sessions/{session_id}/short", response_model=dict[str, int | None])
    def set_short(session_id: int, body: dict[str, int | None]) -> dict[str, int | None]:
        with Session(api.engine) as s:
            m = s.get(models.WorkoutSession, session_id)
            if m is None:
                raise HTTPException(status_code=404, detail="session not found")
            for k, v in body.items():
                if not (k.isascii() and k.isdigit()) or int(k) not in (m.fell_short or []):
                    raise HTTPException(status_code=422, detail=f"minute {k} was not flagged as fell short")
                if v is not None and not 0 <= v <= 500:
                    raise HTTPException(status_code=422, detail="reps must be between 0 and 500")
            merged = {**(m.short_reps or {}), **{str(int(k)): v for k, v in body.items()}}
            m.short_reps = merged  # a new dict: SQLAlchemy does not see an in-place JSON change
            s.commit()
            return merged

    @r.put("/sessions/{session_id}/rungs", response_model=dict[str, int | None])
    def set_set_rungs(session_id: int, body: dict[str, int | None]) -> dict[str, int | None]:
        """Records a lower rung actually done for a set ("move:instance"); null restores the planned one. User content:
        nothing here enqueues a recompute."""
        with Session(api.engine) as s:
            m = s.get(models.WorkoutSession, session_id)
            if m is None:
                raise HTTPException(status_code=404, detail="session not found")
            moves = m.plan["moves"]
            norm: dict[str, int | None] = {}
            for k, v in body.items():
                a, _, b = k.partition(":")
                if not all(x.isascii() and x.isdigit() and len(x) <= 3 for x in (a, b)):
                    raise HTTPException(status_code=422, detail=f"{k} is not a set (use move:instance)")
                i, inst = int(a), int(b)
                planned = moves[i].get("rung") if i < len(moves) and moves[i].get("ladder") is not None else None
                if planned is None:
                    raise HTTPException(status_code=422, detail=f"move {i} is not a ladder move")
                if inst >= m.rounds_done + (1 if i < m.partial_moves else 0):
                    raise HTTPException(status_code=422, detail=f"move {i} has no set {inst}")
                if v is not None and not 0 <= v <= planned:
                    raise HTTPException(status_code=422, detail="a set can only step down to a lower rung")
                norm[f"{i}:{inst}"] = None if v == planned else v  # the planned rung is the default
            merged = {k: v for k, v in {**(m.set_rungs or {}), **norm}.items() if v is not None}
            m.set_rungs = merged or None  # a new dict: SQLAlchemy does not see an in-place JSON change
            s.commit()
            return merged

    return r
