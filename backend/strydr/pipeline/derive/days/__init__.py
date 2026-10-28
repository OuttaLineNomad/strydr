"""derive/days: hard-day and rest-day classification (FR-18; AD-7 owner of both). Pure.

Hard day: >= 20 min at >= 88% of HRmax (summed across the day's workouts), or a long run.
Rest day: no run and only light activity. "Light" means the day's non-run load is at most 25% of the
runner's median run-day load over the previous 28 days. With no run-day history the fallback is:
<= 60 min of workouts, effort <= 4 and <= 150 m of climbing. So an easy walk is rest and a big hike
is an active day, not rest. Days without any workout are rest days.
"""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median
from typing import Any

from strydr.pipeline.derive.load.trimp import HrSample, LoadParams, hr_intervals


@dataclass(frozen=True, slots=True)
class DayParams:
    hard_hr_fraction: float
    hard_minutes: float
    light_load_fraction: float
    light_median_window_days: int
    fallback_max_minutes: float
    fallback_max_effort: float
    fallback_max_gain_m: float

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> "DayParams":
        return cls(
            hard_hr_fraction=m["hard_hr_fraction"],
            hard_minutes=m["hard_minutes"],
            light_load_fraction=m["light_load_fraction"],
            light_median_window_days=m["light_median_window_days"],
            fallback_max_minutes=m["fallback_max_minutes"],
            fallback_max_effort=m["fallback_max_effort"],
            fallback_max_gain_m=m["fallback_max_gain_m"],
        )


@dataclass(frozen=True, slots=True)
class DayWorkout:
    """One workout as `derive/days` sees it. `hard_s` comes from `hard_seconds()`."""

    type: str  # run | walk | hike
    duration_s: float
    load: float  # the workout's TRIMP from derive/load
    hard_s: float = 0.0
    is_long_run: bool = False  # from derive/summary
    effort_score: float | None = None
    elevation_gain_m: float | None = None


@dataclass(frozen=True, slots=True)
class DayClass:
    """One row of the analytic `day_class` table (zero-filled, one per local date)."""

    local_date: date
    has_run: bool
    is_hard: bool
    is_rest: bool
    kind: str  # run | active | rest
    load: float  # same daily number as derive/load
    hard_seconds: float
    reasons: tuple[str, ...] = field(default=())


def hard_seconds(
    samples: Sequence[HrSample], duration_s: float | None, hr_max: float, load_params: LoadParams,
    fraction: float,
) -> float:
    """Seconds of a workout spent at or above `fraction` x HRmax (gaps are not filled)."""
    cut = fraction * hr_max
    return sum(dt for hr, dt in hr_intervals(samples, duration_s, load_params) if hr >= cut)


def _light(workouts: Sequence[DayWorkout], load: float, run_day_loads: list[float], p: DayParams) -> bool:
    if run_day_loads:
        return load <= p.light_load_fraction * median(run_day_loads)
    return (
        sum(w.duration_s for w in workouts) <= p.fallback_max_minutes * 60
        and all((w.effort_score or 0) <= p.fallback_max_effort for w in workouts)
        and sum(w.elevation_gain_m or 0.0 for w in workouts) <= p.fallback_max_gain_m
    )


def classify_days(
    workouts_by_day: Mapping[date, Sequence[DayWorkout]], start: date, end: date, p: DayParams
) -> list[DayClass]:
    """Classify every local date in [start, end]. History before `start` feeds the median cap."""
    run_load: dict[date, float] = {}
    for d, ws in workouts_by_day.items():
        if any(w.type == "run" for w in ws):
            run_load[d] = sum(w.load for w in ws)
    out = []
    d = start
    while d <= end:
        ws = workouts_by_day.get(d, ())
        load = sum(w.load for w in ws)
        hard_s = sum(w.hard_s for w in ws)
        has_run = any(w.type == "run" for w in ws)
        reasons = []
        if hard_s >= p.hard_minutes * 60:
            reasons.append("time-at-high-hr")
        if any(w.is_long_run for w in ws):
            reasons.append("long-run")
        if has_run:
            kind = "run"
        else:
            window = [
                run_load[x]
                for x in (d - timedelta(days=k) for k in range(1, p.light_median_window_days + 1))
                if run_load.get(x, 0) > 0
            ]
            kind = "rest" if _light(ws, load, window, p) else "active"
        out.append(DayClass(d, has_run, bool(reasons), kind == "rest", kind, load, hard_s, tuple(reasons)))
        d += timedelta(days=1)
    return out
