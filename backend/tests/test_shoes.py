from datetime import datetime, timedelta

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from strydr.store import migrate, models

from conftest import KEY, count
from helpers import add_run, login, recompute_now

API = "/api/v1"


def _shoe(c, name):
    r = c.post(f"{API}/shoes", json={"name": name})
    assert r.status_code == 201
    return next(x["id"] for x in r.json()["shoes"] if x["name"] == name)


def _default(c, shoe_id, from_date):
    return c.put(f"{API}/shoes/default", json={"shoe_id": shoe_id, "from_date": from_date})


def _runs(engine, *specs):
    """specs: (workout_id, 'MM-DD', type)"""
    for wid, md, typ in specs:
        add_run(engine, wid, datetime(2026, int(md[:2]), int(md[3:]), 7), 10, 3.0, type_=typ)


def _shoe_of(c, wid):
    return c.get(f"{API}/workouts/{wid}").json()["shoe"]


def _totals(c):
    return {x["name"]: (round(x["distance_m"]), x["runs"]) for x in c.get(f"{API}/shoes").json()["shoes"]}


def _setup(engine, app_client, *specs):
    _runs(engine, *specs)
    recompute_now(engine, "2026-10-26")
    login(app_client)


def test_default_covers_new_runs(engine, app_client):
    _setup(engine, app_client, ("r1", "10-20", "run"))
    a = _shoe(app_client, "A")
    _default(app_client, a, "2026-10-01")
    s = _shoe_of(app_client, "r1")
    assert (s["id"], s["source"], s["name"]) == (a, "default", "A")


def test_before_the_default_there_is_no_shoe(engine, app_client):
    _setup(engine, app_client, ("r1", "09-30", "run"))
    _default(app_client, _shoe(app_client, "A"), "2026-10-01")
    assert _shoe_of(app_client, "r1") is None


def test_default_switch_splits_totals(engine, app_client):
    _setup(engine, app_client, ("r1", "10-10", "run"), ("r2", "10-20", "run"))
    a, b = _shoe(app_client, "A"), _shoe(app_client, "B")
    _default(app_client, a, "2026-10-01")
    _default(app_client, b, "2026-10-15")
    assert _shoe_of(app_client, "r1")["id"] == a and _shoe_of(app_client, "r2")["id"] == b
    t = _totals(app_client)
    assert t["A"][1] == 1 and t["B"][1] == 1 and t["A"][0] > 0


def test_walk_has_no_default_shoe_but_can_be_given_one(engine, app_client):
    _setup(engine, app_client, ("w1", "10-20", "walk"))
    a = _shoe(app_client, "A")
    _default(app_client, a, "2026-10-01")
    assert _shoe_of(app_client, "w1") is None and _totals(app_client)["A"] == (0, 0)
    assert app_client.put(f"{API}/workouts/w1/shoe", json={"shoe_id": a}).status_code == 200
    assert _shoe_of(app_client, "w1")["source"] == "chosen" and _totals(app_client)["A"][1] == 1


def test_explicit_none_beats_the_default_and_use_default_restores_it(engine, app_client):
    _setup(engine, app_client, ("r1", "10-20", "run"))
    a = _shoe(app_client, "A")
    _default(app_client, a, "2026-10-01")
    assert app_client.put(f"{API}/workouts/r1/shoe", json={"shoe_id": None}).json()["shoe"] is None
    assert _shoe_of(app_client, "r1") is None and _totals(app_client)["A"] == (0, 0)
    r = app_client.delete(f"{API}/workouts/r1/shoe")
    assert r.status_code == 200 and r.json()["shoe"]["id"] == a and r.json()["shoe"]["source"] == "default"
    assert app_client.delete(f"{API}/workouts/r1/shoe").status_code == 200  # idempotent


def test_reparse_keeps_shoes_and_totals(engine, app_client):
    _setup(engine, app_client, ("r1", "10-20", "run"), ("r2", "10-21", "run"))
    a, b = _shoe(app_client, "A"), _shoe(app_client, "B")
    _default(app_client, a, "2026-10-01")
    app_client.put(f"{API}/workouts/r2/shoe", json={"shoe_id": b})
    before = _totals(app_client)
    recompute_now(engine, "2026-10-27")
    assert _totals(app_client) == before and _shoe_of(app_client, "r2")["id"] == b


