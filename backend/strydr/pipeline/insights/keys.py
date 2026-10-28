"""AD-6 insight_key grammar and the helpers rules use to build facts and evidence."""
import re
from datetime import date
from typing import Any

from .models import InsightFact, InsightKind

ATHLETE = "athlete"
_KEY_RE = re.compile(
    r"^(?P<rule>[a-z0-9]+(?:-[a-z0-9]+)*):"
    r"(?P<subject>athlete|run/.+|week/\d{4}-W\d{2}|route/.+):"
    r"(?P<period>\d{4}-\d{2}-\d{2}|\d{4}-W\d{2})$"
)


def week_id(d: date) -> str:
    """ISO week of the local date, `%G-W%V` (AD-6)."""
    return d.strftime("%G-W%V")


def run_subject(workout_id: str) -> str:
    return f"run/{workout_id}"


def week_subject(wid: str) -> str:
    return f"week/{wid}"


def build_key(rule_id: str, subject: str, period: str) -> str:
    return f"{rule_id}:{subject}:{period}"


def is_valid_key(key: str) -> bool:
    return _KEY_RE.match(key) is not None


def make_evidence(rule_id: str, data: dict[str, Any], note: str) -> dict[str, Any]:
    """FR-19: the rule that fired, the data it used, and a short evidence note."""
    return {"rule": rule_id, "data": data, "note": note}


def make_fact(
    rule_id: str,
    subject: str,
    period: str | date,
    kind: InsightKind,
    number: float,
    unit: str,
    evidence: dict[str, Any],
    template_id: str,
) -> InsightFact:
    p = period.isoformat() if isinstance(period, date) else period
    return InsightFact(build_key(rule_id, subject, p), rule_id, subject, p, kind, number, unit, evidence, template_id)
