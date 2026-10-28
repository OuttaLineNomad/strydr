"""Daily tick (AD-15): recompute(as_of=today) at 03:00 home_tz. Nightly snapshot (AD-12): 02:30 home_tz."""
import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from strydr.jobs import queue
from strydr.store import settings

log = logging.getLogger("strydr.jobs")
TICK_HOUR = 3
SNAPSHOT_AT = (2, 30)


def seconds_until(now: datetime, tz: tzinfo, hour: int, minute: int = 0) -> float:
    local = now.astimezone(tz)
    nxt = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if nxt <= local:
        nxt = (local + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return (nxt - local).total_seconds()


def seconds_until_tick(now: datetime, tz: tzinfo) -> float:
    return seconds_until(now, tz, TICK_HOUR)


def tick(engine: Engine, default_tz: str) -> str:
    """Enqueue recompute(as_of=today in home_tz). The queue coalesces it with any pending recompute (AD-5)."""
    with Session(engine) as s:
        today = queue.local_today(settings.read(s, default_tz).home_tz)
        queue.enqueue_recompute(s, today)
        if settings.read_weather_enabled(s):
            queue.enqueue_weather(s)  # retries runs whose weather was unavailable
        s.commit()
    queue.wakeup.set()
    return today


def snapshot_tick(engine: Engine) -> None:
    with Session(engine) as s:
        queue.enqueue_snapshot(s)
        s.commit()
    queue.wakeup.set()


async def _daily(engine: Engine, default_tz: str, hour: int, minute: int, action: Callable[[], object]) -> None:
    while True:
        with Session(engine) as s:
            tz = ZoneInfo(settings.read(s, default_tz).home_tz)  # re-read so a home_tz change applies to the next run
        await asyncio.sleep(seconds_until(datetime.now(tz), tz, hour, minute))
        action()


async def run(engine: Engine, default_tz: str) -> None:
    def do_tick() -> None:
        log.info("daily tick: recompute enqueued as_of=%s", tick(engine, default_tz))

    def do_snapshot() -> None:
        snapshot_tick(engine)
        log.info("nightly snapshot enqueued")

    await asyncio.gather(
        _daily(engine, default_tz, TICK_HOUR, 0, do_tick),
        _daily(engine, default_tz, *SNAPSHOT_AT, do_snapshot),
    )
