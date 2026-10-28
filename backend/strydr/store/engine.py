"""SQLCipher engine (AD-12)."""
import re
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.dialects import registry
from sqlalchemy.dialects.sqlite.pysqlcipher import SQLiteDialect_pysqlcipher
from sqlalchemy.dialects.sqlite.pysqlite import SQLiteDialect_pysqlite
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


class _Dialect(SQLiteDialect_pysqlcipher):
    """Same driver, but the key is applied by our `connect` event (AD-12) instead of from the URL password."""

    supports_statement_cache = True

    def on_connect_url(self, url):
        return SQLiteDialect_pysqlite.on_connect_url(self, url)


registry.register("sqlite.pysqlcipher", __name__, "_Dialect")


def key_pragma(key: str) -> str:
    # A 64-hex key is used as a raw key (no per-connection KDF); anything else is a passphrase.
    if _HEX64.match(key):
        return f"PRAGMA key = \"x'{key}'\""
    return "PRAGMA key = '" + key.replace("'", "''") + "'"


def make_engine(db_path: Path, key: str) -> Engine:
    engine = create_engine(
        f"sqlite+pysqlcipher:///{db_path}",
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=5,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    pragma = key_pragma(key)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute(pragma)  # must be first statement on the connection
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
