"""Source-agnostic canonical models: SI units, UTC (AD-4)."""
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class SampleSeries:
    name: str  # heart_rate | route
    columns: dict[str, list]  # columnar, equal-length lists; "t" = seconds since workout start

    @property
    def n(self) -> int:
        return len(self.columns["t"])


@dataclass(slots=True)
class Workout:
    workout_id: str
    type: str  # run | walk | hike
    is_indoor: bool
    start_utc: datetime  # naive UTC
    end_utc: datetime
    utc_offset_s: int
    local_date: str
    duration_s: float | None = None
    distance_m: float | None = None
    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    avg_cadence: float | None = None
    elevation_gain_m: float | None = None
    energy_kcal: float | None = None
    temperature_c: float | None = None
    humidity_pct: float | None = None
    effort_score: float | None = None
    effort_estimated: bool | None = None
    quality_flags: dict[str, int] = field(default_factory=dict)
    series: dict[str, SampleSeries] = field(default_factory=dict)


@dataclass(slots=True)
class DailyMetric:
    metric: str
    local_date: str
    units: str  # canonical (SI) units
    value: float | None
    extra: dict | None = None
    field_count: int = 1  # populated fields; AD-3 "more samples" proxy


def fallback_workout_id(wtype: str, start_utc: datetime) -> str:
    """The AD-6 key for a workout with no source id: `h:` + sha256(type|start)[:16]. Shared by every adapter."""
    key = f"{wtype}|{start_utc.replace(tzinfo=UTC).isoformat(timespec='seconds')}"
    return "h:" + hashlib.sha256(key.encode()).hexdigest()[:16]


def active_seconds(t: float, pauses: list[tuple[float, float]]) -> float:
    """Seconds since start with paused time removed; a point inside a pause sits at the pause's start.

    `pauses` is sorted, non-overlapping (start, end) intervals in seconds since the workout start.
    """
    removed = 0.0
    for a, b in pauses:
        if t >= b:
            removed += b - a
        elif t > a:
            return a - removed
        else:
            break
    return t - removed
