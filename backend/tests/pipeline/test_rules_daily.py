"""Rules: resting-hr, hrv, pace-at-fixed-hr, hard-day-stacking, no-rest-day, training-state."""
import math
from datetime import date, timedelta

import pytest
from insight_synth import AS_OF, baseline, day_classes, daily, minutes, run, snapshot, th

from strydr.pipeline.derive.load.model import TrainingStateDay
from strydr.pipeline.insights.keys import make_fact
from strydr.pipeline.insights.rules.hard_days import hard_day_stacking
from strydr.pipeline.insights.rules.hrv import hrv
from strydr.pipeline.insights.rules.no_rest_day import no_rest_day
from strydr.pipeline.insights.rules.pace_at_fixed_hr import pace_at_fixed_hr
from strydr.pipeline.insights.rules.resting_hr import resting_hr
from strydr.pipeline.insights.rules.training_state import training_state

D = timedelta(days=1)


# ---- resting-hr ----

def _rhr(values, base=baseline(50.0, 2.0, 30), as_of=AS_OF):
    snap = snapshot(as_of=as_of, resting_hr=daily(as_of - (len(values) - 1) * D, values), rhr_baseline=base)
    return resting_hr(snap, th(), [])


def test_rhr_fires_after_three_days_at_or_above_baseline_plus_five():
    (f,) = _rhr([55.0, 56.0, 57.0])  # cut = 50 + max(5, 1.5*2) = 55
    assert f.kind == "observation" and f.template_id == "resting-hr-elevated" and f.unit == "bpm"
    assert f.number == 6.0
    assert f.insight_key == f"resting-hr:athlete:{(AS_OF - 2 * D).isoformat()}"
    assert f.evidence["data"]["baseline_days"] == 30


def test_rhr_edges_just_below_cut_two_days_and_a_gap():
    assert _rhr([54.9, 56.0, 57.0]) == []
    assert _rhr([40.0, 55.0, 56.0]) == []  # only two elevated days
    snap = snapshot(resting_hr=daily(AS_OF - 2 * D, [56.0, 56.0, 56.0])[:1] + daily(AS_OF, [56.0]), rhr_baseline=baseline(50, 2))
    assert resting_hr(snap, th(), []) == []  # a missing day breaks the run


def test_rhr_uses_one_and_a_half_sd_when_larger_than_five_bpm():
    wide = baseline(50.0, 5.0)  # cut = 50 + 7.5
    assert _rhr([57.0, 57.0, 57.0], wide) == []
    assert len(_rhr([57.5, 57.5, 57.5], wide)) == 1


def test_rhr_needs_21_baseline_days():
    assert _rhr([60.0, 60.0, 60.0], baseline(50, 2, 20)) == []
    assert len(_rhr([60.0, 60.0, 60.0], baseline(50, 2, 21))) == 1
    assert _rhr([60.0, 60.0, 60.0], None) == []


def test_rhr_episode_key_is_the_start_date_and_is_stable_while_the_episode_lasts():
    vals = [57.0] * 5
    a = _rhr(vals, as_of=AS_OF)[0]
    b = _rhr(vals + [58.0], as_of=AS_OF + D)[0]
    assert a.insight_key == b.insight_key == f"resting-hr:athlete:{(AS_OF - 4 * D).isoformat()}"


def test_rhr_outliers_become_check_readings_not_interpretation():
    for value in (120.0, 34.0, 65.0):  # >100, <35, baseline + 15
        facts = _rhr([51.0, 51.0, value])
        assert [(f.kind, f.template_id, f.number) for f in facts] == [("check-reading", "resting-hr-check", value)]
    assert all(f.kind != "check-reading" for f in _rhr([51.0, 51.0, 64.9]))
    assert _rhr([51.0, 51.0, 35.0]) == []  # 35 and 100 are inside the plausible range
    assert _rhr([51.0, 51.0, 100.0]) != []  # 100 is plausible but 50 above baseline: check, not interpreted


def test_rhr_outlier_day_does_not_count_toward_an_elevated_streak():
    facts = _rhr([56.0, 66.0, 56.0])
    assert [f.kind for f in facts] == ["check-reading"]


