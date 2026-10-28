from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.pipeline.derive import records, summary, track
from strydr.store import generations, models

from helpers import add_run, recompute_now

AS_OF = "2026-10-26"


def _records(engine) -> dict[str, models.Record]:
    with Session(engine) as s:
        return {r.key: r for r in s.execute(generations.scoped(models.Record)).scalars()}


def test_best_efforts_from_route_distance_and_time(engine):
    # 5 m/s for the first 1100 s (5.5 km), then 3 m/s: the fast block holds every best effort up to 5 km.
    add_run(engine, "fast", datetime(2026, 10, 6, 7), 40, speed_fn=lambda i: 5.0 if i < 1100 else 3.0)
    add_run(engine, "slow", datetime(2026, 10, 4, 7), 60, 2.8)
    recompute_now(engine, AS_OF)
    r = _records(engine)
    assert r["best_1km"].value == pytest.approx(200, abs=1.5) and r["best_1km"].workout_id == "fast"
    assert r["best_1mi"].value == pytest.approx(1609.344 / 5, abs=1.5)
    assert r["best_5km"].value == pytest.approx(1000, abs=2)
    assert r["best_10km"].workout_id == "slow"  # only the 10.08 km run reaches 10 km
    assert "best_half" not in r and "best_marathon" not in r
    assert r["longest_run"].workout_id == "slow"


def test_gps_sanity_rejects_untrusted_tracks_and_dropouts():
    t = list(range(401))
    dist = [i * 5.0 for i in t]  # 5 m/s
    assert track.best_time(dist, t, 1000) == pytest.approx(200)
    assert track.best_time([i * 20.0 for i in range(101)], list(range(101)), 1000) is None  # 20 m/s: GPS glitch
    gap_t = list(range(150)) + list(range(350, 500))  # 200 s dropout in the middle of every 1 km window
    assert track.best_time([i * 5.0 for i in range(300)], gap_t, 1000) is None
    assert records.best_efforts(dist, t, reported_m=1000) == {}  # track 2x the watch's distance: not trusted
    assert records.best_efforts(dist, t, reported_m=None)["1km"] == pytest.approx(200)
    assert records.best_efforts(dist, t, reported_m=2010)["1mi"] == pytest.approx(1609.344 / 5)


def test_walks_and_routeless_runs_have_no_best_efforts(engine):
    add_run(engine, "walk", datetime(2026, 10, 6, 7), 40, 1.5, type_="walk")
    add_run(engine, "treadmill", datetime(2026, 10, 7, 7), 40, 3.0, route=False)
    recompute_now(engine, AS_OF)
    r = _records(engine)
    assert not any(k.startswith("best_1") for k in r)
    assert r["longest_run"].workout_id == "treadmill"  # route-free runs still count toward distance records


def test_record_week_and_month(engine):
    add_run(engine, "a", datetime(2026, 10, 5, 7), 30, 3.0)  # week 41
    add_run(engine, "b", datetime(2026, 10, 7, 7), 30, 3.0)  # week 41
    add_run(engine, "c", datetime(2026, 10, 13, 7), 50, 3.0)  # week 42
    add_run(engine, "w", datetime(2026, 10, 8, 7), 120, 1.4, type_="walk")  # never counted
    recompute_now(engine, AS_OF)
    r = _records(engine)
    assert r["record_week"].period_id == "2026-W41" and r["record_week"].value == pytest.approx(10_800, rel=0.01)
    assert r["record_month"].period_id == "2026-10"


def test_records_update_on_recompute(engine):
    add_run(engine, "a", datetime(2026, 10, 5, 7), 30, 3.0)
    recompute_now(engine, AS_OF)
    first = _records(engine)["longest_run"]
    add_run(engine, "b", datetime(2026, 10, 12, 7), 45, 3.0)
    recompute_now(engine, AS_OF)
    assert (first.workout_id, _records(engine)["longest_run"].workout_id) == ("a", "b")


def test_summary_pure_functions():
    assert summary.week_id("2026-12-31") == "2026-W53" and summary.week_id("2027-01-03") == "2026-W53"
    assert summary.zone_seconds([100, 120, 140, 160, 180], [110, 128, 146, 165]) == [60, 60, 60, 60, 60]
    assert summary.zone_seconds([], [110, 128, 146, 165]) is None and summary.zone_seconds([100], None) is None
    assert summary.is_long_run(17_000, 3000) and summary.is_long_run(8000, 80 * 60) and not summary.is_long_run(10_000, 3000)
