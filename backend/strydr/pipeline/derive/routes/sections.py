"""Route sections (FR-23): fixed geographic splits, plus per-run timing and HR on each section.

Sections are cut on the route's reference line, so every run is timed over the same ground, using
its position along that line and not its own odometer. Pure: no DB, clock or I/O.
"""
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from strydr.pipeline.derive.routes import geo
from strydr.pipeline.derive.routes.matching import RoutePath, RouteThresholds, align_offset
from strydr.sources.canonical import Workout


@dataclass(frozen=True)
class Section:
    section_id: str  # {route_key}/{s|c}{index}, 1-based (AD-6)
    route_key: str
    kind: str  # s = split, c = climb
    index: int
    start_m: float  # distance along the reference line
    end_m: float
    gain_m: float | None = None  # climbs only

    @property
    def length_m(self) -> float:
        return self.end_m - self.start_m


def make_section_id(route_key: str, kind: str, index: int) -> str:
    if kind not in ("s", "c"):
        raise ValueError(f"unknown section kind {kind!r}")
    return f"{route_key}/{kind}{index}"


def split_unit_m(units: str, th: RouteThresholds) -> float:
    """`units` is the runner's unit setting: 'metric' (1 km) or 'imperial' (1 mi)."""
    return th.split_unit_m_imperial if units == "imperial" else th.split_unit_m_metric


def fixed_splits(route_key: str, length_m: float, unit_m: float, th: RouteThresholds) -> list[Section]:
    """Splits of `unit_m` from the route start; a short tail is merged into the last split."""
    n = int(length_m // unit_m)
    if n == 0:
        return [Section(make_section_id(route_key, "s", 1), route_key, "s", 1, 0.0, length_m)]
    if length_m - n * unit_m >= th.split_min_tail_frac * unit_m:
        n += 1
    out = []
    for i in range(1, n + 1):
        end = length_m if i == n else i * unit_m
        out.append(Section(make_section_id(route_key, "s", i), route_key, "s", i, (i - 1) * unit_m, end))
    return out


def hr_claim_allowed(durations_s: Sequence[float], th: RouteThresholds) -> bool:
    """A section supports HR claims only if its median duration on the route reaches the minimum."""
    return len(durations_s) > 0 and float(np.median(durations_s)) >= th.min_hr_section_s


def section_avg_hr(
    hr_t: Sequence[float], hr_avg: Sequence[float], t0: float, t1: float, th: RouteThresholds
) -> float | None:
    """Time-weighted mean of per-minute HR over [t0, t1] shifted later by the cardiac lag.

    Each sample covers the time up to the next one, at most `hr_sample_span_s`. None when fewer
    than `min_hr_samples` samples overlap the window.
    """
    t = np.asarray(hr_t, dtype=float)
    v = np.asarray(hr_avg, dtype=float)
    if len(t) == 0:
        return None
    ends = np.minimum(np.append(t[1:], np.inf), t + th.hr_sample_span_s)
    w0, w1 = t0 + th.hr_lag_s, t1 + th.hr_lag_s
    overlap = np.clip(np.minimum(ends, w1) - np.maximum(t, w0), 0.0, None)
    if int((overlap > 0).sum()) < th.min_hr_samples:
        return None
    return float((v * overlap).sum() / overlap.sum())


def hr_from_workout(w: Workout) -> tuple[list[float], list[float]] | None:
    s = w.series.get("heart_rate")
    return (s.columns["t"], s.columns["avg"]) if s is not None else None


@dataclass(frozen=True)
class SectionMeasure:
    section_id: str
    time_s: float | None
    avg_hr: float | None  # lagged, time-weighted; None if too few HR samples
    comparable: bool
    reason: str | None = None  # why not comparable


def _longest_pause_s(t: np.ndarray, s: np.ndarray, th: RouteThresholds) -> float:
    """Longest stretch with no GPS fixes or almost no progress along the route."""
    longest = run = 0.0
    for i in range(len(t) - 1):
        dt = t[i + 1] - t[i]
        slow = dt <= 0 or (s[i + 1] - s[i]) / dt < th.pause_speed_mps
        if dt > th.max_gps_gap_s or slow:
            run += max(dt, 0.0)
            longest = max(longest, run)
        else:
            run = 0.0
    return longest


def measure_run(
    ref: RoutePath,
    run: RoutePath,
    sections: Sequence[Section],
    hr: tuple[Sequence[float], Sequence[float]] | None,
    th: RouteThresholds,
) -> dict[str, SectionMeasure]:
    """Time and average HR of `run` over each section of the route whose reference is `ref`.

    A section is not comparable when the run never reaches both boundaries, leaves the corridor
    inside it (a detour), or stops for longer than `pause_s` inside it.
    """
    pts = run.raw_xy + align_offset(ref, run)
    s, off = geo.progress_along(
        ref.xy, ref.cum, pts, th.corridor_m, th.progress_window_back, th.progress_window_fwd
    )
    t = run.t
    out: dict[str, SectionMeasure] = {}
    for sec in sections:
        on = ~off
        if not on.any():
            out[sec.section_id] = SectionMeasure(sec.section_id, None, None, False, "off route")
            continue
        s_on, t_on = s[on], t[on]
        tol = th.boundary_tolerance_m
        if s_on[0] > sec.start_m + tol or s_on[-1] < sec.end_m - tol:
            out[sec.section_id] = SectionMeasure(sec.section_id, None, None, False, "boundary not reached")
            continue
        t0 = float(np.interp(sec.start_m, s_on, t_on))
        t1 = float(np.interp(sec.end_m, s_on, t_on))
        inside = (t >= t0) & (t <= t1)
        if (off & inside).any():
            out[sec.section_id] = SectionMeasure(sec.section_id, t1 - t0, None, False, "detour")
            continue
        if _longest_pause_s(t[inside], s[inside], th) > th.pause_s:
            out[sec.section_id] = SectionMeasure(sec.section_id, t1 - t0, None, False, "pause")
            continue
        avg = section_avg_hr(hr[0], hr[1], t0, t1, th) if hr is not None else None
        out[sec.section_id] = SectionMeasure(sec.section_id, t1 - t0, avg, True)
    return out
