"""Rules: intensity-mix (80/20), easy-creep, cardiac-drift."""
from datetime import timedelta

import pytest
from insight_synth import AS_OF, minutes, run, snapshot, th

from strydr.pipeline.insights.keys import make_fact
from strydr.pipeline.insights.rules.cardiac_drift import cardiac_drift
from strydr.pipeline.insights.rules.intensity import easy_creep, intensity_mix

D = timedelta(days=1)


# ---- intensity-mix ----

def _mix_runs(n, easy_share, hr_time=3000.0, **kw):
    return tuple(
        run(f"r{i}", AS_OF - (2 + 3 * i) * D, hr_time_s=hr_time, easy_time_s=hr_time * easy_share, **kw) for i in range(n)
    )


def test_intensity_mix_fires_below_seventy_percent_easy():
    (f,) = intensity_mix(snapshot(runs=_mix_runs(8, 0.5)), th(), [])
    assert f.insight_key == "intensity-mix:week/2026-W44:2026-W44"
    assert (f.number, f.unit, f.kind) == (50.0, "%", "observation")
    assert f.evidence["data"]["runs"] == 8


def test_intensity_mix_silent_at_exactly_seventy_and_above():
    assert intensity_mix(snapshot(runs=_mix_runs(8, 0.7)), th(), []) == []
    assert intensity_mix(snapshot(runs=_mix_runs(8, 0.8)), th(), []) == []
    assert len(intensity_mix(snapshot(runs=_mix_runs(8, 0.69)), th(), [])) == 1


def test_intensity_mix_needs_eight_runs_with_hr_inside_28_days():
    assert intensity_mix(snapshot(runs=_mix_runs(7, 0.5)), th(), []) == []
    old = tuple(run(f"o{i}", AS_OF - (29 + i) * D, hr_time_s=3000.0, easy_time_s=1000.0) for i in range(8))
    assert intensity_mix(snapshot(runs=old), th(), []) == []
    thin = _mix_runs(8, 0.5, hr_coverage=0.7)
    assert intensity_mix(snapshot(runs=thin), th(), []) == []


# ---- easy-creep ----

def _easy(i, hr, speed=3.0, days_ago=None, **kw):
    return run(f"e{i}", AS_OF - (days_ago if days_ago is not None else 1 + 2 * i) * D, is_easy_intended=True, avg_hr=hr,
               avg_speed_mps=speed, **kw)


def test_easy_creep_fires_when_two_of_five_easy_runs_exceed_the_ceiling():
    runs = tuple(_easy(i, 155.0 if i < 2 else 140.0) for i in range(5))  # 40% over the 152 ceiling
    (f,) = easy_creep(snapshot(runs=runs), th(), [])
    assert f.template_id == "easy-creep-ceiling" and f.number == 40.0 and f.insight_key == "easy-creep:week/2026-W44:2026-W44"


def test_easy_creep_silent_below_forty_percent_or_with_fewer_than_four_runs():
    runs = tuple(_easy(i, 155.0 if i < 1 else 140.0) for i in range(5))  # 20%
    assert easy_creep(snapshot(runs=runs), th(), []) == []
    assert easy_creep(snapshot(runs=tuple(_easy(i, 160.0) for i in range(3))), th(), []) == []
    at_ceiling = tuple(_easy(i, 152.0) for i in range(5))  # at (not over) the ceiling
    assert easy_creep(snapshot(runs=at_ceiling), th(), []) == []


def test_easy_creep_ignores_runs_that_are_not_easy_intended_or_lack_hr_coverage():
    runs = tuple(_easy(i, 160.0, hr_coverage=0.5) for i in range(5))
    assert easy_creep(snapshot(runs=runs), th(), []) == []
    runs = tuple(run(f"x{i}", AS_OF - (1 + i) * D, avg_hr=160.0) for i in range(5))
    assert easy_creep(snapshot(runs=runs), th(), []) == []


def _creep_pair(recent_speed, recent_hr, old_hr=146.0, old_speed=3.0):
    recent = tuple(_easy(i, recent_hr, recent_speed) for i in range(4))
    old = tuple(_easy(10 + i, old_hr, old_speed, days_ago=20 + 5 * i) for i in range(4))
    return snapshot(runs=recent + old)


def test_easy_creep_by_pace_needs_both_faster_pace_and_higher_hr():
    (f,) = easy_creep(_creep_pair(3.15, 150.0), th(), [])  # +5.0% speed, +4 bpm, still under the ceiling
    assert f.template_id == "easy-creep-pace" and f.number == 5.0
    assert f.evidence["data"]["hr_higher_bpm"] == 4.0


def test_easy_creep_by_pace_edges():
    assert easy_creep(_creep_pair(3.14, 150.0), th(), []) == []  # 4.7% faster
    assert easy_creep(_creep_pair(3.2, 148.0), th(), []) == []  # HR only +2: fitness, not creep
    assert len(easy_creep(_creep_pair(3.2, 149.0), th(), [])) == 1  # HR exactly +3
    assert easy_creep(_creep_pair(3.2, 143.0), th(), []) == []  # faster at lower HR


