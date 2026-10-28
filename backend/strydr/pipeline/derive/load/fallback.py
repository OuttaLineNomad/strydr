"""Per-workout load with the FR-24a missing-HR fallback chain.

Order: (1) >=80% HR coverage -> scale the measured TRIMP to the full duration; (2) average HR x
duration; (3) duration x the runner's own median load per minute for that type (runs: pace-banded);
(4) duration x a default intensity by type. An RPE from the run note overrides any estimated result.
Every estimate is flagged `estimated`.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from statistics import median

from .trimp import (
    HrSample,
    LoadParams,
    covered_seconds,
    hr_intervals,
    trimp_constant_hr,
    trimp_from_intervals,
    trimp_per_min,
)


@dataclass(frozen=True, slots=True)
class WorkoutLoadInput:
    """What the load model needs from one workout (canonical `workout` + its HR series + the note RPE)."""

    workout_id: str
    type: str  # run | walk | hike
    local_date: date
    duration_s: float | None
    avg_hr: float | None = None
    avg_speed_mps: float | None = None
    hr_samples: Sequence[HrSample] | None = None  # (t_s, avg HR) from the heart_rate series
    rpe: float | None = None  # workout_note.rpe, 1-10


@dataclass(frozen=True, slots=True)
class WorkoutLoad:
    """One row of the analytic `workout_load` table. Parameters are stored with the value (research-load 2.2)."""

    workout_id: str
    type: str
    local_date: date
    trimp: float
    estimated: bool
    source: str  # hr | hr-scaled | avg-hr | personal-rate | default | rpe | none
    coverage: float | None  # share of the duration with usable HR samples
    duration_s: float | None
    avg_speed_mps: float | None
    hr_max: float
    hr_rest: float
    b: float


def _interp(points: tuple[tuple[float, float], ...], x: float) -> float:
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def _pace(speed_mps: float | None) -> float | None:
    return 1000.0 / speed_mps if speed_mps and speed_mps > 0 else None


def personal_rate(
    inp: WorkoutLoadInput, history: Sequence[WorkoutLoad], params: LoadParams
) -> float | None:
    """Median TRIMP/min of the runner's own HR-backed sessions of this type, or None when too few."""
    pool = [
        h
        for h in history
        if h.type == inp.type
        and not h.estimated
        and h.duration_s
        and 0 < (inp.local_date - h.local_date).days <= params.history_window_days
    ]
    if len(pool) < params.history_min_sessions:
        return None
    if inp.type == "run":
        pace = _pace(inp.avg_speed_mps)
        if pace is not None:
            banded = [
                h
                for h in pool
                if (hp := _pace(h.avg_speed_mps)) is not None
                and abs(hp - pace) <= params.pace_band_s_per_km
            ]
            if len(banded) >= params.history_min_sessions:
                pool = banded
    return median(h.trimp / (h.duration_s / 60.0) for h in pool)


def compute_workout_load(
    inp: WorkoutLoadInput,
    *,
    hr_max: float,
    hr_rest: float | None,
    sex: str | None,
    params: LoadParams,
    history: Sequence[WorkoutLoad] = (),
) -> WorkoutLoad:
    """`hr_rest` is the 7-day rolling median of resting HR as of the workout date (passed in)."""
    rest = params.default_resting_hr if hr_rest is None else hr_rest
    b = params.b_for(sex)
    samples = list(inp.hr_samples or ())
    duration = inp.duration_s
    if not duration and samples:
        intervals_all = hr_intervals(samples, None, params)
        duration = covered_seconds(intervals_all) or None
    intervals = hr_intervals(samples, duration, params) if samples else []

    def make(trimp: float, estimated: bool, source: str, coverage: float | None) -> WorkoutLoad:
        return WorkoutLoad(
            inp.workout_id, inp.type, inp.local_date, trimp, estimated, source, coverage,
            duration, inp.avg_speed_mps, hr_max, rest, b,
        )

    if not duration:
        return make(0.0, True, "none", None)

    coverage = covered_seconds(intervals) / duration if intervals else 0.0
    if coverage >= params.tier_a_min_coverage:
        measured = trimp_from_intervals(intervals, hr_max, rest, b)
        scaled = measured * duration / covered_seconds(intervals)
        est = coverage < params.full_coverage
        result = make(scaled, est, "hr-scaled" if est else "hr", min(coverage, 1.0))
    elif inp.avg_hr is not None and params.hr_floor_bpm <= inp.avg_hr <= params.hr_ceiling_bpm:
        result = make(trimp_constant_hr(inp.avg_hr, duration, hr_max, rest, b), True, "avg-hr", coverage)
    elif (rate := personal_rate(inp, history, params)) is not None:
        result = make(rate * duration / 60.0, True, "personal-rate", coverage)
    else:
        x = params.default_hrr_fraction.get(inp.type, params.default_hrr_fraction["run"])
        result = make(duration / 60.0 * trimp_per_min(x, b), True, "default", coverage)

    if inp.rpe is not None and result.estimated:
        x = _interp(params.rpe_hrr, inp.rpe)
        return make(duration / 60.0 * trimp_per_min(x, b), True, "rpe", result.coverage)
    return result
