"""Insight templates and `render` (AD-8). The recompute stores `render(fact, units)` as `text_template`."""
import hashlib
import json

from ..models import InsightFact
from ._format import Template, Units, base_fields
from .definitions import TEMPLATES
from .routes import ROUTE_TEMPLATES

# Bump when any template wording changes: part of the phrasing-cache key (AD-9).
TEMPLATE_VERSION = "3"

# Health-wording guardrails (FR-21/21a). Case-insensitive substring match; the lint test enforces them.
BANNED_TERMS = (
    "!", "cause", "because", "due to", "leads to", "results in", "diagnos", "disease", "injur", "risk", "danger",
    "overtrain", "calorie", "kcal", "weight", "burn", "illness", "you should", "you must",
)

__all__ = ["BANNED_TERMS", "ROUTE_TEMPLATES", "TEMPLATES", "TEMPLATE_VERSION", "Template", "Units", "fact_hash", "render"]


def render(fact: InsightFact, units: Units) -> str:
    """The fact as one sentence in the runner's units (km or mi). Deterministic."""
    try:
        t = TEMPLATES.get(fact.template_id) or ROUTE_TEMPLATES[fact.template_id]
    except KeyError:
        raise KeyError(f"no template {fact.template_id!r}") from None
    fields = base_fields(fact, units)
    if t.extra is not None:
        fields.update(t.extra(fact, units))
    return t.text.format(**fields)


def fact_hash(fact: InsightFact, units: Units) -> str:
    """The phrasing-cache key part (AD-9): sha256 of the fact, the runner's units and the template version."""
    body = json.dumps(
        [fact.insight_key, fact.rule_id, fact.kind, fact.number, fact.unit, fact.evidence.get("data"), fact.template_id,
         units, TEMPLATE_VERSION], sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()
