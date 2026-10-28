"""Nightly encrypted snapshot (AD-12): SQLite online backup into a destination keyed with the same key."""
import logging
from pathlib import Path

import sqlcipher3
from sqlalchemy import Engine

from strydr.store.engine import key_pragma

log = logging.getLogger("strydr.jobs")
KEEP = 7
PREFIX, SUFFIX = "strydr-", ".db"


def snapshot(engine: Engine, key: str, dest_dir: Path, today: str, keep: int = KEEP) -> Path:
    """Write `strydr-YYYYMMDD.db` into `dest_dir` and prune to the newest `keep`. `today` is the home_tz local date."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / f"{PREFIX}{today.replace('-', '')}{SUFFIX}"
    tmp = final.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    dest = sqlcipher3.connect(str(tmp))
    try:
        dest.execute(key_pragma(key))  # the destination is keyed before any page is written: no plaintext copy ever exists
        src = engine.raw_connection()
        try:
            src.driver_connection.backup(dest)
        finally:
            src.close()
        dest.commit()
    except BaseException:
        dest.close()
        tmp.unlink(missing_ok=True)
        raise
    dest.close()
    tmp.replace(final)
    for old in sorted(dest_dir.glob(f"{PREFIX}*{SUFFIX}"))[:-keep]:
        old.unlink()
    log.info("snapshot written: %s", final.name)
    return final
