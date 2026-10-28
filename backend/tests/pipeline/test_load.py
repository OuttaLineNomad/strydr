"""derive/load: TRIMP, fallback chain, EWMA, hysteresis (hand-computed expectations)."""
import math
from datetime import date, timedelta

import pytest
from insight_synth import load_params, th

from strydr.pipeline.derive.load import (
    WorkoutLoad,
    WorkoutLoadInput,
    apply_hysteresis,
    compute_workout_load,
    covered_seconds,
    daily_loads,
    fitness_fatigue,
    hr_intervals,
    hrr_fraction,
    trimp_from_intervals,
    training_states,
)

P = load_params()
D0 = date(2026, 9, 1)


def test_trimp_matches_hand_computation():
    # HRmax 200, rest 40, 30 min at 130 bpm: x = 90/160 = 0.5625
    # 30 * 0.5625 * 0.64 * exp(1.92 * 0.5625) = 31.8025...
    samples = [(60.0 * i, 130.0) for i in range(30)]
    iv = hr_intervals(samples, 1800, P)
    assert trimp_from_intervals(iv, 200, 40, P.b_for("male")) == pytest.approx(31.8025, abs=1e-3)
    # female coefficient 1.67 -> 27.6305
    assert trimp_from_intervals(iv, 200, 40, P.b_for("female")) == pytest.approx(27.6305, abs=1e-3)


def test_default_coefficient_is_male_and_unknown_sex_uses_it():
    assert P.b_for(None) == 1.92 and P.b_for("male") == 1.92 and P.b_for("female") == 1.67


def test_single_minute_value():
    # x = 0.5 -> 0.5 * 0.64 * exp(0.96) = 0.83574
    assert trimp_from_intervals([(120.0, 60.0)], 200, 40, 1.92) == pytest.approx(0.835743, abs=1e-5)


def test_hr_reserve_is_clamped():
    assert hrr_fraction(210, 190, 50) == 1.0
    assert hrr_fraction(40, 190, 50) == 0.0
    assert hrr_fraction(100, 50, 50) == 0.0  # degenerate reserve


def test_time_step_capped_at_two_minutes_and_gap_not_filled():
    # samples at 0 s and 600 s: the first covers 120 s of the 600 s gap, the rest is a gap.
    iv = hr_intervals([(0.0, 150.0), (600.0, 150.0)], 660, P)
    assert iv[0] == (150.0, 120.0)
    assert covered_seconds(iv) == 120.0 + 60.0  # last sample: typical step capped at 120 -> 60 s remaining


def test_implausible_samples_are_dropped_without_stretching_neighbours():
    iv = hr_intervals([(0.0, 140.0), (60.0, 250.0), (120.0, 140.0)], 180, P)
    assert [dt for _, dt in iv] == [60.0, 60.0]


def _hr_input(coverage_minutes, total_min=60, hr=150.0, **kw):
    return WorkoutLoadInput(
        "w1", "run", D0, total_min * 60.0, avg_hr=kw.pop("avg_hr", 150.0),
        hr_samples=[(60.0 * i, hr) for i in range(coverage_minutes)], **kw,
    )


def test_tier_a_full_coverage_is_measured():
    res = compute_workout_load(_hr_input(60), hr_max=190, hr_rest=50, sex="male", params=P)
    assert (res.source, res.estimated) == ("hr", False)
    x = (150 - 50) / 140
    assert res.trimp == pytest.approx(60 * x * 0.64 * math.exp(1.92 * x))


def test_tier_a_partial_coverage_scales_to_full_duration_and_flags_estimate():
    full = compute_workout_load(_hr_input(60), hr_max=190, hr_rest=50, sex="male", params=P).trimp
    part = compute_workout_load(_hr_input(48), hr_max=190, hr_rest=50, sex="male", params=P)  # 80% coverage
    assert part.source == "hr-scaled" and part.estimated
    assert part.coverage == pytest.approx(0.8)
    assert part.trimp == pytest.approx(full)


def test_tier_b_average_hr_when_coverage_below_80():
    res = compute_workout_load(_hr_input(30, avg_hr=140.0), hr_max=190, hr_rest=50, sex="male", params=P)
    x = 90 / 140
    assert (res.source, res.estimated) == ("avg-hr", True)
    assert res.trimp == pytest.approx(60 * x * 0.64 * math.exp(1.92 * x))


def _history(n, trimp_per_min=1.0, days_ago=10):
    return [
        WorkoutLoad(f"h{i}", "run", D0 - timedelta(days=days_ago + i), trimp_per_min * 60, False, "hr", 1.0, 3600.0,
                    3.0, 190, 50, 1.92)
        for i in range(n)
    ]


