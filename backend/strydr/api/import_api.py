"""Apple Health export import: upload on the private app port (AD-11, CAP-17) and its progress.

The zip streams straight into raw_chunk rows (AD-3) and is never spooled to disk. The job that reads it is import_apple.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from strydr.api import schemas as sc
from strydr.api.common import Api, rfc3339
from strydr.ingest.stream import store_body
from strydr.jobs import queue
from strydr.store import models
from strydr.store.util import utcnow

MAX_UPLOAD_BYTES = 4 * 1024 ** 3
ZIP_MAGIC = b"PK\x03\x04"
CONTENT_TYPES = {"application/zip", "application/octet-stream"}


def _out(row: models.ImportStatus) -> sc.ImportStatusOut:
    return sc.ImportStatusOut(
        payload_id=row.payload_id, state=row.state, workouts=row.workouts, merged=row.merged,
        kept_existing=row.kept_existing, metrics=row.metrics, nights=row.nights, date_from=row.date_from,
        date_to=row.date_to, error=row.error, updated_at=rfc3339(row.updated_at))


def _enqueue(s: Session, payload_id: int) -> None:
    s.add(models.ImportStatus(payload_id=payload_id, state="queued", updated_at=utcnow()))
    queue.enqueue_import_apple(s, payload_id)


def _retry_failed(api: Api, payload_id: int) -> sc.ImportStatusOut | None:
    """Re-uploading an export whose import failed queues it again. None if its status is not failed."""
    with Session(api.engine) as s:
        row = s.get(models.ImportStatus, payload_id)
        if row is None or row.state != "failed":
            return None
        row.state, row.error, row.date_from, row.date_to, row.updated_at = "queued", None, None, None, utcnow()
        row.workouts = row.merged = row.kept_existing = row.metrics = row.nights = 0
        s.execute(update(models.RawPayload).where(models.RawPayload.id == payload_id).values(status="accepted", error=None))
        queue.enqueue_import_apple(s, payload_id)
        s.commit()
        return _out(row)


def _status(api: Api, payload_id: int) -> sc.ImportStatusOut | None:
    with Session(api.engine) as s:
        row = s.get(models.ImportStatus, payload_id)
        return _out(row) if row else None


def router(api: Api) -> APIRouter:
    r = APIRouter(prefix="/import", tags=["import"], dependencies=api.auth)

    @r.post(
        "/apple", status_code=202, response_model=sc.ImportStatusOut,
        responses={200: {"model": sc.ImportStatusOut, "description": "This export was already uploaded: its status"},
                   401: {"description": "Not authenticated"},
                   409: {"description": "The same bytes are stored as something other than an Apple export"},
                   413: {"description": "Body over 4 GiB"},
                   415: {"description": "Body is not a zip"}},
        openapi_extra={"requestBody": {"required": True, "content": {
            "application/zip": {"schema": {"type": "string", "format": "binary"}}}}},
    )
    async def upload_apple_import(request: Request) -> JSONResponse:
        """Upload an Apple Health `export.zip` (raw body). It is validated and imported by a background job."""
        if request.headers.get("content-type", "").split(";")[0].strip().lower() not in CONTENT_TYPES:
            raise HTTPException(status_code=415, detail="send the zip as application/zip")
        payload_id, accepted, _ = await store_body(
            api.engine, request, "apple", _enqueue, magic=ZIP_MAGIC, max_bytes=MAX_UPLOAD_BYTES)
        status = await run_in_threadpool(_status, api, payload_id)
        if status is None:  # the same bytes were stored as something other than an Apple export
            raise HTTPException(status_code=409, detail="already stored")
        retried = None if accepted else await run_in_threadpool(_retry_failed, api, payload_id)
        if retried is not None:
            status, accepted = retried, True
        if accepted:
            api.wake()
        return JSONResponse(status.model_dump(), status_code=202 if accepted else 200)

    @r.get("/apple", response_model=sc.ImportStatusOut | None)
    def get_apple_import() -> sc.ImportStatusOut | None:
        """The latest import's status, or null when none was uploaded."""
        with Session(api.engine) as s:
            row = s.execute(select(models.ImportStatus).order_by(models.ImportStatus.payload_id.desc()).limit(1)).scalar_one_or_none()
            return _out(row) if row else None

    return r
