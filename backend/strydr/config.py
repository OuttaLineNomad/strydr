"""Runtime configuration. Secrets come from files, never env values (AD-12)."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Config:
    db_path: Path = field(default_factory=lambda: Path(os.environ.get("STRYDR_DB_PATH", "/data/strydr.db")))
    db_key_file: Path = field(
        default_factory=lambda: Path(os.environ.get("STRYDR_DB_KEY_FILE", "/run/secrets/strydr_db_key"))
    )
    data_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("STRYDR_DATA_DIR") or Path(os.environ.get("STRYDR_DB_PATH", "/data/strydr.db")).parent))
    web_dist: Path = field(default_factory=lambda: Path(os.environ.get("STRYDR_WEB_DIST", "/app/web/dist")))
    app_port: int = field(default_factory=lambda: int(os.environ.get("STRYDR_APP_PORT", "8080")))
    ingest_port: int = field(default_factory=lambda: int(os.environ.get("STRYDR_INGEST_PORT", "8081")))
    host: str = field(default_factory=lambda: os.environ.get("STRYDR_HOST", "0.0.0.0"))
    home_tz: str = field(default_factory=lambda: os.environ.get("STRYDR_HOME_TZ") or os.environ.get("TZ") or "UTC")
    retry_backoff_s: float = field(default_factory=lambda: float(os.environ.get("STRYDR_RETRY_BACKOFF_S", "5")))

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.home_tz)


def read_db_key(path: Path) -> str:
    try:
        key = path.read_text().strip()
    except OSError as e:
        raise SystemExit(f"cannot read DB key file {path}: {e.strerror}") from None
    if not key:
        raise SystemExit(f"DB key file {path} is empty")
    return key
