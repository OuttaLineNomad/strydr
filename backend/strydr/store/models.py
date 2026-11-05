"""Tables for every tier plus jobs, auth and settings (AD-1, AD-5, AD-6)."""
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy import UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RawPayload(Base):
    __tablename__ = "raw_payload"
    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL only while the body is still streaming in (AD-3); unique once known.
    sha256: Mapped[str | None] = mapped_column(String(64), unique=True)
    received_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16))  # receiving|accepted|processed|quarantined
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    error: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(8), default="hae", server_default="hae")  # hae|apple
    adapter_version: Mapped[int | None] = mapped_column(Integer)  # the source adapter that normalized it; NULL until processed


class ImportStatus(Base):
    """Progress of an Apple Health export import (persistent tier: not rebuilt by recompute or reparse)."""
    __tablename__ = "import_status"
    payload_id: Mapped[int] = mapped_column(ForeignKey("raw_payload.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[str] = mapped_column(String(12))  # queued|validating|writing|done|failed
    workouts: Mapped[int] = mapped_column(Integer, default=0)
    merged: Mapped[int] = mapped_column(Integer, default=0)
    kept_existing: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[int] = mapped_column(Integer, default=0)
    nights: Mapped[int] = mapped_column(Integer, default=0)
    date_from: Mapped[str | None] = mapped_column(String(10))
    date_to: Mapped[str | None] = mapped_column(String(10))
    error: Mapped[str | None] = mapped_column(String(200))  # exception class name only
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class RawChunk(Base):
    __tablename__ = "raw_chunk"
    payload_id: Mapped[int] = mapped_column(ForeignKey("raw_payload.id", ondelete="CASCADE"), primary_key=True)
    seq: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class Job(Base):
    __tablename__ = "job"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(32))  # process_raw|recompute|...
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|running|done|failed
    payload_id: Mapped[int | None] = mapped_column(ForeignKey("raw_payload.id", ondelete="SET NULL"))
    as_of: Mapped[str | None] = mapped_column(String(10))  # local date, AD-15
    attempts: Mapped[int] = mapped_column(default=0)
    run_after: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (Index("ix_job_status_run_after", "status", "run_after"),)


class Workout(Base):
    __tablename__ = "workout"
    id: Mapped[int] = mapped_column(primary_key=True)
    workout_id: Mapped[str] = mapped_column(String(64), unique=True)  # AD-6
    type: Mapped[str] = mapped_column(String(8))  # run|walk|hike
    is_indoor: Mapped[bool] = mapped_column(Boolean)
    start_utc: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_utc: Mapped[datetime] = mapped_column(DateTime)
    utc_offset_s: Mapped[int] = mapped_column(Integer)
    local_date: Mapped[str] = mapped_column(String(10), index=True)
    duration_s: Mapped[float | None] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)
    avg_speed_mps: Mapped[float | None] = mapped_column(Float)
    max_speed_mps: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    max_hr: Mapped[float | None] = mapped_column(Float)
    avg_cadence: Mapped[float | None] = mapped_column(Float)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float)
    energy_kcal: Mapped[float | None] = mapped_column(Float)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    effort_score: Mapped[float | None] = mapped_column(Float)
    effort_estimated: Mapped[bool | None] = mapped_column(Boolean)
    quality_flags: Mapped[dict] = mapped_column(JSON, default=dict)
    series_count: Mapped[int] = mapped_column(default=0)  # AD-3 precedence inputs
    sample_count: Mapped[int] = mapped_column(default=0)
    adapter_version: Mapped[int] = mapped_column(Integer)
    payload_id: Mapped[int | None] = mapped_column(ForeignKey("raw_payload.id", ondelete="SET NULL"))
    received_at: Mapped[datetime] = mapped_column(DateTime)


class SampleSeries(Base):
    __tablename__ = "sample_series"
    id: Mapped[int] = mapped_column(primary_key=True)
    workout_id: Mapped[str] = mapped_column(ForeignKey("workout.workout_id", ondelete="CASCADE"))
    series: Mapped[str] = mapped_column(String(32))  # heart_rate|route
    n_samples: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)  # zlib-compressed columnar JSON
    adapter_version: Mapped[int] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("workout_id", "series"),)


