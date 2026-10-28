"""Banister TRIMP from HR samples (FR-24). Pure: no I/O, no clock.

TRIMP += dt_min * x * 0.64 * exp(b * x), with x = (HR - HRrest) / (HRmax - HRrest) clamped to [0, 1].
Each sample's time step is the gap to the next sample, capped at `max_step_s`. A gap longer than the
cap is missing coverage: the last HR is never carried forward across it.
"""
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Any

HrSample = tuple[float, float]  # (t_s since workout start, avg HR bpm)
DEFAULT_STEP_S = 60.0  # per-minute HR is what HAE gives us; used only when a lone sample has no neighbour


@dataclass(frozen=True, slots=True)
class LoadParams:
    """FR-24/24a parameters; build with `from_mapping(thresholds.section("load"))`."""

    b_male: float
    b_female: float
    max_step_s: float
    hr_floor_bpm: float
    hr_ceiling_bpm: float
    default_resting_hr: float
    full_coverage: float
    tier_a_min_coverage: float
    history_min_sessions: int
    history_window_days: int
    pace_band_s_per_km: float
    default_hrr_fraction: Mapping[str, float]
    tau_fitness_days: float
    tau_fatigue_days: float
    warmup_days: int
    seed_days: int
    rpe_hrr: tuple[tuple[float, float], ...]  # sorted (rpe, hrr_fraction)

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> "LoadParams":
        return cls(
            b_male=m["trimp_b_male"],
            b_female=m["trimp_b_female"],
            max_step_s=m["max_step_s"],
            hr_floor_bpm=m["hr_floor_bpm"],
            hr_ceiling_bpm=m["hr_ceiling_bpm"],
            default_resting_hr=m["default_resting_hr"],
            full_coverage=m["full_coverage"],
            tier_a_min_coverage=m["tier_a_min_coverage"],
            history_min_sessions=m["history_min_sessions"],
            history_window_days=m["history_window_days"],
            pace_band_s_per_km=m["pace_band_s_per_km"],
            default_hrr_fraction=dict(m["default_hrr_fraction"]),
            tau_fitness_days=m["tau_fitness_days"],
            tau_fatigue_days=m["tau_fatigue_days"],
            warmup_days=m["warmup_days"],
            seed_days=m["seed_days"],
            rpe_hrr=tuple(sorted((float(k), float(v)) for k, v in m["rpe_hrr"].items())),
        )

    def b_for(self, sex: str | None) -> float:
        """Female coefficient only when explicitly female; the documented default is male (1.92)."""
        return self.b_female if sex == "female" else self.b_male


def hrr_fraction(hr: float, hr_max: float, hr_rest: float) -> float:
    """Fraction of heart-rate reserve, clamped to [0, 1]."""
    if hr_max <= hr_rest:
        return 0.0
    return min(1.0, max(0.0, (hr - hr_rest) / (hr_max - hr_rest)))


def trimp_per_min(x: float, b: float) -> float:
    return x * 0.64 * math.exp(b * x)


def hr_intervals(
    samples: Sequence[HrSample], duration_s: float | None, params: LoadParams
) -> list[tuple[float, float]]:
    """Return (hr, dt_s) for each valid sample. dt is capped at `max_step_s`; gaps are not filled.

    Steps are measured on the full timeline, so a dropped (implausible) sample leaves a gap rather than
    letting its neighbour's HR stretch across it.
    """
    pts = sorted(samples, key=lambda s: s[0])
    if not pts:
        return []
    gaps = [b[0] - a[0] for a, b in zip(pts, pts[1:]) if b[0] > a[0]]
    typical = min(median(gaps), params.max_step_s) if gaps else DEFAULT_STEP_S
    out: list[tuple[float, float]] = []
    for i, (t, hr) in enumerate(pts):
        if i + 1 < len(pts):
            step = pts[i + 1][0] - t
        else:
            step = typical if duration_s is None else min(typical, duration_s - t)
        step = min(max(step, 0.0), params.max_step_s)
        if step > 0 and params.hr_floor_bpm <= hr <= params.hr_ceiling_bpm:
            out.append((hr, step))
    return out


def covered_seconds(intervals: Sequence[tuple[float, float]]) -> float:
    return sum(dt for _, dt in intervals)


def trimp_from_intervals(
    intervals: Sequence[tuple[float, float]], hr_max: float, hr_rest: float, b: float
) -> float:
    return sum(
        dt / 60.0 * trimp_per_min(hrr_fraction(hr, hr_max, hr_rest), b) for hr, dt in intervals
    )


def trimp_constant_hr(hr: float, duration_s: float, hr_max: float, hr_rest: float, b: float) -> float:
    """TRIMP for a workout summarised by one average HR (FR-24a step 2)."""
    return duration_s / 60.0 * trimp_per_min(hrr_fraction(hr, hr_max, hr_rest), b)