def _home_today(engine):
    from datetime import UTC
    from zoneinfo import ZoneInfo

    from strydr.store import settings
    with Session(engine) as s:
        tz = settings.read(s, "UTC").home_tz
    return datetime.now(UTC).astimezone(ZoneInfo(tz)).date()


def test_retiring_the_default_ends_it_tomorrow_and_keeps_history(engine, app_client):
    _setup(engine, app_client, ("r1", "10-20", "run"))
    a = _shoe(app_client, "A")
    _default(app_client, a, "2026-10-01")
    r = app_client.patch(f"{API}/shoes/{a}", json={"retired": True})
    assert r.status_code == 200
    body = r.json()
    assert body["default"]["shoe_id"] == a  # still the default today
    with Session(engine) as s:
        tomorrow = (_home_today(engine) + timedelta(days=1)).isoformat()
        assert s.get(models.ShoeDefault, tomorrow).shoe_id is None
    assert body["shoes"][0]["retired"] and body["shoes"][0]["runs"] == 1
    assert _shoe_of(app_client, "r1")["id"] == a  # past runs keep A (the null row starts today, after 10-20)
    app_client.patch(f"{API}/shoes/{a}", json={"retired": False})
    assert not _shoe_of(app_client, "r1")["retired"]


def test_bad_input(engine, app_client):
    _setup(engine, app_client, ("r1", "10-20", "run"))
    a = _shoe(app_client, "A")
    app_client.patch(f"{API}/shoes/{a}", json={"retired": True})
    assert _default(app_client, a, "2026-10-01").status_code == 422
    assert _default(app_client, 999, "2026-10-01").status_code == 422
    assert _default(app_client, None, "2026-13-01").status_code == 422
    assert app_client.put(f"{API}/workouts/r1/shoe", json={"shoe_id": 999}).status_code == 422
    assert app_client.put(f"{API}/workouts/missing/shoe", json={"shoe_id": None}).status_code == 404
    assert app_client.delete(f"{API}/workouts/missing/shoe").status_code == 404
    for name in ("", "   ", "x" * 61):
        assert app_client.post(f"{API}/shoes", json={"name": name}).status_code == 422
    assert app_client.post(f"{API}/shoes", json={"name": "B"}).status_code == 201
    assert app_client.post(f"{API}/shoes", json={"name": "b"}).status_code == 422
    assert app_client.patch(f"{API}/shoes/{a}", json={"name": " B "}).status_code == 422
    assert app_client.patch(f"{API}/shoes/999", json={"name": "Z"}).status_code == 404


def test_shoe_writes_do_not_enqueue_a_recompute(engine, app_client):
    _setup(engine, app_client, ("r1", "10-20", "run"))
    before = count(engine, models.Job, models.Job.type == "recompute")
    a = _shoe(app_client, "A")
    _default(app_client, a, "2026-10-01")
    app_client.put(f"{API}/workouts/r1/shoe", json={"shoe_id": a})
    app_client.patch(f"{API}/shoes/{a}", json={"name": "A2"})
    assert count(engine, models.Job, models.Job.type == "recompute") == before


def test_no_foreign_keys_and_not_analytic():
    for t in (models.Shoe, models.ShoeDefault, models.WorkoutShoe):
        assert [f.column.table.name for f in t.__table__.foreign_keys] == []
        assert t not in models.ANALYTIC


def test_endpoints_need_login(app_client):
    assert app_client.get(f"{API}/shoes").status_code == 401
    assert app_client.post(f"{API}/shoes", json={"name": "A"}).status_code == 401
    assert app_client.patch(f"{API}/shoes/1", json={"retired": True}).status_code == 401
    assert app_client.put(f"{API}/shoes/default", json={"shoe_id": None, "from_date": "2026-10-01"}).status_code == 401
    assert app_client.put(f"{API}/workouts/r1/shoe", json={"shoe_id": None}).status_code == 401
    assert app_client.delete(f"{API}/workouts/r1/shoe").status_code == 401


