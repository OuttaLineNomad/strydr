"""Threshold loading (AD-8). `config/thresholds.toml` is the only home of tunable numbers.

Sections are keyed by `rule_id` (plus `engine`, `load` and `days` for the derive stages).
Runner overrides come from `settings` and are passed in; nothing here reads the DB or the clock.
"""
import copy
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "thresholds.toml"


class Thresholds:
    """Immutable-by-convention view over the parsed TOML, with overrides already applied."""

    def __init__(self, data: Mapping[str, Mapping[str, Any]]):
        self._data = {k: dict(v) for k, v in data.items()}

    def section(self, name: str) -> Mapping[str, Any]:
        try:
            return self._data[name]
        except KeyError:
            raise KeyError(f"no thresholds section {name!r}") from None

    def rule(self, rule_id: str) -> Mapping[str, Any]:
        return self.section(rule_id)

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._data)


def load_thresholds(
    overrides: Mapping[str, Mapping[str, Any]] | None = None, path: Path | None = None
) -> Thresholds:
    """Parse the TOML and layer runner overrides on top.

    Overrides may only change keys that exist in the defaults, so a typo fails loudly instead of
    silently doing nothing. Example: `{"no-rest-day": {"enabled": False}}`.
    """
    with open(path or DEFAULT_PATH, "rb") as f:
        data = tomllib.load(f)
    for section, values in (overrides or {}).items():
        if section not in data:
            raise ValueError(f"unknown thresholds section {section!r}")
        for key, value in values.items():
            if key not in data[section]:
                raise ValueError(f"unknown threshold {section}.{key}")
            data[section][key] = value
    return Thresholds(data)