class DailyMetric(Base):
    __tablename__ = "daily_metric"
    id: Mapped[int] = mapped_column(primary_key=True)
    metric: Mapped[str] = mapped_column(String(64))
    local_date: Mapped[str] = mapped_column(String(10))
    units: Mapped[str] = mapped_column(String(32))  # canonical (SI) units
    value: Mapped[float | None] = mapped_column(Float)
    extra: Mapped[dict | None] = mapped_column(JSON)
    series_count: Mapped[int] = mapped_column(default=1)
    sample_count: Mapped[int] = mapped_column(default=1)
    adapter_version: Mapped[int] = mapped_column(Integer)
    payload_id: Mapped[int | None] = mapped_column(ForeignKey("raw_payload.id", ondelete="SET NULL"))
    received_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("metric", "local_date"),)


class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    ingest_token_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Session(Base):
    __tablename__ = "session"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the cookie value
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Settings(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


# --- Analytic tier (AD-1): every row belongs to a generation and is never updated in place ----------------

class Generation(Base):
    __tablename__ = "generation"
    id: Mapped[int] = mapped_column(primary_key=True)
    as_of: Mapped[str] = mapped_column(String(10))  # AD-15 local date the generation was computed for
    created_at: Mapped[datetime] = mapped_column(DateTime)


class CurrentGeneration(Base):
    """Single-row pointer; flipping it is the only way a generation becomes visible (AD-1)."""
    __tablename__ = "current_generation"
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[int] = mapped_column(ForeignKey("generation.id"))

    __table_args__ = (CheckConstraint("id = 1"),)


def _gen() -> Mapped[int]:
    return mapped_column(ForeignKey("generation.id", ondelete="CASCADE"), primary_key=True)


class ProfileResult(Base):
    __tablename__ = "profile_result"
    generation_id: Mapped[int] = _gen()
    hrmax: Mapped[int | None] = mapped_column(Integer)
    hrmax_source: Mapped[str] = mapped_column(String(16))  # override|observed|tanaka|unavailable
    zone_bounds_bpm: Mapped[list | None] = mapped_column(JSON)  # upper bound of zones 1-4
    easy_ceiling_bpm: Mapped[float | None] = mapped_column(Float)
    rhr_7d_median: Mapped[float | None] = mapped_column(Float)
    rhr_30d_baseline: Mapped[float | None] = mapped_column(Float)
    hrv_60d_baseline: Mapped[float | None] = mapped_column(Float)
    rhr_baseline_mean: Mapped[float | None] = mapped_column(Float)
    rhr_baseline_sd: Mapped[float | None] = mapped_column(Float)
    rhr_baseline_days: Mapped[int | None] = mapped_column(Integer)
    hrv_baseline_mean: Mapped[float | None] = mapped_column(Float)  # mean of ln(SDNN)
    hrv_baseline_sd: Mapped[float | None] = mapped_column(Float)
    hrv_baseline_days: Mapped[int | None] = mapped_column(Integer)


class WorkoutSummary(Base):
    __tablename__ = "workout_summary"
    generation_id: Mapped[int] = _gen()
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    is_long_run: Mapped[bool] = mapped_column(Boolean)
    zone_seconds: Mapped[list | None] = mapped_column(JSON)  # seconds in zones 1-5
    # Intensity mix inputs (derive/summary): post-warm-up seconds with HR, those at or below the easy ceiling.
    hr_time_s: Mapped[float | None] = mapped_column(Float)
    easy_time_s: Mapped[float | None] = mapped_column(Float)
    hr_coverage: Mapped[float | None] = mapped_column(Float)
    minutes: Mapped[list | None] = mapped_column(JSON)  # per-minute [hr, speed_mps, altitude_m] for the insight rules


class WorkoutDetail(Base):
    __tablename__ = "workout_detail"
    generation_id: Mapped[int] = _gen()
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    splits_km: Mapped[list | None] = mapped_column(JSON)
    splits_mi: Mapped[list | None] = mapped_column(JSON)
    hr_series: Mapped[list | None] = mapped_column(JSON)
    pace_series: Mapped[list | None] = mapped_column(JSON)
    elevation_series: Mapped[list | None] = mapped_column(JSON)
    conditions: Mapped[dict | None] = mapped_column(JSON)  # derive/conditions: weather and heat adjustment
    gap: Mapped[dict | None] = mapped_column(JSON)  # derive/grade: whole-run grade adjusted pace and relief
    sleep: Mapped[dict | None] = mapped_column(JSON)  # derive/sleep: the night before and the next morning's readings
    runwalk: Mapped[dict | None] = mapped_column(JSON)  # derive/runwalk: running, walking and stopped shares, source, cutoff


class WorkoutDisplay(Base):
    """The only geometry the API may serve (AD-10)."""
    __tablename__ = "workout_display"
    generation_id: Mapped[int] = _gen()
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_geometry: Mapped[dict | None] = mapped_column(JSON)


class PeriodSummary(Base):
    __tablename__ = "period_summary"
    generation_id: Mapped[int] = _gen()
    kind: Mapped[str] = mapped_column(String(8), primary_key=True)  # week|month
    period_id: Mapped[str] = mapped_column(String(10), primary_key=True)  # %G-W%V or YYYY-MM
    start_date: Mapped[str] = mapped_column(String(10))
    distance_m: Mapped[float] = mapped_column(Float)
    duration_s: Mapped[float] = mapped_column(Float)
    run_count: Mapped[int] = mapped_column(Integer)
    long_run_count: Mapped[int] = mapped_column(Integer)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float)
    zone_seconds: Mapped[list | None] = mapped_column(JSON)
    run_s: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")  # derive/runwalk seconds
    walk_s: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")


