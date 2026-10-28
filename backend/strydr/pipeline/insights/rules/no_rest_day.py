"""No rest day (FR-18): 6 or more consecutive days without a rest day, carrying >= 50% of the usual weekly load.

A rest day comes from derive/days (no run and only light activity: an easy walk counts, a big hike does
not). Usual weekly load = the 28 days ending at as_of divided by 4; the gate compares the latest
`min_days` days against half of it and is skipped (and noted in the evidence) with under 28 days of
history. The episode key is the first day of the current no-rest streak. The runner can switch the rule
off with the `enabled` threshold override (e.g. while run-streaking).
"""
from datetime import timedelta

from ..keys import ATHLETE, make_evidence, make_fact
from ..models import DerivedSnapshot, InsightFact
from ..registry import rule
from ..thresholds import Thresholds
from ._common import q, r1

RULE_ID = "no-rest-day"


@rule(RULE_ID)
def no_rest_day(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(RULE_ID)
    if not th["enabled"]:
        return []
    by_day = {d.local_date: d for d in snap.days}
    streak = 0
    while (snap.as_of - timedelta(days=streak)) in by_day and not by_day[snap.as_of - timedelta(days=streak)].is_rest:
        streak += 1
    if streak < th["min_days"]:
        return []
    latest = [by_day[snap.as_of - timedelta(days=k)].load for k in range(th["min_days"])]
    four = [snap.as_of - timedelta(days=k) for k in range(7 * th["volume_weeks"])]
    has_history = snap.history_start is not None and snap.history_start <= four[-1] and all(x in by_day for x in four)
    data = {"streak_days": streak, "latest_days_load": r1(sum(latest))}
    if has_history:
        usual = sum(by_day[x].load for x in four) / th["volume_weeks"]
        if usual > 0 and q(sum(latest)) < q(th["min_load_fraction"] * usual):
            return []
        data["usual_week_load"] = r1(usual)
    else:
        data["volume_gate"] = "skipped (under 4 weeks of history)"
    start = snap.as_of - timedelta(days=streak - 1)
    data["episode_start"] = start.isoformat()
    return [
        make_fact(
            RULE_ID, ATHLETE, start, "observation", float(streak), "days",
            make_evidence(RULE_ID, data, "Many training plans include a lighter or rest day each week. Context, not a rule."),
            "no-rest-day",
        )
    ]
