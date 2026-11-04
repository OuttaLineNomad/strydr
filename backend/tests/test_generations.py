from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from strydr.jobs import queue, scheduler
from strydr.store import generations, models, settings
from strydr.store.models import Base

from conftest import count, load_fixture
from helpers import add_run, recompute_now

AS_OF = "2026-10-26"


def _seed(engine):
    add_run(engine, "r1", datetime(2026, 10, 5, 7), 40, 3.0)
    add_run(engine, "r2", datetime(2026, 10, 7, 7), 30, 3.2)


def _current(engine) -> int | None:
    with Session(engine) as s:
        return generations.current_id(s)


def test_swap_is_atomic_for_a_reader(engine):
    _seed(engine)
    first = recompute_now(engine, AS_OF)
    with generations.read_snapshot(engine) as reader:
        seen = reader.execute(select(func.count()).select_from(models.WorkoutDetail).where(generations.in_current(models.WorkoutDetail))).scalar_one()
        second = recompute_now(engine, AS_OF)  # flips the pointer and deletes the first generation mid-read
        again = reader.execute(select(func.count()).select_from(models.WorkoutDetail).where(generations.in_current(models.WorkoutDetail))).scalar_one()
        assert reader.execute(select(models.CurrentGeneration.generation_id)).scalar_one() == first
    assert seen == again == 2
    assert _current(engine) == second != first
    assert count(engine, models.Generation) == 1
    assert count(engine, models.WorkoutDetail, models.WorkoutDetail.generation_id == first) == 0


def test_partial_generation_is_never_visible(engine, monkeypatch):
    _seed(engine)
    first = recompute_now(engine, AS_OF)
    observed = {}

    def spy(ctx, profile):  # runs after derive wrote the new generation, before the flip
        observed["building"] = count(engine, models.WorkoutDetail, models.WorkoutDetail.generation_id == ctx.generation_id)
        observed["current"] = _current(engine)

    monkeypatch.setattr("strydr.jobs.recompute.insights.run", spy)
    second = recompute_now(engine, AS_OF)
    assert observed == {"building": 2, "current": first}
    assert _current(engine) == second


def test_failed_generation_is_discarded_and_old_one_stays(engine, monkeypatch):
    _seed(engine)
    first = recompute_now(engine, AS_OF)

    def boom(ctx, profile):
        raise RuntimeError("stage failed")

    monkeypatch.setattr("strydr.jobs.recompute.insights.run", boom)
    with pytest.raises(RuntimeError):
        recompute_now(engine, AS_OF)
    assert _current(engine) == first
    assert count(engine, models.Generation) == 1


def test_one_bad_workout_is_a_data_quality_issue_not_a_failure(engine, monkeypatch):
    _seed(engine)
    real = __import__("strydr.pipeline.derive.track", fromlist=["splits"]).splits
    calls = {"n": 0}

    def flaky(*args, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("bad track")
        return real(*args, **kw)

    monkeypatch.setattr("strydr.pipeline.derive.track.splits", flaky)
    gid = recompute_now(engine, AS_OF)
    with Session(engine) as s:
        issues = s.execute(select(models.DataQualityIssue).where(models.DataQualityIssue.generation_id == gid)).scalars().all()
    assert [(i.workout_id, i.stage, i.error) for i in issues] == [("r1", "derive", "ValueError")]
    assert count(engine, models.WorkoutDetail, models.WorkoutDetail.generation_id == gid) == 1
    assert _current(engine) == gid


def test_worker_runs_recompute_job_and_coalesces(engine, worker):
    _seed(engine)
    with Session(engine) as s:
        queue.enqueue_recompute(s, "2026-10-25")
        queue.enqueue_recompute(s, AS_OF)
        s.commit()
    assert count(engine, models.Job, models.Job.type == "recompute") == 1
    worker.run_all()
    with Session(engine) as s:
        assert s.get(models.Generation, _current(engine)).as_of == AS_OF


def test_daily_tick_enqueues_today_in_home_tz(engine):
    with Session(engine) as s:
        settings.write(s, settings.UserSettings(home_tz="Pacific/Auckland"))
        s.commit()
    today = scheduler.tick(engine, "UTC")
    assert today == queue.local_today("Pacific/Auckland")
    with Session(engine) as s:
        job = s.execute(select(models.Job).where(models.Job.type == "recompute")).scalar_one()
    assert job.as_of == today and job.status == "pending"


def test_seconds_until_tick_is_0300_local():
    tz = ZoneInfo("America/New_York")
    assert scheduler.seconds_until_tick(datetime(2026, 10, 26, 2, 0, tzinfo=tz), tz) == 3600
    assert scheduler.seconds_until_tick(datetime(2026, 10, 26, 4, 0, tzinfo=tz), tz) == 23 * 3600


def test_fixture_export_recomputes_end_to_end(engine, send):
    send(load_fixture("hae-export.json"))  # process_raw jobs enqueue and run the real recompute
    with Session(engine) as s:
        gid = generations.current_id(s)
        assert gid is not None
        assert s.get(models.ProfileResult, gid) is not None
        assert s.execute(select(func.count()).select_from(models.WorkoutDetail)).scalar_one() == 9


def test_migrations_match_models(engine):
    with engine.connect() as c:
        assert compare_metadata(MigrationContext.configure(c), Base.metadata) == []
