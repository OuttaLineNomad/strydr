"""Typed response and request models: the OpenAPI schema is the frontend contract (AD-13).

SI units throughout; missing data is None (never zero). The only coordinates any model may carry are in
DisplayGeometry, the output of derive/routes/display.for_display (AD-10).
"""
from datetime import datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator


class LoginIn(BaseModel):
    username: str
    password: str


class QuarantinedPayload(BaseModel):
    id: int
    received_at: str
    size_bytes: int
    error: str | None


class SyncStatus(BaseModel):
    last_processed_at: str | None
    stale: bool
    stale_after_days: int
    quarantined: list[QuarantinedPayload]


class WorkoutOut(BaseModel):
    workout_id: str
    type: Literal["run", "walk", "hike", "strength"]
    is_indoor: bool
    start: str
    local_date: str
    duration_s: float | None
    distance_m: float | None
    avg_speed_mps: float | None
    avg_hr: float | None
    max_hr: float | None
    elevation_gain_m: float | None
    has_hr: bool
    has_route: bool
    is_long_run: bool | None  # None for walks and hikes, and until the first generation exists
    carry_kg: float | None = None  # extra weight carried, from workout_carry


class SplitOut(BaseModel):
    index: int
    distance_m: float
    duration_s: float
    speed_mps: float | None
    avg_hr: float | None
    elevation_change_m: float | None
    partial: bool
    gap_speed_mps: float | None = None  # grade adjusted; None on flat splits or without altitude


class HrPoint(BaseModel):
    t_s: float  # seconds since the workout started
    avg: float
    min: float
    max: float


class PacePoint(BaseModel):
    t_s: float
    distance_m: float
    speed_mps: float | None


class ElevationPoint(BaseModel):
    distance_m: float
    altitude_m: float


class DisplayGeometry(BaseModel):
    """Clipped by the privacy zones; markers and bounds come from the clipped track only. Points are [lat, lon]."""
    segments: list[list[tuple[float, float]]]
    start: tuple[float, float]
    end: tuple[float, float]
    bounds: tuple[float, float, float, float]  # south, west, north, east
    walk_segments: list[list[tuple[float, float]]] = []  # walking sections, cut from the same clipped points


class RunWalkOut(BaseModel):
    """Share of a run's active time spent running, walking and standing still (derive/runwalk)."""
    run_pct: float
    walk_pct: float
    stopped_pct: float  # under 60 spm while recording; counts as neither running nor walking
    source: Literal["cadence", "pace"]
    cutoff: float  # steps per minute for cadence, metres per second for pace
    cutoff_learned: bool  # False when the default was used


class NoteOut(BaseModel):
    text: str | None
    rpe: int | None
    updated_at: str


class NoteIn(BaseModel):
    text: str | None = Field(None, max_length=10_000)
    rpe: int | None = Field(None, ge=1, le=10)

    @model_validator(mode="after")
    def _not_empty(self):
        if not (self.text and self.text.strip()) and self.rpe is None:
            raise ValueError("a note needs text or an RPE")
        return self


class WorkoutTypeIn(BaseModel):
    type: Literal["run", "walk", "hike"]


class WorkoutTypeOut(BaseModel):
    workout_id: str
    type: Literal["run", "walk", "hike"]


class WorkoutCarryIn(BaseModel):
    weight_kg: float = Field(gt=0, le=100)


class SleepCorrectionIn(BaseModel):
    hours: float = Field(ge=0.5, le=14, allow_inf_nan=False)


class SleepCorrectionOut(BaseModel):
    local_date: str
    hours: float | None


class WorkoutCarryOut(BaseModel):
    carry_kg: float | None


class WorkoutShoeOut(BaseModel):
    id: int
    name: str
    retired: bool
    source: Literal["default", "chosen"]


class WorkoutShoeResult(BaseModel):
    shoe: WorkoutShoeOut | None
    chosen: bool  # a workout_shoe row exists (an explicit choice, possibly "no shoe")


class WorkoutShoeIn(BaseModel):
    shoe_id: int | None


class ShoeOut(BaseModel):
    id: int
    name: str
    retired: bool
    distance_m: float
    runs: int


class ShoeDefaultOut(BaseModel):
    shoe_id: int | None
    from_date: str


class ShoesOut(BaseModel):
    shoes: list[ShoeOut]
    default: ShoeDefaultOut | None
    history: list[ShoeDefaultOut]


class ShoeIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)

    @field_validator("name", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class ShoePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=60)
    retired: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class ShoeDefaultIn(BaseModel):
    shoe_id: int | None
    from_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("from_date")
    @classmethod
    def _real_date(cls, v: str) -> str:
        from datetime import date as _d
        _d.fromisoformat(v)  # ValueError becomes a 422
        return v


class ConditionsOut(BaseModel):
    """Weather for an outdoor run (derive/conditions). Apple's own reading wins; fetched weather fills the rest."""
    temp_c: float
    humidity_pct: float | None
    dew_point_c: float | None
    apparent_c: float | None
    wind_ms: float | None
    wind_dir_deg: float | None
    gust_ms: float | None
    precip_mm_h: float | None
    cloud_pct: float | None
    temp_dew_sum_f: float | None
    heat_adjust_pct: float | None  # rule-of-thumb estimate
    heat_adjusted_speed_mps: float | None
    band: Literal["ideal", "warm", "hot", "oppressive", "cold", "freezing"]
    windy: bool
    rain: bool
    sources: dict[str, Literal["apple", "open-meteo"]]


class SleepOut(BaseModel):
    """The night before a run (derive/sleep): hours from Apple's sleep stages, and the next morning's readings."""
    night_of: str  # the morning the night ended
    total_h: float
    deep_h: float | None
    rem_h: float | None
    core_h: float | None
    awake_h: float
    bedtime: str | None  # HH:MM, the run's local time
    wake: str | None
    hours_before_run: float | None
    efficiency_pct: float | None  # asleep / (asleep + awake)
    deep_rem_pct: float | None
    usual_h: float | None  # median of the previous 30 nights, from 7 nights up
    vs_usual_h: float | None
    quality: Literal["short", "restless", "good", "fair"]
    corrected: bool = False  # the runner entered these hours
    suspicious: bool = False  # looks like a watch put on late: offer the fix
    rhr_bpm: float | None
    rhr_usual_bpm: float | None
    hrv_ms: float | None
    hrv_usual_ms: float | None


class GapOut(BaseModel):
    gap_speed_mps: float
    relief_m: float
    relief_m_per_km: float
    hilly: bool


class RunSummaryOut(BaseModel):
    text: str
    source: Literal["ai", "template"]
    key: str  # run-summary/{workout_id}, the feedback key
    thumb: Literal["up", "down"] | None = None


class WorkoutDetailOut(BaseModel):
    workout: WorkoutOut
    max_speed_mps: float | None
    avg_cadence: float | None
    temperature_c: float | None
    humidity_pct: float | None
    effort_score: float | None
    effort_estimated: bool | None
    zone_seconds: list[float] | None
    splits_km: list[SplitOut] | None
    splits_mi: list[SplitOut] | None
    hr_series: list[HrPoint] | None
    pace_series: list[PacePoint] | None
    elevation_series: list[ElevationPoint] | None
    conditions: ConditionsOut | None = None
    gap: GapOut | None = None
    sleep: SleepOut | None = None
    runwalk: RunWalkOut | None = None
    display_geometry: DisplayGeometry | None
    quality_flags: dict[str, int]
    data_quality_issues: list[str]
    note: NoteOut | None
    shoe: WorkoutShoeOut | None = None
    shoe_chosen: bool = False
    carry_kg: float | None = None
    training_load: float | None = None  # this workout's TRIMP (heart-rate effort over time); None when not computed
    training_load_estimated: bool | None = None
    summary: RunSummaryOut | None = None


class WeekTotal(BaseModel):
    week_id: str
    week_start: str
    distance_m: float
    duration_s: float
    run_count: int


class Tile(BaseModel):
    latest_speed_mps: float | None
    latest_workout_id: str | None
    latest_local_date: str | None
    pr_speed_mps: float | None
    pr_workout_id: str | None
    pr_local_date: str | None


class DashboardOut(BaseModel):
    as_of: str | None
    weeks: list[WeekTotal]
    one_mile_pace: Tile
    avg_pace: Tile


class RecordOut(BaseModel):
    key: str
    value: float
    unit: Literal["s", "m", "m/s"]
    workout_id: str | None
    local_date: str | None
    period_id: str | None


