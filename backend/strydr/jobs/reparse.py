"""Rebuild the canonical tier from raw when the source adapter has changed (AD-1, AD-14)."""
import logging

from sqlalchemy import Engine, delete, func, or_, select, update
from sqlalchemy.orm import Session

from strydr.jobs import queue
from strydr.pipeline.normalize.process import adapter_version, process_payload
from strydr.store import models, settings

log = logging.getLogger("strydr.jobs")


def needs_reparse(engine: Engine) -> bool:
    """True when a processed payload, or a canonical row, came from an older version of its own source's adapter."""
    with Session(engine) as s:
        for source in ("hae", "apple"):
            current = adapter_version(source)
            src = func.coalesce(models.RawPayload.source, "hae")  # a row with no payload is HAE's
            stale = [
                select(models.RawPayload.id).where(models.RawPayload.status == "processed", src == source, or_(
                    models.RawPayload.adapter_version.is_(None), models.RawPayload.adapter_version < current)),
                # series carry a kept copy's version, so only workouts and metrics are compared
                *(select(m.id).outerjoin(models.RawPayload, models.RawPayload.id == m.payload_id)
                  .where(src == source, m.adapter_version < current) for m in (models.Workout, models.DailyMetric)),
            ]
            if any(s.execute(q.limit(1)).first() is not None for q in stale):
                return True
    return False


def enqueue_if_stale(engine: Engine) -> bool:
    if not needs_reparse(engine):
        return False
    with Session(engine) as s:
        queue.enqueue_reparse(s)
        s.commit()
    queue.wakeup.set()
    return True


def reparse(engine: Engine, default_tz: str = "UTC") -> int:
    """Delete canonical rows and normalize every processed payload again, oldest first. Raw is never touched.

    A payload that no longer parses is quarantined like any failed process_raw (AD-5). Returns the payload count.
    """
    with Session(engine) as s:
        for model in (models.SampleSeries, models.Workout, models.DailyMetric):
            s.execute(delete(model))
        s.commit()
        ids = list(s.execute(select(models.RawPayload.id).where(models.RawPayload.status == "processed")
                             .order_by(models.RawPayload.received_at, models.RawPayload.id)).scalars())
    for pid in ids:
        try:
            process_payload(engine, pid, default_tz)
        except Exception as e:
            log.warning("reparse: payload %s quarantined: %s", pid, type(e).__name__)
            with Session(engine) as s:
                s.execute(update(models.RawPayload).where(models.RawPayload.id == pid)
                          .values(status="quarantined", error=type(e).__name__))
                s.commit()
    with Session(engine) as s:
        queue.enqueue_recompute(s, queue.local_today(settings.read(s, default_tz).home_tz))
        s.commit()
    return len(ids)
