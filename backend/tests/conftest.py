import json
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from strydr.api import create_app
from strydr.auth.service import create_user
from strydr.ingest import create_ingest_app
from strydr.jobs import Worker
from strydr.store import migrate, models
from strydr.store.engine import make_engine

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
KEY = secrets.token_hex(32)


@pytest.fixture
def engine(tmp_path):
    e = make_engine(tmp_path / "strydr.db", KEY)
    migrate.upgrade(e)
    yield e
    e.dispose()


@pytest.fixture
def token(engine):
    return create_user(engine, "runner", "correct horse battery", reset=True)


@pytest.fixture
def worker(engine):
    return Worker(engine, "UTC", backoff_s=0)


@pytest.fixture
def ingest(engine, token):
    return TestClient(create_ingest_app(engine), headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def app_client(engine, token):
    return TestClient(create_app(engine))


@pytest.fixture
def send(ingest, worker):
    def _send(body: bytes | dict, process=True):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        r = ingest.post("/ingest/hae", content=raw)
        assert r.status_code == 202
        if process:
            worker.run_all()
        return r
    return _send


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def count(engine, model, *where) -> int:
    from sqlalchemy import func, select
    with Session(engine) as s:
        return s.execute(select(func.count()).select_from(model).where(*where)).scalar_one()


def workouts(engine) -> dict[str, models.Workout]:
    from sqlalchemy import select
    with Session(engine) as s:
        return {w.workout_id: w for w in s.execute(select(models.Workout)).scalars()}
