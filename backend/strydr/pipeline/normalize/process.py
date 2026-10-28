"""Raw -> canonical: stream-parse a stored payload and write it with AD-3 precedence dedup."""
import bisect
import json
import zipfile
import zlib
from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.orm import Session

from strydr.sources.canonical import DailyMetric, Workout, fallback_workout_id
from strydr.sources import apple
from strydr.sources import hae
from strydr.sources.hae import ADAPTER_VERSION
from strydr.store import models, settings



def adapter_version(source: str) -> int:
    """The current adapter version of a payload source."""
    return apple.ADAPTER_VERSION if source == "apple" else ADAPTER_VERSION

BATCH = 25  # commit every N items to keep write transactions short (AD-5)


class ChunkReader:
    """File-like read() over a payload's raw_chunk rows, one chunk in memory at a time."""

    def __init__(self, engine: Engine, payload_id: int):
        self._engine, self._payload_id = engine, payload_id
        self._seq = -1
        self._buf = b""
        self._done = False

    def _next_chunk(self) -> bytes:
        with Session(self._engine) as s:
            row = s.execute(
                select(models.RawChunk.seq, models.RawChunk.data)
                .where(models.RawChunk.payload_id == self._payload_id, models.RawChunk.seq > self._seq)
                .order_by(models.RawChunk.seq).limit(1)
            ).first()
        if row is None:
            self._done = True
            return b""
        self._seq = row.seq
        return row.data

    def read(self, n: int = -1) -> bytes:
        while not self._done and (n < 0 or len(self._buf) < n):
            self._buf += self._next_chunk()
        if n < 0:
            out, self._buf = self._buf, b""
        else:
            out, self._buf = self._buf[:n], self._buf[n:]
        return out


class SeekableChunkReader:
    """Seekable file-like view of a payload's raw_chunk rows, so `zipfile.ZipFile` can open it straight from the DB.

    Chunk sizes are read once up front; only the chunk being read is held in memory.
    """

    def __init__(self, engine: Engine, payload_id: int):
        self._engine, self._payload_id = engine, payload_id
        with Session(engine) as s:
            rows = s.execute(select(models.RawChunk.seq, func.length(models.RawChunk.data))
                             .where(models.RawChunk.payload_id == payload_id).order_by(models.RawChunk.seq)).all()
        self._seqs = [r[0] for r in rows]
        self._starts: list[int] = []
        total = 0
        for _, n in rows:
            self._starts.append(total)
            total += n
        self._size, self._pos = total, 0
        self._cached: tuple[int, bytes] | None = None  # (index, data)

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = 0) -> int:
        base = (0, self._pos, self._size)[whence]
        self._pos = max(0, base + offset)
        return self._pos

    def _chunk(self, i: int) -> bytes:
        if self._cached is None or self._cached[0] != i:
            with Session(self._engine) as s:
                data = s.execute(select(models.RawChunk.data).where(
                    models.RawChunk.payload_id == self._payload_id, models.RawChunk.seq == self._seqs[i])).scalar_one()
            self._cached = (i, data)
        return self._cached[1]

    def read(self, n: int = -1) -> bytes:
        end = self._size if n is None or n < 0 else min(self._size, self._pos + n)
        out = bytearray()
        while self._pos < end:
            i = bisect.bisect_right(self._starts, self._pos) - 1
            data = self._chunk(i)
            off = self._pos - self._starts[i]
            part = data[off:off + (end - self._pos)]
            out += part
            self._pos += len(part)
        return bytes(out)

    def close(self) -> None:
        self._cached = None


def apple_items(engine: Engine, payload_id: int, home_tz: str) -> Iterator[Workout | DailyMetric]:
    """Parse an uploaded Apple Health export.zip in place. Raises apple.AdapterError or zipfile.BadZipFile.

    Output before an error is partial: callers that must not write a partial export validate with a first pass.
    """
    reader = SeekableChunkReader(engine, payload_id)
    with zipfile.ZipFile(reader) as zf:
        exports = [n for n in zf.namelist() if n.rpartition("/")[2] == "export.xml" and "__MACOSX" not in n.split("/")]
        if len(exports) != 1:
            raise apple.AdapterError("no single export.xml in the archive")
        base = exports[0].removesuffix("export.xml")  # routes resolve next to it, wherever the archive put it

        def open_route(path: str):
            try:
                return zf.open(base + path.lstrip("/"))
            except (KeyError, zipfile.BadZipFile, ValueError, RuntimeError):
                return None

        with zf.open(exports[0]) as xml:
            yield from apple.parse(xml, ZoneInfo(home_tz), open_route)


