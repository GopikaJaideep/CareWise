"""Async database session and engine setup."""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# libpq options that hosted-Postgres URLs often carry but asyncpg rejects as unknown arguments.
_LIBPQ_ONLY_PARAMS = {"channel_binding", "target_session_attrs", "gssencmode"}


def normalize_database_url(url: str) -> str:
    """Accept the Postgres URLs hosting providers hand out (Render, Neon, Supabase, Railway...).

    They look like ``postgres://user:pw@host/db?sslmode=require``. SQLAlchemy needs an
    explicit async driver, and asyncpg spells ``sslmode`` as ``ssl``. SQLite URLs pass through.
    """
    url = url.strip()
    if not url:
        return get_settings().model_fields["database_url"].default
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
            break
    if not url.startswith("postgresql+asyncpg://"):
        return url

    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode":
            # disable/allow/prefer map to asyncpg's own values; require/verify-* all mean "use TLS".
            query.append(("ssl", value if value in ("disable", "allow", "prefer") else "require"))
        elif key not in _LIBPQ_ONLY_PARAMS:
            query.append((key, value))
    return urlunsplit(parts._replace(query=urlencode(query)))


def describe_database(url: str) -> str:
    """Where the data lives, for the startup log. Never includes credentials."""
    if url.startswith("sqlite"):
        return f"SQLite file {url.split(':///', 1)[-1]}"
    parts = urlsplit(url)
    return f"Postgres at {parts.hostname}{parts.path}"


settings = get_settings()
DATABASE_URL = normalize_database_url(settings.database_url)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

def engine_options(url: str) -> dict:
    """Connection options for this database.

    Hosted Postgres drops idle connections, so connections are checked before use. Behind a
    transaction-mode connection pooler (PgBouncer: Neon's "-pooler" hosts, Supabase's port 6543),
    asyncpg's prepared-statement caches break ("prepared statement ... already exists"), so both
    asyncpg's and SQLAlchemy's are switched off there. A direct connection keeps them.
    """
    if url.startswith("sqlite"):
        return {}
    options: dict = {"pool_pre_ping": True}
    parts = urlsplit(url)
    if "-pooler" in (parts.hostname or "") or parts.port == 6543:
        options["connect_args"] = {"statement_cache_size": 0, "prepared_statement_cache_size": 0}
    return options


engine = create_async_engine(DATABASE_URL, echo=settings.debug, **engine_options(DATABASE_URL))
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    logger.info("Database: %s", describe_database(DATABASE_URL))
    if IS_SQLITE:
        logger.warning(
            "Using a SQLite file. On hosts that reset the disk on each deploy (Render, Railway, "
            "Koyeb, Fly without a volume...) every account and record is lost on redeploy. "
            "Set DATABASE_URL to a Postgres database for any hosted deployment."
        )
    # Migrations, not metadata.create_all: create_all only adds missing tables and never changes
    # existing ones, so schema changes would silently never reach a deployed database.
    from app.core.migrations import upgrade_to_head  # imported here: migrations/env.py imports this module

    async with engine.begin() as conn:
        await conn.run_sync(upgrade_to_head)


def get_session_factory():
    """For code that must open its own session, e.g. a streaming response that outlives the
    request-scoped get_db session. Overridable in tests."""
    return SessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