def test_rhr_check_reading_works_without_a_baseline_for_absolute_range():
    (f,) = _rhr([120.0], base=None)
    assert f.kind == "check-reading"


# ---- hrv ----

HB = baseline(math.log(60.0), 0.1, 45)  # range floor = exp(ln60 - 0.1) = 54.3 ms


def _hrv(values, base=HB, prior=None, as_of=AS_OF):
    snap = snapshot(as_of=as_of, hrv_sdnn_ms=daily(as_of - (len(values) - 1) * D, values), hrv_baseline=base)
    return hrv(snap, th(), prior or [])


def test_hrv_fires_when_rolling_mean_is_below_range_two_days_running():
    (f,) = _hrv([50.0] * 10)
    assert f.kind == "observation" and f.template_id == "hrv-below" and f.unit == "%"
    assert f.number == pytest.approx(16.7, abs=0.05)  # 50 vs 60 ms
    assert f.period == (AS_OF - 6 * D).isoformat()  # first day with >= 4 readings in the window
    assert "noisy" in f.evidence["note"]


def test_hrv_silent_when_only_one_day_is_below_range():
    assert _hrv([60.0] * 9 + [10.0]) == []


def test_hrv_silent_at_the_range_floor_and_with_a_normal_week():
    assert _hrv([60.0] * 10) == []
    floor = math.exp(HB.mean - HB.sd)
    assert _hrv([floor] * 10) == []
    assert len(_hrv([floor * 0.99] * 10)) == 1


def test_hrv_needs_40_baseline_days_and_four_readings_in_the_window():
    assert _hrv([50.0] * 10, baseline(HB.mean, HB.sd, 39)) == []
    assert len(_hrv([50.0] * 10, baseline(HB.mean, HB.sd, 40))) == 1
    sparse = snapshot(hrv_sdnn_ms=daily(AS_OF - 9 * D, [50.0] * 10)[::3], hrv_baseline=HB)  # 4 readings in 10 days
    assert hrv(sparse, th(), []) == []
    assert _hrv([50.0] * 3) == []


def test_hrv_mentions_resting_hr_when_an_episode_is_active():
    rhr = make_fact("resting-hr", "athlete", AS_OF - 2 * D, "observation", 6.0, "bpm", {}, "resting-hr-elevated")
    (f,) = _hrv([50.0] * 10, prior=[rhr])
    assert f.template_id == "hrv-below-rhr" and f.evidence["data"]["resting_hr_also_elevated"] is True
    check = make_fact("resting-hr", "athlete", AS_OF, "check-reading", 120.0, "bpm", {}, "resting-hr-check")
    assert _hrv([50.0] * 10, prior=[check])[0].template_id == "hrv-below"


# ---- pace-at-fixed-hr ----

def _band_runs(recent_speed, old_speed, n_recent=4, n_old=4, temp=None, alt_slope=0.0, hr=140.0):
    mk = lambda wid, ago, speed: run(  # noqa: E731
        wid, AS_OF - ago * D, 8.0, 40, temperature_c=temp,
        minutes=minutes(40, hr=hr, speed=speed, alt_slope=alt_slope),
    )
    recent = tuple(mk(f"n{i}", 2 + 5 * i, recent_speed) for i in range(n_recent))
    old = tuple(mk(f"o{i}", 30 + 5 * i, old_speed) for i in range(n_old))
    return snapshot(runs=recent + old)


def test_pace_at_hr_faster_is_an_attaboy():
    (f,) = pace_at_fixed_hr(_band_runs(3.15, 3.0), th(), [])
    assert f.kind == "attaboy" and f.template_id == "pace-at-hr-faster" and f.number == 5.0
    assert f.evidence["data"]["band_bpm"] == [135.0, 145.0] and f.insight_key == "pace-at-fixed-hr:week/2026-W44:2026-W44"


def test_pace_at_hr_slower_is_a_neutral_observation():
    (f,) = pace_at_fixed_hr(_band_runs(2.9, 3.0), th(), [])
    assert f.kind == "observation" and f.template_id == "pace-at-hr-slower"


