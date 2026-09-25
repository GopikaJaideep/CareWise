"""Regression tests for bugs found reviewing every agent. Each test failed before its fix."""
import pytest
from sqlalchemy import select

from app.agents.base import AgentName, SessionContext
from app.agents.care_coordinator import CareCoordinatorAgent
from app.agents.orchestrator import Orchestrator
from app.agents.symptom_tracker import SymptomTrackerAgent, parse_severity
from app.core.safety import detect_crisis
from app.models.db import CareTask, SymptomLog
from tests.fakes import StructuredFromJson


class FakeLLM(StructuredFromJson):
    """Scripted stand-in for the LLM client; records what each call was sent."""

    provider = "fake"

    def __init__(self, json_reply=None, text_reply="ok"):
        self.json_reply = json_reply or {}
        self.text_reply = text_reply
        self.json_calls = []
        self.text_calls = []

    async def complete_json(self, system, messages, schema_hint, max_tokens=None):
        self.json_calls.append(messages)
        return self.json_reply

    async def complete(self, system, messages, **kwargs):
        self.text_calls.append({"system": system, "messages": messages})
        return self.text_reply


def ctx(message, **kwargs):
    return SessionContext(user_id=1, conversation_id=1, user_message=message, **kwargs)


def orchestrator(json_reply):
    orch = Orchestrator.__new__(Orchestrator)
    orch.llm = FakeLLM(json_reply)
    return orch


# --- Safety -------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "message",
    [
        "I'm feeling suicidal",
        "I wish I was dead",
        "honestly everyone would be better off without me",
        "I don't want to be here anymore",
        "I don’t want to live like this",  # curly apostrophe
        "i dont want to wake up tomorrow",
        "I've thought about an overdose",
    ],
)
def test_common_crisis_phrasings_trigger_the_safety_response(message):
    assert detect_crisis(message).requires_intervention


def test_crisis_setting_cannot_switch_off_core_phrases(monkeypatch):
    from app.core import safety

    monkeypatch.setattr(safety.settings, "crisis_keywords", "some other phrase")
    assert detect_crisis("I want to kill myself").requires_intervention


def test_everyday_caregiving_language_is_not_a_crisis():
    assert not detect_crisis("Mum had nausea this morning and I'm exhausted").requires_intervention


@pytest.mark.parametrize(
    "message",
    [
        # Missed in a live test while the AI risk screen was down: only the keyword check was left.
        "I've been saving up her sleeping pills, just in case it all gets too much.",
        "He's been stockpiling his morphine.",
        "I've got a stash of tablets put aside.",
        "I took a lot more of my sleeping pills than I should have tonight.",
        "I've taken way too many of my tablets",
        "I keep thinking about taking all my pills at once.",
        "I've been thinking about ending my life.",
        "I'd rather be dead than keep living like this.",
    ],
)
def test_method_and_indirect_language_triggers_the_safety_response(message):
    check = detect_crisis(message)
    assert check.requires_intervention and not check.someone_else


@pytest.mark.parametrize(
    "message",
    [
        "I'm saving up for her medications, they're expensive.",  # money, not stockpiling
        "She has to take all her pills with food or she gets sick.",
        "I collected her tablets from the pharmacy.",
        "I took all my tablets this morning like the doctor said.",
        "She took too much of her painkillers by mistake and the GP adjusted the dose.",
        "She fell and hurt herself in the garden.",
        "We talked with the team about voluntary assisted dying to end her life peacefully.",
    ],
)
def test_near_misses_are_not_a_crisis(message):
    assert not detect_crisis(message).requires_intervention


async def test_someone_else_at_risk_gets_the_reply_for_helping_them():
    from app.agents.safety import SafetyAgent
    from app.core.safety import _format_third_party_crisis_response

    check = detect_crisis("Mum said she wants to kill herself and I don't know what to do.")
    assert check.requires_intervention and check.someone_else
    response = await SafetyAgent().handle(ctx("Mum said she wants to kill herself and I don't know what to do."))
    assert response.content == _format_third_party_crisis_response()
    # If the writer is at risk too, their reply comes first.
    assert not detect_crisis("I want to die, and mum said she wants to kill herself.").someone_else


def test_a_failed_reply_still_says_where_to_get_help():
    # When the model is down the AI risk screen usually is too, so this message may be all a
    # person in crisis sees.
    from app.services.llm import ERROR_MESSAGE

    assert "000" in ERROR_MESSAGE and "13 11 14" in ERROR_MESSAGE


# --- Routing ------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "message",
    [
        "What is caregiver burnout and what helps?",  # used to start a check-in
        "How can I prepare for an oncology appointment?",  # used to go to the task agent
    ],
)
async def test_information_questions_skip_the_keyword_shortcuts(message):
    orch = orchestrator({"agent": "resource_guide"})
    assert await orch._classify_intent(ctx(message)) == AgentName.RESOURCE_GUIDE
    assert orch.llm.json_calls, "should have been classified by the model, not a shortcut"


async def test_requests_still_use_the_shortcuts():
    orch = orchestrator({"agent": "emotional_support"})
    assert await orch._classify_intent(ctx("Add: oncology appointment Tuesday at 10am")) == AgentName.CARE_COORDINATOR
    assert await orch._classify_intent(ctx("Run a burnout check-in")) == AgentName.BURNOUT_MONITOR
    assert orch.llm.json_calls == []


