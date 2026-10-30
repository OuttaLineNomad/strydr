import numpy as np
import pytest

from strydr.pipeline.derive.routes import (
    build_path, detect_climbs, fixed_splits, hr_claim_allowed, hr_from_workout, load_thresholds,
    make_section_id, measure_run, route_climbs, section_avg_hr, split_unit_m,
)
from strydr.sources.canonical import SampleSeries
from synth import line, make_workout, with_spur

TH = load_thresholds()


def test_section_id_grammar():
    assert make_section_id("abc123", "c", 2) == "abc123/c2"
    assert make_section_id("abc123", "s", 1) == "abc123/s1"
    with pytest.raises(ValueError):
        make_section_id("abc123", "x", 1)


def test_fixed_splits_ids_and_bounds():
    secs = fixed_splits("k", 3000.0, 1000.0, TH)
    assert [s.section_id for s in secs] == ["k/s1", "k/s2", "k/s3"]
    assert [(s.start_m, s.end_m) for s in secs] == [(0, 1000), (1000, 2000), (2000, 3000)]


def test_fixed_splits_tail_is_kept_or_merged():
    assert [s.length_m for s in fixed_splits("k", 2600.0, 1000.0, TH)][-1] == 600.0
    merged = fixed_splits("k", 2400.0, 1000.0, TH)
    assert len(merged) == 2 and merged[-1].end_m == 2400.0
    assert len(fixed_splits("k", 700.0, 1000.0, TH)) == 1


def test_imperial_splits_use_a_mile():
    assert split_unit_m("imperial", TH) == pytest.approx(1609.344)
    assert split_unit_m("metric", TH) == 1000.0
    assert len(fixed_splits("k", 5000.0, split_unit_m("imperial", TH), TH)) == 3


def ramp(cum, flat=500.0, rise=600.0, grade=0.05):
    out = np.zeros(len(cum))
    out[:] = np.clip(cum - flat, 0, rise) * grade
    return out


def profile(fn, length=2000.0, step=10.0):
    cum = np.arange(0, length + step, step)
    return cum, fn(cum)


def test_detects_a_real_climb_and_numbers_it():
    cum, alt = profile(lambda c: ramp(c) + 0.4 * np.sin(c / 7.0))
    climbs = detect_climbs("k", cum, alt, TH)
    assert [c.section_id for c in climbs] == ["k/c1"]
    c = climbs[0]
    assert c.kind == "c" and c.index == 1
    assert abs(c.start_m - 500) < 70 and abs(c.end_m - 1100) < 70
    assert 25 < c.gain_m < 32 and c.length_m >= 300


def test_rejects_short_shallow_and_small_climbs():
    cum = np.arange(0, 3001.0, 10.0)
    alt = np.zeros(len(cum))
    alt += np.clip(cum - 300, 0, 200) * 0.08   # 200 m at 8%: too short
    alt += np.clip(cum - 1000, 0, 600) * 0.02  # 600 m at 2%: too shallow, 12 m gain
    alt += np.clip(cum - 2000, 0, 200) * 0.0   # nothing
    assert detect_climbs("k", cum, alt, TH) == []


def _piecewise(points, length=3000.0):
    xs, ys = zip(*points)
    cum = np.arange(0, length + 1, 10.0)
    return cum, np.interp(cum, xs, ys)


def test_climbs_split_by_a_short_dip_merge_into_one():
    # 24 m up, a 4 m / 30 m dip, 24 m more: one climb; a separate climb later is its own
    cum, alt = _piecewise([(0, 0), (300, 0), (700, 24), (730, 20), (1140, 40), (2000, 40), (2400, 64), (3000, 64)])
    climbs = detect_climbs("k", cum, alt, TH)
    assert [c.section_id for c in climbs] == ["k/c1", "k/c2"]
    assert climbs[0].start_m < 400 and climbs[0].end_m > 1100


def test_climbs_separated_by_a_long_flat_stay_separate():
    cum, alt = _piecewise([(0, 0), (300, 0), (700, 24), (900, 24), (1300, 48), (3000, 48)])
    assert [c.section_id for c in detect_climbs("k", cum, alt, TH)] == ["k/c1", "k/c2"]


def test_missing_altitude_gives_no_climbs():
    cum = np.arange(0, 2000.0, 10.0)
    assert detect_climbs("k", cum, np.full(len(cum), np.nan), TH) == []


def test_route_climbs_on_reference_run():
    w = make_workout("a", 1, line(2000.0), alt=lambda c: float(ramp(np.array([c]))[0]))
    ref = build_path(w, TH)
    assert [c.section_id for c in route_climbs("a", ref, TH)] == ["a/c1"]


def test_hr_claim_needs_three_minutes_median():
    assert hr_claim_allowed([200, 210, 190], TH)
    assert not hr_claim_allowed([179, 170, 400], TH)
    assert hr_claim_allowed([180], TH)
    assert not hr_claim_allowed([], TH)


def test_section_avg_hr_is_lagged_and_time_weighted():
    t = [0, 60, 120, 180, 240, 300]
    hr = [100, 110, 120, 130, 140, 150]
    # window [0, 120] shifted 30 s -> [30, 150]: 30 s of 100, 60 s of 110, 30 s of 120
    assert section_avg_hr(t, hr, 0, 120, TH) == pytest.approx((30 * 100 + 60 * 110 + 30 * 120) / 120)
    assert section_avg_hr(t, hr, 0, 60, TH) is None  # only 2 samples overlap
    assert section_avg_hr([], [], 0, 600, TH) is None


