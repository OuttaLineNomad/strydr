"""Insight contract types (AD-8): `InsightFact` and the `DerivedSnapshot` rules read.

`DerivedSnapshot` is plain frozen dataclasses of builtins and `date`s, so the recompute can fill it
from the analytic/canonical tables (named per field below) and tests can build it by hand. Rules never
touch the DB or the clock; everything is relative to `as_of`. SI units throughout (m, s, m/s, bpm, degC).
"""
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from strydr.pipeline.derive.days import DayClass
from strydr.pipeline.derive.load.model import TrainingStateDay

M_PER_UNIT = {"km": 1000.0, "mi": 1609.344}  # metres per runner distance unit

InsightKind = Literal["observation", "attaboy", "check-reading"]
KINDS: tuple[str, ...] = ("observation", "attaboy", "check-reading")


@dataclass(frozen=True, slots=True)
class InsightFact:
    """AD-8, exactly. There is no severity or risk field. `evidence` = {rule, data, note} (FR-19)."""

    insight_key: str  # {rule_id}:{subject}:{period}  (AD-6)
    rule_id: str
    subject: str  # run/{workout_id} | week/{week_id} | route/{route_key} | athlete
    period: str  # YYYY-MM-DD | week_id; episode-start date for ongoing conditions
    kind: InsightKind
    number: float
    unit: str
    evidence: dict[str, Any]
    template_id: str


@dataclass(frozen=True, slots=True)
class MinutePoint:
    """One minute of a run, resampled by the recompute from `sample_series` (HR avg, route speed/alt)."""

    hr: float | None  # per-minute Avg HR (bpm)
    speed_mps: float | None  # mean GPS speed over the minute
    altitude_m: float | None  # altitude at the start of the minute


@dataclass(frozen=True, slots=True)
class RunSummary:
    """One run (type == 'run' only; walks/hikes never reach the rules, FR-7a).

    Source: `workout` row + `derive/summary` flags + minute resampling of `sample_series`.
    """

    workout_id: str
    local_date: date
    distance_m: float | None
    duration_s: float | None
    avg_speed_mps: float | None
    avg_hr: float | None
    elevation_gain_m: float | None
    temperature_c: float | None  # None when the export carries no weather (rules then skip heat tagging)
    is_indoor: bool
    is_long_run: bool  # derive/summary
    is_easy_intended: bool  # derive/summary
    hr_time_s: float | None  # post-warm-up seconds with HR, derive/summary intensity mix
    easy_time_s: float | None  # of which at or below the easy ceiling (<= hr_time_s)
    hr_coverage: float | None  # share of the post-warm-up minutes with HR (0..1)
    minutes: tuple[MinutePoint, ...] | None = None  # None when no per-minute series exists
    conditions: dict | None = None  # derive/conditions (dew point, heat adjustment, band); None indoors or unknown
    gap: dict | None = None  # derive/grade: whole-run grade adjusted pace and relief; None without altitude
    sleep: dict | None = None  # derive/sleep: the night before (hours, stages, quality, usual) and morning RHR/HRV
    carry_kg: float | None = None  # workout_carry: extra mass carried (> 0); None = uncarried. Splits runs into two cohorts


@dataclass(frozen=True, slots=True)
class PeriodVolume:
    """Running volume for a week (`period_id` = week_id) or a calendar month (`YYYY-MM`). derive/summary."""

    period_id: str
    start: date  # Monday of the week / first of the month
    end: date  # Sunday / last of the month
    distance_m: float
    duration_s: float
    run_count: int


@dataclass(frozen=True, slots=True)
class BestEffort:
    """A best effort on a run, from derive/records. Only `is_record` efforts become attaboys."""

    workout_id: str
    local_date: date
    label: str  # 1k | 1mi | 5k | 10k | half | marathon ...
    distance_m: float
    time_s: float
    is_record: bool  # best at the time of the run (all-time scope)
    gps_ok: bool  # passed the GPS sanity check (FR-18); failing efforts never fire


@dataclass(frozen=True, slots=True)
class DailyValue:
    local_date: date
    value: float


@dataclass(frozen=True, slots=True)
class Baseline:
    """A profile-owned baseline (AD-7): mean/SD over `n_days` valid days. HRV values are in ln(SDNN)."""

    mean: float
    sd: float
    n_days: int


@dataclass(frozen=True, slots=True)
class DerivedSnapshot:
    """Everything the tier-1 rules read, as of one local date.

    Fields and where they come from (all ascending by date):
      as_of            recompute(as_of): local date in home_tz (AD-15)
      units            settings.units: "km" | "mi" (lifetime milestones are in this unit)
      hr_max           profile: resolved HRmax (FR-31)
      easy_ceiling_bpm profile: easy ceiling (runner's zone, default 80% HRmax)
      history_start    earliest canonical workout local date (None = no data)
      runs             all runs: workout + derive/summary flags (full history; rules slice windows)
      weekly / monthly derive/summary: running volume per ISO week / calendar month (runs only);
                       missing periods mean zero
      best_efforts     derive/records: best efforts on runs
      carried_run_dates local dates with a carried run (workout_carry); a hard-day stack including one says so
      days             derive/days: DayClass for every local date up to as_of (zero-filled, with load)
      training_state   derive/load: TrainingStateDay for as_of (None = unavailable)
      resting_hr       daily_metric resting_heart_rate: the day's value, profile outliers already removed
      rhr_baseline     profile: 30-day mean/SD ending the day before the last 3 days (n valid days)
      hrv_sdnn_ms      daily_metric heart_rate_variability: the day's SDNN in ms
      hrv_baseline     profile: mean/SD of the daily ln(SDNN) over the 60 days ending 7 days before as_of
    """

    as_of: date
    units: Literal["km", "mi"]
    hr_max: float
    easy_ceiling_bpm: float
    history_start: date | None
    runs: tuple[RunSummary, ...] = ()
    weekly: tuple[PeriodVolume, ...] = ()
    monthly: tuple[PeriodVolume, ...] = ()
    best_efforts: tuple[BestEffort, ...] = ()
    days: tuple[DayClass, ...] = ()
    training_state: TrainingStateDay | None = None
    resting_hr: tuple[DailyValue, ...] = ()
    rhr_baseline: Baseline | None = None
    hrv_sdnn_ms: tuple[DailyValue, ...] = ()
    hrv_baseline: Baseline | None = None
    carried_run_dates: frozenset[date] = frozenset()
