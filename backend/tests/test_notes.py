from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.store import models

from conftest import count
from helpers import add_run, login, recompute_now


def _setup(engine, app_client):
    add_run(engine, "r1", datetime(2026, 10, 20, 7), 30, 3.0)
    recompute_now(engine, "2026-10-26")
    login(app_client)


def test_note_roundtrip_and_survives_a_full_recompute(engine, app_client, worker):
    _setup(engine, app_client)
    r = app_client.put("/api/v1/workouts/r1/note", json={"text": "felt strong", "rpe": 7})
    assert r.status_code == 200 and r.json()["rpe"] == 7
    worker.run_all()  # the write enqueued a recompute (RPE is a pipeline input)
    recompute_now(engine, "2026-10-27")
    note = app_client.get("/api/v1/workouts/r1").json()["note"]
    assert (note["text"], note["rpe"]) == ("felt strong", 7)
    assert app_client.put("/api/v1/workouts/r1/note", json={"text": "tired legs", "rpe": None}).json()["rpe"] is None
    assert app_client.get("/api/v1/workouts/r1").json()["note"]["text"] == "tired legs"


def test_note_is_keyed_by_workout_id_without_fk(engine, app_client):
    _setup(engine, app_client)
    app_client.put("/api/v1/workouts/r1/note", json={"rpe": 3})
    with Session(engine) as s:
        assert [f.column.table.name for f in models.WorkoutNote.__table__.foreign_keys] == []
        assert s.execute(select(models.WorkoutNote.workout_id)).scalar_one() == "r1"


def test_write_enqueues_one_coalesced_recompute(engine, app_client):
    _setup(engine, app_client)
    app_client.put("/api/v1/workouts/r1/note", json={"rpe": 3})
    app_client.put("/api/v1/workouts/r1/note", json={"rpe": 4})
    app_client.delete("/api/v1/workouts/r1/note")
    assert count(engine, models.Job, models.Job.type == "recompute", models.Job.status == "pending") == 1


def test_delete_note_is_idempotent(engine, app_client):
    _setup(engine, app_client)
    app_client.put("/api/v1/workouts/r1/note", json={"text": "x"})
    assert app_client.delete("/api/v1/workouts/r1/note").status_code == 204
    assert app_client.delete("/api/v1/workouts/r1/note").status_code == 204
    assert app_client.get("/api/v1/workouts/r1").json()["note"] is None


def test_note_validation(engine, app_client):
    _setup(engine, app_client)
    put = lambda body, wid="r1": app_client.put(f"/api/v1/workouts/{wid}/note", json=body)  # noqa: E731
    assert put({"text": "ok", "rpe": 0}).status_code == 422
    assert put({"text": "ok", "rpe": 11}).status_code == 422
    assert put({"text": "  ", "rpe": None}).status_code == 422
    assert put({}).status_code == 422
    assert put({"rpe": 5}, "missing").status_code == 404


def test_notes_need_login(app_client):
    assert app_client.put("/api/v1/workouts/r1/note", json={"rpe": 3}).status_code == 401
    assert app_client.delete("/api/v1/workouts/r1/note").status_code == 401
    assert app_client.get("/api/v1/dashboard").status_code == 401
    assert app_client.get("/api/v1/profile").status_code == 401
