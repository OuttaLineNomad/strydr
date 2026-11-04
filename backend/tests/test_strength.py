"""Strength workouts: imported with HR and effort, never an input to running load, fitness or insights."""
import copy
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from strydr.relabel import relabel
from strydr.sources.hae import adapter as hae
from strydr.sources.apple import parse as apple_parse
from strydr.sources.canonical import Workout
from strydr.store import models

from conftest import FIXTURES, load_fixture
from helpers import add_run, login, recompute_now, set_hrmax
from test_e2e import AS_OF, drain, history_payload

API = "/api/v1"
EXPORT = FIXTURES / "apple_health_export" / "export.xml"


def _hae(name="hae-export.json"):
    return {w.workout_id: w for w in (hae.convert_workout(x) for x in load_fixture(name)["data"]["workouts"]) if w}


def _apple():
    with open(EXPORT, "rb") as f:
        return [w for w in apple_parse(f, ZoneInfo("America/New_York"), None) if isinstance(w, Workout)]


# --- adapters -----------------------------------------------------------------

def test_hae_functional_strength_is_indoor_strength_with_hr_and_effort():
    w = next(x for x in _hae().values() if x.type == "strength" and x.effort_score == 5)
    assert w.is_indoor and w.distance_m is None and "route" not in w.series
    assert w.series["heart_rate"].columns["t"] and w.series["step_count"].columns["t"]
    assert w.avg_hr == 128 and w.max_hr == 152 and w.effort_estimated is False


def test_hae_traditional_strength_by_code_and_by_name():
    raw = next(x for x in load_fixture("hae-export.json")["data"]["workouts"] if x["activities"][0]["activityTypeCode"] == 50)
    assert hae.convert_workout(raw).type == "strength"
    for activity in ({"activityType": "somethingNew", "activityTypeCode": 50}, {"activityType": "other", "activityTypeCode": 999}):
        w = copy.deepcopy(raw)
        w["activities"][0].update(activity)
        w["name"] = "Core Strength"
        assert hae.convert_workout(w).type == "strength"
    w = copy.deepcopy(raw)
    w["activities"][0].update(activityType="x", activityTypeCode=20)
    w["name"] = "Unnamed"
    assert hae.convert_workout(w).type == "strength"
    w["isIndoor"] = False
    assert hae.convert_workout(w).is_indoor  # strength is always indoor: no weather


def test_apple_strength_reads_effort_from_the_linked_record():
    ws = {w.type + w.start_utc.isoformat(): w for w in _apple() if w.type == "strength"}
    assert len(ws) == 2
    functional = next(w for w in ws.values() if w.start_utc.hour == 23)  # 18:00 local
    assert functional.effort_score == 5 and functional.is_indoor and functional.distance_m is None
    assert functional.series["heart_rate"].columns["t"] and functional.avg_hr and functional.max_hr
    traditional = next(w for w in ws.values() if w.start_utc.hour == 0)  # 19:00 local, no effort record
    assert traditional.effort_score is None and traditional.series["heart_rate"].columns["t"]


def test_apple_runs_do_not_take_an_effort_score():
    assert all(w.effort_score is None for w in _apple() if w.type != "strength")


# --- running analytics are untouched -------------------------------------------

def _current(s, model, *cols):
    gid = s.execute(select(models.CurrentGeneration.generation_id)).scalar_one()
    return [tuple(getattr(r, c) for c in cols) for r in s.execute(
        select(model).where(model.generation_id == gid).order_by(*[getattr(model, c) for c in cols[:1]])).scalars()]


def _running_outputs(engine):
    with Session(engine) as s:
        return {
            "load": _current(s, models.DailyLoad, "local_date", "load", "fitness", "fatigue", "form", "form_pct", "acwr", "training_state"),
            "days": _current(s, models.DayClass, "local_date", "has_run", "is_hard", "load", "hard_seconds", "reasons"),
            "workout_load": sorted(_current(s, models.WorkoutLoad, "workout_id", "trimp", "source")),
            "records": sorted(map(str, _current(s, models.Record, "key", "value", "workout_id", "local_date"))),
            "insights": sorted(map(str, _current(s, models.InsightFact, "insight_key", "rule_id", "text_template", "number"))),
        }


