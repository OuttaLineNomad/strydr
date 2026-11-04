"""Run/walk split of a run (CAP-19). Pure functions.

A run is cut into 10 s windows on the active clock (paused time adds nothing). Each window is classed as running,
walking or stopped. Cadence (steps per minute from the `step_count` series) is compared with a cutoff learned from
all the runner's windows; pace stands in for a run that has no steps. Only percentages, the cutoff and walk time
ranges leave this module: the raw step series never does."""
import bisect
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

WINDOW_S = 10.0
MAX_SPM = 250.0  # a window above this is a glitch and counts as no cadence
STOPPED_SPM = 60.0  # under this cadence, while recording, the runner is standing
STOPPED_MPS = 0.5  # the same, by speed
CUTOFF_RANGE_SPM = (110.0, 150.0)
DEFAULT_CUTOFF_SPM = 130.0
MIN_HISTORY_S = 30 * 60.0
PACE_RANGE_MPS = (1.5, 2.7)
DEFAULT_PACE_CUTOFF_MPS = 1609.344 / (13 * 60)  # 13:00 per mile
BIN_SPM = 5.0
BIN_MPS = 0.1
MIN_PEAK_GAP_SPM = 20.0
MIN_PEAK_GAP_MPS = 0.4
MIN_SECOND_PEAK = 0.02  # the smaller peak must reach this share of the larger
MAX_VALLEY = 0.85  # the low point must sit at most this share of the smaller peak


@dataclass(frozen=True)
class Window:
    cadence: float | None  # steps per minute, None when the step series does not cover the window
    speed: float | None  # metres per second from the route, None when there is none


def _interp(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
    i = bisect.bisect_left(xs, x)
    if i <= 0:
        return ys[0] + (x - xs[0])
    if i >= len(xs):
        return ys[-1] + (x - xs[-1])
    x0, x1 = xs[i - 1], xs[i]
    if x1 <= x0:
        return ys[i]
    return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - x0) / (x1 - x0)


def _point_window(at: float) -> int:
    """A route point closes the second before it, so one on a boundary belongs to the window that ends there."""
    return max(0, math.ceil(at / WINDOW_S) - 1)


def _clock(cols: Mapping[str, Sequence] | None) -> tuple[list[float], list[float]] | None:
    """Sorted (wall t, active at) pairs from a series that carries both, else None."""
    if not cols or not cols.get("at") or not cols.get("t"):
        return None
    pairs = sorted(zip(cols["t"], cols["at"]))
    return [p[0] for p in pairs], [p[1] for p in pairs]


