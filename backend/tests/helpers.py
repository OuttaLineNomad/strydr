"""Synthetic canonical data for analytic tests. Everything here is invented."""
import json
from dataclasses import replace
import zlib
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from strydr.jobs.recompute import recompute
from strydr.store import models

ORIGIN = (52.3700, 4.8900)  # arbitrary, as in fixtures/generate_hae_export.py


def add_run(engine, wid: str, start: datetime, minutes: int, speed_mps: float = 3.0, *, hr: float | list[float] | None = 150.0,
            route: bool = True, reported_m: float | None = None, speed_fn=None, type_: str = "run",
            origin=ORIGIN, cadence_fn=None) -> float:
    """Insert a canonical workout: a straight track at 1 Hz and per-minute HR buckets. Returns the track length."""
    seconds = minutes * 60
    t, lat, speeds = list(range(seconds + 1)), [origin[0]], []
    for i in range(seconds):
        v = speed_fn(i) if speed_fn else speed_mps
        speeds.append(v)
        lat.append(lat[-1] + v / 111_320)
    dist = sum(speeds)
    series = {}
    if route:
        series["route"] = {"t": t, "lat": lat, "lon": [origin[1]] * len(t), "alt": [10 + (i % 60) / 10 for i in t], "at": [float(i) for i in t],
                           "speed": speeds + [speeds[-1]]}
    if cadence_fn:  # steps per minute at second i -> 10 s step intervals, as the adapters store them
        ts = list(range(0, seconds, 10))
        series["step_count"] = {"t": ts, "dt": [10.0] * len(ts), "steps": [cadence_fn(i) / 6 for i in ts]}
    avgs = None if hr is None else (hr if isinstance(hr, list) else [hr] * minutes)
    if avgs is not None:
        series["heart_rate"] = {"t": [m * 60 + 30 for m in range(len(avgs))], "min": [a - 4 for a in avgs],
                                "avg": avgs, "max": [a + 5 for a in avgs]}
    with Session(engine) as s:
        s.add(models.Workout(
            workout_id=wid, type=type_, is_indoor=not route, start_utc=start,
            end_utc=start + timedelta(seconds=seconds), utc_offset_s=0, local_date=start.date().isoformat(),
            duration_s=float(seconds), distance_m=reported_m if reported_m is not None else dist,
            avg_speed_mps=dist / seconds, avg_hr=sum(avgs) / len(avgs) if avgs else None,
            max_hr=max(avgs) + 5 if avgs else None, elevation_gain_m=30.0,
            quality_flags={}, series_count=len(series), sample_count=sum(len(v["t"]) for v in series.values()),
            adapter_version=1, received_at=start))
        s.flush()
        for name, cols in series.items():
            s.add(models.SampleSeries(workout_id=wid, series=name, n_samples=len(cols["t"]), adapter_version=1,
                                      data=zlib.compress(json.dumps(cols).encode())))
        s.commit()
    return dist


def set_hrmax(engine, hrmax: int) -> None:
    """HRmax is the runner's override or comes from age; tests that need zones pin it before the recompute."""
    from strydr.store import settings
    with Session(engine) as s:
        settings.write(s, replace(settings.read(s), hrmax_override=hrmax))
        s.commit()


def recompute_now(engine, as_of: str) -> int:
    return recompute(engine, as_of)


def login(client) -> None:
    r = client.post("/api/v1/auth/login", json={"username": "runner", "password": "correct horse battery"})
    assert r.status_code == 204
