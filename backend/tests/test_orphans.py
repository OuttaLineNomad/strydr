"""Orphan watch workouts: detection, the history guess, logging on the watch's times, dismissal."""
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from strydr.store import migrate

from conftest import KEY
from helpers import login
from test_plans import plan
from test_session_summary import D0, add_strength
from test_sessions import session

API = "/api/v1"


def now():
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def c(app_client):
    login(app_client)
    return app_client


def live(c, plan_id, start, minutes=10, **kw):
    return c.post(f"{API}/sessions", json=session(plan_id, start_utc=iso(start), end_utc=iso(start + timedelta(minutes=minutes)), **kw)).json()


def new_plan(c, name="Swing circuit"):
    return c.post(f"{API}/plans", json=plan(name)).json()["id"]


def test_happy_path_guess_and_log_with_hr_and_effort(c, engine):
    pid = new_plan(c)
    w0 = now() - timedelta(hours=3)
    live(c, pid, w0 - timedelta(days=7), rounds_done=7, weight_kg=15.88)  # same weekday
    live(c, pid, w0 - timedelta(days=2), rounds_done=3)
    add_strength(engine, "w1", start=w0, minutes=12, effort=6, hr_fn=lambda ts: 130)
    got = c.get(f"{API}/orphans").json()
    assert len(got) == 1 and got[0]["workout_id"] == "w1" and got[0]["duration_s"] == 720
    g = got[0]["guess"]
    assert g["plan_id"] == pid and g["plan_name"] == "Swing circuit" and g["format"] == "amrap"
    assert g["rounds_done"] == 7 and g["weight_kg"] == 15.88 and g["same_weekday"] is True
    assert g["session_date"] == (w0 - timedelta(days=7)).date().isoformat()
    r = c.post(f"{API}/orphans/w1/log", json={"plan_id": pid, "weight_kg": 15.88, "rounds_done": 7, "partial_moves": 0})
    assert r.status_code == 201
    s = r.json()
    assert s["source"] == "watch" and s["start_utc"] == iso(w0) and s["end_utc"] == iso(w0 + timedelta(minutes=12))
    assert s["events"] == [{"t_ms": 720_000, "kind": "end", "move": 0, "round": 0}] and s["fell_short"] == []
    assert s["active_s"] == 720 and s["rounds_done"] == 7
    sm = c.get(f"{API}/sessions/{s['id']}/summary").json()
    assert sm["source"] == "watch" and sm["matched_workout_id"] == "w1"
    assert sm["avg_hr"] == 130 and sm["effort"] == 6 and sm["effort_source"] == "watch"
    assert sm["moves"] == [] and sm["rounds"] == []
    assert c.get(f"{API}/orphans").json() == []  # not asked again
    assert c.get(f"{API}/sessions").json()[0]["id"] == s["id"]


def test_logging_against_a_round_mode_plan_keeps_tap_per_in_the_snapshot(c, engine):
    pid = c.post(f"{API}/plans", json=plan("Rounds", "complex", tap_per="round")).json()["id"]
    add_strength(engine, "w1", start=now() - timedelta(hours=3), minutes=12)
    r = c.post(f"{API}/orphans/w1/log", json={"plan_id": pid, "weight_kg": None, "rounds_done": 2, "partial_moves": 0})
    assert r.status_code == 201
    assert r.json()["plan"]["tap_per"] == "round"


def test_double_tap_makes_one_session(c, engine):
    pid = new_plan(c)
    add_strength(engine, "w1", start=now() - timedelta(hours=3))
    body = {"plan_id": pid, "weight_kg": None, "rounds_done": 4, "partial_moves": 0}
    a = c.post(f"{API}/orphans/w1/log", json=body)
    b = c.post(f"{API}/orphans/w1/log", json=body)
    assert (a.status_code, b.status_code) == (201, 200) and a.json()["id"] == b.json()["id"]
    assert len(c.get(f"{API}/sessions").json()) == 1


