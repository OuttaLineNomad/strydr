from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

_DIR = Path(__file__).parent / "migrations"


def upgrade(engine: Engine) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(_DIR))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
