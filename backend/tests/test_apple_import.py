"""Apple Health export upload, the import_apple job and per-source reparse (CAP-17, story 4)."""
import json
import zipfile
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import count, load_fixture
from test_apple_fixture import _generator
from strydr.jobs import queue, reparse
from strydr.pipeline.normalize import process
from strydr.pipeline.normalize.process import SeekableChunkReader
from strydr.store import models
from strydr.store.util import utcnow

URL = "/api/v1/import/apple"


@pytest.fixture
def login(app_client):
    r = app_client.post("/api/v1/auth/login", json={"username": "runner", "password": "correct horse battery"})
    assert r.status_code == 204
    return app_client


@pytest.fixture
def export_zip(tmp_path):
    return _generator().make_zip(tmp_path / "export.zip").read_bytes()


def upload(client, body: bytes):
    return client.post(URL, content=body, headers={"content-type": "application/zip"})


def rewrite(src: bytes, tmp_path, edit) -> bytes:
    """A copy of the zip with each member passed through edit(name, bytes) -> bytes | None (None drops it)."""
    out = tmp_path / "edited.zip"
    (tmp_path / "in.zip").write_bytes(src)
    with zipfile.ZipFile(tmp_path / "in.zip") as zi, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for name in zi.namelist():
            data = edit(name, zi.read(name))
            if isinstance(data, tuple):  # (new name, data)
                name, data = data
            if data is not None:
                zo.writestr(name, data)
    return out.read_bytes()


def test_upload_requires_a_session(app_client, export_zip):
    assert upload(app_client, export_zip).status_code == 401
    assert app_client.get(URL).status_code == 401


def test_status_is_null_before_any_upload(login):
    r = login.get(URL)
    assert r.status_code == 200 and r.json() is None


def test_happy_path_after_hae_merges_the_twins(engine, send, worker, login, export_zip):
    send(load_fixture("hae-export.json"))
    hae_ids = set(select_ids(engine))
    r = upload(login, export_zip)
    assert r.status_code == 202 and r.json()["state"] == "queued"
    assert count(engine, models.Job, models.Job.type == "import_apple", models.Job.status == "pending") == 1
    assert worker.run_one()  # only the import
    assert count(engine, models.Job, models.Job.type == "recompute", models.Job.status == "pending") == 1
    worker.run_all()
    st = login.get(URL).json()
    assert st["state"] == "done" and st["error"] is None
    assert (st["workouts"], st["merged"], st["kept_existing"], st["metrics"], st["nights"]) == (4, 2, 0, 13, 3)
    assert (st["date_from"], st["date_to"]) == ("2026-03-02", "2026-03-09")
    assert hae_ids <= set(select_ids(engine))  # the twins kept HAE's ids; Apple-only workouts were added
    assert len(select_ids(engine)) > len(hae_ids)
    with Session(engine) as s:
        p = s.execute(select(models.RawPayload).where(models.RawPayload.source == "apple")).scalar_one()
        assert p.status == "processed" and p.adapter_version == 2
    assert count(engine, models.Job, models.Job.type == "fetch_weather") == 0  # weather is off


def select_ids(engine):
    with Session(engine) as s:
        return s.execute(select(models.Workout.workout_id)).scalars().all()


def test_duplicate_upload_returns_the_existing_status(engine, worker, login, export_zip):
    first = upload(login, export_zip)
    worker.run_all()
    again = upload(login, export_zip)
    assert again.status_code == 200 and again.json()["payload_id"] == first.json()["payload_id"]
    assert again.json()["state"] == "done"
    assert count(engine, models.Job, models.Job.type == "import_apple") == 1
    assert count(engine, models.RawPayload) == 1


def test_not_a_zip_is_415_and_stores_nothing(engine, login):
    r = login.post(URL, content=b'{"data": {}}', headers={"content-type": "application/json"})
    assert r.status_code == 415
    assert count(engine, models.RawPayload) == 0 and count(engine, models.RawChunk) == 0


def test_oversize_body_is_413(engine, login, monkeypatch, export_zip):
    from strydr.api import import_api
    monkeypatch.setattr(import_api, "MAX_UPLOAD_BYTES", 100)
    assert upload(login, export_zip).status_code == 413
    assert count(engine, models.RawPayload) == 0


