import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from strydr.store import migrate, models

from conftest import KEY, count
from helpers import login

API = "/api/v1"


def mv(name="Swing", **kw):
    d = {"name": name, "reps": 10, "seconds": None, "weight_kg": 16.0}
    d.update(kw)
    return d


def plan(name="Swing circuit", fmt="amrap", **kw):
    d = {"name": name, "format": fmt, "cap_min": 20 if fmt == "amrap" else None,
         "emom_min": 12 if fmt == "emom" else None, "rounds": 4 if fmt == "complex" else None,
         "moves": [mv()], "video_url": None}
    d.update(kw)
    return d


@pytest.fixture
def c(app_client):
    login(app_client)
    return app_client


def test_create_amrap_reopens_intact(c):
    moves = [mv(f"Move {i}", weight_kg=11.34) for i in range(5)]
    r = c.post(f"{API}/plans", json=plan(moves=moves, video_url="https://example.com/v"))
    assert r.status_code == 201
    got = c.get(f"{API}/plans/{r.json()['id']}").json()
    assert got["name"] == "Swing circuit" and got["format"] == "amrap" and got["cap_min"] == 20
    assert got["moves"] == moves and got["video_url"] == "https://example.com/v"
    assert [p["id"] for p in c.get(f"{API}/plans").json()] == [got["id"]]


def test_emom_and_complex(c):
    e = c.post(f"{API}/plans", json=plan("E", "emom", moves=[mv("A"), mv("B"), mv("C")])).json()
    assert e["emom_min"] == 12 and e["cap_min"] is None and len(e["moves"]) == 3
    k = c.post(f"{API}/plans", json=plan("K", "complex", moves=[mv("A"), mv("B", reps=None, seconds=30)])).json()
    assert k["rounds"] == 4 and k["moves"][1]["seconds"] == 30 and k["moves"][1]["reps"] is None


def test_bodyweight_move_and_other_format_settings_dropped(c):
    r = c.post(f"{API}/plans", json=plan(moves=[mv("Pushups", weight_kg=None)], rounds=9))
    assert r.status_code == 201 and r.json()["moves"][0]["weight_kg"] is None and r.json()["rounds"] is None


@pytest.mark.parametrize("move", [
    mv(reps=10, seconds=30), mv(reps=None, seconds=None), mv(reps=0), mv(reps=501), mv(reps=None, seconds=4),
    mv(reps=None, seconds=601), mv(weight_kg=0.4), mv(weight_kg=100.1), mv(name=""), mv(name="x" * 41)])
def test_bad_moves_rejected(c, move):
    assert c.post(f"{API}/plans", json=plan(moves=[move])).status_code == 422


@pytest.mark.parametrize("body", [
    plan(cap_min=0), plan(cap_min=91), plan(cap_min=None), plan("E", "emom", emom_min=91), plan("K", "complex", rounds=51),
    plan("K", "complex", rounds=None), plan(moves=[]), plan(moves=[mv()] * 13), plan(name=""), plan(name="x" * 61),
    plan(video_url="ftp://x.com/v"), plan(video_url="javascript:alert(1)"), plan(video_url="https://")])
def test_bad_plans_rejected(c, body):
    assert c.post(f"{API}/plans", json=body).status_code == 422


def test_limits_accepted(c):
    ok = plan(moves=[mv(weight_kg=0.5), mv(weight_kg=100, reps=500)] * 6, cap_min=90)
    assert c.post(f"{API}/plans", json=ok).status_code == 201


def test_duplicate_name_rejected_any_case_and_on_edit(c):
    a = c.post(f"{API}/plans", json=plan("Swing circuit")).json()
    r = c.post(f"{API}/plans", json=plan("SWING CIRCUIT"))
    assert r.status_code == 422 and "name" in r.json()["detail"]
    b = c.post(f"{API}/plans", json=plan("Other")).json()
    assert c.put(f"{API}/plans/{b['id']}", json=plan("swing circuit")).status_code == 422
    assert c.put(f"{API}/plans/{a['id']}", json=plan("Swing Circuit", cap_min=25)).json()["cap_min"] == 25


def test_edit_changes_format_and_404s(c):
    a = c.post(f"{API}/plans", json=plan()).json()
    r = c.put(f"{API}/plans/{a['id']}", json=plan("Swing circuit", "complex"))
    assert r.json()["format"] == "complex" and r.json()["cap_min"] is None and r.json()["rounds"] == 4
    assert c.put(f"{API}/plans/999", json=plan()).status_code == 404
    assert c.get(f"{API}/plans/999").status_code == 404
    assert c.delete(f"{API}/plans/999").status_code == 404
    assert c.post(f"{API}/plans/999/duplicate").status_code == 404


def test_duplicate_makes_a_copy_then_numbers_it(c):
    a = c.post(f"{API}/plans", json=plan(moves=[mv("A"), mv("B", weight_kg=None)])).json()
    d1 = c.post(f"{API}/plans/{a['id']}/duplicate")
    assert d1.status_code == 201 and d1.json()["name"] == "Swing circuit (copy)"
    assert d1.json()["id"] != a["id"] and d1.json()["moves"] == a["moves"]
    assert c.post(f"{API}/plans/{a['id']}/duplicate").json()["name"] == "Swing circuit (copy 2)"
    long = c.post(f"{API}/plans", json=plan("x" * 60)).json()
    assert len(c.post(f"{API}/plans/{long['id']}/duplicate").json()["name"]) <= 60


def test_duplicate_names_stay_within_60_characters(c):
    long = c.post(f"{API}/plans", json=plan("x" * 60)).json()
    names = [c.post(f"{API}/plans/{long['id']}/duplicate").json()["name"] for _ in range(10)]
    assert all(len(n) <= 60 for n in names) and len(set(names)) == 10
    assert names[1].endswith(" (copy 2)") and names[9].endswith(" (copy 10)")


def test_delete(c):
    a = c.post(f"{API}/plans", json=plan()).json()
    assert c.delete(f"{API}/plans/{a['id']}").status_code == 204
    assert c.get(f"{API}/plans").json() == []


def test_plan_writes_do_not_enqueue_a_recompute(engine, c):
    before = count(engine, models.Job, models.Job.type == "recompute")
    a = c.post(f"{API}/plans", json=plan()).json()
    c.put(f"{API}/plans/{a['id']}", json=plan(cap_min=30))
    d = c.post(f"{API}/plans/{a['id']}/duplicate").json()
    c.delete(f"{API}/plans/{d['id']}")
    c.delete(f"{API}/plans/{a['id']}")
    assert count(engine, models.Job, models.Job.type == "recompute") == before


def test_needs_login(app_client):
    assert app_client.get(f"{API}/plans").status_code == 401
    assert app_client.post(f"{API}/plans", json=plan()).status_code == 401
    assert app_client.delete(f"{API}/plans/1").status_code == 401


def test_migration_0014_up_and_down(tmp_path):
    from strydr.store.engine import make_engine
    e = make_engine(tmp_path / "m.db", KEY)
    cfg = Config()
    cfg.set_main_option("script_location", str(migrate._DIR))
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.upgrade(cfg, "0013")
    assert "workout_plan" not in inspect(e).get_table_names()
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.upgrade(cfg, "head")
        cn.execute(text("INSERT INTO workout_plan (name, format, moves, created_at, updated_at) "
                        "VALUES ('A', 'amrap', '[]', '2026-01-01', '2026-01-01')"))
    assert "workout_plan" in inspect(e).get_table_names()
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.downgrade(cfg, "0013")
    assert "workout_plan" not in inspect(e).get_table_names()
    e.dispose()
