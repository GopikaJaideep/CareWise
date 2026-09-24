"""Alembic environment.

Two ways in:
- From the app (app.core.migrations.upgrade_to_head): the app passes its own open connection in
  config.attributes["connection"], so migrations run on startup with no extra setup on Render.
- From the command line (`alembic upgrade head`, `alembic revision --autogenerate -m "..."`):
  connects using DATABASE_URL, exactly as the app would.
"""
from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import DATABASE_URL
from app.models.db import Base

target_metadata = Base.metadata


def run_on_connection(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite can't ALTER most things in place; batch mode rebuilds the table instead.
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_from_cli() -> None:
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        await conn.run_sync(run_on_connection)
        await conn.commit()
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif (connection := context.config.attributes.get("connection")) is not None:
    run_on_connection(connection)
else:
    asyncio.run(run_from_cli())
