"""Orchestrator — routes user messages to specialized agents.

Architecture:
1. Pre-flight safety check (deterministic, no LLM call)
2. Intent classification (LLM call → AgentName)
3. Agent invocation
4. Handoff handling with cycle detection (max 3 hops per turn)
5. Response synthesis if multiple agents contributed
"""
from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.agents.burnout_monitor import BurnoutMonitorAgent
from app.agents.care_coordinator import CareCoordinatorAgent
from app.agents.emotional_support import EmotionalSupportAgent
from app.agents.resource_guide import ResourceGuideAgent
from app.agents.safety import SafetyAgent
from app.agents.symptom_tracker import SymptomTrackerAgent
from app.core.safety import detect_crisis
from app.services.llm import get_llm_client

logger = logging.getLogger(__name__)

MAX_HOPS = 3


INTENT_SYSTEM = """You are the routing layer for CareWise, an AI companion for cancer caregivers.

Classify the user's message into ONE primary intent. Return JSON: {"agent": "<name>", "confidence": float, "reason": "brief"}

Available agents:
- "emotional_support": caregiver expressing feelings, venting, struggling, processing grief/fear/anger/guilt
- "symptom_tracker": logging symptoms or medications, asking about a logged symptom history
- "care_coordinator": adding/listing/completing tasks, appointments, reminders
- "resource_guide": asking for information about a symptom/condition/treatment in general (NOT logging)
- "burnout_monitor": doing a check-in on their own wellbeing, or asking how they're doing

If unclear, prefer "emotional_support" — it's the safest default.
"""


class Orchestrator:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.llm = get_llm_client()
        self.agents: dict[AgentName, BaseAgent] = {
            AgentName.EMOTIONAL_SUPPORT: EmotionalSupportAgent(),
            AgentName.SYMPTOM_TRACKER: SymptomTrackerAgent(db),
            AgentName.CARE_COORDINATOR: CareCoordinatorAgent(db),
            AgentName.RESOURCE_GUIDE: ResourceGuideAgent(),
            AgentName.BURNOUT_MONITOR: BurnoutMonitorAgent(db),
            AgentName.SAFETY: SafetyAgent(),
        }

    async def run(self, ctx: SessionContext) -> list[AgentResponse]:
        """Run the orchestration loop. Returns the ordered list of agent responses."""
        # 1. Pre-flight safety check — never depends on LLM
        crisis = detect_crisis(ctx.user_message)
        if crisis.requires_intervention:
            logger.warning(
                "Crisis content detected for user_id=%s, triggers=%s",
                ctx.user_id, crisis.triggers,
            )
            response = await self.agents[AgentName.SAFETY].handle(ctx)
            ctx.append_output(response)
            return ctx.agent_outputs

        # 2. Intent classification
        primary = await self._classify_intent(ctx)
        logger.info("Routing user_id=%s to agent=%s", ctx.user_id, primary.value)

        # 3. Invocation loop with cycle protection
        current = primary
        hops = 0
        while current is not None and hops < MAX_HOPS:
            if ctx.has_visited(current):
                logger.warning("Cycle detected: %s already visited. Halting handoff loop.", current.value)
                break

            agent = self.agents[current]
            response = await agent.handle(ctx)
            ctx.append_output(response)

            # If the agent yielded an empty response and a handoff, follow the handoff
            current = response.handoff_to
            hops += 1

        return ctx.agent_outputs

    async def _classify_intent(self, ctx: SessionContext) -> AgentName:
        # Quick heuristic shortcuts (cheap, deterministic)
        msg = ctx.user_message.lower()
        if any(kw in msg for kw in ["check in", "check-in", "how am i doing", "burnout"]):
            return AgentName.BURNOUT_MONITOR
        if any(kw in msg for kw in ["remind me", "appointment", "add task", "to-do", "todo"]):
            return AgentName.CARE_COORDINATOR

        # LLM-based classification for the harder cases
        result = await self.llm.complete_json(
            system=INTENT_SYSTEM,
            messages=[{"role": "user", "content": ctx.user_message}],
            schema_hint='{"agent": str, "confidence": float, "reason": str}',
        )
        agent_str = result.get("agent", "emotional_support")
        try:
            return AgentName(agent_str)
        except ValueError:
            logger.warning("Unknown agent from classifier: %s, defaulting to emotional_support", agent_str)
            return AgentName.EMOTIONAL_SUPPORT

    @staticmethod
    def synthesize(responses: Iterable[AgentResponse]) -> str:
        """If multiple agents contributed, join their outputs cleanly."""
        non_empty = [r for r in responses if r.content.strip()]
        if not non_empty:
            return "I'm not sure how to help with that yet — could you tell me a bit more?"
        if len(non_empty) == 1:
            return non_empty[0].content
        return "\n\n---\n\n".join(r.content for r in non_empty)
