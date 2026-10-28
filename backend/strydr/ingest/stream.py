"""Stream a request body into 1 MiB raw_chunk rows (AD-3). Shared by /ingest/hae and the Apple import upload.

Nothing is spooled to disk: the body goes from the socket to encrypted chunk rows, one chunk in memory at a time.
"""
import hashlib
from collections.abc import Callable

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from strydr.store import models
from strydr.store.util import utcnow

CHUNK = 1024 * 1024  # AD-3

Enqueue = Callable[[Session, int], None]


def purge_incomplete(engine: Engine) -> None:
    """Drop bodies whose upload never finished (crash or dropped connection)."""
    with Session(engine) as s:
        s.execute(delete(models.RawPayload).where(models.RawPayload.status == "receiving"))
        s.commit()


def _begin(engine: Engine, source: str) -> int:
    with Session(engine) as s:
        row = models.RawPayload(received_at=utcnow(), status="receiving", size_bytes=0, source=source)
        s.add(row)
        s.commit()
        return row.id


def _put_chunk(engine: Engine, payload_id: int, seq: int, data: bytes) -> None:
    with Session(engine) as s:
        s.add(models.RawChunk(payload_id=payload_id, seq=seq, data=data))
        s.commit()


def _discard(engine: Engine, payload_id: int) -> None:
    with Session(engine) as s:
        s.execute(delete(models.RawPayload).where(models.RawPayload.id == payload_id))
        s.commit()


def _existing(engine: Engine, sha: str) -> int | None:
    with Session(engine) as s:
        return s.execute(select(models.RawPayload.id).where(models.RawPayload.sha256 == sha)).scalar_one_or_none()


def _finish(engine: Engine, payload_id: int, sha: str, size: int, enqueue: Enqueue) -> int | None:
    """Publish the payload and its job in one transaction. None if the hash is a duplicate (the body is discarded)."""
    with Session(engine) as s:
        if s.execute(select(models.RawPayload.id).where(models.RawPayload.sha256 == sha)).first() is None:
            try:
                s.execute(
                    models.RawPayload.__table__.update().where(models.RawPayload.id == payload_id)
                    .values(sha256=sha, status="accepted", size_bytes=size)
                )
                enqueue(s, payload_id)
                s.commit()
                return payload_id
            except IntegrityError:  # concurrent identical upload won the race
                s.rollback()
    _discard(engine, payload_id)
    return None


async def store_body(engine: Engine, request: Request, source: str, enqueue: Enqueue, *,
                     magic: bytes | None = None, max_bytes: int | None = None) -> tuple[int, bool, int]:
    """Store the request body as a `source` payload and enqueue its job. Returns (payload id, accepted, bytes received).

    A duplicate body returns the id of the stored copy and accepted=False. An empty body is a 400, a body not
    starting with `magic` a 415 and one over `max_bytes` a 413; all of these discard what was received.
    """
    declared = request.headers.get("content-length")
    if max_bytes is not None and declared and declared.isdigit() and int(declared) > max_bytes:
        raise HTTPException(status_code=413, detail="body too large")
    payload_id = await run_in_threadpool(_begin, engine, source)
    sha, buf, seq, size = hashlib.sha256(), bytearray(), 0, 0
    checked = magic is None
    try:
        async for part in request.stream():
            sha.update(part)
            buf += part
            size += len(part)
            if max_bytes is not None and size > max_bytes:
                raise HTTPException(status_code=413, detail="body too large")
            if not checked and size >= len(magic):  # the first chunk is still in `buf`: nothing is flushed under 1 MiB
                if not buf.startswith(magic):
                    raise HTTPException(status_code=415, detail="unsupported body")
                checked = True
            while len(buf) >= CHUNK:
                chunk = bytes(buf[:CHUNK])
                del buf[:CHUNK]
                await run_in_threadpool(_put_chunk, engine, payload_id, seq, chunk)
                seq += 1
        if size == 0:
            raise HTTPException(status_code=400, detail="empty body")
        if not checked:
            raise HTTPException(status_code=415, detail="unsupported body")
        if buf:
            await run_in_threadpool(_put_chunk, engine, payload_id, seq, bytes(buf))
        digest = sha.hexdigest()
        stored = await run_in_threadpool(_finish, engine, payload_id, digest, size, enqueue)
    except BaseException:
        await run_in_threadpool(_discard, engine, payload_id)
        raise
    if stored is not None:
        return stored, True, size
    existing = await run_in_threadpool(_existing, engine, digest)
    return (existing if existing is not None else payload_id), False, size
