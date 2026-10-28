"""Helpers shared by the tier-1 rules."""
from datetime import date, timedelta
from statistics import median

from ..models import DerivedSnapshot, InsightFact, RunSummary
from ..thresholds import Thresholds


def lookback_start(snap: DerivedSnapshot, th: Thresholds) -> date:
    """First day (inclusive) of the per-run / per-day evaluation window ending at as_of."""
    return snap.as_of - timedelta(days=th.section("engine")["run_lookback_days"] - 1)


def recent_runs(snap: DerivedSnapshot, th: Thresholds) -> list[RunSummary]:
    lo = lookback_start(snap, th)
    return sorted(
        (r for r in snap.runs if lo <= r.local_date <= snap.as_of), key=lambda r: (r.local_date, r.workout_id)
    )


def runs_between(snap: DerivedSnapshot, first: date, last: date) -> list[RunSummary]:
    """Runs with first <= local_date <= last."""
    return [r for r in snap.runs if first <= r.local_date <= last]


def has_check_reading(prior: list[InsightFact]) -> bool:
    """Attaboys never fire alongside a 'check this reading' escalation (research-thresholds 7)."""
    return any(f.kind == "check-reading" for f in prior)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def q(x: float) -> float:
    """Round away float noise before comparing against a threshold (11000/10000 - 1 is not exactly 0.1)."""
    return round(x, 6)


def r1(x: float) -> float:
    return round(x, 1)


def med(xs: list[float]) -> float:
    return float(median(xs))
