"""Weekly and monthly running volume, time in zone and long runs (AD-7). Runs only: walks and hikes never count (FR-7a)."""
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from ..hr import MINUTE_S, active_clock, minute_means, sample_steps

LONG_RUN_MIN_S = 75 * 60
LONG_RUN_MIN_M = 16_000.0


@dataclass(frozen=True)
class RunFacts:
    workout_id: str
    local_date: str
    distance_m: float
    duration_s: float
    elevation_gain_m: float | None
    zone_seconds: list[float] | None
    is_long_run: bool


def week_id(local_date: str) -> str:
    return date.fromisoformat(local_date).strftime("%G-W%V")  # AD-6


def month_id(local_date: str) -> str:
    return local_date[:7]


def is_long_run(distance_m: float | None, duration_s: float | None) -> bool:
    return (duration_s or 0) >= LONG_RUN_MIN_S or (distance_m or 0) >= LONG_RUN_MIN_M


def zone_seconds(hr_avg: Sequence[float], bounds_bpm: Sequence[float] | None,
                 hr_t: Sequence[float] | None = None) -> list[float] | None:
    """Seconds in zones 1-5, each HR sample weighted by the time it covers. `hr_t` is the active clock (see `hr.active_clock`), so paused readings add nothing. Without `hr_t`, samples are 60 s apart."""
    if bounds_bpm is None or not hr_avg:
        return None
    t = hr_t if hr_t is not None else [i * MINUTE_S for i in range(len(hr_avg))]
    out = [0.0] * (len(bounds_bpm) + 1)
    for hr, w in zip(hr_avg, sample_steps(t, hr_avg)):
        if w > 0:
            out[sum(hr > b for b in bounds_bpm)] += w
    return out if any(out) else None


def period_summaries(runs: Sequence[RunFacts]) -> list[dict]:
    """One row per ISO week and per calendar month that has at least one run."""
    groups: dict[tuple[str, str], list[RunFacts]] = {}
    for r in runs:
        groups.setdefault(("week", week_id(r.local_date)), []).append(r)
        groups.setdefault(("month", month_id(r.local_date)), []).append(r)
    out = []
    for (kind, pid), rs in sorted(groups.items()):
        zones = [r.zone_seconds for r in rs if r.zone_seconds]
        gains = [r.elevation_gain_m for r in rs if r.elevation_gain_m is not None]
        start = date.fromisocalendar(int(pid[:4]), int(pid[6:]), 1).isoformat() if kind == "week" else pid + "-01"
        out.append({
            "kind": kind, "period_id": pid, "start_date": start,
            "distance_m": sum(r.distance_m for r in rs), "duration_s": sum(r.duration_s for r in rs),
            "run_count": len(rs), "long_run_count": sum(r.is_long_run for r in rs),
            "elevation_gain_m": sum(gains) if gains else None,
            "zone_seconds": [sum(z[i] for z in zones) for i in range(len(zones[0]))] if zones else None,
        })
    return out


WARMUP_S = 300.0  # [ASSUMPTION] the first 5 minutes do not count toward the intensity mix
EASY_INTENDED_MAX_RPE = 6  # [ASSUMPTION] a run the runner rated 7+ was not meant to be easy


def intensity_mix(hr_t: Sequence[float], hr_avg: Sequence[float], duration_s: float | None,
                  easy_ceiling_bpm: float | None) -> tuple[float, float, float] | None:
    """(hr_time_s, easy_time_s, hr_coverage) over the post-warm-up minutes of the active clock `hr_t` (pauses removed), or None without HR or a ceiling."""
    if easy_ceiling_bpm is None or not hr_t:
        return None
    steps = sample_steps(hr_t, hr_avg)
    kept = [(a, w) for t, a, w in zip(hr_t, hr_avg, steps) if t >= WARMUP_S and w > 0]
    if not kept:
        return None
    expected_s = max(1, math.ceil(((duration_s or hr_t[-1]) - WARMUP_S) / MINUTE_S)) * MINUTE_S
    total = sum(w for _, w in kept)
    easy = sum(w for a, w in kept if a <= easy_ceiling_bpm)
    return total, easy, min(1.0, total / expected_s)


def is_easy_intended(long_run: bool, hard_day: bool, rpe: int | None) -> bool:
    return not long_run and not hard_day and (rpe is None or rpe <= EASY_INTENDED_MAX_RPE)


def minute_points(hr: Mapping[str, Sequence] | None, route: Mapping[str, Sequence] | None,
                  duration_s: float | None) -> list[list[float | None]] | None:
    """Per-minute [HR, mean speed, altitude at the minute start] for the insight rules; None when there is neither series."""
    if not hr and not route:
        return None
    n = math.ceil(duration_s / MINUTE_S) if duration_s else 0
    hr_by = minute_means(active_clock(hr), hr["avg"]) if hr else {}
    speeds: dict[int, list[float]] = {}
    alts: dict[int, float] = {}
    if route:
        rt = active_clock(route)
        prev = None
        for t, v, alt in zip(rt, route.get("speed", [None] * len(rt)), route["alt"]):
            if t == prev:  # a paused fix: no active time passed since the last one, so it adds nothing
                continue
            prev = t
            m = int(t // MINUTE_S)
            if v is not None:
                speeds.setdefault(m, []).append(v)
            if alt is not None:
                alts.setdefault(m, alt)
    n = max([n, *(k + 1 for k in hr_by), *(k + 1 for k in speeds)])
    return [[hr_by.get(m), sum(speeds[m]) / len(speeds[m]) if m in speeds else None, alts.get(m)] for m in range(n)]
