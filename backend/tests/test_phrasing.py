"""AD-9: AI phrasing is an optional, validated overlay. A fake provider stands in for the network."""
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.egress import EgressError, RunContextPayload
from strydr.jobs import Worker, queue
from strydr.pipeline.insights.templates import BANNED_TERMS
from strydr.pipeline.phrasing import SYSTEM, build_payload
from strydr.pipeline.phrasing.validate import number_tokens, validate
from strydr.store import generations, models
from strydr.store.util import utcnow

from helpers import add_run, login, recompute_now, set_hrmax

AS_OF = "2026-10-26"


class FakeProvider:
    """Insight payloads go to `reply`; run-context payloads (story 6) to `reply_run`, recorded apart in `run_calls`."""

    def __init__(self, reply=lambda payload: payload.reference, reply_run=lambda payload: "A steady run."):
        self.reply, self.reply_run, self.calls, self.run_calls = reply, reply_run, [], []

    def complete(self, payload, system, max_tokens=120):
        run = isinstance(payload, RunContextPayload)
        (self.run_calls if run else self.calls).append((payload, system, max_tokens) if run else (payload, system))
        self.max_tokens = max_tokens
        out = (self.reply_run if run else self.reply)(payload)
        if isinstance(out, Exception):
            raise out
        return out

    def __call__(self, config):  # also usable as the worker's provider_factory
        self.config = config
        return self


@pytest.fixture
def seeded(engine, app_client):
    # an easy-pace history with every run above the easy ceiling: intensity-mix fires
    for i in range(10):
        add_run(engine, f"r{i}", datetime(2026, 10, 1 + 2 * i, 7), 40, 3.0, hr=[150.0 + (i % 3)] * 40)
    set_hrmax(engine, 151)
    recompute_now(engine, AS_OF)
    login(app_client)
    return app_client


def _worker(engine, provider):
    return Worker(engine, "UTC", backoff_s=0, provider_factory=provider)


def _enable(client, **extra):
    r = client.put("/api/v1/settings/ai", json={"provider": "nvidia", "api_key": "sk-test", **extra})
    assert r.status_code == 200
    return r.json()


def _feed(client):
    return client.get("/api/v1/insights", params={"limit": 200}).json()["items"]


# ---- validation -----------------------------------------------------------------------------------------------------

NUMS = number_tokens("Your pace is 7.5% faster over 4 weeks, a 25:00 effort with 0 misses.")


@pytest.mark.parametrize("text", [
    "Great run!",  # "!"
    "Your pace is 7.5% faster because of the heat.",  # causal wording
    "That is a risk of 7.5 percent.",
    "You ran 9 km.",  # a number that is not in the fact
    "One. Two. Three.",  # more than 2 sentences
    "Your time of 25:00 burned 300.",  # banned term and unknown number
    "",
    "x" * 400,
    "Your 1500.0 s is associated with 5k.",  # the raw seconds behind a shown 25:00
    "A 25.0 minute effort.",  # the same number written differently
    "About twenty runs at 7.5%.",  # a spelled-out number the reference never had
])
def test_validate_discards_bad_text(text):
    assert validate(text, NUMS) is None


def test_signs_are_part_of_the_number():
    allowed = number_tokens("Your dew point was -3 °C.")
    assert validate("A dew point of -3 °C.", allowed) and validate("A dew point of 3 °C.", allowed) is None


def test_validate_keeps_good_text_and_normalises_whitespace():
    assert validate("Your  pace is 7.5% faster.\n It held for 4 weeks.", NUMS) == "Your pace is 7.5% faster. It held for 4 weeks."
    assert validate("A 25:00 effort.", NUMS) == "A 25:00 effort."
    assert validate("A calm, steady week with no numbers at all.", set())


def test_every_banned_term_is_rejected():
    for term in BANNED_TERMS:
        assert validate(f"You had a {term} day.", set()) is None


def test_prompt_carries_the_voice_and_health_rules():
    low = SYSTEM.lower()
    for needle in ("second person", "'you'", "associated with", "exclamation", "never state a cause", "medical", "pain", "rest"):
        assert needle in low or needle.replace("second person", "as 'you'") in low
    assert "diagnos" in low and "calorie" in low


# ---- the phrase job -------------------------------------------------------------------------------------------------

def test_ai_is_off_until_a_key_is_set(engine, seeded):
    prov = FakeProvider()
    w = _worker(engine, prov)
    with Session(engine) as s:
        queue.enqueue_phrase(s)
        s.commit()
    w.run_all()
    assert prov.calls == [] and {i["text_source"] for i in _feed(seeded)} == {"template"}
    state = seeded.get("/api/v1/settings/ai").json()
    assert state["enabled"] is False and state["has_key"] is False and "api_key" not in state


