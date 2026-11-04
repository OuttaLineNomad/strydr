"""The step_count series from both adapters (story 20): intervals of {t, dt, steps} per workout."""
import io
import json
from datetime import datetime, timedelta

import pytest

from conftest import FIXTURES
from strydr.sources import apple, hae
from strydr.sources.hae import adapter as hae_adapter
from strydr.sources.canonical import Workout
from test_apple_adapter import EXPORT, HOME, open_route

START = datetime(2026, 3, 3, 12, 0, 0)  # UTC
TZ = "-0500"


def _d(sec: float) -> str:
    return (START + timedelta(seconds=sec) - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S ") + TZ


def _hae_workout(steps, minutes=10) -> Workout:
    w = {"id": "W1", "name": "Outdoor Run", "isIndoor": False, "start": _d(0), "end": _d(minutes * 60),
         "duration": minutes * 60.0, "activities": [{"activityType": "running"}]}
    if steps is not None:
        w["stepCount"] = steps
    return hae_adapter.convert_workout(w)


def _el(sec, qty="x", **kw):
    e = {"date": _d(sec), "qty": 3 if qty == "x" else qty, "source": "S", "units": "count"}
    e.update(kw)
    return e


def test_versions():
    assert hae.ADAPTER_VERSION == 4 and apple.ADAPTER_VERSION == 5


def test_hae_seconds_keep_every_step():
    items = [_el(i, 2 + i % 3) for i in range(300)]
    ser = _hae_workout(items).series["step_count"]
    assert ser.columns["t"] == list(range(300)) and set(ser.columns["dt"]) == {1}
    assert sum(ser.columns["steps"]) == sum(e["qty"] for e in items)
    assert ser.columns.keys() == {"t", "dt", "steps"}


def test_hae_per_minute_dt_60():
    ser = _hae_workout([_el(30 + 60 * m, 80) for m in range(5)]).series["step_count"]
    assert ser.columns["dt"] == [60] * 5


def test_hae_gap_is_capped_and_last_gets_median():
    ser = _hae_workout([_el(0), _el(5), _el(10), _el(310), _el(311)]).series["step_count"]
    assert ser.columns["dt"] == [5, 5, 60, 1, 5]  # the 300 s hole caps at 60; median gap is 5
    ser = _hae_workout([_el(0), _el(200), _el(400)]).series["step_count"]
    assert ser.columns["dt"] == [60, 60, 60]


def test_hae_bad_elements_are_dropped_and_counted():
    items = [_el(0), _el(1, qty=None), _el(2, qty=-4), {"date": "garbage", "qty": 3}, {"qty": 3}, _el(-5), _el(9999),
             _el(3, 7), _el(4, 0)]
    w = _hae_workout(items)
    assert w.series["step_count"].columns["steps"] == [3, 7, 0]
    assert w.quality_flags["step_samples_dropped"] == 6
    assert "source" not in json.dumps(w.series["step_count"].columns)


def test_hae_infinite_qty_is_dropped():
    w = _hae_workout([_el(0, 3), _el(1, float("inf"))])
    assert w.series["step_count"].columns["steps"] == [3] and w.quality_flags["step_samples_dropped"] == 1


def test_hae_equal_timestamps_are_summed_so_dt_is_never_zero():
    ser = _hae_workout([_el(0, 2), _el(0, 3), _el(5, 4), _el(5, 1)]).series["step_count"]
    assert ser.columns["t"] == [0, 5] and ser.columns["steps"] == [5, 5] and ser.columns["dt"] == [5, 5]


def test_hae_unsorted_input_is_sorted_and_no_key_means_no_series():
    ser = _hae_workout([_el(5, 1), _el(1, 2), _el(3, 3)]).series["step_count"]
    assert ser.columns["t"] == [1, 3, 5] and ser.columns["steps"] == [2, 3, 1]
    assert "step_count" not in _hae_workout(None).series
    assert "step_count" not in _hae_workout([]).series
    assert "step_count" not in _hae_workout([_el(1, qty=-1)]).series


# --- Apple -------------------------------------------------------------------

def _rec(start, end, value, src="Synthetic Watch", unit="count"):
    return (f'<Record type="HKQuantityTypeIdentifierStepCount" sourceName="{src}" unit="{unit}" '
            f'startDate="{_d(start)}" endDate="{_d(end)}" value="{value}"/>')


def _apple(records, source="Synthetic Watch", minutes=10) -> Workout:
    xml = (f"<HealthData>{''.join(records)}"
           f'<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="{minutes}" durationUnit="min" '
           f'startDate="{_d(0)}" endDate="{_d(minutes * 60)}" sourceName="{source}"/></HealthData>')
    (w,) = [x for x in apple.parse(io.BytesIO(xml.encode()), HOME) if isinstance(x, Workout)]
    return w


def test_apple_interval_inside_the_run():
    ser = _apple([_rec(100, 108, 20), _rec(108, 116, 22)]).series["step_count"]
    assert ser.columns == {"t": [100, 108], "dt": [8, 8], "steps": [20, 22]}


def test_apple_overlap_is_clipped_and_prorated():
    ser = _apple([_rec(-4, 4, 16), _rec(596, 608, 24), _rec(-30, -10, 99), _rec(700, 710, 99)]).series["step_count"]
    assert ser.columns["t"] == [0, 596] and ser.columns["dt"] == [4, 4]
    assert ser.columns["steps"] == pytest.approx([8, 8])


def test_apple_prefers_the_workouts_own_source():
    recs = [_rec(10, 18, 20), _rec(10, 70, 90, src="Synthetic Phone")]
    assert _apple(recs).series["step_count"].columns["steps"] == [20]
    # no record from the workout's own source: whatever is there is used
    assert _apple([_rec(10, 70, 90, src="Synthetic Phone")]).series["step_count"].columns["steps"] == [90]


def test_apple_without_own_source_uses_the_single_busiest_other_source():
    recs = [_rec(10, 70, 90, src="Phone"), _rec(10, 70, 60, src="Tablet"), _rec(70, 130, 80, src="Phone")]
    ser = _apple(recs, source="Watch").series["step_count"]
    assert ser.columns["steps"] == [90, 80]  # the phone's, not phone + tablet


def test_apple_nested_step_records_count_once_and_are_claimed():
    inner = _rec(10, 18, 20)
    nested_only = _rec(30, 38, 7)
    xml = (f"<HealthData>{_rec(10, 18, 20)}"
           f'<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="10" durationUnit="min" '
           f'startDate="{_d(0)}" endDate="{_d(600)}" sourceName="Synthetic Watch">{inner}{nested_only}</Workout></HealthData>')
    (w,) = [x for x in apple.parse(io.BytesIO(xml.encode()), HOME) if isinstance(x, Workout)]
    assert w.series["step_count"].columns == {"t": [10, 30], "dt": [8, 8], "steps": [20, 7]}


def test_apple_ignores_bad_records_and_missing_steps():
    assert "step_count" not in _apple([]).series
    recs = [_rec(10, 10, 5), _rec(10, 18, -3), _rec(10, 18, "abc"), _rec(10, 18, "inf"), _rec(10, 18, 5, unit="km")]
    assert "step_count" not in _apple(recs).series


def test_apple_unsorted_records_come_out_sorted():
    ser = _apple([_rec(200, 208, 3), _rec(100, 108, 1), _rec(150, 158, 2)]).series["step_count"]
    assert ser.columns["t"] == [100, 150, 200] and ser.columns["steps"] == [1, 2, 3]


def test_apple_fixture_run_has_steps_summing_to_the_clipped_records():
    with open(EXPORT, "rb") as f:
        ws = {w.start_utc: w for w in apple.parse(f, HOME, open_route) if isinstance(w, Workout)}
    run = ws[datetime(2026, 3, 3, 12, 30, 20)]
    cols = run.series["step_count"].columns
    assert cols["t"] == sorted(cols["t"]) and cols["t"][0] == 0 and cols["dt"][0] == 4  # the first record straddles
    assert set(cols["dt"][1:-1]) == {8}
    assert len(cols["t"]) == len(cols["dt"]) == len(cols["steps"])
    assert 25 * 60 * 83 / 60 * 0.9 < sum(cols["steps"]) < 26 * 60 * 83 / 60 * 1.1  # 3.2 m/s x 26 steps per m


def test_hae_fixtures_carry_steps():
    for name in ("hae-export.json", "hae-seconds.json"):
        raw = {w["id"]: w for w in json.loads((FIXTURES / name).read_text())["data"]["workouts"] if "id" in w}
        with open(FIXTURES / name, "rb") as f:
            ws = [w for w in hae.parse(f) if isinstance(w, Workout)]
        assert ws
        for w in ws:
            if w.workout_id in raw:
                got = sum(w.series["step_count"].columns["steps"])
                assert got == pytest.approx(sum(e["qty"] for e in raw[w.workout_id]["stepCount"]))
    (sec,) = [w for w in ws if w.workout_id in raw]
    assert sec.series["step_count"].n == 25 * 60 and set(sec.series["step_count"].columns["dt"]) == {1}


def test_ingested_fixture_runs_store_step_count_and_merge_counts_ignore_it(engine, send):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from conftest import load_fixture
    from strydr.store import models
    from strydr.store.series import load_series

    send(load_fixture("hae-seconds.json"))
    with Session(engine) as s:
        (wid, n_series), = s.execute(select(models.Workout.workout_id, models.Workout.series_count)).all()
        stored = load_series(s, wid)
    raw = load_fixture("hae-seconds.json")["data"]["workouts"][0]["stepCount"]
    assert sum(stored["step_count"]["steps"]) == pytest.approx(sum(e["qty"] for e in raw))
    assert n_series == len([k for k in stored if k not in ("splits", "step_count")])
