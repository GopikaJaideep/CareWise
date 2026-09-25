"""Hosted-Postgres URLs must work as pasted from the provider's dashboard. Without this,
the only option was the default SQLite file, which hosts wipe on every deploy."""
import pytest

from app.core.database import describe_database, normalize_database_url


@pytest.mark.parametrize(
    "given, expected",
    [
        # Render / Heroku style
        ("postgres://u:p@db.example.com:5432/carewise", "postgresql+asyncpg://u:p@db.example.com:5432/carewise"),
        # Plain SQLAlchemy style without a driver
        ("postgresql://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        # Neon: sslmode -> ssl, and channel_binding (unsupported by asyncpg) dropped
        (
            "postgresql://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://u:p@ep-x.neon.tech/db?ssl=require",
        ),
        ("postgres://u:p@host/db?sslmode=verify-full", "postgresql+asyncpg://u:p@host/db?ssl=require"),
        ("postgres://u:p@host/db?sslmode=disable", "postgresql+asyncpg://u:p@host/db?ssl=disable"),
        # Already correct: left alone
        ("postgresql+asyncpg://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        # SQLite passes through untouched
        ("sqlite+aiosqlite:////data/carewise.db", "sqlite+aiosqlite:////data/carewise.db"),
        # Empty (e.g. `DATABASE_URL=` in .env) falls back to the default instead of crashing
        ("", "sqlite+aiosqlite:///./carewise.db"),
        ("  ", "sqlite+aiosqlite:///./carewise.db"),
    ],
)
def test_normalize_database_url(given, expected):
    assert normalize_database_url(given) == expected


def test_describe_database_never_logs_credentials():
    text = describe_database("postgresql+asyncpg://user:s3cret@db.example.com:5432/carewise?ssl=require")
    assert text == "Postgres at db.example.com/carewise"
    assert "s3cret" not in text and "user" not in text


def test_pooled_postgres_disables_prepared_statement_caches():
    from app.core.database import engine_options, normalize_database_url

    neon_pooled = normalize_database_url(
        "postgresql://u:p@ep-wild-tree-a7f53cl-pooler.ap-southeast-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
    assert engine_options(neon_pooled)["connect_args"] == {"statement_cache_size": 0, "prepared_statement_cache_size": 0}
    supabase_pooled = normalize_database_url("postgresql://u:p@aws-0-ap-southeast-2.pooler.supabase.com:6543/postgres")
    assert "connect_args" in engine_options(supabase_pooled)
    direct = normalize_database_url("postgresql://u:p@ep-wild-tree-a7f53cl.ap-southeast-2.aws.neon.tech/neondb?sslmode=require")
    assert engine_options(direct) == {"pool_pre_ping": True}
    assert engine_options("sqlite+aiosqlite:///./carewise.db") == {}


async def test_sqlalchemy_takes_its_cache_option_out_before_calling_asyncpg(monkeypatch):
    """prepared_statement_cache_size belongs to SQLAlchemy's adapter; if it reached asyncpg.connect
    as an unknown argument, every connection would fail. Check it's removed on the way."""
    import asyncpg
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.database import engine_options

    seen = {}

    async def fake_connect(*args, **kwargs):
        seen.update(kwargs)
        raise ConnectionRefusedError("stop here: only the arguments matter")

    monkeypatch.setattr(asyncpg, "connect", fake_connect)
    url = "postgresql+asyncpg://u:p@ep-x-pooler.ap-southeast-2.aws.neon.tech/neondb?ssl=require"
    engine = create_async_engine(url, **engine_options(url))
    try:
        async with engine.connect():
            pass
    except Exception:
        pass
    finally:
        await engine.dispose()
    assert seen.get("statement_cache_size") == 0 and "prepared_statement_cache_size" not in seen
