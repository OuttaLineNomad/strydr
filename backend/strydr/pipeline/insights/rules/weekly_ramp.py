"""Weekly ramp (FR-18): this week's running volume is more than 30% above the 4-week average.

Evaluated for the week containing as_of (week to date) and for the weeks that start inside the lookback
window, so the record-week check can see whether a ramp fired that week. Context only (FR-21a).
The 4-week average is the mean of the 4 preceding ISO weeks, empty weeks counting as zero; it needs
4 weeks of history and a non-zero average.
"""
from datetime import date, timedelta

from ..keys import make_evidence, make_fact, week_id, week_subject
from ..models import DerivedSnapshot, InsightFact
from ..registry import rule
from ..thresholds import Thresholds
from ._common import lookback_start, q, r1, week_start

RULE_ID = "weekly-ramp"


def ramp_check(snap: DerivedSnapshot, monday: date, th) -> tuple[float, float, float] | None:
    """(this_week_m, baseline_avg_m, pct_above) when the week has a full baseline, else None."""
    if snap.history_start is None:
        return None
    n = th["baseline_weeks"]
    if snap.history_start > monday - timedelta(weeks=n):
        return None  # fewer than n weeks of history
    vols = {w.start: w.distance_m for w in snap.weekly}
    avg = sum(vols.get(monday - timedelta(weeks=k), 0.0) for k in range(1, n + 1)) / n
    if avg <= 0:
        return None
    this = vols.get(monday, 0.0)
    return this, avg, q((this / avg - 1.0) * 100.0)


@rule(RULE_ID)
def weekly_ramp(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(RULE_ID)
    out = []
    monday = week_start(snap.as_of)
    week = week_start(lookback_start(snap, thresholds))
    while week <= monday:
        res = ramp_check(snap, week, th)
        if res is not None and res[2] > th["ramp_pct"]:
            this, avg, pct = res
            wid = week_id(week)
            out.append(
                make_fact(
                    RULE_ID, week_subject(wid), wid, "observation", r1(pct), "%",
                    make_evidence(
                        RULE_ID,
                        {"week_id": wid, "week_distance_m": round(this), "avg_prior_weeks_m": round(avg),
                         "baseline_weeks": th["baseline_weeks"], "week_to_date": week == monday},
                        "Volume versus your recent average, shown as context only. It is not a risk score.",
                    ),
                    "weekly-ramp",
                )
            )
        week += timedelta(weeks=1)
    return out
