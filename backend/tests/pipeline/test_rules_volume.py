"""Rules: long-run-spike, weekly-ramp, attaboys-streaks."""
from datetime import date, timedelta

from insight_synth import AS_OF, run, snapshot, th, weekly

from strydr.pipeline.insights.keys import make_fact
from strydr.pipeline.insights.models import BestEffort
from strydr.pipeline.insights.rules.attaboys_streaks import attaboys_streaks
from strydr.pipeline.insights.rules.long_run_spike import long_run_spike
from strydr.pipeline.insights.rules.weekly_ramp import weekly_ramp

D = timedelta(days=1)
MONDAY = date(2026, 10, 26)


# ---- long-run-spike ----

def _lrs(new_km, old_km=10.0, old_days_ago=20, **kw):
    runs = (run("old", AS_OF - old_days_ago * D, old_km), run("new", AS_OF - D, new_km))
    return long_run_spike(snapshot(runs=runs, **kw), th(), [])


def test_long_run_spike_fires_above_ten_percent():
    (f,) = _lrs(11.5)
    assert f.insight_key == f"long-run-spike:run/new:{(AS_OF - D).isoformat()}"
    assert (f.kind, f.number, f.unit, f.template_id) == ("observation", 15.0, "%", "long-run-spike")
    assert f.evidence["rule"] == "long-run-spike" and f.evidence["data"]["longest_prior_m"] == 10000 and f.evidence["note"]


def test_long_run_spike_silent_at_exactly_ten_percent_and_below():
    assert _lrs(11.0) == []
    assert _lrs(10.9) == []
    assert _lrs(8.0) == []


def test_long_run_spike_just_over_threshold_fires():
    assert len(_lrs(11.01)) == 1


def test_long_run_spike_only_looks_back_30_days():
    assert _lrs(15.0, old_days_ago=32) == []  # nothing in the window to compare against
    assert len(_lrs(15.0, old_days_ago=31)) == 1


def test_long_run_spike_needs_prior_run_and_ignores_runs_outside_lookback():
    assert long_run_spike(snapshot(runs=(run("only", AS_OF - D, 30.0),)), th(), []) == []
    old_spike = (run("a", AS_OF - 60 * D, 5.0), run("b", AS_OF - 40 * D, 9.0))
    assert long_run_spike(snapshot(runs=old_spike), th(), []) == []  # spike is older than the evaluation window


def test_long_run_spike_threshold_is_configurable():
    runs = (run("old", AS_OF - 5 * D, 10.0), run("new", AS_OF - D, 10.6))
    assert long_run_spike(snapshot(runs=runs), th(), []) == []
    assert len(long_run_spike(snapshot(runs=runs), th({"long-run-spike": {"jump_pct": 5.0}}), [])) == 1


# ---- weekly-ramp ----

def _weeks(this_km, prior_km=(20,) * 8, start_hist=None):
    specs = [(MONDAY, this_km, 3)] + [(MONDAY - timedelta(weeks=k + 1), v, 3) for k, v in enumerate(prior_km)]
    return snapshot(weekly=weekly(*specs), history_start=start_hist or MONDAY - timedelta(weeks=12))


def test_weekly_ramp_fires_above_thirty_percent():
    (f,) = weekly_ramp(_weeks(27.0), th(), [])
    assert f.insight_key == "weekly-ramp:week/2026-W44:2026-W44"
    assert f.number == 35.0 and f.unit == "%" and f.kind == "observation"
    assert f.evidence["data"]["week_to_date"] is True


def test_weekly_ramp_silent_at_exactly_thirty_percent():
    assert weekly_ramp(_weeks(26.0), th(), []) == []
    assert weekly_ramp(_weeks(20.0), th(), []) == []


def test_weekly_ramp_needs_four_weeks_of_history_and_nonzero_average():
    assert weekly_ramp(_weeks(40.0, start_hist=MONDAY - timedelta(weeks=3)), th(), []) == []
    assert weekly_ramp(_weeks(40.0, prior_km=(0,) * 8), th(), []) == []
    assert weekly_ramp(snapshot(history_start=None), th(), []) == []


def test_weekly_ramp_missing_weeks_count_as_zero():
    # only two of the four prior weeks have runs: average is 10 km
    snap = snapshot(weekly=weekly((MONDAY, 14.0, 3), (MONDAY - timedelta(weeks=1), 20, 3), (MONDAY - timedelta(weeks=2), 20, 3)),
                    history_start=MONDAY - timedelta(weeks=8))
    facts = {f.subject: f for f in weekly_ramp(snap, th(), [])}
    assert facts["week/2026-W44"].number == 40.0


def test_weekly_ramp_also_reports_a_completed_week_in_the_lookback_window():
    last = MONDAY - timedelta(weeks=1)
    specs = [(last, 30.0, 4)] + [(last - timedelta(weeks=k), 20.0, 3) for k in range(1, 10)] + [(MONDAY, 2.0, 1)]
    facts = weekly_ramp(snapshot(weekly=weekly(*specs), history_start=last - timedelta(weeks=8)), th(), [])
    assert [f.subject for f in facts] == ["week/2026-W43"]


