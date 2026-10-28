"""Pure helpers over a GPS track's columns (`t`, `lat`, `lon`, `alt`); coordinates never leave this layer."""
import math
from bisect import bisect_left
from collections.abc import Sequence

EARTH_RADIUS_M = 6_371_000.0


def cumulative_m(lat: Sequence[float], lon: Sequence[float]) -> list[float]:
    out = [0.0]
    for i in range(1, len(lat)):
        p1, p2 = math.radians(lat[i - 1]), math.radians(lat[i])
        a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon[i] - lon[i - 1]) / 2) ** 2
        out.append(out[-1] + 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a)))
    return out


def interp(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
    """Linear interpolation of ys at x; xs is non-decreasing."""
    j = bisect_left(xs, x)
    if j <= 0:
        return ys[0]
    if j >= len(xs):
        return ys[-1]
    span = xs[j] - xs[j - 1]
    return ys[j] if span <= 0 else ys[j - 1] + (ys[j] - ys[j - 1]) * (x - xs[j - 1]) / span


def splits(dist: Sequence[float], t: Sequence[float], alt: Sequence[float | None], hr_t: Sequence[float],
           hr_avg: Sequence[float], size_m: float, min_partial_m: float = 100.0) -> list[dict]:
    """Fixed-distance splits. The last one is partial when the run does not end on a boundary."""
    total = dist[-1]
    out = []
    k = 0
    while k * size_m < total:
        d0, d1 = k * size_m, min((k + 1) * size_m, total)
        if d1 - d0 < size_m and d1 - d0 < min_partial_m:
            break
        t0, t1 = interp(dist, t, d0), interp(dist, t, d1)
        in_split = [a for ht, a in zip(hr_t, hr_avg) if t0 <= ht < t1]
        a0, a1 = _alt_near(dist, alt, d0), _alt_near(dist, alt, d1)
        out.append({
            "index": k, "distance_m": d1 - d0, "duration_s": t1 - t0,
            "speed_mps": (d1 - d0) / (t1 - t0) if t1 > t0 else None,
            "avg_hr": sum(in_split) / len(in_split) if in_split else None,
            "elevation_change_m": a1 - a0 if a0 is not None and a1 is not None else None,
            "partial": d1 - d0 < size_m,
        })
        k += 1
    return out


def source_splits(own: dict, unit: str, dist: Sequence[float], alt: Sequence[float | None]) -> list[dict]:
    """The watch's own splits for `unit` ("km" or "mi"); elevation change comes from the track."""
    size = 1000.0 if unit == "km" else 1609.344
    rows = sorted((i, d, t, h) for u, i, d, t, h in zip(own["unit"], own["index"], own["distance_m"], own["duration_s"], own["avg_hr"])
                  if u == unit)
    out, d0 = [], 0.0
    for i, d, t, h in rows:
        a0, a1 = _alt_near(dist, alt, d0), _alt_near(dist, alt, d0 + d)
        out.append({
            "index": i, "distance_m": d, "duration_s": t, "speed_mps": d / t if t > 0 else None, "avg_hr": h,
            "elevation_change_m": a1 - a0 if a0 is not None and a1 is not None else None,
            "partial": d < size - 1.0,
        })
        d0 += d
    return out


def _alt_near(dist: Sequence[float], alt: Sequence[float | None], d: float) -> float | None:
    i = min(bisect_left(dist, d), len(dist) - 1)
    for j in sorted(range(max(0, i - 5), min(len(dist), i + 6)), key=lambda x: abs(x - i)):
        if alt[j] is not None:
            return alt[j]
    return None


def pace_series(dist: Sequence[float], t: Sequence[float], max_points: int = 240) -> list[dict]:
    """Speed per time bin, so the chart is smooth without storing the 1 Hz track."""
    span = t[-1] - t[0]
    if span <= 0:
        return []
    step = max(5.0, math.ceil(span / max_points))
    out, edge = [], t[0]
    while edge < t[-1]:
        end = min(edge + step, t[-1])
        d0, d1 = interp(t, dist, edge), interp(t, dist, end)
        out.append({"t_s": edge + (end - edge) / 2, "distance_m": d1,
                    "speed_mps": (d1 - d0) / (end - edge) if end > edge else None})
        edge = end
    return out


def elevation_series(dist: Sequence[float], alt: Sequence[float | None], max_points: int = 300) -> list[dict]:
    pts = [(d, a) for d, a in zip(dist, alt) if a is not None]
    stride = max(1, math.ceil(len(pts) / max_points))
    return [{"distance_m": d, "altitude_m": a} for d, a in pts[::stride]]


MAX_GAP_S = 30.0  # a longer GPS gap inside a window disqualifies it as a best effort


def best_time(dist: Sequence[float], t: Sequence[float], target_m: float, max_speed_mps: float = 12.0) -> float | None:
    """Fastest time over target_m starting at any sample, or None. Windows spanning a GPS dropout are skipped."""
    n = len(dist)
    gaps = [0]
    for i in range(1, n):
        gaps.append(gaps[-1] + (t[i] - t[i - 1] > MAX_GAP_S))
    best = None
    for i in range(n):
        j = bisect_left(dist, dist[i] + target_m, lo=i)
        if j >= n:
            break
        if gaps[j] - gaps[i]:
            continue
        end = interp(dist, t, dist[i] + target_m)
        elapsed = end - t[i]
        if elapsed < target_m / max_speed_mps:
            continue
        if best is None or elapsed < best:
            best = elapsed
    return best
