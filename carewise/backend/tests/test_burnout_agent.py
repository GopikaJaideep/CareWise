"""BurnoutMonitorAgent.handle: how extraction results are interpreted."""
from sqlalchemy import select

from app.agents.base import SessionContext
from app.agents.burnout_monitor import BurnoutMonitorAgent
from app.models.db import BurnoutCheckin


class FakeLLM:
    def __init__(self, extraction):
        self.extraction = extraction

    async def complete_json(self, **kwargs):
        return self.extraction

    async def complete(self, **kwargs):
        return "reflected reply"


def make_agent(db, extraction):
    agent = BurnoutMonitorAgent(db)
    agent.llm = FakeLLM(extraction)
    return agent


def ctx(message="Run a burnout check-in: 5 hours sleep, stress 8, energy 3, 0 minutes for me."):
    return SessionContext(user_id=1, conversation_id=1, user_message=message)


ALL_FIELDS = {"sleep_hours": 5, "stress_level": 8, "energy_level": 3, "self_care_minutes": 0}


async def saved_checkins(db):
    return list((await db.execute(select(BurnoutCheckin))).scalars())


async def test_records_checkin_when_flag_true(db):
    result = await make_agent(db, {**ALL_FIELDS, "is_checkin": True}).handle(ctx())
    assert result.content == "reflected reply"
    assert len(await saved_checkins(db)) == 1


async def test_records_checkin_even_if_model_sets_flag_false(db):
    # The message asks for a check-in *and* supplies the numbers.
    result = await make_agent(db, {**ALL_FIELDS, "is_checkin": False}).handle(ctx())
    assert result.content == "reflected reply"
    assert len(await saved_checkins(db)) == 1


async def test_partial_data_asks_for_the_missing_fields(db):
    result = await make_agent(db, {"sleep_hours": 5, "is_checkin": False}).handle(ctx("I slept 5 hours"))
    assert result.requires_followup
    assert set(result.metadata["missing_fields"]) == {"stress_level", "energy_level", "self_care_minutes"}
    assert await saved_checkins(db) == []


async def test_status_question_returns_trend_not_a_checkin(db):
    result = await make_agent(db, {"is_checkin": False}).handle(ctx("how am I doing?"))
    assert "No check-ins yet" in result.content
    assert await saved_checkins(db) == []


async def test_unparseable_extraction_falls_back_to_trend(db):
    result = await make_agent(db, {}).handle(ctx())
    assert "No check-ins yet" in result.content
    assert await saved_checkins(db) == []