@pytest.mark.parametrize("reply", ["6 hours, stress 7, energy 4, 20 minutes", "yes", "Sure!"])
async def test_answers_to_the_burnout_questions_go_back_to_the_burnout_monitor(reply):
    orch = orchestrator({"agent": "symptom_tracker"})
    routed = await orch._classify_intent(ctx(reply, metadata={"last_agent": "burnout_monitor"}))
    assert routed == AgentName.BURNOUT_MONITOR


async def test_router_sees_recent_turns():
    orch = orchestrator({"agent": "emotional_support"})
    history = [{"role": "user", "content": f"turn {i}"} for i in range(10)]
    await orch._classify_intent(ctx("and another thing", history=history))
    sent = orch.llm.json_calls[0]
    assert sent[-1]["content"] == "and another thing"
    assert [m["content"] for m in sent[:-1]] == ["turn 6", "turn 7", "turn 8", "turn 9"]


# --- Care coordinator ---------------------------------------------------------------------------

@pytest.mark.parametrize("fragment", ["", " ", "a", "%", "_"])
async def test_mark_done_never_completes_every_task(db, fragment):
    db.add_all([CareTask(user_id=1, title="Chemo Tuesday"), CareTask(user_id=1, title="Pharmacy pickup")])
    await db.commit()
    agent = CareCoordinatorAgent(db)
    agent.llm = FakeLLM({"tasks": [], "mark_done": [fragment]})
    await agent.handle(ctx("done"))
    done = (await db.execute(select(CareTask).where(CareTask.completed.is_(True)))).scalars().all()
    assert done == []


async def test_mark_done_still_completes_the_named_task(db):
    db.add_all([CareTask(user_id=1, title="Chemo Tuesday"), CareTask(user_id=1, title="Pharmacy pickup")])
    await db.commit()
    agent = CareCoordinatorAgent(db)
    agent.llm = FakeLLM({"tasks": [], "mark_done": ["pharmacy"]})
    await agent.handle(ctx("picked up the prescription"))
    done = (await db.execute(select(CareTask.title).where(CareTask.completed.is_(True)))).scalars().all()
    assert done == ["Pharmacy pickup"]


async def test_unknown_task_category_falls_back_to_general(db):
    agent = CareCoordinatorAgent(db)
    agent.llm = FakeLLM({"tasks": [{"title": "Scan", "category": "Medical-ish"}]})
    await agent.handle(ctx("add scan"))
    task = (await db.execute(select(CareTask))).scalar_one()
    assert task.category == "general"


async def test_care_reply_is_told_when_nothing_was_saved(db):
    agent = CareCoordinatorAgent(db)
    agent.llm = FakeLLM({"tasks": []})
    await agent.handle(ctx("can you sort out her appointments"))
    assert "Nothing was added" in agent.llm.text_calls[-1]["system"]


# --- Symptom tracker ----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value, expected",
    [(6, 6), ("6", 6), ("6/10", 6), (6.4, 6), ("7.5", 8), (0, None), (15, None), ("really bad", None), (None, None), (True, None)],
)
def test_parse_severity(value, expected):
    assert parse_severity(value) == expected


async def test_unparseable_severity_does_not_crash_the_chat(db):
    agent = SymptomTrackerAgent(db)
    agent.llm = FakeLLM({"symptoms": [{"symptom": "pain", "severity": "6/10"}]})
    response = await agent.handle(ctx("pain about 6/10"))
    assert response.metadata["logged"] == ["pain (6/10)"]


async def test_symptom_reply_is_told_when_nothing_was_logged(db):
    agent = SymptomTrackerAgent(db)
    agent.llm = FakeLLM({"symptoms": [{"symptom": "pain", "severity": None}]})
    response = await agent.handle(ctx("Mum's pain is really bad today"))
    assert response.metadata["logged"] == []
    assert "Nothing was logged" in agent.llm.text_calls[-1]["system"]
    assert (await db.execute(select(SymptomLog))).scalars().all() == []


async def test_symptom_questions_are_answered_from_the_saved_records(db):
    db.add(SymptomLog(user_id=1, symptom="nausea", severity=6))
    await db.commit()
    agent = SymptomTrackerAgent(db)
    agent.llm = FakeLLM({"query": "list_symptoms"})
    await agent.handle(ctx("What symptoms have we logged this week?"))
    assert "nausea 6/10" in agent.llm.text_calls[-1]["messages"][0]["content"]


async def test_symptom_question_with_no_records_says_so_without_the_model(db):
    agent = SymptomTrackerAgent(db)
    agent.llm = FakeLLM({"query": "list_symptoms"})
    response = await agent.handle(ctx("What have we logged?"))
    assert "Nothing has been logged" in response.content
    assert agent.llm.text_calls == []


async def test_without_a_model_questions_reach_the_resource_guide():
    orch = orchestrator({})
    orch.llm.provider = None
    assert await orch._classify_intent(ctx("How can we manage nausea during chemo?")) == AgentName.RESOURCE_GUIDE
    assert await orch._classify_intent(ctx("I had such a hard day")) == AgentName.EMOTIONAL_SUPPORT