def _seed(engine, with_strength):
    add_run(engine, "r1", datetime(2026, 10, 20, 7), 40, 3.0, hr=150.0)
    add_run(engine, "r2", datetime(2026, 10, 22, 7), 30, 3.1, hr=160.0)
    add_run(engine, "w1", datetime(2026, 10, 23, 7), 20, 1.5, hr=110.0, type_="walk")
    if with_strength:
        add_run(engine, "s1", datetime(2026, 10, 20, 18), 25, hr=[150.0] * 25, route=False, type_="strength")  # a run day
        add_run(engine, "s2", datetime(2026, 10, 22, 18), 25, hr=[170.0] * 25, route=False, type_="strength")


def test_strength_on_run_days_leaves_every_running_number_alone(engine, tmp_path):
    set_hrmax(engine, 190)
    _seed(engine, True)
    recompute_now(engine, "2026-10-26")
    with_s = _running_outputs(engine)
    with Session(engine) as s:  # the same database without the strength workouts
        s.execute(delete(models.SampleSeries).where(models.SampleSeries.workout_id.in_(("s1", "s2"))))
        s.execute(delete(models.Workout).where(models.Workout.workout_id.in_(("s1", "s2"))))
        s.commit()
    recompute_now(engine, "2026-10-26")
    assert _running_outputs(engine) == with_s
    assert with_s["load"] and with_s["days"]


def test_strength_day_is_active_never_hard_and_adds_no_load(engine):
    set_hrmax(engine, 190)
    add_run(engine, "r1", datetime(2026, 10, 20, 7), 40, 3.0, hr=150.0)
    add_run(engine, "s1", datetime(2026, 10, 22, 18), 30, hr=[185.0] * 30, route=False, type_="strength")  # hard HR
    recompute_now(engine, "2026-10-26")
    with Session(engine) as s:
        gid = s.execute(select(models.CurrentGeneration.generation_id)).scalar_one()
        day = s.execute(select(models.DayClass).where(models.DayClass.generation_id == gid,
                                                      models.DayClass.local_date == "2026-10-22")).scalar_one()
        assert (day.kind, day.is_hard, day.has_run, day.load, day.hard_seconds) == ("active", False, False, 0.0, 0.0)
        assert s.execute(select(models.WorkoutLoad).where(models.WorkoutLoad.workout_id == "s1")).first() is None
        summary = s.execute(select(models.WorkoutSummary).where(models.WorkoutSummary.workout_id == "s1")).scalar_one()
        assert sum(summary.zone_seconds) > 0  # zones for the detail page


def test_the_live_shaped_fixture_gives_the_same_running_numbers_without_strength(engine, ingest, worker):
    for body in (load_fixture("hae-export.json"), history_payload()):
        assert ingest.post("/ingest/hae", content=json.dumps(body).encode()).status_code == 202
    drain(worker, engine)
    with Session(engine) as s:
        ids = [w for (w,) in s.execute(select(models.Workout.workout_id).where(models.Workout.type == "strength"))]
    assert len(ids) == 2
    with_s = _running_outputs(engine)
    with Session(engine) as s:
        s.execute(delete(models.SampleSeries).where(models.SampleSeries.workout_id.in_(ids)))
        s.execute(delete(models.Workout).where(models.Workout.workout_id.in_(ids)))
        s.commit()
    recompute_now(engine, AS_OF)
    assert _running_outputs(engine) == with_s
    assert with_s["insights"] and with_s["workout_load"]


# --- API ------------------------------------------------------------------------

@pytest.fixture
def c(engine, app_client):
    set_hrmax(engine, 190)
    add_run(engine, "r1", datetime(2026, 10, 20, 7), 10, 3.0, type_="run")
    add_run(engine, "w1", datetime(2026, 10, 21, 7), 10, 1.5, type_="walk")
    add_run(engine, "s1", datetime(2026, 10, 22, 18), 20, hr=[130.0] * 20, route=False, type_="strength")
    recompute_now(engine, "2026-10-26")
    login(app_client)
    return app_client


def _ids(c, **q):
    return sorted(w["workout_id"] for w in c.get(f"{API}/workouts", params=q).json())


def test_lists_keep_strength_out_of_run_and_serve_it_on_request(c):
    assert _ids(c, type="run") == ["r1"]
    assert _ids(c, type="strength") == ["s1"]
    assert _ids(c, type="walk,hike") == ["w1"]
    assert _ids(c) == ["r1", "s1", "w1"]


