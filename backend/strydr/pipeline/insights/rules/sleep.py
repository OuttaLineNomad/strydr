"""Sleep (tier 2): the night before a run, and the runner's own pattern of sleep against effort.

short-sleep-run: a recent run after a night `short_h` or more under the runner's usual sleep (or under
`floor_h` while there is no usual yet). Number: hours slept.
effort-by-sleep: easy-intended runs with heart rate over `window_days`, after short nights against good nights;
needs `min_runs` on each side and fires when heartbeats per metre (avg HR / speed, so pace and route length
cancel out) are `change_pct` or more higher after short nights. Weekly athlete fact keyed on as_of's week.
"""
from datetime import timedelta

from ..keys import ATHLETE, make_evidence, make_fact, run_subject, week_id
from ..models import DerivedSnapshot, InsightFact
from ..registry import rule
from ..thresholds import Thresholds
from ._common import med, q, r1, recent_runs, runs_between

SHORT, PATTERN = "short-sleep-run", "effort-by-sleep"


@rule(SHORT)
def short_sleep_run(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(SHORT)
    out = []
    for run in recent_runs(snap, thresholds):
        z = run.sleep
        if not z:
            continue
        usual, total = z.get("usual_h"), z["total_h"]
        if usual is not None:
            if q(usual - total) < th["short_h"]:
                continue
            template = "short-sleep-run"
        elif total < th["floor_h"]:
            template = "short-sleep-run-no-usual"
        else:
            continue
        out.append(make_fact(
            SHORT, run_subject(run.workout_id), run.local_date, "observation", r1(total), "h",
            make_evidence(SHORT, {
                "total_h": r1(total), "usual_h": r1(usual) if usual is not None else None,
                "under_usual_h": round(usual - total, 2) if usual is not None else None, "quality": z["quality"],
                "deep_h": z.get("deep_h"), "rem_h": z.get("rem_h"), "awake_h": z.get("awake_h"),
                "avg_hr": r1(run.avg_hr) if run.avg_hr else None,
            }, "One night is one data point; caffeine, heat and stress move effort too."),
            template))
    return out


@rule(PATTERN)
def effort_by_sleep(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(PATTERN)
    short, good = [], []
    for r in runs_between(snap, snap.as_of - timedelta(days=th["window_days"] - 1), snap.as_of, False):
        z = r.sleep
        if not z or not r.is_easy_intended or not r.avg_hr or not r.avg_speed_mps:
            continue
        beats_per_km = r.avg_hr / r.avg_speed_mps * 1000.0 / 60
        if z["quality"] == "short":
            short.append(beats_per_km)
        elif z["quality"] == "good":
            good.append(beats_per_km)
    if len(short) < th["min_runs"] or len(good) < th["min_runs"]:
        return []
    more = q((med(short) / med(good) - 1.0) * 100.0)
    if more < th["change_pct"]:
        return []
    wid = week_id(snap.as_of)
    return [make_fact(
        PATTERN, ATHLETE, wid, "observation", r1(more), "%",
        make_evidence(PATTERN, {
            "window_days": th["window_days"], "short_runs": len(short), "good_runs": len(good),
            "short_beats_per_km": round(med(short)), "good_beats_per_km": round(med(good)),
        }, "A pattern across your own runs; it does not show that sleep alone explains it."),
        "effort-by-sleep")]
