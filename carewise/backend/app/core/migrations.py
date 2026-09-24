"""Apply database migrations on startup, so a deploy (e.g. on Render) needs no manual step."""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
# The first migration: the schema as it was when Alembic was introduced.
BASELINE_REVISION = "0001"


def alembic_config(connection: Connection | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def upgrade_to_head(connection: Connection) -> None:
    """Bring the database up to the latest migration. Run inside the app's own connection.

    Databases created before migrations existed (by metadata.create_all) already have the
    baseline tables but no alembic_version table. They are stamped at the baseline first,
    so Alembic adopts them instead of trying to create tables that already exist.
    """
    tables = set(inspect(connection).get_table_names())
    cfg = alembic_config(connection)
    if "users" in tables and "alembic_version" not in tables:
        logger.info("Existing database without migration history: adopting it at revision %s", BASELINE_REVISION)
        command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")
