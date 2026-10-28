"""Daily load, fitness/fatigue/form EWMAs (FR-24) and the training state (FR-24b). Pure functions.

Recurrence (daily, zero-load days included). Both averages start at the mean daily load of the first
`seed_days` days (research-load 3.1; `seed_days=0` seeds at 0), so form is not biased by a cold start:
    fitness_t = fitness_{t-1} + (L_t - fitness_{t-1}) / 42
    fatigue_t = fatigue_{t-1} + (L_t - fatigue_{t-1}) / 7
    form_t    = fitness_{t-1} - fatigue_{t-1}   (the morning of day t)
    form_pct  = form_t / fitness_{t-1} * 100
The first `warmup_days` days of the series are flagged `warmup`.
"""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .fallback import WorkoutLoad

LOAD_TYPES = ("run", "walk", "hike")
STATES = ("Building", "Holding", "Easing", "Overreaching")


@dataclass(frozen=True, slots=True)
class DailyLoad:
    """One row of the analytic `daily_load` table: the single daily number (FR-14 = FR-24)."""

    local_date: date
    total: float
    by_type: Mapping[str, float]  # stacked: run / walk / hike
    estimated: bool  # any contributing workout load is an estimate
    n_workouts: int


@dataclass(frozen=True, slots=True)
class FitnessDay:
    local_date: date
    load: float
    fitness: float
    fatigue: float
    form: float | None  # None on the first day (no previous fitness)
    form_pct: float | None
    warmup: bool
    estimated: bool
    n_workouts: int


@dataclass(frozen=True, slots=True)
class TrainingStateDay:
    local_date: date
    raw_state: str | None  # the state before hysteresis
    state: str | None  # the label shown; None = not enough recent training / warm-up
    since: date | None  # first day of the confirmed state: the insight's episode start (AD-6)
    ramp_pct: float | None  # weekly change in fitness
    form_pct: float | None
    detail: Mapping[str, Any] = field(default_factory=dict)


def daily_loads(loads: Sequence[WorkoutLoad], start: date, end: date) -> list[DailyLoad]:
    """One entry per local date in [start, end]; days without a workout are an explicit zero."""
    by_day: dict[date, list[WorkoutLoad]] = {}
    for w in loads:
        by_day.setdefault(w.local_date, []).append(w)
    out = []
    d = start
    while d <= end:
        ws = by_day.get(d, [])
        by_type = {t: sum(w.trimp for w in ws if w.type == t) for t in LOAD_TYPES}
        out.append(DailyLoad(d, sum(by_type.values()), by_type, any(w.estimated for w in ws), len(ws)))
        d += timedelta(days=1)
    return out


def fitness_fatigue(
    days: Sequence[DailyLoad], tau_fitness: float, tau_fatigue: float, warmup_days: int, seed_days: int = 0
) -> list[FitnessDay]:
    head = [d.total for d in days[:seed_days]]
    fitness = fatigue = sum(head) / len(head) if head else 0.0
    out: list[FitnessDay] = []
    for i, day in enumerate(days):
        form = fitness - fatigue if (i > 0 or seed_days) else None
        form_pct = form / fitness * 100.0 if form is not None and fitness > 1e-9 else None
        fitness += (day.total - fitness) / tau_fitness
        fatigue += (day.total - fatigue) / tau_fatigue
        out.append(
            FitnessDay(day.local_date, day.total, fitness, fatigue, form, form_pct, i < warmup_days,
                       day.estimated, day.n_workouts)
        )
    return out


def _raw_state(days: Sequence[FitnessDay], i: int, p: Mapping[str, Any]) -> tuple[str | None, float | None, dict]:
    """The FR-24b state for day index i before hysteresis, plus the weekly fitness change."""
    day = days[i]
    ramp = _ramp(days, i)
    detail: dict[str, Any] = {}
    if day.warmup or ramp is None:
        return None, ramp, {"reason": "warm-up"}
    lo = max(0, i - p["fitness_max_window_days"] + 1)
    peak = max(d.fitness for d in days[lo : i + 1])
    sessions = sum(d.n_workouts for d in days[max(0, i - 13) : i + 1])
    if day.fitness < p["min_fitness_fraction_of_max"] * peak or sessions < p["min_sessions_14d"]:
        return None, ramp, {"reason": "not enough recent training"}
    window = days[max(0, i - p["overreach_form_window"] + 1) : i + 1]
    low_form = sum(1 for d in window if d.form_pct is not None and d.form_pct <= p["overreach_form_pct"])
    detail["low_form_days"] = low_form
    ramp_streak = all(
        (r := _ramp(days, i - 7 * k)) is not None and r > p["overreach_ramp_pct"]
        for k in range(p["overreach_ramp_weeks"])
    )
    if low_form >= p["overreach_form_days"] or ramp_streak:
        return "Overreaching", ramp, detail
    if ramp >= p["building_ramp_pct"]:
        return "Building", ramp, detail
    if ramp <= p["easing_ramp_pct"]:
        return "Easing", ramp, detail
    return "Holding", ramp, detail


def _ramp(days: Sequence[FitnessDay], i: int) -> float | None:
    if i < 7:
        return None
    before = days[i - 7].fitness
    if before <= 1e-9:
        return None
    return (days[i].fitness - before) / before * 100.0


def apply_hysteresis(raw: Sequence[str | None], need: int) -> list[tuple[str | None, int | None]]:
    """Smooth raw daily states: the label changes only after `need` consecutive days in the new state.

    Returns (state, since_index) per day, where `since_index` is the index of the first day of the
    confirmed state. The first computable state is adopted at once; None (no state) resets everything.
    """
    out: list[tuple[str | None, int | None]] = []
    state: str | None = None
    since: int | None = None
    cand: str | None = None
    cand_start = 0
    cand_n = 0
    for i, r in enumerate(raw):
        if r is None:
            state, since, cand, cand_n = None, None, None, 0
        elif state is None:
            state, since, cand, cand_n = r, i, None, 0
        elif r == state:
            cand, cand_n = None, 0
        else:
            if r == cand:
                cand_n += 1
            else:
                cand, cand_start, cand_n = r, i, 1
            if cand_n >= need:
                state, since, cand, cand_n = r, cand_start, None, 0
        out.append((state, since))
    return out


def training_states(days: Sequence[FitnessDay], p: Mapping[str, Any]) -> list[TrainingStateDay]:
    """Training state per day with hysteresis (`training-state` thresholds section `p`).

    The reported `since` is the first day of the confirmed run, so the insight key stays fixed while
    the state lasts.
    """
    raws = [_raw_state(days, i, p) for i in range(len(days))]
    smoothed = apply_hysteresis([r[0] for r in raws], p["hysteresis_days"])
    return [
        TrainingStateDay(
            day.local_date, raw, state, None if since is None else days[since].local_date, ramp, day.form_pct, detail
        )
        for day, (raw, ramp, detail), (state, since) in zip(days, raws, smoothed)
    ]


def acwr(days: Sequence[DailyLoad], i: int, acute: int = 7, chronic: int = 28) -> float | None:
    """Acute:chronic mean daily load. Tooltip context only, never a risk score (FR-24c)."""
    if i + 1 < chronic:
        return None
    base = sum(d.total for d in days[i + 1 - chronic : i + 1]) / chronic
    if base <= 1e-9:
        return None
    return sum(d.total for d in days[i + 1 - acute : i + 1]) / acute / base
