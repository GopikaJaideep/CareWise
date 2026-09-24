"""Manual burnout check-ins (the dashboard form). Before this endpoint existed, the only
way to check in was through the chat agent."""
import httpx
import pytest
from fastapi import FastAPI

from app.agents.burnout_monitor import compute_burnout_score
from app.api import tracking_routes
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.db import User

TIRED = {"sleep_hours": 5, "stress_level": 8, "energy_level": 3, "self_care_minutes": 0}


@pytest.fixture
async def client(db):
    app = FastAPI()
    app.include_router(tracking_routes.router)

    async def current_user():
        return await db.get(User, 1)

    async def session():
        yield db

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db] = session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_manual_checkin_is_scored_saved_and_categorised(client):
    r = await client.post("/api/burnout/checkins", json={**TIRED, "notes": "rough week"})
    assert r.status_code == 200
    body = r.json()
    assert body["burnout_score"] == compute_burnout_score(**TIRED)
    assert body["category"] == "high"
    assert body["notes"] == "rough week"

    listed = await client.get("/api/burnout/checkins")
    assert [c["id"] for c in listed.json()] == [body["id"]]


async def test_manual_checkin_uses_the_same_trend_amplifier_as_chat(client):
    # Three worsening check-ins in a row: the third should get the trend bonus.
    steps = [
        {"sleep_hours": 7, "stress_level": 3, "energy_level": 7, "self_care_minutes": 30},
        {"sleep_hours": 6, "stress_level": 5, "energy_level": 5, "self_care_minutes": 20},
        TIRED,
    ]
    scores = [(await client.post("/api/burnout/checkins", json=s)).json()["burnout_score"] for s in steps]
    assert scores[2] == compute_burnout_score(**TIRED, recent_trend=scores[:2])
    assert scores[2] > compute_burnout_score(**TIRED)


@pytest.mark.parametrize(
    "bad",
    [
        {"stress_level": 0},
        {"stress_level": 11},
        {"energy_level": 0},
        {"sleep_hours": -1},
        {"sleep_hours": 25},
        {"self_care_minutes": -5},
    ],
)
async def test_out_of_range_values_are_rejected(client, bad):
    r = await client.post("/api/burnout/checkins", json={**TIRED, **bad})
    assert r.status_code == 422
    assert (await client.get("/api/burnout/checkins")).json() == []
