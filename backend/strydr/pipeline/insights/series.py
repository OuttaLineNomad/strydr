"""Per-minute run analytics shared by the cardiac-drift and pace-at-fixed-HR rules. Pure.

A run's `minutes` are already aligned (HR avg per minute, GPS speed per minute, altitude); see
`RunSummary`. Minute 0 is the start of the run and the first `warmup_min` minutes are ignored.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from statistics import fmean, median, pstdev
from typing import Any

from .models import MinutePoint, RunSummary


@dataclass(frozen=True, slots=True)
class Drift:
    decoupling_pct: float
    ef_first: float
    ef_second: float
    mean_hr: float
    minutes_used: int
    hill_gate: str  # "checked" | "not checked (no elevation data)"


def drift_for_run(run: RunSummary, ceiling_bpm: float, th: Mapping[str, Any]) -> Drift | None:
    """Decoupling % for a steady, easy run (FR-18), or None when the run is not eligible."""
    mins = run.minutes
    if not mins or (run.duration_s or len(mins) * 60.0) < th["min_duration_min"] * 60:
        return None
    window = mins[th["warmup_min"] :]
    if len(window) < th["min_duration_min"] - th["warmup_min"]:
        return None
    hr_cov = sum(1 for m in window if m.hr is not None) / len(window)
    sp_cov = sum(1 for m in window if m.speed_mps is not None) / len(window)
    if hr_cov < th["min_hr_coverage"] or sp_cov < th["min_hr_coverage"]:
        return None
    pts = [m for m in window if m.hr is not None and m.speed_mps is not None]
    speeds = [m.speed_mps for m in pts]
    mean_speed = fmean(speeds)
    if mean_speed <= 0 or pstdev(speeds) / mean_speed > th["max_speed_cv"]:
        return None
    if sum(1 for s in speeds if s > th["surge_factor"] * median(speeds)) > th["max_surge_minutes"]:
        return None
    mean_hr = fmean(m.hr for m in pts)
    if mean_hr > ceiling_bpm:
        return None
    hill = _hill_gate(run, window, th)
    if hill is None:
        return None
    h = len(pts) // 2
    first, second = pts[:h], pts[len(pts) - h :]
    ef1, ef2 = _ef(first), _ef(second)
    if ef1 <= 0:
        return None
    return Drift((ef1 - ef2) / ef1 * 100.0, ef1, ef2, mean_hr, len(pts), hill)


def _ef(pts: list[MinutePoint]) -> float:
    """Efficiency factor: mean speed (m/min) over mean HR."""
    return fmean(m.speed_mps * 60.0 for m in pts) / fmean(m.hr for m in pts)


def _hill_gate(run: RunSummary, window: tuple[MinutePoint, ...], th: Mapping[str, Any]) -> str | None:
    """Little climbing, and the second half no hillier than the first. None = gate failed."""
    km = sum(m.speed_mps * 60.0 for m in window if m.speed_mps) / 1000.0
    alts = [m.altitude_m for m in window]
    if km <= 0:
        return None
    if all(a is not None for a in alts) and len(alts) > 1:
        ascent = sum(max(0.0, b - a) for a, b in zip(alts, alts[1:]))
        mid = len(alts) // 2
        half_diff = abs((alts[-1] - alts[mid]) - (alts[mid] - alts[0]))
        if ascent / km > th["max_net_gain_m_per_km"] or half_diff / km > th["max_half_gain_diff_m_per_km"]:
            return None
        return "checked"
    if run.elevation_gain_m is not None and run.distance_m:
        return "checked" if run.elevation_gain_m / (run.distance_m / 1000.0) <= th["max_net_gain_m_per_km"] else None
    return "not checked (no elevation data)"


def qualifying_speeds(run: RunSummary, band: tuple[float, float], th: Mapping[str, Any]) -> list[float]:
    """Speeds (m/s) of post-warm-up flat minutes whose HR is inside the band (pace-at-fixed-HR)."""
    mins = run.minutes
    if not mins:
        return []
    out = []
    for i in range(th["warmup_min"], len(mins)):
        m = mins[i]
        if m.hr is None or m.speed_mps is None or m.speed_mps < th["min_speed_mps"]:
            continue
        if not (band[0] <= m.hr <= band[1]):
            continue
        if not run.is_indoor:
            nxt = mins[i + 1].altitude_m if i + 1 < len(mins) else None
            if m.altitude_m is None or nxt is None:
                continue
            if abs(nxt - m.altitude_m) / (m.speed_mps * 60.0) * 100.0 > th["max_abs_grade_pct"]:
                continue
        out.append(m.speed_mps)
    return out
