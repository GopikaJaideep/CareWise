"""Long-term memory: opt-in, in the person's control, and never storing what it shouldn't."""
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.agents.outputs import MemoryItem, MemoryUpdate
from app.models.db import Conversation, Message, User, UserMemory
from app.services import memory
from tests.fakes import StructuredFromJson


class MemoryModel(StructuredFromJson):
    provider, model = "fake", "fake"

    def __init__(self, update=None):
        self.update = update or {"add": [], "remove": []}
        self.calls = []

    async def complete_json(self, system, messages, schema_hint="", max_tokens=None):
        self.calls.append(messages[-1]["content"])
        return self.update


async def user(db, enabled=True) -> User:
    u = await db.get(User, 1)
    u.memory_enabled = enabled
    await db.commit()
    return u


async def conversation_with(db, *user_messages) -> int:
    conv = Conversation(user_id=1, title="t")
    db.add(conv)
    await db.flush()
    for text in user_messages:
        db.add(Message(conversation_id=conv.id, role="user", content=text))
        db.add(Message(conversation_id=conv.id, role="assistant", content="ok"))
    await db.commit()
    return conv.id


async def texts(db) -> list[str]:
    return [m.text for m in await memory.load_memories(db, 1)]


# --- What gets stored -------------------------------------------------------------------------------

async def test_durable_facts_are_added_once(db):
    await user(db)
    update = MemoryUpdate(add=[MemoryItem(text="Their mum, Anne, has breast cancer.", category="care_recipient")])
    await memory.apply_update(db, 1, [], update)
    await memory.apply_update(db, 1, await memory.load_memories(db, 1), update)  # same fact again
    assert await texts(db) == ["Their mum, Anne, has breast cancer."]


@pytest.mark.parametrize("unsafe", [
    "Their mobile is 0412 345 678.",
    "Email them at anne@example.com.",
    "Her Medicare number is 2123 45670 1.",
    "They said they want to kill themselves.",
    "They have been self-harming.",
])
async def test_contact_details_and_crisis_content_are_never_stored(db, unsafe):
    await memory.apply_update(db, 1, [], MemoryUpdate(add=[MemoryItem(text=unsafe)]))
    assert await texts(db) == []


async def test_outdated_facts_are_removed_but_only_the_users_own(db):
    db.add(User(email="b@example.com", hashed_password="x", display_name="B"))
    await db.flush()
    mine = UserMemory(user_id=1, text="Chemo is on Tuesdays.")
    theirs = UserMemory(user_id=2, text="Someone else's fact.")
    db.add_all([mine, theirs])
    await db.commit()
    result = await memory.apply_update(db, 1, [mine], MemoryUpdate(remove=[mine.id, theirs.id]))
    assert result["removed"] == 1
    assert (await db.execute(select(UserMemory.text))).scalars().all() == ["Someone else's fact."]


