"""Hard-day stacking / monotony (FR-18).

A hard day comes from derive/days (>= 20 min at >= 88% HRmax, or a long run).
  Stacking: 2 hard days in a row, or >= 3 hard days in any 7. Reported on the day that completes the
            stack, and only when the day before did not already (one fact per episode start).
  Monotony: mean / SD (population) of daily load over 7 days > 2.0 (capped at 10 when SD is 0), and the
            7-day load is at or above the 4-week average weekly load (28 days / 4, current week included).
            Needs 28 days of history. Weekly fact keyed on the week of as_of.
"""
from datetime import date, timedelta
from statistics import fmean, pstdev

from ..keys import ATHLETE, make_evidence, make_fact, week_id, week_subject
from ..models import DerivedSnapshot, InsightFact
from ..registry import rule
from ..thresholds import Thresholds
from ._common import lookback_start, q, r1

RULE_ID = "hard-day-stacking"


def _trigger(hard: dict[date, bool], d: date, th) -> str | None:
    if not hard.get(d):
        return None
    n = th["consecutive_days"]
    if all(hard.get(d - timedelta(days=k)) for k in range(n)):
        return "consecutive"
    if sum(1 for k in range(th["window_days"]) if hard.get(d - timedelta(days=k))) >= th["window_count"]:
        return "window"
    return None


@rule(RULE_ID)
def hard_day_stacking(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(RULE_ID)
    hard = {d.local_date: d.is_hard for d in snap.days}
    loads = {d.local_date: d.load for d in snap.days}
    out = []
    d = lookback_start(snap, thresholds)
    while d <= snap.as_of:
        trig = _trigger(hard, d, th)
        if trig and not _trigger(hard, d - timedelta(days=1), th):
            days_in = [d - timedelta(days=k) for k in range(th["window_days"]) if hard.get(d - timedelta(days=k))]
            data = {"trigger": trig, "hard_days": sorted(x.isoformat() for x in days_in), "window_days": th["window_days"]}
            carried = sorted(x.isoformat() for x in days_in if x in snap.carried_run_dates)
            if carried:
                data["carried_days"] = carried
            out.append(
                make_fact(
                    RULE_ID, ATHLETE, d, "observation", float(len(days_in)), "days",
                    make_evidence(
                        RULE_ID, data,
                        "Hard days are 20+ minutes near your maximum heart rate, or a long run. Easy days between them are a common pattern.",
                    ),
                    f"hard-day-stacking-{trig}" + ("-carry" if carried else ""),
                )
            )
        d += timedelta(days=1)

    n = th["monotony_window_days"]
    span = [snap.as_of - timedelta(days=k) for k in range(n)]
    four = [snap.as_of - timedelta(days=k) for k in range(7 * th["volume_weeks"])]
    if (
        snap.history_start is not None
        and snap.history_start <= four[-1]
        and all(x in loads for x in four)
    ):
        week = [loads[x] for x in span]
        mean = fmean(week)
        sd = pstdev(week)
        weekly_avg = sum(loads[x] for x in four) / th["volume_weeks"]
        if mean > 0:
            mono = th["monotony_cap"] if sd == 0 else min(mean / sd, th["monotony_cap"])
            if q(mono) > th["monotony_threshold"] and q(sum(week)) >= q(weekly_avg):
                wid = week_id(snap.as_of)
                out.append(
                    make_fact(
                        RULE_ID, week_subject(wid), wid, "observation", r1(mono), "ratio",
                        make_evidence(
                            RULE_ID,
                            {"mean_daily_load": r1(mean), "sd_daily_load": r1(sd), "week_load": r1(sum(week)),
                             "avg_weekly_load_4w": r1(weekly_avg), "window_days": n},
                            "Monotony is the mean daily load divided by its spread. Similar loads every day give a high value.",
                        ),
                        "hard-day-stacking-monotony",
                    )
                )
    return out
