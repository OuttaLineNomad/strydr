"""The home-workout summary: the watch match, HR slices, effort and the EMOM fell-short answers."""
import json
import zlib
from datetime import datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr import sessions_summary as ss
from strydr.store import migrate, models

from conftest import KEY
from helpers import login, recompute_now, set_hrmax
from test_plans import mv, plan
from test_sessions import ev, session

API = "/api/v1"
D0 = datetime(2026, 11, 3, 18, 0, 0)


@pytest.fixture
def c(app_client):
    login(app_client)
    return app_client


def add_strength(engine, wid="s1", start=D0 - timedelta(minutes=1), minutes=12, hr_fn=None, effort=None, type_="strength", series=True, estimated=False):
    """A strength workout with HR once a second. `hr_fn(session_seconds)` gives the bpm; the session starts at D0."""
    off = (start - D0).total_seconds()
    secs = minutes * 60
    hr_fn = hr_fn or (lambda ts: 100 + (ts // 60) * 10)
    with Session(engine) as s:
        s.add(models.Workout(
            workout_id=wid, type=type_, is_indoor=True, start_utc=start, end_utc=start + timedelta(seconds=secs), utc_offset_s=0,
            local_date=start.date().isoformat(), duration_s=float(secs), quality_flags={}, series_count=int(series),
            sample_count=secs, adapter_version=1, received_at=start, effort_score=effort,
            effort_estimated=estimated if effort is not None else None))
        s.flush()
        if series:
            cols = {"t": list(range(secs)), "avg": [float(hr_fn(t + off)) for t in range(secs)]}
            s.add(models.SampleSeries(workout_id=wid, series="heart_rate", n_samples=secs, adapter_version=1,
                                      data=zlib.compress(json.dumps(cols).encode())))
        s.commit()


def two_move_plan():
    return plan(moves=[mv("Swing"), mv("Goblet squat")])


# Round 1: Swing 0-60, Squat 60-120, rest 120-150. Round 2: Swing 150-210, then the runner ends in Squat at 240.
EVENTS = [ev(60_000, "next", 0, 0), ev(120_000, "next", 1, 0), ev(150_000, "next", 1, 0),
          ev(210_000, "next", 0, 1), ev(240_000, "end", 1, 1)]


def summary(c, **kw):
    sid = c.post(f"{API}/sessions", json=session(**{"plan": two_move_plan(), "events": EVENTS, "rounds_done": 1,
                                                    "partial_moves": 1, "end_utc": "2026-11-03T18:04:00Z", **kw})).json()["id"]
    return sid, c.get(f"{API}/sessions/{sid}/summary").json()


def test_matched_gives_hr_per_move_per_round_and_the_watch_effort(c, engine):
    add_strength(engine, effort=5)
    _, sm = summary(c)
    assert sm["matched_workout_id"] == "s1"
    assert sm["effort"] == 5 and sm["effort_source"] == "watch"
    by = {m["name"]: m for m in sm["moves"]}
    assert by["Swing"]["avg_hr"] == pytest.approx(112.5, abs=0.1) and by["Swing"]["instances"] == 2
    assert by["Goblet squat"]["avg_hr"] == pytest.approx(110, abs=0.1) and by["Goblet squat"]["instances"] == 1  # the unfinished one is left out
    assert [(r["round"], r["time_s"], r["moves"]) for r in sm["rounds"]] == [(1, 120, 2), (2, 60, 1)]
    assert [r["avg_hr"] for r in sm["rounds"]] == [pytest.approx(105, abs=0.1), pytest.approx(125, abs=0.1)]
    assert sm["avg_hr"] == pytest.approx(sum(100 + (t // 60) * 10 for t in range(240)) / 240, abs=0.1)


def test_zones_use_the_profile_bounds(c, engine):
    add_strength(engine)
    set_hrmax(engine, 200)
    recompute_now(engine, "2026-11-04")
    _, sm = summary(c)
    z = sm["zone_seconds"]
    assert len(z) == 5 and sum(z) == pytest.approx(240, abs=1) and len(sm["zone_bounds_bpm"]) == 4
    assert z[0] > 0  # 100 bpm is under 60% of 200


def test_no_hrmax_means_no_zones(c, engine):
    add_strength(engine)
    _, sm = summary(c)
    assert sm["matched_workout_id"] == "s1" and sm["zone_seconds"] is None and sm["avg_hr"] is not None


def test_late_sync_attaches_on_the_next_read(c, engine):
    sid, sm = summary(c)
    assert sm["matched_workout_id"] is None and sm["moves"] == [] and sm["avg_hr"] is None and sm["effort"] is None
    assert len(sm["rounds"]) == 2  # the taps alone give the round table
    add_strength(engine, effort=7)
    sm = c.get(f"{API}/sessions/{sid}/summary").json()
    assert sm["matched_workout_id"] == "s1" and sm["moves"] and sm["effort"] == 7


def test_the_larger_overlap_wins(c, engine):
    add_strength(engine, "small", start=D0 + timedelta(minutes=2), minutes=10)  # 2 of the 4 minutes
    add_strength(engine, "big", start=D0 - timedelta(minutes=1), minutes=12)  # all 4
    _, sm = summary(c)
    assert sm["matched_workout_id"] == "big"


def test_overlap_under_half_of_the_shorter_is_no_match(c, engine):
    add_strength(engine, "late", start=D0 + timedelta(minutes=3), minutes=10)  # 1 of the session's 4 minutes
    _, sm = summary(c)
    assert sm["matched_workout_id"] is None and sm["moves"] == [] and sm["zone_seconds"] is None


def test_only_strength_workouts_match(c, engine):
    add_strength(engine, "run", type_="run")
    _, sm = summary(c)
    assert sm["matched_workout_id"] is None


def test_matched_workout_without_hr_still_lends_effort(c, engine):
    add_strength(engine, effort=6, series=False)
    _, sm = summary(c)
    assert sm["matched_workout_id"] == "s1" and sm["moves"] == [] and sm["avg_hr"] is None and sm["effort"] == 6


def test_manual_effort_saved_changeable_and_beaten_by_the_watch(c, engine):
    sid, sm = summary(c)
    assert sm["effort"] is None
    assert c.put(f"{API}/sessions/{sid}/effort", json={"effort": 7}).json() == {"effort": 7}
    sm = c.get(f"{API}/sessions/{sid}/summary").json()
    assert sm["effort"] == 7 and sm["effort_source"] == "manual"
    c.put(f"{API}/sessions/{sid}/effort", json={"effort": 4})
    assert c.get(f"{API}/sessions/{sid}/summary").json()["effort"] == 4
    add_strength(engine, effort=5)
    sm = c.get(f"{API}/sessions/{sid}/summary").json()
    assert sm["effort"] == 5 and sm["effort_source"] == "watch"


@pytest.mark.parametrize("effort", [0, 11, -1, "x"])
def test_bad_effort_is_422(c, effort):
    sid, _ = summary(c)
    assert c.put(f"{API}/sessions/{sid}/effort", json={"effort": effort}).status_code == 422


def test_missing_session_is_404(c):
    assert c.get(f"{API}/sessions/99/summary").status_code == 404
    assert c.put(f"{API}/sessions/99/effort", json={"effort": 3}).status_code == 404
    assert c.put(f"{API}/sessions/99/short", json={"5": 3}).status_code == 404


def test_pause_samples_are_excluded(c, engine):
    # Swing runs 0-120 with a pause 30-90 where HR spikes to 200; those readings must not count.
    add_strength(engine, hr_fn=lambda ts: 200 if 30 <= ts < 90 else 100)
    events = [ev(30_000, "pause", 0, 0), ev(90_000, "resume", 0, 0), ev(120_000, "next", 0, 0), ev(180_000, "end", 1, 0)]
    _, sm = summary(c, events=events, plan=two_move_plan(), rounds_done=0, partial_moves=1, end_utc="2026-11-03T18:03:00Z")
    assert sm["moves"] == [{"name": "Swing", "avg_hr": 100.0, "instances": 1}]
    assert sm["rounds"][0]["time_s"] == 60 and sm["avg_hr"] == pytest.approx(100, abs=0.1)


def test_partial_round_row_covers_the_finished_moves(c, engine):
    add_strength(engine)
    p = plan(moves=[mv("A"), mv("B"), mv("C")])
    _, sm = summary(c, plan=p, events=[ev(60_000, "next", 0, 0), ev(120_000, "next", 1, 0), ev(180_000, "next", 2, 0), ev(210_000, "next", 2, 0),
                                       ev(270_000, "next", 0, 1), ev(330_000, "next", 1, 1), ev(360_000, "end", 2, 1)],
                    rounds_done=1, partial_moves=2, end_utc="2026-11-03T18:06:00Z")
    assert [(r["round"], r["moves"]) for r in sm["rounds"]] == [(1, 3), (2, 2)]


def test_emom_short_minutes_ask_and_save(c):
    p = plan("E", "emom", moves=[mv("Swings", reps=10), mv("Squats", reps=12)])
    events = [ev(60_000 * k, "auto", (k - 1) % 2, (k - 1) // 2) for k in range(1, 13)]
    sid = c.post(f"{API}/sessions", json=session(plan=p, events=events, end_utc="2026-11-03T18:12:00Z", fell_short=[5, 9],
                                                 rounds_done=6, partial_moves=0)).json()["id"]
    sm = c.get(f"{API}/sessions/{sid}/summary").json()
    assert sm["fell_short"] == [{"minute": 5, "move": "Swings", "target_reps": 10, "short_reps": None},
                                {"minute": 9, "move": "Swings", "target_reps": 10, "short_reps": None}]
    assert len(sm["rounds"]) == 6 and sm["rounds"][0]["time_s"] == 120
    assert c.put(f"{API}/sessions/{sid}/short", json={"5": 8}).json() == {"5": 8}
    assert c.put(f"{API}/sessions/{sid}/short", json={"9": 6}).json() == {"5": 8, "9": 6}
    sm = c.get(f"{API}/sessions/{sid}/summary").json()
    assert [r["short_reps"] for r in sm["fell_short"]] == [8, 6]
    c.put(f"{API}/sessions/{sid}/short", json={"5": None})  # taken back
    assert c.get(f"{API}/sessions/{sid}/summary").json()["fell_short"][0]["short_reps"] is None


def test_short_rejects_unflagged_minutes_and_wild_reps(c):
    p = plan("E", "emom", moves=[mv("Swings")])
    sid = c.post(f"{API}/sessions", json=session(plan=p, fell_short=[5])).json()["id"]
    assert c.put(f"{API}/sessions/{sid}/short", json={"6": 3}).status_code == 422
    assert c.put(f"{API}/sessions/{sid}/short", json={"x": 3}).status_code == 422
    assert c.put(f"{API}/sessions/{sid}/short", json={"5": 501}).status_code == 422
    assert c.put(f"{API}/sessions/{sid}/short", json={"5": -1}).status_code == 422


def test_non_emom_has_no_short_rows(c):
    _, sm = summary(c)
    assert sm["fell_short"] == []


def test_summary_needs_login(app_client):
    assert app_client.get(f"{API}/sessions/1/summary").status_code == 401
    assert app_client.put(f"{API}/sessions/1/effort", json={"effort": 3}).status_code == 401
    assert app_client.put(f"{API}/sessions/1/short", json={"1": 3}).status_code == 401


def test_summary_writes_do_not_enqueue_a_recompute(c, engine):
    from conftest import count
    sid, _ = summary(c)
    before = count(engine, models.Job, models.Job.type == "recompute")
    c.put(f"{API}/sessions/{sid}/effort", json={"effort": 3})
    assert count(engine, models.Job, models.Job.type == "recompute") == before


def test_match_helper_edge_cases():
    class W:
        def __init__(self, a, b):
            self.start_utc, self.end_utc = D0 + timedelta(minutes=a), D0 + timedelta(minutes=b)
    end = D0 + timedelta(minutes=10)
    assert ss.match(D0, end, [W(20, 30)]) is None
    assert ss.match(D0, end, [W(0, 5)]).end_utc == D0 + timedelta(minutes=5)  # all of the shorter
    assert ss.match(D0, end, [W(9, 40)]) is None  # 1 of 10 minutes
    assert ss.match(D0, D0, [W(-1, 1)]) is None  # a zero-length session


def test_migration_0016_up_and_down(tmp_path):
    from strydr.store.engine import make_engine
    e = make_engine(tmp_path / "m.db", KEY)
    cfg = Config()
    cfg.set_main_option("script_location", str(migrate._DIR))
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.upgrade(cfg, "0015")
    assert "short_reps" not in {x["name"] for x in inspect(e).get_columns("workout_session")}
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.upgrade(cfg, "head")
    assert "short_reps" in {x["name"] for x in inspect(e).get_columns("workout_session")}
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.downgrade(cfg, "0015")
    assert "short_reps" not in {x["name"] for x in inspect(e).get_columns("workout_session")}
    e.dispose()


def test_zone_seconds_are_exact_and_a_reading_on_a_bound_is_the_lower_zone(c, engine):
    add_strength(engine, hr_fn=lambda ts: 0)  # placeholder, replaced below once the bounds are known
    set_hrmax(engine, 200)
    recompute_now(engine, "2026-11-04")
    with Session(engine) as s:
        b = s.execute(select(models.ProfileResult.zone_bounds_bpm)).scalar_one()
        s.query(models.SampleSeries).delete()
        s.query(models.Workout).delete()
        s.commit()
    pick = {0: b[0], 1: b[0] + 1, 2: b[1], 3: b[3] + 1}
    add_strength(engine, hr_fn=lambda ts: pick[int(ts // 60)] if 0 <= ts < 240 else 100)
    _, sm = summary(c)
    # on b[0] is zone 1; just over it zone 2; on b[1] zone 2; over the last bound zone 5
    assert sm["zone_seconds"] == [60.0, 120.0, 0.0, 0.0, 60.0]


def test_null_and_nan_hr_readings_are_skipped_not_a_500(c, engine):
    add_strength(engine)
    cols = {"t": [None, 0, 1, 2, 3, "x"], "avg": [100.0, float("nan"), None, 120.0, 130.0, 140.0]}
    with Session(engine) as s:
        row = s.query(models.SampleSeries).one()
        row.data = zlib.compress(json.dumps(cols).encode())
        s.commit()
    r = c.post(f"{API}/sessions", json=session(plan=two_move_plan(), events=EVENTS, end_utc="2026-11-03T18:04:00Z"))
    got = c.get(f"{API}/sessions/{r.json()['id']}/summary")
    assert got.status_code == 200


def test_events_past_the_end_do_not_stretch_a_segment():
    ev_list = [ev(60_000, "next", 0, 0), ev(900_000, "next", 1, 0)]
    segs = ss.segments(ev_list, "amrap", 2, 120_000)
    assert [(s.t0, s.t1) for s in segs] == [(0, 60_000), (60_000, 120_000)]


def test_non_ascii_digit_key_is_422_and_missing_fell_short_is_safe(c, engine):
    p = plan("E", "emom", moves=[mv("Swings")])
    sid = c.post(f"{API}/sessions", json=session(plan=p, fell_short=[2])).json()["id"]
    assert c.put(f"{API}/sessions/{sid}/short", json={"\u00b2": 3}).status_code == 422
    assert c.put(f"{API}/sessions/{sid}/short", json={"\u0662": 3}).status_code == 422  # Arabic-Indic two
    with Session(engine) as s:
        s.get(models.WorkoutSession, sid).fell_short = None
        s.commit()
    assert c.put(f"{API}/sessions/{sid}/short", json={"2": 3}).status_code == 422
    r = c.get(f"{API}/sessions/{sid}/summary")
    assert r.status_code == 200 and r.json()["fell_short"] == []


def test_estimated_watch_effort_is_flagged_and_loses_to_a_manual_pick(c, engine):
    sid, _ = summary(c)
    add_strength(engine, effort=4, estimated=True)
    sm = c.get(f"{API}/sessions/{sid}/summary").json()
    assert sm["effort"] == 4 and sm["effort_source"] == "watch" and sm["effort_estimated"] is True
    c.put(f"{API}/sessions/{sid}/effort", json={"effort": 8})
    sm = c.get(f"{API}/sessions/{sid}/summary").json()
    assert sm["effort"] == 8 and sm["effort_source"] == "manual" and sm["effort_estimated"] is False


def test_real_watch_rating_beats_a_manual_pick(c, engine):
    sid, _ = summary(c)
    c.put(f"{API}/sessions/{sid}/effort", json={"effort": 8})
    add_strength(engine, effort=5)
    sm = c.get(f"{API}/sessions/{sid}/summary").json()
    assert sm["effort"] == 5 and sm["effort_source"] == "watch" and sm["effort_estimated"] is False


def test_round_mode_session_has_per_round_hr_zones_and_no_per_move_rows(c, engine):
    add_strength(engine)
    set_hrmax(engine, 200)
    recompute_now(engine, "2026-11-04")
    # Round 1 work 0-60, rest 60-90, round 2 work 90-150, rest 150-180, End in round 3 at 200.
    events = [ev(60_000, "next", 1, 0), ev(90_000, "next", 1, 0), ev(150_000, "next", 1, 1), ev(180_000, "next", 1, 1),
              ev(200_000, "end", 0, 2)]
    pl = plan(moves=[mv("Swing"), mv("Goblet squat")], fmt="complex", tap_per="round", rounds=5)
    _, sm = summary(c, plan=pl, events=events, rounds_done=2, partial_moves=1, end_utc="2026-11-03T18:03:20Z")
    assert sm["session"]["plan"]["tap_per"] == "round"
    assert sm["moves"] == []
    assert [(r["round"], r["time_s"], r["moves"]) for r in sm["rounds"]] == [(1, 60, 2), (2, 60, 2)]
    assert [r["avg_hr"] for r in sm["rounds"]] == [pytest.approx(100, abs=0.1), pytest.approx(115, abs=0.1)]
    assert sm["zone_seconds"] and sm["avg_hr"] is not None


def test_emom_ignores_tap_per_round_and_old_plans_default_to_move(c):
    p = c.post(f"{API}/plans", json=plan("E", "emom", tap_per="round")).json()
    assert p["tap_per"] == "move"
    q = c.post(f"{API}/plans", json=plan("C", "complex", tap_per="round")).json()
    assert q["tap_per"] == "round"
    assert c.post(f"{API}/plans", json=plan("D", "complex")).json()["tap_per"] == "move"
    assert c.post(f"{API}/plans/{q['id']}/duplicate").json()["tap_per"] == "round"
    q["tap_per"] = "move"
    assert c.put(f"{API}/plans/{q['id']}", json=q).json()["tap_per"] == "move"


def test_migration_0019_defaults_existing_plans_to_move(tmp_path):
    from strydr.store.engine import make_engine
    from sqlalchemy import text
    e = make_engine(tmp_path / "m.db", KEY)
    cfg = Config()
    cfg.set_main_option("script_location", str(migrate._DIR))
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.upgrade(cfg, "0018")
        cn.execute(text("insert into workout_plan (name, format, rounds, moves, created_at, updated_at) values ('x','complex',3,'[]','2026-01-01','2026-01-01')"))
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.upgrade(cfg, "head")
    with e.connect() as cn:
        assert cn.execute(text("select tap_per from workout_plan")).scalar() == "move"
    with e.begin() as cn:
        cfg.attributes["connection"] = cn
        command.downgrade(cfg, "0018")
    assert "tap_per" not in {x["name"] for x in inspect(e).get_columns("workout_plan")}
    e.dispose()
