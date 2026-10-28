"""Rule registry (AD-8): a rule is a pure `(DerivedSnapshot, Thresholds, prior) -> list[InsightFact]`
registered with a stable kebab-case `rule_id` and an `after` list of rules whose facts it reads."""
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .models import DerivedSnapshot, InsightFact
from .thresholds import Thresholds

RuleFn = Callable[[DerivedSnapshot, Thresholds, list[InsightFact]], list[InsightFact]]
_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    fn: RuleFn
    after: tuple[str, ...] = ()


_RULES: dict[str, Rule] = {}


def rule(rule_id: str, after: Sequence[str] = ()) -> Callable[[RuleFn], RuleFn]:
    """Decorator registering `fn` under `rule_id`. Ids are unique, kebab-case and never renamed."""
    if not _ID_RE.match(rule_id):
        raise ValueError(f"rule_id must be kebab-case: {rule_id!r}")

    def deco(fn: RuleFn) -> RuleFn:
        if rule_id in _RULES:
            raise ValueError(f"duplicate rule_id {rule_id!r}")
        _RULES[rule_id] = Rule(rule_id, fn, tuple(after))
        return fn

    return deco


def registered_rules() -> list[Rule]:
    """All registered rules in registration order (the rules package is imported first)."""
    from . import rules  # noqa: F401  (importing registers every rule)

    return list(_RULES.values())
