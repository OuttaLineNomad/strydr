"""Same-HR section comparison and the FR-23a firing decision. Pure: no DB, clock or I/O.

Compares a run's section against earlier runs on the same route (and so the same direction: a
reverse run is a different route) in the window before `as_of`, using only past runs whose section
HR is within +-`hr_match_bpm` of this run's. Gap is positive when the run was slower.
"""
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Sequence

import numpy as np

from strydr.pipeline.derive.routes.matching import RouteThresholds
from strydr.pipeline.derive.routes.sections import SectionMeasure, hr_claim_allowed

MAD_TO_SIGMA = 1.4826


@dataclass(frozen=True)
class SectionObs:
    """One run's result on one section, as stored in the analytic tier."""

    section_id: str
    workout_id: str
    local_date: date
    time_s: float | None
    avg_hr: float | None
    comparable: bool = True
    excluded: bool = False  # user marked the run race / workout / intervals


def observations(
    workout_id: str, local_date: date, measures: Iterable[SectionMeasure], excluded: bool = False
) -> list[SectionObs]:
    return [
        SectionObs(m.section_id, workout_id, local_date, m.time_s, m.avg_hr, m.comparable, excluded)
        for m in measures
    ]


@dataclass(frozen=True)
class SectionComparison:
    section_id: str
    workout_id: str
    n: int  # HR-matched past runs
    baseline_time_s: float | None  # median of the matched runs
    baseline_hr: float | None
    time_s: float | None
    avg_hr: float | None
    gap_s: float | None  # time - baseline; positive = slower
    spread_s: float | None  # robust spread (1.4826 x MAD) of the matched times
    z: float | None  # |gap| / spread; None when the spread is 0
    direction: str | None  # slower | faster
    fires: bool
    reasons: tuple[str, ...] = field(default=())  # checks that failed


def compare_section(
    current: SectionObs,
    history: Sequence[SectionObs],
    as_of: date,
    th: RouteThresholds,
) -> SectionComparison:
    """Compare `current` with matched-HR past runs of the same section and decide whether it fires."""

    def result(n=0, base_t=None, base_hr=None, gap=None, spread=None, z=None, fires=False, reasons=()):
        direction = None if gap is None else ("slower" if gap > 0 else "faster")
        return SectionComparison(
            current.section_id, current.workout_id, n, base_t, base_hr, current.time_s, current.avg_hr,
            gap, spread, z, direction, fires, tuple(reasons),
        )

    if not current.comparable or current.time_s is None:
        return result(reasons=["section not comparable"])
    if current.avg_hr is None:
        return result(reasons=["no HR for section"])

    earliest = as_of - timedelta(days=th.window_days)
    key = (current.local_date, current.workout_id)
    pool = [
        h for h in history
        if h.section_id == current.section_id and h.workout_id != current.workout_id
        and h.comparable and not h.excluded and h.time_s is not None and h.avg_hr is not None
        and earliest <= h.local_date <= as_of and (h.local_date, h.workout_id) < key
    ]
    reasons: list[str] = []
    if not hr_claim_allowed([current.time_s] + [h.time_s for h in pool], th):
        reasons.append("section too short for HR claims")

    matched = [h for h in pool if abs(h.avg_hr - current.avg_hr) <= th.hr_match_bpm]
    n = len(matched)
    if n == 0:
        return result(reasons=reasons + ["no HR-matched runs"])
    times = np.array([h.time_s for h in matched], dtype=float)
    base_t = float(np.median(times))
    spread = float(MAD_TO_SIGMA * np.median(np.abs(times - base_t)))
    base_hr = float(np.mean([h.avg_hr for h in matched]))
    gap = current.time_s - base_t
    z = abs(gap) / spread if spread > 0 else None

    if n < th.compare_min_runs:
        reasons.append("too few matched runs")
    if abs(gap) < max(th.min_gap_s, th.min_gap_frac * base_t):
        reasons.append("gap too small")
    z_min = th.z_min_small_n if n < th.small_n_below else th.z_min
    if abs(gap) < z_min * spread:
        reasons.append("gap within run-to-run spread")
    return result(n, base_t, base_hr, gap, spread, z, not reasons, reasons)


def compare_run(
    current: Sequence[SectionObs],
    history: Sequence[SectionObs],
    as_of: date,
    th: RouteThresholds,
) -> list[SectionComparison]:
    """Compare every section of one run; at most `max_per_run` of them fire, strongest first."""
    comps = [compare_section(c, history, as_of, th) for c in current]
    comps.sort(key=lambda c: c.section_id)
    firing = sorted((c for c in comps if c.fires), key=lambda c: (-(math.inf if c.z is None else c.z), c.section_id))
    keep = {c.section_id for c in firing[: th.max_per_run]}
    return [c if (not c.fires or c.section_id in keep) else _suppressed(c) for c in comps]


def _suppressed(c: SectionComparison) -> SectionComparison:
    return SectionComparison(
        c.section_id, c.workout_id, c.n, c.baseline_time_s, c.baseline_hr, c.time_s, c.avg_hr,
        c.gap_s, c.spread_s, c.z, c.direction, False, ("over per-run budget",),
    )
