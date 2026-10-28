"""Profile stage: resolves the runner's physiological reference values for one generation (AD-7)."""
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.pipeline.context import Context
from strydr.pipeline.hr import active_clock
from strydr.pipeline.profile import resolve
from strydr.store import generations, models, series, settings


@dataclass(frozen=True)
class Profile:
    sex: str | None
    birth_year: int | None
    units: str
    hrmax: int | None
    hrmax_source: str
    zone_bounds_bpm: list[float] | None  # upper bounds of zones 1-4; zone 5 is above the last
    easy_ceiling_bpm: float | None
    rhr_7d_median: float | None
    rhr_30d_baseline: float | None
    hrv_60d_baseline: float | None
    rhr_baseline: resolve.BaselineStats | None = None  # mean/SD for the resting-HR rule
    hrv_baseline: resolve.BaselineStats | None = None  # mean/SD of ln(SDNN) for the HRV rule


def run(ctx: Context) -> Profile:
    with Session(ctx.engine) as s:
        cfg = settings.read(s, ctx.tz.key)
        window_start = (ctx.as_of - timedelta(days=resolve.OBSERVED_WINDOW_DAYS)).isoformat()
        run_ids = s.execute(select(models.Workout.workout_id).where(
            models.Workout.type == "run", models.Workout.local_date > window_start,
            models.Workout.local_date <= ctx.as_of.isoformat(), models.Workout.series_count > 0)).scalars().all()
        hr_runs = []
        for wid in run_ids:
            hr = series.load_series(s, wid).get("heart_rate")
            if hr:
                hr_runs.append((active_clock(hr), hr["avg"]))
        observed = resolve.observed_hrmax(hr_runs)
        found = resolve.resolve_hrmax(cfg.hrmax_override, observed, len(hr_runs), cfg.birth_year, ctx.as_of)
        bounds = resolve.zone_bounds_bpm(found.hrmax, cfg.zone_bounds_pct)
        rhr = _daily(s, "resting_heart_rate")
        hrv = _daily(s, "heart_rate_variability")

    profile = Profile(
        sex=cfg.sex, birth_year=cfg.birth_year, units=cfg.units, hrmax=found.hrmax, hrmax_source=found.source,
        zone_bounds_bpm=bounds, easy_ceiling_bpm=resolve.easy_ceiling_bpm(bounds),
        rhr_7d_median=resolve.window_median(rhr, ctx.as_of, 7, resolve.RHR_PLAUSIBLE),
        rhr_30d_baseline=resolve.window_median(rhr, ctx.as_of, 30, resolve.RHR_PLAUSIBLE),
        hrv_60d_baseline=resolve.window_median(hrv, ctx.as_of, 60, resolve.HRV_PLAUSIBLE),
        rhr_baseline=resolve.rhr_baseline(rhr, ctx.as_of), hrv_baseline=resolve.hrv_baseline(hrv, ctx.as_of),
    )
    rb, hb = profile.rhr_baseline, profile.hrv_baseline
    generations.add_rows(ctx.engine, [models.ProfileResult(
        generation_id=ctx.generation_id, hrmax=profile.hrmax, hrmax_source=profile.hrmax_source,
        zone_bounds_bpm=profile.zone_bounds_bpm, easy_ceiling_bpm=profile.easy_ceiling_bpm,
        rhr_7d_median=profile.rhr_7d_median, rhr_30d_baseline=profile.rhr_30d_baseline,
        hrv_60d_baseline=profile.hrv_60d_baseline,
        rhr_baseline_mean=rb and rb.mean, rhr_baseline_sd=rb and rb.sd, rhr_baseline_days=rb and rb.n_days,
        hrv_baseline_mean=hb and hb.mean, hrv_baseline_sd=hb and hb.sd, hrv_baseline_days=hb and hb.n_days)])
    return profile


def _daily(s: Session, metric: str) -> dict[str, float]:
    return {d: v for d, v in s.execute(select(models.DailyMetric.local_date, models.DailyMetric.value)
                                       .where(models.DailyMetric.metric == metric, models.DailyMetric.value.is_not(None)))}