def test_pace_at_hr_edges_around_three_percent():
    assert len(pace_at_fixed_hr(_band_runs(3.09, 3.0), th(), [])) == 1
    assert pace_at_fixed_hr(_band_runs(3.08, 3.0), th(), []) == []
    assert pace_at_fixed_hr(_band_runs(3.0, 3.0), th(), []) == []


def test_pace_at_hr_needs_four_runs_in_each_half():
    assert pace_at_fixed_hr(_band_runs(3.3, 3.0, n_recent=3), th(), []) == []
    assert pace_at_fixed_hr(_band_runs(3.3, 3.0, n_old=3), th(), []) == []


def test_pace_at_hr_leaves_out_hot_runs_and_hilly_minutes():
    assert pace_at_fixed_hr(_band_runs(3.3, 3.0, temp=24.0), th(), []) == []
    assert len(pace_at_fixed_hr(_band_runs(3.3, 3.0, temp=23.9), th(), [])) == 1
    assert pace_at_fixed_hr(_band_runs(3.3, 3.0, alt_slope=20.0), th(), []) == []  # ~11% grade is not flat ground


def test_pace_at_hr_ignores_runs_with_fewer_than_ten_minutes_in_band():
    short = tuple(run(f"s{i}", AS_OF - (2 + i) * D, 5.0, 18, minutes=minutes(18, hr=140.0, speed=3.5)) for i in range(4))
    old = _band_runs(3.0, 3.0).runs[4:]
    assert pace_at_fixed_hr(snapshot(runs=short + old), th(), []) == []


def test_pace_at_hr_faster_held_back_by_a_check_reading():
    check = make_fact("resting-hr", "athlete", AS_OF, "check-reading", 120.0, "bpm", {}, "resting-hr-check")
    assert pace_at_fixed_hr(_band_runs(3.3, 3.0), th(), [check]) == []
    assert len(pace_at_fixed_hr(_band_runs(2.8, 3.0), th(), [check])) == 1  # the neutral slower note still shows


# ---- hard-day-stacking ----

START = AS_OF - 40 * D


def _stack(snap):
    return [f for f in hard_day_stacking(snap, th(), []) if f.subject == "athlete"]


def _days(hard=(), **kw):
    return snapshot(days=day_classes(START, AS_OF, hard=set(hard), **kw), history_start=START)


def test_two_hard_days_in_a_row_fire_on_the_second():
    (f,) = _stack(_days([AS_OF - D, AS_OF]))
    assert f.insight_key == f"hard-day-stacking:athlete:{AS_OF.isoformat()}"
    assert f.template_id == "hard-day-stacking-consecutive" and f.number == 2.0 and f.unit == "days"


def test_one_hard_day_or_two_apart_are_silent():
    assert _stack(_days([AS_OF])) == []
    assert _stack(_days([AS_OF - 2 * D, AS_OF])) == []


def test_three_hard_days_in_seven_fire_even_when_not_adjacent():
    (f,) = _stack(_days([AS_OF - 6 * D, AS_OF - 3 * D, AS_OF]))
    assert f.template_id == "hard-day-stacking-window" and f.number == 3.0


def test_three_hard_days_spread_over_eight_are_silent():
    assert _stack(_days([AS_OF - 7 * D, AS_OF - 3 * D, AS_OF])) == []


def test_a_long_chain_reports_only_its_start():
    facts = _stack(_days([AS_OF - 2 * D, AS_OF - D, AS_OF]))
    assert [f.period for f in facts] == [(AS_OF - D).isoformat()]


def test_stacking_key_is_stable_across_days():
    a = _stack(_days([AS_OF - D, AS_OF]))[0]
    nxt = snapshot(as_of=AS_OF + D, days=day_classes(START, AS_OF + D, hard={AS_OF - D, AS_OF}), history_start=START)
    b = _stack(nxt)[0]
    assert a.insight_key == b.insight_key


def _mono(loads_last7, prior_daily=50.0, history_days=40):
    start = AS_OF - (history_days - 1) * D
    loads = {AS_OF - (6 - i) * D: v for i, v in enumerate(loads_last7)}
    return snapshot(days=day_classes(start, AS_OF, load=prior_daily, loads=loads), history_start=start)


