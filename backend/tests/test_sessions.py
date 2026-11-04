import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from strydr.store import migrate, models

from conftest import KEY, count
from helpers import login
from test_plans import mv, plan

API = "/api/v1"


@pytest.fixture
def c(app_client):
    login(app_client)
    return app_client


def ev(t, kind="next", move=0, rnd=0):
    return {"t_ms": t, "kind": kind, "move": move, "round": rnd}


def session(plan_id=None, **kw):
    d = {"plan_id": plan_id, "plan": plan(), "weight_kg": 11.34, "start_utc": "2026-11-03T18:00:00Z",
         "end_utc": "2026-11-03T18:10:00Z", "events": [ev(1000), ev(2000)], "rounds_done": 4, "partial_moves": 2,
         "fell_short": []}
    d.update(kw)
    return d


def test_roundtrip_and_latest_first(c):
    p = c.post(f"{API}/plans", json=plan()).json()
    a = c.post(f"{API}/sessions", json=session(p["id"])).json()
    b = c.post(f"{API}/sessions", json=session(p["id"], start_utc="2026-11-04T18:00:00Z", end_utc="2026-11-04T18:05:00Z", rounds_done=5)).json()
    assert a["rounds_done"] == 4 and a["partial_moves"] == 2 and a["weight_kg"] == 11.34
    assert a["start_utc"] == "2026-11-03T18:00:00Z" and a["events"][0] == ev(1000)
    assert a["plan"]["name"] == "Swing circuit" and a["plan"]["moves"][0]["weight_kg"] == 16.0
    got = c.get(f"{API}/sessions", params={"plan_id": p["id"]}).json()
    assert [s["id"] for s in got] == [b["id"], a["id"]]
    assert c.get(f"{API}/sessions/{a['id']}").json() == a
    assert c.get(f"{API}/sessions/999").status_code == 404
    assert len(c.get(f"{API}/sessions", params={"plan_id": p["id"], "limit": 1}).json()) == 1
    assert c.get(f"{API}/sessions", params={"plan_id": 999}).json() == []


def test_plan_list_carries_the_last_session(c):
    p = c.post(f"{API}/plans", json=plan()).json()
    assert c.get(f"{API}/plans").json()[0]["last_session"] is None
    c.post(f"{API}/sessions", json=session(p["id"]))
    c.post(f"{API}/sessions", json=session(p["id"], start_utc="2026-11-04T18:00:00Z", end_utc="2026-11-04T18:05:00Z", rounds_done=5, partial_moves=0))
    last = c.get(f"{API}/plans").json()[0]["last_session"]
    assert last == {"rounds": 5, "partial_moves": 0, "date": "2026-11-04T18:00:00Z"}
    assert c.get(f"{API}/plans/{p['id']}").json()["last_session"] == last


def test_active_time_is_recomputed_excluding_pauses(c):
    ev_list = [ev(60_000, "pause"), ev(180_000, "resume"), ev(400_000, "pause")]  # last pause never resumes
    r = c.post(f"{API}/sessions", json=session(events=ev_list, plan=plan(cap_min=5))).json()
    # 600 s span - 120 s - 200 s paused
    assert r["active_s"] == 280 and r["overtime_s"] == 0


def test_overtime_recorded_for_amrap(c):
    r = c.post(f"{API}/sessions", json=session(plan=plan(cap_min=8), end_utc="2026-11-03T18:10:00Z")).json()
    assert r["active_s"] == 600 and r["overtime_s"] == 120
    e = c.post(f"{API}/sessions", json=session(plan=plan("E", "emom"), start_utc="2026-11-03T19:00:00Z", end_utc="2026-11-03T19:12:00Z", fell_short=[5, 5, 2])).json()
    assert e["overtime_s"] == 0 and e["fell_short"] == [2, 5]


def test_client_cannot_set_active_time(c):
    r = c.post(f"{API}/sessions", json={**session(), "active_s": 1, "overtime_s": 99}).json()
    assert r["active_s"] == 600 and r["overtime_s"] == 0


def test_retried_save_does_not_duplicate(c):
    p = c.post(f"{API}/plans", json=plan()).json()
    a = c.post(f"{API}/sessions", json=session(p["id"])).json()
    b = c.post(f"{API}/sessions", json=session(p["id"]))
    assert b.status_code == 201 and b.json()["id"] == a["id"]
    assert len(c.get(f"{API}/sessions").json()) == 1


