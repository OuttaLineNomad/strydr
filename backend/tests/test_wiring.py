"""The recompute stages end to end on synthetic canonical rows: what lands in each analytic table."""
import re
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.pipeline.derive import summary
from strydr.pipeline.derive.load import DailyLoad, acwr
from strydr.pipeline.insights.keys import make_evidence, make_fact
from strydr.pipeline.insights.templates import BANNED_TERMS, ROUTE_TEMPLATES, render
from strydr.pipeline.profile import resolve
from strydr.store import models

from helpers import add_run, login, recompute_now, set_hrmax

AS_OF = "2026-10-26"


def _history(engine):
    set_hrmax(engine, 150)
    for i in range(8):
        add_run(engine, f"r{i}", datetime(2026, 10, 1 + 3 * i, 7), 40, 3.0, hr=[150.0] * 40)
    add_run(engine, "walk-nohr", datetime(2026, 10, 22, 12), 30, 1.3, hr=None, route=False, type_="walk")
    add_run(engine, "run-nohr", datetime(2026, 10, 25, 12), 30, 3.0, hr=None, route=False, reported_m=5400)


def _loads(engine):
    with Session(engine) as s:
        return {w.workout_id: w for w in s.execute(select(models.WorkoutLoad)).scalars()}


def test_load_days_and_profile_rows_are_persisted(engine):
    _history(engine)
    recompute_now(engine, AS_OF)
    loads = _loads(engine)
    assert set(loads) == {f"r{i}" for i in range(8)} | {"walk-nohr", "run-nohr"}
    assert loads["r0"].estimated is False and loads["r0"].source in ("hr", "hr-scaled")
    assert loads["walk-nohr"].estimated and loads["walk-nohr"].source == "default" and loads["walk-nohr"].trimp > 0
    with Session(engine) as s:
        days = {d.local_date: d for d in s.execute(select(models.DailyLoad)).scalars()}
        classes = {d.local_date: d for d in s.execute(select(models.DayClass)).scalars()}
        prof = s.execute(select(models.ProfileResult)).scalar_one()
    assert min(days) == "2026-10-01" and max(days) == AS_OF and set(days) == set(classes)  # zero-filled, one per date
    assert days["2026-10-02"].load == 0 and days["2026-10-01"].load == pytest.approx(loads["r0"].trimp)
    assert days["2026-10-22"].by_type["walk"] == pytest.approx(loads["walk-nohr"].trimp) and days["2026-10-22"].estimated
    assert all(d.fitness >= 0 and d.fatigue >= 0 for d in days.values()) and days["2026-10-01"].warmup
    assert classes["2026-10-02"].kind == "rest" and classes["2026-10-01"].kind == "run"
    assert prof.hrmax and prof.rhr_baseline_mean is None  # no resting-HR data in these rows


def test_note_rpe_overrides_only_estimated_loads(engine, app_client, worker):
    _history(engine)
    recompute_now(engine, AS_OF)
    before = _loads(engine)
    login(app_client)
    for wid in ("r0", "walk-nohr", "run-nohr"):
        assert app_client.put(f"/api/v1/workouts/{wid}/note", json={"rpe": 9}).status_code == 200
    worker.run_all()  # the writes enqueued one recompute (AD-1)
    after = _loads(engine)
    assert after["r0"].trimp == pytest.approx(before["r0"].trimp) and after["r0"].source == before["r0"].source  # measured: untouched
    for wid in ("walk-nohr", "run-nohr"):
        assert after[wid].source == "rpe" and after[wid].estimated and after[wid].rpe == 9
        assert after[wid].trimp != before[wid].trimp  # the rating replaced the estimate
    assert after["r0"].rpe == 9  # recorded, but not used


def test_resting_hr_and_hrv_baselines_follow_the_documented_windows():
    as_of = date(2026, 10, 26)
    rhr = {(as_of - timedelta(days=k)).isoformat(): 50.0 + (k % 3) for k in range(0, 60)}
    b = resolve.rhr_baseline(rhr, as_of)
    assert b.n_days == 30 and 50 <= b.mean <= 52 and b.sd > 0
    last = (as_of - timedelta(days=3)).isoformat()
    assert resolve.rhr_baseline({**rhr, as_of.isoformat(): 120.0}, as_of).n_days == 30  # the last 3 days are excluded
    hrv = {(as_of - timedelta(days=k)).isoformat(): 60.0 for k in range(0, 80)}
    h = resolve.hrv_baseline(hrv, as_of)
    assert h.n_days == 60 and h.mean == pytest.approx(4.0943445, abs=1e-6) and h.sd == 0
    assert resolve.rhr_baseline({}, as_of) is None and last


def test_summary_intensity_minutes_and_easy_intended():
    t = [30.0 + 60 * m for m in range(20)]
    avg = [120.0] * 10 + [160.0] * 10
    hr_time, easy, cov = summary.intensity_mix(t, avg, 1200.0, 140.0)
    assert (hr_time, easy) == (15 * 60.0, 5 * 60.0) and cov == pytest.approx(1.0)  # first 5 minutes are warm-up
    assert summary.intensity_mix(t, avg, 1200.0, None) is None and summary.intensity_mix([], [], 600.0, 140.0) is None
    mins = summary.minute_points({"t": [30.0, 90.0], "avg": [140.0, 150.0]}, {"t": [0.0, 30.0, 70.0], "speed": [3.0, 4.0, 5.0],
                                                                                "alt": [10.0, None, 12.0]}, 120.0)
    assert mins == [[140.0, 3.5, 10.0], [150.0, 5.0, 12.0]]
    assert summary.minute_points(None, None, 60.0) is None
    assert summary.is_easy_intended(False, False, None) and summary.is_easy_intended(False, False, 6)
    assert not summary.is_easy_intended(True, False, None) and not summary.is_easy_intended(False, True, None)
    assert not summary.is_easy_intended(False, False, 7)


def test_acwr_is_the_acute_to_chronic_ratio_and_needs_28_days():
    days = [DailyLoad(date(2026, 1, 1) + timedelta(days=i), 10.0 if i < 21 else 20.0, {}, False, 1) for i in range(28)]
    assert acwr(days, 26) is None
    assert acwr(days, 27) == pytest.approx(20.0 / ((21 * 10 + 7 * 20) / 28))


@pytest.mark.parametrize("tid", sorted(ROUTE_TEMPLATES))
@pytest.mark.parametrize("units", ["km", "mi"])
def test_same_route_templates_follow_the_wording_rules(tid, units):
    data = {"label": "km 3", "hr_bpm": 150, "runs": 4}
    fact = make_fact("same-route-hr", "run/abc", "2026-10-24", "observation", 21.5, "s", make_evidence("same-route-hr", data, "n"), tid)
    text = render(fact, units)
    assert "21.5" in text and "!" not in text and re.search(r"\byou\b", text.lower())
    assert text.endswith(".") and not re.search(r"[.!?]\s", text)
    assert not any(term in text.lower() for term in BANNED_TERMS)
