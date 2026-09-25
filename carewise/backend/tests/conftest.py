import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, User
from app.core.config import get_settings

# No DNS lookups in tests: sign-up's email deliverability check is tested with it switched back on.
get_settings().email_check_deliverability = False


@pytest.fixture
async def db():
    """Fresh in-memory database with one user (id=1)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add(User(email="a@example.com", hashed_password="x", display_name="A"))
        await session.commit()
        yield session
    await engine.dispose()
