"""End to end on synthetic data only: ingest the fixture export, drain the jobs, read everything through the API."""
import importlib.util
import json
import math
import sys
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.jobs import queue
from strydr.store import models

from conftest import FIXTURES
from helpers import login

AS_OF = "2026-03-10"
ZONE = {"lat": 52.3700, "lon": 4.8900, "radius_m": 400.0}  # the fixture route's start: a test "home"


def _generator():
    spec = importlib.util.spec_from_file_location("hae_gen", FIXTURES / "generate_hae_export.py")
    mod = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # no __pycache__ in fixtures/
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


def history_payload() -> dict:
    """Ten weeks of synthetic runs before the fixture's own (no GPS, so the file stays small)."""
    g = _generator()
    runs = []
    for i in range(30):
        day = datetime(2026, 1, 1, 7, 0, tzinfo=g.TZ) + timedelta(days=2 * i)
        runs.append(g.workout(f"hist-{i}", "Outdoor Run", "running", 37, day, 40 + (i % 4) * 5, 3.0 + (i % 3) * 0.1,
                              with_route=False, seed=100 + i, base_hr=150 + i % 5))
    return g.export(runs, with_metrics=False)


def drain(worker, engine, as_of=AS_OF):
    worker.run_all()
    with Session(engine) as s:  # recomputes enqueued by jobs use the real clock; pin the generation to the fixture's time
        queue.enqueue_recompute(s, as_of)
        s.commit()
    worker.run_all()


@pytest.fixture
def seeded(engine, ingest, worker, app_client):
    for body in (json.loads((FIXTURES / "hae-export.json").read_text()), history_payload()):
        assert ingest.post("/ingest/hae", content=json.dumps(body).encode()).status_code == 202
    drain(worker, engine)
    login(app_client)
    return app_client


def _walk(node):
    yield node
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _metres(a, b):
    return math.hypot((a[0] - b[0]) * 111_320, (a[1] - b[1]) * 111_320 * math.cos(math.radians(b[0])))


def test_the_whole_pipeline_serves_every_screen(seeded, engine):
    c = seeded
    ws = c.get("/api/v1/workouts?type=run&limit=200").json()
    assert len(ws) >= 31
    assert any(w["has_route"] for w in ws)

    dash = c.get("/api/v1/dashboard?weeks=12").json()
    assert dash["as_of"] == AS_OF and any(w["run_count"] for w in dash["weeks"])

    load = c.get("/api/v1/load?days=90").json()
    assert load["series"] and load["series"][-1]["local_date"] == AS_OF
    assert set(load["series"][-1]) >= {"fitness", "fatigue", "form_pct", "tooltip"}
    assert "risk" not in json.dumps(load).lower()

    feed = c.get("/api/v1/insights").json()
    assert feed["items"] and all(i["text"] for i in feed["items"]) and feed["disclaimer"]
    assert [i["local_date"] for i in feed["items"]] == sorted((i["local_date"] for i in feed["items"]), reverse=True)
    first = feed["items"][0]
    detail = c.get(f"/api/v1/insights/{first['insight_key']}").json()
    assert detail["reasoning"]["rule"] == first["rule_id"] and detail["reasoning"]["note"]

    weeks = c.get("/api/v1/weeks?from=2026-W02&to=2026-W10").json()
    assert weeks[0]["week_id"] == "2026-W10" and sum(w["run_count"] for w in weeks) > 20
    wk = c.get("/api/v1/weeks/2026-W10").json()
    assert wk["days"] and len(wk["days"]) == 7
    assert wk["load"]["total"] == pytest.approx(sum(d["load"] for d in wk["days"]))
    dash_week = next(w for w in dash["weeks"] if w["week_id"] == "2026-W10")
    assert dash_week["distance_m"] == pytest.approx(wk["distance_m"])  # the dashboard and week view agree


def test_feedback_and_week_note_survive_settings_change_and_recompute(seeded, engine, worker):
    c = seeded
    key = c.get("/api/v1/insights").json()["items"][0]["insight_key"]
    r = c.put(f"/api/v1/insights/{key}/feedback", json={"thumb": "up"})
    assert r.status_code == 200 and r.json()["snapshot"]["evidence"]
    assert c.put("/api/v1/weeks/2026-W10/note", json={"text": "easy week"}).status_code == 200
    run = c.get("/api/v1/workouts?type=run&limit=1").json()[0]["workout_id"]
    assert c.put(f"/api/v1/workouts/{run}/note", json={"text": "legs heavy", "rpe": 6}).status_code == 200

    profile = c.get("/api/v1/profile").json()["settings"]
    profile["units"] = "imperial"
    assert c.put("/api/v1/profile", json=profile).json()["recompute_pending"]  # AD-5: enqueued with the write
    drain(worker, engine)

    items = {i["insight_key"]: i for i in c.get("/api/v1/insights").json()["items"]}
    assert items[key]["thumb"] == "up"
    assert c.get("/api/v1/weeks/2026-W10").json()["note"]["text"] == "easy week"
    note = c.get(f"/api/v1/workouts/{run}").json()["note"]
    assert (note["text"], note["rpe"]) == ("legs heavy", 6)
    assert any(" mi" in i["text"] for i in items.values())  # server-rendered text follows the runner's units


