"""Apple adapter: workout heart rate, route and pauses (story 3), against the fixture export and inline XML."""
import io
from zoneinfo import ZoneInfo

import pytest

from strydr.sources.apple import parse
from strydr.sources.canonical import Workout
from test_apple_adapter import EXPORT, HOME, open_route

_WORKOUTS = None


def _all():
    global _WORKOUTS
    if _WORKOUTS is None:
        with open(EXPORT, "rb") as f:
            _WORKOUTS = {(w.type, w.start_utc.isoformat()): w for w in parse(f, HOME, open_route) if isinstance(w, Workout)}
    return _WORKOUTS


RUN = ("run", "2026-03-03T12:30:20")
PAUSED_WALK = ("walk", "2026-03-04T22:40:20")
NO_HR_WALK = ("walk", "2026-03-05T20:05:00")
SPARSE_WALK = ("walk", "2026-03-09T15:00:00")


def test_twin_run_heart_rate():
    w = _all()[RUN]
    hr = w.series["heart_rate"].columns
    assert list(hr) == ["t", "min", "avg", "max", "at"]
    assert hr["t"] == sorted(hr["t"]) and all(a == b == c for a, b, c in zip(hr["min"], hr["avg"], hr["max"]))
    assert 320 not in hr["max"] and w.quality_flags["hr_samples_dropped"] == 1
    assert all(25 <= v <= 250 for v in hr["avg"]) and len(hr["t"]) == 321
    assert w.series["heart_rate"].n == 321


def test_twin_run_route_and_pause():
    w = _all()[RUN]
    route = w.series["route"].columns
    assert list(route) == ["t", "lat", "lon", "alt", "speed", "at"]
    assert route["t"][:3] == [0.0, 1.0, 2.0] and route["lat"][0] == pytest.approx(52.370019)
    assert route["lon"][0] == pytest.approx(4.890036) and route["alt"][0] == 2.8 and route["speed"][0] == 3.28
    for series in (route, w.series["heart_rate"].columns):
        pairs = list(zip(series["t"], series["at"]))
        assert all(at == t for t, at in pairs if t < 480)  # before the pause
        assert all(at == 480 for t, at in pairs if 480 <= t <= 540)  # inside: parked at the pause's start
        assert all(at == pytest.approx(t - 60) for t, at in pairs if t >= 540)  # after: 60 s removed
    assert "route_missing" not in w.quality_flags and "route_points_dropped" not in w.quality_flags


def test_second_source_is_excluded():
    w = _all()[RUN]
    assert w.series["heart_rate"].n == 321  # the fixture's phone readings inside the twin run are not in it
    xml = (_rec("Watch", "00:10", "00:10", 150) + _rec("Phone", "00:20", "00:20", 90)
           + _rec("Watch", "00:30", "00:30", 152) + _wk())
    (out,) = _items(xml)
    assert out.series["heart_rate"].columns["avg"] == [150, 152]


def test_fixture_phone_reading_excluded_from_twin_walk():
    c = _all()[PAUSED_WALK].series["heart_rate"].columns
    assert (187.0, 118.0) not in set(zip(c["t"], c["avg"]))  # the phone's reading, 3 min 7 s in


def test_other_sources_used_when_workout_source_has_none():
    xml = _rec("Phone", "00:20", "00:20", 90) + _wk()
    (out,) = _items(xml)
    assert out.series["heart_rate"].columns["avg"] == [90]


def test_nested_duplicate_counts_once():
    r = _rec("Watch", "00:10", "00:10", 150)
    (out,) = _items(r + _wk(r + _rec("Watch", "00:20", "00:20", 151)))
    assert out.series["heart_rate"].columns["avg"] == [150, 151]
    assert _all()[RUN].series["heart_rate"].n == 321  # the fixture's nested copy did not add a row


def test_sparse_walk_midpoint():
    cols = _all()[SPARSE_WALK].series["heart_rate"].columns
    assert len(cols["t"]) == 4
    assert cols["t"][1] == 17 * 60 + 45  # (minute 17, span 90 s) -> midpoint


def test_no_hr_walk():
    w = _all()[NO_HR_WALK]
    assert "heart_rate" not in w.series and "route" in w.series


def test_unpaired_pause_is_ignored():
    w = _all()[PAUSED_WALK]
    for name in ("heart_rate", "route"):
        c = w.series[name].columns
        assert c["at"] == c["t"]


def test_pause_resume_and_motion_events_pair():
    events = ('<WorkoutEvent type="HKWorkoutEventTypeMotionPaused" date="2026-03-03 21:02:00 -0500"/>'
              '<WorkoutEvent type="HKWorkoutEventTypeMotionResumed" date="2026-03-03 21:03:00 -0500"/>')
    xml = _rec("Watch", "01:00", "01:00", 150) + _rec("Watch", "02:30", "02:30", 151) \
        + _rec("Watch", "05:00", "05:00", 152) + _wk(events)
    (out,) = _items(xml)
    assert out.series["heart_rate"].columns["t"] == [60, 150, 300]
    assert out.series["heart_rate"].columns["at"] == [60, 120, 240]


def test_missing_gpx_flags_route_missing():
    ref = '<WorkoutRoute><FileReference path="/workout-routes/nope.gpx"/></WorkoutRoute>'
    (w,) = _items(_wk(ref), route=open_route)
    assert "route" not in w.series and w.quality_flags == {"route_missing": 1}
    (w,) = _items(_wk(ref), route=None)
    assert "route" not in w.series and w.quality_flags == {"route_missing": 1}
    (w,) = _items(_wk())  # no FileReference at all: nothing to flag
    assert w.quality_flags == {}