# ---- attaboys-streaks: run events ----

def _be(wid="new", record=True, gps=True, label="5k", d=None):
    return BestEffort(wid, d or AS_OF - D, label, 5000.0, 1500.0, record, gps)


def test_best_effort_attaboy_fires_for_record_with_good_gps():
    snap = snapshot(runs=(run("new", AS_OF - D),), best_efforts=(_be(),))
    (f,) = attaboys_streaks(snap, th(), [])
    assert f.kind == "attaboy" and f.template_id == "attaboys-streaks-best-effort"
    assert (f.number, f.unit) == (1500.0, "s")
    assert f.insight_key == f"attaboys-streaks:run/new:{(AS_OF - D).isoformat()}"


def test_best_effort_silent_without_record_or_with_bad_gps():
    for be in (_be(record=False), _be(gps=False), _be(wid="someone-else")):
        assert attaboys_streaks(snapshot(runs=(run("new", AS_OF - D),), best_efforts=(be,)), th(), []) == []


def _history(n, km, start_days_ago=100):
    return tuple(run(f"h{i}", AS_OF - (start_days_ago - 3 * i) * D, km) for i in range(n))


def test_longest_run_needs_ten_prior_runs_and_a_new_maximum():
    hist = _history(10, 8.0)
    (f,) = attaboys_streaks(snapshot(runs=hist + (run("new", AS_OF - D, 12.0),)), th(), [])
    assert f.template_id == "attaboys-streaks-longest-run" and f.number == 12000
    assert attaboys_streaks(snapshot(runs=hist + (run("new", AS_OF - D, 8.0),)), th(), []) == []  # ties are not records
    assert attaboys_streaks(snapshot(runs=_history(9, 8.0) + (run("new", AS_OF - D, 12.0),)), th(), []) == []


def test_lifetime_milestone_in_runner_units():  # km
    hist = (run("big", AS_OF - 90 * D, 12.0),) + _history(18, 4.5, 80)  # 12 + 81 = 93 km
    snap = snapshot(runs=hist + (run("new", AS_OF - D, 8.0),))  # 101 km
    (f,) = attaboys_streaks(snap, th(), [])
    assert f.template_id == "attaboys-streaks-milestone" and f.number == 100 and f.unit == "km"
    exact = snapshot(runs=hist + (run("new", AS_OF - D, 7.0),))  # exactly 100 km counts as reached
    assert len(attaboys_streaks(exact, th(), [])) == 1
    shorter = snapshot(runs=hist + (run("new", AS_OF - D, 6.9),))
    assert attaboys_streaks(shorter, th(), []) == []


def test_lifetime_milestone_uses_miles_when_the_runner_prefers_miles():
    hist = _history(16, 10.0)  # 160 km = 99.4 mi
    snap = snapshot(units="mi", runs=hist + (run("new", AS_OF - D, 5.0),))  # 165 km = 102.5 mi
    (f,) = attaboys_streaks(snap, th(), [])
    assert (f.number, f.unit) == (100, "mi")


def test_at_most_two_events_ride_along_on_one_run():
    hist = (run("big", AS_OF - 90 * D, 12.0),) + _history(18, 4.5, 80)
    snap = snapshot(runs=hist + (run("new", AS_OF - D, 20.0),), best_efforts=(_be(),))
    (f,) = attaboys_streaks(snap, th(), [])
    assert [e["event"] for e in f.evidence["data"]["events"]] == ["best-effort", "longest-run"]
    assert f.template_id == "attaboys-streaks-best-effort"


def test_no_attaboy_alongside_a_check_reading():
    snap = snapshot(runs=(run("new", AS_OF - D),), best_efforts=(_be(),))
    check = make_fact("resting-hr", "athlete", AS_OF, "check-reading", 120.0, "bpm", {}, "resting-hr-check")
    assert attaboys_streaks(snap, th(), [check]) == []


# ---- attaboys-streaks: record weeks and months ----

def _record_week_snapshot(last_km=40.0, earlier=(20,) * 9, **kw):
    last = MONDAY - timedelta(weeks=1)
    specs = [(last, last_km, 4)] + [(last - timedelta(weeks=k + 1), v, 3) for k, v in enumerate(earlier)]
    return snapshot(weekly=weekly(*specs), history_start=last - timedelta(weeks=len(earlier)), **kw)


def _kinds(facts):
    return [f.template_id for f in facts]


def test_record_week_fires_for_a_completed_week_with_enough_history():
    facts = attaboys_streaks(_record_week_snapshot(), th(), [])
    assert "attaboys-streaks-record-week" in _kinds(facts)
    f = [f for f in facts if f.template_id == "attaboys-streaks-record-week"][0]
    assert f.subject == "week/2026-W43" and f.period == "2026-W43" and f.number == 40000


def test_record_week_silent_when_tied_or_short_history():
    assert "attaboys-streaks-record-week" not in _kinds(attaboys_streaks(_record_week_snapshot(last_km=20.0), th(), []))
    assert "attaboys-streaks-record-week" not in _kinds(attaboys_streaks(_record_week_snapshot(earlier=(20,) * 7), th(), []))