def test_every_closed_list_input_enqueues_a_recompute(seeded, engine, worker):
    c = seeded
    workouts = [w["workout_id"] for w in c.get("/api/v1/workouts?type=run&limit=2").json()]

    def pending() -> int:
        with Session(engine) as s:
            return len(s.execute(select(models.Job).where(models.Job.type == "recompute", models.Job.status == "pending")).all())

    zone = None
    for write in (
        lambda: c.put("/api/v1/profile", json={**c.get("/api/v1/profile").json()["settings"], "hrmax_override": 190}),
        lambda: c.put("/api/v1/settings/thresholds", json={"overrides": {"no-rest-day": {"min_days": 7}}}),
        lambda: c.put(f"/api/v1/workouts/{workouts[0]}/note", json={"rpe": 4}),
        lambda: c.post("/api/v1/routes/overrides", json={"workout_a": workouts[0], "workout_b": workouts[1], "action": "split"}),
        lambda: c.post("/api/v1/privacy-zones", json=ZONE),
    ):
        worker.run_all()
        assert pending() == 0
        assert write().status_code in (200, 201)
        assert pending() == 1
    zone = c.get("/api/v1/privacy-zones").json()[0]["id"]
    worker.run_all()
    assert c.delete(f"/api/v1/privacy-zones/{zone}").status_code == 204
    assert pending() == 1


def test_threshold_overrides_validate_and_apply(seeded, engine, worker):
    c = seeded
    assert c.put("/api/v1/settings/thresholds", json={"overrides": {"nope": {"x": 1}}}).status_code == 422
    assert c.put("/api/v1/settings/thresholds", json={"overrides": {"no-rest-day": {"typo": 1}}}).status_code == 422
    out = c.put("/api/v1/settings/thresholds", json={"overrides": {"no-rest-day": {"enabled": False}}}).json()
    assert out["overrides"] == {"no-rest-day": {"enabled": False}} and out["defaults"]["no-rest-day"]["enabled"] is True
    drain(worker, engine)
    assert not [i for i in c.get("/api/v1/insights?limit=200").json()["items"] if i["rule_id"] == "no-rest-day"]


def test_no_api_response_contains_a_coordinate_inside_a_privacy_zone(seeded, engine, worker):
    c = seeded
    assert c.post("/api/v1/privacy-zones", json=ZONE).status_code == 201
    assert c.get("/api/v1/privacy-zones").json()[0].keys() == {"id", "radius_m"}  # the centre is never echoed
    drain(worker, engine)
    spec = c.get("/openapi.json")  # no schema route on the app port: only the generated one in tests below
    assert spec.status_code in (200, 404)

    paths = ["/api/v1/workouts?limit=200", "/api/v1/dashboard", "/api/v1/records", "/api/v1/profile", "/api/v1/sync-status",
             "/api/v1/insights?limit=200", "/api/v1/weeks", "/api/v1/weeks/2026-W10", "/api/v1/recap/2026", "/api/v1/load", "/api/v1/routes",
             "/api/v1/routes/overrides", "/api/v1/privacy-zones", "/api/v1/settings/ai", "/api/v1/settings/thresholds"]
    for w in c.get("/api/v1/workouts?limit=200").json():
        paths.append(f"/api/v1/workouts/{w['workout_id']}")
    for r in c.get("/api/v1/routes").json():
        paths.append(f"/api/v1/routes/{r['route_key']}")
    centre = (ZONE["lat"], ZONE["lon"])
    seen_geometry = 0
    for path in paths:
        r = c.get(path)
        assert r.status_code == 200, path
        body = r.json()
        for node in _walk(body):
            if isinstance(node, list) and len(node) == 2 and all(isinstance(x, float) for x in node):
                seen_geometry += 1
                assert _metres(node, centre) > ZONE["radius_m"], path
            if isinstance(node, dict):
                assert not {"lat", "lon", "latitude", "longitude"} & node.keys(), path
    assert seen_geometry > 0  # the clipped track really was served and checked


def test_health_is_public_and_leaks_nothing(engine):
    from fastapi.testclient import TestClient
    from strydr.api import create_app
    r = TestClient(create_app(engine)).get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