class ProfileSettings(BaseModel):
    birth_year: int | None = Field(None, ge=1900, le=2100)
    sex: Literal["male", "female"] | None = None
    hrmax_override: int | None = Field(None, ge=100, le=230)
    zones: list[float] | None = None  # upper bounds of zones 1-4 as % of HRmax; None uses the defaults
    units: Literal["metric", "imperial"] = "metric"
    home_tz: str

    @field_validator("zones")
    @classmethod
    def _zones(cls, v):
        if v is not None and not (len(v) == 4 and all(0 < a < b < 100 for a, b in zip(v, v[1:])) and 0 < v[0] and v[-1] < 100):
            raise ValueError("zones must be 4 ascending percentages between 0 and 100")
        return v

    @field_validator("home_tz")
    @classmethod
    def _tz(cls, v):
        try:
            ZoneInfo(v)
        except (KeyError, ValueError, OSError):
            raise ValueError("unknown time zone") from None
        return v


class ResolvedProfile(BaseModel):
    as_of: str
    hrmax: int | None
    hrmax_source: Literal["override", "observed", "tanaka", "unavailable"]
    zone_bounds_bpm: list[float] | None
    easy_ceiling_bpm: float | None
    rhr_7d_median: float | None
    rhr_30d_baseline: float | None
    hrv_60d_baseline: float | None


class ProfileOut(BaseModel):
    settings: ProfileSettings
    zone_bounds_pct: list[float]  # the percentages in effect
    resolved: ResolvedProfile | None  # None until the first generation exists
    recompute_pending: bool


# --- Insights (FR-10, FR-12, FR-15, FR-19, FR-20) -------------------------------------------------------------------

class InsightOut(BaseModel):
    insight_key: str
    rule_id: str
    subject: str  # run/{workout_id} | week/{week_id} | route/{route_key} | athlete
    period: str
    kind: Literal["observation", "attaboy", "check-reading"]
    number: float | None
    unit: str | None
    text: str  # the validated AI phrasing when cached and fresh, else text_template (AD-9)
    text_source: Literal["ai", "template"]
    local_date: str  # orders the feed
    week_id: str
    run_id: str | None  # the workout_id when the subject is a run
    thumb: Literal["up", "down"] | None


class InsightFeedOut(BaseModel):
    items: list[InsightOut]
    total: int
    limit: int
    offset: int
    disclaimer: str  # FR-21 standing line


class InsightReasoning(BaseModel):
    """FR-19: the rule that fired, the data it used and a short note on the evidence."""
    rule: str
    data: dict[str, Any]
    note: str


class InsightDetailOut(InsightOut):
    template_id: str
    text_template: str
    reasoning: InsightReasoning


class FeedbackIn(BaseModel):
    thumb: Literal["up", "down"]


class FeedbackSnapshot(BaseModel):
    number: float | None = None
    unit: str | None = None
    evidence: dict[str, Any] = {}
    # a run summary's snapshot (key run-summary/{id}) carries these instead
    context_hash: str | None = None
    text: str | None = None
    source: Literal["ai", "template"] | None = None


class FeedbackOut(BaseModel):
    insight_key: str
    thumb: Literal["up", "down"]
    snapshot: FeedbackSnapshot  # the fact as it was when rated (AD-6)
    updated_at: str


# --- Weeks (FR-14..FR-16) -------------------------------------------------------------------------------------------

class IntensityMix(BaseModel):
    zone_seconds: list[float] | None  # zones 1-5
    easy_share_pct: float | None  # zones 1-3 as a share of time with HR


class WeekLoad(BaseModel):
    total: float
    by_type: dict[str, float]  # run / walk / hike, the same daily numbers as /load
    estimated: bool
    fitness: float | None  # at the end of the week
    fatigue: float | None
    form_pct: float | None


class WeekNoteOut(BaseModel):
    text: str
    updated_at: str


class WeekNoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("a note needs text")
        return v.strip()


class WeekSummaryOut(BaseModel):
    week_id: str
    week_start: str
    week_end: str
    distance_m: float  # runs only (FR-7a)
    duration_s: float
    run_count: int
    long_run_count: int
    elevation_gain_m: float | None
    intensity: IntensityMix
    walk_pct: float | None = None  # walking time over running plus walking time; None when no run had a split
    load: WeekLoad
    insight_count: int
    has_note: bool


class DayLoadOut(BaseModel):
    local_date: str
    load: float
    by_type: dict[str, float]
    estimated: bool
    is_hard: bool | None
    is_rest: bool | None


