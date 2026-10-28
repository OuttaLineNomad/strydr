"""Display formatting for the run context payload: a mirror of `web/src/lib/units.ts` and `sleep.ts`.

The AI's numbers are checked against these strings as written, so they must match what the run page shows. Every
function takes SI values and the runner's `units` ("km" or "mi") and returns None for a missing value. Kept apart
from `insights/templates/_format.py`, whose "84 °F" is template wording.
"""
import math

METERS_PER_MILE = 1609.344
FEET_PER_METER = 3.280839895
MINUS = "−"


def finite(v: object) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v)


def js_round(x: float) -> int:
    """JavaScript's Math.round: halves go up, not to even."""
    return math.floor(x + 0.5)


def _imperial(units: str) -> bool:
    return units == "mi"


def clock(total_s: float) -> str:
    if not finite(total_s):
        return "0:00"
    s = js_round(total_s)
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h > 0 else f"{m}:{sec:02d}"


def pace_s(speed_mps: float | None, units: str) -> float | None:
    if not finite(speed_mps) or speed_mps <= 0:
        return None
    return (METERS_PER_MILE if _imperial(units) else 1000.0) / speed_mps


def pace(speed_mps: float | None, units: str) -> str | None:
    p = pace_s(speed_mps, units)
    return None if p is None else f"{clock(p)} /{units}"


def pace_from_s(seconds: float | None, units: str) -> str | None:
    return None if not finite(seconds) or seconds <= 0 else f"{clock(seconds)} /{units}"


def distance(meters: float | None, units: str, digits: int = 1) -> str | None:
    if not finite(meters):
        return None
    return f"{meters / (METERS_PER_MILE if _imperial(units) else 1000.0):.{digits}f} {units}"


def elevation(meters: float | None, units: str, signed: bool = False) -> str | None:
    if not finite(meters):
        return None
    n = js_round(meters * FEET_PER_METER if _imperial(units) else meters)
    return _sign(n, signed) + f"{abs(n) if signed else n} {'ft' if _imperial(units) else 'm'}"


def relief_per_unit(m_per_km: float | None, units: str) -> str | None:
    """Relief per distance unit, in the elevation unit: '12 m/km' or '63 ft/mi'."""
    if not finite(m_per_km):
        return None
    if _imperial(units):
        return f"{js_round(m_per_km * FEET_PER_METER * METERS_PER_MILE / 1000.0)} ft/mi"
    return f"{js_round(m_per_km)} m/km"


def temperature(c: float | None, units: str) -> str | None:
    if not finite(c):
        return None
    return f"{js_round(c * 9 / 5 + 32)}°F" if _imperial(units) else f"{js_round(c)}°C"


def wind(mps: float | None, units: str) -> str | None:
    if not finite(mps):
        return None
    return f"{js_round(mps * 2.236936)} mph" if _imperial(units) else f"{js_round(mps * 3.6)} km/h"


def duration(seconds: float | None) -> str | None:
    return None if not finite(seconds) else clock(seconds)


def hours(h: float | None) -> str | None:
    """'4h 16m' from hours, as `formatHours` in sleep.ts."""
    if not finite(h):
        return None
    m = js_round(h * 60)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def signed_hours(h: float | None) -> str | None:
    if not finite(h):
        return None
    n = js_round(h * 60)
    return _sign(n, True) + hours(abs(h))


def bpm(v: float | None) -> str | None:
    return None if not finite(v) else f"{js_round(v)} bpm"


def percent(v: float | None) -> str | None:
    return None if not finite(v) else f"{js_round(v)}%"


def whole(v: float | None, unit: str = "") -> str | None:
    return None if not finite(v) else f"{js_round(v)}{' ' + unit if unit else ''}"


def signed_whole(v: float | None, unit: str = "") -> str | None:
    if not finite(v):
        return None
    n = js_round(v)
    return _sign(n, True) + f"{abs(n)}{' ' + unit if unit else ''}"


def _sign(n: int, signed: bool) -> str:
    return (MINUS if n < 0 else "+" if n > 0 else "") if signed else ""


def pace_delta(seconds: float | None, units: str) -> str | None:
    """A signed pace difference: '+0:08 /mi' (slower) or '−0:08 /mi' (faster)."""
    if not finite(seconds):
        return None
    n = js_round(seconds)
    return _sign(n, True) + f"{clock(abs(n))} /{units}"
