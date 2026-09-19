"""Caregiver-timezone handling: helpers, and the Care Coordinator's use of them."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.agents.base import SessionContext
from app.agents.care_coordinator import CareCoordinatorAgent
from app.core.tz import day_bounds_utc, parse_due_at, resolve_timezone, to_local, tz_label
from app.models.db import CareTask

SYDNEY = resolve_timezone("Australia/Sydney")  # UTC+10 in June, UTC+11 in summer (DST)
UTC = timezone.utc


class TestResolveTimezone:
    def test_valid_name(self):
        assert tz_label(resolve_timezone("Australia/Sydney")) == "Australia/Sydney"

    def test_missing_falls_back_to_utc(self):
        assert resolve_timezone(None) is UTC
        assert resolve_timezone("") is UTC

    def test_garbage_falls_back_to_utc(self):
        assert resolve_timezone("Not/AZone") is UTC
        assert resolve_timezone("../../etc/passwd") is UTC


class TestParseDueAt:
    def test_naive_value_is_local_wall_clock(self):
        # 10am Sydney (AEST, UTC+10) on 22 Jun == 00:00 UTC
        assert parse_due_at("2026-06-22T10:00:00", SYDNEY) == datetime(2026, 6, 22, 0, 0, tzinfo=UTC)

    def test_dst_offset_is_applied(self):
        # 22 Dec is AEDT (UTC+11): 10am local == 23:00 UTC the day before
        assert parse_due_at("2026-12-22T10:00:00", SYDNEY) == datetime(2026, 12, 21, 23, 0, tzinfo=UTC)

    def test_explicit_z_is_respected(self):
        assert parse_due_at("2026-06-22T10:00:00Z", SYDNEY) == datetime(2026, 6, 22, 10, 0, tzinfo=UTC)

    def test_explicit_offset_is_respected(self):
        assert parse_due_at("2026-06-22T10:00:00+10:00", UTC) == datetime(2026, 6, 22, 0, 0, tzinfo=UTC)

    def test_unknown_timezone_behaves_like_before(self):
        assert parse_due_at("2026-06-22T10:00:00", resolve_timezone(None)) == datetime(2026, 6, 22, 10, 0, tzinfo=UTC)

    def test_garbage_returns_none(self):
        assert parse_due_at("next tuesday", SYDNEY) is None
        assert parse_due_at(None, SYDNEY) is None


class TestDayBounds:
    def test_local_day_in_utc(self):
        # 5pm Sydney on 18 Jun == 07:00 UTC 18 Jun. Sydney's day is 14:00Z 17 Jun -> 14:00Z 18 Jun.
        start, end = day_bounds_utc(SYDNEY, datetime(2026, 6, 18, 7, 0, tzinfo=UTC))
        assert start == datetime(2026, 6, 17, 14, 0, tzinfo=UTC)
        assert end == datetime(2026, 6, 18, 14, 0, tzinfo=UTC)

    def test_dst_transition_day_is_23_hours(self):
        # Sydney springs forward on 4 Oct 2026 (02:00 -> 03:00): that local day is 23h long.
        start, end = day_bounds_utc(SYDNEY, datetime(2026, 10, 4, 0, 0, tzinfo=UTC))
        assert (end - start).total_seconds() == 23 * 3600

    def test_utc_is_unchanged(self):
        start, end = day_bounds_utc(UTC, datetime(2026, 6, 18, 7, 0, tzinfo=UTC))
        assert start == datetime(2026, 6, 18, 0, 0, tzinfo=UTC)
        assert end == datetime(2026, 6, 19, 0, 0, tzinfo=UTC)


class TestToLocal:
    def test_naive_from_sqlite_is_treated_as_utc(self):
        assert to_local(datetime(2026, 6, 22, 0, 0), SYDNEY).hour == 10


class RecordingLLM:
    def __init__(self, extraction):
        self.extraction = extraction
        self.system_prompts = []

    async def complete_json(self, system, **kwargs):
        self.system_prompts.append(system)
        return self.extraction

    async def complete(self, **kwargs):
        return "fallback"


def make_ctx(tz_name):
    return SessionContext(
        user_id=1, conversation_id=1, user_message="remind me she has chemo on Tuesday at 10",
        metadata={"timezone": tz_name} if tz_name else {},
    )


EXTRACTION = {"tasks": [{"title": "Chemo", "due_at": "2026-06-23T10:00:00", "category": "appointment"}]}


async def stored_due(db):
    return (await db.execute(select(CareTask))).scalar_one().due_at


async def test_chemo_at_10_is_saved_as_10_local_not_10_utc(db):
    agent = CareCoordinatorAgent(db)
    agent.llm = RecordingLLM(EXTRACTION)
    await agent.handle(make_ctx("Australia/Sydney"))
    due = await stored_due(db)
    # 10:00 Sydney (UTC+10) is 00:00 UTC — the bug stored 10:00 UTC.
    assert (due.hour, due.day) == (0, 23)


async def test_prompt_tells_the_model_the_users_timezone_and_local_time(db):
    agent = CareCoordinatorAgent(db)
    agent.llm = RecordingLLM(EXTRACTION)
    await agent.handle(make_ctx("Australia/Sydney"))
    prompt = agent.llm.system_prompts[0]
    assert "Australia/Sydney" in prompt
    assert "{now}" not in prompt and "{tz}" not in prompt


async def test_no_timezone_keeps_previous_utc_behaviour(db):
    agent = CareCoordinatorAgent(db)
    agent.llm = RecordingLLM(EXTRACTION)
    await agent.handle(make_ctx(None))
    assert (await stored_due(db)).hour == 10


async def test_unparseable_due_date_still_saves_the_task(db):
    agent = CareCoordinatorAgent(db)
    agent.llm = RecordingLLM({"tasks": [{"title": "Call GP", "due_at": "sometime soon"}]})
    result = await agent.handle(make_ctx("Australia/Sydney"))
    assert "Call GP" in result.content
    assert await stored_due(db) is None
