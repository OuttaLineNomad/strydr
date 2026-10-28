"""Attaboys and streaks (FR-18).

Run attaboys: a best effort over a standard distance (GPS sanity-checked upstream), the longest run, or
a lifetime milestone. A run yields one fact (keys are unique per rule/subject/period); the primary event
decides the template and the other events (up to `max_per_run` in total) ride along in the evidence.
Record weeks and months compare completed periods. A record week is held back when a weekly-ramp fact
exists for that week. Streaks count consecutive ISO weeks with at least `streak_min_runs` runs; one
missed week in `forgive_one_per_weeks` is forgiven ("paused, not broken"); there are no daily streaks.
Nothing fires while a check-reading escalation is active.
"""
from datetime import timedelta

from ..keys import ATHLETE, make_evidence, make_fact, run_subject, week_subject
from ..models import M_PER_UNIT, DerivedSnapshot, InsightFact
from ..registry import rule
from ..thresholds import Thresholds
from ._common import has_check_reading, lookback_start, recent_runs, week_start

RULE_ID = "attaboys-streaks"


def _run_events(snap: DerivedSnapshot, thresholds: Thresholds, th) -> list[InsightFact]:
    out = []
    ordered = sorted(snap.runs, key=lambda r: (r.local_date, r.workout_id))
    unit_m = M_PER_UNIT[snap.units]
    # cumulative distance before each run, in order
    cum_before: dict[str, float] = {}
    longest_before: dict[str, tuple[float, int]] = {}
    total, longest, count = 0.0, 0.0, 0
    for r in ordered:
        cum_before[r.workout_id] = total
        longest_before[r.workout_id] = (longest, count)
        total += r.distance_m or 0.0
        longest = max(longest, r.distance_m or 0.0)
        count += 1
    for run in recent_runs(snap, thresholds):
        events: list[tuple[str, dict]] = []
        efforts = [b for b in snap.best_efforts if b.workout_id == run.workout_id and b.is_record and b.gps_ok]
        if efforts:
            best = max(efforts, key=lambda b: b.distance_m)
            events.append(("best-effort", {"label": best.label, "distance_m": round(best.distance_m), "time_s": round(best.time_s, 1)}))
        prev_longest, prev_count = longest_before[run.workout_id]
        if run.distance_m and prev_count >= th["longest_run_min_prior_runs"] and run.distance_m > prev_longest:
            events.append(("longest-run", {"distance_m": round(run.distance_m), "previous_m": round(prev_longest)}))
        before = cum_before[run.workout_id] / unit_m
        after = (cum_before[run.workout_id] + (run.distance_m or 0.0)) / unit_m
        crossed = [m for m in th["lifetime_milestones"] if before < m <= after]
        if crossed:
            events.append(("milestone", {"milestone": max(crossed), "unit": snap.units}))
        if not events:
            continue
        events = events[: th["max_per_run"]]
        kind, data = events[0]
        number, unit = {
            "best-effort": (data.get("time_s"), "s"),
            "longest-run": (data.get("distance_m"), "m"),
            "milestone": (data.get("milestone"), snap.units),
        }[kind]
        out.append(
            make_fact(
                RULE_ID, run_subject(run.workout_id), run.local_date, "attaboy", number, unit,
                make_evidence(
                    RULE_ID,
                    {"events": [{"event": k, **d} for k, d in events]},
                    "A factual note on a personal best; it says nothing about how hard to push next.",
                ),
                f"attaboys-streaks-{kind}",
            )
        )
    return out


def _record_periods(snap: DerivedSnapshot, thresholds: Thresholds, th, prior: list[InsightFact]) -> list[InsightFact]:
    out = []
    lo, hi = lookback_start(snap, thresholds), snap.as_of
    ramp_weeks = {f.subject for f in prior if f.rule_id == "weekly-ramp"}
    for periods, label, min_history in (
        (snap.weekly, "week", th["record_min_history_weeks"]),
        (snap.monthly, "month", th["record_min_history_months"]),
    ):
        ordered = sorted(periods, key=lambda p: p.start)
        for i, p in enumerate(ordered):
            if not (lo <= p.end < hi):
                continue  # only periods completed inside the lookback window
            earlier = ordered[:i]
            if len(earlier) < min_history or p.distance_m <= 0 or p.distance_m <= max(e.distance_m for e in earlier):
                continue
            if label == "week":
                if week_subject(p.period_id) in ramp_weeks:
                    continue
                subject, period = week_subject(p.period_id), p.period_id
            else:
                subject, period = ATHLETE, p.start.isoformat()
            out.append(
                make_fact(
                    RULE_ID, subject, period, "attaboy", round(p.distance_m), "m",
                    make_evidence(
                        RULE_ID,
                        {"period": p.period_id, "distance_m": round(p.distance_m), "previous_best_m": round(max(e.distance_m for e in earlier)),
                         "runs": p.run_count},
                        "Volume record over your history. A week that also showed a ramp is not celebrated.",
                    ),
                    f"attaboys-streaks-record-{label}",
                )
            )
    return out


def _streaks(snap: DerivedSnapshot, thresholds: Thresholds, th) -> list[InsightFact]:
    if snap.history_start is None:
        return []
    counts = {w.start: w.run_count for w in snap.weekly}
    monday_now = week_start(snap.as_of)
    first_window = week_start(lookback_start(snap, thresholds))
    wk = week_start(snap.history_start)
    streak, start, last_forgiven, i = 0, None, None, 0
    out = []
    while wk <= monday_now:
        n = counts.get(wk, 0)
        if n >= th["streak_min_runs"]:
            streak += 1
            start = wk if streak == 1 else start
            if streak in th["streak_milestones"] and wk >= first_window:
                out.append(
                    make_fact(
                        RULE_ID, ATHLETE, wk, "attaboy", float(streak), "weeks",
                        make_evidence(
                            RULE_ID,
                            {"streak_weeks": streak, "streak_start": start.isoformat(), "min_runs_per_week": th["streak_min_runs"],
                             "forgiven_week_in_streak": last_forgiven is not None},
                            "Consecutive weeks with enough runs. Rest days never break it and one missed week in 12 is forgiven.",
                        ),
                        "attaboys-streaks-streak",
                    )
                )
        elif wk < monday_now and streak > 0:
            if last_forgiven is None or i - last_forgiven >= th["forgive_one_per_weeks"]:
                last_forgiven = i  # paused, not broken
            else:
                streak, start = 0, None
        wk += timedelta(weeks=1)
        i += 1
    return out


@rule(RULE_ID, after=("weekly-ramp", "resting-hr"))
def attaboys_streaks(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    if has_check_reading(prior):
        return []
    th = thresholds.rule(RULE_ID)
    out: list[InsightFact] = []
    seen: set[str] = set()
    for f in _run_events(snap, thresholds, th) + _record_periods(snap, thresholds, th, prior) + _streaks(snap, thresholds, th):
        if f.insight_key not in seen:
            seen.add(f.insight_key)
            out.append(f)
    return out
