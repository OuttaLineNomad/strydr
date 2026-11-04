"""Identity merge between HAE and Apple copies of the same workout (CAP-17, story 3)."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import FIXTURES, count
from strydr.pipeline.normalize.process import write_workout
from strydr.sources import hae
from strydr.sources.apple import parse as apple_parse
from strydr.sources.canonical import SampleSeries, Workout, fallback_workout_id
from strydr.store import models
from test_apple_adapter import EXPORT, HOME, open_route

T0 = datetime(2026, 4, 1)
HAE_RUN = "009B784A-7117-5211-8A16-975F687B671C"  # 2026-03-03 12:30:00 UTC; Apple's twin starts 20 s later


def hae_items():
    with open(FIXTURES / "hae-export.json", "rb") as f:
        return [w for w in hae.parse(f) if isinstance(w, Workout)]


def apple_items():
    with open(EXPORT, "rb") as f:
        return [w for w in apple_parse(f, HOME, open_route) if isinstance(w, Workout)]


def put(engine, items, n=0, source="hae"):
    """Write items as one payload of `source` received at T0 + n minutes."""
    with Session(engine) as s:
        p = models.RawPayload(received_at=T0 + timedelta(minutes=n), status="processed", size_bytes=0, source=source)
        s.add(p)
        s.flush()
        for w in items:
            write_workout(s, w, p.id, T0 + timedelta(minutes=n))
        s.commit()


def rows(engine):
    with Session(engine) as s:
        return {w.workout_id: w for w in s.execute(select(models.Workout)).scalars()}


def series(engine, wid):
    with Session(engine) as s:
        return {r.series: r.n_samples for r in s.execute(
            select(models.SampleSeries).where(models.SampleSeries.workout_id == wid)).scalars()}


def user_data(engine, wid):
    with Session(engine) as s:
        s.add(models.WorkoutNote(workout_id=wid, text="felt good", rpe=6, updated_at=T0))
        s.commit()


def test_apple_after_hae_merges_into_one_workout(engine):
    put(engine, [w for w in hae_items() if w.workout_id == HAE_RUN])
    user_data(engine, HAE_RUN)
    with Session(engine) as s:
        s.add(models.WorkoutTypeOverride(workout_id=HAE_RUN, type="run", created_at=T0))
        s.commit()
    apple_run = next(w for w in apple_items() if w.type == "run" and not w.is_indoor)
    put(engine, [apple_run], n=5, source="apple")

    got = rows(engine)
    assert list(got) == [HAE_RUN]  # one workout, HAE's id
    w = got[HAE_RUN]
    assert w.start_utc == datetime(2026, 3, 3, 12, 30, 20)  # Apple wins: its copy has the samples
    assert w.sample_count == 321 + 1500 and w.series_count == 2
    assert series(engine, HAE_RUN) == {"heart_rate": 321, "route": 1500, "splits": 8, "step_count": 188}  # HAE's splits are kept
    hae_run = next(x for x in hae_items() if x.workout_id == HAE_RUN)
    assert (w.effort_score, w.effort_estimated) == (5.0, hae_run.effort_estimated) and w.avg_cadence == 83.2
    assert hae_run.effort_estimated is not None  # the HAE-only fields survive the Apple win
    assert w.avg_hr == 158 and w.max_hr == 176  # Apple's own values stay
    with Session(engine) as s:
        assert s.get(models.WorkoutNote, HAE_RUN).text == "felt good"
        assert s.get(models.WorkoutTypeOverride, HAE_RUN).type == "run"


def test_hae_after_apple_keeps_apples_id(engine):
    apple_run = next(w for w in apple_items() if w.type == "run" and not w.is_indoor)
    apple_id = fallback_workout_id("run", apple_run.start_utc)
    put(engine, [apple_run], source="apple")
    put(engine, [w for w in hae_items() if w.workout_id == HAE_RUN], n=5)  # later, but fewer samples

    got = rows(engine)
    assert list(got) == [apple_id] and apple_id.startswith("h:")
    w = got[apple_id]
    assert w.start_utc == apple_run.start_utc and w.series_count == 2
    hae_run = next(x for x in hae_items() if x.workout_id == HAE_RUN)
    assert (w.effort_score, w.effort_estimated) == (5.0, hae_run.effort_estimated) and w.avg_cadence == 83.2  # from the losing HAE copy
    assert hae_run.effort_estimated is not None
    # HAE's splits join the winning Apple copy; precedence counts stay Apple's own.
    assert series(engine, apple_id) == {"heart_rate": 321, "route": 1500, "splits": 8, "step_count": 188}
    assert w.sample_count == 321 + 1500


def _route_heavy_hae_run():
    """The HAE twin (per-minute heart rate) with a route far denser than Apple's: each point split into k."""
    hae_run = next(x for x in hae_items() if x.workout_id == HAE_RUN)
    route = hae_run.series["route"].columns
    k = 3000 // len(route["t"]) + 1
    dense = {c: [x for x in v for _ in range(k)] for c, v in route.items()}
    dense["t"] = [x + i / k for x in route["t"] for i in range(k)]  # still increasing
    hae_run.series["route"] = SampleSeries("route", dense)
    return hae_run


