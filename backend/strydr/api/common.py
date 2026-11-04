"""Helpers shared by the app-port routers (AD-2: tables and the job queue only, never pipeline code)."""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import params
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from strydr.api import schemas as sc
from strydr.egress import Provider, ProviderConfig, make_provider, youtube
from strydr.jobs import queue
from strydr.store import models, settings


def rfc3339(dt: datetime | None) -> str | None:
    return dt.replace(tzinfo=UTC).isoformat(timespec="seconds").replace("+00:00", "Z") if dt else None


def workout_out(w: models.Workout, names: set[str], long_run: bool | None, carry_kg: float | None = None) -> sc.WorkoutOut:
    return sc.WorkoutOut(
        workout_id=w.workout_id, type=w.type, is_indoor=w.is_indoor, start=rfc3339(w.start_utc),
        local_date=w.local_date, duration_s=w.duration_s, distance_m=w.distance_m,
        avg_speed_mps=w.avg_speed_mps, avg_hr=w.avg_hr, max_hr=w.max_hr, elevation_gain_m=w.elevation_gain_m,
        has_hr="heart_rate" in names, has_route="route" in names, is_long_run=long_run, carry_kg=carry_kg,
    )


@dataclass(frozen=True)
class Api:
    engine: Engine
    default_tz: str
    auth: list[params.Depends]
    # injectable for tests, as the worker's provider_factory is
    provider_factory: Callable[[ProviderConfig], Provider] = make_provider
    video_fetch: Callable[[str], youtube.VideoText | None] = youtube.fetch

    def enqueue_recompute(self, s: Session) -> None:
        """Every write to a closed-list pipeline input calls this inside its own transaction (AD-1, AD-5)."""
        queue.enqueue_recompute(s, queue.local_today(settings.read(s, self.default_tz).home_tz))

    @staticmethod
    def wake() -> None:
        queue.wakeup.set()
