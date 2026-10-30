"""The only shape that may leave the server (AD-10, FR-27): an allow-list of derived values.

No coordinates, timestamps, names or free text. Strings are limited to closed vocabularies or tight patterns, and
`extra="forbid"` rejects any field not listed here.
"""
import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

# Words from the insight evidence that may be sent verbatim.
Term = Literal[
    "Building", "Holding", "Easing", "Overreaching", "km", "mi", "1k", "1mi", "5k", "10k", "half", "marathon",
    "ceiling", "pace-and-hr", "best-effort", "longest-run", "milestone",
    "ideal", "warm", "hot", "oppressive", "cold", "freezing", "short", "restless", "good", "fair",
]
TERMS = frozenset(Term.__args__)

_KEBAB = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_KEY = re.compile(r"[a-z0-9_.\[\]]{1,48}")


class EgressPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(pattern=_KEBAB, max_length=64)
    template_id: str = Field(pattern=_KEBAB, max_length=64)
    kind: Literal["observation", "attaboy", "check-reading"]
    number: float
    unit: str = Field(pattern=r"^[a-z%/]{0,8}$")
    units: Literal["km", "mi"]
    when: str = Field(pattern=r"^(today|yesterday|earlier|\d{1,3} days ago)$")  # relative, never an exact date
    numbers: dict[str, float] = Field(default_factory=dict, max_length=60)
    terms: list[Term] = Field(default_factory=list, max_length=12)
    # The template wording of this same fact: derived numbers and fixed words only.
    reference: str = Field(pattern=r"^[A-Za-z0-9 .,:%/()'+°-]{1,400}$")

    @field_validator("numbers")
    @classmethod
    def _keys(cls, v: dict[str, float]) -> dict[str, float]:
        if any(not _KEY.fullmatch(k) for k in v):
            raise ValueError("numbers keys must be plain identifiers")
        return v


# --- One run (ai-run-context.md, CAP-16) ---------------------------------------------------------------------------

CONTEXT_VALUE = r"^[A-Za-z0-9 .,:%/()'+°\u2212-]{1,48}$"  # preformatted, in the runner's units: "14:04 /mi", "84°F"
_CONTEXT_VALUE = re.compile(CONTEXT_VALUE)
_SENTENCE = re.compile(r"^[A-Za-z0-9 .,:%/()'+°\u2212-]{1,400}$")

RunKey = Literal["type", "when", "time_band", "distance", "active_time", "avg_pace", "avg_hr", "max_hr", "cadence",
                 "elevation_gain", "effort_score", "rpe", "carry"]
SplitKey = Literal["split", "distance", "pace", "gap_pace", "hr", "elevation_change"]
TerrainKey = Literal["gap_pace", "relief", "relief_per_distance", "hilly"]
ConditionsKey = Literal["temperature", "feels_like", "humidity", "dew_point", "wind", "rain", "cloud",
                        "heat_adjustment", "band"]
SleepKey = Literal["hours", "deep", "core", "rem", "awake", "efficiency", "usual_sleep", "vs_usual", "quality",
                   "morning_rhr", "usual_rhr", "rhr_vs_usual", "morning_hrv", "usual_hrv", "hrv_vs_usual"]
TrainingKey = Literal["run_load", "load_7_days", "fitness", "fatigue", "form", "state", "days_since_last_run",
                      "runs_this_week"]
ComparisonKey = Literal["similar_runs", "pace", "usual_pace", "hr", "usual_hr", "beats_per_km", "usual_beats_per_km"]
# Word-valued keys, each with its own closed set of values (group, key) -> full-match pattern.
_WORD_VALUES = {
    ("run", "type"): r"run|walk|hike",
    ("run", "when"): r"today|yesterday|earlier|\d{1,3} days ago",
    ("run", "time_band"): r"morning|midday|evening",
    ("terrain", "hilly"): r"yes|no",
    ("conditions", "rain"): r"Dry|\d{1,3}\.\d mm/h",
    ("conditions", "band"): r"ideal|warm|hot|oppressive|cold|freezing",
    ("sleep", "quality"): r"short|restless|good|fair",
    ("sleep", "vs_usual"): r"about usual|[+\u2212]\d+h \d{2}m|[+\u2212]\d+m",
    ("training", "state"): r"Building|Holding|Easing|Overreaching",
}
WORD_VALUES = {k: re.compile(v) for k, v in _WORD_VALUES.items()}

# Shapes the character class alone would let through: an absolute date, a clock time with am/pm, a coordinate.
_MONTH = (r"(?:january|february|march|april|may|june|july|august|september|october|november|december|"
          r"jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)")
_UNSAFE = re.compile(
    r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}:\d{2}\s?[ap]\.?m|\d+\.\d{3,}"
    rf"|\b{_MONTH}\b\.?\s*\d{{1,2}}\b|\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}\b", re.I)


def _safe(v: str) -> str:
    if _UNSAFE.search(v):
        raise ValueError("a date, clock time or coordinate-like value")
    return v


ContextValue = Annotated[str, StringConstraints(pattern=CONTEXT_VALUE), AfterValidator(_safe)]


class RunInsight(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(pattern=_KEBAB, max_length=64)
    sentence: Annotated[str, StringConstraints(pattern=_SENTENCE.pattern), AfterValidator(_safe)]  # the template wording of a fact already fired for this run


class RunContextPayload(BaseModel):
    """Everything the AI may know about one run: closed-key maps of preformatted strings. A missing value is absent."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    units: Literal["km", "mi"]
    run: dict[RunKey, ContextValue] = Field(default_factory=dict)
    splits: list[dict[SplitKey, ContextValue]] = Field(default_factory=list, max_length=60)
    terrain: dict[TerrainKey, ContextValue] = Field(default_factory=dict)
    conditions: dict[ConditionsKey, ContextValue] = Field(default_factory=dict)
    sleep: dict[SleepKey, ContextValue] = Field(default_factory=dict)
    training: dict[TrainingKey, ContextValue] = Field(default_factory=dict)
    comparison: dict[ComparisonKey, ContextValue] = Field(default_factory=dict)
    insights: list[RunInsight] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def _closed_words(self) -> "RunContextPayload":
        for name in ("run", "terrain", "conditions", "sleep", "training"):
            for k, v in getattr(self, name).items():
                rx = WORD_VALUES.get((name, k))
                if rx is not None and not rx.fullmatch(v):
                    raise ValueError(f"{name}.{k} is outside its closed set")
        return self


def context_value_ok(value: object) -> bool:
    return isinstance(value, str) and _CONTEXT_VALUE.fullmatch(value) is not None and not _UNSAFE.search(value)


def context_sentence_ok(value: object) -> bool:
    return isinstance(value, str) and _SENTENCE.fullmatch(value) is not None and not _UNSAFE.search(value)