class WeekDetailOut(WeekSummaryOut):
    days: list[DayLoadOut]
    runs: list[WorkoutOut]
    insights: list[InsightOut]
    note: WeekNoteOut | None


# --- Calendar -------------------------------------------------------------------------------------------------------

class CalendarWorkout(BaseModel):
    workout_id: str
    type: Literal["run", "walk", "hike", "strength"]
    distance_m: float | None
    duration_s: float | None


class CalendarDay(BaseModel):
    local_date: str
    in_month: bool
    kind: Literal["run", "active", "rest"] | None  # None: before the first workout or after as_of
    is_hard: bool | None
    load: float
    workouts: list[CalendarWorkout]


class MonthTotals(BaseModel):
    month: str  # YYYY-MM
    distance_m: float  # runs only
    duration_s: float
    run_count: int
    elevation_gain_m: float | None


class CalendarOut(BaseModel):
    month: str
    as_of: str | None
    days: list[CalendarDay]  # whole Monday-to-Sunday weeks covering the month
    totals: MonthTotals
    previous: MonthTotals
    longest_run_m: float | None
    active_days: int
    rest_days: int


class RecapTotals(BaseModel):
    period: str  # YYYY or YYYY-MM
    distance_m: float  # runs only
    duration_s: float
    run_count: int
    long_run_count: int
    elevation_gain_m: float | None
    active_days: int


class RecapRoute(BaseModel):
    route_key: str
    distance_m: float
    runs: int  # runs in the period, not all-time


class RecapShoe(BaseModel):
    id: int
    name: str
    retired: bool
    distance_m: float
    runs: int


class RecapFitnessPoint(BaseModel):
    local_date: str
    fitness: float


class RecapFitness(BaseModel):
    start: float
    end: float
    series: list[RecapFitnessPoint]  # daily for a month, week-end values for a year


class RecapOut(BaseModel):
    period: str
    kind: Literal["month", "year"]
    start_date: str
    end_date: str
    as_of: str | None
    is_current: bool  # the period contains as_of, so it is "so far"
    totals: RecapTotals
    previous: RecapTotals
    longest_runs: list[WorkoutOut]
    top_routes: list[RecapRoute]
    shoes: list[RecapShoe]
    fitness: RecapFitness | None
    best_weeks: list[WeekSummaryOut]


# --- Load (FR-24) ---------------------------------------------------------------------------------------------------

class LoadTooltip(BaseModel):
    """Context for tooltips only (FR-24c): no risk colours, no risk wording."""
    acwr: float | None
    ramp_pct: float | None


class LoadDayOut(BaseModel):
    local_date: str
    load: float
    by_type: dict[str, float]
    estimated: bool
    fitness: float
    fatigue: float
    form: float | None
    form_pct: float | None
    warmup: bool
    tooltip: LoadTooltip


class TrainingStateOut(BaseModel):
    state: Literal["Building", "Holding", "Easing", "Overreaching"] | None  # None: warm-up or too little recent training
    since: str | None


class LoadOut(BaseModel):
    as_of: str | None
    series: list[LoadDayOut]
    training_state: TrainingStateOut | None


# --- Routes (FR-22, FR-23, FR-23b) ----------------------------------------------------------------------------------

class RouteOut(BaseModel):
    route_key: str
    run_count: int
    distance_m: float
    first_date: str
    last_date: str
    sibling_key: str | None  # the same route run in reverse
    display_geometry: DisplayGeometry | None


class RouteMapLine(BaseModel):
    workout_id: str
    type: Literal["run", "walk", "hike"]
    local_date: str
    display_geometry: DisplayGeometry  # clipped by the privacy zones (AD-10); bounds come from these


class RouteMapOut(BaseModel):
    lines: list[RouteMapLine]


class SectionOut(BaseModel):
    section_id: str
    kind: Literal["s", "c"]  # split or climb
    index: int
    start_m: float
    end_m: float
    length_m: float
    gain_m: float | None


class SectionResultOut(BaseModel):
    section_id: str
    workout_id: str
    local_date: str
    time_s: float | None
    avg_hr: float | None
    comparable: bool
    n: int  # HR-matched earlier runs
    baseline_time_s: float | None
    baseline_hr: float | None
    gap_s: float | None  # positive = slower
    spread_s: float | None
    z: float | None
    direction: Literal["slower", "faster"] | None
    fires: bool
    reasons: list[str]