def test_overlapping_session_is_not_an_orphan(c, engine):
    pid = new_plan(c)
    w0 = now() - timedelta(hours=3)
    live(c, pid, w0 + timedelta(minutes=1))
    add_strength(engine, "w1", start=w0, minutes=12)
    assert c.get(f"{API}/orphans").json() == []
    add_strength(engine, "w2", start=w0 - timedelta(hours=1), minutes=12)  # a session far away does not hide it
    assert [o["workout_id"] for o in c.get(f"{API}/orphans").json()] == ["w2"]


def test_only_strength_and_only_last_14_days(c, engine):
    add_strength(engine, "run", start=now() - timedelta(hours=3), type_="run")
    add_strength(engine, "old", start=now() - timedelta(days=16))
    add_strength(engine, "recent", start=now() - timedelta(days=12))
    assert [o["workout_id"] for o in c.get(f"{API}/orphans").json()] == ["recent"]


def test_newest_first(c, engine):
    add_strength(engine, "a", start=now() - timedelta(days=3))
    add_strength(engine, "b", start=now() - timedelta(days=1))
    assert [o["workout_id"] for o in c.get(f"{API}/orphans").json()] == ["b", "a"]


def test_no_same_weekday_uses_the_latest_session(c, engine):
    pid = new_plan(c)
    w0 = now() - timedelta(hours=3)
    live(c, pid, w0 - timedelta(days=3), rounds_done=5)
    live(c, pid, w0 - timedelta(days=4), rounds_done=9)
    add_strength(engine, "w1", start=w0)
    g = c.get(f"{API}/orphans").json()[0]["guess"]
    assert g["same_weekday"] is False and g["rounds_done"] == 5


def test_no_history_means_no_guess(c, engine):
    add_strength(engine, "w1", start=now() - timedelta(hours=3))
    assert c.get(f"{API}/orphans").json()[0]["guess"] is None


def test_a_session_after_the_workout_is_not_a_guess(c, engine):
    pid = new_plan(c)
    w0 = now() - timedelta(days=3)
    live(c, pid, w0 + timedelta(days=1))
    add_strength(engine, "w1", start=w0)
    assert c.get(f"{API}/orphans").json()[0]["guess"] is None


def test_deleted_plan_is_skipped_for_the_guess(c, engine):
    gone, kept = new_plan(c, "Gone"), new_plan(c, "Kept")
    w0 = now() - timedelta(hours=3)
    live(c, kept, w0 - timedelta(days=9), rounds_done=2)
    live(c, gone, w0 - timedelta(days=7), rounds_done=8)
    c.delete(f"{API}/plans/{gone}")
    add_strength(engine, "w1", start=w0)
    g = c.get(f"{API}/orphans").json()[0]["guess"]
    assert g["plan_name"] == "Kept" and g["rounds_done"] == 2


def test_weekday_is_the_home_time_zone_weekday(c, engine):
    pid = new_plan(c)
    assert c.put(f"{API}/profile", json={"units": "metric", "home_tz": "Pacific/Auckland"}).status_code == 200
    base = now().replace(hour=20, minute=0, second=0) - timedelta(days=1)  # 20:00 UTC = next morning in Auckland
    live(c, pid, base - timedelta(days=7), rounds_done=6)  # same UTC weekday and same Auckland weekday as base
    live(c, pid, base - timedelta(days=1) - timedelta(hours=3), rounds_done=1)  # Auckland weekday differs
    add_strength(engine, "w1", start=base)
    g = c.get(f"{API}/orphans").json()[0]["guess"]
    assert g["same_weekday"] is True and g["rounds_done"] == 6


