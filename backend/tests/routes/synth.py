"""Synthetic route geometry in an invented spot (mid-Atlantic); no real data."""
import math
import random
from datetime import datetime, timedelta

import numpy as np

from strydr.pipeline.derive.routes import geo
from strydr.sources.canonical import SampleSeries, Workout

ORIGIN = (10.0, -40.0)
STEP_M = 3.0


def circle(r: float = 480.0, cx: float = 0.0, ccw: bool = True, start_east: bool = False) -> np.ndarray:
    """A loop of centre (cx, 0). Starts at its west point, or its east point when start_east.

    r=480 gives about 3.0 km. The default loop starts at (cx - r, 0).
    """
    n = int(2 * math.pi * r / STEP_M)
    ang = np.linspace(0, 2 * math.pi, n + 1)
    sign = 1 if ccw else -1
    x = cx + r * np.cos(ang) if start_east else cx - r * np.cos(ang)
    return np.column_stack([x, sign * r * np.sin(ang)])


def line(length: float = 3000.0, y: float = 0.0) -> np.ndarray:
    xs = np.arange(0, length + STEP_M, STEP_M)
    return np.column_stack([xs, np.full(len(xs), y)])


def with_spur(xy: np.ndarray, at: int, length: float = 120.0, direction=(0.0, 1.0)) -> np.ndarray:
    """Insert an out-and-back detour of `length` metres at vertex `at`."""
    d = np.arange(STEP_M, length + STEP_M, STEP_M)
    d = np.concatenate([d, d[::-1][1:]])
    spur = xy[at] + np.outer(d, direction)
    return np.vstack([xy[: at + 1], spur, xy[at + 1:]])


def make_workout(
    wid: str, day: int, xy: np.ndarray, speed: float = 3.0, alt=None, noise: float = 0.0,
    seed: int = 0, hr_bpm: float | None = None, month: int = 3, rtype: str = "run",
) -> Workout:
    """A 1 Hz-ish run along `xy` at constant `speed`; `alt` maps distance-along (m) to altitude (m)."""
    rng = random.Random(seed)
    pts = np.array(xy, dtype=float)
    if noise:
        pts = pts + np.array([[rng.gauss(0, noise), rng.gauss(0, noise)] for _ in pts])
    cum = geo.cumulative(xy)
    t = (cum / speed).tolist()
    lat, lon = geo.unproject(pts, ORIGIN)
    alts = [None] * len(t) if alt is None else [float(alt(c)) for c in cum]
    start = datetime(2026, month, day, 7, 0, 0)
    dur = t[-1]
    series = {"route": SampleSeries("route", {
        "t": t, "lat": lat.tolist(), "lon": lon.tolist(), "alt": alts, "speed": [speed] * len(t),
    })}
    if hr_bpm is not None:
        mins = list(range(0, int(dur) + 60, 60))
        series["heart_rate"] = SampleSeries("heart_rate", {
            "t": [float(m) for m in mins], "min": [hr_bpm] * len(mins),
            "avg": [hr_bpm] * len(mins), "max": [hr_bpm] * len(mins),
        })
    return Workout(
        workout_id=wid, type=rtype, is_indoor=False, start_utc=start,
        end_utc=start + timedelta(seconds=dur), utc_offset_s=0, local_date=start.date().isoformat(),
        duration_s=dur, series=series,
    )