class RouteDetailOut(RouteOut):
    sections: list[SectionOut]
    runs: list[WorkoutOut]
    results: list[SectionResultOut]


class RouteOverrideIn(BaseModel):
    workout_a: str = Field(min_length=1, max_length=64)
    workout_b: str = Field(min_length=1, max_length=64)
    action: Literal["join", "split"]

    @model_validator(mode="after")
    def _distinct(self):
        if self.workout_a == self.workout_b:
            raise ValueError("an override needs two different runs")
        return self


class RouteOverrideOut(BaseModel):
    workout_a: str
    workout_b: str
    action: Literal["join", "split"]


# --- Privacy zones (FR-23b) -----------------------------------------------------------------------------------------

class PrivacyZoneIn(BaseModel):
    """Input only. The centre is accepted here and never returned by any endpoint."""
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_m: float = Field(400.0, ge=50, le=5000)


class PrivacyZoneOut(BaseModel):
    id: int
    radius_m: float


# --- Settings -------------------------------------------------------------------------------------------------------

class AiSettingsIn(BaseModel):
    provider: Literal["nvidia", "openai-compatible"] = "nvidia"
    base_url: str | None = Field(None, max_length=300)
    model: str | None = Field(None, max_length=120)
    api_key: str | None = Field(None, max_length=500, description="Write-only. Omit to keep the stored key; empty string removes it.")


class AiSettingsOut(BaseModel):
    provider: Literal["nvidia", "openai-compatible"]
    base_url: str | None  # as stored; None means the provider default below
    model: str | None
    default_base_url: str
    default_model: str
    has_key: bool
    enabled: bool  # AI stays off until a key is set (FR-28)


class WeatherSettingsIn(BaseModel):
    enabled: bool


class WeatherSettingsOut(BaseModel):
    enabled: bool
    provider_host: str
    fetched: int  # outdoor workouts with fetched weather
    unavailable: int
    skipped: int  # nothing left outside the privacy zones to place the run


class ThresholdsIn(BaseModel):
    overrides: dict[str, dict[str, JsonValue]]


class ThresholdsOut(BaseModel):
    defaults: dict[str, dict[str, JsonValue]]
    overrides: dict[str, dict[str, JsonValue]]
    recompute_pending: bool


class ImportStatusOut(BaseModel):
    """Progress of the latest Apple Health export import."""
    payload_id: int
    state: Literal["queued", "validating", "writing", "done", "failed"]
    workouts: int
    merged: int
    kept_existing: int
    metrics: int
    nights: int
    date_from: str | None
    date_to: str | None
    error: str | None  # exception class name only
    updated_at: str


class HealthOut(BaseModel):
    status: Literal["ok"]