def _home_tz(engine: Engine, default_tz: str) -> str:
    with Session(engine) as s:
        return settings.read(s, default_tz).home_tz


def process_payload(engine: Engine, payload_id: int, default_tz: str = "UTC") -> dict[str, int]:
    """Normalize one payload with the parser of its source. Raises on malformed input; the job layer handles retry/quarantine."""
    with Session(engine) as s:
        received_at, source = s.execute(select(models.RawPayload.received_at, models.RawPayload.source)
                                        .where(models.RawPayload.id == payload_id)).one()
    version = adapter_version(source)
    items = apple_items(engine, payload_id, _home_tz(engine, default_tz)) if source == "apple" else hae.parse(ChunkReader(engine, payload_id))
    counts = {"workouts": 0, "metrics": 0}
    with Session(engine) as s:
        for i, item in enumerate(items, 1):
            if isinstance(item, Workout):
                counts["workouts"] += write_workout(s, item, payload_id, received_at, version)
            else:
                counts["metrics"] += write_metric(s, item, payload_id, received_at, version)
            if i % BATCH == 0:
                s.commit()
        s.execute(update(models.RawPayload).where(models.RawPayload.id == payload_id).values(adapter_version=version))
        s.commit()
    return counts


def _wins(new: tuple, old: tuple) -> bool:
    """AD-3: precedence tuples compare left to right, received_at last. A full tie keeps the existing copy."""
    return new > old


def _hr_samples(s: Session, workout_id: str) -> int:
    """Heart-rate samples of a stored workout; the second workout precedence key."""
    n = s.execute(select(models.SampleSeries.n_samples).where(
        models.SampleSeries.workout_id == workout_id, models.SampleSeries.series == "heart_rate")).scalar_one_or_none()
    return n or 0


def _series_data(ser) -> bytes:
    return zlib.compress(json.dumps(ser.columns, separators=(",", ":")).encode())


MERGE_WINDOW = timedelta(seconds=60)
# Scalar fields a losing copy can still contribute (an HAE effort score under an Apple copy, say).
_FILL = ("duration_s", "distance_m", "avg_speed_mps", "max_speed_mps", "avg_hr", "max_hr", "avg_cadence",
         "elevation_gain_m", "energy_kcal", "temperature_c", "humidity_pct")


def _source(s: Session, payload_id: int | None) -> str:
    """The exporter a payload came from; hae when unknown (payload deleted, or none given)."""
    src = s.execute(select(models.RawPayload.source).where(models.RawPayload.id == payload_id)).scalar_one_or_none()
    return src or "hae"


def match_existing(s: Session, w: Workout, source: str = "hae") -> str | None:
    """The workout_id of the stored workout that is the same activity as `w` from another source, if any.

    Same type (or any type once the runner overrode it), a different payload source, and the nearest start
    within 60 s. Meant for a workout_id that is not stored yet; a stored id is the identity already.
    """
    rows = s.execute(
        select(models.Workout.workout_id, models.Workout.type, models.Workout.start_utc,
               func.coalesce(models.RawPayload.source, "hae"))
        .outerjoin(models.RawPayload, models.RawPayload.id == models.Workout.payload_id)
        .where(models.Workout.start_utc >= w.start_utc - MERGE_WINDOW, models.Workout.start_utc <= w.start_utc + MERGE_WINDOW)
    ).all()
    best: tuple[float, str] | None = None
    # An AD-6 key is derived from type and start, so a stored workout with exactly that start is the same
    # workout re-sent (an export re-uploaded after its copy won a merge and took the other source's id).
    derived = w.workout_id == fallback_workout_id(w.type, w.start_utc)
    for wid, wtype, start, src in rows:
        if (src == source and not (derived and start == w.start_utc)) or (wtype != w.type and s.get(models.WorkoutTypeOverride, wid) is None):
            continue
        cand = (abs((start - w.start_utc).total_seconds()), wid)
        if best is None or cand < best:
            best = cand
    return best[1] if best else None


def _fill(winner, loser) -> None:
    """Fill the winner's None fields from the loser and union their quality flags (the winner's value wins).
    Effort score and its estimated flag move together."""
    for f in _FILL:
        if getattr(winner, f) is None:
            setattr(winner, f, getattr(loser, f))
    if winner.effort_score is None and loser.effort_score is not None:
        winner.effort_score, winner.effort_estimated = loser.effort_score, loser.effort_estimated
    winner.quality_flags = {**(loser.quality_flags or {}), **(winner.quality_flags or {})}


