from datetime import datetime

import pytest

from strydr.jobs import reparse
from strydr.store import models

from conftest import count, load_fixture, workouts
from helpers import add_run, login, recompute_now

API = "/api/v1"


@pytest.fixture
def c(engine, app_client):
    add_run(engine, "r1", datetime(2026, 10, 20, 7), 10, 3.0, type_="run")
    add_run(engine, "w1", datetime(2026, 10, 21, 7), 10, 1.5, type_="walk")
    add_run(engine, "h1", datetime(2026, 10, 22, 7), 10, 1.2, type_="hike")
    recompute_now(engine, "2026-10-26")
    login(app_client)
    return app_client


def _ids(c, **q):
    return sorted(w["workout_id"] for w in c.get(f"{API}/workouts", params=q).json())


def _pending(engine):
    return count(engine, models.Job, models.Job.type == "recompute", models.Job.status == "pending")


def test_list_type_filter_single_and_comma(c):
    assert _ids(c, type="run") == ["r1"]
    assert _ids(c, type="walk,hike") == ["h1", "w1"]
    assert _ids(c, type="walk") == ["w1"]
    assert _ids(c) == ["h1", "r1", "w1"]
    assert _ids(c, type="walk, hike") == ["h1", "w1"]
    assert c.get(f"{API}/workouts", params={"type": "walk,swim"}).status_code == 422


def test_change_type_writes_override_and_enqueues_recompute(engine, c):
    before = _pending(engine)
    r = c.put(f"{API}/workouts/w1/type", json={"type": "run"})
    assert r.status_code == 200 and r.json()["type"] == "run"
    assert c.get(f"{API}/workouts/w1").json()["workout"]["type"] == "run"
    assert count(engine, models.WorkoutTypeOverride) == 1
    assert _pending(engine) == before + 1
    assert _ids(c, type="run") == ["r1", "w1"] and _ids(c, type="walk,hike") == ["h1"]


def test_same_type_is_harmless(engine, c):
    before = _pending(engine)
    assert c.put(f"{API}/workouts/w1/type", json={"type": "walk"}).status_code == 200
    assert c.get(f"{API}/workouts/w1").json()["workout"]["type"] == "walk"
    assert _pending(engine) == before


def test_type_bad_input(c):
    assert c.put(f"{API}/workouts/w1/type", json={"type": "swim"}).status_code == 422
    assert c.put(f"{API}/workouts/nope/type", json={"type": "run"}).status_code == 404


def test_carry_set_shows_on_detail_and_list_then_clears(c):
    assert c.get(f"{API}/workouts/w1").json()["carry_kg"] is None
    assert c.put(f"{API}/workouts/w1/carry", json={"weight_kg": 11.3}).json() == {"carry_kg": 11.3}
    d = c.get(f"{API}/workouts/w1").json()
    assert d["carry_kg"] == 11.3 and d["workout"]["carry_kg"] == 11.3
    by_id = {w["workout_id"]: w["carry_kg"] for w in c.get(f"{API}/workouts").json()}
    assert by_id == {"w1": 11.3, "r1": None, "h1": None}
    assert c.delete(f"{API}/workouts/w1/carry").json() == {"carry_kg": None}
    assert c.get(f"{API}/workouts/w1").json()["carry_kg"] is None


@pytest.mark.parametrize("kg", [0, -1, 101])
def test_carry_bounds(c, kg):
    assert c.put(f"{API}/workouts/w1/carry", json={"weight_kg": kg}).status_code == 422


def test_carry_upper_edge(c):
    assert c.put(f"{API}/workouts/w1/carry", json={"weight_kg": 100}).status_code == 200
    assert c.put(f"{API}/workouts/w1/carry", json={"weight_kg": 100.01}).status_code == 422


def test_carry_unknown_workout(c):
    assert c.put(f"{API}/workouts/nope/carry", json={"weight_kg": 5}).status_code == 404
    assert c.delete(f"{API}/workouts/nope/carry").status_code == 404


def test_carry_does_not_enqueue_recompute(engine, c):
    before = _pending(engine)
    c.put(f"{API}/workouts/w1/carry", json={"weight_kg": 5})
    c.delete(f"{API}/workouts/w1/carry")
    assert _pending(engine) == before


def _reparse(engine, worker):
    with engine.begin() as conn:
        conn.execute(models.Workout.__table__.update().values(adapter_version=0))
    assert reparse.enqueue_if_stale(engine)
    worker.run_all()


def test_changed_type_and_carry_survive_reparse(engine, app_client, send, worker):
    send(load_fixture("hae-export.json"))
    login(app_client)
    wid = next(w.workout_id for w in workouts(engine).values() if w.type == "walk")
    app_client.put(f"{API}/workouts/{wid}/type", json={"type": "run"})
    app_client.put(f"{API}/workouts/{wid}/carry", json={"weight_kg": 7})
    _reparse(engine, worker)
    d = app_client.get(f"{API}/workouts/{wid}").json()
    assert d["workout"]["type"] == "run" and d["carry_kg"] == 7


def test_no_foreign_keys_and_not_analytic():
    assert [f.column.table.name for f in models.WorkoutCarry.__table__.foreign_keys] == []
    assert models.WorkoutCarry not in models.ANALYTIC


def test_new_endpoints_need_login(app_client):
    assert app_client.put(f"{API}/workouts/w1/type", json={"type": "run"}).status_code == 401
    assert app_client.put(f"{API}/workouts/w1/carry", json={"weight_kg": 5}).status_code == 401
    assert app_client.delete(f"{API}/workouts/w1/carry").status_code == 401
