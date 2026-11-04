import json
import resource
import sys

import httpx2 as httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.ingest import create_ingest_app
from strydr.jobs import enqueue_recompute
from strydr.store import models

from conftest import KEY, count, load_fixture, workouts


def test_auth_rejects_missing_and_wrong_token(engine, token):
    from fastapi.testclient import TestClient
    c = TestClient(create_ingest_app(engine))
    assert c.post("/ingest/hae", content=b"{}").status_code == 401
    assert c.post("/ingest/hae", content=b"{}", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.post("/ingest/hae", content=b"{}", headers={"Authorization": f"Basic {token}"}).status_code == 401
    assert count(engine, models.RawPayload) == 0


def test_only_ingest_route_is_mounted(ingest):
    assert ingest.get("/api/v1/workouts").status_code == 404
    assert ingest.get("/openapi.json").status_code == 404


def test_resend_is_idempotent(engine, send):
    body = (json.dumps(load_fixture("hae-export.json"))).encode()
    send(body)
    before = (count(engine, models.Workout), count(engine, models.DailyMetric), count(engine, models.RawChunk))
    send(body)
    assert count(engine, models.RawPayload) == 1
    assert count(engine, models.Job, models.Job.status != "done") == 0
    assert (count(engine, models.Workout), count(engine, models.DailyMetric), count(engine, models.RawChunk)) == before


def test_same_workout_in_different_payload_does_not_duplicate(engine, send):
    send(load_fixture("hae-export.json"))
    n = count(engine, models.Workout)
    send(load_fixture("hae-resend.json"))
    assert count(engine, models.RawPayload) == 2
    assert count(engine, models.Workout) == n


def test_richer_copy_wins_and_poorer_does_not(engine, send):
    send(load_fixture("hae-export.json"))
    wid = next(w for w in workouts(engine).values() if w.series_count == 1 and not w.is_indoor and w.type == "walk"
               and w.avg_hr is not None).workout_id
    send(load_fixture("hae-richer.json"))
    w = workouts(engine)[wid]
    assert w.series_count == 2
    # a thinner copy arriving later (hr only) must not displace it
    thin = load_fixture("hae-richer.json")
    for wk in thin["data"]["workouts"]:
        del wk["route"]
    send(thin)
    assert workouts(engine)[wid].series_count == 2
    assert count(engine, models.SampleSeries, models.SampleSeries.workout_id == wid, models.SampleSeries.series.not_in(("splits", "step_count"))) == 2


def test_missing_fields_still_import(engine, send):
    send(load_fixture("hae-export.json"))
    ws = workouts(engine)
    assert len(ws) == 7  # cycling is raw-only
    assert {w.type for w in ws.values()} == {"run", "walk", "hike"}
    nohr = [w for w in ws.values() if w.avg_hr is None]
    assert len(nohr) == 1 and nohr[0].series_count == 1  # route only
    indoor = next(w for w in ws.values() if w.is_indoor)
    assert indoor.is_indoor and indoor.elevation_gain_m is None and indoor.temperature_c is None
    assert indoor.effort_estimated is True and indoor.series_count == 1  # HR only, no route
    assert any(w.workout_id.startswith("h:") for w in ws.values())  # AD-6 hash id for the id-less workout


def test_units_are_converted_per_value(engine, send):
    send(load_fixture("hae-export.json"))
    run = next(w for w in workouts(engine).values() if w.type == "run")
    assert run.distance_m == pytest.approx(3.2 * 25 * 60, rel=1e-3)  # mi -> m
    assert run.temperature_c == pytest.approx(5.0)  # 41 degF
    assert run.avg_speed_mps == pytest.approx(3.2, rel=1e-3)  # mislabelled "mi" avgSpeed is mi/hr -> m/s
    hike = next(w for w in workouts(engine).values() if w.type == "hike")
    assert hike.temperature_c == 4.0  # already degC
    assert hike.distance_m == pytest.approx(1.1 * 40 * 60, rel=1e-3)  # km -> m
    with Session(engine) as s:
        m = {(r.metric, r.local_date): r for r in s.execute(select(models.DailyMetric)).scalars()}
    assert m[("weight_body_mass", "2026-03-01")].units == "kg"
    assert m[("weight_body_mass", "2026-03-01")].value == pytest.approx(170 * 0.45359237)
    assert m[("walking_speed", "2026-03-01")].value == pytest.approx(3.0 * 0.44704)
    assert m[("apple_sleeping_wrist_temperature", "2026-03-01")].value == pytest.approx((96.8 - 32) / 1.8)
    assert m[("six_minute_walking_test_distance", "2026-03-01")].value == 510
    assert m[("heart_rate", "2026-03-01")].extra == {"min": 48.0, "avg": 70.0, "max": 150.0}


def test_impossible_hr_sample_is_dropped_and_flagged(engine, send):
    send(load_fixture("hae-export.json"))
    run = next(w for w in workouts(engine).values() if w.type == "run")
    assert run.quality_flags == {"hr_samples_dropped": 1}


def test_malformed_payload_is_quarantined_after_three_attempts(engine, send, worker, app_client):
    send(b'{"data": {"workouts": [ {"id": ', process=False)
    worker.run_all()
    with Session(engine) as s:
        p = s.execute(select(models.RawPayload)).scalar_one()
        job = s.execute(select(models.Job).where(models.Job.type == "process_raw")).scalar_one()
    assert (p.status, job.status, job.attempts) == ("quarantined", "failed", 3)
    assert count(engine, models.Workout) == 0
    app_client.post("/api/v1/auth/login", json={"username": "runner", "password": "correct horse battery"})
    st = app_client.get("/api/v1/sync-status").json()
    assert [q["id"] for q in st["quarantined"]] == [p.id] and st["stale"] is True


def test_recompute_coalesces(engine, send, worker):
    for i in range(3):
        send({"data": {"metrics": [], "workouts": []}, "n": i}, process=False)
    with Session(engine) as s:
        enqueue_recompute(s, "2026-03-01")
        enqueue_recompute(s, "2026-03-09")
        enqueue_recompute(s, "2026-03-05")
        s.commit()
    assert count(engine, models.Job, models.Job.type == "recompute") == 1
    worker.run_all()
    with Session(engine) as s:
        recomputes = s.execute(select(models.Job).where(models.Job.type == "recompute")).scalars().all()
    # three process_raw jobs drained, each enqueueing: still only one recompute ran for the burst
    assert len(recomputes) == 1 and recomputes[0].status == "done"
    assert recomputes[0].as_of >= "2026-03-09"


def test_db_does_not_open_without_key(engine, send, tmp_path):
    import sqlcipher3
    send(load_fixture("hae-export.json"))
    engine.dispose()
    path = str(tmp_path / "strydr.db")
    for pragma in (None, "PRAGMA key = \"x'" + "00" * 32 + "'\""):
        c = sqlcipher3.connect(path)
        if pragma:
            c.execute(pragma)
        with pytest.raises(sqlcipher3.DatabaseError):
            c.execute("select count(*) from sqlite_master").fetchall()
        c.close()
    c = sqlcipher3.connect(path)
    c.execute(f"PRAGMA key = \"x'{KEY}'\"")
    assert c.execute("select count(*) from workout").fetchone()[0] == 7


def test_no_plaintext_on_disk(engine, send, tmp_path):
    send(load_fixture("hae-export.json"))
    engine.dispose()
    files = list(tmp_path.rglob("*"))
    assert {f.name for f in files if f.is_file()} <= {"strydr.db", "strydr.db-wal", "strydr.db-shm"}
    blob = b"".join(f.read_bytes() for f in files if f.is_file())
    for marker in (b"Synthetic Watch", b"latitude", b"heartRateData"):
        assert marker not in blob


def _big_body(target_bytes: int):
    """Yield a valid HAE-shaped body of ~target_bytes without ever holding it in memory."""
    base = load_fixture("hae-export.json")["data"]["workouts"][1]  # the run, with ~1500 route points
    sample = json.dumps(base)
    per = len(sample)
    n = target_bytes // per + 1
    yield b'{"data":{"metrics":[],"workouts":['
    for i in range(n):
        w = json.loads(sample)
        w["id"] = f"BIG-{i:06d}"
        yield (b"," if i else b"") + json.dumps(w).encode()
    yield b"]}}"


@pytest.mark.slow
def test_large_payload_streams_without_loading_it_into_memory(engine, token, worker):
    import asyncio

    app = create_ingest_app(engine)
    target = 150 * 1024 * 1024

    async def post():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            async def body():
                for part in _big_body(target):
                    yield part
            return await c.post("/ingest/hae", content=body(), headers={"Authorization": f"Bearer {token}"})

    scale = 1 if sys.platform == "darwin" else 1024  # ru_maxrss: bytes on macOS, KiB on Linux
    rss = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale
    before = rss()
    assert asyncio.run(post()).status_code == 202
    worker.run_all()
    growth = rss() - before
    with Session(engine) as s:
        p = s.execute(select(models.RawPayload)).scalar_one()
    assert p.size_bytes >= target and p.status == "processed"
    assert count(engine, models.Workout) > 100
    print(f"rss growth {growth / 2**20:.0f} MiB, workouts {count(engine, models.Workout)}")
    assert growth < 120 * 1024 * 1024, f"peak RSS grew {growth / 2**20:.0f} MiB"
