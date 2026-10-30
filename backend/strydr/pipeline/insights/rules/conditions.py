"""Conditions (tier 2): how much of a run's pace heat and hills account for, and the runner's own heat pattern.

heat-adjusted-pace: a recent outdoor run where the temperature + dew point rule of thumb (derive/conditions)
puts the adjustment at `min_pct` or more. Number: seconds per runner unit associated with the conditions.
hill-adjusted-pace: a recent run on hilly ground whose grade adjusted pace (derive/grade) is `min_pct` or more
faster than its actual pace. Number: seconds per runner unit associated with the climbs.
pace-by-conditions: easy-intended outdoor runs with a known dew point over `window_days`, split at
`dew_split_c`; needs `min_runs` on each side and fires when the warm side's median pace (grade adjusted where
known, so hills do not pass for heat) is `change_pct` or more slower. Weekly athlete fact keyed on as_of's week.
All three are estimates: the evidence note says so and the templates use "associated with".
"""
from datetime import timedelta

from ..keys import ATHLETE, make_evidence, make_fact, run_subject, week_id, week_subject
from ..models import M_PER_UNIT, DerivedSnapshot, InsightFact, RunSummary
from ..registry import rule
from ..thresholds import Thresholds
from ._common import med, q, r1, recent_runs, runs_between

HEAT, HILL, PATTERN = "heat-adjusted-pace", "hill-adjusted-pace", "pace-by-conditions"


def _pace_s(unit_m: float, speed: float) -> float:
    return unit_m / speed


@rule(HEAT)
def heat_adjusted_pace(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(HEAT)
    unit_m = M_PER_UNIT[snap.units]
    out = []
    for run in recent_runs(snap, thresholds):
        c = run.conditions
        if run.is_indoor or not c or not run.avg_speed_mps or (run.distance_m or 0) < th["min_distance_m"]:
            continue
        pct = c.get("heat_adjust_pct")
        if pct is None or q(pct) < th["min_pct"]:
            continue
        adj_speed = run.avg_speed_mps * (1.0 + pct / 100.0)
        cost = _pace_s(unit_m, run.avg_speed_mps) - _pace_s(unit_m, adj_speed)
        out.append(make_fact(
            HEAT, run_subject(run.workout_id), run.local_date, "observation", round(cost), "s",
            make_evidence(HEAT, {
                "heat_adjust_pct": r1(pct), "temperature_c": c["temp_c"], "dew_point_c": c["dew_point_c"],
                "temp_dew_sum_f": c["temp_dew_sum_f"], "band": c["band"],
                "pace_s_per_unit": round(_pace_s(unit_m, run.avg_speed_mps)),
                "adjusted_pace_s_per_unit": round(_pace_s(unit_m, adj_speed)),
            }, "Temperature plus dew point is a coaching rule of thumb for heat; treat the adjustment as an estimate."),
            "heat-adjusted-pace"))
    return out


@rule(HILL)
def hill_adjusted_pace(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    th = thresholds.rule(HILL)
    unit_m = M_PER_UNIT[snap.units]
    out = []
    for run in recent_runs(snap, thresholds):
        g = run.gap
        if not g or not g.get("hilly") or not run.avg_speed_mps or not g.get("gap_speed_mps"):
            continue
        pct = q((g["gap_speed_mps"] / run.avg_speed_mps - 1.0) * 100.0)
        if pct < th["min_pct"]:
            continue
        cost = _pace_s(unit_m, run.avg_speed_mps) - _pace_s(unit_m, g["gap_speed_mps"])
        out.append(make_fact(
            HILL, run_subject(run.workout_id), run.local_date, "observation", round(cost), "s",
            make_evidence(HILL, {
                "gap_pct": r1(pct), "relief_m": g["relief_m"], "relief_m_per_km": g["relief_m_per_km"],
                "pace_s_per_unit": round(_pace_s(unit_m, run.avg_speed_mps)),
                "adjusted_pace_s_per_unit": round(_pace_s(unit_m, g["gap_speed_mps"])),
            }, "Grade adjusted pace uses a lab model of running cost on slopes and the watch's altitude, so it is an estimate."),
            "hill-adjusted-pace"))
    return out


def _speed(r: RunSummary) -> float | None:
    g = r.gap or {}
    return g.get("gap_speed_mps") or r.avg_speed_mps


@rule(PATTERN)
def pace_by_conditions(snap: DerivedSnapshot, thresholds: Thresholds, prior: list[InsightFact]) -> list[InsightFact]:
    """Runs once per cohort (carried / uncarried). The carried fact is keyed on the week subject, the uncarried on `athlete`."""
    return [f for carried in (False, True) for f in _pattern(snap, thresholds, carried)]


def _pattern(snap: DerivedSnapshot, thresholds: Thresholds, carried: bool) -> list[InsightFact]:
    th = thresholds.rule(PATTERN)
    runs = runs_between(snap, snap.as_of - timedelta(days=th["window_days"] - 1), snap.as_of, carried)
    warm, cool = [], []
    for r in runs:
        dew = (r.conditions or {}).get("dew_point_c")
        speed = _speed(r)
        band = (r.conditions or {}).get("band")
        if r.is_indoor or not r.is_easy_intended or dew is None or not speed or band in ("cold", "freezing"):
            continue  # icy and freezing runs are slow for other reasons
        (warm if dew >= th["dew_split_c"] else cool).append(speed)
    if len(warm) < th["min_runs"] or len(cool) < th["min_runs"]:
        return []
    slower = q((med(cool) / med(warm) - 1.0) * 100.0)
    if slower < th["change_pct"]:
        return []
    wid = week_id(snap.as_of)
    data = {
        "window_days": th["window_days"], "dew_split_c": th["dew_split_c"], "warm_runs": len(warm), "cool_runs": len(cool),
        "warm_speed_mps": round(med(warm), 3), "cool_speed_mps": round(med(cool), 3),
    }
    if carried:
        data["carried"] = True
    return [make_fact(
        PATTERN, week_subject(wid) if carried else ATHLETE, wid, "observation", r1(slower), "%",
        make_evidence(PATTERN, data, "A pattern across your own runs, not a rule; route, tiredness and time of day differ between runs too."),
        "pace-by-conditions-carry" if carried else "pace-by-conditions")]
