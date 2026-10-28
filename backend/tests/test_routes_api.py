"""Routes, section comparisons, the same-route insight (FR-23a) and overrides, through the real recompute."""
from datetime import datetime

import pytest

from helpers import add_run, login, recompute_now

AS_OF = "2026-10-26"
PAST = [("p1", 10), ("p2", 13), ("p3", 16), ("p4", 19)]


def _seed(engine, current_minutes=28, current_hr=150.0):
    for wid, day in PAST:
        add_run(engine, wid, datetime(2026, 10, day, 7), 30, 3.0, hr=150.0)  # 5.4 km, 333 s per km
    add_run(engine, "cur", datetime(2026, 10, 24, 7), current_minutes, 5400 / (current_minutes * 60), hr=current_hr)
    recompute_now(engine, AS_OF)


def test_repeat_runs_cluster_and_the_same_hr_insight_fires(engine, app_client):
    _seed(engine)
    login(app_client)
    routes = app_client.get("/api/v1/routes").json()
    assert len(routes) == 1 and routes[0]["run_count"] == 5 and routes[0]["route_key"] == "p1"
    detail = app_client.get("/api/v1/routes/p1").json()
    assert {r["workout_id"] for r in detail["runs"]} == {"p1", "p2", "p3", "p4", "cur"}
    assert [s["kind"] for s in detail["sections"]].count("s") == 5 and detail["display_geometry"]
    fired = [x for x in detail["results"] if x["fires"]]
    assert fired and {x["workout_id"] for x in fired} == {"cur"} and len(fired) <= 2  # at most 2 per run
    assert all(x["direction"] == "faster" and x["n"] >= 3 and x["gap_s"] < -15 for x in fired)

    items = app_client.get("/api/v1/insights", params={"run": "cur", "rule_id": "same-route-hr"}).json()["items"]
    assert len(items) == 1
    fact = items[0]
    assert fact["insight_key"] == f"same-route-hr:run/cur:2026-10-24" and "faster" in fact["text"] and "150 bpm" in fact["text"]
    why = app_client.get(f"/api/v1/insights/{fact['insight_key']}").json()
    assert why["reasoning"]["data"]["runs"] >= 3 and why["reasoning"]["data"]["sections"]


def test_no_claim_when_the_heart_rate_differs(engine, app_client):
    _seed(engine, current_hr=165.0)  # more than 4 bpm from every earlier run: nothing is comparable
    login(app_client)
    assert not app_client.get("/api/v1/insights", params={"rule_id": "same-route-hr"}).json()["items"]


def test_split_override_survives_a_recompute_and_separates_the_runs(engine, app_client, worker):
    _seed(engine)
    login(app_client)
    r = app_client.post("/api/v1/routes/overrides", json={"workout_a": "p2", "workout_b": "p1", "action": "split"})
    assert r.status_code == 201 and (r.json()["workout_a"], r.json()["workout_b"]) == ("p1", "p2")  # unordered pair, stored sorted
    worker.run_all()
    recompute_now(engine, AS_OF)
    for route in app_client.get("/api/v1/routes").json():
        members = {x["workout_id"] for x in app_client.get(f"/api/v1/routes/{route['route_key']}").json()["runs"]}
        assert not {"p1", "p2"} <= members
    assert len(app_client.get("/api/v1/routes/overrides").json()) == 1
    assert app_client.post("/api/v1/routes/overrides", json={"workout_a": "p1", "workout_b": "nope", "action": "join"}).status_code == 404
    assert app_client.post("/api/v1/routes/overrides", json={"workout_a": "p1", "workout_b": "p1", "action": "join"}).status_code == 422
    assert app_client.delete("/api/v1/routes/overrides", params={"workout_a": "p1", "workout_b": "p2"}).status_code == 204


def test_unknown_route_is_404(engine, app_client):
    _seed(engine)
    login(app_client)
    assert app_client.get("/api/v1/routes/nope").status_code == 404


@pytest.mark.parametrize("path", ["/api/v1/routes", "/api/v1/insights", "/api/v1/weeks", "/api/v1/load", "/api/v1/privacy-zones",
                                  "/api/v1/settings/ai", "/api/v1/settings/thresholds"])
def test_endpoints_need_a_session(app_client, path):
    assert app_client.get(path).status_code == 401
