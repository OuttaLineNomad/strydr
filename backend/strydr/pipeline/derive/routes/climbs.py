"""Auto-detected climbs on a route's reference run (FR-23). Pure: no DB, clock or I/O.

Detected on the reference run only, so boundaries are identical for every run on the route.
Elevation is smoothed first (watch altitude is noisy); ripples smaller than the pivot prominence
are ignored; climbs separated by a short dip are merged; then length, grade and gain are checked.
"""
import numpy as np

from strydr.pipeline.derive.routes.matching import RoutePath, RouteThresholds
from strydr.pipeline.derive.routes.sections import Section, make_section_id


def smooth(alt: np.ndarray, spacing_m: float, window_m: float) -> np.ndarray:
    """Centred moving average over at least `window_m`; shrinks at the ends instead of padding."""
    n = max(1, int(round(window_m / spacing_m)))
    if n % 2 == 0:
        n += 1
    k = np.ones(n)
    return np.convolve(alt, k, mode="same") / np.convolve(np.ones(len(alt)), k, mode="same")


def _fill_missing(alt: np.ndarray) -> np.ndarray | None:
    ok = ~np.isnan(alt)
    if ok.sum() < 2:
        return None
    return np.interp(np.arange(len(alt)), np.flatnonzero(ok), alt[ok])


def _pivots(v: np.ndarray, h: float) -> list[tuple[int, str]]:
    """Alternating valleys ('v') and peaks ('p') whose rise or fall is at least `h`."""
    piv: list[tuple[int, str]] = []
    imin = imax = 0
    direction = 0  # 0 undecided, 1 rising, -1 falling
    cur = 0
    for i in range(1, len(v)):
        if direction == 0:
            if v[i] < v[imin]:
                imin = i
            if v[i] > v[imax]:
                imax = i
            if v[i] - v[imin] >= h:
                piv.append((imin, "v"))
                direction, cur = 1, i
            elif v[imax] - v[i] >= h:
                piv.append((imax, "p"))
                direction, cur = -1, i
        elif direction == 1:
            if v[i] > v[cur]:
                cur = i
            elif v[cur] - v[i] >= h:
                piv.append((cur, "p"))
                direction, cur = -1, i
        else:
            if v[i] < v[cur]:
                cur = i
            elif v[i] - v[cur] >= h:
                piv.append((cur, "v"))
                direction, cur = 1, i
    if direction != 0:
        piv.append((cur, "p" if direction == 1 else "v"))
    return piv


def detect_climbs(
    route_key: str, cum: np.ndarray, alt: np.ndarray, th: RouteThresholds
) -> list[Section]:
    """Climb sections `{route_key}/c1`, `c2`, ... in route order, from a uniformly spaced profile."""
    cum = np.asarray(cum, dtype=float)
    filled = _fill_missing(np.asarray(alt, dtype=float))
    if filled is None or len(cum) < 3:
        return []
    spacing = float(np.median(np.diff(cum)))
    v = smooth(filled, spacing, th.smoothing_window_m)
    piv = _pivots(v, th.pivot_prominence_m)
    grade = np.diff(v) / spacing
    slack = 0.1 * th.pivot_prominence_m  # trim flat run-in / run-out off each leg
    min_flat = max(1, int(round(th.merge_gap_m / spacing)))
    legs = []
    for (a, ka), (b, kb) in zip(piv, piv[1:]):
        if ka != "v" or kb != "p":
            continue
        # a rise can pause on a plateau without ever falling: cut at flats as long as the merge gap
        cuts = [a]
        flat_from = None
        for i in range(a, b + 1):
            flat = i < b and grade[i] < th.flat_grade
            if flat and flat_from is None:
                flat_from = i
            elif not flat and flat_from is not None:
                if i - flat_from >= min_flat:
                    cuts += [flat_from, i]
                flat_from = None
        cuts.append(b)
        for lo, hi in zip(cuts[0::2], cuts[1::2]):
            if hi > lo:
                lo = lo + int(np.flatnonzero(v[lo:hi + 1] <= v[lo] + slack)[-1])
                hi = lo + int(np.flatnonzero(v[lo:hi + 1] >= v[hi] - slack)[0])
                legs.append((lo, hi))
    merged: list[list[int]] = []
    for a, b in legs:
        if merged and cum[a] - cum[merged[-1][1]] < th.merge_gap_m:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out: list[Section] = []
    for a, b in merged:
        length = float(cum[b] - cum[a])
        gain = float(v[b] - v[a])
        if length < th.min_length_m or gain < th.min_gain_m or gain / length < th.min_avg_grade:
            continue
        i = len(out) + 1
        out.append(Section(make_section_id(route_key, "c", i), route_key, "c", i,
                           float(cum[a]), float(cum[b]), gain))
    return out


def route_climbs(route_key: str, ref: RoutePath, th: RouteThresholds) -> list[Section]:
    """Climbs on a route's reference run."""
    return detect_climbs(route_key, ref.cum, ref.alt, th)