def test_dismiss_is_for_good_and_404s_for_unknown(c, engine):
    add_strength(engine, "w1", start=now() - timedelta(hours=3))
    assert c.post(f"{API}/orphans/w1/dismiss").status_code == 204
    assert c.post(f"{API}/orphans/w1/dismiss").status_code == 204
    assert c.get(f"{API}/orphans").json() == []
    assert c.post(f"{API}/orphans/nope/dismiss").status_code == 404
    assert c.post(f"{API}/orphans/nope/log", json={"plan_id": 1, "rounds_done": 1}).status_code == 404


def test_log_validates(c, engine):
    pid = new_plan(c)
    add_strength(engine, "w1", start=now() - timedelta(hours=3))
    u = f"{API}/orphans/w1/log"
    assert c.post(u, json={"plan_id": 999, "rounds_done": 1}).status_code == 422
    assert c.post(u, json={"plan_id": pid, "rounds_done": 1001}).status_code == 422
    assert c.post(u, json={"plan_id": pid, "rounds_done": -1}).status_code == 422
    assert c.post(u, json={"plan_id": pid, "rounds_done": 1, "weight_kg": 0.4}).status_code == 422
    assert c.post(u, json={"plan_id": pid, "rounds_done": 1, "weight_kg": 301}).status_code == 422
    assert c.post(u, json={"plan_id": pid, "rounds_done": 1, "partial_moves": 1}).status_code == 422  # a one-move plan
    assert c.get(f"{API}/sessions").json() == []
    assert c.post(u, json={"plan_id": pid, "rounds_done": 0, "weight_kg": None}).status_code == 201


def test_logged_session_counts_in_the_streak(c, engine):
    pid = new_plan(c)
    add_strength(engine, "w1", start=now() - timedelta(hours=3))
    c.post(f"{API}/orphans/w1/log", json={"plan_id": pid, "rounds_done": 3})
    assert c.get(f"{API}/streak").json()["this_week"] is True


def test_migration_0018_up_and_down(tmp_path):
    from strydr.store.engine import make_engine
    e = make_engine(tmp_path / "m.db", KEY)
    cfg = Config()
    cfg.set_main_option("script_location", str(migrate._DIR))
    with e.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0018")
        assert "orphan_dismissal" in inspect(conn).get_table_names()
        assert "source" in {x["name"] for x in inspect(conn).get_columns("workout_session")}
        command.downgrade(cfg, "0017")
        assert "orphan_dismissal" not in inspect(conn).get_table_names()
        assert "source" not in {x["name"] for x in inspect(conn).get_columns("workout_session")}
    e.dispose()


def test_deleting_a_logged_session_does_not_ask_again(c, engine):
    pid = new_plan(c)
    add_strength(engine, "w1", start=now() - timedelta(hours=3))
    sid = c.post(f"{API}/orphans/w1/log", json={"plan_id": pid, "rounds_done": 3}).json()["id"]
    assert c.delete(f"{API}/sessions/{sid}").status_code == 204
    assert c.get(f"{API}/orphans").json() == []


def test_watch_logged_session_has_no_overtime(c, engine):
    pid = c.post(f"{API}/plans", json=plan(cap_min=5)).json()["id"]
    add_strength(engine, "w1", start=now() - timedelta(hours=3), minutes=12)
    assert c.post(f"{API}/orphans/w1/log", json={"plan_id": pid, "rounds_done": 3}).json()["overtime_s"] == 0


def test_a_session_that_only_grazes_the_workout_leaves_it_an_orphan(c, engine):
    pid = new_plan(c)
    w0 = now() - timedelta(hours=3)
    add_strength(engine, "w1", start=w0, minutes=12)
    live(c, pid, w0 + timedelta(minutes=11), minutes=10)  # 1 min of overlap, under half the shorter span
    assert [o["workout_id"] for o in c.get(f"{API}/orphans").json()] == ["w1"]
    r = c.post(f"{API}/orphans/w1/log", json={"plan_id": pid, "rounds_done": 2})
    assert r.status_code == 201 and r.json()["source"] == "watch"