def test_valid_phrasing_is_served_and_invalid_phrasing_falls_back(engine, seeded):
    items = _feed(seeded)
    assert items
    out = _enable(seeded)
    assert out["enabled"] and "sk-test" not in str(out) and "api_key" not in out
    prov = FakeProvider(lambda p: "Honestly, " + p.reference if p.rule_id == items[0]["rule_id"] else "Wow, nice work!")
    _worker(engine, prov).run_all()
    assert prov.calls and all(system == SYSTEM for _, system in prov.calls)
    by_key = {i["insight_key"]: i for i in _feed(seeded)}
    top = by_key[items[0]["insight_key"]]
    assert top["text_source"] == "ai" and top["text"].startswith("Honestly, ")
    for k, i in by_key.items():
        if k != top["insight_key"] and i["rule_id"] != items[0]["rule_id"]:
            assert i["text_source"] == "template" and "!" not in i["text"]
    with Session(engine) as s:  # the rejected reply is cached as a miss so it is not requested again
        assert s.execute(select(models.PhrasingCache.text).where(models.PhrasingCache.text.is_(None))).first()
    n = len(prov.calls)
    with Session(engine) as s:
        queue.enqueue_phrase(s)
        s.commit()
    _worker(engine, prov).run_all()
    assert len(prov.calls) == n


def test_provider_failure_falls_back_to_templates_and_is_retried_later(engine, seeded):
    _enable(seeded)
    prov = FakeProvider(lambda p: EgressError("ReadTimeout"))
    _worker(engine, prov).run_all()
    assert len(prov.calls) == 3  # gives up after consecutive failures instead of hammering the provider
    assert {i["text_source"] for i in _feed(seeded)} == {"template"}
    with Session(engine) as s:
        assert s.execute(select(models.PhrasingCache)).first() is None
    with Session(engine) as s:
        queue.enqueue_phrase(s)
        s.commit()
    ok = FakeProvider()
    _worker(engine, ok).run_all()
    assert "ai" in {i["text_source"] for i in _feed(seeded)}


def test_phrasing_is_stale_after_the_units_change(engine, seeded, worker):
    _enable(seeded)
    _worker(engine, FakeProvider()).run_all()
    assert "ai" in {i["text_source"] for i in _feed(seeded)}
    profile = seeded.get("/api/v1/profile").json()["settings"]
    seeded.put("/api/v1/profile", json={**profile, "units": "imperial"})
    recompute_now(engine, AS_OF)
    assert {i["text_source"] for i in _feed(seeded)} == {"template"}  # the hash covers the units (AD-9)
    with Session(engine) as s:
        assert s.execute(select(models.PhrasingCache)).first() is not None  # the cache itself is never wiped


def test_phrase_waits_for_recompute_and_process_raw(engine):
    with Session(engine) as s:
        queue.enqueue_phrase(s)
        s.commit()
        queue.enqueue_recompute(s, AS_OF)
        s.commit()
    with Session(engine) as s:
        assert queue.claim_next(s, utcnow()).type == "recompute"
    with Session(engine) as s:
        assert queue.claim_next(s, utcnow()) is None  # the recompute is still running: phrase keeps waiting
        s.execute(models.Job.__table__.update().where(models.Job.type == "recompute").values(status="done"))
        s.commit()
        assert queue.claim_next(s, utcnow()).type == "phrase"


def test_phrasing_cache_is_persistent_tier():
    assert models.PhrasingCache not in models.ANALYTIC


def test_cache_survives_recompute_and_generation_deletion(engine, seeded):
    with Session(engine) as s:
        s.add(models.PhrasingCache(insight_key="k", fact_hash="h", text="t", created_at=utcnow()))
        s.commit()
    recompute_now(engine, AS_OF)
    generations.purge_stale(engine)
    with Session(engine) as s:
        assert s.get(models.PhrasingCache, ("k", "h")).text == "t"


def test_payload_built_from_an_insight_carries_no_dates_or_names(engine, seeded):
    with Session(engine) as s:
        row = s.execute(select(models.InsightFact)).scalars().first()
        payload = build_payload(row, "km", datetime(2026, 10, 26).date())
    dumped = payload.model_dump_json()
    assert "2026-" not in dumped and "r0" not in payload.numbers
    assert payload.when in ("today", "yesterday") or payload.when.endswith("days ago")
