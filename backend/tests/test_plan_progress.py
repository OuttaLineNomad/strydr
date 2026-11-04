"""Progress per workout: the sessions of one plan, effort, missed reps, the changed flag and then-vs-now."""
from datetime import datetime, timedelta

import pytest

from helpers import login
from test_plans import mv, plan
from test_session_summary import add_strength
from test_sessions import session

API = "/api/v1"


@pytest.fixture
def c(app_client):
    login(app_client)
    return app_client


def day(n):
    """(start, end) of a 10-minute session on November `n`, 2026."""
    return {"start_utc": f"2026-11-{n:02d}T18:00:00Z", "end_utc": f"2026-11-{n:02d}T18:10:00Z"}


def add(c, pid, n, **kw):
    return c.post(f"{API}/sessions", json=session(pid, **day(n), **kw)).json()


def progress(c, pid):
    return c.get(f"{API}/plans/{pid}/progress").json()


def test_amrap_gain_then_and_now(c):
    pl = plan(moves=[mv("Swing", weight_kg=11.34), mv("Squat", weight_kg=11.34)])
    p = c.post(f"{API}/plans", json=pl).json()
    a = add(c, p["id"], 3, plan=pl, weight_kg=11.34, rounds_done=4, partial_moves=0)
    b = add(c, p["id"], 10, plan=pl, weight_kg=15.88, rounds_done=6, partial_moves=1)
    c.put(f"{API}/sessions/{a['id']}/effort", json={"effort": 8})
    c.put(f"{API}/sessions/{b['id']}/effort", json={"effort": 6})
    got = progress(c, p["id"])
    assert got["plan"]["id"] == p["id"]
    assert [s["id"] for s in got["sessions"]] == [b["id"], a["id"]]
    assert got["then"]["id"] == a["id"] and got["now"]["id"] == b["id"]
    assert got["then"]["effort"] == 8 and got["now"]["effort"] == 6
    assert got["now"]["rounds_done"] == 6 and got["now"]["partial_moves"] == 1 and got["now"]["move_count"] == 2
    assert got["now"]["cap_min"] == 20 and got["now"]["missed_reps"] is None
    assert got["then"]["avg_hr"] is None and got["now"]["weight_kg"] == 15.88


def test_one_session_has_no_then_or_now(c):
    p = c.post(f"{API}/plans", json=plan()).json()
    assert progress(c, p["id"]) | {"plan": None} == {"plan": None, "sessions": [], "then": None, "now": None}
    add(c, p["id"], 3)
    got = progress(c, p["id"])
    assert len(got["sessions"]) == 1 and got["then"] is None and got["now"] is None


def test_unknown_plan_is_404(c):
    assert c.get(f"{API}/plans/999/progress").status_code == 404


def test_other_plans_sessions_are_left_out(c):
    p = c.post(f"{API}/plans", json=plan()).json()
    q = c.post(f"{API}/plans", json=plan("Other")).json()
    add(c, p["id"], 3)
    add(c, q["id"], 4)
    assert len(progress(c, p["id"])["sessions"]) == 1


def test_effort_watch_rating_beats_manual(c, engine):
    p = c.post(f"{API}/plans", json=plan()).json()
    s = add(c, p["id"], 3)
    add(c, p["id"], 4)
    c.put(f"{API}/sessions/{s['id']}/effort", json={"effort": 7})
    add_strength(engine, wid="w", start=datetime(2026, 11, 3, 17, 59), effort=5)
    # session() puts the start at 18:00 on the 3rd, which add_strength's D0 also is
    got = progress(c, p["id"])
    assert got["then"]["effort"] == 5
    assert got["now"]["effort"] is None  # no watch match and no pick: missing


def test_watch_estimate_loses_to_manual(c, engine):
    p = c.post(f"{API}/plans", json=plan()).json()
    s = add(c, p["id"], 3)
    add(c, p["id"], 4)
    add_strength(engine, wid="w", start=datetime(2026, 11, 3, 17, 59), effort=5, estimated=True)
    assert progress(c, p["id"])["then"]["effort"] == 5  # the estimate stands in when nothing else exists
    c.put(f"{API}/sessions/{s['id']}/effort", json={"effort": 7})
    assert progress(c, p["id"])["then"]["effort"] == 7


def test_then_and_now_carry_avg_hr_from_the_match(c, engine):
    p = c.post(f"{API}/plans", json=plan()).json()
    add(c, p["id"], 3, events=[{"t_ms": 60_000, "kind": "end", "move": 0, "round": 0}])
    add(c, p["id"], 4)
    add_strength(engine, wid="w", start=datetime(2026, 11, 3, 17, 59), hr_fn=lambda ts: 120)
    got = progress(c, p["id"])
    assert got["then"]["avg_hr"] == pytest.approx(120, abs=0.1) and got["now"]["avg_hr"] is None


def emom_plan():
    return plan("Every minute", "emom", emom_min=6, moves=[mv("Swing", reps=10), mv("Squat", reps=12)])


def emom(c, pid, n, short, answers):
    s = add(c, pid, n, plan=emom_plan(), fell_short=short)
    if answers:
        c.put(f"{API}/sessions/{s['id']}/short", json=answers)
    return s


def test_emom_missed_reps_sum_and_unknown(c):
    p = c.post(f"{API}/plans", json=emom_plan()).json()
    emom(c, p["id"], 3, [1, 2, 3], {"1": 6, "2": 8, "3": 4})  # (10-6) + (12-8) + (10-4) = 14
    emom(c, p["id"], 4, [1, 2], {"1": 8, "2": 12})  # 2 + 0
    emom(c, p["id"], 5, [1, 2], {"1": 8})  # minute 2 unanswered
    emom(c, p["id"], 6, [], None)  # nothing fell short
    got = progress(c, p["id"])
    assert [s["missed_reps"] for s in got["sessions"]] == [0, None, 2, 14]
    assert got["then"]["missed_reps"] == 14 and got["now"]["missed_reps"] == 0


def test_complex_fields(c):
    pl = plan("Complex", "complex", rounds=4)
    p = c.post(f"{API}/plans", json=pl).json()
    add(c, p["id"], 3, plan=pl, rounds_done=4, partial_moves=0)
    add(c, p["id"], 4, plan=pl, rounds_done=3, partial_moves=1)
    got = progress(c, p["id"])
    assert got["then"]["target_rounds"] == 4 and got["then"]["rounds_done"] == 4
    assert got["now"]["rounds_done"] == 3 and got["now"]["cap_min"] is None


def test_changed_flag_follows_the_current_plan(c):
    p = c.post(f"{API}/plans", json=plan(moves=[mv("Swing"), mv("Squat")])).json()
    add(c, p["id"], 3, plan=plan(moves=[mv("Swing"), mv("Squat")]))
    add(c, p["id"], 4, plan=plan(moves=[mv("Swing"), mv("Squat")]))
    got = progress(c, p["id"])
    assert [s["changed"] for s in got["sessions"]] == [False, False]
    # a heavier bell is not a change; a renamed move is
    c.put(f"{API}/plans/{p['id']}", json=plan(moves=[mv("Swing", weight_kg=24), mv("Goblet squat")]))
    got = progress(c, p["id"])
    assert [s["changed"] for s in got["sessions"]] == [True, True]
    assert got["then"]["changed"] is True
    c.put(f"{API}/plans/{p['id']}", json=plan(moves=[mv("Swing", weight_kg=24), mv("Squat")]))
    assert progress(c, p["id"])["then"]["changed"] is False
