"""Pure geometry helpers: local-metre projection and fixed-spacing resampling (SI, no I/O)."""
import math

import numpy as np

EARTH_RADIUS_M = 6371008.8


def project(lat, lon, origin: tuple[float, float]) -> np.ndarray:
    """Equirectangular projection to metres east/north of `origin` (lat, lon). Shape (n, 2)."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    lat0, lon0 = origin
    x = np.radians(lon - lon0) * math.cos(math.radians(lat0)) * EARTH_RADIUS_M
    y = np.radians(lat - lat0) * EARTH_RADIUS_M
    return np.column_stack([x, y])


def unproject(xy, origin: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    """Inverse of `project`; returns (lat, lon)."""
    xy = np.asarray(xy, dtype=float)
    lat0, lon0 = origin
    lat = lat0 + np.degrees(xy[:, 1] / EARTH_RADIUS_M)
    lon = lon0 + np.degrees(xy[:, 0] / (EARTH_RADIUS_M * math.cos(math.radians(lat0))))
    return lat, lon


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def cumulative(xy: np.ndarray) -> np.ndarray:
    """Distance along the path at each vertex, starting at 0."""
    xy = np.asarray(xy, dtype=float)
    if len(xy) == 0:
        return np.zeros(0)
    steps = np.hypot(*np.diff(xy, axis=0).T) if len(xy) > 1 else np.zeros(0)
    return np.concatenate([[0.0], np.cumsum(steps)])


def path_length(xy: np.ndarray) -> float:
    cum = cumulative(xy)
    return float(cum[-1]) if len(cum) else 0.0


def resample(xy, spacing: float, extra=None):
    """Resample a path to `spacing` metres along its length, always keeping the end point.

    `extra` is an optional per-vertex value (NaN = missing) interpolated alongside; NaNs are
    skipped when interpolating. Returns (xy, cum, extra) with extra None when not given.
    """
    xy = np.asarray(xy, dtype=float)
    if len(xy) < 2:
        raise ValueError("need at least two points")
    cum = cumulative(xy)
    keep = np.concatenate([[True], np.diff(cum) > 0])  # drop repeated points so cum is increasing
    xy, cum = xy[keep], cum[keep]
    if len(xy) < 2:
        raise ValueError("path has zero length")
    total = float(cum[-1])
    targets = np.arange(0.0, total, spacing)
    if total - targets[-1] > 1e-9:
        targets = np.append(targets, total)
    out = np.column_stack([np.interp(targets, cum, xy[:, 0]), np.interp(targets, cum, xy[:, 1])])
    out_extra = None
    if extra is not None:
        ex = np.asarray(extra, dtype=float)[keep]
        ok = ~np.isnan(ex)
        out_extra = np.interp(targets, cum[ok], ex[ok]) if ok.sum() >= 2 else np.full(len(targets), np.nan)
    return out, targets, out_extra


def progress_along(line_xy, line_cum, pts_xy, corridor_m: float, window_back: int = 3, window_fwd: int = 60):
    """Monotone progress of a track along a reference polyline.

    For each point returns (s, off): `s` is the distance along the line of its nearest position
    (searched only a little behind and well ahead of the previous fix, so loops whose start and
    end coincide are not confused) and `off` is True when the point is farther than
    `corridor_m` from the line; off points keep the previous `s`.
    """
    line_xy = np.asarray(line_xy, dtype=float)
    pts_xy = np.asarray(pts_xy, dtype=float)
    nseg = len(line_xy) - 1
    a_all, b_all = line_xy[:-1], line_xy[1:]
    seglen = np.diff(line_cum)
    s_out = np.zeros(len(pts_xy))
    off = np.zeros(len(pts_xy), dtype=bool)
    idx = 0
    s_prev = 0.0

    def nearest(p, lo, hi):
        a, b = a_all[lo:hi], b_all[lo:hi]
        d = b - a
        L2 = np.maximum((d * d).sum(axis=1), 1e-12)
        t = np.clip(((p - a) * d).sum(axis=1) / L2, 0.0, 1.0)
        dist = np.hypot(*(a + d * t[:, None] - p).T)
        k = int(np.argmin(dist))
        return lo + k, float(dist[k]), float(line_cum[lo + k] + t[k] * seglen[lo + k])

    for i, p in enumerate(pts_xy):
        lo = max(0, idx - window_back)
        k, dist, s = nearest(p, lo, min(nseg, idx + window_fwd))
        if dist > corridor_m:
            k, dist, s = nearest(p, lo, nseg)  # lost the track: look anywhere ahead
        if dist > corridor_m:
            off[i] = True
            s_out[i] = s_prev
            continue
        s = max(s, s_prev)
        s_out[i], s_prev, idx = s, s, k
    return s_out, off