@pytest.mark.parametrize("apple_first", [True, False])
def test_finer_heart_rate_beats_a_denser_route(engine, apple_first):
    apple_run = next(w for w in apple_items() if w.type == "run" and not w.is_indoor)
    hae_run = _route_heavy_hae_run()
    assert hae_run.series["route"].n + hae_run.series["heart_rate"].n > 321 + 1500  # more samples in total
    copies = [(apple_run, "apple"), (hae_run, "hae")]
    for n, (w, src) in enumerate(copies if apple_first else copies[::-1]):
        put(engine, [w], n=n, source=src)

    (wid, w), = rows(engine).items()
    assert w.start_utc == apple_run.start_utc  # Apple's copy won either way
    assert series(engine, wid)["heart_rate"] == 321 and series(engine, wid)["splits"] == 8


def test_a_re_exported_apple_history_keeps_what_hae_merged_in(engine):
    apple_run = next(w for w in apple_items() if w.type == "run" and not w.is_indoor)
    put(engine, [apple_run], source="apple")
    put(engine, [w for w in hae_items() if w.workout_id == HAE_RUN], n=5)
    put(engine, [next(w for w in apple_items() if w.type == "run" and not w.is_indoor)], n=10, source="apple")

    (wid, w), = rows(engine).items()
    assert w.received_at == T0 + timedelta(minutes=10)  # the newer export replaced the stored copy
    assert series(engine, wid) == {"heart_rate": 321, "route": 1500, "splits": 8, "step_count": 188}
    assert w.effort_score == 5.0 and w.avg_cadence == 83.2


def test_hr_tie_falls_back_to_total_samples(engine):
    apple_run = next(w for w in apple_items() if w.type == "run" and not w.is_indoor)
    hae_run = _route_heavy_hae_run()
    hae_run.series["heart_rate"] = apple_run.series["heart_rate"]  # equal heart rate
    put(engine, [apple_run], source="apple")
    put(engine, [hae_run], n=5)

    (wid, w), = rows(engine).items()
    assert w.start_utc == hae_run.start_utc and w.sample_count == hae_run.series["route"].n + 321


def test_different_type_is_not_merged(engine):
    indoor_walk = next(w for w in hae_items() if w.type == "walk" and w.is_indoor)
    indoor_run = next(w for w in apple_items() if w.type == "run" and w.is_indoor)
    assert indoor_walk.start_utc == indoor_run.start_utc
    put(engine, [indoor_walk])
    put(engine, [indoor_run], n=5, source="apple")
    assert len(rows(engine)) == 2


