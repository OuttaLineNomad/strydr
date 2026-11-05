"""Home-workout plans: the saved library. User table only; plans are not a pipeline input, so no write here
enqueues a recompute."""
import json
import logging
import re

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from strydr import progress as pg
from strydr import sessions_summary as ss
from strydr.api import schemas as sc
from strydr.api.sessions import build_summary, last_sessions, session_effort, session_ladder_sets
from strydr.api.common import Api, rfc3339
from strydr.egress import EgressError, PlanImportPayload, resolve, youtube
from strydr.store import models, settings
from strydr.store.util import utcnow

log = logging.getLogger("strydr.plans")

AI_OFF = "Turn on AI in Settings to read workouts from videos."
NO_TRANSCRIPT = "This video has no transcript, so Strydr can't read the workout from it."
NOT_YOUTUBE = "Paste a YouTube or YouTube Shorts link."
UNREACHABLE = "Couldn't reach YouTube or the AI just now. Try again."
UNREADABLE = "Couldn't read a workout from this video."
UNAVAILABLE = "This video isn't available to Strydr (private, removed or age-restricted)."


def _clip(v: object, n: int) -> object:
    """A model's over-long name cut at a word boundary, so a video-title name doesn't sink the whole draft."""
    if not isinstance(v, str) or len(v.strip()) <= n:
        return v
    cut = v.strip()[:n + 1].rsplit(" ", 1)[0] if " " in v.strip()[:n + 1] else v.strip()[:n]
    return cut[:n].rstrip(" .,;:!-–—|")


def _shorten_names(obj: dict) -> dict:
    out = obj | {"name": _clip(obj.get("name"), 60)}
    if isinstance(obj.get("moves"), list):
        out["moves"] = [m | {"name": _clip(m.get("name"), 40)} if isinstance(m, dict) else m for m in obj["moves"]]
    return out


def _plan_from_reply(raw: str, video_url: str) -> sc.PlanIn:
    """The first JSON object in the reply that validates as a plan. Prose, <think> text and code fences around it
    are ignored; nothing is honoured that PlanIn does not accept. `video_url` is always the pasted link."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", raw):
        try:
            obj, _ = dec.raw_decode(raw, m.start())
            if isinstance(obj, dict):
                return sc.PlanIn.model_validate(_shorten_names(obj) | {"video_url": video_url})
        except (ValueError, ValidationError, RecursionError):
            continue
    raise ValueError("no plan in the reply")


TAKEN = "a workout with that name exists"


def plan_out(p: models.WorkoutPlan, last: sc.LastSessionOut | None = None, score: int | None = None,
             change: int | None = None, unlocks: list[dict] | None = None) -> sc.PlanOut:
    return sc.PlanOut(unlocks=[sc.UnlockOut(**u) for u in unlocks or []], strength_score=score, strength_change=change, id=p.id, name=p.name, format=p.format, cap_min=p.cap_min, emom_min=p.emom_min, rounds=p.rounds, tap_per=p.tap_per,
                      moves=[sc.MoveIn(**m) for m in p.moves], video_url=p.video_url,
                      created_at=p.created_at.isoformat(), updated_at=p.updated_at.isoformat(), last_session=last)


def _missed_reps(m: models.WorkoutSession) -> int | None:
    """EMOM: reps short of target over the fell-short minutes. None if any flagged minute is unanswered."""
    plan = m.plan
    if plan["format"] != "emom":
        return None
    moves, short, total = plan["moves"], m.short_reps or {}, 0
    for minute in m.fell_short or []:
        answer = short.get(str(minute))
        if answer is None:
            return None
        target = moves[(minute - 1) % len(moves)].get("reps") if moves else None
        total += max(0, target - answer) if target is not None else 0
    return total


def _unlocks(s: Session, plans: list[models.WorkoutPlan]) -> dict[int, list[dict]]:
    """The next rungs each plan's latest session earned, computed on read (nothing stored)."""
    ladder_plans = [p for p in plans if any(m.get("ladder") for m in p.moves)]
    out: dict[int, list[dict]] = {}
    if not ladder_plans:
        return out
    rows = s.execute(select(models.WorkoutSession).where(models.WorkoutSession.plan_id.in_([p.id for p in ladder_plans]))
                     .order_by(models.WorkoutSession.start_utc.desc(), models.WorkoutSession.id.desc())).scalars()
    latest: dict[int, models.WorkoutSession] = {}
    for m in rows:
        latest.setdefault(m.plan_id, m)
    for p in ladder_plans:
        if p.id in latest:
            out[p.id] = pg.unlocks(p.moves, session_ladder_sets(latest[p.id]))
    return out


