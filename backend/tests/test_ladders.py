"""Bodyweight levels (CAP-13): ladders, unlocks, step-down, the staircase, per-name score baselines."""
import re
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from strydr import progress as pg
from strydr.store import migrate, models

from conftest import KEY, count
from helpers import login
from test_plans import mv, plan
from test_sessions import session

API = "/api/v1"


@pytest.fixture
def c(app_client):
    login(app_client)
    return app_client


def lm(ladder="push-up", rung=1, reps=12, **kw):
    return {"name": "x", "reps": reps, "seconds": None, "weight_kg": None, "ladder": ladder, "rung": rung} | kw


def lplan(rung=1, reps=12, name="Push day", **kw):
    return plan(name, "complex", moves=[lm(rung=rung, reps=reps)], **kw)


def day(n, **kw):
    return {"start_utc": f"2026-11-{n:02d}T18:00:00Z", "end_utc": f"2026-11-{n:02d}T18:10:00Z"} | kw


def test_web_ladders_mirror_the_server():
    src = (Path(__file__).parents[2] / "web/src/lib/ladders.ts").read_text()
    for ladder, rungs in pg.LADDERS.items():
        m = re.search(rf"'{ladder}':\s*\[([^\]]*)\]", src)
        assert m, ladder
        assert re.findall(r"'([^']+)'", m.group(1)) == rungs


def test_ladder_move_is_named_from_the_rung(c):
    got = c.post(f"{API}/plans", json=lplan(1)).json()
    assert got["moves"][0]["name"] == "Incline push-up" and got["moves"][0]["rung"] == 1
    put = c.put(f"{API}/plans/{got['id']}", json=lplan(2)).json()
    assert put["moves"][0]["name"] == "Knee push-up"
    pull = c.post(f"{API}/plans", json=plan("Pull", "complex", moves=[lm("pull-up", 1)])).json()
    assert pull["moves"][0]["name"] == "Band-assisted pull-up"


@pytest.mark.parametrize("move", [
    lm(weight_kg=16.0), lm(reps=None, seconds=30), lm(rung=9), lm(rung=None), lm(ladder=None), lm(ladder="sit-up"),
])
def test_bad_ladder_moves_are_422(c, move):
    assert c.post(f"{API}/plans", json=plan("Bad", "complex", moves=[move])).status_code == 422


def _plan_with_sessions(c, rung=1, reps=12, rounds=3, **kw):
    p = c.post(f"{API}/plans", json=lplan(rung)).json()
    pl = lplan(rung, reps)
    pl["moves"][0]["name"] = p["moves"][0]["name"]
    s = c.post(f"{API}/sessions", json=session(p["id"], plan=pl, rounds_done=rounds, partial_moves=0, weight_kg=None, **day(3), **kw)).json()
    return p["id"], s["id"]


def test_unlock_after_three_sets_of_twelve(c):
    pid, sid = _plan_with_sessions(c)
    assert c.get(f"{API}/plans/{pid}").json()["unlocks"] == [{"move_index": 0, "ladder": "push-up", "from_rung": 1, "to_rung": 2}]
    assert c.get(f"{API}/plans").json()[0]["unlocks"][0]["to_rung"] == 2
    assert c.get(f"{API}/sessions/{sid}/summary").json()["unlocked"] == ["Knee push-up"]


def test_not_enough_sets_or_reps(c):
    pid, _ = _plan_with_sessions(c, rounds=2)
    assert c.get(f"{API}/plans/{pid}").json()["unlocks"] == []
    pid2 = c.post(f"{API}/plans", json=lplan(1, name="Ten")).json()["id"]
    pl = lplan(1, 10, name="Ten")
    c.post(f"{API}/sessions", json=session(pid2, plan=pl, rounds_done=3, partial_moves=0, weight_kg=None, **day(4)))
    assert c.get(f"{API}/plans/{pid2}").json()["unlocks"] == []


def test_top_rung_never_unlocks(c):
    pid, sid = _plan_with_sessions(c, rung=4)
    assert c.get(f"{API}/plans/{pid}").json()["unlocks"] == []
    assert c.get(f"{API}/sessions/{sid}/summary").json()["unlocked"] == []


def test_step_down_blocks_the_unlock_and_can_be_undone(c, engine):
    pid, sid = _plan_with_sessions(c)
    before = count(engine, models.Job, models.Job.type == "recompute")
    assert c.put(f"{API}/sessions/{sid}/rungs", json={"0:2": 0}).json() == {"0:2": 0}
    sets = c.get(f"{API}/sessions/{sid}/summary").json()["ladder_sets"]
    assert [(x["instance"], x["planned_rung"], x["rung"]) for x in sets] == [(0, 1, 1), (1, 1, 1), (2, 1, 0)]
    assert c.get(f"{API}/plans/{pid}").json()["unlocks"] == []
    assert c.put(f"{API}/sessions/{sid}/rungs", json={"0:2": None}).json() == {}
    assert len(c.get(f"{API}/plans/{pid}").json()["unlocks"]) == 1
    assert count(engine, models.Job, models.Job.type == "recompute") == before