# ---- cardiac-drift ----

def _drift_run(hr2, dur=60, temp=None, wid="d1", **kw):
    n = dur
    return run(wid, AS_OF - D, 10.0, dur, temperature_c=temp, minutes=minutes(n, hr=140.0, hr2=hr2, split=(n + 10) // 2), **kw)


def _drift(r, prior=None):
    return cardiac_drift(snapshot(runs=(r,)), th(), prior or [])


def test_drift_notable_between_five_and_ten_percent():
    (f,) = _drift(_drift_run(148.0))  # 1 - 140/148 = 5.4%
    assert f.kind == "observation" and f.template_id == "cardiac-drift-notable"
    assert f.number == pytest.approx(5.4) and f.unit == "%"
    assert f.insight_key == f"cardiac-drift:run/d1:{(AS_OF - D).isoformat()}"
    assert f.evidence["data"]["heat_affected"] is False and f.evidence["note"]


def test_drift_high_above_ten_percent():
    (f,) = _drift(_drift_run(156.0))  # 10.3%
    assert f.template_id == "cardiac-drift-high" and f.kind == "observation"


def test_drift_edges_exactly_five_and_ten_are_not_above():
    assert _drift(_drift_run(140.0 / 0.95)) == []  # exactly 5%: not notable, not under 5 either
    (f,) = _drift(_drift_run(140.0 / 0.90))  # exactly 10%: notable, not high
    assert f.template_id == "cardiac-drift-notable"


def test_drift_under_five_percent_is_an_attaboy_only_on_runs_of_sixty_minutes_or_more():
    (f,) = _drift(_drift_run(145.0))  # 3.4%
    assert f.kind == "attaboy" and f.template_id == "cardiac-drift-solid"
    assert _drift(_drift_run(145.0, dur=59)) == []
    assert len(_drift(_drift_run(145.0, dur=60))) == 1


def test_drift_attaboy_held_back_by_a_check_reading_but_observations_still_fire():
    check = make_fact("resting-hr", "athlete", AS_OF, "check-reading", 120.0, "bpm", {}, "resting-hr-check")
    assert _drift(_drift_run(145.0), [check]) == []
    assert len(_drift(_drift_run(156.0), [check])) == 1


def test_drift_needs_forty_minutes_total():
    assert _drift(_drift_run(160.0, dur=39)) == []
    assert len(_drift(_drift_run(160.0, dur=40))) == 1


def test_drift_heat_tagging_at_24_degrees():
    (hot,) = _drift(_drift_run(156.0, temp=24.0))
    assert hot.template_id == "cardiac-drift-high-heat"
    assert hot.evidence["data"]["heat_affected"] is True and hot.evidence["data"]["in_trend"] is False
    (cool,) = _drift(_drift_run(156.0, temp=23.9))
    assert cool.template_id == "cardiac-drift-high" and cool.evidence["data"]["in_trend"] is True
    (unknown,) = _drift(_drift_run(148.0, temp=None))  # no weather: no tag, heat caveat stays in wording
    assert unknown.evidence["data"]["temperature_c"] is None and unknown.evidence["data"]["heat_affected"] is False


def test_drift_requires_hr_coverage_of_ninety_percent():
    base = _drift_run(156.0)
    gappy = tuple(m if i % 5 else type(m)(None, m.speed_mps, m.altitude_m) for i, m in enumerate(base.minutes))  # 20% missing
    assert _drift(run("g", AS_OF - D, 10.0, 60, minutes=gappy)) == []
    ok = tuple(m if i % 20 else type(m)(None, m.speed_mps, m.altitude_m) for i, m in enumerate(base.minutes))  # 5% missing
    assert len(_drift(run("g", AS_OF - D, 10.0, 60, minutes=ok))) == 1


def test_drift_requires_steady_pace():
    wobble = tuple(type(m)(m.hr, 2.0 if i % 2 else 4.0, m.altitude_m) for i, m in enumerate(_drift_run(156.0).minutes))
    assert _drift(run("w", AS_OF - D, 10.0, 60, minutes=wobble)) == []


def test_drift_requires_aerobic_intensity():
    hard = minutes(60, hr=165.0, hr2=180.0, split=35)  # mean HR above the 152 ceiling
    assert _drift(run("h", AS_OF - D, 10.0, 60, minutes=hard)) == []


def test_drift_hill_gate():
    climbing = minutes(60, hr=140.0, hr2=156.0, split=35, alt_slope=3.0)  # ~16 m/km of climbing
    assert _drift(run("c", AS_OF - D, 10.0, 60, minutes=climbing)) == []
    gentle = minutes(60, hr=140.0, hr2=156.0, split=35, alt_slope=0.3)
    assert len(_drift(run("c", AS_OF - D, 10.0, 60, minutes=gentle))) == 1


def test_drift_skips_runs_without_a_minute_series_and_old_runs():
    assert _drift(run("n", AS_OF - D, 10.0, 60, minutes=None)) == []
    old = run("o", AS_OF - 30 * D, 10.0, 60, minutes=minutes(60, hr=140.0, hr2=156.0, split=35))
    assert _drift(old) == []