def test_truncated_export_fails_without_writing(engine, worker, login, export_zip, tmp_path):
    bad = rewrite(export_zip, tmp_path, lambda n, d: d[: len(d) // 2] if n.endswith("export.xml") else d)
    assert upload(login, bad).status_code == 202
    worker.run_all()
    st = login.get(URL).json()
    assert st["state"] == "failed" and st["error"] == "AdapterError"
    assert count(engine, models.Workout) == 0 and count(engine, models.DailyMetric) == 0
    with Session(engine) as s:
        assert s.execute(select(models.RawPayload.status)).scalar_one() == "quarantined"
    assert count(engine, models.Job, models.Job.type == "import_apple", models.Job.status == "done") == 1


def test_zip_without_export_xml_fails_with_a_class_name(engine, worker, login, export_zip, tmp_path):
    bad = rewrite(export_zip, tmp_path, lambda n, d: None if n.endswith("export.xml") else d)
    upload(login, bad)
    worker.run_all()
    st = login.get(URL).json()
    assert st["state"] == "failed" and st["error"] == "AdapterError"
    assert count(engine, models.Workout) == 0


def test_truncated_zip_is_a_bad_zip(engine, worker, login, export_zip):
    upload(login, export_zip[:200])
    worker.run_all()
    st = login.get(URL).json()
    assert st["state"] == "failed" and st["error"] == "BadZipFile"


def test_seekable_reader_matches_the_bytes(engine, export_zip, monkeypatch):
    with Session(engine) as s:
        p = models.RawPayload(received_at=datetime(2026, 1, 1),
                              status="accepted", size_bytes=len(export_zip), source="apple")
        s.add(p)
        s.flush()
        step = 1000
        for i in range(0, len(export_zip), step):
            s.add(models.RawChunk(payload_id=p.id, seq=i // step, data=export_zip[i:i + step]))
        s.commit()
        pid = p.id
    r = SeekableChunkReader(engine, pid)
    assert r.seekable() and r.read() == export_zip and r.read(5) == b""
    r.seek(-30, 2)
    assert r.tell() == len(export_zip) - 30 and r.read(10) == export_zip[-30:-20]
    r.seek(995)
    assert r.read(12) == export_zip[995:1007]  # across a chunk boundary


def test_reparse_replays_each_payload_through_its_own_parser(engine, send, worker, login, export_zip, monkeypatch):
    send(load_fixture("hae-export.json"))
    upload(login, export_zip)
    worker.run_all()
    before = {w.workout_id: (w.type, w.start_utc, w.payload_id) for w in _workouts(engine)}
    assert not reparse.needs_reparse(engine)  # Apple v2 and HAE v2 are both current
    monkeypatch.setattr(process, "ADAPTER_VERSION", process.ADAPTER_VERSION + 1)
    assert reparse.needs_reparse(engine) and reparse.enqueue_if_stale(engine)
    worker.run_all()
    after = {w.workout_id: (w.type, w.start_utc, w.payload_id) for w in _workouts(engine)}
    assert after == before
    with Session(engine) as s:  # the HAE payload now carries the bumped version; the Apple one is untouched
        vers = dict(s.execute(select(models.RawPayload.source, models.RawPayload.adapter_version)).all())
    assert vers == {"hae": process.ADAPTER_VERSION, "apple": 2}
    assert not reparse.needs_reparse(engine)


def _workouts(engine):
    with Session(engine) as s:
        return s.execute(select(models.Workout)).scalars().all()


def test_import_yields_to_process_raw(engine, ingest, login, export_zip):
    upload(login, export_zip)  # import_apple is queued first
    assert ingest.post("/ingest/hae", content=json.dumps(load_fixture("hae-export.json")).encode()).status_code == 202
    with Session(engine) as s:
        first = queue.claim_next(s, utcnow())
        assert first.type == "process_raw"


def test_phrase_and_weather_wait_for_an_import(engine, login, export_zip):
    upload(login, export_zip)
    with Session(engine) as s:
        queue.enqueue_phrase(s)
        queue.enqueue_weather(s)
        s.commit()
        assert queue.busy_with_pipeline(s)
        assert queue.claim_next(s, utcnow()).type == "import_apple"


def test_migration_0009_backfills_existing_payloads(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from strydr.store import migrate
    from strydr.store.engine import make_engine
    from conftest import KEY
    e = make_engine(tmp_path / "m.db", KEY)
    cfg = Config()
    cfg.set_main_option("script_location", str(migrate._DIR))
    with e.begin() as c:
        cfg.attributes["connection"] = c
        command.upgrade(cfg, "0008")
        c.execute(text("INSERT INTO raw_payload (id, received_at, status, size_bytes, source) VALUES "
                       "(1, '2026-01-01', 'processed', 1, 'hae'), (2, '2026-01-02', 'processed', 1, 'hae')"))
        c.execute(text("INSERT INTO daily_metric (metric, local_date, units, value, extra, series_count, sample_count, "
                       "adapter_version, payload_id, received_at) VALUES ('m','2026-01-01','u',1,'{}',1,1,1,1,'2026-01-01')"))
    with e.begin() as c:
        cfg.attributes["connection"] = c
        command.upgrade(cfg, "head")
    with e.connect() as c:
        rows = dict(c.execute(text("SELECT id, adapter_version FROM raw_payload")).all())
        assert rows[1] == 1 and rows[2] == 2
    with e.begin() as c:
        cfg.attributes["connection"] = c
        command.downgrade(cfg, "0008")
    e.dispose()



def _run(engine, worker, login, body):
    upload(login, body)
    worker.run_all()
    return login.get(URL).json()


def test_weather_job_is_queued_once_when_enabled(engine, worker, login, export_zip):
    from strydr.store import settings
    with Session(engine) as s:
        settings.write_weather_enabled(s, True)
        s.commit()
    upload(login, export_zip)
    worker.run_all()
    assert count(engine, models.Job, models.Job.type == "fetch_weather") == 1


def test_a_second_export_of_the_same_runs_is_already_there(engine, send, worker, login, export_zip, tmp_path):
    send(load_fixture("hae-export.json"))
    assert _run(engine, worker, login, export_zip)["state"] == "done"
    again = rewrite(export_zip, tmp_path, lambda n, d: d + b"\n" if n.endswith("export.xml") else d)  # new bytes, same runs
    st = _run(engine, worker, login, again)
    assert st["state"] == "done" and (st["workouts"], st["merged"], st["kept_existing"]) == (0, 2, 4)


def test_export_at_the_zip_root_or_nested_deeper(engine, worker, login, export_zip, tmp_path):
    root = rewrite(export_zip, tmp_path, lambda n, d: (n.removeprefix("apple_health_export/"), d))
    st = _run(engine, worker, login, root)
    assert st["state"] == "done" and st["workouts"] == 6
    with Session(engine) as s:
        assert s.execute(select(models.SampleSeries.id).where(models.SampleSeries.series == "route")).first() is not None


def test_nested_export_ignores_macosx_litter(engine, worker, login, export_zip, tmp_path):
    def edit(n, d):
        return ("Health/2026/" + n, d)
    nested = rewrite(export_zip, tmp_path, edit)
    with zipfile.ZipFile(tmp_path / "edited.zip", "a") as z:
        z.writestr("__MACOSX/Health/2026/apple_health_export/export.xml", b"junk")
    st = _run(engine, worker, login, (tmp_path / "edited.zip").read_bytes())
    assert st["state"] == "done" and st["workouts"] == 6


def test_two_export_files_are_rejected(engine, worker, login, export_zip, tmp_path):
    rewrite(export_zip, tmp_path, lambda n, d: d)
    with zipfile.ZipFile(tmp_path / "edited.zip", "a") as z:
        z.writestr("other/export.xml", b"<HealthData/>")
    st = _run(engine, worker, login, (tmp_path / "edited.zip").read_bytes())
    assert st["state"] == "failed" and st["error"] == "AdapterError"


def test_wrong_content_type_is_415(engine, login, export_zip):
    r = login.post(URL, content=export_zip, headers={"content-type": "text/plain"})
    assert r.status_code == 415 and count(engine, models.RawPayload) == 0
    r = login.post(URL, content=export_zip, headers={"content-type": "application/octet-stream"})
    assert r.status_code == 202


def test_chunked_oversize_body_is_413_and_leaves_no_rows(engine, login, monkeypatch, export_zip):
    from strydr.api import import_api
    monkeypatch.setattr(import_api, "MAX_UPLOAD_BYTES", 5000)

    def body():  # no Content-Length: the cap must hold while streaming
        for i in range(0, len(export_zip), 1000):
            yield export_zip[i:i + 1000]
    r = login.post(URL, content=body(), headers={"content-type": "application/zip"})
    assert r.status_code == 413
    assert count(engine, models.RawPayload) == 0 and count(engine, models.RawChunk) == 0


def test_reuploading_a_failed_import_queues_it_again(engine, worker, login, export_zip, tmp_path):
    bad = rewrite(export_zip, tmp_path, lambda n, d: d[: len(d) // 2] if n.endswith("export.xml") else d)
    assert _run(engine, worker, login, bad)["state"] == "failed"
    r = upload(login, bad)
    assert r.status_code == 202 and r.json()["state"] == "queued" and r.json()["error"] is None
    assert count(engine, models.Job, models.Job.type == "import_apple", models.Job.status == "pending") == 1
    with Session(engine) as s:
        assert s.execute(select(models.RawPayload.status)).scalar_one() == "accepted"
    worker.run_all()
    assert login.get(URL).json()["state"] == "failed"
    assert count(engine, models.RawPayload) == 1


@pytest.mark.parametrize("exc", [RuntimeError, EOFError])
def test_unreadable_member_is_a_failed_export_not_a_retry(engine, worker, login, export_zip, monkeypatch, exc):
    from strydr.pipeline.normalize import apple_import

    def boom(*a, **k):
        raise exc("secret")
        yield
    monkeypatch.setattr(apple_import, "apple_items", boom)
    st = _run(engine, worker, login, export_zip)
    assert st["state"] == "failed" and st["error"] == exc.__name__
    assert count(engine, models.Job, models.Job.type == "import_apple", models.Job.attempts == 1) == 1


def test_failure_mid_write_rolls_everything_back_and_ends_failed(engine, worker, login, export_zip, monkeypatch):
    from strydr.pipeline.normalize import apple_import
    real, calls = apple_import.write_workout, []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) > 2:
            raise ValueError("secret")
        return real(*a, **k)
    monkeypatch.setattr(apple_import, "write_workout", flaky)
    st = _run(engine, worker, login, export_zip)
    assert st["state"] == "failed" and st["error"] == "ValueError" and "secret" not in str(st)
    assert count(engine, models.Workout) == 0 and count(engine, models.DailyMetric) == 0
    assert count(engine, models.Job, models.Job.type == "import_apple", models.Job.status == "failed") == 1
    with Session(engine) as s:
        assert s.execute(select(models.RawPayload.status)).scalar_one() == "quarantined"
    assert count(engine, models.Job, models.Job.type == "recompute") == 0


def test_a_processed_payload_is_not_imported_twice(engine, worker, login, export_zip):
    from strydr.pipeline.normalize import apple_import
    st = _run(engine, worker, login, export_zip)
    apple_import.run(engine, st["payload_id"], "UTC")
    assert login.get(URL).json() == st


def test_apple_payload_staleness_is_judged_by_the_apple_version(engine, worker, login, export_zip, monkeypatch):
    assert _run(engine, worker, login, export_zip)["state"] == "done"
    assert not reparse.needs_reparse(engine)
    monkeypatch.setattr(process.apple, "ADAPTER_VERSION", 3)
    assert reparse.needs_reparse(engine) and reparse.enqueue_if_stale(engine)
    worker.run_all()
    assert not reparse.needs_reparse(engine)
    with Session(engine) as s:
        assert s.execute(select(models.RawPayload.adapter_version)).scalar_one() == 3
        assert s.execute(select(models.Workout.adapter_version).distinct()).scalars().all() == [3]


def test_a_processed_payload_with_no_version_is_stale(engine, worker, login, export_zip):
    _run(engine, worker, login, export_zip)
    with Session(engine) as s:
        s.execute(models.RawPayload.__table__.update().values(adapter_version=None))
        s.commit()
    assert reparse.needs_reparse(engine)
