"""Schema changes must reach deployed databases. Before Alembic, startup ran metadata.create_all,
which never alters an existing table, so a new column would silently never exist in production."""
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.migrations import BASELINE_REVISION, alembic_config, upgrade_to_head
from app.models.db import Base

HEAD = ScriptDirectory.from_config(alembic_config()).get_current_head()


async def _engine(tmp_path):
    return create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")


def _state(conn):
    return {
        "tables": set(sa.inspect(conn).get_table_names()),
        "revision": MigrationContext.configure(conn).get_current_revision(),
        "drift": compare_metadata(MigrationContext.configure(conn), Base.metadata),
    }


async def test_fresh_database_is_built_by_migrations_and_matches_the_models(tmp_path):
    engine = await _engine(tmp_path)
    async with engine.begin() as conn:
        await conn.run_sync(upgrade_to_head)
        state = await conn.run_sync(_state)
    await engine.dispose()
    assert set(Base.metadata.tables) <= state["tables"]
    assert state["revision"] == HEAD
    # The migrations produce exactly the schema the models describe. If this fails after a
    # model change, generate a migration: alembic revision --autogenerate -m "..."
    assert state["drift"] == []


async def test_database_created_before_migrations_is_adopted_not_recreated(tmp_path):
    engine = await _engine(tmp_path)
    async with engine.begin() as conn:
        # Recreate a pre-Alembic database as it really was: the baseline (0001) schema made by
        # create_all, with no migration history. (Not today's models: later migrations add tables
        # that old databases don't have.)
        await conn.run_sync(lambda c: command.upgrade(alembic_config(c), BASELINE_REVISION))
        await conn.execute(sa.text("DROP TABLE alembic_version"))
        await conn.execute(sa.text(
            "INSERT INTO users (email, hashed_password, display_name, created_at) "
            "VALUES ('a@example.com', 'x', 'A', CURRENT_TIMESTAMP)"
        ))
    async with engine.begin() as conn:
        await conn.run_sync(upgrade_to_head)
        state = await conn.run_sync(_state)
        users = (await conn.execute(sa.text("SELECT email FROM users"))).scalars().all()
    await engine.dispose()
    assert state["revision"] == HEAD
    assert users == ["a@example.com"]  # existing data untouched


async def test_running_on_every_startup_is_harmless(tmp_path):
    engine = await _engine(tmp_path)
    for _ in range(3):
        async with engine.begin() as conn:
            await conn.run_sync(upgrade_to_head)
    async with engine.connect() as conn:
        state = await conn.run_sync(_state)
    await engine.dispose()
    assert state["revision"] == HEAD


def test_baseline_revision_exists():
    assert ScriptDirectory.from_config(alembic_config()).get_revision(BASELINE_REVISION) is not None
