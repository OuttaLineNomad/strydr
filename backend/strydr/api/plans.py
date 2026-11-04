"""Home-workout plans: the saved library. User table only; plans are not a pipeline input, so no write here
enqueues a recompute."""
from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from strydr.api import schemas as sc
from strydr.api.sessions import last_sessions
from strydr.api.common import Api
from strydr.store import models
from strydr.store.util import utcnow

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
