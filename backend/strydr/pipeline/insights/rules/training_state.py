"""Training state (FR-24b): Building, Holding, Easing or Overreaching, with 3-day hysteresis.

The state itself (and its hysteresis) is computed by derive/load; this rule turns the as_of day into a
fact keyed on the first day of the confirmed state. Nothing fires during the warm-up or when there is
too little recent training. ACWR/ramp figures stay context in the evidence (FR-24c, FR-21a).
"""
from ..keys import ATHLETE, make_evidence, make_fact
from ..models import DerivedSnapshot, InsightFact
from ..registry import rule
from ..thresholds import Thresholds
from ._common import r1

RULE_ID = "training-state"


@rule(RULE_ID)
def training_state(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(RULE_ID)
    ts = snap.training_state
    if not th["enabled"] or ts is None or ts.state is None or ts.since is None or ts.ramp_pct is None:
        return []
    return [
        make_fact(
            RULE_ID, ATHLETE, ts.since, "observation", r1(ts.ramp_pct), "%",
            make_evidence(
                RULE_ID,
                {"state": ts.state, "raw_state_today": ts.raw_state, "weekly_fitness_change_pct": r1(ts.ramp_pct),
                 "form_pct": None if ts.form_pct is None else r1(ts.form_pct), "since": ts.since.isoformat(),
                 "hysteresis_days": th["hysteresis_days"]},
                "A description of the recent load trend from your fitness and fatigue curves. It is not a diagnosis.",
            ),
            f"training-state-{ts.state.lower()}",
        )
    ]
