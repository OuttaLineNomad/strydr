"""Snapshot (AD-12), reparse (AD-1), the nightly schedule and the SPA / health surface (AD-11)."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import sqlcipher3
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from strydr.api import create_app
from strydr.jobs import Worker, queue, reparse, scheduler
from strydr.jobs.snapshot import snapshot
from strydr.sources.hae import ADAPTER_VERSION
from strydr.store import models
from strydr.store.engine import key_pragma

from conftest import FIXTURES, KEY, count
from helpers import add_run


def _open(path, key):
    conn = sqlcipher3.connect(str(path))
    if key is not None:
        conn.execute(key_pragma(key))
    return conn


def test_snapshot_opens_only_with_the_key(engine, tmp_path):
    add_run(engine, "r1", datetime(2026, 10, 20, 7), 5, 3.0)
    out = snapshot(engine, KEY, tmp_path / "backups", "2026-10-26")
    assert out.name == "strydr-20261026.db"
    with _open(out, KEY) as c:
        assert c.execute("SELECT count(*) FROM workout").fetchone()[0] == 1
    for wrong in (None, "0" * 64, "not the key"):
        with _open(out, wrong) as c, pytest.raises(sqlcipher3.DatabaseError):
            c.execute("SELECT count(*) FROM workout").fetchone()
    assert b"SQLite format 3" not in out.read_bytes()[:16]  # no plaintext header
    assert not list((tmp_path / "backups").glob("*.tmp"))


def test_snapshot_keeps_the_newest_seven(engine, tmp_path):
    dest = tmp_path / "b"
    for day in range(1, 10):
        snapshot(engine, KEY, dest, f"2026-10-{day:02d}")
    assert [p.name for p in sorted(dest.glob("*.db"))] == [f"strydr-202610{d:02d}.db" for d in range(3, 10)]


def test_snapshot_job_runs_through_the_worker(engine, tmp_path):
    w = Worker(engine, "UTC", backoff_s=0, db_key=KEY, backup_dir=tmp_path / "backups")
    scheduler.snapshot_tick(engine)
    scheduler.snapshot_tick(engine)  # coalesced
    assert count(engine, models.Job, models.Job.type == "snapshot") == 1
    w.run_all()
    assert len(list((tmp_path / "backups").glob("strydr-*.db"))) == 1
    assert count(engine, models.Job, models.Job.type == "snapshot", models.Job.status == "done") == 1


def test_snapshot_is_scheduled_at_0230_home_tz_before_the_tick():
    tz = ZoneInfo("America/New_York")
    now = datetime(2026, 10, 26, 1, 0, tzinfo=tz)
    assert scheduler.seconds_until(now, tz, *scheduler.SNAPSHOT_AT) == 90 * 60
    assert scheduler.seconds_until(datetime(2026, 10, 26, 2, 30, tzinfo=tz), tz, *scheduler.SNAPSHOT_AT) == 24 * 3600
    assert scheduler.seconds_until_tick(now, tz) == 2 * 3600


# ---- reparse ----------------------------------------------------------------------------------------------------------

def test_reparse_rebuilds_canonical_from_raw_when_the_adapter_is_newer(engine, send, worker):
    send(json.loads((FIXTURES / "hae-export.json").read_text()))
    before = {m.__name__ if hasattr(m, "__name__") else str(m): count(engine, m) for m in (models.Workout, models.SampleSeries, models.DailyMetric)}
    assert not reparse.needs_reparse(engine) and reparse.enqueue_if_stale(engine) is False
    with Session(engine) as s:  # pretend an older adapter produced these rows
        for m in (models.Workout, models.SampleSeries, models.DailyMetric):
            s.execute(m.__table__.update().values(adapter_version=ADAPTER_VERSION - 1))
        s.commit()
    assert reparse.needs_reparse(engine) and reparse.enqueue_if_stale(engine) and reparse.enqueue_if_stale(engine)
    assert count(engine, models.Job, models.Job.type == "reparse", models.Job.status == "pending") == 1
    worker.run_all()
    after = {m.__name__ if hasattr(m, "__name__") else str(m): count(engine, m) for m in (models.Workout, models.SampleSeries, models.DailyMetric)}
    assert after == before
    with Session(engine) as s:
        for m in (models.Workout, models.SampleSeries, models.DailyMetric):
            assert s.execute(select(func.min(m.adapter_version))).scalar_one() == ADAPTER_VERSION
        assert s.execute(select(func.count()).select_from(models.RawPayload).where(models.RawPayload.status == "processed")).scalar_one() == 1
    assert not reparse.needs_reparse(engine)


def test_reparse_with_no_data_is_a_no_op(engine):
    assert reparse.needs_reparse(engine) is False


# ---- serving ----------------------------------------------------------------------------------------------------------

@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<html>spa</html>")
    (d / "assets" / "app-abc123.js").write_text("console.log(1)")
    (d / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("secret")
    return d


def test_spa_assets_and_history_fallback(engine, dist):
    c = TestClient(create_app(engine, web_dist=dist))
    assert c.get("/").text == "<html>spa</html>"
    assert c.get("/runs/abc/def").text == "<html>spa</html>"  # client-side route
    a = c.get("/assets/app-abc123.js")
    assert a.text == "console.log(1)" and "immutable" in a.headers["cache-control"]
    assert c.get("/favicon.svg").text == "<svg/>"
    assert c.get("/").headers["cache-control"] == "no-cache"


def test_spa_fallback_never_swallows_the_api_or_escapes_the_dist(engine, dist):
    c = TestClient(create_app(engine, web_dist=dist))
    r = c.get("/api/v1/nope")
    assert r.status_code == 404 and "spa" not in r.text
    assert c.get("/api/v1/insights").status_code == 401  # still behind the session
    for p in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        assert "secret" not in c.get(p).text
    assert c.post("/runs/abc").status_code in (404, 405)


def test_without_a_dist_directory_nothing_is_served(engine, tmp_path):
    assert TestClient(create_app(engine, web_dist=tmp_path / "missing")).get("/").status_code == 404


def test_health_needs_no_session_and_no_database(dist):
    c = TestClient(create_app(None, web_dist=dist))  # no engine at all: it cannot touch the DB or its key
    r = c.get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"} and "set-cookie" not in r.headers
