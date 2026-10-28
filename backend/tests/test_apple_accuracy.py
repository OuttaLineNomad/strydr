"""Numbers agree with the watch: pauses excluded, the watch's own speed, ascent and splits (adapter v2). Synthetic data."""
import copy
from datetime import datetime

from sqlalchemy.orm import Session

from conftest import load_fixture, workouts
from helpers import recompute_now
from strydr.pipeline.derive import track
from strydr.sources.canonical import active_seconds as _active
from strydr.sources.hae.adapter import _pauses, convert_workout
from strydr.store import models

def _run() -> dict:
    body = load_fixture("hae-export.json")
    return copy.deepcopy(next(w for w in body["data"]["workouts"] if w["name"] == "Outdoor Run"))


def test_pause_events_become_active_time():
    p = _pauses([{"type": "pause", "start": "2026-03-03 07:10:00 +0000"}, {"type": "resume", "start": "2026-03-03 07:10:30 +0000"}],
                datetime(2026, 3, 3, 7, 0, 0))
    assert p == [(600.0, 630.0)]
    assert _active(500, p) == 500 and _active(615, p) == 600 and _active(700, p) == 670


def test_average_speed_is_over_active_time_not_elapsed():
    w = _run()
    w["avgSpeed"] = {"qty": 1.0, "units": "mi"}  # an elapsed-time figure that must lose
    w["activities"][0]["metrics"] = {"speed": {"qty": 3.25, "units": "m/s"}}
    assert convert_workout(w).avg_speed_mps == 3.25
    del w["activities"][0]["metrics"]
    out = convert_workout(w)
    assert abs(out.avg_speed_mps - out.distance_m / out.duration_s) < 1e-9


def test_watch_ascent_wins_over_the_gps_estimate():
    w = _run()
    w["elevationUp"] = {"qty": 47.0, "units": "ft"}
    assert abs(convert_workout(w).elevation_gain_m - 47.0 * 0.3048) < 1e-9


def test_watch_splits_are_shown_and_paused_time_is_left_out(engine, send):
    body = load_fixture("hae-export.json")
    run = next(w for w in body["data"]["workouts"] if w["name"] == "Outdoor Run")
    t0 = run["start"]
    # pause for 60 s two minutes in
    hh, mm = int(t0[11:13]), int(t0[14:16])
    run["events"] = [{"type": "pause", "start": f"{t0[:11]}{hh:02d}:{mm + 2:02d}:00{t0[19:]}"},
                     {"type": "resume", "start": f"{t0[:11]}{hh:02d}:{mm + 3:02d}:00{t0[19:]}"}]
    send(body)
    wid = run["id"]
    recompute_now(engine, run["start"][:10])
    with Session(engine) as s:
        d = s.query(models.WorkoutDetail).filter_by(workout_id=wid).one()
        series = {x.series for x in s.query(models.SampleSeries).filter_by(workout_id=wid)}
    assert "splits" in series
    own = [x for x in run["splits"] if x["targetDistance"]["units"] == "km"][0]["items"]
    assert [round(x["duration_s"], 1) for x in d.splits_km] == [round(i["activeDuration"], 1) for i in own]


def test_source_splits_mark_the_last_short_split_partial():
    own = {"unit": ["mi", "mi", "mi"], "index": [0, 1, 2], "distance_m": [1609.344, 1609.344, 34.5],
           "duration_s": [968.5, 844.0, 39.0], "avg_hr": [124.0, 143.0, 158.0]}
    dist = [0.0, 1700.0, 3253.2]
    rows = track.source_splits(own, "mi", dist, [10.0, 12.0, 11.0])
    assert [r["duration_s"] for r in rows] == [968.5, 844.0, 39.0]
    assert [r["partial"] for r in rows] == [False, False, True]
    assert rows[1]["avg_hr"] == 143.0


def test_short_bests_come_from_the_watch_splits():
    from strydr.pipeline.derive.records import best_from_splits
    own = {"unit": ["mi", "mi", "mi", "km", "km", "km"], "distance_m": [1609.344, 1609.344, 34.5, 1000.0, 1000.0, 917.0],
           "duration_s": [968.5, 844.0, 39.0, 588.0, 526.0, 300.0], "index": [0, 1, 2, 0, 1, 2], "avg_hr": [None] * 6}
    got = best_from_splits(own, {"1km": 480.0, "1mi": 820.0, "5km": 3000.0})
    assert got == {"1km": 526.0, "1mi": 844.0, "5km": 3000.0}  # partial splits never count; 5 km keeps the GPS value
