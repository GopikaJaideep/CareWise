"""Moving to a new database copies every row, keeps ids, and refuses mismatched schemas."""
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.migrations import upgrade_to_head
from app.models.db import CareTask, Conversation, Message, SymptomLog, User
from scripts.copy_database import copy


async def migrated(path):
    url = f"sqlite+aiosqlite:///{path}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(upgrade_to_head)
    return url, engine


async def test_every_row_is_copied_with_its_id(tmp_path):
    old_url, old = await migrated(tmp_path / "old.db")
    new_url, new = await migrated(tmp_path / "new.db")
    async with async_sessionmaker(old)() as s:
        user = User(email="carer@example.com", hashed_password="x", display_name="Sam")
        s.add(user)
        await s.flush()
        s.add_all([SymptomLog(user_id=user.id, symptom="nausea", severity=6), CareTask(user_id=user.id, title="Chemo")])
        conv = Conversation(user_id=user.id, title="Hi")
        conv.messages = [Message(role="user", content="hello")]
        s.add(conv)
        await s.commit()
    async with async_sessionmaker(new)() as s:  # a stray row in the target is replaced, not kept
        s.add(User(email="stray@example.com", hashed_password="x", display_name="Stray"))
        await s.commit()

    counts = await copy(old_url, new_url)
    assert counts["users"] == 1 and counts["symptom_logs"] == 1 and counts["messages"] == 1
    async with async_sessionmaker(new)() as s:
        emails = list((await s.execute(select(User.email))).scalars())
        assert emails == ["carer@example.com"]
        message = (await s.execute(select(Message))).scalar_one()
        assert message.content == "hello"
    await old.dispose()
    await new.dispose()


async def test_a_target_on_a_different_migration_is_refused(tmp_path):
    old_url, old = await migrated(tmp_path / "old.db")
    new_url, new = await migrated(tmp_path / "new.db")
    async with new.begin() as conn:
        await conn.execute(text("UPDATE alembic_version SET version_num = 'something-else'"))
    with pytest.raises(SystemExit, match="same migration"):
        await copy(old_url, new_url)
    await old.dispose()
    await new.dispose()