def test_tier_c_personal_rate_from_own_history():
    inp = WorkoutLoadInput("w1", "run", D0, 1800.0, avg_speed_mps=3.0)
    res = compute_workout_load(inp, hr_max=190, hr_rest=50, sex="male", params=P, history=_history(5, 1.2))
    assert (res.source, res.estimated) == ("personal-rate", True)
    assert res.trimp == pytest.approx(1.2 * 30)


def test_tier_c_needs_five_sessions_then_default_applies():
    inp = WorkoutLoadInput("w1", "run", D0, 1800.0, avg_speed_mps=3.0)
    res = compute_workout_load(inp, hr_max=190, hr_rest=50, sex="male", params=P, history=_history(4))
    assert res.source == "default"
    x = 0.70  # run default HR-reserve fraction
    assert res.trimp == pytest.approx(30 * x * 0.64 * math.exp(1.92 * x))


def test_tier_c_ignores_estimated_and_old_history():
    old = _history(5, days_ago=130)
    est = [WorkoutLoad(h.workout_id, h.type, h.local_date + timedelta(days=125), h.trimp, True, "avg-hr", 0.0, h.duration_s,
                       3.0, 190, 50, 1.92) for h in old]
    inp = WorkoutLoadInput("w1", "run", D0, 1800.0)
    assert compute_workout_load(inp, hr_max=190, hr_rest=50, sex=None, params=P, history=old + est).source == "default"


def test_tier_c_pace_band_for_runs():
    fast = [WorkoutLoad(f"f{i}", "run", D0 - timedelta(days=5 + i), 120.0, False, "hr", 1.0, 3600.0, 4.0, 190, 50, 1.92) for i in range(5)]
    slow = [WorkoutLoad(f"s{i}", "run", D0 - timedelta(days=20 + i), 30.0, False, "hr", 1.0, 3600.0, 2.5, 190, 50, 1.92) for i in range(5)]
    inp = WorkoutLoadInput("w1", "run", D0, 3600.0, avg_speed_mps=4.0)  # 250 s/km, matches the fast set only
    res = compute_workout_load(inp, hr_max=190, hr_rest=50, sex=None, params=P, history=fast + slow)
    assert res.trimp == pytest.approx(120.0)


def test_tier_d_defaults_by_type():
    walk = compute_workout_load(WorkoutLoadInput("w", "walk", D0, 3600.0), hr_max=190, hr_rest=50, sex=None, params=P)
    hike = compute_workout_load(WorkoutLoadInput("w", "hike", D0, 3600.0), hr_max=190, hr_rest=50, sex=None, params=P)
    assert walk.source == hike.source == "default" and walk.estimated
    assert walk.trimp == pytest.approx(60 * 0.40 * 0.64 * math.exp(1.92 * 0.40))
    assert hike.trimp == pytest.approx(60 * 0.55 * 0.64 * math.exp(1.92 * 0.55))


def test_rpe_overrides_an_estimate_by_interpolation_but_not_a_measured_load():
    est = compute_workout_load(WorkoutLoadInput("w", "run", D0, 3600.0, rpe=5), hr_max=190, hr_rest=50, sex=None, params=P)
    assert est.source == "rpe" and est.estimated
    assert est.trimp == pytest.approx(60 * 0.70 * 0.64 * math.exp(1.92 * 0.70))  # RPE 5 -> 0.70
    mid = compute_workout_load(WorkoutLoadInput("w", "run", D0, 3600.0, rpe=6), hr_max=190, hr_rest=50, sex=None, params=P)
    x = (0.70 + 0.82) / 2
    assert mid.trimp == pytest.approx(60 * x * 0.64 * math.exp(1.92 * x))
    measured = compute_workout_load(_hr_input(60, rpe=9), hr_max=190, hr_rest=50, sex=None, params=P)
    assert measured.source == "hr"


def test_missing_resting_hr_uses_default_and_no_duration_is_zero():
    res = compute_workout_load(_hr_input(60), hr_max=190, hr_rest=None, sex=None, params=P)
    assert res.hr_rest == 60
    none = compute_workout_load(WorkoutLoadInput("w", "run", D0, None), hr_max=190, hr_rest=50, sex=None, params=P)
    assert none.trimp == 0 and none.estimated


def test_daily_loads_zero_filled_and_stacked_by_type():
    mk = lambda wid, t, d, v, est=False: WorkoutLoad(wid, t, d, v, est, "hr", 1.0, 3600.0, None, 190, 50, 1.92)  # noqa: E731
    loads = [mk("a", "run", D0, 40), mk("b", "walk", D0, 5, True), mk("c", "hike", D0 + timedelta(days=2), 30)]
    days = daily_loads(loads, D0, D0 + timedelta(days=3))
    assert [d.total for d in days] == [45, 0, 30, 0]
    assert days[0].by_type == {"run": 40, "walk": 5, "hike": 0}
    assert days[0].estimated and not days[2].estimated
    assert [d.n_workouts for d in days] == [2, 0, 1, 0]