def test_unreadable_gpx_flags_route_missing():
    ref = '<WorkoutRoute><FileReference path="/r.gpx"/></WorkoutRoute>'
    (w,) = _items(_wk(ref), route=lambda p: io.BytesIO(b"<gpx><trk"))
    assert "route" not in w.series and w.quality_flags == {"route_missing": 1}


def _gpx(*pts):
    body = "".join(f'<trkpt lat="{la}" lon="{lo}">{x}</trkpt>' for la, lo, x in pts)
    return f'<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>{body}</trkseg></trk></gpx>'.encode()


def _pt(time, ele="<ele>1.5</ele>", speed="3.0"):
    return f"{ele}<time>{time}</time><extensions>{'' if speed is None else f'<speed>{speed}</speed>'}</extensions>"


def test_route_drops_and_columns():
    ref = '<WorkoutRoute><FileReference path="/r.gpx"/></WorkoutRoute>'
    gpx = _gpx(
        (52.0, 4.0, _pt("2026-03-04T02:00:10Z")),
        (52.0, 4.0, _pt("2026-03-04T02:00:11Z", ele="", speed="-1")),   # no alt; negative speed -> None
        (91.0, 4.0, _pt("2026-03-04T02:00:12Z")),                        # latitude out of range
        (52.0, 4.0, _pt("2026-03-04T02:00:13Z", speed="13")),            # faster than 12 m/s
        (52.0, 4.0, _pt("2026-03-04T01:00:00Z")),                        # before the workout
        (52.0, 4.0, _pt("2026-03-04T03:00:00Z")),                        # after the workout
        (52.0, 4.0, _pt("2026-03-04T02:00:14Z", speed=None)),            # no speed
    )
    (w,) = _items(_wk(ref), route=lambda p: io.BytesIO(gpx))
    c = w.series["route"].columns
    assert c["t"] == [10, 11, 14] and c["alt"] == [1.5, None, 1.5] and c["speed"] == [3.0, None, None]
    assert w.quality_flags == {"route_points_dropped": 4}


# --- inline helpers: a run starting 2026-03-03 21:00 -0500 (= 02:00 UTC on the 4th), 10 minutes ---------------

def _rec(src, a, b, bpm, day="2026-03-03"):
    # the clock times are minutes:seconds after 21:00, given as "00:10" style for readability (hh is ignored)
    return (f'<Record type="HKQuantityTypeIdentifierHeartRate" sourceName="{src}" unit="count/min" '
            f'startDate="{day} 21:{a} -0500" endDate="{day} 21:{b} -0500" value="{bpm}"/>')


def _wk(inner="", src="Watch"):
    return ('<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="10" durationUnit="min" '
            f'sourceName="{src}" startDate="2026-03-03 21:00:00 -0500" endDate="2026-03-03 21:10:00 -0500">{inner}</Workout>')


def _items(xml, tz=HOME, route=None):
    return list(parse(io.BytesIO(f"<HealthData>{xml}</HealthData>".encode()), tz, route))


def test_offset_workout_places_records_at_the_right_t():
    off = "+0100"
    rec = ('<Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch" unit="count/min" '
           f'startDate="2026-03-03 21:00:30 {off}" endDate="2026-03-03 21:00:50 {off}" value="140"/>')
    wk = ('<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="10" durationUnit="min" sourceName="Watch" '
          f'startDate="2026-03-03 21:00:00 {off}" endDate="2026-03-03 21:10:00 {off}"></Workout>')
    (w,) = _items(rec + wk)
    assert w.series["heart_rate"].columns["t"] == [40.0]  # midpoint 21:00:40


def test_non_bpm_unit_is_excluded():
    rec = _rec("Watch", "00:10", "00:10", 150).replace("count/min", "count/s")
    (w,) = _items(rec + _rec("Watch", "00:20", "00:20", 151) + _wk())
    assert w.series["heart_rate"].columns["avg"] == [151]


def test_invalid_own_source_does_not_hide_valid_other_source():
    xml = _rec("Watch", "00:10", "00:10", 320) + _rec("Phone", "00:20", "00:20", 90) + _wk()
    (w,) = _items(xml)
    assert w.series["heart_rate"].columns["avg"] == [90] and w.quality_flags == {"hr_samples_dropped": 1}


def test_fractional_values_dedup_and_keep_precision():
    r = _rec("Watch", "00:10", "00:10", 150.1)
    (w,) = _items(r + _wk(r))
    assert w.series["heart_rate"].columns["avg"] == [150.1]


def test_events_are_paired_by_date_not_file_order():
    events = ('<WorkoutEvent type="HKWorkoutEventTypeResume" date="2026-03-03 21:03:00 -0500"/>'
              '<WorkoutEvent type="HKWorkoutEventTypePause" date="2026-03-03 21:02:00 -0500"/>')
    xml = _rec("Watch", "05:00", "05:00", 152) + _wk(events)
    (w,) = _items(xml)
    assert w.series["heart_rate"].columns["at"] == [240]


@pytest.mark.parametrize("exc", [KeyError("x"), ValueError("x"), __import__("zipfile").BadZipFile("x"), OSError("x")])
def test_route_open_errors_mean_route_missing(exc):
    def boom(path):
        raise exc

    ref = '<WorkoutRoute><FileReference path="/r.gpx"/></WorkoutRoute>'
    (w,) = _items(_wk(ref), route=boom)
    assert "route" not in w.series and w.quality_flags == {"route_missing": 1}
