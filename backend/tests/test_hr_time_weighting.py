"""Per-second HR (HAE at seconds aggregation) counts by the time each reading covers, never 60 s per reading."""
import importlib.util
import json
import sys
import zlib
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from strydr.pipeline import hr
from strydr.pipeline.derive import summary
from strydr.pipeline.derive import days as days_mod
from strydr.pipeline.derive.load import LoadParams
from strydr.pipeline.derive.load.trimp import hr_intervals
from strydr.pipeline.hr import minute_means, sample_steps
from strydr.pipeline.insights.thresholds import load_thresholds
from strydr.pipeline.profile import resolve
from strydr.store import models, settings

from conftest import FIXTURES, load_fixture
from helpers import add_run, login, recompute_now



def _generator():
    spec = importlib.util.spec_from_file_location("hae_gen", FIXTURES / "generate_hae_export.py")
    mod = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # no __pycache__ in fixtures/
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


g = _generator()

BOUNDS = [114.0, 133.0, 152.0, 171.0]


def _readings(minutes, per_minute_hr, step=5):
    """5-s readings holding `per_minute_hr[m]` inside minute m."""
    t = [float(s) for s in range(0, minutes * 60, step)]
    return t, [float(per_minute_hr[int(x // 60)]) for x in t]


def test_per_minute_twin_agrees_with_five_second_readings():
    hrs = [140 + (m * 7) % 40 for m in range(30)]
    t5, a5 = _readings(30, hrs)
    t60, a60 = [m * 60.0 + 30 for m in range(30)], [float(h) for h in hrs]
    z5, z60 = summary.zone_seconds(a5, BOUNDS, hr_t=t5), summary.zone_seconds(a60, BOUNDS, hr_t=t60)
    assert z5 == pytest.approx(z60, rel=0.01)
    m5, m60 = summary.intensity_mix(t5, a5, 1800.0, 152.0), summary.intensity_mix(t60, a60, 1800.0, 152.0)
    assert m5 == pytest.approx(m60, rel=0.01)
    assert sum(z5) == pytest.approx(1800.0)
    p5 = summary.minute_points({"t": t5, "avg": a5}, None, 1800.0)
    p60 = summary.minute_points({"t": t60, "avg": a60}, None, 1800.0)
    assert p5 == p60


def test_regular_minute_data_is_unchanged():
    assert summary.zone_seconds([100, 120, 140, 160, 180], [110, 128, 146, 165]) == [60, 60, 60, 60, 60]
    assert sample_steps([30, 90, 150], [140, 140, 140]) == [60, 60, 60]


def test_dropout_adds_the_cap_not_the_gap():
    t = [float(x) for x in range(0, 300, 5)] + [float(x) for x in range(660, 960, 5)]  # 6-min hole after t=295
    a = [150.0] * len(t)
    steps = sample_steps(t, a)
    assert steps[59] == 120.0
    assert sum(steps) == pytest.approx(59 * 5 + 120 + 59 * 5 + 5)
    means = minute_means(t, a)
    assert not any(m in means for m in range(6, 11))  # minutes inside the gap have no HR


def test_hrmax_spike_needs_two_full_minutes():
    t, a = _readings(10, [170.0] * 10)
    for i, x in enumerate(t):
        if 200 <= x < 220:
            a[i] = 195.0
    assert resolve.observed_hrmax([(t, a)]) <= 172


def test_hrmax_sustained_two_minutes():
    hrs = [150.0] * 10
    hrs[4] = hrs[5] = 180.0
    t, a = _readings(10, hrs)
    assert resolve.observed_hrmax([(t, a)]) == 180


def test_impossible_reading_counts_no_time_and_neighbours_do_not_stretch():
    t = [0.0, 5.0, 10.0, 15.0, 20.0]
    a = [150.0, 150.0, 320.0, 150.0, 150.0]
    assert sample_steps(t, a) == [5.0, 5.0, 0.0, 5.0, 5.0]


def test_lone_sample_covers_sixty_seconds():
    assert sample_steps([12.0], [150.0]) == [60.0]
    assert summary.zone_seconds([150.0], BOUNDS, hr_t=[12.0]) == [0, 0, 60, 0, 0]


def test_ingested_seconds_run_never_exceeds_its_duration(engine, ingest, worker, app_client):
    body = load_fixture("hae-seconds.json")
    assert ingest.post("/ingest/hae", content=json.dumps(body).encode()).status_code == 202
    worker.run_all()
    with Session(engine) as s:
        settings.write(s, settings.UserSettings(birth_year=1990))
        s.commit()
    recompute_now(engine, "2026-03-10")
    login(app_client)
    (wo,) = app_client.get("/api/v1/workouts").json()
    d = app_client.get(f"/api/v1/workouts/{wo['workout_id']}").json()
    assert len(d["hr_series"]) == len(body["data"]["workouts"][0]["heartRateData"])  # nothing thinned at ingest
    zones = d["zone_seconds"]
    assert zones and 0 < sum(zones) <= d["workout"]["duration_s"]

    # the same run at per-minute resolution: minute means of the ingested readings, placed mid-minute
    bounds = [100.0, 120.0, 140.0, 175.0]  # the run sits well inside one zone, clear of boundary flapping
    t = [p["t_s"] for p in d["hr_series"]]
    a = [p["avg"] for p in d["hr_series"]]
    means = minute_means(t, a)
    keys = sorted(means)
    z_secs = summary.zone_seconds(a, bounds, hr_t=t)
    z_min = summary.zone_seconds([means[m] for m in keys], bounds, hr_t=[m * 60.0 + 30 for m in keys])
    assert z_secs == pytest.approx(z_min, abs=120)  # the one dropout adds up to the 120-s cap that the twin lacks


def test_per_minute_buckets_with_a_missing_minute_keep_todays_results():
    t, a = [300.0, 360.0, 480.0], [150.0] * 3
    assert sample_steps(t, a) == [60, 60, 60]
    assert sum(summary.zone_seconds(a, BOUNDS, hr_t=t)) == 180


def test_unsorted_readings_get_the_same_steps_in_the_callers_order():
    t = [float(x) for x in range(0, 100, 5)]
    a = [150.0 + i for i in range(len(t))]
    a[7] = 320.0
    want = sample_steps(t, a)
    order = [11, 3, 19, 0, 7, 15, 1, 12, 5, 18, 2, 9, 14, 4, 17, 6, 10, 13, 8, 16]
    got = sample_steps([t[i] for i in order], [a[i] for i in order])
    assert got == [want[i] for i in order]


def test_a_few_seconds_in_two_minutes_is_not_two_minutes_held():
    assert resolve.observed_hrmax([([119.0, 121.0], [180.0, 180.0])]) is None


def test_all_impossible_readings_give_no_zones():
    assert summary.zone_seconds([320.0, 10.0], BOUNDS, hr_t=[0.0, 5.0]) is None


def test_step_cap_equals_the_configured_max_step():
    assert hr.MAX_STEP_S == LoadParams.from_mapping(load_thresholds().section("load")).max_step_s


# --- story 10: heart rate is weighted on the active clock `at`, so a pause adds no time ---

def _paused_run(paused_hr=190.0, run_hr=130.0):
    """5-s readings over 20 wall-clock minutes; minutes 10-14 are paused (`at` parked at 600 s) at `paused_hr`."""
    t = [float(s) for s in range(0, 1200, 5)]
    at = [x if x < 600 else (600.0 if x <= 900 else x - 300.0) for x in t]
    avg = [paused_hr if 600 <= x < 900 else run_hr for x in t]
    return {"t": t, "at": at, "avg": avg}, 900.0  # 900 s active


def test_active_clock_falls_back_to_t_when_at_is_missing_or_empty():
    assert hr.active_clock({"t": [1.0], "at": [2.0]}) == [2.0]
    assert hr.active_clock({"t": [1.0]}) == [1.0]
    assert hr.active_clock({"t": [1.0], "at": []}) == [1.0]


def test_paused_readings_add_no_zone_easy_intensity_hard_or_load_time():
    series, active_s = _paused_run()
    clock = hr.active_clock(series)
    zones = summary.zone_seconds(series["avg"], BOUNDS, hr_t=clock)
    assert zones[4] == 0 and sum(zones) <= active_s
    assert summary.zone_seconds(series["avg"], BOUNDS, hr_t=series["t"])[4] > 0  # wall clock would have counted the pause

    total, easy, _ = summary.intensity_mix(clock, series["avg"], active_s, 140.0)
    assert easy == total <= active_s - summary.WARMUP_S

    params = LoadParams.from_mapping(load_thresholds().section("load"))
    samples = list(zip(clock, series["avg"]))
    assert days_mod.hard_seconds(samples, active_s, 200.0, params, 0.85) == 0.0
    assert sum(dt for _, dt in hr_intervals(samples, active_s, params)) <= active_s
    assert not any(h == 190.0 and dt > 0 for h, dt in hr_intervals(samples, active_s, params))


def test_minute_points_bin_hr_and_route_on_the_active_clock():
    series, active_s = _paused_run()
    route = {"t": series["t"], "at": series["at"], "alt": [10.0] * len(series["t"]),
             "speed": [3.0] * len(series["t"])}
    pts = summary.minute_points(series, route, active_s)
    assert len(pts) == 15
    assert all(p[0] == 130.0 for p in pts) and all(p[1] == 3.0 for p in pts)


def test_run_without_pauses_gives_identical_results_on_either_clock():
    t, a = _readings(30, [140 + (m * 7) % 40 for m in range(30)])
    series = {"t": t, "at": list(t), "avg": a}
    assert summary.zone_seconds(a, BOUNDS, hr_t=hr.active_clock(series)) == summary.zone_seconds(a, BOUNDS, hr_t=t)
    assert summary.intensity_mix(hr.active_clock(series), a, 1800.0, 152.0) == summary.intensity_mix(t, a, 1800.0, 152.0)
    assert summary.minute_points(series, None, 1800.0) == summary.minute_points({"t": t, "avg": a}, None, 1800.0)


def test_observed_hrmax_ignores_a_paused_spike():
    series, _ = _paused_run(paused_hr=200.0, run_hr=150.0)
    assert resolve.observed_hrmax([(series["t"], series["avg"])]) == 200  # wall clock sees the spike
    assert resolve.observed_hrmax([(hr.active_clock(series), series["avg"])]) == 150


def test_paused_route_fixes_do_not_dilute_the_pause_start_minute_speed():
    t = [float(x) for x in range(150)]
    at = [x if x <= 60 else (60.0 if x < 90 else x - 29.0) for x in t]
    speed = [0.0 if 60 < x < 90 else 3.0 for x in t]
    route = {"t": t, "at": at, "alt": [10.0] * len(t), "speed": speed}
    pts = summary.minute_points(None, route, 121.0)
    assert [p[1] for p in pts] == [3.0, 3.0, 3.0]


# --- the real pipeline reads the active clock (guards the wiring in derive and profile) ---

def _add_hr_with_pause(engine, wid, paused: bool, *, paused_hr=190.0, run_hr=130.0):
    """HR series of 5-s readings; with `paused` the middle 5 of 20 wall-clock minutes are a pause (`at` parked)."""
    t = [float(s) for s in range(0, 1200, 5)]
    if paused:
        at = [x if x < 600 else (600.0 if x <= 900 else x - 300.0) for x in t]
        avg = [paused_hr if 600 <= x < 900 else run_hr for x in t]
    else:
        t = [float(s) for s in range(0, 900, 5)]
        at, avg = list(t), [run_hr] * len(t)
    cols = {"t": t, "at": at, "avg": avg, "min": avg, "max": avg}
    with Session(engine) as s:
        w = s.query(models.Workout).filter_by(workout_id=wid).one()
        w.duration_s = 900.0  # active time
        s.add(models.SampleSeries(workout_id=wid, series="heart_rate", n_samples=len(t), adapter_version=1,
                                  data=zlib.compress(json.dumps(cols).encode())))
        w.series_count += 1
        s.commit()


def _latest(s, model, **kw):
    return s.query(model).filter_by(**kw).order_by(model.generation_id.desc()).first()


def test_pipeline_gives_a_paused_run_no_zone_intensity_load_or_hard_time(engine):
    with Session(engine) as s:
        settings.write(s, settings.UserSettings(birth_year=1990, hrmax_override=190))
        s.commit()
    for wid, day, paused in (("paused", 10, True), ("control", 11, False)):
        add_run(engine, wid, datetime(2026, 3, day, 8, 0), 15, hr=None, route=False)
        _add_hr_with_pause(engine, wid, paused)
    recompute_now(engine, "2026-03-12")
    with Session(engine) as s:
        ws, ctl = _latest(s, models.WorkoutSummary, workout_id="paused"), _latest(s, models.WorkoutSummary, workout_id="control")
        assert sum(ws.zone_seconds) <= 900.0 and ws.zone_seconds[4] == 0
        assert ws.zone_seconds == ctl.zone_seconds
        assert ws.hr_time_s <= 900.0 - summary.WARMUP_S and ws.hr_time_s == pytest.approx(ctl.hr_time_s)
        assert _latest(s, models.WorkoutLoad, workout_id="paused").trimp == pytest.approx(
            _latest(s, models.WorkoutLoad, workout_id="control").trimp)
        assert _latest(s, models.DayClass, local_date="2026-03-10").hard_seconds == 0.0


def test_profile_observed_hrmax_ignores_a_paused_spike(engine):
    for i in range(resolve.OBSERVED_MIN_RUNS):
        wid = f"r{i}"
        add_run(engine, wid, datetime(2026, 3, 1 + i, 8, 0), 15, hr=None, route=False)
        _add_hr_with_pause(engine, wid, True, paused_hr=200.0, run_hr=150.0)
    recompute_now(engine, "2026-03-12")
    with Session(engine) as s:
        prof = _latest(s, models.ProfileResult)
    assert (prof.hrmax_source, prof.hrmax) == ("observed", 150)