def test_monotony_fires_when_uniform_and_weekly_load_at_or_above_average():
    (f,) = hard_day_stacking(_mono([50.0] * 7), th(), [])  # SD 0 -> capped at 10
    assert f.template_id == "hard-day-stacking-monotony" and f.number == 10.0
    assert f.insight_key == "hard-day-stacking:week/2026-W44:2026-W44"


def test_monotony_value_and_threshold():
    # mean 42.86, population SD 17.49 -> 2.45; weekly load 300 equals the 4-week average of 300
    snap = _mono([50, 50, 50, 50, 50, 50, 0], prior_daily=300 / 7)
    (f,) = hard_day_stacking(snap, th(), [])
    assert f.number == pytest.approx(2.4, abs=0.05)
    varied = _mono([100, 0, 100, 0, 100, 0, 100], prior_daily=300 / 7)
    assert hard_day_stacking(varied, th(), []) == []  # monotony ~1.2


def test_monotony_suppressed_when_weekly_load_is_below_the_four_week_average():
    assert hard_day_stacking(_mono([50, 50, 50, 50, 50, 50, 0], prior_daily=50.0), th(), []) == []  # 300 < 337.5


def test_monotony_needs_four_weeks_of_history():
    assert hard_day_stacking(_mono([50.0] * 7, history_days=20), th(), []) == []


# ---- no-rest-day ----

def _nr(streak, last6=10.0, earlier=20.0, history_days=40, **ov):
    start = AS_OF - (history_days - 1) * D
    rest = {AS_OF - streak * D} if streak < history_days else set()
    loads = {AS_OF - k * D: last6 for k in range(6)}
    snap = snapshot(days=day_classes(start, AS_OF, rest=rest, load=earlier, loads=loads), history_start=start)
    return no_rest_day(snap, th(ov or None), [])


def test_six_days_without_rest_fires_with_episode_start_key():
    (f,) = _nr(6)
    assert f.insight_key == f"no-rest-day:athlete:{(AS_OF - 5 * D).isoformat()}"
    assert f.number == 6.0 and f.unit == "days" and f.kind == "observation"


def test_five_days_without_rest_is_silent_and_longer_streaks_keep_the_start():
    assert _nr(5) == []
    (f,) = _nr(9)
    assert f.number == 9.0 and f.period == (AS_OF - 8 * D).isoformat()


def test_no_rest_day_volume_gate_edges():
    # usual weekly load = (6*10 + 21*20) / 4 = 120; half of that is exactly the last six days' load
    assert len(_nr(6, last6=10.0, earlier=20.0)) == 1
    assert _nr(6, last6=10.0, earlier=20.5) == []
    assert len(_nr(6, last6=10.0, earlier=19.0)) == 1


def test_no_rest_day_without_four_weeks_of_history_skips_the_gate():
    (f,) = _nr(6, history_days=14)
    assert "skipped" in f.evidence["data"]["volume_gate"]


def test_no_rest_day_can_be_turned_off():
    assert _nr(8, **{"no-rest-day": {"enabled": False}}) == []


# ---- training-state ----

def _ts(state, since=date(2026, 10, 12), ramp=4.2, raw=None):
    return TrainingStateDay(AS_OF, raw or state, state, since, ramp, -12.0)


def test_training_state_fact_keyed_on_episode_start():
    (f,) = training_state(snapshot(training_state=_ts("Building")), th(), [])
    assert f.insight_key == "training-state:athlete:2026-10-12"
    assert (f.template_id, f.number, f.unit, f.kind) == ("training-state-building", 4.2, "%", "observation")
    assert f.evidence["data"]["state"] == "Building"


@pytest.mark.parametrize("state", ["Building", "Holding", "Easing", "Overreaching"])
def test_training_state_has_a_template_per_state(state):
    (f,) = training_state(snapshot(training_state=_ts(state)), th(), [])
    assert f.template_id == f"training-state-{state.lower()}"


def test_training_state_silent_without_a_confirmed_state():
    assert training_state(snapshot(training_state=None), th(), []) == []
    assert training_state(snapshot(training_state=TrainingStateDay(AS_OF, None, None, None, None, None)), th(), []) == []
    assert training_state(snapshot(training_state=_ts("Building")), th({"training-state": {"enabled": False}}), []) == []
