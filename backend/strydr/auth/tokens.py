import hashlib
import hmac
import secrets

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from strydr.store import models


def new_token() -> str:
    return secrets.token_urlsafe(32)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_ingest_token(engine: Engine, presented: str | None) -> bool:
    """Constant-time comparison of digests (AD-11). Only the digest is stored."""
    with Session(engine) as s:
        stored = s.execute(select(models.User.ingest_token_sha256)).scalars().first()
    return hmac.compare_digest(digest(presented or ""), stored or "0" * 64) and stored is not None
