"""One-click demo accounts: private, pre-filled, capped, and deleted after a day."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.api import auth_routes
from app.core.database import get_db
from app.models.db import CareTask, Conversation, Message, SymptomLog, User
from app.services import demo


@pytest.fixture(autouse=True)
def fresh_limits():
    demo._recent_by_ip.clear()
    yield
    demo._recent_by_ip.clear()


@pytest.fixture
async def client(db):
    app = FastAPI()
    app.include_router(auth_routes.router)

    async def session():
        yield db

    app.dependency_overrides[get_db] = session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def count(db, model, **where):
    q = select(func.count()).select_from(model)
    for k, v in where.items():
        q = q.where(getattr(model, k) == v)
    return await db.scalar(q)


async def test_each_visitor_gets_their_own_prefilled_account(client, db):
    first = await client.post("/api/auth/demo")
    second = await client.post("/api/auth/demo")
    assert first.status_code == second.status_code == 201
    a, b = first.json()["user_id"], second.json()["user_id"]
    assert a != b  # never a shared account

    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {first.json()['access_token']}"})
    assert me.json()["is_demo"] is True and me.json()["email"].endswith(".invalid")
    assert await count(db, SymptomLog, user_id=a) >= 5
    assert await count(db, CareTask, user_id=a) >= 3
    assert await count(db, Conversation, user_id=a) == 1


async def test_starting_demos_is_rate_limited_per_address(client):
    headers = {"X-Forwarded-For": "203.0.113.7"}
    codes = [(await client.post("/api/auth/demo", headers=headers)).status_code for _ in range(demo.DEMO_PER_IP_PER_HOUR + 1)]
    assert codes[:-1] == [201] * demo.DEMO_PER_IP_PER_HOUR and codes[-1] == 429
    # Someone else is unaffected.
    assert (await client.post("/api/auth/demo", headers={"X-Forwarded-For": "198.51.100.2"})).status_code == 201


async def test_there_is_a_hard_ceiling_on_live_demos(client, monkeypatch):
    monkeypatch.setattr(demo, "MAX_LIVE_DEMOS", 1)
    assert (await client.post("/api/auth/demo")).status_code == 201
    busy = await client.post("/api/auth/demo", headers={"X-Forwarded-For": "198.51.100.9"})
    assert busy.status_code == 503 and "busy" in busy.json()["detail"]


async def test_a_demo_account_has_a_message_limit(db, monkeypatch):
    from fastapi import HTTPException

    from app.api.chat_routes import run_chat_turn
    from app.api.schemas import ChatRequest

    user = await demo.create_demo_user(db)
    conversation = (await db.execute(select(Conversation).where(Conversation.user_id == user.id))).scalar_one()
    monkeypatch.setattr(demo, "DEMO_MESSAGE_LIMIT", 2)  # the seeded chat already has 1 message from the user
    db.add(Message(conversation_id=conversation.id, role="user", content="another"))
    await db.commit()
    with pytest.raises(HTTPException) as err:
        await run_chat_turn(ChatRequest(message="hello"), user, db)
    assert err.value.status_code == 429 and "Create a free account" in err.value.detail


async def test_demos_are_deleted_after_a_day_with_all_their_data(db):
    now = datetime.now(timezone.utc)
    old = await demo.create_demo_user(db, now=now)
    old.created_at = now - timedelta(hours=demo.DEMO_TTL_HOURS + 1)
    fresh = await demo.create_demo_user(db, now=now)
    real = await db.get(User, 1)  # a real account, however old, is never touched
    real.created_at = now - timedelta(days=365)
    await db.commit()

    assert await demo.purge_expired_demos(db, now=now) == 1
    remaining = set((await db.execute(select(User.id))).scalars())
    assert remaining == {real.id, fresh.id}
    assert await count(db, SymptomLog, user_id=old.id) == 0  # their data went with them


def test_rate_limit_window_slides():
    for _ in range(demo.DEMO_PER_IP_PER_HOUR):
        assert demo.allow_new_demo("192.0.2.1", now=0)
    assert not demo.allow_new_demo("192.0.2.1", now=10)
    assert demo.allow_new_demo("192.0.2.1", now=3700)  # an hour later
