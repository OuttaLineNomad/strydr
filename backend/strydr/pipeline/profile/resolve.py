"""Pure profile math (AD-7: the sole owner of HRmax, zones, easy ceiling and the resting-HR / HRV baselines)."""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
import math
from statistics import median, stdev

from ..hr import minute_bins

MIN_PAIR_COVERAGE_S = 45  # two adjacent minute bins must hold this much valid HR time between them
OBSERVED_WINDOW_DAYS = 365
OBSERVED_MIN_RUNS = 5  # fewer runs with HR and the observed value is not trusted yet (FR-31)
EASY_CEILING_BOUND = 2  # index into the four zone upper bounds: 80% of HRmax by default (FR-18)
RHR_PLAUSIBLE = (25.0, 130.0)
HRV_PLAUSIBLE = (5.0, 300.0)


@dataclass(frozen=True)
class HrmaxResult:
    hrmax: int | None
    source: str  # override|observed|tanaka|unavailable


def tanaka(birth_year: int, as_of: date) -> int:
    return round(208 - 0.7 * (as_of.year - birth_year))


def observed_hrmax(runs: Iterable[tuple[Sequence[float], Sequence[float]]]) -> int | None:
    """Highest average HR held for 2+ consecutive minutes, over (active clock, avg) columns of each run (`hr.active_clock`, so paused readings count for nothing).

    Each active-clock minute is the time-weighted mean of its samples; the best adjacent pair of minutes bounds
    every longer stretch, so a pair is enough."""
    best = None
    for t, avg in runs:
        bins = minute_bins(t, avg)
        for m, (a, wa) in bins.items():
            nxt = bins.get(m + 1)
            if nxt is not None and wa + nxt[1] >= MIN_PAIR_COVERAGE_S:
                pair = min(a, nxt[0])
                best = pair if best is None else max(best, pair)
    return round(best) if best is not None else None


def resolve_hrmax(override: int | None, observed: int | None, observed_runs: int,
                  birth_year: int | None, as_of: date) -> HrmaxResult:
    """Order (FR-31): the runner's override, the observed value, then Tanaka from birth year."""
    if override is not None:
        return HrmaxResult(override, "override")
    if observed is not None and observed_runs >= OBSERVED_MIN_RUNS:
        return HrmaxResult(observed, "observed")
    if birth_year is not None:
        return HrmaxResult(tanaka(birth_year, as_of), "tanaka")
    return HrmaxResult(None, "unavailable")


def zone_bounds_bpm(hrmax: int | None, bounds_pct: Sequence[float]) -> list[float] | None:
    return None if hrmax is None else [round(hrmax * p / 100, 1) for p in bounds_pct]


def easy_ceiling_bpm(bounds_bpm: Sequence[float] | None) -> float | None:
    return None if bounds_bpm is None else bounds_bpm[EASY_CEILING_BOUND]


def window_median(values: dict[str, float], as_of: date, days: int, plausible: tuple[float, float]) -> float | None:
    """Median of the daily values in the `days` local dates ending at as_of."""
    lo, hi = plausible
    start = as_of - timedelta(days=days - 1)
    vals = [v for d, v in values.items() if start.isoformat() <= d <= as_of.isoformat() and lo <= v <= hi]
    return float(median(vals)) if vals else None


@dataclass(frozen=True)
class BaselineStats:
    mean: float
    sd: float
    n_days: int


def _stats(vals: list[float]) -> BaselineStats | None:
    if not vals:
        return None
    return BaselineStats(sum(vals) / len(vals), stdev(vals) if len(vals) > 1 else 0.0, len(vals))


def _window(values: dict[str, float], last: date, days: int, plausible: tuple[float, float]) -> list[float]:
    lo, hi = plausible
    start = (last - timedelta(days=days - 1)).isoformat()
    return [v for d, v in values.items() if start <= d <= last.isoformat() and lo <= v <= hi]


def rhr_baseline(values: dict[str, float], as_of: date) -> BaselineStats | None:
    """Mean/SD over the 30 days ending the day before the last 3 days (FR-18)."""
    return _stats(_window(values, as_of - timedelta(days=3), 30, RHR_PLAUSIBLE))


def hrv_baseline(values: dict[str, float], as_of: date) -> BaselineStats | None:
    """Mean/SD of ln(SDNN) over the 60 days ending 7 days before as_of (FR-18)."""
    return _stats([math.log(v) for v in _window(values, as_of - timedelta(days=7), 60, HRV_PLAUSIBLE)])
