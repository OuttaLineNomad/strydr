"""The weekly home-workout streak (CAP-10), computed on read from sessions and watch workouts (AD-2)."""
from datetime import UTC, date
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from strydr import progress
from strydr.api import schemas as sc
from strydr.api.common import Api
from strydr.jobs import queue
from strydr.store import models, settings


def router(api: Api) -> APIRouter:
    r = APIRouter(tags=["streak"], dependencies=api.auth)

    @r.get("/streak", response_model=sc.StreakOut)
    def get_streak() -> sc.StreakOut:
        with Session(api.engine) as s:
            tz_name = settings.read(s, api.default_tz).home_tz
            tz = ZoneInfo(tz_name)
            starts = list(s.execute(select(models.WorkoutSession.start_utc)).scalars())
            starts += s.execute(select(models.Workout.start_utc).where(or_(
                models.Workout.type == "strength",
                and_(models.Workout.type == "walk", models.Workout.is_indoor.is_(True))))).scalars()
        local = [d.replace(tzinfo=UTC).astimezone(tz).date() for d in starts]
        res = progress.streak(local, date.fromisoformat(queue.local_today(tz_name)))
        return sc.StreakOut(weeks=res.weeks, this_week=res.this_week, last_streak=res.last_streak,
                            recent=[sc.StreakWeekOut(week_start=w.isoformat(), counted=c) for w, c in res.recent])

    return r
