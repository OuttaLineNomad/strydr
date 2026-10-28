from datetime import timedelta

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from strydr.auth.passwords import verify_password
from strydr.auth.tokens import digest, new_token
from strydr.store import models
from strydr.store.util import utcnow

COOKIE = "strydr_session"
TTL = timedelta(days=30)


def login(engine: Engine, username: str, password: str) -> str | None:
    """Return a new session cookie value, or None for bad credentials."""
    with Session(engine) as s:
        user = s.execute(select(models.User).where(models.User.username == username)).scalar_one_or_none()
        if not verify_password(user.password_hash if user else None, password):
            return None
        raw = new_token()
        now = utcnow()
        s.add(models.Session(id=digest(raw), user_id=user.id, created_at=now, expires_at=now + TTL))
        s.commit()
        return raw


def user_for_session(engine: Engine, raw: str | None) -> int | None:
    if not raw:
        return None
    with Session(engine) as s:
        row = s.get(models.Session, digest(raw))
        return row.user_id if row and row.expires_at > utcnow() else None


def logout(engine: Engine, raw: str | None) -> None:
    if not raw:
        return
    with Session(engine) as s:
        row = s.get(models.Session, digest(raw))
        if row:
            s.delete(row)
            s.commit()
