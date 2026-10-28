"""fetch_weather job: fills `workout_weather` for outdoor workouts while the runner has weather turned on.

Location is the start of the privacy-clipped display track (so never a point inside a zone), coarsened to a
0.1 degree cell; a run with nothing left after clipping is `skipped`. One provider reply per (cell, UTC date) is
cached, so a day's runs and later runs in the same area cost one request. A failure marks the run
`unavailable` and is retried on a later tick; it never blocks ingest or a recompute (AD-5).
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from strydr.egress import EgressError
from strydr.egress.weather import OpenMeteo, WeatherRequest, cell_of
from strydr.store import models, settings
from strydr.store.generations import scoped
from strydr.store.util import utcnow

log = logging.getLogger("strydr.jobs")
MAX_REQUESTS = 120  # per job; Open-Meteo allows 600 a minute, and the next tick picks up the rest
MAX_ATTEMPTS = 5
RETRY_AFTER = timedelta(hours=6)
_MAP = {"temp_c": "temperature_2m", "humidity_pct": "relative_humidity_2m", "dew_point_c": "dew_point_2m",
        "apparent_c": "apparent_temperature", "precip_mm_h": "precipitation", "wind_ms": "wind_speed_10m",
        "wind_dir_deg": "wind_direction_10m", "gust_ms": "wind_gusts_10m", "cloud_pct": "cloud_cover"}


def _summary(hourly: dict, start: datetime, end: datetime) -> dict | None:
    """Mean of each value over the hours the run touched; None when the provider had no temperature for them."""
    first = start.replace(minute=0, second=0, microsecond=0)
    hours = {f"{(first + timedelta(hours=i)):%Y-%m-%dT%H:00}" for i in range(int((end - first).total_seconds() // 3600) + 1)}
    idx = [i for i, t in enumerate(hourly["time"]) if t in hours]
    out = {}
    for col, key in _MAP.items():
        vals = [hourly[key][i] for i in idx if hourly[key][i] is not None]
        out[col] = round(sum(vals) / len(vals), 1) if vals else None
    if out["temp_c"] is None:
        return None
    if out["wind_dir_deg"] is not None:  # a mean of angles is only meaningful for the single hour most runs take
        out["wind_dir_deg"] = hourly[_MAP["wind_dir_deg"]][idx[0]]
    return out


def fetch(engine: Engine, client: OpenMeteo, now: datetime | None = None) -> int:
    """Returns how many workouts gained weather (the caller recomputes when it is more than zero)."""
    now = now or utcnow()
    with Session(engine) as s:
        if not settings.read_weather_enabled(s):
            return 0
        workouts = s.execute(select(models.Workout).where(models.Workout.is_indoor.is_(False))
                             .order_by(models.Workout.start_utc)).scalars().all()
        starts = {wid: g["start"] if g else None for wid, g in s.execute(
            scoped(models.WorkoutDisplay).with_only_columns(models.WorkoutDisplay.workout_id, models.WorkoutDisplay.display_geometry))}
        have = {r.workout_id: r for r in s.execute(select(models.WorkoutWeather)).scalars()}
        s.expunge_all()

    added, requests = 0, 0
    for w in workouts:
        old = have.get(w.workout_id)
        if old is not None and (old.status in ("ok", "skipped") or old.attempts >= MAX_ATTEMPTS
                                or now - old.fetched_at < RETRY_AFTER):
            continue
        if w.workout_id not in starts:
            continue  # not derived yet: the next tick has its display track
        point = starts[w.workout_id]
        row = {"status": "skipped"}
        if point is not None:
            lat, lon = cell_of(*point)
            req = WeatherRequest(lat=lat, lon=lon, utc_date=w.start_utc.date().isoformat())
            with Session(engine) as s:
                cached = s.get(models.WeatherCache, (req.cell, req.utc_date))
                hourly = cached.hourly if cached else None
            if hourly is None:
                if requests >= MAX_REQUESTS:
                    break
                requests += 1
                try:
                    hourly = client.hourly(req)
                except EgressError as e:
                    log.warning("weather fetch failed: %s", e)
                    _store(engine, w.workout_id, {"status": "unavailable"}, old, now)
                    break  # the provider or the network is down: try again on a later tick
                with Session(engine) as s:
                    s.merge(models.WeatherCache(cell=req.cell, utc_date=req.utc_date, hourly=hourly, fetched_at=now))
                    s.commit()
            summary = _summary(hourly, w.start_utc, w.end_utc)
            if summary is None:
                with Session(engine) as s:  # an incomplete reply: forget it so a retry asks again
                    s.execute(delete(models.WeatherCache).where(
                        models.WeatherCache.cell == req.cell, models.WeatherCache.utc_date == req.utc_date))
                    s.commit()
                row = {"status": "unavailable"}
            else:
                row = {"status": "ok", **summary}
                added += 1
        _store(engine, w.workout_id, row, old, now)
    log.info("weather: %d workouts updated, %d requests", added, requests)
    return added


def _store(engine: Engine, workout_id: str, row: dict, old, now: datetime) -> None:
    with Session(engine) as s:
        s.merge(models.WorkoutWeather(workout_id=workout_id, attempts=(old.attempts if old else 0) + 1,
                                      fetched_at=now, **{c: None for c in _MAP} | row))
        s.commit()


def clear(s: Session) -> None:
    """Turning weather off forgets everything fetched; the caller recomputes."""
    s.execute(delete(models.WorkoutWeather))
    s.execute(delete(models.WeatherCache))