def _shape(moves: list[dict]) -> list[tuple]:
    return [(x["name"], x.get("reps"), x.get("seconds")) for x in moves]


def _efforts(s: Session, rows: list[models.WorkoutSession]) -> dict[int, float | None]:
    """Each session's effort (watch rating, then manual pick, then estimate) from one query for the strength workouts."""
    if not rows:
        return {}
    lo, hi = min(m.start_utc for m in rows), max(m.end_utc for m in rows)
    cands = s.execute(select(models.Workout).where(models.Workout.type == "strength", models.Workout.start_utc < hi,
                                                   models.Workout.end_utc > lo)).scalars().all()
    return {m.id: session_effort(m, ss.match(m.start_utc, m.end_utc, cands))[0] for m in rows}


def _scores(rows: list[models.WorkoutSession], efforts: dict[int, float | None]) -> dict[int, int | None]:
    """Strength score by session id for the sessions of ONE plan (any order)."""
    ordered = sorted(rows, key=lambda m: (m.start_utc, m.id))
    got = pg.scores([pg.ScoreInput(m.plan, m.weight_kg, m.rounds_done, m.partial_moves, m.fell_short, m.short_reps,
                                   m.active_s, efforts.get(m.id), m.set_rungs) for m in ordered])
    return {m.id: sc_ for m, sc_ in zip(ordered, got)}


def _plan_scores(s: Session, plan_ids: list[int]) -> dict[int, tuple[int | None, int | None]]:
    """(strength_score, strength_change) per plan from one sessions query; absent with fewer than 2 sessions."""
    if not plan_ids:
        return {}
    rows = list(s.execute(select(models.WorkoutSession).where(models.WorkoutSession.plan_id.in_(plan_ids))).scalars())
    efforts = _efforts(s, rows)
    by_plan: dict[int, list[models.WorkoutSession]] = {}
    for m in rows:
        by_plan.setdefault(m.plan_id, []).append(m)
    out = {}
    for pid, ms in by_plan.items():
        if len(ms) < 2:
            continue
        latest = max(ms, key=lambda m: (m.start_utc, m.id))
        score = _scores(ms, efforts)[latest.id]
        out[pid] = (score, score - 100) if score is not None else (None, None)
    return out


def _progress_row(m: models.WorkoutSession, current: list[tuple], effort: float | None, score: int | None) -> dict:
    return dict(id=m.id, date=rfc3339(m.start_utc), weight_kg=m.weight_kg, rounds_done=m.rounds_done,
                partial_moves=m.partial_moves, active_s=m.active_s, overtime_s=m.overtime_s, effort=effort, score=score,
                missed_reps=_missed_reps(m), changed=_shape(m.plan["moves"]) != current, cap_min=m.plan.get("cap_min"),
                target_rounds=m.plan.get("rounds"), move_count=len(m.plan["moves"]))


