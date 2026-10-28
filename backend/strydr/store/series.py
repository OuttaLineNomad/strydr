"""Decode canonical sample series (written by pipeline/normalize as zlib-compressed columnar JSON)."""
import json
import zlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.store import models


def decode(data: bytes) -> dict[str, list]:
    return json.loads(zlib.decompress(data))


def load_series(s: Session, workout_id: str) -> dict[str, dict[str, list]]:
    rows = s.execute(select(models.SampleSeries.series, models.SampleSeries.data)
                     .where(models.SampleSeries.workout_id == workout_id)).all()
    return {name: decode(data) for name, data in rows}
