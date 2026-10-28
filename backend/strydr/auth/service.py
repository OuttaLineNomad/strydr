from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from strydr.auth.passwords import hash_password
from strydr.auth.tokens import digest, new_token
from strydr.store import models
from strydr.store.util import utcnow


def create_user(engine: Engine, username: str, password: str, reset: bool = False) -> str:
    """Create the single user (FR-34) and return the plaintext ingest token, shown once."""
    token = new_token()
    with Session(engine) as s:
        if s.execute(select(models.User.id)).first() is not None:
            if not reset:
                raise SystemExit("a user already exists; use --reset to replace it")
            s.execute(delete(models.Session))
            s.execute(delete(models.User))
        s.add(models.User(username=username, password_hash=hash_password(password),
                          ingest_token_sha256=digest(token), created_at=utcnow()))
        s.commit()
    return token
