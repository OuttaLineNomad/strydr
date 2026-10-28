"""Tier-2 conditions rules: heat-adjusted-pace, hill-adjusted-pace, pace-by-conditions."""
from datetime import timedelta

import pytest
from insight_synth import AS_OF, run, snapshot, th

from strydr.pipeline.insights.engine import run_rules
from strydr.pipeline.insights.templates import render


def _cond(dew, adj, band="warm"):
    return {"temp_c": 27.0, "dew_point_c": dew, "temp_dew_sum_f": 140, "heat_adjust_pct": adj, "band": band}


def test_heat_adjusted_pace_fires_on_a_humid_run_and_renders():
    r = run("hot", AS_OF, 3.2, 30.0, conditions=_cond(21.0, 3.0))
    facts = [f for f in run_rules(snapshot(runs=(r,)), th()) if f.rule_id == "heat-adjusted-pace"]
    assert len(facts) == 1 and facts[0].unit == "s" and facts[0].number > 0
    text = render(facts[0], "mi")
    assert "°F" in text and "associated with" in text and "per mile" in text
    cool = run("cool", AS_OF, 3.2, 30.0, conditions=_cond(8.0, 0.0, "ideal"))
    assert not [f for f in run_rules(snapshot(runs=(cool,)), th()) if f.rule_id == "heat-adjusted-pace"]


def test_hill_adjusted_pace_needs_a_hilly_run():
    gap = {"gap_speed_mps": 2.0, "relief_m": 60.0, "relief_m_per_km": 18.0, "hilly": True}
    r = run("hill", AS_OF, 3.2, 30.0, gap=gap)  # actual 1.78 m/s
    facts = [f for f in run_rules(snapshot(runs=(r,)), th()) if f.rule_id == "hill-adjusted-pace"]
    assert len(facts) == 1 and "climbs" in render(facts[0], "km")
    flat = run("flat", AS_OF, 3.2, 30.0, gap=gap | {"hilly": False})
    assert not [f for f in run_rules(snapshot(runs=(flat,)), th()) if f.rule_id == "hill-adjusted-pace"]


def test_pace_by_conditions_needs_six_runs_each_side():
    def runs(n_warm, n_cool):
        out = []
        for i in range(n_warm):
            out.append(run(f"w{i}", AS_OF - timedelta(days=2 * i), 3.2, 33.0, is_easy_intended=True, conditions=_cond(19.0, 2.0)))
        for i in range(n_cool):
            out.append(run(f"c{i}", AS_OF - timedelta(days=2 * i + 1), 3.2, 30.0, is_easy_intended=True,
                           conditions=_cond(6.0, 0.0, "ideal")))
        return tuple(out)

    facts = [f for f in run_rules(snapshot(runs=runs(6, 6)), th()) if f.rule_id == "pace-by-conditions"]
    assert len(facts) == 1 and facts[0].number == pytest.approx(10.0, abs=0.1)
    assert "slower than your cooler ones" in render(facts[0], "km")
    assert not [f for f in run_rules(snapshot(runs=runs(5, 6)), th()) if f.rule_id == "pace-by-conditions"]




def _sleep(total, usual=7.5, quality="short"):
    return {"total_h": total, "usual_h": usual, "quality": quality, "deep_h": 0.8, "rem_h": 1.2, "awake_h": 0.4}


def test_short_sleep_run_fires_an_hour_under_usual():
    r = run("tired", AS_OF, 3.2, 30.0, sleep=_sleep(5.9))
    facts = [f for f in run_rules(snapshot(runs=(r,)), th()) if f.rule_id == "short-sleep-run"]
    assert len(facts) == 1 and facts[0].number == 5.9
    assert "1 h 36 min under your usual" in render(facts[0], "km")
    ok = run("rested", AS_OF, 3.2, 30.0, sleep=_sleep(7.2, quality="good"))
    assert not [f for f in run_rules(snapshot(runs=(ok,)), th()) if f.rule_id == "short-sleep-run"]


def test_effort_by_sleep_compares_heartbeats_per_km():
    runs = tuple(run(f"s{i}", AS_OF - timedelta(days=2 * i), 3.2, 30.0, is_easy_intended=True, avg_hr=150.0,
                     sleep=_sleep(5.5)) for i in range(5)) + \
        tuple(run(f"g{i}", AS_OF - timedelta(days=2 * i + 1), 3.2, 30.0, is_easy_intended=True, avg_hr=140.0,
                  sleep=_sleep(7.8, quality="good")) for i in range(5))
    facts = [f for f in run_rules(snapshot(runs=runs), th()) if f.rule_id == "effort-by-sleep"]
    assert len(facts) == 1 and facts[0].number == pytest.approx(7.1, abs=0.1)
    assert not [f for f in run_rules(snapshot(runs=runs[1:]), th()) if f.rule_id == "effort-by-sleep"]