def test_migration_0010_upgrades_a_0009_database(tmp_path):
    from strydr.store.engine import make_engine
    e = make_engine(tmp_path / "m.db", KEY)
    cfg = Config()
    cfg.set_main_option("script_location", str(migrate._DIR))
    with e.begin() as c:
        cfg.attributes["connection"] = c
        command.upgrade(cfg, "0009")
    assert "shoe" not in inspect(e).get_table_names()
    with e.begin() as c:
        cfg.attributes["connection"] = c
        command.upgrade(cfg, "head")
        c.execute(text("INSERT INTO shoe (name, retired, created_at) VALUES ('A', 0, '2026-01-01')"))
    assert {"shoe", "shoe_default", "workout_shoe"} <= set(inspect(e).get_table_names())
    e.dispose()


def test_reparse_of_real_payloads_keeps_shoes_and_totals(engine, send, app_client):
    from strydr.jobs import reparse

    from conftest import load_fixture, workouts
    send(load_fixture("hae-export.json"))
    recompute_now(engine, "2026-10-26")
    login(app_client)
    ws = workouts(engine)
    runs = sorted((w for w in ws.values() if w.type == "run"), key=lambda w: w.local_date)
    assert len(runs) >= 1
    a, b = _shoe(app_client, "A"), _shoe(app_client, "B")
    _default(app_client, a, "2000-01-01")
    assert app_client.put(f"{API}/workouts/{runs[-1].workout_id}/shoe", json={"shoe_id": b}).status_code == 200
    before_totals = _totals(app_client)
    before_shoes = {wid: _shoe_of(app_client, wid) for wid in ws}
    assert before_totals["A"][1] + before_totals["B"][1] == len(runs)
    assert reparse.reparse(engine) >= 1
    assert set(workouts(engine)) == set(ws)  # rows were deleted and rebuilt
    recompute_now(engine, "2026-10-27")
    assert _totals(app_client) == before_totals
    assert {wid: _shoe_of(app_client, wid) for wid in ws} == before_shoes


def test_retiring_the_default_keeps_a_run_from_today(engine, app_client):
    today = _home_today(engine)
    add_run(engine, "t1", datetime(today.year, today.month, today.day, 0, 5), 10, 3.0)
    recompute_now(engine, today.isoformat())
    login(app_client)
    a = _shoe(app_client, "A")
    _default(app_client, a, today.isoformat())
    app_client.patch(f"{API}/shoes/{a}", json={"retired": True})
    assert _shoe_of(app_client, "t1")["id"] == a


def test_retiring_clears_future_defaults_for_that_shoe(engine, app_client):
    login(app_client)
    a, b = _shoe(app_client, "A"), _shoe(app_client, "B")
    future = (_home_today(engine) + timedelta(days=30)).isoformat()
    _default(app_client, a, future)
    app_client.patch(f"{API}/shoes/{a}", json={"retired": True})
    with Session(engine) as s:
        assert s.get(models.ShoeDefault, future).shoe_id is None
    assert b  # unrelated shoe untouched


def test_case_only_rename_and_unicode_duplicates(engine, app_client):
    login(app_client)
    a = _shoe(app_client, "A")
    assert app_client.patch(f"{API}/shoes/{a}", json={"name": "a"}).status_code == 200
    assert app_client.post(f"{API}/shoes", json={"name": "Éclair"}).status_code == 201
    assert app_client.post(f"{API}/shoes", json={"name": "éclair"}).status_code == 422
    assert app_client.post(f"{API}/shoes", json={"name": "Éclair"}).status_code == 422


def test_padded_names_are_stripped_before_the_length_check(engine, app_client):
    login(app_client)
    r = app_client.post(f"{API}/shoes", json={"name": "  " + "x" * 60 + "  "})
    assert r.status_code == 201 and r.json()["shoes"][0]["name"] == "x" * 60


def test_detail_reports_whether_the_shoe_is_chosen(engine, app_client):
    _setup(engine, app_client, ("r1", "10-20", "run"))
    detail = lambda: app_client.get(f"{API}/workouts/r1").json()  # noqa: E731
    assert detail()["shoe_chosen"] is False
    r = app_client.put(f"{API}/workouts/r1/shoe", json={"shoe_id": None})
    assert r.json() == {"shoe": None, "chosen": True} and detail()["shoe_chosen"] is True
    assert app_client.delete(f"{API}/workouts/r1/shoe").json() == {"shoe": None, "chosen": False}