def write_workout(s: Session, w: Workout, payload_id: int, received_at: datetime, version: int | None = None) -> int:
    if version is None:
        version = ADAPTER_VERSION
    # AD-3 precedence counts sample streams only; the watch's split summary is not one.
    streams = [x for name, x in w.series.items() if name != "splits"]
    n_series = len(streams)
    n_samples = sum(x.n for x in streams)
    hr = w.series.get("heart_rate")
    n_hr = hr.n if hr is not None else 0
    source = _source(s, payload_id)
    existing = s.execute(select(models.Workout).where(models.Workout.workout_id == w.workout_id)).scalar_one_or_none()
    if existing is None and (adopted := match_existing(s, w, source)) is not None:
        # Another source's copy of the same activity: keep its id so notes, overrides and thumbs stay attached.
        w.workout_id = adopted
        existing = s.execute(select(models.Workout).where(models.Workout.workout_id == adopted)).scalar_one()
    kept: list[tuple] = []
    if existing is not None:
        cross = _source(s, existing.payload_id) != source  # the other source's copy: its fields still count
        # Workouts rank heart-rate samples before total ones, so per-second HR beats a denser route.
        old = (existing.series_count, _hr_samples(s, existing.workout_id), existing.sample_count, existing.received_at)
        if not _wins((n_series, n_hr, n_samples, received_at), old):
            if cross:
                _fill(existing, w)
                # Series only this copy has (HAE splits after an Apple win); counts stay the winner's own.
                have = set(s.execute(select(models.SampleSeries.series).where(
                    models.SampleSeries.workout_id == existing.workout_id)).scalars())
                for name, ser in w.series.items():
                    if name not in have:
                        s.add(models.SampleSeries(workout_id=existing.workout_id, series=name, n_samples=ser.n,
                                                  adapter_version=version, data=_series_data(ser)))
            return 0
        # Any replacement keeps what the stored copy carried that this one lacks, so a re-exported Apple
        # history does not drop what an HAE copy merged in. Reparse clears canonical, so nothing goes stale.
        _fill(w, existing)
        kept = [(r.series, r.n_samples, r.adapter_version, r.data) for r in s.execute(
            select(models.SampleSeries).where(models.SampleSeries.workout_id == w.workout_id)).scalars()
            if r.series not in w.series]
        s.execute(delete(models.SampleSeries).where(models.SampleSeries.workout_id == w.workout_id))
        s.delete(existing)
        s.flush()
    row = models.Workout(
        **{f: getattr(w, f) for f in (
            "workout_id", "type", "is_indoor", "start_utc", "end_utc", "utc_offset_s", "local_date", "duration_s",
            "distance_m", "avg_speed_mps", "max_speed_mps", "avg_hr", "max_hr", "avg_cadence", "elevation_gain_m",
            "energy_kcal", "temperature_c", "humidity_pct", "effort_score", "effort_estimated", "quality_flags")},
        series_count=n_series, sample_count=n_samples, adapter_version=version,
        payload_id=payload_id, received_at=received_at,
    )
    override = s.get(models.WorkoutTypeOverride, w.workout_id)
    if override is not None:
        row.type = override.type
    s.add(row)
    s.flush()
    for name, ser in w.series.items():
        s.add(models.SampleSeries(
            workout_id=w.workout_id, series=name, n_samples=ser.n, adapter_version=version,
            data=_series_data(ser),
        ))
    for name, n, kept_version, data in kept:  # a series only the replaced copy had, such as HAE's splits
        s.add(models.SampleSeries(workout_id=w.workout_id, series=name, n_samples=n, adapter_version=kept_version, data=data))
    return 1


def write_metric(s: Session, m: DailyMetric, payload_id: int, received_at: datetime, version: int | None = None) -> int:
    if version is None:
        version = ADAPTER_VERSION
    existing = s.execute(
        select(models.DailyMetric).where(models.DailyMetric.metric == m.metric, models.DailyMetric.local_date == m.local_date)
    ).scalar_one_or_none()
    if existing is not None:
        if not _wins((1, m.field_count, received_at), (existing.series_count, existing.sample_count, existing.received_at)):
            return 0
        s.delete(existing)
        s.flush()
    s.add(models.DailyMetric(
        metric=m.metric, local_date=m.local_date, units=m.units, value=m.value, extra=m.extra,
        series_count=1, sample_count=m.field_count, adapter_version=version,
        payload_id=payload_id, received_at=received_at,
    ))
    return 1
