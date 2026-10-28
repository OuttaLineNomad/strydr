"""AI provider settings and threshold overrides."""
from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from strydr.api import schemas as sc
from strydr.api.common import Api
from strydr.egress import NVIDIA_BASE_URL, NVIDIA_DEFAULT_MODEL, valid_base_url
from strydr.egress.weather import WEATHER_HOST
from strydr.jobs import queue
from strydr.jobs import weather as weather_job
from strydr.pipeline.insights.thresholds import load_thresholds
from strydr.store import models, settings


def _ai_out(ai: settings.AiSettings) -> sc.AiSettingsOut:
    return sc.AiSettingsOut(
        provider=ai.provider, base_url=ai.base_url, model=ai.model, default_base_url=NVIDIA_BASE_URL,
        default_model=NVIDIA_DEFAULT_MODEL, has_key=ai.enabled, enabled=ai.enabled)  # the key itself is never returned


def router(api: Api) -> APIRouter:
    r = APIRouter(prefix="/settings", tags=["settings"], dependencies=api.auth)

    @r.get("/ai", response_model=sc.AiSettingsOut)
    def get_ai() -> sc.AiSettingsOut:
        with Session(api.engine) as s:
            return _ai_out(settings.read_ai(s))

    @r.put("/ai", response_model=sc.AiSettingsOut)
    def put_ai(body: sc.AiSettingsIn) -> sc.AiSettingsOut:
        if body.base_url and not valid_base_url(body.base_url):
            raise HTTPException(status_code=422, detail="base_url must be https (http only for localhost)")
        if body.provider == "openai-compatible" and not (body.base_url and body.model):
            raise HTTPException(status_code=422, detail="an openai-compatible provider needs a base URL and a model")
        with Session(api.engine) as s:
            old = settings.read_ai(s)
            key = old.api_key if body.api_key is None else (body.api_key.strip() or None)
            new = settings.AiSettings(body.provider, body.base_url, body.model, key)
            settings.write_ai(s, new)
            if new.enabled:  # settings are not a pipeline input (AD-1), but fresh wording is wanted for existing insights
                queue.enqueue_phrase(s)
            s.commit()
        api.wake()
        return _ai_out(new)

    def weather_out(s: Session) -> sc.WeatherSettingsOut:
        counts = dict(s.execute(select(models.WorkoutWeather.status, func.count()).group_by(models.WorkoutWeather.status)).all())
        return sc.WeatherSettingsOut(enabled=settings.read_weather_enabled(s), provider_host=WEATHER_HOST,
                                     fetched=counts.get("ok", 0), unavailable=counts.get("unavailable", 0),
                                     skipped=counts.get("skipped", 0))

    @r.get("/weather", response_model=sc.WeatherSettingsOut)
    def get_weather() -> sc.WeatherSettingsOut:
        with Session(api.engine) as s:
            return weather_out(s)

    @r.put("/weather", response_model=sc.WeatherSettingsOut)
    def put_weather(body: sc.WeatherSettingsIn) -> sc.WeatherSettingsOut:
        with Session(api.engine) as s:
            if body.enabled != settings.read_weather_enabled(s):
                settings.write_weather_enabled(s, body.enabled)
                if body.enabled:
                    queue.enqueue_weather(s)
                else:
                    weather_job.clear(s)  # off means nothing fetched is kept
                api.enqueue_recompute(s)  # AD-1: the weather switch is a pipeline input
            s.commit()
            out = weather_out(s)
        api.wake()
        return out

    def thresholds_out(s: Session, overrides: dict) -> sc.ThresholdsOut:
        pending = s.execute(select(models.Job.id).where(models.Job.type == "recompute",
                                                       models.Job.status.in_(("pending", "running"))).limit(1)).first()
        return sc.ThresholdsOut(defaults=load_thresholds().as_dict(), overrides=overrides, recompute_pending=pending is not None)

    @r.get("/thresholds", response_model=sc.ThresholdsOut)
    def get_thresholds() -> sc.ThresholdsOut:
        with Session(api.engine) as s:
            return thresholds_out(s, settings.read_threshold_overrides(s))

    @r.put("/thresholds", response_model=sc.ThresholdsOut)
    def put_thresholds(body: sc.ThresholdsIn) -> sc.ThresholdsOut:
        try:
            load_thresholds(body.overrides)  # unknown sections and keys fail loudly (AD-8)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        with Session(api.engine) as s:
            settings.write_threshold_overrides(s, body.overrides)
            api.enqueue_recompute(s)  # AD-1: threshold overrides are a pipeline input
            s.commit()
            out = thresholds_out(s, body.overrides)
        api.wake()
        return out

    return r