class BestEffort(Base):
    __tablename__ = "best_effort"
    generation_id: Mapped[int] = _gen()
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    distance_key: Mapped[str] = mapped_column(String(16), primary_key=True)
    time_s: Mapped[float] = mapped_column(Float)


class Record(Base):
    __tablename__ = "record"
    generation_id: Mapped[int] = _gen()
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(8))  # s|m|m/s
    workout_id: Mapped[str | None] = mapped_column(String(64))
    local_date: Mapped[str | None] = mapped_column(String(10))
    period_id: Mapped[str | None] = mapped_column(String(10))


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issue"
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[int] = mapped_column(ForeignKey("generation.id", ondelete="CASCADE"), index=True)
    workout_id: Mapped[str | None] = mapped_column(String(64))
    stage: Mapped[str] = mapped_column(String(32))
    error: Mapped[str] = mapped_column(String(200))  # exception class name only, never payload content


# Tables owned by derive/load, derive/days, derive/routes and insights.

class WorkoutLoad(Base):
    __tablename__ = "workout_load"
    generation_id: Mapped[int] = _gen()
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(8))
    local_date: Mapped[str] = mapped_column(String(10))
    trimp: Mapped[float] = mapped_column(Float)
    estimated: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(16))  # hr|hr-scaled|avg-hr|personal-rate|default|rpe|none
    coverage: Mapped[float | None] = mapped_column(Float)
    rpe: Mapped[int | None] = mapped_column(Integer)  # the note RPE that was available (FR-24a)
    hr_max: Mapped[float | None] = mapped_column(Float)
    hr_rest: Mapped[float | None] = mapped_column(Float)
    b: Mapped[float | None] = mapped_column(Float)


class DailyLoad(Base):
    __tablename__ = "daily_load"
    generation_id: Mapped[int] = _gen()
    local_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    load: Mapped[float] = mapped_column(Float)
    by_type: Mapped[dict] = mapped_column(JSON)
    estimated: Mapped[bool] = mapped_column(Boolean)
    n_workouts: Mapped[int] = mapped_column(Integer)
    fitness: Mapped[float] = mapped_column(Float)
    fatigue: Mapped[float] = mapped_column(Float)
    form: Mapped[float | None] = mapped_column(Float)
    form_pct: Mapped[float | None] = mapped_column(Float)
    warmup: Mapped[bool] = mapped_column(Boolean)
    acwr: Mapped[float | None] = mapped_column(Float)  # tooltip context only (FR-24c)
    ramp_pct: Mapped[float | None] = mapped_column(Float)  # tooltip context only (FR-24c)
    raw_state: Mapped[str | None] = mapped_column(String(16))
    training_state: Mapped[str | None] = mapped_column(String(16))
    state_since: Mapped[str | None] = mapped_column(String(10))