def test_strength_detail_has_hr_and_no_pace_or_map(c):
    d = c.get(f"{API}/workouts/s1").json()
    assert d["workout"]["type"] == "strength" and d["workout"]["is_indoor"]
    assert d["hr_series"] and d["zone_seconds"] and sum(d["zone_seconds"]) > 0
    assert d["splits_km"] is None and d["pace_series"] is None and d["display_geometry"] is None
    assert d["training_load"] is None and d["shoe"] is None


def test_calendar_lists_the_workout_and_marks_the_day_active(c):
    cal = c.get(f"{API}/calendar", params={"month": "2026-10"}).json()
    day = next(x for x in cal["days"] if x["local_date"] == "2026-10-22")
    assert [w["type"] for w in day["workouts"]] == ["strength"]
    assert day["kind"] == "active" and day["is_hard"] is False and day["load"] == 0.0
    assert cal["longest_run_m"] is not None and cal["totals"]["run_count"] == 1


def test_a_run_cannot_be_relabelled_to_strength(c, engine):
    assert c.put(f"{API}/workouts/r1/type", json={"type": "strength"}).status_code == 422
    with pytest.raises(ValueError):
        relabel(engine, "run", "strength", "2026-12-31")


def test_strength_gets_no_default_shoe(c):
    shoe = c.post(f"{API}/shoes", json={"name": "Daily"}).json()["shoes"][0]["id"]
    assert c.put(f"{API}/shoes/default", json={"shoe_id": shoe, "from_date": "2026-10-01"}).status_code == 200
    assert c.get(f"{API}/workouts/r1").json()["shoe"]["id"] == shoe
    assert c.get(f"{API}/workouts/s1").json()["shoe"] is None


def test_strength_never_reaches_week_or_recap_runs(c):
    wk = c.get(f"{API}/weeks/2026-W43").json()
    assert [r["workout_id"] for r in wk["runs"]] == ["r1"]


# --- history start and Apple effort matching --------------------------------------

def test_a_strength_workout_before_every_run_does_not_move_history_start(engine, monkeypatch):
    from strydr.pipeline.insights import snapshot
    starts = []
    orig = snapshot.build
    monkeypatch.setattr(snapshot, "build", lambda ctx, profile: starts.append((s := orig(ctx, profile)).history_start) or s)
    set_hrmax(engine, 190)
    _seed(engine, False)
    recompute_now(engine, "2026-10-26")
    baseline = (starts[-1], _running_outputs(engine))
    add_run(engine, "early", datetime(2026, 9, 1, 18), 25, hr=[150.0] * 25, route=False, type_="strength")
    recompute_now(engine, "2026-10-26")
    assert starts[-1] == baseline[0] == datetime(2026, 10, 20).date()
    assert _running_outputs(engine) == baseline[1]


def _w(start="2026-03-03 18:00:00", end="2026-03-03 18:20:00"):
    return Workout("x", "strength", True, datetime.fromisoformat(start), datetime.fromisoformat(end), 0,
                   start[:10], duration_s=1200.0)


def _ts(text):
    return datetime.fromisoformat(text).replace(tzinfo=__import__("datetime").timezone.utc).timestamp()


def test_effort_record_needs_half_the_window_and_a_score_from_1_to_10():
    from strydr.sources.apple.adapter import _effort_for
    w = _w()
    a, b = _ts("2026-03-03 18:00:00"), _ts("2026-03-03 18:20:00")
    assert _effort_for(w, [(a + 900, b + 3000, 5.0)]) is None  # 300 s of 1200 s: under half
    assert _effort_for(w, [(a, b, 5.0)]) == 5.0
    assert _effort_for(w, []) is None


def test_effort_scores_out_of_range_are_ignored():
    from xml.etree import ElementTree as ET
    from strydr.sources.apple.adapter import _effort_record
    out = []
    for v in ("0", "11", "nan", "x", "7"):
        _effort_record(ET.fromstring(f'<Record value="{v}" startDate="2026-03-03 18:00:00 +0000" '
                                     'endDate="2026-03-03 18:20:00 +0000"/>'), out)
    assert [x[2] for x in out] == [7.0]


def test_the_larger_overlap_wins_between_two_effort_records():
    from strydr.sources.apple.adapter import _effort_for
    w = _w()
    a, b = _ts("2026-03-03 18:00:00"), _ts("2026-03-03 18:20:00")
    assert _effort_for(w, [(a, a + 700, 3.0), (a, b, 8.0)]) == 8.0
    assert _effort_for(w, [(a, b, 8.0), (a, a + 700, 3.0)]) == 8.0
