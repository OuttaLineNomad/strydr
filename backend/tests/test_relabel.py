"""`strydr relabel`: past walks corrected to runs stay runs through re-sends and reparse; later imports keep their type."""
import copy

from strydr.jobs import reparse
from strydr.relabel import relabel
from strydr.store import models

from conftest import count, load_fixture, workouts


def _types(engine) -> dict[str, str]:
    return {w.local_date: w.type for w in workouts(engine).values()}


def test_relabel_turns_past_walks_into_runs_and_queues_a_recompute(engine, send):
    send(load_fixture("hae-export.json"))
    walks = [d for d, t in _types(engine).items() if t == "walk"]
    assert len(walks) == 5
    assert relabel(engine, "walk", "run", "2026-03-05") == 3  # the indoor walk and the walks on Mar 4 and 5
    types = _types(engine)
    assert [types[d] for d in ("2026-03-02", "2026-03-04", "2026-03-05")] == ["run"] * 3
    assert [types[d] for d in ("2026-03-06", "2026-03-07")] == ["walk", "walk"]  # after the cutoff: untouched
    assert types["2026-03-08"] == "hike"
    assert count(engine, models.WorkoutTypeOverride) == 3
    assert count(engine, models.Job, models.Job.type == "recompute", models.Job.status == "pending") == 1


def test_relabel_survives_a_resent_payload_and_a_reparse(engine, send, worker):
    body = load_fixture("hae-export.json")
    send(body)
    relabel(engine, "walk", "run", "2026-03-05")
    resent = copy.deepcopy(body)  # a later copy wins AD-3 precedence and replaces the canonical rows
    send(resent)
    assert _types(engine)["2026-03-04"] == "run"
    with engine.begin() as c:  # force a reparse
        c.execute(models.Workout.__table__.update().values(adapter_version=0))
    assert reparse.enqueue_if_stale(engine)
    worker.run_all()
    types = _types(engine)
    assert types["2026-03-04"] == "run" and types["2026-03-06"] == "walk"


def test_relabel_rejects_a_no_op(engine):
    import pytest
    with pytest.raises(ValueError):
        relabel(engine, "run", "run", "2026-03-05")
