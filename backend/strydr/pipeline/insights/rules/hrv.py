"""HRV (FR-18): the 7-day rolling mean of ln(SDNN) falls below the baseline mean - 1 SD for 2 days in a row.

The baseline (profile) is the mean/SD of the daily ln(SDNN) over the 60 days ending a week before as_of and
needs >= 40 days. Each rolling mean needs >= 4 readings (days with a value) in its 7-day window. If a
resting-HR episode is also active the fact says so (evidence and template). Episode key = first day of the
current below-range streak. Apple Watch HRV is noisy; the wording says so (FR-21a).
"""
import math
from datetime import date, timedelta

from ..keys import ATHLETE, make_evidence, make_fact
from ..models import DerivedSnapshot, InsightFact
from ..registry import rule
from ..thresholds import Thresholds
from ._common import q, r1

RULE_ID = "hrv"


def rolling_ln(ln_by_day: dict[date, float], day: date, th) -> float | None:
    vals = [ln_by_day[d] for k in range(th["window_days"]) if (d := day - timedelta(days=k)) in ln_by_day]
    return sum(vals) / len(vals) if len(vals) >= th["min_readings"] else None


@rule(RULE_ID, after=("resting-hr",))
def hrv(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(RULE_ID)
    b = snap.hrv_baseline
    if b is None or b.n_days < th["baseline_min_days"]:
        return []
    ln_by_day = {v.local_date: math.log(v.value) for v in snap.hrv_sdnn_ms if v.value > 0}
    cut = b.mean - th["sd_multiple"] * b.sd

    def below(day: date) -> bool:
        r = rolling_ln(ln_by_day, day, th)
        return r is not None and q(r) < q(cut)

    n = th["consecutive_days"]
    if not all(below(snap.as_of - timedelta(days=k)) for k in range(n)):
        return []
    start = snap.as_of - timedelta(days=n - 1)
    while below(start - timedelta(days=1)):
        start -= timedelta(days=1)
    rolling = rolling_ln(ln_by_day, snap.as_of, th)
    pct_below = (1.0 - math.exp(rolling - b.mean)) * 100.0
    rhr_high = any(f.rule_id == "resting-hr" and f.kind == "observation" for f in prior)
    return [
        make_fact(
            RULE_ID, ATHLETE, start, "observation", r1(pct_below), "%",
            make_evidence(
                RULE_ID,
                {"rolling_7d_sdnn_ms": r1(math.exp(rolling)), "baseline_sdnn_ms": r1(math.exp(b.mean)),
                 "range_floor_sdnn_ms": r1(math.exp(cut)), "baseline_days": b.n_days, "resting_hr_also_elevated": rhr_high,
                 "episode_start": start.isoformat()},
                "Apple Watch reports SDNN at irregular times, so HRV is noisy. Treat it as a trend, not a daily verdict.",
            ),
            "hrv-below-rhr" if rhr_high else "hrv-below",
        )
    ]
