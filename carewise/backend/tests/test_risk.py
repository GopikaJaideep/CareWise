"""The AI risk screen: extra protection on top of the keyword check, never less."""
import asyncio
import time

import pytest

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.agents.orchestrator import CONCERN_NOTE, Orchestrator
from app.agents.safety import SafetyAgent
from app.core import risk as risk_module
from app.core.risk import UNKNOWN, assess_risk
from app.core.safety import _format_crisis_response, _format_third_party_crisis_response


class ScriptedModel:
    """Answers the risk screen and the router from scripts; can be slow or fail."""

    provider, model = "fake", "fake"

    def __init__(self, risk=None, route="emotional_support", delay=0.0, fail_risk=False):
        self.risk = {"level": "none"} if risk is None else risk
        self.route, self.delay, self.fail_risk = route, delay, fail_risk
        self.risk_calls = 0

    async def complete_json(self, system, messages, schema_hint, max_tokens=None):
        await asyncio.sleep(self.delay)
        if "screen messages" in system:
            self.risk_calls += 1
            if self.fail_risk:
                raise RuntimeError("quota exceeded")
            return self.risk
        return {"agent": self.route}

    async def complete(self, system, messages, **kwargs):
        return "ok"


class RecordingAgent(BaseAgent):
    def __init__(self, name):
        self.name, self.description, self.system_prompt = name, "", ""
        self.seen = []

    async def handle(self, ctx):
        self.seen.append(dict(ctx.metadata))
        return AgentResponse(agent=self.name, content=f"reply from {self.name.value}")


def orchestrator(model):
    orch = Orchestrator.__new__(Orchestrator)
    orch.llm = model
    orch.agents = {name: RecordingAgent(name) for name in AgentName if name != AgentName.SAFETY}
    orch.agents[AgentName.SAFETY] = SafetyAgent()
    return orch


def ctx(message):
    return SessionContext(user_id=1, conversation_id=1, user_message=message)


# --- assess_risk --------------------------------------------------------------------------------

async def test_parses_level_and_who():
    r = await assess_risk(ScriptedModel({"level": "crisis", "who": "care_recipient", "reason": "stockpiling"}), "x")
    assert (r.level, r.who) == ("crisis", "care_recipient")


@pytest.mark.parametrize("reply", [{}, {"level": "maybe"}, {"level": 3}])
async def test_unusable_output_means_unknown(reply):
    assert await assess_risk(ScriptedModel(reply), "x") == UNKNOWN


async def test_errors_and_no_model_mean_unknown():
    assert await assess_risk(ScriptedModel(fail_risk=True), "x") == UNKNOWN
    assert await assess_risk(type("NoModel", (), {"provider": None})(), "x") == UNKNOWN


async def test_a_hung_call_times_out_to_unknown(monkeypatch):
    monkeypatch.setattr(risk_module, "TIMEOUT_S", 0.05)
    assert await assess_risk(ScriptedModel({"level": "crisis"}, delay=1.0), "x") == UNKNOWN


# --- In the orchestrator ------------------------------------------------------------------------

async def test_screen_catches_a_crisis_the_keywords_miss():
    orch = orchestrator(ScriptedModel({"level": "crisis", "who": "self"}))
    (response,) = await orch.run(ctx("What's the point of living anymore?"))
    assert response.agent == AgentName.SAFETY
    assert response.content == _format_crisis_response()  # fixed text, never model-written
    assert response.metadata["detected_by"] == "ai_screen"


async def test_risk_to_the_person_being_cared_for_gets_the_third_party_response():
    orch = orchestrator(ScriptedModel({"level": "crisis", "who": "care_recipient"}))
    (response,) = await orch.run(ctx("Mum said she wants to kill herself and I don't know what to do."))
    assert response.content == _format_third_party_crisis_response()
    assert "stay with them" in response.content and response.metadata["at_risk"] == "someone_else"


async def test_keyword_crisis_never_waits_for_the_model():
    model = ScriptedModel({"level": "none"})
    (response,) = await orchestrator(model).run(ctx("I want to kill myself"))
    assert response.agent == AgentName.SAFETY and response.metadata["detected_by"] == "keyword"
    assert model.risk_calls == 0


async def test_screen_failure_falls_back_to_normal_routing():
    orch = orchestrator(ScriptedModel(fail_risk=True, route="symptom_tracker"))
    (response,) = await orch.run(ctx("Mum had nausea this morning, around a 6."))
    assert response.agent == AgentName.SYMPTOM_TRACKER


async def test_concern_reaches_emotional_support_as_context():
    orch = orchestrator(ScriptedModel({"level": "concern", "who": "self"}, route="emotional_support"))
    (response,) = await orch.run(ctx("I can't cope with any of this"))
    assert orch.agents[AgentName.EMOTIONAL_SUPPORT].seen[0]["risk_concern"] is True
    assert CONCERN_NOTE not in response.content  # emotional support handles it in its own words


async def test_concern_adds_a_gentle_note_to_a_task_reply():
    orch = orchestrator(ScriptedModel({"level": "concern"}, route="care_coordinator"))
    (response,) = await orch.run(ctx("Add chemo Tuesday, honestly I'm falling apart"))
    assert response.content.endswith(CONCERN_NOTE) and "13 11 14" in response.content


async def test_screen_runs_alongside_routing_not_after_it():
    orch = orchestrator(ScriptedModel({"level": "none"}, delay=0.3))
    start = time.perf_counter()
    await orch.run(ctx("I had a long day at the hospital"))
    # Router and screen each take 0.3s; in parallel the turn takes ~0.3s, not ~0.6s.
    assert time.perf_counter() - start < 0.5