def windows(step: Mapping[str, Sequence] | None, route: Mapping[str, Sequence] | None,
            hr: Mapping[str, Sequence] | None = None) -> list[Window]:
    """The run's 10 s windows on the active clock, up to the last that has step or speed data.

    A step interval {t, dt, steps} is mapped onto the active clock through the (t, at) pairs of the route or the
    heart-rate series (identity when neither has pauses), and its steps are spread evenly over that active span."""
    clock = _clock(route) or _clock(hr)

    def to_active(t: float) -> float:
        return _interp(clock[0], clock[1], t) if clock else t

    # cadence: steps spread over each interval's active span
    spans: list[tuple[float, float, float]] = []
    if step and step.get("t"):
        for t, dt, n in zip(step["t"], step["dt"], step["steps"]):
            a0, a1 = to_active(t), to_active(t + dt)
            if a1 > a0 and n is not None:
                spans.append((a0, a1, float(n)))
    # speed: route points on the active clock
    pts: list[tuple[float, float]] = []
    if route and route.get("speed"):
        at = route.get("at") or route["t"]
        pts = sorted((a, v) for a, v in zip(at, route["speed"]) if v is not None)
    if not spans and not pts:
        return []
    last = max([math.ceil(s[1] / WINDOW_S) - 1 for s in spans] + [_point_window(p[0]) for p in pts])  # window k covers [10k, 10k + 10)
    n_win = last + 1
    steps = [0.0] * n_win
    covered = [0.0] * n_win
    for a0, a1, n in spans:
        rate = n / (a1 - a0)
        k = int(a0 // WINDOW_S)
        while k * WINDOW_S < a1:
            ov = min(a1, (k + 1) * WINDOW_S) - max(a0, k * WINDOW_S)
            if ov > 0 and 0 <= k <= last:
                steps[k] += rate * ov
                covered[k] += ov
            k += 1
    speeds: list[list[float]] = [[] for _ in range(n_win)]
    for a, v in pts:
        k = _point_window(a)
        if 0 <= k <= last:
            speeds[k].append(v)
    out = []
    for i in range(n_win):
        cad = steps[i] / covered[i] * 60.0 if covered[i] >= WINDOW_S / 2 else None
        if cad is not None and cad > MAX_SPM:
            cad = None
        spd = sum(speeds[i]) / len(speeds[i]) if speeds[i] else None
        out.append(Window(cad, spd))
    return out


def _low_point(values: Sequence[float], rng: tuple[float, float], bin_w: float, min_gap: float,
               lo_edge: float, fallback: float, min_seconds: float, seconds_each: float = WINDOW_S) -> tuple[float, bool]:
    """The low point between the walking and running peaks of `values`, as (cutoff, learned).

    Falls back when there is under `min_seconds` of history, no second peak, no clear valley, or the valley lies
    outside `rng`."""
    if len(values) * seconds_each < min_seconds:
        return fallback, False
    nb = int((max(values) - lo_edge) // bin_w) + 2
    if nb < 5:
        return fallback, False
    hist = [0.0] * nb
    for v in values:
        if v >= lo_edge:
            hist[int((v - lo_edge) // bin_w)] += 1
    sm = [sum(hist[max(0, i - 1):i + 2]) / len(hist[max(0, i - 1):i + 2]) for i in range(nb)]
    gap = max(1, int(round(min_gap / bin_w)))
    p1 = max(range(nb), key=lambda i: (sm[i], -i))
    # the second peak is a local maximum, so the slope of the first peak never counts as one
    rest = [i for i in range(1, nb - 1) if abs(i - p1) >= gap and sm[i - 1] <= sm[i] >= sm[i + 1] and sm[i] > 0]
    if not rest:
        return fallback, False
    p2 = max(rest, key=lambda i: (sm[i], -i))
    pl, ph = sorted((p1, p2))
    small = min(sm[pl], sm[ph])
    if small < MIN_SECOND_PEAK * max(sm[pl], sm[ph]):
        return fallback, False
    valley = min(range(pl, ph + 1), key=lambda i: (sm[i], abs(i - (pl + ph) / 2)))
    if valley in (pl, ph) or sm[valley] > MAX_VALLEY * small:
        return fallback, False
    # the flat bottom of the valley: the contiguous bins within 5% of the minimum
    lim = sm[valley] * 1.05 + 1e-9
    left = right = valley
    while left - 1 > pl and sm[left - 1] <= lim:
        left -= 1
    while right + 1 < ph and sm[right + 1] <= lim:
        right += 1
    centre = (left + right) / 2
    cutoff = lo_edge + (centre + 0.5) * bin_w
    if not rng[0] <= cutoff <= rng[1]:
        return fallback, False
    return cutoff, True


@dataclass(frozen=True)
class Cutoffs:
    spm: float
    spm_learned: bool
    mps: float
    mps_learned: bool


def learn_cutoff(runs: Sequence[Sequence[Window]]) -> Cutoffs:
    """Cadence and pace cutoffs from every run's windows in this recompute.

    The cadence cutoff comes from all windows with a cadence at or above the stopped level. The pace cutoff comes
    from the speeds of windows in runs that have both cadence and pace."""
    cad = [w.cadence for r in runs for w in r if w.cadence is not None and STOPPED_SPM <= w.cadence <= MAX_SPM]
    spm, spm_l = _low_point(cad, CUTOFF_RANGE_SPM, BIN_SPM, MIN_PEAK_GAP_SPM, STOPPED_SPM, DEFAULT_CUTOFF_SPM, MIN_HISTORY_S)
    spd = [w.speed for r in runs if any(w.cadence is not None for w in r)
           for w in r if w.speed is not None and w.cadence is not None and STOPPED_SPM <= w.cadence <= MAX_SPM and w.speed >= STOPPED_MPS]
    mps, mps_l = _low_point(spd, PACE_RANGE_MPS, BIN_MPS, MIN_PEAK_GAP_MPS, STOPPED_MPS, DEFAULT_PACE_CUTOFF_MPS, MIN_HISTORY_S)
    return Cutoffs(spm, spm_l, mps, mps_l)


def split(wins: Sequence[Window], cut: Cutoffs) -> dict | None:
    """The run's split, or None when it has neither steps nor pace.

    Keys: run_pct, walk_pct, stopped_pct (sum 100), run_s, walk_s, stopped_s, source ("cadence" | "pace"), cutoff
    (steps per minute for cadence, metres per second for pace), cutoff_learned, and walk [t0, t1] ranges in seconds
    on the active clock. Window k covers [10k, 10k + 10)."""
    by_cad = any(w.cadence is not None for w in wins)
    if not by_cad and not any(w.speed is not None for w in wins):
        return None
    labels: list[str | None] = []
    for w in wins:
        v = w.cadence if by_cad else w.speed
        if v is None:
            labels.append(None)
        elif by_cad:
            labels.append("stopped" if v < STOPPED_SPM else "walk" if v < cut.spm else "run")
        else:
            labels.append("stopped" if v < STOPPED_MPS else "walk" if v < cut.mps else "run")
    n = {k: labels.count(k) for k in ("run", "walk", "stopped")}
    total = sum(n.values())
    if not total:
        return None
    walk_pct = round(n["walk"] / total * 100, 1)
    stopped_pct = round(n["stopped"] / total * 100, 1)
    ranges: list[list[float]] = []
    for i, lab in enumerate(labels):
        if lab != "walk":
            continue
        t0, t1 = i * WINDOW_S, (i + 1) * WINDOW_S
        if ranges and ranges[-1][1] == t0:
            ranges[-1][1] = t1
        else:
            ranges.append([t0, t1])
    return {
        "run_pct": round(100 - walk_pct - stopped_pct, 1), "walk_pct": walk_pct, "stopped_pct": stopped_pct,
        "run_s": n["run"] * WINDOW_S, "walk_s": n["walk"] * WINDOW_S, "stopped_s": n["stopped"] * WINDOW_S,
        "source": "cadence" if by_cad else "pace",
        "cutoff": round(cut.spm if by_cad else cut.mps, 3), "cutoff_learned": cut.spm_learned if by_cad else cut.mps_learned,
        "walk_ranges": ranges,
    }
