"""Copy every CareWise table from one database to another, e.g. Neon to Cloud SQL.

    OLD_DATABASE_URL=postgresql://...  DATABASE_URL=postgresql://...  python -m scripts.copy_database

Both databases must be on the same migration (the target is migrated by starting the app once).
The target's existing rows are replaced: it's for moving to a new database, not merging two.
On Google Cloud it runs as a one-off Cloud Run job with the app's own image (see
deploy/gcp/README.md), so Cloud SQL is reachable without installing database tools locally.
Prints row counts only, never data or connection details.
"""
from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.database import engine_options, normalize_database_url
from app.models.db import Base

CHUNK = 500


async def _revision(engine: AsyncEngine) -> str | None:
    async with engine.connect() as conn:
        try:
            return (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        except Exception:  # noqa: BLE001 - no alembic table: not a migrated CareWise database
            return None


async def copy(source_url: str, target_url: str) -> dict[str, int]:
    source_url, target_url = normalize_database_url(source_url), normalize_database_url(target_url)
    source = create_async_engine(source_url, **engine_options(source_url))
    target = create_async_engine(target_url, **engine_options(target_url))
    try:
        old, new = await _revision(source), await _revision(target)
        if old is None or old != new:
            raise SystemExit(
                f"Both databases must be on the same migration (source: {old}, target: {new}). "
                "Start the new app once so it migrates the target, then run this again."
            )
        tables = Base.metadata.sorted_tables  # parents before children
        counts: dict[str, int] = {}
        async with target.begin() as dst:
            for table in reversed(tables):  # children first, so foreign keys allow it
                await dst.execute(table.delete())
            async with source.connect() as src:
                for table in tables:
                    rows = [dict(r._mapping) for r in (await src.execute(select(table))).all()]
                    for start in range(0, len(rows), CHUNK):
                        await dst.execute(insert(table), rows[start:start + CHUNK])
                    counts[table.name] = len(rows)
            if target.dialect.name == "postgresql":
                # Inserting explicit ids doesn't move the id counters; without this, the next new
                # row would collide with a copied one.
                for table in tables:
                    if "id" in table.c and table.c.id.autoincrement in (True, "auto"):
                        await dst.execute(text(
                            f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                            f"COALESCE((SELECT MAX(id) FROM {table.name}), 1), "
                            f"(SELECT MAX(id) FROM {table.name}) IS NOT NULL)"
                        ))
        # Read back from the target, so the report shows what actually landed.
        async with target.connect() as dst:
            for table in tables:
                landed = (await dst.execute(select(func.count()).select_from(table))).scalar()
                if landed != counts[table.name]:
                    raise SystemExit(f"{table.name}: copied {counts[table.name]} rows but found {landed}")
        return counts
    finally:
        await source.dispose()
        await target.dispose()


def main() -> None:
    source, target = os.environ.get("OLD_DATABASE_URL", ""), os.environ.get("DATABASE_URL", "")
    if not source or not target:
        sys.exit("Set OLD_DATABASE_URL (copy from) and DATABASE_URL (copy to).")
    counts = asyncio.run(copy(source, target))
    for name, n in counts.items():
        print(f"{name}: {n} rows")
    print("Done.")


if __name__ == "__main__":
    main()
