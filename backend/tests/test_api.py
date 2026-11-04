from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from strydr.store import models
from strydr.store.util import utcnow

from conftest import load_fixture


def test_api_requires_login(app_client):
    assert app_client.get("/api/v1/workouts").status_code == 401
    assert app_client.get("/api/v1/sync-status").status_code == 401
    assert app_client.post("/api/v1/auth/login", json={"username": "runner", "password": "wrong"}).status_code == 401


def test_login_cookie_flags_and_workout_list(engine, send, app_client):
    send(load_fixture("hae-export.json"))
    r = app_client.post("/api/v1/auth/login", json={"username": "runner", "password": "correct horse battery"})
    cookie = r.headers["set-cookie"].lower()
    assert r.status_code == 204 and "httponly" in cookie and "samesite=strict" in cookie
    rows = app_client.get("/api/v1/workouts").json()
    assert len(rows) == 9
    assert rows[0]["start"] >= rows[-1]["start"]
    assert all("latitude" not in str(r) for r in rows)
    assert any(r["has_hr"] is False for r in rows) and any(r["has_route"] is False for r in rows)
    app_client.post("/api/v1/auth/logout")
    assert app_client.get("/api/v1/workouts").status_code == 401


def test_sync_status_staleness(engine, send, app_client):
    app_client.post("/api/v1/auth/login", json={"username": "runner", "password": "correct horse battery"})
    assert app_client.get("/api/v1/sync-status").json()["stale"] is True  # nothing ever arrived
    send(load_fixture("hae-export.json"))
    st = app_client.get("/api/v1/sync-status").json()
    assert st["stale"] is False and st["last_processed_at"].endswith("Z") and st["quarantined"] == []
    with Session(engine) as s:
        s.execute(update(models.RawPayload).values(received_at=utcnow() - timedelta(days=8)))
        s.commit()
    assert app_client.get("/api/v1/sync-status").json()["stale"] is True
