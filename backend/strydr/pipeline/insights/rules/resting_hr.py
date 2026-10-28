"""Resting HR (FR-18): at or above the 30-day mean + max(5 bpm, 1.5 SD) for 3 days in a row.

The baseline (profile) needs >= 21 valid days. A reading outside 35-100 bpm, or a single day >= 15 bpm
above the baseline mean, produces a neutral check-reading fact instead and is never interpreted (FR-21a);
such days do not count toward an elevated streak. The episode key is the first day of the current streak.
"""
from datetime import timedelta

from ..keys import ATHLETE, make_evidence, make_fact
from ..models import DerivedSnapshot, InsightFact
from ..registry import rule
from ..thresholds import Thresholds
from ._common import q, r1

RULE_ID = "resting-hr"


def _is_check(value: float, snap: DerivedSnapshot, th) -> bool:
    if value < th["check_low_bpm"] or value > th["check_high_bpm"]:
        return True
    b = snap.rhr_baseline
    return b is not None and b.n_days >= th["baseline_min_days"] and value >= b.mean + th["check_jump_bpm"]


@rule(RULE_ID)
def resting_hr(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(RULE_ID)
    values = {v.local_date: v.value for v in snap.resting_hr}
    out = []
    for k in range(th["check_lookback_days"]):
        d = snap.as_of - timedelta(days=k)
        if d in values and _is_check(values[d], snap, th):
            out.append(
                make_fact(
                    RULE_ID, ATHLETE, d, "check-reading", r1(values[d]), "bpm",
                    make_evidence(
                        RULE_ID,
                        {"value_bpm": r1(values[d]), "baseline_mean_bpm": r1(snap.rhr_baseline.mean) if snap.rhr_baseline else None,
                         "plausible_range_bpm": [th["check_low_bpm"], th["check_high_bpm"]]},
                        "An unusual reading is shown as is and not interpreted. Check your device.",
                    ),
                    "resting-hr-check",
                )
            )
    b = snap.rhr_baseline
    if b is None or b.n_days < th["baseline_min_days"]:
        return out
    cut = q(b.mean + max(th["abs_bpm"], th["sd_multiple"] * max(b.sd, th["sd_floor_bpm"])))

    def elevated(d) -> bool:
        return d in values and q(values[d]) >= cut and not _is_check(values[d], snap, th)

    n = th["consecutive_days"]
    if all(elevated(snap.as_of - timedelta(days=k)) for k in range(n)):
        start = snap.as_of - timedelta(days=n - 1)
        while elevated(start - timedelta(days=1)):
            start -= timedelta(days=1)
        last = [values[snap.as_of - timedelta(days=k)] for k in range(n)]
        excess = sum(last) / n - b.mean
        out.append(
            make_fact(
                RULE_ID, ATHLETE, start, "observation", r1(excess), "bpm",
                make_evidence(
                    RULE_ID,
                    {"last_days_bpm": [r1(v) for v in reversed(last)], "baseline_mean_bpm": r1(b.mean), "baseline_sd_bpm": r1(b.sd),
                     "baseline_days": b.n_days, "threshold_bpm": r1(cut), "episode_start": start.isoformat()},
                    "Resting HR can rise with incomplete recovery, heat or poor sleep. Apple's value is a derived estimate.",
                ),
                "resting-hr-elevated",
            )
        )
    return out
