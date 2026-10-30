"""Template plumbing: the Template type and number/distance formatters (SI in, runner's units out)."""
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from ..models import M_PER_UNIT, InsightFact

Units = Literal["km", "mi"]


def num(x: float) -> str:
    """One decimal at most, no trailing zero: 7.0 -> '7', 7.25 -> '7.2'."""
    s = f"{x:.1f}"
    return s[:-2] if s.endswith(".0") else s


def dist(m: float, units: Units) -> str:
    return f"{num(m / M_PER_UNIT["mi"])} mi" if units == "mi" else f"{num(m / M_PER_UNIT["km"])} km"


def clock(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def carry_text(kg: float, units: Units) -> str:
    """The carry as the web's `formatWeightValue` shows it: whole pounds or kilograms to one decimal, never 0. "25 lb"."""
    step = 1 if units == "mi" else 0.1
    v = kg * 2.2046226218 if units == "mi" else kg
    r = math.floor(v / step + 0.5) * step
    r = step if v > 0 and r < step else r
    return f"{num(r)} {'lb' if units == 'mi' else 'kg'}"


EXTRA = Callable[[InsightFact, Units], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class Template:
    """One sentence, second person, one headline number `{n}`. `extra` supplies further placeholders."""

    template_id: str
    rule_id: str
    text: str
    extra: EXTRA | None = None


def base_fields(fact: InsightFact, units: Units) -> dict[str, Any]:
    n = fact.number
    if fact.unit == "s":
        shown = clock(n)
    elif fact.unit == "m":
        shown = dist(n, units)
    else:
        shown = num(n)
    return {"n": shown, "n_abs": num(abs(n)), "n_signed": f"{n:+.1f}".replace("+0.0", "0").replace("-0.0", "0"), "d": fact.evidence["data"]}
