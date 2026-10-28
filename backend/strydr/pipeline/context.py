"""What every stage of one recompute run shares. `as_of` is the only notion of "today" in the pipeline (AD-15)."""
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import Engine

if TYPE_CHECKING:
    from strydr.pipeline.insights.thresholds import Thresholds


@dataclass(frozen=True)
class Context:
    engine: Engine
    generation_id: int
    as_of: date
    tz: ZoneInfo
    thresholds: "Thresholds | None" = None  # defaults plus the runner's overrides (AD-8); None means the defaults

    @property
    def th(self) -> "Thresholds":
        from strydr.pipeline.insights.thresholds import load_thresholds  # lazy: insights imports this module
        return self.thresholds or load_thresholds()