def test_bad_rung_puts_are_422(c):
    _, sid = _plan_with_sessions(c)
    for body in ({"0:2": 3}, {"5:0": 0}, {"0:3": 0}, {"x": 0}, {"0:0": -1}):
        assert c.put(f"{API}/sessions/{sid}/rungs", json=body).status_code == 422, body
    plain = c.post(f"{API}/sessions", json=session(plan=plan(), **day(5))).json()["id"]
    assert c.put(f"{API}/sessions/{plain}/rungs", json={"0:0": 0}).status_code == 422
    assert c.put(f"{API}/sessions/999/rungs", json={}).status_code == 404


def test_accepting_the_offer_renames_the_move(c):
    pid, _ = _plan_with_sessions(c)
    got = c.put(f"{API}/plans/{pid}", json=lplan(2)).json()
    assert got["moves"][0]["name"] == "Knee push-up" and got["unlocks"] == []


def test_staircase_is_best_set_per_session(c):
    pid, a = _plan_with_sessions(c)  # incline 3 x 12 on the 3rd
    for n, rung, reps in ((4, 2, 6), (5, 2, 9)):
        pl = lplan(rung, reps)
        pl["moves"][0]["name"] = pg.rung_name("push-up", rung)
        c.post(f"{API}/sessions", json=session(pid, plan=pl, rounds_done=3, partial_moves=0, weight_kg=None, **day(n)))
    c.put(f"{API}/sessions/{a}/rungs", json={"0:0": 0})  # one wall set does not change the best
    got = c.get(f"{API}/ladders/push-up/history").json()
    assert [(p["rung"], p["reps"]) for p in got] == [(1, 12), (2, 6), (2, 9)]
    assert got[0]["date"] == "2026-11-03T18:00:00Z" and got[0]["session_id"] == a
    assert c.get(f"{API}/ladders/pull-up/history").json() == []
    assert c.get(f"{API}/ladders/sit-up/history").status_code == 422


def test_emom_fell_short_answer_lowers_reps():
    plan_ = {"format": "emom", "moves": [lm(rung=1, reps=12)]}
    sets = pg.ladder_sets(plan_, 3, 0, [2], {"2": 9}, None)
    assert [s.reps for s in sets] == [12, 9, 12]
    assert pg.unlocks(plan_["moves"], sets) == []


def test_score_baseline_is_per_move_name():
    def si(name, rounds):
        return pg.ScoreInput({"format": "amrap", "moves": [mv(name, reps=10, weight_kg=None), mv("Swing", reps=10)]},
                             16.0, rounds, 0, [], None, 600, None)
    got = pg.scores([si("Incline push-up", 4), si("Knee push-up", 4), si("Knee push-up", 5)])
    # the rung-up session scores from Swing alone; the next compares Knee with it and Swing with the first
    assert got == [100, 100, 125]
    only_new = pg.scores([si("Incline push-up", 4), pg.ScoreInput({"format": "amrap", "moves": [mv("Knee push-up", reps=10, weight_kg=None)]}, 16.0, 4, 0, [], None, 600, None)])
    assert only_new == [100, None]


def test_migration_0017_up_and_down(tmp_path):
    from strydr.store.engine import make_engine
    e = make_engine(tmp_path / "m.db", KEY)
    cfg = Config()
    cfg.set_main_option("script_location", str(migrate._DIR))

    def cols():
        return {x["name"] for x in inspect(e).get_columns("workout_session")}
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.upgrade(cfg, "0016")
    assert "set_rungs" not in cols()
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.upgrade(cfg, "head")
    assert "set_rungs" in cols()
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.downgrade(cfg, "0016")
    assert "set_rungs" not in cols()
    e.dispose()


def lsets(*rows):
    return [pg.LadderSet(m, k, "push-up", r, r, reps) for m, k, r, reps in rows]


def test_unlock_counts_sets_by_ladder_and_rung_not_position():
    moves = [lm(rung=1), lm(rung=2)]
    only_first = lsets(*[(0, k, 1, 12) for k in range(3)], *[(1, k, 2, 12) for k in range(2)])
    assert [u["move_index"] for u in pg.unlocks(moves, only_first)] == [0]  # (a) one of two reaches 3 x 12
    partial = pg.ladder_sets({"format": "amrap", "moves": [lm(rung=0), lm(rung=1)]}, 2, 1, [], None, None)
    assert pg.unlocks([lm(rung=1)], partial) == []  # (b) move 2 was not reached in the partial round
    reordered = lsets(*[(1, k, 1, 12) for k in range(3)])  # (c) the session had it second; the plan now has it first
    assert [u["move_index"] for u in pg.unlocks([lm(rung=1)], reordered)] == [0]


def test_stepped_down_sets_are_not_work_at_the_planned_rung():
    p = {"format": "amrap", "moves": [lm(rung=1, reps=10)]}
    assert pg.session_rates(p, None, 3, 0, [], None, 60)["Incline push-up" if False else "x"] == 30
    assert pg.session_rates(p, None, 3, 0, [], None, 60, {"0:2": 0})["x"] == 20


def test_rung_put_edge_cases(c):
    _, sid = _plan_with_sessions(c)
    assert c.put(f"{API}/sessions/{sid}/rungs", json={"0:2": 1}).json() == {}  # the planned rung restores the default
    assert c.put(f"{API}/sessions/{sid}/rungs", json={"0:" + "9" * 40: 0}).status_code == 422
    assert c.put(f"{API}/sessions/{sid}/rungs", json={"1234:0": 0}).status_code == 422
