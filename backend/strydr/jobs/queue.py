"""Job table operations. Writers pass their own session so a write and its job commit together (AD-5)."""
import threading
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from strydr.store import models
from strydr.store.util import utcnow

PIPELINE = ("recompute", "process_raw", "reparse")  # what an import_apple yields to
wakeup = threading.Event()  # nudges the worker; it also polls, so a missed set() is harmless


def local_today(tz: str) -> str:
    """The as_of for a job enqueued now (AD-15). Only job producers read the clock, never the pipeline."""
    return datetime.now(UTC).astimezone(ZoneInfo(tz)).date().isoformat()


def enqueue_process_raw(s: Session, payload_id: int) -> None:
    now = utcnow()
    s.add(models.Job(type="process_raw", payload_id=payload_id, run_after=now, created_at=now))


def enqueue_import_apple(s: Session, payload_id: int) -> None:
    now = utcnow()
    s.add(models.Job(type="import_apple", payload_id=payload_id, run_after=now, created_at=now))


def enqueue_recompute(s: Session, as_of: str) -> None:
    """Coalescing (AD-5): at most one pending recompute, carrying the newest as_of."""
    pending = s.execute(
        select(models.Job).where(models.Job.type == "recompute", models.Job.status == "pending")
    ).scalars().first()
    if pending is not None:
        pending.as_of = max(pending.as_of or "", as_of)
        return
    now = utcnow()
    s.add(models.Job(type="recompute", as_of=as_of, run_after=now, created_at=now))


def _enqueue_once(s: Session, jtype: str) -> None:
    if s.execute(select(models.Job.id).where(models.Job.type == jtype, models.Job.status == "pending")).first() is None:
        now = utcnow()
        s.add(models.Job(type=jtype, run_after=now, created_at=now))


def enqueue_phrase(s: Session) -> None:
    _enqueue_once(s, "phrase")


def enqueue_snapshot(s: Session) -> None:
    _enqueue_once(s, "snapshot")


def enqueue_reparse(s: Session) -> None:
    _enqueue_once(s, "reparse")


def enqueue_weather(s: Session) -> None:
    _enqueue_once(s, "fetch_weather")


def busy_with_pipeline(s: Session) -> bool:
    """True while a recompute, process_raw, import_apple or reparse is waiting or running (AD-5: phrase yields to them)."""
    return s.execute(select(models.Job.id).where(
        models.Job.type.in_(PIPELINE + ("import_apple",)), models.Job.status.in_(("pending", "running"))
    ).limit(1)).first() is not None


def claim_next(s: Session, now: datetime) -> models.Job | None:
    job = s.execute(
        select(models.Job)
        .where(models.Job.status == "pending", models.Job.run_after <= now,
               or_(models.Job.type.not_in(("phrase", "fetch_weather")), ~_pipeline_waiting(PIPELINE + ("import_apple",))),
               or_(models.Job.type != "import_apple", ~_pipeline_waiting(PIPELINE)))
        .order_by(models.Job.id).limit(1)
    ).scalar_one_or_none()
    if job is not None:
        job.status = "running"
        job.attempts += 1
        s.commit()
    return job


def _pipeline_waiting(types: tuple[str, ...]):
    other = models.Job.__table__.alias("other")
    return exists().where(other.c.type.in_(types), other.c.status.in_(("pending", "running")))
