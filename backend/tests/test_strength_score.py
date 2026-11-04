"""Strength score (CAP-12): the pure formula for every matrix row, then the routes."""
import pytest

from helpers import login
from strydr.progress import ScoreInput, scores, session_rates
from datetime import datetime

from test_plan_progress import add, day
from test_session_summary import add_strength
from test_plans import mv, plan
from test_sessions import session

API = "/api/v1"


def snap(fmt="amrap", moves=None):
    return {"format": fmt, "moves": moves or [mv(f"M{i}", reps=10) for i in range(5)]}


def si(plan_=None, kg=16.0, rounds=4, partial=0, active=1200, effort=None, fell=(), short=None):
    return ScoreInput(plan_ or snap(), kg, rounds, partial, list(fell), short, active, effort)


def test_first_is_100():
    assert scores([si()]) == [100]


def test_heavier_same_work():
    assert scores([si(kg=16), si(kg=20)]) == [100, 125]


def test_more_rounds():
    assert scores([si(rounds=4), si(rounds=5)]) == [100, 125]


def test_easier():
    assert scores([si(effort=8), si(effort=6)]) == [100, 110]


def test_one_effort_missing():
    assert scores([si(effort=8), si()]) == [100, 100]


def test_partial_round_instances():
    r = session_rates(snap(moves=[mv(f"M{i}", reps=10, weight_kg=None) for i in range(5)]), None, 4, 2, [], None, 60)
    assert [r[f"M{i}"] for i in range(5)] == [50, 50, 40, 40, 40]  # reps x bell 1, per active minute


def test_bodyweight_bell_counts_one():
    assert session_rates(snap(moves=[mv("Push-up", reps=10, weight_kg=None)]), None, 3, 0, [], None, 60) == {"Push-up": 30}


def test_timed_move_amount():
    assert session_rates(snap(moves=[mv("Plank", reps=None, seconds=30, weight_kg=None)]), None, 2, 0, [], None, 60) == {"Plank": 60}


def test_emom_short_answer():
    p = snap("emom", [mv("A", reps=10, weight_kg=None)])
    r = session_rates(p, None, 6, 0, [5], {"5": 7}, 60)
    assert r == {"A": 57}
    assert session_rates(p, None, 6, 0, [5], {"5": None}, 60) == {"A": 60}  # unanswered: the target


def test_bell_delta_and_floor():
    p = snap(moves=[mv("A", reps=10, weight_kg=16), mv("B", reps=10, weight_kg=1)])
    r = session_rates(p, 4, 1, 0, [], None, 60)  # delta -12: A 4, B floored to 0.5
    assert r == {"A": 40, "B": 5}


def test_renamed_moves_and_zero_active_are_null():
    other = snap(moves=[mv("Other", reps=10)])
    assert scores([si(), si(other)]) == [100, None]
    assert scores([si(), si(active=0)]) == [100, None]
    assert scores([si(active=0), si()]) == [None, 100]  # an empty first session is skipped as baseline
    assert scores([si(active=0), si(active=0)]) == [None, None]


def test_emom_shortfall_never_negative():
    p = snap("emom", [mv("A", reps=10, weight_kg=None)])
    assert session_rates(p, None, 1, 0, [1], {"1": 0}, 60) == {"A": 0.0}


@pytest.fixture
def c(app_client):
    login(app_client)
    return app_client


def test_routes_and_library(c):
    pl = plan(moves=[mv("Swing", weight_kg=16)])
    p = c.post(f"{API}/plans", json=pl).json()
    pid = p["id"]
    add(c, pid, 3, plan=pl, weight_kg=16, rounds_done=4, partial_moves=0)
    got = c.get(f"{API}/plans/{pid}/progress").json()
    assert [s["score"] for s in got["sessions"]] == [100]  # the row carries 100; the page hides it
    assert c.get(f"{API}/plans").json()[0]["strength_score"] is None
    add(c, pid, 5, plan=pl, weight_kg=16, rounds_done=5, partial_moves=0)
    b = add(c, pid, 10, plan=pl, weight_kg=20, rounds_done=5, partial_moves=0)
    got = c.get(f"{API}/plans/{pid}/progress").json()
    assert [s["score"] for s in got["sessions"]] == [156, 125, 100]
    assert got["now"]["score"] == 156 and got["then"]["score"] == 100 and got["now"]["id"] == b["id"]
    lib = c.get(f"{API}/plans").json()[0]
    assert (lib["strength_score"], lib["strength_change"]) == (156, 56)
    one = c.get(f"{API}/plans/{pid}").json()
    assert (one["strength_score"], one["strength_change"]) == (156, 56)
    assert got["plan"]["strength_score"] == 156


def _two_same(c, pl, ns=(3, 4)):
    p = c.post(f"{API}/plans", json=pl).json()
    ids = [add(c, p["id"], n, plan=pl, weight_kg=16, rounds_done=4, partial_moves=0)["id"] for n in ns]
    return p["id"], ids


def _check(c, pid, row_score):
    got = c.get(f"{API}/plans/{pid}/progress").json()
    assert got["sessions"][0]["score"] == row_score and got["plan"]["strength_score"] == row_score
    assert c.get(f"{API}/plans").json()[0]["strength_score"] == row_score
    assert c.get(f"{API}/plans/{pid}").json()["strength_score"] == row_score


def test_manual_effort_reaches_the_score(c):
    pid, (a, b) = _two_same(c, plan(moves=[mv("Swing", weight_kg=16)]))
    c.put(f"{API}/sessions/{a}/effort", json={"effort": 8})
    c.put(f"{API}/sessions/{b}/effort", json={"effort": 6})
    _check(c, pid, 110)


def test_watch_effort_reaches_the_score(c, engine):
    pid, (a, b) = _two_same(c, plan(moves=[mv("Swing", weight_kg=16)]))
    c.put(f"{API}/sessions/{a}/effort", json={"effort": 8})
    c.put(f"{API}/sessions/{b}/effort", json={"effort": 8})
    add_strength(engine, wid="w", start=datetime(2026, 11, 4, 17, 59), effort=6)  # the watch rating beats the manual 8
    _check(c, pid, 110)