@pytest.mark.parametrize("body", [
    session(events=[ev(i) for i in range(5001)]),
    session(start_utc="2026-11-03T18:00:00Z", end_utc="2026-11-03T22:00:01Z"),
    session(start_utc="2026-11-03T18:10:00Z", end_utc="2026-11-03T18:00:00Z"),
    session(events=[ev(4 * 3600 * 1000 + 1)]),
    session(events=[{"t_ms": 1, "kind": "dance", "move": 0, "round": 0}]),
    session(events=[ev(-1)]),
    session(plan={**plan(), "moves": []}),
    session(rounds_done=-1)])
def test_caps_and_bad_bodies_rejected(c, body):
    assert c.post(f"{API}/sessions", json=body).status_code == 422


def test_limits_accepted(c):
    ok = session(events=[ev(i) for i in range(5000)], end_utc="2026-11-03T22:00:00Z")
    assert c.post(f"{API}/sessions", json=ok).status_code == 201


def test_session_writes_do_not_enqueue_a_recompute(engine, c):
    before = count(engine, models.Job, models.Job.type == "recompute")
    c.post(f"{API}/sessions", json=session())
    assert count(engine, models.Job, models.Job.type == "recompute") == before
    assert models.WorkoutSession not in models.ANALYTIC


def test_needs_login(app_client):
    assert app_client.get(f"{API}/sessions").status_code == 401
    assert app_client.post(f"{API}/sessions", json=session()).status_code == 401
    assert app_client.get(f"{API}/sessions/1").status_code == 401


def test_migration_0015_up_and_down(tmp_path):
    from strydr.store.engine import make_engine
    e = make_engine(tmp_path / "m.db", KEY)
    cfg = Config()
    cfg.set_main_option("script_location", str(migrate._DIR))
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.upgrade(cfg, "0014")
    assert "workout_session" not in inspect(e).get_table_names()
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.upgrade(cfg, "head")
        cn.execute(text("INSERT INTO workout_session (plan, start_utc, end_utc, events, rounds_done, partial_moves, "
                        "fell_short, active_s, overtime_s, created_at) VALUES ('{}', '2026-01-01', '2026-01-01', '[]', "
                        "0, 0, '[]', 0, 0, '2026-01-01')"))
    assert "workout_session" in inspect(e).get_table_names()
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.downgrade(cfg, "0014")
    assert "workout_session" not in inspect(e).get_table_names()
    e.dispose()


def test_last_session_is_by_start_not_insertion_order(c):
    p = c.post(f"{API}/plans", json=plan()).json()
    c.post(f"{API}/sessions", json=session(p["id"], start_utc="2026-11-05T18:00:00Z", end_utc="2026-11-05T18:05:00Z", rounds_done=7))
    c.post(f"{API}/sessions", json=session(p["id"], start_utc="2026-11-02T18:00:00Z", end_utc="2026-11-02T18:05:00Z", rounds_done=1))
    assert c.get(f"{API}/plans").json()[0]["last_session"]["rounds"] == 7
    assert [s["rounds_done"] for s in c.get(f"{API}/sessions", params={"plan_id": p["id"]}).json()] == [7, 1]


def test_put_plan_keeps_last_session(c):
    p = c.post(f"{API}/plans", json=plan()).json()
    c.post(f"{API}/sessions", json=session(p["id"]))
    r = c.put(f"{API}/plans/{p['id']}", json=plan(cap_min=25))
    assert r.json()["last_session"] == {"rounds": 4, "partial_moves": 2, "date": "2026-11-03T18:00:00Z"}


def test_deleting_a_plan_detaches_its_sessions_so_a_reused_id_has_no_last(c):
    p = c.post(f"{API}/plans", json=plan()).json()
    s = c.post(f"{API}/sessions", json=session(p["id"])).json()
    assert c.delete(f"{API}/plans/{p['id']}").status_code == 204
    again = c.post(f"{API}/plans", json=plan("Other")).json()
    assert again["id"] == p["id"]  # SQLite hands the freed id back
    assert again["last_session"] is None
    assert c.get(f"{API}/plans").json()[0]["last_session"] is None
    assert c.get(f"{API}/sessions/{s['id']}").json()["plan_id"] is None  # the record itself is kept


@pytest.mark.parametrize("body", [
    session(start_utc="2026-11-03T18:00:00", end_utc="2026-11-03T18:10:00Z"),
    session(fell_short=[0]),
    session(fell_short=[91]),
    session(plan=plan("E", "emom"), fell_short=[13])])
def test_mixed_timestamps_and_bad_fell_short_are_422_not_500(c, body):
    assert c.post(f"{API}/sessions", json=body).status_code == 422


def test_both_naive_timestamps_are_taken(c):
    assert c.post(f"{API}/sessions", json=session(start_utc="2026-11-03T18:00:00", end_utc="2026-11-03T18:10:00")).status_code == 201