class DayClass(Base):
    __tablename__ = "day_class"
    generation_id: Mapped[int] = _gen()
    local_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    has_run: Mapped[bool] = mapped_column(Boolean)
    is_hard: Mapped[bool] = mapped_column(Boolean)
    is_rest: Mapped[bool] = mapped_column(Boolean)
    kind: Mapped[str] = mapped_column(String(8))  # run|active|rest
    load: Mapped[float] = mapped_column(Float)
    hard_seconds: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list] = mapped_column(JSON)


class Route(Base):
    __tablename__ = "route"
    generation_id: Mapped[int] = _gen()
    route_key: Mapped[str] = mapped_column(String(64), primary_key=True)  # AD-6
    run_count: Mapped[int] = mapped_column(Integer)
    reference_id: Mapped[str] = mapped_column(String(64))
    sibling_key: Mapped[str | None] = mapped_column(String(64))
    distance_m: Mapped[float] = mapped_column(Float)
    first_date: Mapped[str] = mapped_column(String(10))
    last_date: Mapped[str] = mapped_column(String(10))
    display_geometry: Mapped[dict | None] = mapped_column(JSON)  # clipped by for_display (AD-10)


class WorkoutRoute(Base):
    __tablename__ = "workout_route"
    generation_id: Mapped[int] = _gen()
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    route_key: Mapped[str] = mapped_column(String(64), index=True)


class RouteSection(Base):
    __tablename__ = "route_section"
    generation_id: Mapped[int] = _gen()
    section_id: Mapped[str] = mapped_column(String(80), primary_key=True)  # AD-6
    route_key: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(1))  # s|c
    idx: Mapped[int] = mapped_column(Integer)
    start_m: Mapped[float] = mapped_column(Float)
    end_m: Mapped[float] = mapped_column(Float)
    gain_m: Mapped[float | None] = mapped_column(Float)  # climbs only


class SectionResult(Base):
    """One run on one section: its measure and the same-HR comparison with earlier runs (FR-23, FR-23a)."""
    __tablename__ = "section_result"
    generation_id: Mapped[int] = _gen()
    section_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    route_key: Mapped[str] = mapped_column(String(64), index=True)
    local_date: Mapped[str] = mapped_column(String(10))
    time_s: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    comparable: Mapped[bool] = mapped_column(Boolean)
    n: Mapped[int] = mapped_column(Integer)
    baseline_time_s: Mapped[float | None] = mapped_column(Float)
    baseline_hr: Mapped[float | None] = mapped_column(Float)
    gap_s: Mapped[float | None] = mapped_column(Float)
    spread_s: Mapped[float | None] = mapped_column(Float)
    z: Mapped[float | None] = mapped_column(Float)
    direction: Mapped[str | None] = mapped_column(String(8))
    fires: Mapped[bool] = mapped_column(Boolean)
    reasons: Mapped[list] = mapped_column(JSON)


class InsightFact(Base):
    __tablename__ = "insight_fact"
    generation_id: Mapped[int] = _gen()
    insight_key: Mapped[str] = mapped_column(String(160), primary_key=True)  # AD-6
    rule_id: Mapped[str] = mapped_column(String(64), index=True)
    subject: Mapped[str] = mapped_column(String(96), index=True)
    period: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))
    number: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(16))
    evidence: Mapped[dict] = mapped_column(JSON)
    template_id: Mapped[str] = mapped_column(String(64))
    text_template: Mapped[str] = mapped_column(Text)
    phrase_hash: Mapped[str] = mapped_column(String(64))  # sha256(fact + units + template_version), AD-9
    local_date: Mapped[str] = mapped_column(String(10), index=True)  # feed ordering
    week_id: Mapped[str] = mapped_column(String(8), index=True)