def _flat_days(n, load):
    loads = [WorkoutLoad(f"w{i}", "run", D0 + timedelta(days=i), load, False, "hr", 1.0, 3600.0, None, 190, 50, 1.92) for i in range(n)]
    return daily_loads(loads, D0, D0 + timedelta(days=n - 1))


def test_ewma_hand_computed():
    fd = fitness_fatigue(_flat_days(3, 100.0), 42, 7, 42)
    f1, a1 = 100 / 42, 100 / 7
    assert fd[0].fitness == pytest.approx(f1) and fd[0].fatigue == pytest.approx(a1)
    assert fd[0].form is None and fd[0].form_pct is None
    f2, a2 = f1 + (100 - f1) / 42, a1 + (100 - a1) / 7
    assert fd[1].fitness == pytest.approx(f2) and fd[1].fatigue == pytest.approx(a2)
    # form on the morning of day 2 uses the previous day's values, as % of previous fitness
    assert fd[1].form == pytest.approx(f1 - a1)
    assert fd[1].form_pct == pytest.approx((f1 - a1) / f1 * 100)
    assert fd[2].form == pytest.approx(f2 - a2)


def test_ewma_seed_is_mean_of_first_days_and_removes_cold_start_bias():
    fd = fitness_fatigue(_flat_days(3, 100.0), 42, 7, 42, seed_days=28)
    assert [round(d.fitness, 6) for d in fd] == [100.0] * 3 and fd[0].form == 0
    mixed = _flat_days(2, 100.0)
    seeded = fitness_fatigue(mixed, 42, 7, 42, seed_days=2)
    assert seeded[0].fitness == pytest.approx(100.0)


def test_ewma_zero_load_days_decay():
    days = daily_loads([WorkoutLoad("w", "run", D0, 100.0, False, "hr", 1.0, 3600.0, None, 190, 50, 1.92)], D0, D0 + timedelta(days=2))
    fd = fitness_fatigue(days, 42, 7, 42)
    assert fd[1].fitness == pytest.approx(fd[0].fitness * (1 - 1 / 42))
    assert fd[1].fatigue == pytest.approx(fd[0].fatigue * (1 - 1 / 7))


def test_warmup_flag_covers_first_42_days():
    fd = fitness_fatigue(_flat_days(50, 50.0), 42, 7, 42)
    assert all(d.warmup for d in fd[:42]) and not any(d.warmup for d in fd[42:])


def test_hysteresis_needs_three_consecutive_days():
    raw = ["Holding"] * 3 + ["Building", "Building", "Holding"] + ["Building"] * 3
    out = apply_hysteresis(raw, 3)
    assert [s for s, _ in out[:6]] == ["Holding"] * 6  # two Building days then back: no change
    assert [s for s, _ in out[6:]] == ["Holding", "Holding", "Building"]
    assert out[8][1] == 6  # 'since' backdates to the first day of the confirmed run


def test_hysteresis_candidate_switch_restarts_the_count():
    raw = ["Holding", "Building", "Building", "Easing", "Easing", "Easing"]
    out = apply_hysteresis(raw, 3)
    assert [s for s, _ in out] == ["Holding"] * 5 + ["Easing"]


def test_hysteresis_none_resets_and_first_state_is_immediate():
    out = apply_hysteresis([None, "Building", None, "Easing"], 3)
    assert out == [(None, None), ("Building", 1), (None, None), ("Easing", 3)]


def _states(loads_by_day):
    days = daily_loads(
        [WorkoutLoad(f"w{i}", "run", D0 + timedelta(days=i), v, False, "hr", 1.0, 3600.0, None, 190, 50, 1.92)
         for i, v in enumerate(loads_by_day) if v > 0],
        D0, D0 + timedelta(days=len(loads_by_day) - 1))
    return training_states(
        fitness_fatigue(days, P.tau_fitness_days, P.tau_fatigue_days, P.warmup_days, P.seed_days), th().section("training-state")
    )


def test_training_state_none_during_warmup_then_holding_when_steady():
    st = _states([60.0] * 120)
    assert st[30].state is None
    assert st[119].state == "Holding"


def test_training_state_building_and_easing_and_overreaching():
    build = _states([40.0] * 60 + [40.0 + 0.5 * i for i in range(60)])
    assert build[-1].state == "Building"
    assert any(s.state == "Building" for s in build)
    ease = _states([80.0] * 80 + [40.0] * 40)
    assert ease[-1].state == "Easing"
    over = _states([40.0] * 60 + [150.0] * 10)
    assert over[59].state == "Holding"
    assert any(s.state == "Overreaching" for s in over[60:])
    assert over[-1].ramp_pct is not None and over[-1].form_pct is not None and over[-1].form_pct <= -30


def test_training_state_requires_recent_sessions():
    st = _states([60.0] * 100 + [0.0] * 14)
    assert st[-1].state is None  # no sessions in 14 days