def router(api: Api) -> APIRouter:
    r = APIRouter(tags=["plans"], dependencies=api.auth)

    def name_taken(s: Session, name: str, except_id: int | None = None) -> bool:
        # casefold in Python: SQLite lower() folds ASCII only
        return any(i != except_id and n.casefold() == name.casefold()
                   for i, n in s.execute(select(models.WorkoutPlan.id, models.WorkoutPlan.name)).all())

    def commit_unique(s: Session) -> None:
        try:
            s.commit()
        except IntegrityError:  # a concurrent duplicate hit the unique index
            s.rollback()
            raise HTTPException(status_code=422, detail=TAKEN) from None

    def fill(p: models.WorkoutPlan, body: sc.PlanIn) -> None:
        p.name, p.format, p.cap_min, p.emom_min, p.rounds = body.name, body.format, body.cap_min, body.emom_min, body.rounds
        p.tap_per = body.tap_per
        p.moves = [m.model_dump() for m in body.moves]
        p.video_url = body.video_url

    def get_or_404(s: Session, plan_id: int) -> models.WorkoutPlan:
        p = s.get(models.WorkoutPlan, plan_id)
        if p is None:
            raise HTTPException(status_code=404, detail="workout not found")
        return p

    @r.get("/plans", response_model=list[sc.PlanOut])
    def list_plans() -> list[sc.PlanOut]:
        with Session(api.engine) as s:
            rows = s.execute(select(models.WorkoutPlan).order_by(models.WorkoutPlan.name)).scalars()
            plans = list(rows)
            last = last_sessions(s, [p.id for p in plans])
            sc_ = _plan_scores(s, [p.id for p in plans])
            un = _unlocks(s, plans)
            return sorted((plan_out(p, last.get(p.id), *sc_.get(p.id, (None, None)), un.get(p.id)) for p in plans), key=lambda p: p.name.casefold())

    @r.post("/plans/import-youtube", response_model=sc.PlanDraftOut)
    def import_youtube(body: sc.YoutubeImportIn) -> sc.PlanDraftOut:
        """A draft plan from a YouTube link's public text. Saves nothing; the runner checks it in the editor."""
        url = body.url.strip()
        vid = youtube.video_id(url)
        if vid is None:
            raise HTTPException(status_code=422, detail=NOT_YOUTUBE)
        with Session(api.engine) as s:
            ai = settings.read_ai(s)
            units = settings.read(s, api.default_tz).units
        if not ai.enabled:
            raise HTTPException(status_code=409, detail=AI_OFF)
        try:
            video = api.video_fetch(vid)
            if video is None:
                raise HTTPException(status_code=422, detail=NO_TRANSCRIPT)
            payload = PlanImportPayload(title=video.title, description=video.description, transcript=video.transcript[:youtube.MAX_TRANSCRIPT],
                                        units="imperial" if units == "imperial" else "metric")
            raw = api.provider_factory(resolve(ai.provider, ai.base_url, ai.model, ai.api_key)).plan_from_text(payload)
        except youtube.Unavailable:
            raise HTTPException(status_code=422, detail=UNAVAILABLE) from None
        except ValidationError:  # the video's text did not fit the closed payload
            raise HTTPException(status_code=422, detail=UNREADABLE) from None
        except (EgressError, ValueError, TypeError, RecursionError) as e:  # fetch, provider setup or the AI call
            log.warning("youtube import failed: %s", type(e).__name__)
            raise HTTPException(status_code=502, detail=UNREACHABLE) from None
        try:
            plan = _plan_from_reply(raw, url if len(url) <= 500 else f"{youtube.WATCH_URL}?v={vid}")
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail=UNREADABLE) from None
        return sc.PlanDraftOut(title=video.title.strip() or plan.name, plan=plan)

    @r.get("/plans/{plan_id}", response_model=sc.PlanOut)
    def get_plan(plan_id: int) -> sc.PlanOut:
        with Session(api.engine) as s:
            p = get_or_404(s, plan_id)
            return plan_out(p, last_sessions(s, [p.id]).get(p.id), *_plan_scores(s, [p.id]).get(p.id, (None, None)),
                            _unlocks(s, [p]).get(p.id))

    @r.get("/plans/{plan_id}/progress", response_model=sc.PlanProgressOut)
    def plan_progress(plan_id: int) -> sc.PlanProgressOut:
        """Every session of the plan, newest first, and the earliest against the latest. Computed on read."""
        with Session(api.engine) as s:
            p = get_or_404(s, plan_id)
            rows = list(s.execute(select(models.WorkoutSession).where(models.WorkoutSession.plan_id == plan_id)
                                  .order_by(models.WorkoutSession.start_utc.desc(), models.WorkoutSession.id.desc())).scalars())
            current = _shape(p.moves)
            efforts = _efforts(s, rows)
            scored = _scores(rows, efforts)
            sessions = [_progress_row(m, current, efforts[m.id], scored.get(m.id)) for m in rows]
            latest = sessions[0]["score"] if len(rows) >= 2 else None  # rows are newest first
            head = (latest, latest - 100) if latest is not None else (None, None)
            then = now = None
            if len(rows) >= 2:  # the HR series is read for these two only
                now = sc.ProgressCompareOut(**sessions[0], avg_hr=build_summary(s, rows[0]).avg_hr)
                then = sc.ProgressCompareOut(**sessions[-1], avg_hr=build_summary(s, rows[-1]).avg_hr)
            return sc.PlanProgressOut(plan=plan_out(p, last_sessions(s, [p.id]).get(p.id), *head, _unlocks(s, [p]).get(p.id)),
                                      sessions=[sc.ProgressSessionOut(**x) for x in sessions], then=then, now=now)

    @r.post("/plans", response_model=sc.PlanOut, status_code=201)
    def add_plan(body: sc.PlanIn) -> sc.PlanOut:
        with Session(api.engine) as s:
            if name_taken(s, body.name):
                raise HTTPException(status_code=422, detail=TAKEN)
            now = utcnow()
            p = models.WorkoutPlan(created_at=now, updated_at=now)
            fill(p, body)
            s.add(p)
            commit_unique(s)
            return plan_out(p)

    @r.put("/plans/{plan_id}", response_model=sc.PlanOut)
    def put_plan(plan_id: int, body: sc.PlanIn) -> sc.PlanOut:
        with Session(api.engine) as s:
            p = get_or_404(s, plan_id)
            if name_taken(s, body.name, plan_id):
                raise HTTPException(status_code=422, detail=TAKEN)
            fill(p, body)
            p.updated_at = utcnow()
            commit_unique(s)
            return plan_out(p, last_sessions(s, [p.id]).get(p.id), unlocks=_unlocks(s, [p]).get(p.id))

    @r.delete("/plans/{plan_id}", status_code=204)
    def delete_plan(plan_id: int) -> Response:
        with Session(api.engine) as s:
            s.delete(get_or_404(s, plan_id))
            # SQLite may hand this id to a new plan: the old sessions must not become its "Last:"
            s.execute(update(models.WorkoutSession).where(models.WorkoutSession.plan_id == plan_id).values(plan_id=None))
            s.commit()
        return Response(status_code=204)

    @r.post("/plans/{plan_id}/duplicate", response_model=sc.PlanOut, status_code=201)
    def duplicate_plan(plan_id: int) -> sc.PlanOut:
        with Session(api.engine) as s:
            src = get_or_404(s, plan_id)
            def candidate(n: int) -> str:
                suffix = " (copy)" if n == 1 else f" (copy {n})"
                return src.name[:60 - len(suffix)].rstrip() + suffix  # always within 60 characters

            n = 1
            name = candidate(n)
            while name_taken(s, name):
                n += 1
                name = candidate(n)
            now = utcnow()
            p = models.WorkoutPlan(name=name, format=src.format, cap_min=src.cap_min, emom_min=src.emom_min,
                                   rounds=src.rounds, tap_per=src.tap_per, moves=[dict(m) for m in src.moves], video_url=src.video_url,
                                   created_at=now, updated_at=now)
            s.add(p)
            commit_unique(s)
            return plan_out(p)

    return r