def test_record_week_is_held_back_when_a_ramp_fired_that_week():
    ramp = make_fact("weekly-ramp", "week/2026-W43", "2026-W43", "observation", 100.0, "%", {}, "weekly-ramp")
    assert "attaboys-streaks-record-week" not in _kinds(attaboys_streaks(_record_week_snapshot(), th(), [ramp]))
    other = make_fact("weekly-ramp", "week/2026-W44", "2026-W44", "observation", 100.0, "%", {}, "weekly-ramp")
    assert "attaboys-streaks-record-week" in _kinds(attaboys_streaks(_record_week_snapshot(), th(), [other]))


def test_record_month_fires_for_a_completed_month():
    from strydr.pipeline.insights.models import PeriodVolume

    months = tuple(
        PeriodVolume(f"2026-{m:02d}", date(2026, m, 1), date(2026, m, 28), v * 1000, 0, 10)
        for m, v in ((5, 80), (6, 90), (7, 85), (8, 70), (9, 120))
    )
    snap = snapshot(as_of=date(2026, 10, 5), monthly=months)
    (f,) = [f for f in attaboys_streaks(snap, th(), []) if f.template_id == "attaboys-streaks-record-month"]
    assert f.subject == "athlete" and f.period == "2026-09-01" and f.number == 120000
    lower = snapshot(as_of=date(2026, 10, 5), monthly=months[:-1] + (PeriodVolume("2026-09", date(2026, 9, 1), date(2026, 9, 30), 85000, 0, 9),))
    assert not [f for f in attaboys_streaks(lower, th(), []) if f.template_id == "attaboys-streaks-record-month"]


# ---- attaboys-streaks: weekly streaks ----

def _streak_snapshot(counts, last_monday=MONDAY - timedelta(weeks=1), current=None):
    """counts: run counts for consecutive weeks ending at last_monday (oldest first)."""
    first = last_monday - timedelta(weeks=len(counts) - 1)
    specs = [(first + timedelta(weeks=i), 10.0, n) for i, n in enumerate(counts)]
    if current is not None:
        specs.append((MONDAY, 5.0, current))
    return snapshot(weekly=weekly(*specs), history_start=first)


def _streak_facts(snap, overrides=None):
    return [f for f in attaboys_streaks(snap, th(overrides), []) if f.template_id == "attaboys-streaks-streak"]


def test_four_week_streak_fires_on_the_week_it_is_reached():
    (f,) = _streak_facts(_streak_snapshot([3, 3, 3, 3]))
    assert (f.number, f.unit, f.subject) == (4.0, "weeks", "athlete")
    assert f.period == (MONDAY - timedelta(weeks=1)).isoformat()


def test_three_week_streak_is_silent_and_two_run_weeks_do_not_count():
    assert _streak_facts(_streak_snapshot([3, 3, 3])) == []
    assert _streak_facts(_streak_snapshot([3, 3, 2, 3])) == []  # one miss is forgiven but the streak is only 3 long


def test_one_missed_week_is_forgiven_and_the_streak_continues():
    # 3 good, 1 miss (forgiven), 1 good -> 4 qualifying weeks
    (f,) = _streak_facts(_streak_snapshot([3, 3, 3, 1, 3]))
    assert f.number == 4.0 and f.evidence["data"]["forgiven_week_in_streak"] is True


def test_second_miss_inside_twelve_weeks_resets_the_streak():
    snap = _streak_snapshot([3, 3, 3, 1, 3, 3, 3, 3, 1, 3, 3, 3])
    # streak reaches 4 early (outside the window); after the second miss it restarts and never reaches 4 again
    assert _streak_facts(snap) == []


def test_a_miss_far_enough_after_the_last_is_forgiven_again():
    counts = [3, 3, 3, 1, 3, 3, 3, 1, 3, 3]  # second miss is 4 weeks after the first
    assert _streak_facts(_streak_snapshot(counts)) == []  # default: one in 12, so the second miss resets
    (f,) = _streak_facts(_streak_snapshot(counts), {"attaboys-streaks": {"forgive_one_per_weeks": 4}})
    assert f.number == 8.0


def test_current_incomplete_week_neither_breaks_nor_counts_unless_qualifying():
    assert _streak_facts(_streak_snapshot([3, 3, 3], current=1)) == []  # in progress, streak is 3
    (f,) = _streak_facts(_streak_snapshot([3, 3, 3], current=3))
    assert f.number == 4.0 and f.period == MONDAY.isoformat()


def test_no_daily_streak_facts_exist():
    snap = _streak_snapshot([1, 1, 1, 1, 1, 1])
    assert _streak_facts(snap) == []


def test_streak_milestone_outside_lookback_is_not_reported_again():
    counts = [3] * 12  # 4 and 8 were reached long ago; 12 is reached in the last completed week
    (f,) = _streak_facts(_streak_snapshot(counts))
    assert f.number == 12.0
