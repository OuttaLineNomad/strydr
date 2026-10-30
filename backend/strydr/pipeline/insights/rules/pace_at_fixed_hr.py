"""Pace at fixed HR (FR-18): median flat-ground pace while HR is inside a 10 bpm band, weeks 5-8 vs 1-4.

The band is centred on the runner's median easy HR over the last 8 weeks (minutes at or below the easy
ceiling, after warm-up), rounded to 5 bpm. A run qualifies with >= 10 flat, moving, in-band minutes and no
heat tag (>= 24 degC is left out). Needs >= 4 qualifying runs in each 4-week half. Fires on a change of
3% or more: faster is an attaboy, slower a neutral observation. Weekly fact keyed on the week of as_of.
"""
from datetime import timedelta

from ..keys import ATHLETE, make_evidence, make_fact, week_id, week_subject
from ..models import DerivedSnapshot, InsightFact, RunSummary
from ..registry import rule
from ..series import qualifying_speeds
from ..thresholds import Thresholds
from ._common import has_check_reading, med, q, r1, runs_between

RULE_ID = "pace-at-fixed-hr"


def _easy_median_hr(runs: list[RunSummary], ceiling: float, warmup: int) -> float | None:
    hrs = [m.hr for r in runs if r.minutes for m in r.minutes[warmup:] if m.hr is not None and m.hr <= ceiling]
    return med(hrs) if hrs else None


@rule(RULE_ID, after=("resting-hr",))
def pace_at_fixed_hr(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    """Runs once per cohort (carried / uncarried). The carried fact is keyed on `athlete` so it never collides with the uncarried one."""
    return [f for carried in (False, True) for f in _cohort(snap, thresholds, prior, carried)]


def _cohort(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact], carried: bool) -> list[InsightFact]:
    th = thresholds.rule(RULE_ID)
    w = th["window_days"]
    recent_start = snap.as_of - timedelta(days=w - 1)
    prior_start = recent_start - timedelta(days=w)
    base_runs = runs_between(snap, snap.as_of - timedelta(days=th["easy_hr_window_days"] - 1), snap.as_of, carried)
    easy_hr = _easy_median_hr(base_runs, snap.easy_ceiling_bpm, th["warmup_min"])
    if easy_hr is None:
        return []
    centre = 5 * round(easy_hr / 5)
    band = (centre - th["band_bpm"] / 2, centre + th["band_bpm"] / 2)

    def run_speeds(first, last) -> list[float]:
        out = []
        for r in runs_between(snap, first, last, carried):
            if r.temperature_c is not None and r.temperature_c >= th["heat_c"]:
                continue
            speeds = qualifying_speeds(r, band, th)
            if len(speeds) >= th["min_minutes"]:
                out.append(med(speeds))
        return out

    recent = run_speeds(recent_start, snap.as_of)
    older = run_speeds(prior_start, recent_start - timedelta(days=1))
    if len(recent) < th["min_runs"] or len(older) < th["min_runs"]:
        return []
    change = q((med(recent) / med(older) - 1.0) * 100.0)
    if abs(change) < th["change_pct"]:
        return []
    faster = change > 0
    if faster and has_check_reading(prior):
        return []
    wid = week_id(snap.as_of)
    data = {"band_bpm": [band[0], band[1]], "recent_runs": len(recent), "prior_runs": len(older),
            "recent_speed_mps": round(med(recent), 3), "prior_speed_mps": round(med(older), 3), "window_days": w}
    if carried:
        data["carried"] = True
    return [
        make_fact(
            RULE_ID, ATHLETE if carried else week_subject(wid), wid, "attaboy" if faster else "observation", r1(abs(change)), "%",
            make_evidence(RULE_ID, data, "Pace at the same heart rate is a common fitness marker; heat and tiredness move it too."),
            ("pace-at-hr-faster" if faster else "pace-at-hr-slower") + ("-carry" if carried else ""),
        )
    ]
