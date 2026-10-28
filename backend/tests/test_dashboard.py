from collections import defaultdict
from datetime import date, datetime

import pytest

from helpers import add_run, login, recompute_now

AS_OF = "2026-10-26"  # a Monday: ISO week 2026-W44


def _seed(engine):
    add_run(engine, "w42a", datetime(2026, 10, 12, 7), 30, 3.0)
    add_run(engine, "w42b", datetime(2026, 10, 15, 7), 45, 3.1)
    add_run(engine, "w43", datetime(2026, 10, 20, 7), 40, 3.4, speed_fn=lambda i: 4.2 if i < 700 else 3.2)
    add_run(engine, "w44", datetime(2026, 10, 26, 7), 35, 3.0)
    add_run(engine, "walk", datetime(2026, 10, 21, 7), 60, 1.4, type_="walk")  # never counts toward running volume
    recompute_now(engine, AS_OF)


def test_week_totals_equal_the_sum_of_that_weeks_runs(engine, app_client):
    _seed(engine)
    login(app_client)
    runs = app_client.get("/api/v1/workouts", params={"type": "run"}).json()
    expect = defaultdict(lambda: [0.0, 0.0, 0])
    for r in runs:
        wk = date.fromisoformat(r["local_date"]).strftime("%G-W%V")
        expect[wk][0] += r["distance_m"]
        expect[wk][1] += r["duration_s"]
        expect[wk][2] += 1
    d = app_client.get("/api/v1/dashboard", params={"weeks": 6}).json()
    assert d["as_of"] == AS_OF
    assert [w["week_id"] for w in d["weeks"]] == ["2026-W39", "2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44"]
    for w in d["weeks"]:
        dist, dur, n = expect.get(w["week_id"], [0.0, 0.0, 0])
        assert (w["distance_m"], w["duration_s"], w["run_count"]) == (pytest.approx(dist), pytest.approx(dur), n)
    assert d["weeks"][0]["distance_m"] == 0 and d["weeks"][3]["run_count"] == 2
    assert sum(w["run_count"] for w in d["weeks"]) == 4  # the walk is excluded


def test_range_is_selectable(engine, app_client):
    _seed(engine)
    login(app_client)
    assert len(app_client.get("/api/v1/dashboard", params={"weeks": 2}).json()["weeks"]) == 2
    assert app_client.get("/api/v1/dashboard", params={"weeks": 0}).status_code == 422


def test_latest_vs_pr_tiles(engine, app_client):
    _seed(engine)
    login(app_client)
    d = app_client.get("/api/v1/dashboard").json()
    mile, avg = d["one_mile_pace"], d["avg_pace"]
    assert mile["pr_workout_id"] == "w43" and mile["pr_speed_mps"] == pytest.approx(4.2, rel=0.01)
    assert mile["latest_workout_id"] == "w44" and mile["latest_speed_mps"] == pytest.approx(3.0, rel=0.01)
    assert avg["latest_workout_id"] == "w44" and avg["pr_workout_id"] == "w43"


def test_records_endpoint_hides_dashboard_helper_rows(engine, app_client):
    _seed(engine)
    login(app_client)
    keys = {r["key"] for r in app_client.get("/api/v1/records").json()}
    assert {"best_1km", "best_1mi", "best_5km", "longest_run", "record_week", "record_month", "best_avg_pace"} <= keys
    assert not any(k.startswith("latest_") for k in keys)


def test_empty_state_before_first_generation(app_client):
    login(app_client)
    d = app_client.get("/api/v1/dashboard").json()
    assert d["as_of"] is None and d["weeks"] == [] and d["one_mile_pace"]["pr_speed_mps"] is None
    assert app_client.get("/api/v1/records").json() == []
    assert app_client.get("/api/v1/profile").json()["resolved"] is None


def test_workout_detail_series_and_splits(engine, app_client):
    _seed(engine)
    login(app_client)
    d = app_client.get("/api/v1/workouts/w43").json()
    assert d["workout"]["type"] == "run" and d["workout"]["has_route"] and d["workout"]["is_long_run"] is False
    km = d["splits_km"]
    assert [s["index"] for s in km][:3] == [0, 1, 2] and km[0]["distance_m"] == pytest.approx(1000, abs=1)
    assert km[0]["speed_mps"] == pytest.approx(4.2, rel=0.01) and km[-1]["partial"] is True
    assert km[0]["avg_hr"] == pytest.approx(150) and km[0]["elevation_change_m"] is not None
    assert d["splits_mi"][0]["distance_m"] == pytest.approx(1609.344, abs=1)
    assert len(d["hr_series"]) == 40 and d["hr_series"][0]["avg"] == 150
    assert d["pace_series"] and d["elevation_series"] and d["display_geometry"]["segments"]
    assert d["zone_seconds"] is None or len(d["zone_seconds"]) == 5
    assert app_client.get("/api/v1/workouts/nope").status_code == 404


def test_missing_data_is_null_not_zero(engine, app_client):
    add_run(engine, "tm", datetime(2026, 10, 20, 7), 30, 3.0, route=False, hr=None)
    recompute_now(engine, AS_OF)
    login(app_client)
    d = app_client.get("/api/v1/workouts/tm").json()
    assert d["splits_km"] is None and d["hr_series"] is None and d["display_geometry"] is None
    assert d["pace_series"] is None and d["elevation_series"] is None and d["zone_seconds"] is None
    assert d["workout"]["has_hr"] is False and d["workout"]["has_route"] is False
