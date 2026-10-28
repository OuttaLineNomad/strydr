"""Cardiac drift (FR-18): pace:HR decoupling on a steady, easy run of 40+ minutes, first 10 minutes ignored.

Notable above 5%, high above 10%; under 5% on a run of 60+ minutes is an attaboy. Exactly 5% is silent.
With a workout temperature at or above 24 degC the run is tagged heat-affected (own template, and
`in_trend: False` in the evidence so a trend leaves it out). Without weather data no tag is added and
the heat caveat stays in the wording. Walks and hikes are never evaluated (they are not in `runs`).
"""
from ..keys import make_evidence, make_fact, run_subject
from ..models import DerivedSnapshot, InsightFact
from ..registry import rule
from ..series import drift_for_run
from ..thresholds import Thresholds
from ._common import has_check_reading, q, r1, recent_runs

RULE_ID = "cardiac-drift"


@rule(RULE_ID, after=("resting-hr",))
def cardiac_drift(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(RULE_ID)
    out = []
    for run in recent_runs(snap, thresholds):
        d = drift_for_run(run, snap.easy_ceiling_bpm, th)
        if d is None:
            continue
        heat = run.temperature_c is not None and run.temperature_c >= th["heat_c"]
        pct = q(d.decoupling_pct)
        long_enough = (run.duration_s or 0) >= th["attaboy_min_duration_min"] * 60
        if pct > th["high_pct"]:
            kind, template = "observation", "cardiac-drift-high"
        elif pct > th["notable_pct"]:
            kind, template = "observation", "cardiac-drift-notable"
        elif pct < th["notable_pct"] and long_enough and not has_check_reading(prior):
            kind, template = "attaboy", "cardiac-drift-solid"
        else:
            continue
        if heat and kind == "observation":
            template += "-heat"
        out.append(
            make_fact(
                RULE_ID, run_subject(run.workout_id), run.local_date, kind, r1(pct), "%",
                make_evidence(
                    RULE_ID,
                    {"decoupling_pct": r1(pct), "ef_first_half": round(d.ef_first, 3), "ef_second_half": round(d.ef_second, 3),
                     "mean_hr": r1(d.mean_hr), "minutes_used": d.minutes_used, "duration_s": round(run.duration_s or 0),
                     "temperature_c": run.temperature_c, "heat_affected": heat, "in_trend": not heat, "hill_gate": d.hill_gate},
                    "Heat, hills, hydration and fuelling can all skew drift; it is one signal among several.",
                ),
                template,
            )
        )
    return out
