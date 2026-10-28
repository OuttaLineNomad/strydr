"""Phrasing stage (AD-9): an optional AI rewording of an insight, cached in the persistent tier.

The `phrase` job asks the provider (through egress only) to reword each fresh insight, validates the reply and caches
it keyed by `(insight_key, phrase_hash)`. Anything that fails leaves the template wording in place (FR-29).
"""
import logging
from collections.abc import Callable
from datetime import date, timedelta

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from strydr.egress import TERMS, EgressError, EgressPayload, Provider, ProviderConfig, resolve
from strydr.pipeline.insights.templates import BANNED_TERMS
from strydr.pipeline.phrasing.validate import number_tokens, validate
from strydr.store import models, settings
from strydr.store.util import utcnow

log = logging.getLogger("strydr.phrasing")
MAX_CALLS = 40  # per job, newest insights first
MAX_RUN_CALLS = 20  # run summaries per job, newest runs first
RECENT_DAYS = 60
MAX_FAILURES = 3  # consecutive provider failures before the job gives up until the next recompute

SYSTEM = (
    "You reword one running insight for a runner. Voice: a calm, warm coach speaking to the runner as 'you'. "
    "Write one or two short plain sentences and nothing else, in fresh words rather than a copy of the reference. "
    "Keep every number exactly as it appears in the reference sentence, written the same way (14:04 stays 14:04), "
    "with the same units, and add no other numbers, even ones from the JSON. "
    "Where the reference links two things, say they are 'associated with' each other and never state a cause; add no link the "
    "reference does not make. "
    "Give no medical advice, no diagnosis and no injury, risk, calorie or weight talk. "
    "Never tell the runner to push through pain, skip rest or train harder. "
    "Do not use exclamation marks. Never use these words or phrases: " + ", ".join(t for t in BANNED_TERMS if t != "!") + ". "
    "Input is JSON describing the insight; its 'reference' field is the exact wording to rephrase."
)


def _when(local_date: str, as_of: date) -> str:
    days = (as_of - date.fromisoformat(local_date)).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago" if days <= 365 else "earlier"


def _flatten(value, path: str, out: dict[str, float]) -> None:
    if isinstance(value, bool) or len(out) >= 60:
        return
    if isinstance(value, (int, float)):
        out[path] = float(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            _flatten(v, f"{path}.{k}" if path else str(k), out)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _flatten(v, f"{path}[{i}]", out)


def _terms(value, out: list[str]) -> None:
    if isinstance(value, str) and value in TERMS and value not in out:
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _terms(v, out)
    elif isinstance(value, list):
        for v in value:
            _terms(v, out)


def build_payload(row: models.InsightFact, units: str, as_of: date) -> EgressPayload:
    """Derived values only. Raises ValidationError if anything falls outside the allow-list."""
    data = (row.evidence or {}).get("data", {})
    numbers: dict[str, float] = {}
    _flatten(data, "", numbers)
    numbers = {k.lstrip(".").replace(" ", "_").lower(): v for k, v in numbers.items()}
    terms: list[str] = []
    _terms(data, terms)
    return EgressPayload(
        rule_id=row.rule_id, template_id=row.template_id, kind=row.kind, number=row.number or 0.0,
        unit=row.unit or "", units=units, when=_when(row.local_date, as_of), numbers=numbers, terms=terms[:12],
        reference=row.text_template)


def allowed_numbers(payload: EgressPayload) -> set[str]:
    """Only the numbers the runner already sees, as written. The payload's other numbers are context, not copy."""
    return number_tokens(payload.reference)


def run(engine: Engine, default_tz: str, provider_factory: Callable[[ProviderConfig], Provider],
        should_stop: Callable[[], bool]) -> dict[str, int]:
    """Phrase the newest uncached insights of the current generation. No-op while AI is off (FR-28)."""
    counts = {"phrased": 0, "rejected": 0, "failed": 0, "summarised": 0, "summaries_rejected": 0}
    with Session(engine) as s:
        ai = settings.read_ai(s)
        if not ai.enabled:
            return counts
        cfg = settings.read(s, default_tz)
        gen = s.execute(select(models.Generation).join(
            models.CurrentGeneration, models.CurrentGeneration.generation_id == models.Generation.id)).scalar_one_or_none()
        if gen is None:
            return counts
        as_of = date.fromisoformat(gen.as_of)
        since = (as_of - timedelta(days=RECENT_DAYS)).isoformat()
        cached = set(s.execute(select(models.PhrasingCache.insight_key, models.PhrasingCache.fact_hash)).all())
        rows = [r for r in s.execute(select(models.InsightFact).where(
            models.InsightFact.generation_id == gen.id, models.InsightFact.local_date >= since)
            .order_by(models.InsightFact.local_date.desc(), models.InsightFact.insight_key)).scalars()
            if (r.insight_key, r.phrase_hash) not in cached][:MAX_CALLS]
        s.expunge_all()
    provider = provider_factory(resolve(ai.provider, ai.base_url, ai.model, ai.api_key))
    units = "mi" if cfg.units == "imperial" else "km"
    failures = 0
    for row in rows:
        if should_stop():  # AD-5: yield to recompute / process_raw
            break
        try:
            payload = build_payload(row, units, as_of)
            raw = provider.complete(payload, SYSTEM)
        except EgressError as e:
            counts["failed"] += 1
            failures += 1
            log.warning("phrasing call failed: %s", e)
            if failures >= MAX_FAILURES:
                return counts
            continue
        except ValueError as e:  # a payload outside the allow-list is never sent
            counts["rejected"] += 1
            log.warning("payload refused: %s", type(e).__name__)
            continue
        failures = 0
        text = validate(raw, allowed_numbers(payload))
        counts["phrased" if text else "rejected"] += 1
        with Session(engine) as s:
            s.merge(models.PhrasingCache(insight_key=row.insight_key, fact_hash=row.phrase_hash, text=text,
                                         created_at=utcnow()))
            s.commit()
    if not should_stop():
        from strydr.pipeline.phrasing.summary import summarize_runs  # after the insights; imports this module
        with Session(engine) as s:
            summarize_runs(s, provider, units, as_of, should_stop, failures, counts)
    return counts
