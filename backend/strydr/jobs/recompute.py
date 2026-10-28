"""The recompute job (AD-1): build a whole new generation, flip the pointer, delete the old one."""
import logging
from datetime import date

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from strydr.pipeline import derive, insights, profile
from strydr.pipeline.context import Context
from strydr.pipeline.insights.thresholds import load_thresholds
from strydr.store import generations, settings
from zoneinfo import ZoneInfo

log = logging.getLogger("strydr.jobs")


def recompute(engine: Engine, as_of: str, default_tz: str = "UTC") -> int:
    """Runs profile, derive (summary, load, days, records, routes), insights in order. The new generation is invisible
    until the final flip."""
    with Session(engine) as s:
        tz = ZoneInfo(settings.read(s, default_tz).home_tz)
        overrides = settings.read_threshold_overrides(s)
    try:
        th = load_thresholds(overrides)
    except ValueError:  # an override that no longer matches the defaults must not stop every recompute
        log.warning("threshold overrides ignored: unknown section or key")
        th = load_thresholds()
    gid = generations.begin(engine, as_of)
    ctx = Context(engine, gid, date.fromisoformat(as_of), tz, th)
    try:
        prof = profile.run(ctx)
        derive.run(ctx, prof)
        insights.run(ctx, prof)
        generations.publish(engine, gid)
    except BaseException:
        generations.delete_generation(engine, gid)
        raise
    generations.purge_stale(engine)
    log.info("recompute as_of=%s: generation %d published", as_of, gid)
    return gid
