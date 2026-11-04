"""Monthly and yearly recap. All data is invented."""
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from helpers import add_run, login, recompute_now
from strydr.jobs import queue
from strydr.store import models

FAR = (40.0, -3.0)


def _seed(engine):
    add_run(engine, "aug1", datetime(2026, 8, 5, 7), 30)
    add_run(engine, "aug2", datetime(2026, 8, 31, 7), 30, origin=FAR)  # Monday: its week belongs to August
    add_run(engine, "sep1", datetime(2026, 9, 1, 7), 40)
    add_run(engine, "sep2", datetime(2026, 9, 8, 7), 20)
    add_run(engine, "sep3", datetime(2026, 9, 9, 7), 20)
    add_run(engine, "sep4", datetime(2026, 9, 10, 7), 20, origin=FAR)
    add_run(engine, "sep5", datetime(2026, 9, 15, 7), 20, origin=FAR)
    add_run(engine, "walk", datetime(2026, 9, 12, 7), 120, type_="walk")  # longer than any run
    add_run(engine, "y25", datetime(2025, 6, 1, 7), 30)
    with Session(engine) as s:
        s.add_all([models.Shoe(id=1, name="Blue", retired=False, created_at=datetime(2026, 1, 1)),
                   models.Shoe(id=2, name="Red", retired=False, created_at=datetime(2026, 1, 1)),
                   models.Shoe(id=3, name="Unused", retired=False, created_at=datetime(2026, 1, 1)),
                   models.ShoeDefault(from_date="2026-01-01", shoe_id=1),
                   models.WorkoutShoe(workout_id="sep2", shoe_id=2, updated_at=datetime(2026, 9, 9))])
        s.commit()
    recompute_now(engine, "2026-10-26")


@pytest.fixture
def client(engine, app_client, monkeypatch):
    monkeypatch.setattr(queue, "local_today", lambda tz: "2026-10-20")  # the seeded data is "this month"; never the wall clock
    _seed(engine)
    login(app_client)
    return app_client


def get(c, period):
    return c.get(f"/api/v1/recap/{period}")


def test_month_totals_match_the_summary_and_previous_is_last_month(client):
    r = get(client, "2026-09").json()
    cal = client.get("/api/v1/calendar", params={"month": "2026-09"}).json()
    assert r["totals"]["run_count"] == 5 and r["totals"]["distance_m"] == pytest.approx(cal["totals"]["distance_m"])
    assert r["totals"]["duration_s"] == pytest.approx(cal["totals"]["duration_s"])
    assert r["totals"]["active_days"] == 5 and r["kind"] == "month" and not r["is_current"]
    assert r["previous"]["period"] == "2026-08" and r["previous"]["run_count"] == 2


def test_year_sums_months_and_previous_is_last_year(client):
    r = get(client, "2026").json()
    assert r["totals"]["run_count"] == 7 and r["previous"]["period"] == "2025" and r["previous"]["run_count"] == 1
    months = [client.get("/api/v1/calendar", params={"month": f"2026-{m:02d}"}).json()["totals"] for m in (8, 9)]
    assert r["totals"]["distance_m"] == pytest.approx(sum(m["distance_m"] for m in months))
    assert r["totals"]["active_days"] == 7 and r["kind"] == "year"
    assert get(client, "2026-01").json()["previous"]["period"] == "2025-12"


def test_longest_runs_are_three_runs_longest_first_and_never_the_walk(client):
    runs = get(client, "2026-09").json()["longest_runs"]
    assert [x["workout_id"] for x in runs][0] == "sep1" and len(runs) == 3
    assert all(x["type"] == "run" for x in runs)
    d = [x["distance_m"] for x in runs]
    assert d == sorted(d, reverse=True)


def test_top_routes_count_runs_in_the_period(client):
    routes = get(client, "2026-09").json()["top_routes"]
    assert routes and routes[0]["runs"] >= routes[-1]["runs"]
    assert set(routes[0]) == {"route_key", "distance_m", "runs"}
    assert sum(x["runs"] for x in routes) <= 5


def test_shoes_are_per_period_and_skip_unused(client):
    shoes = {x["name"]: x for x in get(client, "2026-09").json()["shoes"]}
    assert shoes["Red"]["runs"] == 1 and shoes["Blue"]["runs"] == 4 and "Unused" not in shoes
    assert shoes["Red"]["distance_m"] > 0


def test_best_week_belongs_to_the_month_of_its_monday(client):
    aug = [w["week_id"] for w in get(client, "2026-08").json()["best_weeks"]]
    sep = [w["week_id"] for w in get(client, "2026-09").json()["best_weeks"]]
    assert "2026-W36" in aug and "2026-W36" not in sep  # Mon 2026-08-31
    assert len(sep) <= 3


def test_fitness_is_daily_for_a_month_and_weekly_for_a_year(client):
    m = get(client, "2026-09").json()["fitness"]
    assert len(m["series"]) == 30 and m["start"] == m["series"][0]["fitness"] and m["end"] == m["series"][-1]["fitness"]
    y = get(client, "2026").json()["fitness"]
    assert 30 < len(y["series"]) < 60


def test_empty_period_is_zeros_and_empty_lists(client):
    r = get(client, "2026-03")
    assert r.status_code == 200
    b = r.json()
    assert b["totals"]["run_count"] == 0 and b["totals"]["distance_m"] == 0 and b["totals"]["active_days"] == 0
    assert b["longest_runs"] == [] and b["top_routes"] == [] and b["shoes"] == [] and b["best_weeks"] == []


def test_current_month_is_so_far(client):
    assert get(client, "2026-10").json()["is_current"] and get(client, "2026").json()["is_current"]


@pytest.mark.parametrize("p", ["2026-13", "26", "2026-00", "abcd", "2026-1", "2026-11", "2027", "0000", "0001-01", "0999"])
def test_bad_or_future_period_is_422(client, p):
    assert get(client, p).status_code == 422


def test_requires_a_session(app_client):
    assert get(app_client, "2026").status_code == 401


def test_best_weeks_rank_by_distance(client):
    ids = lambda p: [w["week_id"] for w in get(client, p).json()["best_weeks"]]
    assert ids("2026-09") == ["2026-W37", "2026-W38"]
    assert ids("2026-08") == ["2026-W36", "2026-W32"]
    assert ids("2026") == ["2026-W36", "2026-W37", "2026-W32"]


def test_best_weeks_carry_load_when_the_top_week_is_the_later_one(client):
    weeks = get(client, "2026-08").json()["best_weeks"]
    assert weeks[0]["week_id"] == "2026-W36" and weeks[0]["load"]["fitness"] is not None
    assert all(w["load"]["fitness"] is not None and w["load"]["total"] > 0 for w in weeks)


def test_shoes_are_ordered_by_distance(client):
    assert [x["name"] for x in get(client, "2026-09").json()["shoes"]] == ["Blue", "Red"]


def test_year_fitness_ends_on_the_last_load_day(client):
    y = get(client, "2026").json()["fitness"]
    assert y["series"][-1]["local_date"] == "2026-10-26" and y["end"] == y["series"][-1]["fitness"]


def test_empty_period_has_no_elevation(client):
    assert get(client, "2026-03").json()["totals"]["elevation_gain_m"] is None


def test_longest_runs_carry_weight(engine, client):
    with Session(engine) as s:
        s.add(models.WorkoutCarry(workout_id="sep1", weight_kg=11.3, updated_at=datetime(2026, 9, 2)))
        s.commit()
    runs = {x["workout_id"]: x for x in get(client, "2026-09").json()["longest_runs"]}
    assert runs["sep1"]["carry_kg"] == pytest.approx(11.3)
