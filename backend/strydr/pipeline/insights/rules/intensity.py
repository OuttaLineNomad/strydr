"""80/20 and easy-pace creep (FR-18), registered as two rules because they fire on different conditions
and are rated (thumbs) separately: `intensity-mix` and `easy-creep`. Both are weekly facts, keyed on the
ISO week of as_of.

Easy means HR at or below the easy ceiling (profile).
  intensity-mix: under 70% of run time easy over 28 days (>= 8 runs with HR).
  easy-creep:    in the last 14 days >= 40% of easy-intended runs averaged above the ceiling, or easy
                 pace is >= 5% faster than the prior 8 weeks while HR is >= 3 bpm higher.
"""
from datetime import timedelta

from ..keys import ATHLETE, make_evidence, make_fact, week_id, week_subject
from ..models import DerivedSnapshot, InsightFact
from ..registry import rule
from ..thresholds import Thresholds
from ._common import med, q, r1, runs_between

MIX_ID = "intensity-mix"
CREEP_ID = "easy-creep"


@rule(MIX_ID)
def intensity_mix(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(MIX_ID)
    runs = [
        r
        for r in runs_between(snap, snap.as_of - timedelta(days=th["window_days"] - 1), snap.as_of)
        if r.hr_time_s and r.easy_time_s is not None and (r.hr_coverage or 0) >= th["min_hr_coverage"]
    ]
    if len(runs) < th["min_runs"]:
        return []
    hr_s = sum(r.hr_time_s for r in runs)
    easy = sum(r.easy_time_s for r in runs)
    share = q(easy / hr_s * 100.0)
    if share >= th["min_easy_share_pct"]:
        return []
    wid = week_id(snap.as_of)
    return [
        make_fact(
            MIX_ID, week_subject(wid), wid, "observation", r1(share), "%",
            make_evidence(
                MIX_ID,
                {"window_days": th["window_days"], "runs": len(runs), "easy_time_s": round(easy), "hr_time_s": round(hr_s),
                 "easy_ceiling_bpm": round(snap.easy_ceiling_bpm)},
                "80/20 is a common pattern among endurance athletes. This is context, not a rule.",
            ),
            "intensity-mix",
        )
    ]


@rule(CREEP_ID)
def easy_creep(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    """Runs once per cohort (carried / uncarried). The carried fact is keyed on `athlete` so it never collides with the uncarried one."""
    return [f for carried in (False, True) for f in _creep(snap, thresholds, carried)]


def _creep(snap: DerivedSnapshot, thresholds: Thresholds, carried: bool) -> list[InsightFact]:
    th = thresholds.rule(CREEP_ID)
    recent_start = snap.as_of - timedelta(days=th["recent_days"] - 1)

    def easy_runs(first, last):
        return [
            r
            for r in runs_between(snap, first, last, carried)
            if r.is_easy_intended and r.avg_hr is not None and (r.hr_coverage or 0) >= th["min_hr_coverage"]
        ]

    recent = easy_runs(recent_start, snap.as_of)
    if len(recent) < th["min_runs"]:
        return []
    over = sum(1 for r in recent if r.avg_hr > snap.easy_ceiling_bpm)
    share = q(over / len(recent) * 100.0)
    by_ceiling = share >= th["over_ceiling_share_pct"]

    older = easy_runs(recent_start - timedelta(days=th["prior_days"]), recent_start - timedelta(days=1))
    pace_pct = hr_delta = None
    by_pace = False
    speeds_r = [r.avg_speed_mps for r in recent if r.avg_speed_mps]
    speeds_o = [r.avg_speed_mps for r in older if r.avg_speed_mps]
    if len(older) >= th["min_runs"] and speeds_r and speeds_o:
        pace_pct = q((med(speeds_r) / med(speeds_o) - 1.0) * 100.0)
        hr_delta = q(med([r.avg_hr for r in recent]) - med([r.avg_hr for r in older]))
        by_pace = pace_pct >= th["pace_faster_pct"] and hr_delta >= th["hr_higher_bpm"]
    if not (by_ceiling or by_pace):
        return []
    wid = week_id(snap.as_of)
    data = {"recent_days": th["recent_days"], "easy_intended_runs": len(recent), "runs_over_ceiling": over,
            "easy_ceiling_bpm": round(snap.easy_ceiling_bpm), "trigger": [t for t, on in (("ceiling", by_ceiling), ("pace-and-hr", by_pace)) if on]}
    if pace_pct is not None:
        data.update({"pace_faster_pct": r1(pace_pct), "hr_higher_bpm": r1(hr_delta), "prior_runs": len(older)})
    number, unit, template = (r1(share), "%", "easy-creep-ceiling") if by_ceiling else (r1(pace_pct), "%", "easy-creep-pace")
    if carried:
        data["carried"] = True
        template += "-carry"
    return [
        make_fact(
            CREEP_ID, ATHLETE if carried else week_subject(wid), wid, "observation", number, unit,
            make_evidence(CREEP_ID, data, "Easy days that drift above the easy ceiling blur the hard/easy pattern. Context, not a rule."),
            template,
        )
    ]