def run_on(wid, day, speed, **kw):
    return build_path(make_workout(wid, day, line(3000.0), speed=speed, **kw), TH)


def test_measure_run_times_and_hr_by_geography():
    ref = run_on("a", 1, 3.0)
    secs = fixed_splits("a", ref.length_m, 1000.0, TH)
    w = make_workout("b", 2, line(3000.0), speed=4.0, hr_bpm=150.0)
    out = measure_run(ref, build_path(w, TH), secs, hr_from_workout(w), TH)
    assert out["a/s1"].comparable and out["a/s1"].time_s == pytest.approx(250.0, abs=2)
    assert out["a/s1"].avg_hr == pytest.approx(150.0)
    assert [out[s.section_id].time_s for s in secs] == pytest.approx([250.0] * 3, abs=3)


def test_measure_run_marks_detour_section_not_comparable():
    ref = run_on("a", 1, 3.0)
    secs = fixed_splits("a", ref.length_m, 1000.0, TH)
    base = line(3000.0)
    detour = with_spur(base, at=500, length=120.0, direction=(0.0, 1.0))  # in split 2 (x = 1500)
    w = make_workout("b", 2, detour, speed=3.0)
    out = measure_run(ref, build_path(w, TH), secs, None, TH)
    assert out["a/s1"].comparable and out["a/s3"].comparable
    assert not out["a/s2"].comparable and out["a/s2"].reason == "detour"


def test_measure_run_marks_pause_and_short_run():
    ref = run_on("a", 1, 3.0)
    secs = fixed_splits("a", ref.length_m, 1000.0, TH)
    # a 60 s stop at 1500 m: repeat one point for 60 s worth of fixes
    xy = np.vstack([line(1500.0), np.tile(line(1500.0)[-1], (60, 1)), line(3000.0)[501:]])
    w = make_workout("p", 2, xy, speed=3.0)
    # make_workout times by distance; give the stop real time
    t = np.array(w.series["route"].columns["t"])
    t[501:] += 60.0
    t[501:561] = np.arange(1, 61) + t[500]
    w.series["route"].columns["t"] = t.tolist()
    out = measure_run(ref, build_path(w, TH), secs, None, TH)
    assert out["a/s2"].reason == "pause" and not out["a/s2"].comparable
    short = make_workout("s", 3, line(1800.0), speed=3.0)
    out = measure_run(ref, build_path(short, TH), secs, None, TH)
    assert out["a/s1"].comparable and out["a/s3"].reason == "boundary not reached"



def _watch_paused_run(pause_s: float):
    """A watch-recorded pause of `pause_s` at 1500 m. Like Apple's GPX, no fixes are written while paused: wall-clock
    `t` jumps and the active clock `at` runs on. Heart rate (10 s samples, offset from the pause edges) reads 100 bpm
    while paused and 150 bpm while running."""
    w = make_workout("p", 2, line(3000.0), speed=3.0)
    t = np.array(w.series["route"].columns["t"])
    at = t.copy()
    t[501:] += pause_s
    w.series["route"].columns["t"], w.series["route"].columns["at"] = t.tolist(), at.tolist()
    pause0, pause1 = float(at[500]), float(at[500]) + pause_s
    ht = np.arange(3.0, float(t[-1]) + 10.0, 10.0)
    hat = np.where(ht < pause0, ht, np.where(ht < pause1, pause0, ht - pause_s))
    w.series["heart_rate"] = SampleSeries("heart_rate", {
        "t": ht.tolist(), "at": hat.tolist(), "avg": [100.0 if pause0 <= x < pause1 else 150.0 for x in ht],
        "min": [0.0] * len(ht), "max": [0.0] * len(ht)})
    return w


def test_a_short_watch_pause_adds_no_section_time_and_little_hr():
    ref = run_on("a", 1, 3.0)
    secs = fixed_splits("a", ref.length_m, 1000.0, TH)
    w = _watch_paused_run(20.0)
    out = measure_run(ref, build_path(w, TH), secs, hr_from_workout(w), TH)
    s2 = out["a/s2"]
    assert s2.comparable and s2.time_s == pytest.approx(1000.0 / 3.0, abs=3)  # running time only
    assert s2.avg_hr == pytest.approx(150.0, abs=3)  # paused readings take at most one sample step


def test_a_long_watch_pause_still_marks_the_section_paused():
    ref = run_on("a", 1, 3.0)
    secs = fixed_splits("a", ref.length_m, 1000.0, TH)
    out = measure_run(ref, build_path(_watch_paused_run(300.0), TH), secs, None, TH)
    assert out["a/s2"].reason == "pause" and not out["a/s2"].comparable
    assert out["a/s1"].comparable and out["a/s3"].comparable


def test_a_paused_run_is_still_eligible_for_routes():
    w = _watch_paused_run(360.0)  # a 6 minute pause in a ~17 minute run: under 80% coverage on the wall clock
    p = build_path(w, TH)
    assert p is not None and p.t[-1] < p.wall_t[-1]


def test_without_an_active_clock_the_wall_clock_is_used():
    w = _watch_paused_run(360.0)
    for name in ("route", "heart_rate"):
        del w.series[name].columns["at"]
    assert build_path(w, TH) is None  # the 6 minute hole reads as a GPS gap
