"""Bodyweight ladders (CAP-13): the staircase of the best set per session. Computed on read from the sessions."""
from typing import Literal

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr import progress as pg
from strydr.api import schemas as sc
from strydr.api.common import Api, rfc3339
from strydr.api.sessions import session_ladder_sets
from strydr.store import models


def router(api: Api) -> APIRouter:
    r = APIRouter(tags=["ladders"], dependencies=api.auth)

    @r.get("/ladders/{ladder}/history", response_model=list[sc.LadderPointOut])
    def ladder_history(ladder: Literal["push-up", "pull-up"]) -> list[sc.LadderPointOut]:
        """One point per session with a set on this ladder, oldest first: its best set (highest rung, then most reps)."""
        with Session(api.engine) as s:
            rows = s.execute(select(models.WorkoutSession).order_by(models.WorkoutSession.start_utc, models.WorkoutSession.id)).scalars()
            out = []
            for m in rows:
                best = pg.best_set(session_ladder_sets(m), ladder)
                if best is not None:
                    out.append(sc.LadderPointOut(session_id=m.id, date=rfc3339(m.start_utc), rung=best.rung, reps=best.reps))
            return out

    return r
