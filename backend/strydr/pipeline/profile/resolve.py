"""Pure profile math (AD-7: the sole owner of HRmax, zones, easy ceiling and the resting-HR / HRV baselines)."""
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
import math
from statistics import median, stdev

EASY_CEILING_BOUND = 2  # index into the four zone upper bounds: 80% of HRmax by default (FR-18)
RHR_PLAUSIBLE = (25.0, 130.0)
HRV_PLAUSIBLE = (5.0, 300.0)


@dataclass(frozen=True)
class HrmaxResult:
    hrmax: int | None
    source: str  # override|tanaka|unavailable ("observed" only in rows from an older generation)


def tanaka(birth_year: int, as_of: date) -> int:
    return round(208 - 0.7 * (as_of.year - birth_year))


def resolve_hrmax(override: int | None, birth_year: int | None, as_of: date) -> HrmaxResult:
    """Order: the runner's override, then Tanaka from birth year. A measured maximum is never used."""
    if override is not None:
        return HrmaxResult(override, "override")
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
