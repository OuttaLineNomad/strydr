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

from strydr.api import schemas as sc
from strydr.api.sessions import last_sessions
from strydr.api.common import Api
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


def plan_out(p: models.WorkoutPlan, last: sc.LastSessionOut | None = None) -> sc.PlanOut:
    return sc.PlanOut(id=p.id, name=p.name, format=p.format, cap_min=p.cap_min, emom_min=p.emom_min, rounds=p.rounds,
                      moves=[sc.MoveIn(**m) for m in p.moves], video_url=p.video_url,
                      created_at=p.created_at.isoformat(), updated_at=p.updated_at.isoformat(), last_session=last)


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
            return sorted((plan_out(p, last.get(p.id)) for p in plans), key=lambda p: p.name.casefold())

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
            return plan_out(p, last_sessions(s, [p.id]).get(p.id))

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
            return plan_out(p, last_sessions(s, [p.id]).get(p.id))

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
                                   rounds=src.rounds, moves=[dict(m) for m in src.moves], video_url=src.video_url,
                                   created_at=now, updated_at=now)
            s.add(p)
            commit_unique(s)
            return plan_out(p)

    return r