ANALYTIC = (
    ProfileResult, WorkoutSummary, WorkoutDetail, WorkoutDisplay, PeriodSummary, BestEffort, Record, DataQualityIssue,
    WorkoutLoad, DailyLoad, DayClass, Route, WorkoutRoute, RouteSection, SectionResult, InsightFact,
)


# --- User inputs and user-authored rows: no FKs into the analytic tier, orphans are kept (AD-6) ------------

class PrivacyZone(Base):
    __tablename__ = "privacy_zone"
    id: Mapped[int] = mapped_column(primary_key=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[float] = mapped_column(Float)
    # Fixed at creation (AD-10): the clip circle is centred at the true centre shifted by this offset, and its radius
    # is radius_m + trim_m. offset <= trim_m, so the true circle always lies inside the clipped area.
    offset_north_m: Mapped[float] = mapped_column(Float)
    offset_east_m: Mapped[float] = mapped_column(Float)
    trim_m: Mapped[float] = mapped_column(Float)


class RouteOverride(Base):
    __tablename__ = "route_override"
    workout_a: Mapped[str] = mapped_column(String(64), primary_key=True)
    workout_b: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(8))  # join|split


class WorkoutTypeOverride(Base):
    """Runner's correction of a workout's type. User input: survives recompute, reparse and re-sent payloads."""
    __tablename__ = "workout_type_override"
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(8))  # run|walk|hike
    created_at: Mapped[datetime] = mapped_column(DateTime)


class WorkoutWeather(Base):
    """Fetched weather for one outdoor workout (opt-in, AD-10 weather exception). Canonical tier, but sourced from
    the weather provider rather than HAE, so only the fetch_weather job writes it. No coordinates are stored."""
    __tablename__ = "workout_weather"
    workout_id: Mapped[str] = mapped_column(ForeignKey("workout.workout_id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))  # ok|unavailable|skipped (skipped: no point outside the zones)
    temp_c: Mapped[float | None] = mapped_column(Float)
    apparent_c: Mapped[float | None] = mapped_column(Float)
    dew_point_c: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    wind_ms: Mapped[float | None] = mapped_column(Float)
    wind_dir_deg: Mapped[float | None] = mapped_column(Float)
    gust_ms: Mapped[float | None] = mapped_column(Float)
    precip_mm_h: Mapped[float | None] = mapped_column(Float)
    cloud_pct: Mapped[float | None] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class WeatherCache(Base):
    """One provider reply per (0.1 degree grid cell, UTC date): hourly values only. `cell` is the rounded
    'lat,lon' that was sent, so it is no finer than what already left the server."""
    __tablename__ = "weather_cache"
    cell: Mapped[str] = mapped_column(String(16), primary_key=True)
    utc_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    hourly: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class WorkoutNote(Base):
    __tablename__ = "workout_note"
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str | None] = mapped_column(Text)
    rpe: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class Shoe(Base):
    """A pair of shoes. Never deleted: retiring hides it, renaming fixes a typo. No FKs; ids are held by value."""
    __tablename__ = "shoe"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    retired: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    __table_args__ = (Index("uq_shoe_name_lower", func.lower(name), unique=True),)


class WorkoutPlan(Base):
    """A saved home-workout plan (kettlebell / bodyweight): user content, not a pipeline input, so a write never
    enqueues a recompute. `moves` is the ordered list of {name, reps|seconds, weight_kg|null}. No FKs."""
    __tablename__ = "workout_plan"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    format: Mapped[str] = mapped_column(String(8))  # amrap|emom|complex
    cap_min: Mapped[int | None] = mapped_column(Integer)  # AMRAP time cap
    emom_min: Mapped[int | None] = mapped_column(Integer)  # EMOM total minutes
    rounds: Mapped[int | None] = mapped_column(Integer)  # complex rounds
    tap_per: Mapped[str] = mapped_column(String(8), default="move", server_default="move")  # move|round (AMRAP, complex)
    moves: Mapped[list] = mapped_column(JSON)
    video_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    __table_args__ = (Index("uq_workout_plan_name_lower", func.lower(name), unique=True),)


class WorkoutSession(Base):
    """One run of a home-workout plan: the taps are the log. `plan` is a snapshot of the plan as it ran, `events` the
    timed taps, auto advances, pauses and resumes. User content, not a pipeline input (never recomputed). No FKs:
    `plan_id` may outlive its plan. `effort` (manual 1-10) and `short_reps` are set from the summary; `matched_workout_id` stays unused (the match is computed on read)."""
    __tablename__ = "workout_session"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int | None] = mapped_column(Integer, index=True)
    plan: Mapped[dict] = mapped_column(JSON)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    start_utc: Mapped[datetime] = mapped_column(DateTime)
    end_utc: Mapped[datetime] = mapped_column(DateTime)
    events: Mapped[list] = mapped_column(JSON)
    rounds_done: Mapped[int] = mapped_column(Integer)
    partial_moves: Mapped[int] = mapped_column(Integer)
    fell_short: Mapped[list] = mapped_column(JSON)
    active_s: Mapped[int] = mapped_column(Integer)
    overtime_s: Mapped[int] = mapped_column(Integer)
    matched_workout_id: Mapped[str | None] = mapped_column(String(64))
    effort: Mapped[int | None] = mapped_column(Integer)
    short_reps: Mapped[dict | None] = mapped_column(JSON)  # {"minute": reps|null} for flagged EMOM minutes
    set_rungs: Mapped[dict | None] = mapped_column(JSON)  # {"move:instance": rung} for sets done at an easier level
    source: Mapped[str | None] = mapped_column(String(8))  # NULL = a live run; 'watch' = logged from an orphan watch workout
    created_at: Mapped[datetime] = mapped_column(DateTime)


