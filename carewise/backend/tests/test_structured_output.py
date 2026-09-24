"""Validated structured output (with one repair retry), and several requests in one message."""
import json

import httpx
import pytest
from pydantic import ValidationError

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.agents.orchestrator import Orchestrator
from app.agents.outputs import CheckinExtraction, RouteDecision, TaskExtraction
from app.services import llm
from tests.fakes import StructuredFromJson


def gemini(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}


def client_answering(monkeypatch, *replies):
    """A real LLMClient whose HTTP calls return these replies in order; records what it was sent."""
    sent = []
    queue = list(replies)

    def handler(request):
        sent.append(json.loads(request.content))
        reply = queue.pop(0)
        return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=gemini(reply))

    real = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return llm.LLMClient(provider="gemini", api_key="k", model="gemini-3.6-flash"), sent


# --- complete_structured -------------------------------------------------------------------------

async def test_valid_reply_needs_one_call(monkeypatch):
    client, sent = client_answering(monkeypatch, '{"intents": [{"agent": "symptom_tracker", "text": "x"}]}')
    result = await client.complete_structured("route", [{"role": "user", "content": "x"}], RouteDecision)
    assert result.intents[0].agent == "symptom_tracker" and len(sent) == 1


async def test_invalid_reply_is_repaired_once_with_the_validation_errors(monkeypatch):
    client, sent = client_answering(
        monkeypatch,
        '{"intents": [{"agent": "doctor_bot"}]}',  # not a real agent
        '{"intents": [{"agent": "resource_guide"}]}',
    )
    result = await client.complete_structured("route", [{"role": "user", "content": "x"}], RouteDecision)
    assert result.intents[0].agent == "resource_guide" and len(sent) == 2
    repair_request = sent[1]["contents"][-1]["parts"][0]["text"]
    assert "didn't match the schema" in repair_request and "intents.0.agent" in repair_request


async def test_still_invalid_after_repair_returns_none(monkeypatch):
    client, sent = client_answering(monkeypatch, "not json", '{"intents": []}')
    assert await client.complete_structured("route", [{"role": "user", "content": "x"}], RouteDecision) is None
    assert len(sent) == 2  # exactly one repair, never a loop


async def test_a_failed_call_is_not_repaired(monkeypatch):
    monkeypatch.setattr(llm.asyncio, "sleep", lambda *_: _noop())
    client, sent = client_answering(monkeypatch, *[httpx.Response(429, json={"error": {"message": "quota"}})] * 3)
    assert await client.complete_structured("route", [{"role": "user", "content": "x"}], RouteDecision) is None
    assert len(sent) == 3  # the client's own 429 retries, but no repair call on top


async def _noop():
    return None


# --- Output models ----------------------------------------------------------------------------------

def test_route_decision_accepts_the_single_agent_form():
    decision = RouteDecision.model_validate({"agent": "care_coordinator", "reason": "task"})
    assert [(i.agent, i.text) for i in decision.intents] == [("care_coordinator", "")]


def test_route_decision_rejects_unknown_agents_and_empty_intents():
    with pytest.raises(ValidationError):
        RouteDecision.model_validate({"intents": [{"agent": "doctor_bot"}]})
    with pytest.raises(ValidationError):
        RouteDecision.model_validate({"intents": []})


def test_checkin_numbers_out_of_range_become_missing():
    c = CheckinExtraction.model_validate(
        {"sleep_hours": 30, "stress_level": 15, "energy_level": "4", "self_care_minutes": -5, "is_checkin": "true"})
    assert (c.sleep_hours, c.stress_level, c.energy_level, c.self_care_minutes, c.is_checkin) == (None, None, 4, None, True)


def test_task_category_and_nulls_are_cleaned_up():
    t = TaskExtraction.model_validate({"tasks": [{"title": "Scan", "category": "Medical"}], "mark_done": None, "query": "?"})
    assert t.tasks[0].category == "general" and t.mark_done == [] and t.query is None


# --- Several requests in one message ------------------------------------------------------------------

