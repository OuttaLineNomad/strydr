"""The run context payload (CAP-16, ai-run-context.md): one run as closed-key maps of preformatted strings.

Pure projection: reads the analytic, canonical and settings rows of one `workout_id` and nothing else. Sleep
bedtime, wake, night and hours-before-run, wind direction, data sources and the note text are never read. A value
that is missing, or that would not pass the payload's pattern, is left out.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.egress.payload import TERMS, RunContextPayload, context_sentence_ok, context_value_ok
from strydr.pipeline.phrasing import _when
from strydr.pipeline.phrasing import format as fmt
from strydr.pipeline.phrasing.validate import number_tokens
from strydr.store import models
from strydr.store.generations import in_current

SIMILAR_RUNS = 4
MIN_SIMILAR = 2
DISTANCE_BAND = 0.2
MAX_INSIGHTS = 12
MAX_SPLITS = 60


def _put(group: dict, key: str, value: str | None) -> None:
    if value is not None and context_value_ok(value):
        group[key] = value


def _put_term(group: dict, key: str, value: str | None) -> None:
    if value in TERMS:
        group[key] = value


def _time_band(start_utc: datetime, offset_s: int) -> str:
    hour = (start_utc + timedelta(seconds=offset_s)).hour
    return "morning" if 4 <= hour < 11 else "midday" if 11 <= hour < 16 else "evening"


def _beats_per_km(hr: float | None, speed: float | None) -> float | None:
    return hr / speed * 1000.0 / 60 if hr and speed and speed > 0 else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _run(w: models.Workout, rpe: int | None, units: str, as_of: date, carry_kg: float | None = None) -> dict:
    out: dict = {}
    _put(out, "type", w.type)
    _put(out, "when", _when(w.local_date, as_of))
    _put(out, "time_band", _time_band(w.start_utc, w.utc_offset_s))
    _put(out, "distance", fmt.distance(w.distance_m, units))
    _put(out, "active_time", fmt.duration(w.duration_s))
    _put(out, "avg_pace", fmt.pace(w.avg_speed_mps, units))
    _put(out, "avg_hr", fmt.bpm(w.avg_hr))
    _put(out, "max_hr", fmt.bpm(w.max_hr))
    _put(out, "cadence", fmt.whole(w.avg_cadence, "spm"))
    _put(out, "elevation_gain", fmt.elevation(w.elevation_gain_m, units))
    _put(out, "effort_score", fmt.whole(w.effort_score))
    _put(out, "rpe", None if rpe is None else str(int(rpe)))
    _put(out, "carry", fmt.carry(carry_kg, units))
    return out


def _splits(rows: list[dict] | None, units: str) -> list[dict]:
    out = []
    for s in (rows or [])[:MAX_SPLITS]:
        g: dict = {}
        _put(g, "split", str(int(s["index"]) + 1))
        if s.get("partial"):
            _put(g, "distance", fmt.distance(s.get("distance_m"), units, 2))
        _put(g, "pace", fmt.pace(s.get("speed_mps"), units))
        _put(g, "gap_pace", fmt.pace(s.get("gap_speed_mps"), units))
        _put(g, "hr", fmt.bpm(s.get("avg_hr")))
        _put(g, "elevation_change", fmt.elevation(s.get("elevation_change_m"), units, signed=True))
        out.append(g)
    return out


def _terrain(gap: dict | None, units: str) -> dict:
    out: dict = {}
    if gap:
        _put(out, "gap_pace", fmt.pace(gap.get("gap_speed_mps"), units))
        _put(out, "relief", fmt.elevation(gap.get("relief_m"), units))
        _put(out, "relief_per_distance", fmt.relief_per_unit(gap.get("relief_m_per_km"), units))
        if gap.get("hilly") is not None:
            _put(out, "hilly", "yes" if gap["hilly"] else "no")
    return out


def _conditions(c: dict | None, units: str) -> dict:
    out: dict = {}
    if c:
        _put(out, "temperature", fmt.temperature(c.get("temp_c"), units))
        _put(out, "feels_like", fmt.temperature(c.get("apparent_c"), units))
        _put(out, "humidity", fmt.percent(c.get("humidity_pct")))
        _put(out, "dew_point", fmt.temperature(c.get("dew_point_c"), units))
        _put(out, "wind", fmt.wind(c.get("wind_ms"), units))
        if fmt.finite(c.get("precip_mm_h")):
            _put(out, "rain", f"{c['precip_mm_h']:.1f} mm/h" if c.get("rain") else "Dry")
        _put(out, "cloud", fmt.percent(c.get("cloud_pct")))
        if fmt.finite(c.get("heat_adjust_pct")):
            _put(out, "heat_adjustment", f"{c['heat_adjust_pct']:.1f}%")
        _put_term(out, "band", c.get("band"))
    return out


def _vs_usual(v: float | None, usual: float | None, unit: str) -> str | None:
    """The difference between the two values as shown (rounded), so the three numbers always add up."""
    if not fmt.finite(v) or not fmt.finite(usual):
        return None
    d = fmt.js_round(v) - fmt.js_round(usual)
    return "0 " + unit if d == 0 else fmt.signed_whole(d, unit)


def _sleep(z: dict | None) -> dict:
    out: dict = {}
    if z:
        _put(out, "hours", fmt.hours(z.get("total_h")))
        for key, field in (("deep", "deep_h"), ("core", "core_h"), ("rem", "rem_h"), ("awake", "awake_h")):
            _put(out, key, fmt.hours(z.get(field)))
        _put(out, "efficiency", fmt.percent(z.get("efficiency_pct")))
        _put(out, "usual_sleep", fmt.hours(z.get("usual_h")))
        total, usual = z.get("total_h"), z.get("usual_h")
        if fmt.finite(total) and fmt.finite(usual):
            mins = fmt.js_round(total * 60) - fmt.js_round(usual * 60)  # from the two shown values
            _put(out, "vs_usual", "about usual" if abs(mins) < 15 else fmt.signed_hours(mins / 60))
        _put_term(out, "quality", z.get("quality"))
        if z.get("corrected"):
            out["corrected"] = "Yes, entered by the runner"
        _put(out, "morning_rhr", fmt.bpm(z.get("rhr_bpm")))
        _put(out, "usual_rhr", fmt.bpm(z.get("rhr_usual_bpm")))
        _put(out, "rhr_vs_usual", _vs_usual(z.get("rhr_bpm"), z.get("rhr_usual_bpm"), "bpm"))
        _put(out, "morning_hrv", fmt.whole(z.get("hrv_ms"), "ms"))
        _put(out, "usual_hrv", fmt.whole(z.get("hrv_usual_ms"), "ms"))
        _put(out, "hrv_vs_usual", _vs_usual(z.get("hrv_ms"), z.get("hrv_usual_ms"), "ms"))
    return out


def _training(s: Session, w: models.Workout) -> dict:
    out: dict = {}
    load = s.execute(select(models.WorkoutLoad).where(
        in_current(models.WorkoutLoad), models.WorkoutLoad.workout_id == w.workout_id)).scalar_one_or_none()
    if load is not None and load.source != "none":
        _put(out, "run_load", fmt.whole(load.trimp))
    day = date.fromisoformat(w.local_date)
    days = {d.local_date: d for d in s.execute(select(models.DailyLoad).where(
        in_current(models.DailyLoad),
        models.DailyLoad.local_date.between((day - timedelta(days=6)).isoformat(), w.local_date))).scalars()}
    if days:
        _put(out, "load_7_days", fmt.whole(sum(d.load for d in days.values())))
    today = days.get(w.local_date)
    if today is not None:
        _put(out, "fitness", fmt.whole(today.fitness))
        _put(out, "fatigue", fmt.whole(today.fatigue))
        _put(out, "form", fmt.signed_whole(today.form))
        _put_term(out, "state", today.training_state)
    prev = s.execute(select(models.Workout).where(
        models.Workout.type == "run", models.Workout.start_utc < w.start_utc)
        .order_by(models.Workout.start_utc.desc()).limit(1)).scalar_one_or_none()
    if prev is not None:
        _put(out, "days_since_last_run", str((day - date.fromisoformat(prev.local_date)).days))
    monday = (day - timedelta(days=day.weekday())).isoformat()
    n = s.execute(select(models.Workout.id).where(
        models.Workout.type == "run", models.Workout.local_date >= monday,
        models.Workout.start_utc <= w.start_utc)).all()
    if n:
        _put(out, "runs_this_week", str(len(n)))
    return out


def _similar(s: Session, w: models.Workout) -> list[models.Workout]:
    """Previous runs of the same type and carry status (carried runs only against carried ones): on the same route
    when that gives enough, else within 20% of the distance."""
    carried = select(models.WorkoutCarry.workout_id).where(models.WorkoutCarry.weight_kg > 0)
    mine = s.execute(carried.where(models.WorkoutCarry.workout_id == w.workout_id)).first() is not None
    q = select(models.Workout).where(
        models.Workout.type == w.type, models.Workout.start_utc < w.start_utc,
        models.Workout.workout_id != w.workout_id,
        models.Workout.workout_id.in_(carried) if mine else models.Workout.workout_id.not_in(carried),
    ).order_by(models.Workout.start_utc.desc())
    key = s.execute(select(models.WorkoutRoute.route_key).where(
        in_current(models.WorkoutRoute), models.WorkoutRoute.workout_id == w.workout_id)).scalar_one_or_none()
    if key is not None:
        on_route = list(s.execute(q.where(models.Workout.workout_id.in_(select(models.WorkoutRoute.workout_id).where(
            in_current(models.WorkoutRoute), models.WorkoutRoute.route_key == key))).limit(SIMILAR_RUNS)).scalars())
        if len(on_route) >= MIN_SIMILAR:
            return on_route
    if not w.distance_m:
        return []
    lo, hi = w.distance_m * (1 - DISTANCE_BAND), w.distance_m * (1 + DISTANCE_BAND)
    return list(s.execute(q.where(models.Workout.distance_m.between(lo, hi)).limit(SIMILAR_RUNS)).scalars())


def _comparison(s: Session, w: models.Workout, units: str) -> dict:
    runs = _similar(s, w)
    if len(runs) < MIN_SIMILAR:
        return {}
    out: dict = {}
    _put(out, "similar_runs", str(len(runs)))
    _put(out, "pace", fmt.pace(w.avg_speed_mps, units))
    _put(out, "usual_pace", fmt.pace_from_s(
        _mean([p for r in runs if (p := fmt.pace_s(r.avg_speed_mps, units)) is not None]), units))
    _put(out, "hr", fmt.bpm(w.avg_hr))
    _put(out, "usual_hr", fmt.bpm(_mean([r.avg_hr for r in runs if r.avg_hr])))
    mine = _beats_per_km(w.avg_hr, w.avg_speed_mps)
    _put(out, "beats_per_km", None if mine is None else f"{fmt.js_round(mine)} beats/km")
    usual = _mean([b for r in runs if (b := _beats_per_km(r.avg_hr, r.avg_speed_mps)) is not None])
    _put(out, "usual_beats_per_km", None if usual is None else f"{fmt.js_round(usual)} beats/km")
    return out


def _insights(s: Session, workout_id: str) -> list[dict]:
    rows = s.execute(select(models.InsightFact).where(
        in_current(models.InsightFact), models.InsightFact.subject == f"run/{workout_id}")
        .order_by(models.InsightFact.local_date.desc(), models.InsightFact.insight_key)).scalars()
    out = []
    for r in rows:
        if context_sentence_ok(r.text_template):
            out.append({"rule_id": r.rule_id, "sentence": r.text_template})
        if len(out) >= MAX_INSIGHTS:
            break
    return out


def build_run_context(s: Session, workout_id: str, units: str, as_of: date) -> RunContextPayload | None:
    """The payload for one run, or None when there is no such run. Raises ValidationError only on a code bug."""
    w = s.execute(select(models.Workout).where(models.Workout.workout_id == workout_id)).scalar_one_or_none()
    if w is None:
        return None
    detail = s.execute(select(models.WorkoutDetail).where(
        in_current(models.WorkoutDetail), models.WorkoutDetail.workout_id == workout_id)).scalar_one_or_none()
    rpe = s.execute(select(models.WorkoutNote.rpe).where(models.WorkoutNote.workout_id == workout_id)).scalar_one_or_none()
    carry_kg = s.execute(select(models.WorkoutCarry.weight_kg).where(
        models.WorkoutCarry.workout_id == workout_id)).scalar_one_or_none()
    splits = None if detail is None else (detail.splits_mi if units == "mi" else detail.splits_km)
    return RunContextPayload(
        units=units, run=_run(w, rpe, units, as_of, carry_kg), splits=_splits(splits, units),
        terrain=_terrain(detail.gap if detail else None, units),
        conditions=_conditions(detail.conditions if detail else None, units),
        sleep=_sleep(detail.sleep if detail else None), training=_training(s, w),
        comparison=_comparison(s, w, units), insights=_insights(s, workout_id))


def allowed_numbers_run(payload: RunContextPayload) -> set[str]:
    """Every number as written in the context strings and the insight sentences."""
    texts: list[str] = list(payload.run.values()) + list(payload.terrain.values()) + list(payload.conditions.values())
    texts += list(payload.sleep.values()) + list(payload.training.values()) + list(payload.comparison.values())
    texts += [v for split in payload.splits for v in split.values()]
    texts += [i.sentence for i in payload.insights]
    return set().union(*(number_tokens(t) for t in texts)) if texts else set()
