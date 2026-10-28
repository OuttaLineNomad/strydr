"""AI run summary (CAP-16): two or three sentences on how a run went, written after recompute by the `phrase` job.

The reply is validated against the run context's own numbers and cached by context hash. The API never calls the
provider: it serves the cached text while the hash still matches, else the template summary.
"""
import hashlib
import json
import logging
from collections.abc import Callable
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from strydr.egress import EgressError, Provider, RunContextPayload
from strydr.pipeline.insights.templates import BANNED_TERMS
from strydr.pipeline.phrasing import MAX_FAILURES, MAX_RUN_CALLS, RECENT_DAYS
from strydr.pipeline.phrasing.run_context import allowed_numbers_run, build_run_context
from strydr.pipeline.phrasing.validate import validate
from strydr.store import models, settings
from strydr.store.generations import in_current
from strydr.store.util import utcnow

log = logging.getLogger("strydr.phrasing")
SUMMARY_VERSION = "2"
MAX_TOKENS = 220
MAX_SENTENCES = 3
MAX_CHARS = 450

SYSTEM_RUN = (
    "You summarise one run for a runner. Voice: a calm, warm coach speaking to the runner as 'you'. "
    "Write two or three short plain sentences and nothing else. "
    "Link the pace or effort to at most two context factors from the JSON (such as the weather, sleep, training load or "
    "the comparison with similar runs), and say they are 'associated with' each other, never that one caused the other. "
    "Use only numbers that appear in the JSON, written exactly the same way (14:04 stays 14:04) with the same units, "
    "and add no other numbers. "
    "Give no medical advice, no diagnosis and no injury, risk, calorie or weight talk. "
    "Never tell the runner to push through pain, skip rest or train harder. "
    "Do not say when the run happened: no 'today', 'yesterday' or 'days ago'. "
    "Do not use exclamation marks. Never use these words or phrases: " + ", ".join(t for t in BANNED_TERMS if t != "!") + ". "
    "Input is JSON describing the run."
)


def context_hash(payload: RunContextPayload, units: str) -> str:
    """Hashes the context without its relative `when`, so a summary does not go stale as days pass."""
    body = payload.model_dump(mode="json")
    body["run"].pop("when", None)
    return hashlib.sha256((json.dumps(body, sort_keys=True) + units + SUMMARY_VERSION).encode()).hexdigest()


def run_context_hash(s: Session, workout_id: str, units: str, as_of: date) -> tuple[RunContextPayload, str] | None:
    payload = build_run_context(s, workout_id, units, as_of)
    return None if payload is None else (payload, context_hash(payload, units))


def template_summary(s: Session, workout_id: str) -> str | None:
    """The run's fired insights in feed order, joined; None when none fired."""
    texts = s.execute(select(models.InsightFact.text_template).where(
        in_current(models.InsightFact), models.InsightFact.subject == f"run/{workout_id}")
        .order_by(models.InsightFact.local_date.desc(), models.InsightFact.insight_key)).scalars().all()
    return " ".join(texts) or None


def summarize_runs(s: Session, provider: Provider, units: str, as_of: date, should_stop: Callable[[], bool],
                   failures: int, counts: dict[str, int]) -> int:
    """Summarise recent runs whose context has no cache row, newest first. Returns the consecutive failure count."""
    since = (as_of - timedelta(days=RECENT_DAYS)).isoformat()
    ids = s.execute(select(models.Workout.workout_id).where(models.Workout.type == "run", models.Workout.local_date >= since)
                    .order_by(models.Workout.start_utc.desc(), models.Workout.workout_id)).scalars().all()
    cached = set(s.execute(select(models.RunSummaryCache.workout_id, models.RunSummaryCache.context_hash)).all())
    todo: list[tuple[str, RunContextPayload, str]] = []
    for wid in ids:
        if len(todo) >= MAX_RUN_CALLS:
            break
        try:
            built = run_context_hash(s, wid, units, as_of)
        except ValueError as e:  # a context outside the payload's allow-list is never sent
            counts["summaries_rejected"] += 1
            log.warning("run context refused: %s", type(e).__name__)
            continue
        if built is not None and (wid, built[1]) not in cached:
            todo.append((wid, *built))
    for wid, payload, h in todo:
        if should_stop():
            break
        try:
            raw = provider.complete(payload, SYSTEM_RUN, max_tokens=MAX_TOKENS)
        except EgressError as e:
            counts["failed"] += 1
            failures += 1
            log.warning("run summary call failed: %s", e)
            if failures >= MAX_FAILURES:
                break
            continue
        failures = 0
        text = validate(raw, allowed_numbers_run(payload), max_sentences=MAX_SENTENCES, max_chars=MAX_CHARS)
        counts["summarised" if text else "summaries_rejected"] += 1
        s.execute(delete(models.RunSummaryCache).where(
            models.RunSummaryCache.workout_id == wid, models.RunSummaryCache.context_hash != h))
        s.merge(models.RunSummaryCache(workout_id=wid, context_hash=h, text=text, created_at=utcnow()))
        s.commit()
    return failures


def serve(s: Session, workout_id: str, default_tz: str) -> tuple[str, str, str | None] | None:
    """What the run page shows: (text, "ai"|"template", context_hash), or None when there is nothing to say.

    The cached AI text is served only while AI is on and its hash matches the run's current context; otherwise the
    template summary. Reads only: no provider call.
    """
    gen = s.execute(select(models.Generation).join(
        models.CurrentGeneration, models.CurrentGeneration.generation_id == models.Generation.id)).scalar_one_or_none()
    w_type = s.execute(select(models.Workout.type).where(models.Workout.workout_id == workout_id)).scalar_one_or_none()
    if gen is None or w_type is None:
        return None
    h = None
    if w_type == "run":
        units = "mi" if settings.read(s, default_tz).units == "imperial" else "km"
        try:
            built = run_context_hash(s, workout_id, units, date.fromisoformat(gen.as_of))
        except ValueError:  # no usable context: fall back to the template
            built = None
        h = built[1] if built else None
        if h and settings.read_ai(s).enabled:
            text = s.execute(select(models.RunSummaryCache.text).where(
                models.RunSummaryCache.workout_id == workout_id, models.RunSummaryCache.context_hash == h)).scalar_one_or_none()
            if text:
                return text, "ai", h
    text = template_summary(s, workout_id)
    return (text, "template", h) if text else None
