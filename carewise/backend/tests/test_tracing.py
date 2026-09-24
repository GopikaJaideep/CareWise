"""Per-turn tracing: routing, agents, model calls and tokens, without message text."""
import json
import logging

import httpx
import pytest
from fastapi import FastAPI

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.agents.orchestrator import Orchestrator
from app.core.tracing import start_trace, step
from app.services import llm
from tests.fakes import StructuredFromJson


def gemini_reply(text, usage=None):
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
        "usageMetadata": usage or {"promptTokenCount": 40, "candidatesTokenCount": 12, "thoughtsTokenCount": 0},
    }


async def test_model_calls_are_recorded_with_step_tokens_and_latency(monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=gemini_reply("hi"))), **kw))
    client = llm.LLMClient(provider="gemini", api_key="k", model="gemini-3.6-flash")
    with start_trace() as trace:
        with step("symptom_tracker"):
            await client.complete("sys", [{"role": "user", "content": "x"}])
    (call,) = trace.calls
    assert (call.step, call.provider, call.model, call.ok) == ("symptom_tracker", "gemini", "gemini-3.6-flash", True)
    assert (call.input_tokens, call.output_tokens, call.thinking_tokens) == (40, 12, 0)
    assert call.latency_ms >= 0 and trace.total_ms is not None


async def test_calls_outside_a_turn_are_not_recorded(monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=gemini_reply("hi"))), **kw))
    client = llm.LLMClient(provider="gemini", api_key="k", model="gemini-3.6-flash")
    assert await client.complete("sys", [{"role": "user", "content": "x"}]) == "hi"  # no trace: no error


def test_summary_totals_tokens_and_reports_no_cost_without_prices(monkeypatch):
    from app.core import tracing

    monkeypatch.setattr(tracing.get_settings(), "llm_price_input_per_mtok", None)
    with start_trace() as trace:
        tracing.record_call(provider="gemini", model="m", latency_ms=100, input_tokens=100, output_tokens=20, thinking_tokens=5)
        tracing.record_call(provider="gemini", model="m", latency_ms=50, input_tokens=10, output_tokens=2)
    s = trace.summary()
    assert s["tokens"] == {"input": 110, "output": 22, "thinking": 5}
    assert s["model_ms"] == 150 and s["cost_usd"] is None


def test_cost_is_estimated_only_when_prices_are_configured(monkeypatch):
    from app.core import tracing

    settings = tracing.get_settings()
    monkeypatch.setattr(settings, "llm_price_input_per_mtok", 1.0)
    monkeypatch.setattr(settings, "llm_price_output_per_mtok", 4.0)
    # 1M input tokens at $1 + 0.5M output (incl. thinking) at $4
    assert tracing.estimate_cost(1_000_000, 500_000) == pytest.approx(3.0)


class FakeAgent(BaseAgent):
    def __init__(self, name, metadata=None):
        self.name, self.description, self.system_prompt = name, "", ""
        self._metadata = metadata or {}

    async def handle(self, ctx):
        return AgentResponse(agent=self.name, content="ok", metadata=self._metadata)


async def test_orchestrator_records_route_method_agents_and_retrieval():
    orch = Orchestrator.__new__(Orchestrator)
    orch.llm = type("NoModel", (), {"provider": None})()
    orch.agents = {AgentName.RESOURCE_GUIDE: FakeAgent(
        AgentName.RESOURCE_GUIDE, {"retrieval_mode": "keyword", "retrieved": [{"id": "fatigue#1"}]})}
    with start_trace() as trace:
        await orch.run(SessionContext(user_id=1, conversation_id=1, user_message="What helps with fatigue?"))
    s = trace.summary()
    assert (s["route"], s["route_method"], s["agents"]) == ("resource_guide", "demo-fallback", ["resource_guide"])
    assert s["retrieval"] == {"mode": "keyword", "sections": ["fatigue#1"]}


async def test_chat_turn_returns_trace_and_logs_it_without_message_text(db, monkeypatch, caplog):
    from app.api import chat_routes
    from app.core.auth import get_current_user
    from app.core.database import get_db
    from app.models.db import User

    class DemoModel(StructuredFromJson):
        provider, model = None, "none"

        async def complete(self, system, messages, **kw):
            return "demo"

        async def complete_json(self, system, messages, schema_hint, max_tokens=None):
            return {}

    monkeypatch.setattr(llm, "_client", DemoModel())
    app = FastAPI()
    app.include_router(chat_routes.router)

    async def current_user():
        return await db.get(User, 1)

    async def session():
        yield db

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db] = session
    # A question, so it reaches the resource guide and retrieves the nausea article.
    secret_text = "How can we manage her nausea during chemo?"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        with caplog.at_level(logging.INFO, logger="app.api.chat_routes"):
            r = await c.post("/api/chat", json={"message": secret_text})
        history = await c.get(f"/api/chat/conversations/{r.json()['conversation_id']}")
    assert r.status_code == 200
    turn = r.json()["turn"]
    assert turn["route_method"] == "demo-fallback" and turn["total_ms"] is not None
    assert any(s.startswith("nausea#") for s in turn["retrieval"]["sections"])  # full detail for the user

    lines = [rec.getMessage() for rec in caplog.records if rec.getMessage().startswith("chat_turn ")]
    assert len(lines) == 1
    logged = json.loads(lines[0].removeprefix("chat_turn "))
    assert logged["route"] == turn["route"]
    # The log line has neither the message nor which health article it matched.
    assert secret_text not in lines[0] and "nausea" not in lines[0]
    assert logged["retrieval"]["sections"] == len(turn["retrieval"]["sections"])

    # The trace is saved with the reply and comes back with the conversation history.
    assistant = [m for m in history.json()["messages"] if m["role"] == "assistant"][0]
    assert assistant["turn"]["route"] == turn["route"]
