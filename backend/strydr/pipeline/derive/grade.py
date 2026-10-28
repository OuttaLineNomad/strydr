"""Grade Adjusted Pace: the flat-ground speed of the same effort. Pure: no DB, clock or I/O.

Energy cost of running on a gradient is Minetti et al. 2002 (J Appl Physiol 93:1039), normalised to flat.
Grade is taken over a smoothed altitude profile and a 100 m baseline, clamped to -10%..+15% so a noisy
altitude step or a steep stair never dominates. Minetti's curve is convex, so altitude noise alone inflates the
flat-equivalent distance; the long baseline, a 3 m hysteresis on relief and the relief gates keep jitter from
reading as hills. The adjustment is a ratio of distances along the same track (flat-equivalent / actual) applied
to the watch's own speed, so a GPS track that disagrees with the watch never shows up as "hill".
"""
from bisect import bisect_left
from collections.abc import Sequence

from strydr.pipeline.derive.track import interp

BASE_M = 100.0
SMOOTH_M = 40.0
GRADE_MIN, GRADE_MAX = -0.10, 0.15
MIN_RELIEF_M = 8.0
HYSTERESIS_M = 3.0  # a rise or fall smaller than this is altitude jitter, not terrain
HILLY_M_PER_KM = 8.0


def cost_ratio(g: float) -> float:
    """Minetti's cost of running at grade g (fraction) over the cost on the flat."""
    g = min(GRADE_MAX, max(GRADE_MIN, g))
    c = 155.4 * g**5 - 30.4 * g**4 - 43.3 * g**3 + 46.3 * g**2 + 19.5 * g + 3.6
    return c / 3.6


def _smoothed(dist: Sequence[float], alt: Sequence[float | None]) -> list[float] | None:
    pts = [(d, a) for d, a in zip(dist, alt) if a is not None]
    if len(pts) < 2:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    filled = [interp(xs, ys, d) for d in dist]
    # Moving average over distance (not samples), so a stop does not stretch the window.
    out, lo, hi, acc = [], 0, 0, 0.0
    for i, d in enumerate(dist):
        while hi < len(dist) and dist[hi] <= d + SMOOTH_M / 2:
            acc += filled[hi]
            hi += 1
        while dist[lo] < d - SMOOTH_M / 2:
            acc -= filled[lo]
            lo += 1
        out.append(acc / (hi - lo))
    return out


def _flat(dist: Sequence[float], sm: Sequence[float]) -> list[float]:
    """Cumulative flat-equivalent distance along the track (same length as `dist`)."""
    out = [0.0]
    for i in range(1, len(dist)):
        mid = (dist[i] + dist[i - 1]) / 2
        a = interp(dist, sm, min(dist[-1], mid + BASE_M / 2))
        b = interp(dist, sm, max(0.0, mid - BASE_M / 2))
        span = min(dist[-1], mid + BASE_M / 2) - max(0.0, mid - BASE_M / 2)
        g = (a - b) / span if span > 0 else 0.0
        out.append(out[-1] + (dist[i] - dist[i - 1]) * cost_ratio(g))
    return out


def _relief(dist: Sequence[float], sm: Sequence[float], d0: float, d1: float) -> float:
    """Total climb plus descent of the smoothed profile between d0 and d1, ignoring jitter under HYSTERESIS_M."""
    i, j = bisect_left(dist, d0), bisect_left(dist, d1)
    seg = sm[i:j + 1]
    if not seg:
        return 0.0
    total, anchor = 0.0, seg[0]
    for a in seg[1:]:
        if abs(a - anchor) >= HYSTERESIS_M:
            total += abs(a - anchor)
            anchor = a
    return total


def gap_speed(dist: Sequence[float], flat: Sequence[float], d0: float, d1: float, speed_mps: float | None) -> float | None:
    """The split's own speed scaled by its flat-equivalent / actual distance ratio along the track."""
    if not speed_mps or d1 <= d0:
        return None
    return speed_mps * (interp(dist, flat, d1) - interp(dist, flat, d0)) / (d1 - d0)


def add_to_splits(splits: list[dict], dist: Sequence[float], alt: Sequence[float | None]) -> None:
    """Sets `gap_speed_mps` on each split in place: None when flat or without altitude."""
    sm = _smoothed(dist, alt)
    flat = _flat(dist, sm) if sm is not None else None
    d0 = 0.0
    for s in splits:
        d1 = d0 + s["distance_m"]
        hilly = flat is not None and _relief(dist, sm, d0, d1) >= MIN_RELIEF_M
        s["gap_speed_mps"] = gap_speed(dist, flat, d0, d1, s.get("speed_mps")) if hilly else None
        d0 = d1


def run_gap(dist: Sequence[float], alt: Sequence[float | None], speed_mps: float | None) -> dict | None:
    """Whole-run GAP (the watch's speed times the track's flat-equivalent ratio) and relief, or None."""
    sm = _smoothed(dist, alt)
    if sm is None or not speed_mps or dist[-1] <= 0:
        return None
    flat, relief = _flat(dist, sm), _relief(dist, sm, 0.0, dist[-1])
    per_km = relief / (dist[-1] / 1000)
    return {"gap_speed_mps": round(speed_mps * flat[-1] / dist[-1], 4), "relief_m": round(relief, 1),
            "relief_m_per_km": round(per_km, 1), "hilly": relief >= 2 * MIN_RELIEF_M and per_km >= HILLY_M_PER_KM}
