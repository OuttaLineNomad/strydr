"""Story 21: run/walk split of a run from cadence (or pace), with a cutoff learned from the runner's own windows."""
import random

from strydr.pipeline.derive import runwalk as rw
from strydr.pipeline.derive.routes.display import for_display


def steps(blocks):
    """A step series of 10 s intervals: blocks are (seconds, steps per minute)."""
    t, dt, n, now = [], [], [], 0.0
    for sec, spm in blocks:
        for _ in range(int(sec // 10)):
            t.append(now), dt.append(10.0), n.append(spm / 6)
            now += 10
    return {"t": t, "dt": dt, "steps": n}


def win(blocks, route=None):
    return rw.windows(steps(blocks), route)


def bimodal(minutes=40, seed=1):
    rnd = random.Random(seed)
    out = []
    for _ in range(minutes * 6):
        centre = 110 if rnd.random() < 0.3 else 150
        out.append(rw.Window(rnd.gauss(centre, 6), None))
    return out


def test_bimodal_history_cuts_at_low_point():
    c = rw.learn_cutoff([bimodal()])
    assert c.spm_learned and 125 <= c.spm <= 135


def test_thin_history_falls_back():
    c = rw.learn_cutoff([bimodal(minutes=20)])
    assert c.spm == 130 and not c.spm_learned


def test_unimodal_history_falls_back():
    rnd = random.Random(2)
    c = rw.learn_cutoff([[rw.Window(rnd.gauss(150, 5), None) for _ in range(400)]])
    assert c.spm == 130 and not c.spm_learned


def test_cutoff_outside_range_falls_back():
    c = rw.learn_cutoff([[rw.Window(150.0 + (i % 2) * 40, None) for i in range(400)]])
    assert c.spm == 130 and not c.spm_learned  # the low point (170) lies outside 110-150


def test_mixed_run():
    r = rw.split(win([(1200, 150), (480, 110)]), rw.Cutoffs(130, True, 2.0, False))
    assert (r["run_pct"], r["walk_pct"], r["stopped_pct"]) == (71.4, 28.6, 0.0)
    assert r["source"] == "cadence" and r["cutoff"] == 130
    assert r["walk_ranges"] == [[1200.0, 1680.0]]


def test_standing_is_stopped_not_walking():
    r = rw.split(win([(900, 150), (60, 20), (840, 150)]), rw.Cutoffs(130, True, 2.0, False))
    assert r["stopped_pct"] == 3.3 and r["walk_pct"] == 0
    assert r["run_pct"] + r["walk_pct"] + r["stopped_pct"] == 100


def test_pause_adds_nothing():
    # 5 minutes paused at 600 s: the active clock freezes, wall time keeps going
    s = steps([(600, 150), (300, 0), (600, 150)])
    route = {"t": [0.0, 600.0, 900.0, 1500.0], "at": [0.0, 600.0, 600.0, 1200.0]}
    # step intervals inside the pause are dropped (zero active length)
    w = rw.windows(s, route)
    assert len(w) == 120
    r = rw.split(w, rw.Cutoffs(130, True, 2.0, False))
    assert r["run_pct"] == 100 and r["stopped_pct"] == 0


def test_pace_only():
    route = {"t": [float(i) for i in range(0, 600)], "at": [float(i) for i in range(0, 600)],
             "speed": [3.0] * 400 + [1.2] * 200}
    w = rw.windows(None, route)
    r = rw.split(w, rw.Cutoffs(130, True, 2.063, False))
    assert r["source"] == "pace" and r["run_pct"] == 66.7 and r["walk_pct"] == 33.3
    assert r["cutoff"] == 2.063


def test_nothing():
    assert rw.windows(None, {"t": [0.0, 1.0], "speed": [None, None]}) == []
    assert rw.split([], rw.Cutoffs(130, False, 2.0, False)) is None


def test_pace_cutoff_default_is_13_minute_mile():
    assert abs(rw.DEFAULT_PACE_CUTOFF_MPS - 2.0633) < 1e-3


def test_map_clip_drops_walk_inside_zone():
    class Z:
        lat, lon, radius_m, offset_north_m, offset_east_m, trim_m = 40.0, -80.0, 200.0, 0.0, 0.0, 50.0
    n = 300
    lat = [40.0 - 0.0045 + i * 0.00003 for i in range(n)]  # heading north through the zone, 3.3 m apart
    geo = {"lat": lat, "lon": [-80.0] * n, "at": [float(i) for i in range(n)]}
    for ranges in ([[0.0, 300.0]], [[10.0, 160.0]], [[140.0, 300.0]]):  # the last two straddle the zone edge
        out = for_display(geo, [Z()], walk_ranges=ranges)
        assert out["walk_segments"]
        assert all(abs((p[0] - 40.0) * 111_320) > 250 for seg in out["walk_segments"] for p in seg)
    assert for_display(geo, [], walk_ranges=[[0.0, 300.0]])["walk_segments"]
    assert for_display(geo, [], walk_ranges=None)["walk_segments"] == []
    assert for_display({"lat": lat, "lon": [-80.0] * n}, [], walk_ranges=[[0.0, 300.0]])["walk_segments"] == []


def test_skewed_history_still_learns_cutoff_and_ignores_glitches():
    rnd = random.Random(3)
    runs = [[rw.Window(rnd.gauss(105, 8), None) for _ in range(900)] + [rw.Window(rnd.gauss(150, 6), None) for _ in range(32)]
            + [rw.Window(1000.0, None) for _ in range(20)]]
    c = rw.learn_cutoff(runs)
    assert c.spm_learned and 125 <= c.spm <= 135


def test_glitch_cadence_is_no_cadence():
    s = steps([(100, 150)])
    s["steps"][0] = 9999.0
    assert rw.windows(s, None)[0].cadence is None


def test_learned_pace_cutoff():
    rnd = random.Random(4)
    run = [rw.Window(150.0, max(0.6, rnd.gauss(3.2 if i % 4 else 1.8, 0.2))) for i in range(400)]
    c = rw.learn_cutoff([run])
    assert c.mps_learned and 2.0 <= c.mps <= 2.7


# --- derive and API -------------------------------------------------------------------------------------------------
from datetime import datetime, timedelta  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from strydr.store import models  # noqa: E402
from helpers import add_run, login, recompute_now  # noqa: E402

T0 = datetime(2026, 10, 5, 12, 0)


def _seed(engine, n=8, cadence=True):
    """Runs of 30 min: 20 at 150 spm then 8 at 110 spm (2 min at 40 spm standing), one run per week."""
    def cad(i):
        return 150 if i < 1200 else 40 if i < 1320 else 110
    for k in range(n):
        add_run(engine, f"rw{k}", T0 + timedelta(days=7 * k), 30, speed_fn=lambda i: 3.0 if i < 1200 else 1.5,
                cadence_fn=cad if cadence else None)
    return recompute_now(engine, (T0 + timedelta(days=7 * n)).date().isoformat())


def test_derive_stores_split_and_week_seconds(engine):
    _seed(engine)
    with Session(engine) as s:
        d = s.execute(select(models.WorkoutDetail).where(models.WorkoutDetail.workout_id == "rw0")).scalar_one()
        assert d.runwalk["source"] == "cadence" and d.runwalk["cutoff_learned"]
        assert d.runwalk["run_pct"] + d.runwalk["walk_pct"] + d.runwalk["stopped_pct"] == 100
        assert d.runwalk["stopped_pct"] == 6.7 and "walk_ranges" not in d.runwalk
        p = s.execute(select(models.PeriodSummary).where(models.PeriodSummary.kind == "week")).scalars().first()
        assert p.run_s == 1200.0 and p.walk_s == 480.0


def test_pace_only_run_and_nothing(engine):
    _seed(engine, n=2, cadence=False)
    add_run(engine, "bare", T0 + timedelta(days=30), 20, route=False, hr=None)
    recompute_now(engine, "2026-12-01")
    with Session(engine) as s:
        rows = {d.workout_id: d.runwalk for d in s.execute(select(models.WorkoutDetail)).scalars()}
    assert rows["rw0"]["source"] == "pace" and rows["rw0"]["walk_pct"] == 33.3
    assert rows["bare"] is None


def test_api_serves_split_walk_segments_and_weekly_share(app_client, engine):
    client = app_client
    login(client)
    _seed(engine)
    d = client.get("/api/v1/workouts/rw0").json()
    assert d["runwalk"]["source"] == "cadence" and d["runwalk"]["walk_pct"] == 26.7
    assert d["display_geometry"]["walk_segments"]
    assert "step" not in str(d["runwalk"]) and "walk_ranges" not in d["runwalk"]
    weeks = client.get("/api/v1/weeks", params={"from": "2026-W41", "to": "2026-W42"}).json()
    assert {w["week_id"]: w["walk_pct"] for w in weeks}["2026-W41"] == 28.6  # walking over running plus walking
    assert client.get("/api/v1/weeks/2026-W41").json()["walk_pct"] == 28.6