def test_type_override_allows_cross_type_merge(engine):
    indoor_walk = next(w for w in hae_items() if w.type == "walk" and w.is_indoor)
    indoor_run = next(w for w in apple_items() if w.type == "run" and w.is_indoor)
    put(engine, [indoor_walk])
    with Session(engine) as s:
        s.add(models.WorkoutTypeOverride(workout_id=indoor_walk.workout_id, type="walk", created_at=T0))
        s.commit()
    put(engine, [indoor_run], n=5, source="apple")
    assert list(rows(engine)) == [indoor_walk.workout_id]


@pytest.mark.parametrize("gap, expected", [(60, 1), (61, 2), (-60, 1), (-61, 2)])
def test_sixty_second_boundary(engine, gap, expected):
    hae_run = next(w for w in hae_items() if w.workout_id == HAE_RUN)
    apple_run = next(w for w in apple_items() if w.type == "run" and not w.is_indoor)
    apple_run.start_utc = hae_run.start_utc + timedelta(seconds=gap)
    apple_run.workout_id = fallback_workout_id("run", apple_run.start_utc)
    put(engine, [hae_run])
    put(engine, [apple_run], n=5, source="apple")
    assert len(rows(engine)) == expected


def test_nearest_start_is_chosen(engine):
    base = next(w for w in hae_items() if w.workout_id == HAE_RUN)
    kw = dict(type="run", is_indoor=False, end_utc=base.end_utc, utc_offset_s=0, local_date="2026-03-03")
    far = Workout(workout_id="far", start_utc=base.start_utc - timedelta(seconds=55), **kw)
    near = Workout(workout_id="near", start_utc=base.start_utc + timedelta(seconds=10), **kw)
    put(engine, [far, near], source="apple")  # 65 s apart, one source: two workouts
    assert sorted(rows(engine)) == ["far", "near"]
    twin = Workout(workout_id="incoming", start_utc=base.start_utc, series={"heart_rate": base.series["heart_rate"]}, **kw)
    put(engine, [twin], n=5)
    assert sorted(rows(engine)) == ["far", "near"]
    assert series(engine, "near") == {"heart_rate": base.series["heart_rate"].n} and series(engine, "far") == {}


def test_same_source_workouts_never_merge(engine):
    base = next(w for w in hae_items() if w.workout_id == HAE_RUN)
    kw = dict(type="run", is_indoor=False, end_utc=base.end_utc, utc_offset_s=0, local_date="2026-03-03")
    a = Workout(workout_id="a", start_utc=base.start_utc, **kw)
    b = Workout(workout_id="b", start_utc=base.start_utc + timedelta(seconds=30), **kw)
    put(engine, [a, b])
    assert sorted(rows(engine)) == ["a", "b"]
    put(engine, [Workout(workout_id="c", start_utc=base.start_utc + timedelta(seconds=15), **kw)], n=1, source="apple")
    assert len(rows(engine)) == 2  # the apple copy joined one of them


def test_quality_flags_union_on_a_cross_source_merge(engine):
    hae_run = next(w for w in hae_items() if w.workout_id == HAE_RUN)
    hae_run.quality_flags = {"hr_samples_dropped": 2, "x": 1}
    apple_run = next(w for w in apple_items() if w.type == "run" and not w.is_indoor)
    put(engine, [hae_run])
    put(engine, [apple_run], n=5, source="apple")
    assert rows(engine)[HAE_RUN].quality_flags == {"hr_samples_dropped": 1, "x": 1}  # the winner's value wins


def test_same_id_copy_of_the_other_source_keeps_the_merge(engine):
    # Apple won the merged row; an HAE resend (same id) that wins back must keep Apple's fields and splits stay
    hae_run = next(w for w in hae_items() if w.workout_id == HAE_RUN)
    apple_run = next(w for w in apple_items() if w.type == "run" and not w.is_indoor)
    put(engine, [hae_run])
    put(engine, [apple_run], n=5, source="apple")
    again = next(w for w in hae_items() if w.workout_id == HAE_RUN)
    again.series["heart_rate"].columns = {k: v * 20 for k, v in again.series["heart_rate"].columns.items()}  # 480 beats HR
    again.series["route"].columns = {k: v * 2 for k, v in again.series["route"].columns.items()}
    again.avg_hr = None
    put(engine, [again], n=9)  # more samples, later: replaces the Apple-won row
    w = rows(engine)[HAE_RUN]
    assert w.sample_count == again.series["heart_rate"].n + again.series["route"].n
    assert w.avg_hr == 158  # filled from the replaced Apple copy


