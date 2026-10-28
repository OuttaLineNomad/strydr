"""Analytic generations and the current_generation pointer (AD-1)."""
from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, Select, delete, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from strydr.store import models
from strydr.store.util import utcnow

CHUNK = 200  # rows per write transaction (AD-5: small transactions)


def begin(engine: Engine, as_of: str) -> int:
    with Session(engine) as s:
        g = models.Generation(as_of=as_of, created_at=utcnow())
        s.add(g)
        s.commit()
        return g.id


def add_rows(engine: Engine, rows: Iterable) -> None:
    """Write rows in small transactions."""
    batch: list = []
    for row in rows:
        batch.append(row)
        if len(batch) >= CHUNK:
            _commit(engine, batch)
            batch = []
    if batch:
        _commit(engine, batch)


def _commit(engine: Engine, batch: list) -> None:
    with Session(engine) as s:
        s.add_all(batch)
        s.commit()


def publish(engine: Engine, generation_id: int) -> None:
    """Flip the pointer in one short transaction. Readers see the old generation or the new one, never a mix."""
    with Session(engine) as s:
        ptr = s.get(models.CurrentGeneration, 1)
        if ptr is None:
            s.add(models.CurrentGeneration(id=1, generation_id=generation_id))
        else:
            ptr.generation_id = generation_id
        s.commit()


def delete_generation(engine: Engine, generation_id: int) -> None:
    for model in models.ANALYTIC:
        while True:
            with Session(engine) as s:
                keys = s.execute(select(model).where(model.generation_id == generation_id).limit(CHUNK)).scalars().all()
                if not keys:
                    break
                for row in keys:
                    s.delete(row)
                s.commit()
    with Session(engine) as s:
        s.execute(delete(models.Generation).where(models.Generation.id == generation_id))
        s.commit()


def purge_stale(engine: Engine) -> None:
    """Delete every generation except the current one, including partial ones left by a crash."""
    with Session(engine) as s:
        keep = current_id(s)
        stale = [g for g in s.execute(select(models.Generation.id)).scalars() if g != keep]
    for gid in stale:
        delete_generation(engine, gid)


def current_id(s: Session) -> int | None:
    return s.execute(select(models.CurrentGeneration.generation_id)).scalar_one_or_none()


def in_current(model) -> ColumnElement[bool]:
    """Scope one statement to the current generation. The pointer is read inside the same statement."""
    return model.generation_id == select(models.CurrentGeneration.generation_id).scalar_subquery()


def scoped(model, *where) -> Select:
    return select(model).where(in_current(model), *where)


@contextmanager
def read_snapshot(engine: Engine) -> Iterator[Session]:
    """A session whose reads all see one database snapshot, so a generation flip mid-request is invisible."""
    with Session(engine) as s:
        s.connection().exec_driver_sql("BEGIN")
        try:
            yield s
        finally:
            s.rollback()
