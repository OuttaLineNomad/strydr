from datetime import date, timedelta

import pytest

from strydr.pipeline.derive.routes import (
    SectionMeasure, SectionObs, compare_run, compare_section, load_thresholds, observations,
)

TH = load_thresholds()
AS_OF = date(2026, 10, 26)
SEC = "k/c1"


def hist(times, hr=150.0, section=SEC, days_ago=10, **kw):
    """Past runs, one per time, on consecutive days before the current run."""
    return [
        SectionObs(section, f"h{section}{i}", AS_OF - timedelta(days=days_ago + i), t,
                   hr[i] if isinstance(hr, list) else hr, **kw)
        for i, t in enumerate(times)
    ]


def cur(time_s, hr=150.0, section=SEC, **kw):
    return SectionObs(section, f"cur{section}", AS_OF, time_s, hr, **kw)


def test_returns_inputs_for_the_insight():
    c = compare_section(cur(330.0), hist([297, 300, 303]), AS_OF, TH)
    assert c.n == 3 and c.baseline_time_s == 300.0 and c.gap_s == 30.0
    assert c.spread_s == pytest.approx(1.4826 * 3) and c.direction == "slower"
    assert c.baseline_hr == 150.0 and c.fires and c.reasons == ()


def test_faster_is_reported_with_negative_gap():
    c = compare_section(cur(270.0), hist([297, 300, 303]), AS_OF, TH)
    assert c.gap_s == -30.0 and c.direction == "faster" and c.fires


@pytest.mark.parametrize("n, fires", [(2, False), (3, True), (4, True)])
def test_needs_three_matched_runs(n, fires):
    c = compare_section(cur(340.0), hist([300, 300, 300, 300][:n]), AS_OF, TH)
    assert c.n == n and c.fires is fires


@pytest.mark.parametrize("gap, fires", [(14.9, False), (15.0, True), (15.1, True)])
def test_absolute_gap_floor_15s(gap, fires):
    # baseline 300 s: 5% = 15 s too; zero spread
    assert compare_section(cur(300 + gap), hist([300, 300, 300]), AS_OF, TH).fires is fires


@pytest.mark.parametrize("gap, fires", [(29.9, False), (30.0, True)])
def test_relative_gap_floor_5pct(gap, fires):
    # baseline 600 s: 5% = 30 s beats the 15 s floor
    assert compare_section(cur(600 + gap), hist([600, 600, 600]), AS_OF, TH).fires is fires


@pytest.mark.parametrize("gap, fires", [(37.0, False), (37.2, True)])
def test_small_n_needs_2_5x_spread(gap, fires):
    # n=3, MAD=10 -> spread 14.826; 2.5x = 37.065
    c = compare_section(cur(300 + gap), hist([290, 300, 310]), AS_OF, TH)
    assert c.n == 3 and c.fires is fires


@pytest.mark.parametrize("gap, fires", [(29.6, False), (29.7, True)])
def test_n5_needs_2x_spread(gap, fires):
    # n=5, MAD=10 -> spread 14.826; 2x = 29.652
    c = compare_section(cur(300 + gap), hist([280, 290, 300, 310, 320]), AS_OF, TH)
    assert c.n == 5 and c.fires is fires


def test_n4_still_uses_the_stricter_2_5x():
    # n=4: median 300, MAD 15, spread 22.239; 2x = 44.5 would pass, 2.5x = 55.6 does not
    c = compare_section(cur(350.0), hist([280, 290, 310, 320]), AS_OF, TH)
    assert c.n == 4 and not c.fires and "gap within run-to-run spread" in c.reasons
    assert compare_section(cur(356.0), hist([280, 290, 310, 320]), AS_OF, TH).fires


@pytest.mark.parametrize("hr, matched", [(154.0, 3), (146.0, 3), (154.1, 0), (145.9, 0)])
def test_hr_match_window_is_inclusive_4_bpm(hr, matched):
    c = compare_section(cur(340.0, hr=150.0), hist([300, 300, 300], hr=hr), AS_OF, TH)
    assert c.n == matched


def test_only_hr_matched_runs_count():
    h = hist([300, 300, 300, 400, 400], hr=[150, 151, 149, 170, 130])
    c = compare_section(cur(340.0), h, AS_OF, TH)
    assert c.n == 3 and c.baseline_time_s == 300.0


def test_180_day_window_ends_at_as_of():
    inside = hist([300], days_ago=180)
    outside = hist([300], days_ago=181)
    assert compare_section(cur(340.0), inside * 1, AS_OF, TH).n == 1
    assert compare_section(cur(340.0), outside, AS_OF, TH).n == 0


def test_only_earlier_runs_other_sections_and_usable_runs_count():
    junk = [
        SectionObs(SEC, "later", AS_OF + timedelta(days=1), 300.0, 150.0),
        SectionObs("z/c1", "other", AS_OF - timedelta(days=3), 300.0, 150.0),
        SectionObs(SEC, "excl", AS_OF - timedelta(days=3), 300.0, 150.0, excluded=True),
        SectionObs(SEC, "bad", AS_OF - timedelta(days=3), 300.0, 150.0, comparable=False),
        SectionObs(SEC, "nohr", AS_OF - timedelta(days=3), 300.0, None),
        SectionObs(SEC, "cur" + SEC, AS_OF - timedelta(days=3), 300.0, 150.0),
    ]
    assert compare_section(cur(340.0), junk, AS_OF, TH).n == 0


def test_not_comparable_or_no_hr_current_never_fires():
    h = hist([300, 300, 300])
    assert not compare_section(cur(340.0, comparable=False), h, AS_OF, TH).fires
    assert not compare_section(cur(340.0, hr=None), h, AS_OF, TH).fires


def test_sections_under_three_minutes_make_no_hr_claim():
    short = compare_section(cur(190.0), hist([160, 160, 160]), AS_OF, TH)
    assert short.n == 3 and short.gap_s == 30.0 and not short.fires
    assert "section too short for HR claims" in short.reasons
    ok = compare_section(cur(210.0), hist([180, 180, 180]), AS_OF, TH)
    assert ok.fires


def test_at_most_two_firing_sections_per_run_strongest_first():
    # three sections that all fire; spreads differ so |z| ranks c3 > c2 > c1
    history, current = [], []
    for sec, times, now in (
        ("k/c1", [290, 300, 310], 345.0),
        ("k/c2", [296, 300, 304], 345.0),
        ("k/c3", [299, 300, 301], 345.0),
        ("k/s1", [300, 300, 300], 300.0),
    ):
        history += hist(times, section=sec)
        current.append(cur(now, section=sec))
    out = {c.section_id: c for c in compare_run(current, history, AS_OF, TH)}
    assert [s for s, c in out.items() if c.fires] == ["k/c2", "k/c3"]
    assert out["k/c1"].reasons == ("over per-run budget",)
    assert not out["k/s1"].fires


def test_observations_from_measures():
    ms = [SectionMeasure("k/s1", 300.0, 150.0, True), SectionMeasure("k/s2", None, None, False, "detour")]
    obs = observations("w1", AS_OF, ms)
    assert [(o.section_id, o.time_s, o.comparable) for o in obs] == [("k/s1", 300.0, True), ("k/s2", None, False)]