def test_stored_id_is_not_rematched(engine):
    # an incoming workout whose id is already stored is that workout, whatever is nearby
    put(engine, [w for w in hae_items() if w.workout_id == HAE_RUN])
    put(engine, [w for w in hae_items() if w.workout_id == HAE_RUN], n=1)
    assert list(rows(engine)) == [HAE_RUN]


def test_reapplying_the_export_changes_nothing(engine):
    put(engine, hae_items())
    put(engine, apple_items(), n=5, source="apple")
    before = {k: (v.start_utc, v.sample_count, v.series_count, v.received_at) for k, v in rows(engine).items()}
    put(engine, apple_items(), n=5, source="apple")
    after = {k: (v.start_utc, v.sample_count, v.series_count, v.received_at) for k, v in rows(engine).items()}
    assert before == after


def test_reparse_order_is_deterministic(tmp_path):
    from conftest import KEY
    from strydr.store import migrate
    from strydr.store.engine import make_engine

    def run(name):
        e = make_engine(tmp_path / f"{name}.db", KEY)
        migrate.upgrade(e)
        put(e, hae_items())
        put(e, apple_items(), n=5, source="apple")
        out = {k: (v.type, v.start_utc, v.sample_count) for k, v in rows(e).items()}
        e.dispose()
        return out

    first, second = run("a"), run("b")
    assert first == second
    assert len(first) == 9 + 8 - 3  # the twin run, the 03-04 walk and the 03-03 strength merge; the other five Apple workouts are new
    assert HAE_RUN in first


def test_merged_twin_run_recomputes_with_zones_route_and_splits(engine, app_client):
    from helpers import login, recompute_now
    from strydr.store import generations, settings

    put(engine, hae_items())
    put(engine, apple_items(), n=5, source="apple")
    with Session(engine) as s:
        settings.write(s, settings.UserSettings(hrmax_override=190))
        s.commit()
    recompute_now(engine, "2026-03-10")
    with Session(engine) as s:
        summ = s.execute(generations.scoped(models.WorkoutSummary).where(models.WorkoutSummary.workout_id == HAE_RUN)).scalar_one()
        det = s.execute(generations.scoped(models.WorkoutDetail).where(models.WorkoutDetail.workout_id == HAE_RUN)).scalar_one()
        disp = s.execute(generations.scoped(models.WorkoutDisplay).where(models.WorkoutDisplay.workout_id == HAE_RUN)).scalar_one()
    assert summ.zone_seconds and sum(summ.zone_seconds) > 1000  # the 320 bpm reading is dropped, the rest is in zones
    assert det.splits_km  # HAE's splits survived the Apple win
    assert disp.display_geometry
    login(app_client)
    listed = app_client.get("/api/v1/workouts", params={"type": "run"}).json()
    on_the_day = [w["workout_id"] for w in listed if w["local_date"] == "2026-03-03"]
    assert on_the_day == [HAE_RUN]  # one row in the run list for the merged run


def test_migration_0008_adds_source_and_downgrade_removes_it(engine):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from strydr.store import migrate

    cols = lambda: {c["name"] for c in inspect(engine).get_columns("raw_payload")}  # noqa: E731
    assert "source" in cols()
    put(engine, [], source="apple")
    cfg = Config()
    cfg.set_main_option("script_location", str(migrate._DIR))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0007")
    assert "source" not in cols()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    with Session(engine) as s:
        assert {p.source for p in s.execute(select(models.RawPayload)).scalars()} == {"hae"}  # existing rows are hae
