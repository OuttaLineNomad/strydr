"""Run conditions, grade adjusted pace, the calendar and the route map. All data is invented."""
from datetime import date, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from helpers import add_run, login, recompute_now
from strydr.pipeline.derive import conditions, grade
from strydr.store import models


# ---- derive/conditions ----

def test_dew_point_matches_published_values():
    assert conditions.dew_point_c(20.0, 50.0) == pytest.approx(9.3, abs=0.2)
    assert conditions.dew_point_c(30.0, 70.0) == pytest.approx(23.9, abs=0.2)
    assert conditions.dew_point_c(10.0, 0.0) is None


def test_heat_adjustment_follows_the_temp_plus_dew_point_rule():
    assert conditions.heat_adjust_pct(95) == 0.0
    assert conditions.heat_adjust_pct(125) == pytest.approx(1.5)
    assert conditions.heat_adjust_pct(175) == pytest.approx(9.0)
    assert conditions.heat_adjust_pct(220) == 10.0  # capped


def test_apple_reading_wins_and_fetched_weather_fills_the_rest():
    c = conditions.conditions(28.0, 70.0, {"temp_c": 20.0, "wind_ms": 7.0, "precip_mm_h": 1.0}, 3.0)
    assert c["temp_c"] == 28.0 and c["sources"] == {"temperature": "apple", "humidity": "apple", "wind": "open-meteo"}
    assert c["band"] in ("hot", "oppressive") and c["windy"] and c["rain"]
    assert c["heat_adjusted_speed_mps"] > 3.0
    filled = conditions.conditions(None, None, {"temp_c": 5.0, "humidity_pct": 80.0}, 3.0)
    assert filled["band"] == "cold" and filled["sources"]["temperature"] == "open-meteo"
    assert conditions.conditions(None, None, None, 3.0) is None


# ---- derive/grade ----

def _hill(n=1000, climb=0.05):
    """1 km out at +5% then 1 km back down: 1 m spacing."""
    dist = [float(i) for i in range(2 * n + 1)]
    alt = [climb * d if d <= n else climb * (2 * n - d) for d in dist]
    return dist, alt


def test_minetti_cost_ratio_is_one_on_the_flat_and_clamped():
    assert grade.cost_ratio(0.0) == 1.0
    assert grade.cost_ratio(0.05) > 1.2 and grade.cost_ratio(-0.05) < 1.0
    assert grade.cost_ratio(0.5) == grade.cost_ratio(grade.GRADE_MAX)


def test_uphill_splits_get_a_faster_gap_and_flat_splits_none():
    dist, alt = _hill()
    splits = [{"distance_m": 1000.0, "duration_s": 400.0, "speed_mps": 2.5}, {"distance_m": 1000.0, "duration_s": 330.0, "speed_mps": 1000 / 330}]
    grade.add_to_splits(splits, dist, alt)
    assert splits[0]["gap_speed_mps"] > 1000 / 400 and splits[1]["gap_speed_mps"] < 1000 / 330
    flat = [{"distance_m": 1000.0, "duration_s": 400.0, "speed_mps": 2.5}]
    grade.add_to_splits(flat, [float(i) for i in range(1001)], [10.0 + (i % 3) * 0.5 for i in range(1001)])
    assert flat[0]["gap_speed_mps"] is None  # 1-3 m of altitude noise is not a hill
    g = grade.run_gap(dist, alt, 2000 / 730)
    assert g["hilly"] and g["relief_m"] == pytest.approx(100, abs=10)  # smoothing and hysteresis round the summit
    assert grade.run_gap(dist, [None] * len(dist), 2000 / 730) is None


def test_altitude_noise_on_flat_ground_is_not_a_hill():
    """A flat 3.2 km run with 2 m of barometric jitter: no hilly flag and almost no adjustment."""
    import random
    rnd = random.Random(7)
    dist = [float(i) for i in range(3201)]
    alt = [20.0 + rnd.gauss(0, 1.0) + (1.5 if (i // 400) % 2 else 0.0) for i in range(3201)]
    g = grade.run_gap(dist, alt, 1.8)
    assert not g["hilly"] and abs(g["gap_speed_mps"] / 1.8 - 1) < 0.01


def test_gap_scales_the_watch_speed_so_gps_length_errors_cancel():
    dist, alt = _hill()
    long_gps = [d * 1.1 for d in dist]  # the track reads 10% long against the watch
    a, b = grade.run_gap(dist, alt, 2.0), grade.run_gap(long_gps, alt, 2.0)
    assert b["gap_speed_mps"] / 2.0 < a["gap_speed_mps"] / 2.0 + 0.02  # same terrain, about the same ratio


# ---- through the recompute and the API ----

def _seed(engine):
    add_run(engine, "a", datetime(2026, 10, 3, 7), 30)
    add_run(engine, "b", datetime(2026, 10, 20, 7), 20, type_="walk")
    add_run(engine, "c", datetime(2026, 9, 28, 7), 25)
    add_run(engine, "indoor", datetime(2026, 10, 5, 7), 20, route=False)  # no track: stored as JSON null
    with Session(engine) as s:
        s.execute(update(models.Workout).where(models.Workout.workout_id == "a").values(temperature_c=27.0, humidity_pct=75.0))
        s.commit()
    recompute_now(engine, "2026-10-26")


def test_run_detail_carries_conditions_and_gap(engine, app_client):
    _seed(engine)
    login(app_client)
    d = app_client.get("/api/v1/workouts/a").json()
    assert d["conditions"]["band"] == "oppressive" and d["conditions"]["sources"]["temperature"] == "apple"
    assert d["conditions"]["dew_point_c"] == pytest.approx(22.2, abs=0.3)
    assert "gap_speed_mps" in d["splits_km"][0]
    assert app_client.get("/api/v1/workouts/c").json()["conditions"] is None  # no reading, weather off


def test_calendar_month_is_whole_weeks_with_totals(engine, app_client):
    _seed(engine)
    login(app_client)
    c = app_client.get("/api/v1/calendar", params={"month": "2026-10"}).json()
    assert c["month"] == "2026-10" and len(c["days"]) % 7 == 0
    assert date.fromisoformat(c["days"][0]["local_date"]).weekday() == 0
    oct3 = next(d for d in c["days"] if d["local_date"] == "2026-10-03")
    assert oct3["workouts"][0]["workout_id"] == "a" and oct3["in_month"]
    sep28 = next(d for d in c["days"] if d["local_date"] == "2026-09-28")
    assert not sep28["in_month"] and sep28["workouts"]
    assert c["totals"]["run_count"] == 2 and c["previous"]["run_count"] == 1 and c["active_days"] == 3
    assert app_client.get("/api/v1/calendar", params={"month": "2026-13"}).status_code == 422


def test_route_map_serves_every_clipped_track(engine, app_client):
    _seed(engine)
    login(app_client)
    m = app_client.get("/api/v1/routes/map").json()
    assert {x["workout_id"] for x in m["lines"]} == {"a", "b", "c"}
    assert {x["type"] for x in m["lines"]} == {"run", "walk"}
    assert set(m["lines"][0]["display_geometry"]) == {"segments", "start", "end", "bounds"}
