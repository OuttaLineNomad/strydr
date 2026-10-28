"""Runtime settings (AD-1 user inputs): JSON values in the key/value `settings` table."""
import json
from dataclasses import asdict, dataclass, fields

from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.store import models

DEFAULT_ZONE_BOUNDS_PCT = [60.0, 70.0, 80.0, 90.0]  # upper bounds of zones 1-4 as % of HRmax; zone 5 is above


@dataclass(frozen=True)
class UserSettings:
    birth_year: int | None = None
    sex: str | None = None  # male|female
    hrmax_override: int | None = None
    zones: list[float] | None = None  # None: DEFAULT_ZONE_BOUNDS_PCT
    units: str = "metric"  # metric|imperial
    home_tz: str = "UTC"

    @property
    def zone_bounds_pct(self) -> list[float]:
        return self.zones or DEFAULT_ZONE_BOUNDS_PCT


def read(s: Session, default_tz: str = "UTC") -> UserSettings:
    stored = {k: json.loads(v) for k, v in s.execute(select(models.Settings.key, models.Settings.value))}
    names = {f.name for f in fields(UserSettings)}
    values = {k: v for k, v in stored.items() if k in names and v is not None}
    values.setdefault("home_tz", default_tz)
    return UserSettings(**values)


def write(s: Session, new: UserSettings) -> None:
    for key, value in asdict(new).items():
        row = s.get(models.Settings, key)
        text = json.dumps(value)
        if row is None:
            s.add(models.Settings(key=key, value=text))
        else:
            row.value = text


# Threshold overrides are a closed-list pipeline input (AD-1): {rule_id: {key: value}}.
THRESHOLD_KEY = "threshold_overrides"


def read_threshold_overrides(s: Session) -> dict[str, dict]:
    row = s.get(models.Settings, THRESHOLD_KEY)
    return json.loads(row.value) if row else {}


def write_threshold_overrides(s: Session, overrides: dict[str, dict]) -> None:
    row = s.get(models.Settings, THRESHOLD_KEY)
    if row is None:
        s.add(models.Settings(key=THRESHOLD_KEY, value=json.dumps(overrides)))
    else:
        row.value = json.dumps(overrides)


@dataclass(frozen=True)
class AiSettings:
    """The AI overlay's provider settings (AD-9). Not a pipeline input: changing them never recomputes.

    `provider` is `nvidia` or `openai-compatible`; None base_url/model means the provider's default. AI is off
    until `api_key` is set (FR-28).
    """
    provider: str = "nvidia"
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


def read_ai(s: Session) -> AiSettings:
    stored = {k[3:]: json.loads(v) for k, v in s.execute(select(models.Settings.key, models.Settings.value))
              if k.startswith("ai_")}
    names = {f.name for f in fields(AiSettings)}
    return AiSettings(**{k: v for k, v in stored.items() if k in names})


def write_ai(s: Session, new: AiSettings) -> None:
    for key, value in asdict(new).items():
        row = s.get(models.Settings, "ai_" + key)
        text = json.dumps(value)
        if row is None:
            s.add(models.Settings(key="ai_" + key, value=text))
        else:
            row.value = text


# Opt-in weather fetch (AD-10 weather exception). A closed-list pipeline input (AD-1): derive only reads
# fetched weather while it is on, so changing it recomputes.
WEATHER_KEY = "weather_enabled"


def read_weather_enabled(s: Session) -> bool:
    row = s.get(models.Settings, WEATHER_KEY)
    return bool(json.loads(row.value)) if row else False


def write_weather_enabled(s: Session, enabled: bool) -> None:
    row = s.get(models.Settings, WEATHER_KEY)
    if row is None:
        s.add(models.Settings(key=WEATHER_KEY, value=json.dumps(enabled)))
    else:
        row.value = json.dumps(enabled)
