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