# --- Home-workout plans (persistent tier) -----------------------------------------------------------------------
class MoveIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    reps: int | None = Field(None, ge=1, le=500)
    seconds: int | None = Field(None, ge=5, le=600)
    weight_kg: float | None = Field(None, ge=0.5, le=100)  # None = bodyweight

    @field_validator("name", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _one_of_reps_or_seconds(self):
        if (self.reps is None) == (self.seconds is None):
            raise ValueError("a move needs exactly one of reps or seconds")
        return self


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    format: Literal["amrap", "emom", "complex"]
    cap_min: int | None = Field(None, ge=1, le=90)
    emom_min: int | None = Field(None, ge=1, le=90)
    rounds: int | None = Field(None, ge=1, le=50)
    moves: list[MoveIn] = Field(min_length=1, max_length=12)
    video_url: str | None = Field(None, max_length=500)

    @field_validator("name", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("video_url", mode="before")
    @classmethod
    def _url(cls, v):
        from urllib.parse import urlparse
        if v is None:
            return None
        if not isinstance(v, str):
            return v
        v = v.strip()
        if not v:
            return None
        u = urlparse(v)
        if u.scheme not in ("http", "https") or not u.netloc:
            raise ValueError("the video link must be an http or https URL")
        return v

    @model_validator(mode="after")
    def _format_setting(self):
        need = {"amrap": "cap_min", "emom": "emom_min", "complex": "rounds"}[self.format]
        if getattr(self, need) is None:
            raise ValueError(f"{self.format} needs {need}")
        for f in ("cap_min", "emom_min", "rounds"):  # settings of other formats are dropped
            if f != need:
                setattr(self, f, None)
        return self


class YoutubeImportIn(BaseModel):
    url: str = Field(max_length=500)


class PlanDraftOut(BaseModel):
    """A plan built from a video, not saved. `title` is the video's, for the editor's note."""
    title: str
    plan: PlanIn


class LastSessionOut(BaseModel):
    id: int  # the session, for the library's link to its summary
    rounds: int
    partial_moves: int
    date: str  # RFC 3339 UTC start of the latest session


class PlanOut(BaseModel):
    id: int
    name: str
    format: Literal["amrap", "emom", "complex"]
    cap_min: int | None
    emom_min: int | None
    rounds: int | None
    moves: list[MoveIn]
    video_url: str | None
    created_at: str
    updated_at: str
    last_session: LastSessionOut | None = None


# --- Home-workout sessions (persistent tier) ---------------------------------------------------------------------
MAX_SESSION_MS = 4 * 3600 * 1000  # a session is at most 4 h
MAX_SESSION_EVENTS = 5000


class SessionEvent(BaseModel):
    t_ms: int = Field(ge=0, le=MAX_SESSION_MS)  # wall milliseconds since the start
    kind: Literal["next", "auto", "flag", "pause", "resume", "end"]
    move: int = Field(ge=0, le=100)  # 0-based position when it happened
    round: int = Field(ge=0, le=1000)


class SessionIn(BaseModel):
    plan_id: int | None = None
    plan: PlanIn
    weight_kg: float | None = Field(None, ge=0.5, le=300)
    start_utc: datetime
    end_utc: datetime
    events: list[SessionEvent] = Field(max_length=MAX_SESSION_EVENTS)
    rounds_done: int = Field(ge=0, le=1000)
    partial_moves: int = Field(ge=0, le=100)
    fell_short: list[Annotated[int, Field(ge=1, le=90)]] = Field(default_factory=list, max_length=100)  # 1-based EMOM minutes

    @model_validator(mode="after")
    def _duration(self):
        if (self.start_utc.tzinfo is None) != (self.end_utc.tzinfo is None):
            raise ValueError("start_utc and end_utc must both carry a timezone, or both not")
        if self.plan.format == "emom" and self.plan.emom_min and any(m > self.plan.emom_min for m in self.fell_short):
            raise ValueError("a fell-short minute is beyond the workout's last minute")
        span = (self.end_utc - self.start_utc).total_seconds() * 1000
        if span < 0 or span > MAX_SESSION_MS:
            raise ValueError("a session lasts between 0 and 4 hours")
        return self


class SessionOut(BaseModel):
    id: int
    plan_id: int | None
    plan: PlanIn
    weight_kg: float | None
    start_utc: str
    end_utc: str
    events: list[SessionEvent]
    rounds_done: int
    partial_moves: int
    fell_short: list[int]
    active_s: int
    overtime_s: int
    created_at: str


class EffortIn(BaseModel):
    effort: int = Field(ge=1, le=10)


class EffortOut(BaseModel):
    effort: int


SHORT_MINUTES = 90


class SessionShortRow(BaseModel):
    minute: int  # 1-based
    move: str
    target_reps: int | None  # None for a timed move
    short_reps: int | None  # what he did, once answered


class SessionMoveHr(BaseModel):
    name: str
    avg_hr: float
    instances: int


class SessionRoundRow(BaseModel):
    round: int  # 1-based
    time_s: int
    moves: int
    avg_hr: float | None


class SessionSummaryOut(BaseModel):
    session: SessionOut
    matched_workout_id: str | None  # the strength workout whose HR and effort this summary borrows
    avg_hr: float | None
    effort: float | None
    effort_source: Literal["watch", "manual"] | None
    effort_estimated: bool  # the watch value shown is its estimate, not a rating he gave
    moves: list[SessionMoveHr]
    rounds: list[SessionRoundRow]
    zone_seconds: list[float] | None
    zone_bounds_bpm: list[float] | None
    fell_short: list[SessionShortRow]


class StreakWeekOut(BaseModel):
    week_start: str  # the Monday, YYYY-MM-DD
    counted: bool


class StreakOut(BaseModel):
    weeks: int
    this_week: bool
    last_streak: int
    recent: list[StreakWeekOut]  # last 8 weeks, oldest first, the current week last