class OrphanDismissal(Base):
    """A watch strength workout the runner has answered (logged as a session, or not a Strydr workout): never asked about
    again, even if the session is later deleted. User content."""
    __tablename__ = "orphan_dismissal"
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class ShoeDefault(Base):
    """Default-shoe history: the row with the latest from_date on or before a run's date applies. NULL shoe_id = none."""
    __tablename__ = "shoe_default"
    from_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    shoe_id: Mapped[int | None] = mapped_column(Integer)


class WorkoutShoe(Base):
    """Per-run shoe choice. NULL shoe_id = explicitly no shoe. Absent row = follow the default."""
    __tablename__ = "workout_shoe"
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    shoe_id: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class WorkoutCarry(Base):
    """Extra weight carried on a run, walk or hike (child carrier, weighted vest). A pipeline input (cohorts for comparisons, hard days) and shown on the page."""
    __tablename__ = "workout_carry"
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class SleepCorrection(Base):
    """The runner's own hours for a night Apple recorded short (watch put on late). A pipeline input (AD-1) keyed by
    the night's wake-up date; derive overlays it on `totalSleep` only."""
    __tablename__ = "sleep_correction"
    local_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    hours: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class WeekNote(Base):
    __tablename__ = "week_note"
    week_id: Mapped[str] = mapped_column(String(8), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class InsightFeedback(Base):
    __tablename__ = "insight_feedback"
    insight_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    thumb: Mapped[str] = mapped_column(String(8))  # up|down
    snapshot: Mapped[dict] = mapped_column(JSON)  # number, unit, evidence at the moment of rating
    updated_at: Mapped[datetime] = mapped_column(DateTime)


# --- Persistent tier (AD-9, AD-14): survives recomputes and migrations; deliberately not in ANALYTIC ----------

class PhrasingCache(Base):
    """AI phrasing overlay keyed by (insight_key, sha256(fact + units + template_version)). text is NULL when
    the provider's output failed validation, so the same rejected phrasing is not requested again."""
    __tablename__ = "phrasing_cache"
    insight_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    fact_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class RunSummaryCache(Base):
    """AI run summary keyed by (workout_id, sha256(run context + units + summary version)). text is NULL when the
    provider's output failed validation, so it is not requested again until the context changes."""
    __tablename__ = "run_summary_cache"
    workout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    context_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
