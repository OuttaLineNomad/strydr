"""derive/days: hard-day and rest-day classification (FR-18)."""
from datetime import date, timedelta

from insight_synth import load_params, th

from strydr.pipeline.derive.days import DayParams, DayWorkout, classify_days, hard_seconds

P = DayParams.from_mapping(th().section("days"))
D = date(2026, 10, 1)


def _classify(by_day, d=D):
    return classify_days(by_day, d, d, P)[0]


def test_hard_seconds_counts_time_at_or_above_88_percent_of_hrmax():
    # HRmax 190 -> cut 167.2; 25 one-minute samples at 170, 35 at 140
    samples = [(60.0 * i, 170.0 if i < 25 else 140.0) for i in range(60)]
    assert hard_seconds(samples, 3600, 190, load_params(), 0.88) == 25 * 60


def test_hard_seconds_does_not_fill_gaps():
    samples = [(0.0, 175.0), (900.0, 175.0)]  # one sample, then a 15-minute hole
    assert hard_seconds(samples, 960, 190, load_params(), 0.88) == 120 + 60


def test_twenty_minutes_hard_is_a_hard_day_nineteen_is_not():
    assert _classify({D: [DayWorkout("run", 3600, 60, hard_s=1200)]}).is_hard
    assert not _classify({D: [DayWorkout("run", 3600, 60, hard_s=1199)]}).is_hard


def test_hard_seconds_sum_across_workouts_in_a_day():
    day = [DayWorkout("run", 1800, 30, hard_s=600), DayWorkout("hike", 1800, 30, hard_s=600)]
    assert _classify({D: day}).is_hard


def test_long_run_is_hard_regardless_of_hr():
    c = _classify({D: [DayWorkout("run", 7000, 80, is_long_run=True)]})
    assert c.is_hard and c.reasons == ("long-run",)


def test_run_day_is_never_rest():
    c = _classify({D: [DayWorkout("run", 1200, 5)]})
    assert c.has_run and not c.is_rest and c.kind == "run"


def test_empty_day_is_rest():
    c = _classify({})
    assert c.is_rest and c.kind == "rest" and c.load == 0 and not c.is_hard


def _with_run_history(extra):
    hist = {D - timedelta(days=k): [DayWorkout("run", 3000, 80.0)] for k in (3, 5, 9, 12)}
    hist.update(extra)
    return hist


def test_easy_walk_counts_as_rest_when_under_quarter_of_median_run_load():
    c = _classify(_with_run_history({D: [DayWorkout("walk", 2400, 20.0)]}))  # cap = 0.25 * 80 = 20
    assert c.is_rest and c.kind == "rest"


def test_big_hike_is_an_active_day_not_rest():
    c = _classify(_with_run_history({D: [DayWorkout("hike", 10800, 90.0, elevation_gain_m=600)]}))
    assert not c.is_rest and c.kind == "active" and not c.is_hard


def test_rest_cap_edge_at_exactly_a_quarter():
    assert _classify(_with_run_history({D: [DayWorkout("walk", 2400, 20.0)]})).is_rest
    assert not _classify(_with_run_history({D: [DayWorkout("walk", 2400, 20.1)]})).is_rest


def test_median_ignores_runs_outside_28_days():
    old = {D - timedelta(days=40): [DayWorkout("run", 3000, 400.0)]}
    c = _classify({**old, D: [DayWorkout("walk", 2400, 20.0)]})  # no usable history -> fallback rule
    assert c.is_rest


def test_fallback_without_history_uses_minutes_effort_and_climb():
    assert _classify({D: [DayWorkout("walk", 3600, 30, effort_score=4, elevation_gain_m=150)]}).is_rest
    assert not _classify({D: [DayWorkout("walk", 3601, 30)]}).is_rest
    assert not _classify({D: [DayWorkout("walk", 1800, 30, effort_score=5)]}).is_rest
    assert not _classify({D: [DayWorkout("hike", 3000, 30, elevation_gain_m=151)]}).is_rest


def test_classify_returns_one_row_per_day_zero_filled():
    out = classify_days({D: [DayWorkout("run", 1800, 40.0)]}, D, D + timedelta(days=2), P)
    assert [c.local_date for c in out] == [D, D + timedelta(days=1), D + timedelta(days=2)]
    assert [c.load for c in out] == [40.0, 0, 0]
