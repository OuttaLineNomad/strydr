"""The import_apple job: validate a whole Apple Health export, then write it (CAP-17).

Pass 1 parses everything without writing; only a clean pass lets pass 2 write, so a bad export never leaves a partial
import behind. Both passes stream, so memory stays bounded. Errors are recorded as class names only.
"""
import logging
import zipfile
import zlib

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from strydr.jobs import queue
from strydr.pipeline.normalize.process import BATCH, apple_items, match_existing, write_metric, write_workout
from strydr.sources import apple
from strydr.sources.canonical import Workout
from strydr.store import models, settings
from strydr.store.util import utcnow

log = logging.getLogger("strydr.jobs")


def _set(engine: Engine, payload_id: int, **values) -> None:
    with Session(engine) as s:
        s.execute(update(models.ImportStatus).where(models.ImportStatus.payload_id == payload_id)
                  .values(updated_at=utcnow(), **values))
        s.commit()


def mark_failed(engine: Engine, payload_id: int, error: str) -> None:
    """Quarantine the payload and record why (class name only)."""
    with Session(engine) as s:
        s.execute(update(models.RawPayload).where(models.RawPayload.id == payload_id)
                  .values(status="quarantined", error=error))
        s.execute(update(models.ImportStatus).where(models.ImportStatus.payload_id == payload_id)
                  .values(state="failed", error=error, updated_at=utcnow()))
        s.commit()


# A bad or unreadable export: structure, zip, deflate, or an encrypted/unsupported member. Never retried.
BAD_EXPORT = (apple.AdapterError, zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error, EOFError, NotImplementedError,
              RuntimeError)


def run(engine: Engine, payload_id: int, default_tz: str) -> None:
    with Session(engine) as s:
        payload = s.get(models.RawPayload, payload_id)
        if payload.status == "processed":  # a crash after the final commit: the import is already complete
            return
        received_at = payload.received_at
        home_tz = settings.read(s, default_tz).home_tz
        if s.get(models.ImportStatus, payload_id) is None:
            s.add(models.ImportStatus(payload_id=payload_id, state="queued", updated_at=utcnow()))
            s.commit()
    _set(engine, payload_id, state="validating", error=None)
    try:
        for _ in apple_items(engine, payload_id, home_tz):
            pass
    except BAD_EXPORT as e:
        log.warning("apple import %s rejected: %s", payload_id, type(e).__name__)
        mark_failed(engine, payload_id, type(e).__name__)
        return

    _set(engine, payload_id, state="writing", workouts=0, merged=0, kept_existing=0, metrics=0, nights=0,
         date_from=None, date_to=None)
    c = {"workouts": 0, "merged": 0, "kept_existing": 0, "metrics": 0, "nights": 0}
    lo = hi = None
    # One transaction: any failure rolls the whole write back, so a retry starts from zero.
    with Session(engine) as s:
        for i, item in enumerate(apple_items(engine, payload_id, home_tz), 1):
            if isinstance(item, Workout):
                same_id = s.execute(select(models.Workout.id).where(models.Workout.workout_id == item.workout_id)).first() is not None
                matched = not same_id and match_existing(s, item, "apple") is not None
                written = write_workout(s, item, payload_id, received_at, apple.ADAPTER_VERSION)
                c["kept_existing" if same_id else "merged" if matched else "workouts"] += 1
            else:
                written = write_metric(s, item, payload_id, received_at, apple.ADAPTER_VERSION)
                if written:
                    c["nights" if item.metric == "sleep_analysis" else "metrics"] += 1
            if written:
                lo, hi = min(lo or item.local_date, item.local_date), max(hi or item.local_date, item.local_date)
            if i % BATCH == 0:
                s.flush()
                s.expunge_all()  # bound memory; nothing is committed
        s.execute(update(models.RawPayload).where(models.RawPayload.id == payload_id)
                  .values(status="processed", error=None, adapter_version=apple.ADAPTER_VERSION))
        s.execute(update(models.ImportStatus).where(models.ImportStatus.payload_id == payload_id)
                  .values(state="done", error=None, date_from=lo, date_to=hi, updated_at=utcnow(), **c))
        queue.enqueue_recompute(s, queue.local_today(settings.read(s, default_tz).home_tz))
        if settings.read_weather_enabled(s):
            queue.enqueue_weather(s)  # runs after the recompute, which derives the new display tracks
        s.commit()  # one commit: the rows, the counts, the processed mark and the follow-up jobs
    log.info("apple import %s done: %s", payload_id, c)
