"""Fitness / fatigue / form series and the current training state (FR-24, FR-24b, FR-24c)."""
from datetime import date, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import select

from strydr.api import schemas as sc
from strydr.api.common import Api
from strydr.store import generations, models
from strydr.store.generations import scoped


def router(api: Api) -> APIRouter:
    r = APIRouter(prefix="/load", tags=["load"], dependencies=api.auth)

    @r.get("", response_model=sc.LoadOut)
    def get_load(days: int = Query(180, ge=1, le=3650, description="how many days to return, ending at as_of")) -> sc.LoadOut:
        with generations.read_snapshot(api.engine) as s:
            gen = s.execute(select(models.Generation).join(
                models.CurrentGeneration, models.CurrentGeneration.generation_id == models.Generation.id)).scalar_one_or_none()
            if gen is None:
                return sc.LoadOut(as_of=None, series=[], training_state=None)
            since = (date.fromisoformat(gen.as_of) - timedelta(days=days - 1)).isoformat()
            rows = s.execute(scoped(models.DailyLoad, models.DailyLoad.local_date >= since)
                             .order_by(models.DailyLoad.local_date)).scalars().all()
            series = [sc.LoadDayOut(
                local_date=d.local_date, load=d.load, by_type=dict(d.by_type), estimated=d.estimated, fitness=d.fitness,
                fatigue=d.fatigue, form=d.form, form_pct=d.form_pct, warmup=d.warmup,
                tooltip=sc.LoadTooltip(acwr=d.acwr, ramp_pct=d.ramp_pct)) for d in rows]
            today = next((d for d in rows if d.local_date == gen.as_of), None)
            state = sc.TrainingStateOut(state=today.training_state, since=today.state_since) if today else None
            return sc.LoadOut(as_of=gen.as_of, series=series, training_state=state)

    return r
