"""Long-run spike (FR-18): a run's distance is more than 10% above the longest run in the last 30 days."""
from datetime import timedelta

from ..keys import make_evidence, make_fact, run_subject
from ..models import DerivedSnapshot, InsightFact
from ..registry import rule
from ..thresholds import Thresholds
from ._common import q, r1, recent_runs, runs_between

RULE_ID = "long-run-spike"


@rule(RULE_ID)
def long_run_spike(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(RULE_ID)
    out = []
    for run in recent_runs(snap, thresholds):
        if not run.distance_m:
            continue
        before = runs_between(snap, run.local_date - timedelta(days=th["window_days"]), run.local_date - timedelta(days=1))
        longest = max((r.distance_m for r in before if r.distance_m), default=None)
        if longest is None:
            continue
        pct = q((run.distance_m / longest - 1.0) * 100.0)
        if pct <= th["jump_pct"]:
            continue
        out.append(
            make_fact(
                RULE_ID, run_subject(run.workout_id), run.local_date, "observation", r1(pct), "%",
                make_evidence(
                    RULE_ID,
                    {"distance_m": round(run.distance_m), "longest_prior_m": round(longest), "window_days": th["window_days"]},
                    "A sudden jump in single-run distance is a common coaching flag; it is context, not a verdict.",
                ),
                "long-run-spike",
            )
        )
    return out
