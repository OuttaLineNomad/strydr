"""The single job worker (AD-5, AD-16)."""
import logging
import threading
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from strydr.egress import Provider, ProviderConfig, make_provider
from strydr.egress.weather import OpenMeteo
from strydr.jobs import queue, reparse, snapshot
from strydr.jobs import weather as weather_job
from strydr.jobs.recompute import recompute
from strydr.pipeline import phrasing
from strydr.pipeline.normalize import AdapterError, apple_import, process_payload
from strydr.store import models, settings
from strydr.store.util import utcnow

log = logging.getLogger("strydr.jobs")
MAX_ATTEMPTS = 3


def _error_text(e: Exception) -> str:
    # Class name only, plus our own adapter messages: never echo payload content.
    return f"{type(e).__name__}: {e}"[:200] if isinstance(e, AdapterError) else type(e).__name__


class Worker:
    def __init__(self, engine: Engine, default_tz: str = "UTC", backoff_s: float = 5.0, *, db_key: str | None = None,
                 backup_dir: Path | None = None,
                 provider_factory: Callable[[ProviderConfig], Provider] = make_provider,
                 weather_client: OpenMeteo | None = None):
        self.engine, self.default_tz, self.backoff_s = engine, default_tz, backoff_s
        self.db_key, self.backup_dir, self.provider_factory = db_key, backup_dir, provider_factory
        self.weather_client = weather_client or OpenMeteo()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="strydr-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        queue.wakeup.set()
        if self._thread:
            self._thread.join(timeout=30)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.run_one():
                    queue.wakeup.wait(timeout=1.0)
                    queue.wakeup.clear()
            except Exception:
                log.exception("worker loop error")
                self._stop.wait(1.0)

    def run_all(self) -> int:
        """Drain due jobs synchronously (tests, and a deterministic seam for the loop)."""
        n = 0
        while self.run_one():
            n += 1
        return n

    def run_one(self) -> bool:
        with Session(self.engine) as s:
            job = queue.claim_next(s, utcnow())
            if job is None:
                return False
            job_id, jtype, payload_id, as_of, attempts = job.id, job.type, job.payload_id, job.as_of, job.attempts
        try:
            if jtype == "process_raw":
                self._process_raw(payload_id)
            elif jtype == "import_apple":
                apple_import.run(self.engine, payload_id, self.default_tz)
            elif jtype == "recompute":
                recompute(self.engine, as_of or self._today(), self.default_tz)
                self._after_recompute()
            elif jtype == "phrase":
                counts = phrasing.run(self.engine, self.default_tz, self.provider_factory, self._pipeline_waiting)
                log.info("phrase job: %s", counts)
            elif jtype == "snapshot":
                if self.db_key is None or self.backup_dir is None:
                    raise RuntimeError("snapshot needs the DB key and a backup directory")
                snapshot.snapshot(self.engine, self.db_key, self.backup_dir, self._today())
            elif jtype == "fetch_weather":
                if weather_job.fetch(self.engine, self.weather_client):
                    with Session(self.engine) as s:
                        queue.enqueue_recompute(s, self._today(s))
                        s.commit()
            elif jtype == "reparse":
                log.info("reparse: %d payloads", reparse.reparse(self.engine, self.default_tz))
            else:
                raise ValueError(f"unknown job type {jtype}")
        except Exception as e:
            log.warning("job %s (%s) failed on attempt %d: %s", job_id, jtype, attempts, type(e).__name__)
            self._fail(job_id, jtype, payload_id, attempts, _error_text(e), type(e).__name__)
        else:
            with Session(self.engine) as s:
                s.execute(update(models.Job).where(models.Job.id == job_id).values(status="done"))
                s.commit()
        return True

    def _process_raw(self, payload_id: int) -> None:
        counts = process_payload(self.engine, payload_id, self.default_tz)
        log.info("payload %s processed: %s", payload_id, counts)
        with Session(self.engine) as s:
            s.execute(update(models.RawPayload).where(models.RawPayload.id == payload_id).values(status="processed", error=None))
            queue.enqueue_recompute(s, self._today(s))
            if settings.read_weather_enabled(s):
                queue.enqueue_weather(s)  # runs after the recompute, which derives the new display tracks
            s.commit()

    def _after_recompute(self) -> None:
        """A new generation may carry insights with no cached phrasing yet (AD-9)."""
        with Session(self.engine) as s:
            if settings.read_ai(s).enabled:
                queue.enqueue_phrase(s)
                s.commit()

    def _pipeline_waiting(self) -> bool:
        with Session(self.engine) as s:
            return queue.busy_with_pipeline(s)

    def _today(self, s: Session | None = None) -> str:
        if s is None:
            with Session(self.engine) as own:
                return self._today(own)
        return queue.local_today(settings.read(s, self.default_tz).home_tz)

    def _fail(self, job_id: int, jtype: str, payload_id: int | None, attempts: int, err: str, exc_name: str) -> None:
        with Session(self.engine) as s:
            job = s.get(models.Job, job_id)
            job.last_error = err
            if attempts >= MAX_ATTEMPTS:
                job.status = "failed"
                if jtype == "process_raw" and payload_id is not None:
                    s.execute(update(models.RawPayload).where(models.RawPayload.id == payload_id)
                              .values(status="quarantined", error=err))
            else:
                job.status = "pending"
                job.run_after = utcnow() + timedelta(seconds=self.backoff_s * 2 ** (attempts - 1))
            s.commit()
        if jtype == "import_apple" and payload_id is not None and attempts >= MAX_ATTEMPTS:
            apple_import.mark_failed(self.engine, payload_id, exc_name)
