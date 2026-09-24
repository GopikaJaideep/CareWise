"""Tests for the orchestrator's routing and cycle protection logic."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext


class FakeAgent(BaseAgent):
    def __init__(self, name: AgentName, content: str = "ok", handoff: AgentName | None = None):
        self.name = name
        self.description = "test"
        self.system_prompt = ""
        self._content = content
        self._handoff = handoff

    async def handle(self, ctx: SessionContext) -> AgentResponse:
        return AgentResponse(agent=self.name, content=self._content, handoff_to=self._handoff)


class TestSessionContext:
    def test_visited_tracking(self):
        ctx = SessionContext(user_id=1, conversation_id=1, user_message="hi")
        assert not ctx.has_visited(AgentName.EMOTIONAL_SUPPORT)

        ctx.append_output(AgentResponse(agent=AgentName.EMOTIONAL_SUPPORT, content="hi"))
        assert ctx.has_visited(AgentName.EMOTIONAL_SUPPORT)
        assert len(ctx.agent_outputs) == 1


class TestOrchestratorCycleDetection:
    """Direct test of the loop logic in Orchestrator.run."""

    @pytest.mark.asyncio
    async def test_handoff_executes_once(self):
        from app.agents.orchestrator import MAX_HOPS, Orchestrator

        orch = Orchestrator.__new__(Orchestrator)
        orch.llm = type("NoModel", (), {"provider": None})()  # risk screen skips without a model
        orch.agents = {
            AgentName.EMOTIONAL_SUPPORT: FakeAgent(
                AgentName.EMOTIONAL_SUPPORT, content="", handoff=AgentName.SAFETY,
            ),
            AgentName.SAFETY: FakeAgent(AgentName.SAFETY, content="crisis resources"),
        }
        orch._classify_intent = AsyncMock(return_value=AgentName.EMOTIONAL_SUPPORT)

        ctx = SessionContext(user_id=1, conversation_id=1, user_message="normal message")
        responses = await orch.run(ctx)

        agents_visited = [r.agent for r in responses]
        assert AgentName.EMOTIONAL_SUPPORT in agents_visited
        assert AgentName.SAFETY in agents_visited

    @pytest.mark.asyncio
    async def test_cycle_breaks(self):
        """If two agents try to hand off to each other, the orchestrator stops."""
        from app.agents.orchestrator import Orchestrator

        orch = Orchestrator.__new__(Orchestrator)
        orch.llm = type("NoModel", (), {"provider": None})()  # risk screen skips without a model
        orch.agents = {
            AgentName.EMOTIONAL_SUPPORT: FakeAgent(
                AgentName.EMOTIONAL_SUPPORT, handoff=AgentName.RESOURCE_GUIDE,
            ),
            AgentName.RESOURCE_GUIDE: FakeAgent(
                AgentName.RESOURCE_GUIDE, handoff=AgentName.EMOTIONAL_SUPPORT,
            ),
        }
        orch._classify_intent = AsyncMock(return_value=AgentName.EMOTIONAL_SUPPORT)

        ctx = SessionContext(user_id=1, conversation_id=1, user_message="anything")
        responses = await orch.run(ctx)

        # Each agent should appear at most once
        agent_counts = {}
        for r in responses:
            agent_counts[r.agent] = agent_counts.get(r.agent, 0) + 1
        assert all(c == 1 for c in agent_counts.values())

    @pytest.mark.asyncio
    async def test_crisis_short_circuits_to_safety(self):
        """A crisis message bypasses normal routing entirely."""
        from app.agents.orchestrator import Orchestrator

        orch = Orchestrator.__new__(Orchestrator)
        orch.llm = type("NoModel", (), {"provider": None})()  # risk screen skips without a model
        orch.agents = {
            AgentName.SAFETY: FakeAgent(AgentName.SAFETY, content="crisis"),
            AgentName.EMOTIONAL_SUPPORT: FakeAgent(AgentName.EMOTIONAL_SUPPORT, content="should not run"),
        }
        # Even if classifier returns something else, crisis check fires first
        orch._classify_intent = AsyncMock(return_value=AgentName.EMOTIONAL_SUPPORT)

        ctx = SessionContext(
            user_id=1, conversation_id=1,
            user_message="I want to kill myself",
        )
        responses = await orch.run(ctx)

        assert len(responses) == 1
        assert responses[0].agent == AgentName.SAFETY
