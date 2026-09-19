"""Chat history endpoints. Both used to 500 (MissingGreenlet on the lazy `messages`
relationship), which the UI hid by showing an empty chat after every page change."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

from app.api import chat_routes
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.db import Conversation, Message, User

T0 = datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
async def seeded(db):
    """User 1 has two conversations; user 2 has one."""
    other = User(email="b@example.com", hashed_password="x", display_name="B")
    db.add(other)
    await db.flush()

    old = Conversation(user_id=1, title="older chat", created_at=T0)
    new = Conversation(user_id=1, title="newer chat", created_at=T0 + timedelta(hours=1))
    theirs = Conversation(user_id=other.id, title="someone else's", created_at=T0)
    db.add_all([old, new, theirs])
    await db.flush()
    # Inserted out of order on purpose: the endpoint must return them chronologically.
    db.add_all([
        Message(conversation_id=new.id, role="assistant", content="second", created_at=T0 + timedelta(minutes=61)),
        Message(conversation_id=new.id, role="user", content="first", created_at=T0 + timedelta(minutes=60)),
        Message(conversation_id=theirs.id, role="user", content="secret", created_at=T0),
    ])
    await db.commit()
    return {"old": old.id, "new": new.id, "theirs": theirs.id}


@pytest.fixture
async def client(db):
    app = FastAPI()
    app.include_router(chat_routes.router)

    async def current_user():
        return await db.get(User, 1)

    async def session():
        yield db

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db] = session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_list_returns_only_my_conversations_newest_first(client, seeded):
    r = await client.get("/api/chat/conversations")
    assert r.status_code == 200
    assert [c["title"] for c in r.json()] == ["newer chat", "older chat"]


async def test_list_is_summaries_without_messages(client, seeded):
    r = await client.get("/api/chat/conversations")
    assert all("messages" not in c for c in r.json())


async def test_timestamps_carry_a_utc_marker(client, seeded):
    r = await client.get("/api/chat/conversations")
    assert r.json()[0]["created_at"].endswith("+00:00")


async def test_get_conversation_returns_messages_in_order(client, seeded):
    r = await client.get(f"/api/chat/conversations/{seeded['new']}")
    assert r.status_code == 200
    assert [m["content"] for m in r.json()["messages"]] == ["first", "second"]
    assert [m["role"] for m in r.json()["messages"]] == ["user", "assistant"]


async def test_empty_conversation_returns_empty_message_list(client, seeded):
    r = await client.get(f"/api/chat/conversations/{seeded['old']}")
    assert r.status_code == 200
    assert r.json()["messages"] == []


async def test_cannot_read_another_users_conversation(client, seeded):
    r = await client.get(f"/api/chat/conversations/{seeded['theirs']}")
    assert r.status_code == 404


async def test_unknown_conversation_is_404(client, seeded):
    assert (await client.get("/api/chat/conversations/9999")).status_code == 404
