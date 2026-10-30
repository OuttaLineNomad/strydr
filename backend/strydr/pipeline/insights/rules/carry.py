"""Carry (story 13): a run with a pack, vest or child carrier gets one fact saying so, so a slower pace or higher heart
rate on it reads as context. Carried runs are judged only against other carried runs (see `_common.in_cohort`).
"""
from ..keys import make_evidence, make_fact, run_subject
from ..models import DerivedSnapshot, InsightFact
from ..registry import rule
from ..thresholds import Thresholds
from ._common import recent_runs

RULE_ID = "carry"


@rule(RULE_ID)
def carry(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    if not thresholds.rule(RULE_ID)["enabled"]:
        return []
    return [
        make_fact(
            RULE_ID, run_subject(run.workout_id), run.local_date, "observation", round(run.carry_kg, 2), "kg",
            make_evidence(RULE_ID, {"carried_kg": round(run.carry_kg, 2)},
                          "Carried runs are compared only with other carried runs, since extra load slows pace and lifts heart rate."),
            "carry-run",
        )
        for run in recent_runs(snap, thresholds, carried=True)
    ]
