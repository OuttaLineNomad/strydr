"""Runs the registered rules in topological order, passing `prior` facts (AD-8). Pure and deterministic."""
from collections.abc import Sequence

from .keys import is_valid_key
from .models import KINDS, DerivedSnapshot, InsightFact
from .registry import Rule, registered_rules
from .thresholds import Thresholds, load_thresholds


def topological_order(rules: Sequence[Rule]) -> list[Rule]:
    """Dependencies first; ties broken by rule_id so the order never depends on import order."""
    by_id = {r.rule_id: r for r in rules}
    if len(by_id) != len(rules):
        raise ValueError("duplicate rule_id")
    for r in rules:
        for dep in r.after:
            if dep not in by_id:
                raise ValueError(f"rule {r.rule_id!r} runs after unknown rule {dep!r}")
    done: list[Rule] = []
    placed: set[str] = set()
    remaining = sorted(rules, key=lambda r: r.rule_id)
    while remaining:
        ready = [r for r in remaining if all(d in placed for d in r.after)]
        if not ready:
            raise ValueError("cycle among rules: " + ", ".join(r.rule_id for r in remaining))
        nxt = ready[0]
        done.append(nxt)
        placed.add(nxt.rule_id)
        remaining.remove(nxt)
    return done


def _check(fact: InsightFact, rule: Rule, seen: set[str]) -> None:
    if fact.rule_id != rule.rule_id:
        raise ValueError(f"{rule.rule_id} emitted a fact for {fact.rule_id}")
    if not is_valid_key(fact.insight_key) or fact.insight_key != f"{fact.rule_id}:{fact.subject}:{fact.period}":
        raise ValueError(f"malformed insight_key {fact.insight_key!r}")
    if fact.kind not in KINDS:
        raise ValueError(f"unknown kind {fact.kind!r}")
    if fact.insight_key in seen:
        raise ValueError(f"duplicate insight_key {fact.insight_key!r}")


def run_rules(
    snapshot: DerivedSnapshot,
    thresholds: Thresholds | None = None,
    rules: Sequence[Rule] | None = None,
) -> list[InsightFact]:
    """Evaluate every rule against the snapshot. Facts come back rule by rule, each rule's sorted by key."""
    th = thresholds or load_thresholds()
    prior: list[InsightFact] = []
    seen: set[str] = set()
    for r in topological_order(rules if rules is not None else registered_rules()):
        facts = sorted(r.fn(snapshot, th, list(prior)), key=lambda f: f.insight_key)
        for f in facts:
            _check(f, r, seen)
            seen.add(f.insight_key)
        prior.extend(facts)
    return prior