async def test_the_list_is_capped_by_dropping_the_oldest(db, monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_LIMIT", 3)
    for i in range(5):
        await memory.apply_update(db, 1, await memory.load_memories(db, 1),
                                  MemoryUpdate(add=[MemoryItem(text=f"Fact number {i}.")]))
    assert await texts(db) == ["Fact number 2.", "Fact number 3.", "Fact number 4."]


# --- When it runs -------------------------------------------------------------------------------------

async def test_nothing_is_asked_or_stored_when_memory_is_off(db):
    u = await user(db, enabled=False)
    model = MemoryModel({"add": [{"text": "Their mum, Anne, has breast cancer."}]})
    await memory.update_memories(model, db, u, await conversation_with(db, "hi"))
    assert model.calls == [] and await texts(db) == []


async def test_update_sends_existing_facts_and_the_conversation(db):
    u = await user(db)
    db.add(UserMemory(user_id=1, text="Works night shifts."))
    await db.commit()
    model = MemoryModel({"add": [{"text": "Their mum, Anne, has chemo every third Tuesday.", "category": "routine"}]})
    await memory.update_memories(model, db, u, await conversation_with(db, "Mum's chemo is every third Tuesday"))
    assert "Works night shifts." in model.calls[0] and "every third Tuesday" in model.calls[0]
    assert await texts(db) == ["Works night shifts.", "Their mum, Anne, has chemo every third Tuesday."]


async def test_background_refresh_runs_every_third_message_and_skips_safety_turns(db, monkeypatch):
    from app.core import database
    from app.services import llm

    class TestSession:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return False

    model = MemoryModel()
    monkeypatch.setattr(database, "get_session_factory", lambda: TestSession)
    monkeypatch.setattr(llm, "get_llm_client", lambda: model)
    u = await user(db)

    conv = await conversation_with(db, "one", "two")
    await memory._refresh(1, conv)
    assert model.calls == []  # 2 messages: not yet
    db.add(Message(conversation_id=conv, role="user", content="three"))
    await db.commit()
    await memory._refresh(1, conv)
    assert len(model.calls) == 1  # 3rd message: update

    memory.after_turn(u, conv, reached_safety=True)
    assert not memory._background  # a turn that reached the safety response is never remembered


# --- The person's controls (API) --------------------------------------------------------------------------

@pytest.fixture
async def client(db):
    from app.api import memory_routes
    from app.core.auth import get_current_user
    from app.core.database import get_db

    app = FastAPI()
    app.include_router(memory_routes.router)

    async def current_user():
        return await db.get(User, 1)

    async def session():
        yield db

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db] = session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_memory_is_off_by_default(client):
    assert (await client.get("/api/memory")).json() == {"enabled": False, "items": []}


async def test_the_person_can_see_and_forget_items(client, db):
    await client.put("/api/memory/enabled", json={"enabled": True})
    db.add_all([UserMemory(user_id=1, text="Works night shifts."), UserMemory(user_id=1, text="Walking helps.")])
    await db.commit()
    items = (await client.get("/api/memory")).json()["items"]
    assert [i["text"] for i in items] == ["Works night shifts.", "Walking helps."]

    assert (await client.delete(f"/api/memory/{items[0]['id']}")).status_code == 204
    assert [i["text"] for i in (await client.get("/api/memory")).json()["items"]] == ["Walking helps."]
    assert (await client.delete("/api/memory")).status_code == 204
    assert (await client.get("/api/memory")).json()["items"] == []


async def test_turning_memory_off_forgets_everything(client, db):
    await client.put("/api/memory/enabled", json={"enabled": True})
    db.add(UserMemory(user_id=1, text="Works night shifts."))
    await db.commit()
    state = (await client.put("/api/memory/enabled", json={"enabled": False})).json()
    assert state == {"enabled": False, "items": []}


async def test_someone_elses_memory_cannot_be_deleted(client, db):
    db.add(User(email="b@example.com", hashed_password="x", display_name="B"))
    await db.flush()
    theirs = UserMemory(user_id=2, text="Not yours.")
    db.add(theirs)
    await db.commit()
    assert (await client.delete(f"/api/memory/{theirs.id}")).status_code == 404


# --- Used in chat -------------------------------------------------------------------------------------------

async def test_emotional_support_gets_remembered_facts_only_when_memory_is_on():
    from app.agents.base import SessionContext
    from app.agents.emotional_support import EmotionalSupportAgent

    class Capture:
        provider = "fake"

        def __init__(self):
            self.system = ""

        async def complete(self, system, messages, **kw):
            self.system = system
            return "ok"

    agent = EmotionalSupportAgent()
    agent.llm = Capture()
    with_memory = SessionContext(user_id=1, conversation_id=1, user_message="rough day",
                                 user_profile={"memories": ["Works night shifts."]})
    await agent.handle(with_memory)
    assert "- Works night shifts." in agent.llm.system and "never recite" in agent.llm.system
    await agent.handle(SessionContext(user_id=1, conversation_id=1, user_message="rough day", user_profile={"memories": []}))
    assert "earlier chats" not in agent.llm.system


@pytest.mark.parametrize("fine", [
    "Their mum, Anne, has breast cancer.",
    "Mum doesn't want to be in hospital at the end; she wants to be at home.",
    "Walking by the river helps them unwind.",
])
def test_ordinary_facts_pass_the_guard(fine):
    assert memory.is_storable(fine)
