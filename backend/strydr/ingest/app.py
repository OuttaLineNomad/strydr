"""Ingest-port app: the only route is POST /ingest/hae (AD-11)."""
import logging

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Engine

from strydr import jobs
from strydr.auth.tokens import verify_ingest_token
from strydr.ingest.stream import CHUNK, purge_incomplete, store_body

log = logging.getLogger("strydr.ingest")

__all__ = ["CHUNK", "create_ingest_app", "purge_incomplete"]


def create_ingest_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="strydr-ingest", docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/ingest/hae", status_code=202)
    async def ingest_hae(request: Request) -> Response:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not await run_in_threadpool(verify_ingest_token, engine, token):
            raise HTTPException(status_code=401, detail="invalid token", headers={"WWW-Authenticate": "Bearer"})

        payload_id, accepted, size = await store_body(engine, request, "hae", jobs.enqueue_process_raw)
        log.info("payload %s %s (%d bytes)", payload_id if accepted else "-", "accepted" if accepted else "duplicate", size)
        if accepted:
            jobs.wakeup.set()
        return Response(status_code=202)

    return app
