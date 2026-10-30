"""Story 6: the AI run summary is written by the phrase job, validated, cached by context hash and served by the API."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.egress import EgressError
from strydr.jobs import queue
from strydr.pipeline.phrasing.summary import SYSTEM_RUN
from strydr.pipeline.phrasing.run_context import allowed_numbers_run, build_run_context
from strydr.store import models

from helpers import add_run, login, recompute_now
from test_phrasing import AS_OF, FakeProvider, _enable, _feed, _worker, seeded  # noqa: F401  (seeded is a fixture)


def _add_facts(engine):
    """Two fired insights for r9 (the seeded history fires none per run)."""
    with Session(engine) as s:
        gen = s.execute(select(models.CurrentGeneration.generation_id)).scalar_one()
        for i in range(2):
            s.add(models.InsightFact(
                generation_id=gen, insight_key=f"effort-by-sleep:run/r9:2026-10-1{i}", rule_id="effort-by-sleep",
                subject="run/r9", period="2026-10-19", kind="observation", number=1.0, unit="%", evidence={},
                template_id="t", text_template=f"Your effort was {10 + i}% higher on 4 hours of sleep.", phrase_hash="h",
                local_date="2026-10-19", week_id="2026-W43"))
        s.commit()


@pytest.fixture
def facts(engine, seeded):
    _add_facts(engine)


def _detail(client, wid):
    r = client.get(f"/api/v1/workouts/{wid}")
    assert r.status_code == 200
    return r.json()


def _cache(engine):
    with Session(engine) as s:
        return s.execute(select(models.RunSummaryCache)).scalars().all()


def _rerun(engine, provider):
    with Session(engine) as s:
        queue.enqueue_phrase(s)
        s.commit()
    _worker(engine, provider).run_all()


def _first_number_reply(p):
    """A reply that uses a number straight from the context."""
    return f"Your pace of {p.run['avg_pace']} is associated with a steady week."


def test_valid_reply_is_cached_and_served_as_ai(engine, seeded):
    _enable(seeded)
    prov = FakeProvider(reply_run=_first_number_reply)
    _worker(engine, prov).run_all()
    assert prov.run_calls and all(s == SYSTEM_RUN and mt == 220 for _, s, mt in prov.run_calls)
    d = _detail(seeded, "r9")["summary"]
    assert d["source"] == "ai" and d["text"].startswith("Your pace of ") and d["key"] == "run-summary/r9" and d["thumb"] is None
    assert any(r.workout_id == "r9" and r.text for r in _cache(engine))


def test_insight_calls_keep_their_limits(engine, seeded):
    _enable(seeded)
    seen = []

    class Spy(FakeProvider):
        def complete(self, payload, system, max_tokens=120):
            seen.append((type(payload).__name__, max_tokens))
            return super().complete(payload, system, max_tokens)

    _worker(engine, Spy(reply_run=_first_number_reply)).run_all()
    assert {mt for n, mt in seen if n == "EgressPayload"} == {120}
    assert {mt for n, mt in seen if n == "RunContextPayload"} == {220}


@pytest.mark.parametrize("reply", [
    "Your pace was associated with 99 degrees.",  # a number not in the context
    "One. Two. Three. Four.",  # four sentences
    "Your run was a great burn.",  # a banned term
    "Your run was associated with carrying a heavy pack.",  # a carry on a run with none logged
])
def test_invalid_reply_is_cached_as_null_and_not_retried(engine, seeded, facts, reply):
    _enable(seeded)
    prov = FakeProvider(reply_run=lambda p: reply)
    _worker(engine, prov).run_all()
    rows = _cache(engine)
    assert rows and all(r.text is None for r in rows)
    s = _detail(seeded, "r9")["summary"]
    assert s["source"] == "template" and s["text"] == " ".join(_feed_texts(seeded, "r9"))
    n = len(prov.run_calls)
    _rerun(engine, prov)
    assert len(prov.run_calls) == n


def test_the_prompt_says_training_load_is_not_carried_mass():
    assert "never carried mass" in SYSTEM_RUN and "Without a 'carry' value, never say the runner carried anything" in SYSTEM_RUN


def test_three_sentences_pass_where_insights_would_not(engine, seeded):
    _enable(seeded)
    _worker(engine, FakeProvider(reply_run=lambda p: "You ran steady. The week was calm. It felt even.")).run_all()
    assert _detail(seeded, "r9")["summary"]["source"] == "ai"


def test_changed_context_gets_a_new_summary_and_the_stale_row_is_ignored(engine, seeded, facts):
    _enable(seeded)
    prov = FakeProvider(reply_run=_first_number_reply)
    _worker(engine, prov).run_all()
    before = {(r.workout_id, r.context_hash) for r in _cache(engine)}
    assert _detail(seeded, "r9")["summary"]["source"] == "ai"
    assert seeded.put("/api/v1/workouts/r9/note", json={"text": None, "rpe": 9}).status_code == 200
    # before the next phrase job: the stale row must not be served (the recompute is run without the phrase job)
    recompute_now(engine, AS_OF)
    _add_facts(engine)
    stale = _detail(seeded, "r9")["summary"]
    assert stale["source"] == "template" and stale["text"] == " ".join(_feed_texts(seeded, "r9"))
    _worker(engine, FakeProvider(reply_run=lambda p: "Your RPE was associated with a hard day.")).run_all()
    after = {(r.workout_id, r.context_hash) for r in _cache(engine)}
    assert len({h for w, h in after if w == "r9"}) == 1 and not ({h for w, h in before if w == "r9"} & {h for w, h in after if w == "r9"})
    assert _detail(seeded, "r9")["summary"]["text"] == "Your RPE was associated with a hard day."


def test_ai_off_makes_no_call_and_serves_the_template(engine, seeded, facts):
    prov = FakeProvider()
    _rerun(engine, prov)
    assert prov.run_calls == [] and _cache(engine) == []
    s = _detail(seeded, "r9")["summary"]
    facts = _feed_texts(seeded, "r9")
    assert s["source"] == "template" and s["text"] == " ".join(facts) and facts


def _feed_texts(client, wid):
    items = client.get("/api/v1/insights", params={"run": wid, "limit": 200}).json()["items"]
    return [i["text"] for i in items]


def test_no_insights_and_no_ai_is_null(engine, app_client):
    add_run(engine, "solo", datetime(2026, 10, 20, 7), 40, 3.0, hr=[150.0] * 40)
    recompute_now(engine, AS_OF)
    login(app_client)
    assert _feed_texts(app_client, "solo") == []
    assert _detail(app_client, "solo")["summary"] is None


def test_provider_failing_stops_after_three_and_caches_nothing(engine, seeded):
    _enable(seeded)
    prov = FakeProvider(reply_run=lambda p: EgressError("ReadTimeout"))
    _worker(engine, prov).run_all()
    assert len(prov.run_calls) == 3 and _cache(engine) == []


def test_cap_is_twenty_newest_first(engine, app_client):
    for i in range(25):
        add_run(engine, f"c{i:02d}", datetime(2026, 9, 26) + timedelta(days=i), 30, 3.0, hr=[150.0] * 30)
    recompute_now(engine, AS_OF)
    login(app_client)
    _enable(app_client)
    prov = FakeProvider(reply_run=_first_number_reply)
    _worker(engine, prov).run_all()
    assert len(prov.run_calls) == 20
    assert {r.workout_id for r in _cache(engine)} == {f"c{i:02d}" for i in range(5, 25)}


def test_walks_are_not_summarised(engine, app_client):
    add_run(engine, "w1", datetime(2026, 10, 20, 7), 40, 1.5, hr=[110.0] * 40, type_="walk")
    recompute_now(engine, AS_OF)
    login(app_client)
    _enable(app_client)
    prov = FakeProvider(reply_run=_first_number_reply)
    _worker(engine, prov).run_all()
    assert prov.run_calls == [] and _cache(engine) == []


def test_thumbs_on_the_summary(engine, seeded, facts):
    k = "/api/v1/insights/run-summary/r9/feedback"
    r = seeded.put(k, json={"thumb": "up"})
    assert r.status_code == 200 and r.json()["snapshot"]["source"] == "template"
    assert set(r.json()["snapshot"]) >= {"context_hash", "text", "source"}
    with Session(engine) as s:
        assert s.get(models.InsightFeedback, "run-summary/r9").thumb == "up"
    assert _detail(seeded, "r9")["summary"]["thumb"] == "up"
    assert seeded.delete(k).status_code == 204
    assert seeded.delete(k).status_code == 204  # toggling off twice is not a 404
    with Session(engine) as s:
        assert s.get(models.InsightFeedback, "run-summary/r9") is None
    assert seeded.put("/api/v1/insights/run-summary/nope/feedback", json={"thumb": "up"}).status_code == 404


def test_cache_is_persistent_tier_and_context_numbers_cover_the_reply(engine, seeded):
    assert models.RunSummaryCache not in models.ANALYTIC
    with Session(engine) as s:
        p = build_run_context(s, "r9", "km", datetime(2026, 10, 26).date())
    assert p.run["avg_pace"] and allowed_numbers_run(p)


def test_migration_0007_creates_and_downgrade_removes_the_table(engine):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from strydr.store import migrate

    cfg = Config()
    cfg.set_main_option("script_location", str(migrate._DIR))
    assert "run_summary_cache" in inspect(engine).get_table_names()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0006")
    assert "run_summary_cache" not in inspect(engine).get_table_names()


def test_ai_off_hides_a_cached_ai_summary(engine, seeded, facts):
    _enable(seeded)
    _worker(engine, FakeProvider(reply_run=_first_number_reply)).run_all()
    assert _detail(seeded, "r9")["summary"]["source"] == "ai"
    assert seeded.put("/api/v1/settings/ai", json={"api_key": ""}).status_code == 200
    assert _detail(seeded, "r9")["summary"]["source"] != "ai"


def test_insight_failures_stop_the_job_before_any_summary(engine, seeded):
    _enable(seeded)
    prov = FakeProvider(reply=lambda p: EgressError("ReadTimeout"))
    _worker(engine, prov).run_all()
    assert len(prov.calls) == 3 and prov.run_calls == []


def test_failures_are_shared_between_insights_and_summaries(engine, seeded):
    _enable(seeded)
    total, n = len(_feed(seeded)), {"i": 0}

    def flaky(p):  # the last two insight calls fail
        n["i"] += 1
        return EgressError("ReadTimeout") if n["i"] > total - 2 else "Fine."

    prov = FakeProvider(reply=flaky, reply_run=lambda p: EgressError("ReadTimeout"))
    _worker(engine, prov).run_all()
    # the third consecutive failure (the first summary call) ends the job; no further summary is attempted
    assert len(prov.run_calls) == 1
    assert _cache(engine) == []


def test_hash_ignores_when_and_changes_with_the_context(engine, seeded):
    from datetime import date

    from strydr.pipeline.phrasing.summary import context_hash

    with Session(engine) as s:
        a = build_run_context(s, "r9", "km", date(2026, 10, 26))
        b = build_run_context(s, "r9", "km", date(2026, 10, 29))
    assert a.run["when"] != b.run["when"] and context_hash(a, "km") == context_hash(b, "km")
    assert context_hash(a, "km") != context_hash(a, "mi")


def test_thumb_resets_when_the_context_changes(engine, seeded, facts):
    k = "/api/v1/insights/run-summary/r9/feedback"
    assert seeded.put(k, json={"thumb": "up"}).status_code == 200
    assert _detail(seeded, "r9")["summary"]["thumb"] == "up"
    seeded.put("/api/v1/workouts/r9/note", json={"text": None, "rpe": 9})
    recompute_now(engine, AS_OF)
    _add_facts(engine)
    assert _detail(seeded, "r9")["summary"]["thumb"] is None


def test_old_hashes_are_pruned(engine, seeded, facts):
    _enable(seeded)
    _worker(engine, FakeProvider(reply_run=_first_number_reply)).run_all()
    seeded.put("/api/v1/workouts/r9/note", json={"text": None, "rpe": 9})
    _worker(engine, FakeProvider(reply_run=_first_number_reply)).run_all()
    assert len([r for r in _cache(engine) if r.workout_id == "r9"]) == 1