class RoutingModel(StructuredFromJson):
    provider, model = "fake", "fake"

    def __init__(self, decision):
        self.decision = decision
        self.routed = 0

    async def complete_json(self, system, messages, schema_hint, max_tokens=None):
        if "screen messages" in system:
            return {"level": "none"}
        self.routed += 1
        return self.decision

    async def complete(self, system, messages, **kwargs):
        return "ok"


class Recorder(BaseAgent):
    def __init__(self, name):
        self.name, self.description, self.system_prompt = name, "", ""
        self.messages = []

    async def handle(self, ctx):
        self.messages.append(ctx.user_message)
        return AgentResponse(agent=self.name, content=f"{self.name.value} done")


def orchestrator(decision):
    orch = Orchestrator.__new__(Orchestrator)
    orch.llm = RoutingModel(decision)
    orch.agents = {name: Recorder(name) for name in AgentName}
    return orch


def ctx(message):
    return SessionContext(user_id=1, conversation_id=1, user_message=message)


MESSAGE = "Mum's nausea was a 6 this morning. Also remind me chemo is Tuesday at 10."


async def test_two_requests_run_two_agents_each_on_its_own_part():
    orch = orchestrator({"intents": [
        {"agent": "symptom_tracker", "text": "Mum's nausea was a 6 this morning."},
        {"agent": "care_coordinator", "text": "remind me chemo is Tuesday at 10."},
    ]})
    responses = await orch.run(ctx(MESSAGE))
    assert [r.agent for r in responses] == [AgentName.SYMPTOM_TRACKER, AgentName.CARE_COORDINATOR]
    assert orch.agents[AgentName.SYMPTOM_TRACKER].messages == ["Mum's nausea was a 6 this morning."]
    assert orch.agents[AgentName.CARE_COORDINATOR].messages == ["remind me chemo is Tuesday at 10."]
    assert Orchestrator.synthesize(responses) == "symptom_tracker done\n\ncare_coordinator done"


async def test_a_shortcut_word_cannot_swallow_a_second_request():
    # "remind me" is a care-coordinator shortcut, but this message has two sentences, so it goes
    # to the model router (which sees both requests) instead.
    orch = orchestrator({"intents": [{"agent": "symptom_tracker", "text": "a"}, {"agent": "care_coordinator", "text": "b"}]})
    await orch.run(ctx(MESSAGE))
    assert orch.llm.routed == 1


async def test_single_sentence_shortcut_still_skips_the_model():
    orch = orchestrator({"intents": [{"agent": "symptom_tracker"}]})
    responses = await orch.run(ctx("Remind me chemo is Tuesday at 10"))
    assert [r.agent for r in responses] == [AgentName.CARE_COORDINATOR] and orch.llm.routed == 0


async def test_emotional_support_always_sees_the_whole_message():
    orch = orchestrator({"intents": [
        {"agent": "emotional_support", "text": "I'm overwhelmed."},
        {"agent": "care_coordinator", "text": "Add chemo Tuesday."},
    ]})
    await orch.run(ctx("I'm overwhelmed. Add chemo Tuesday."))
    assert orch.agents[AgentName.EMOTIONAL_SUPPORT].messages == ["I'm overwhelmed. Add chemo Tuesday."]
    assert orch.agents[AgentName.CARE_COORDINATOR].messages == ["Add chemo Tuesday."]


async def test_one_intent_gets_the_whole_message_and_duplicates_run_once():
    single = orchestrator({"intents": [{"agent": "symptom_tracker", "text": "just part"}]})
    await single.run(ctx("Pain 7 today, and nausea 4"))
    assert single.agents[AgentName.SYMPTOM_TRACKER].messages == ["Pain 7 today, and nausea 4"]

    duplicate = orchestrator({"intents": [{"agent": "symptom_tracker", "text": "a"}, {"agent": "symptom_tracker", "text": "b"}]})
    responses = await duplicate.run(ctx("Pain 7. Nausea 4."))
    assert [r.agent for r in responses] == [AgentName.SYMPTOM_TRACKER]


async def test_unusable_router_output_falls_back_to_emotional_support():
    responses = await orchestrator({"nonsense": True}).run(ctx("hello there"))
    assert [r.agent for r in responses] == [AgentName.EMOTIONAL_SUPPORT]
