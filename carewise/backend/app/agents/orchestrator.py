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
import re
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

Earlier turns may be included for context. Classify the LAST user message: a short reply such as
"6 hours, stress 7" or "yes" belongs to whatever the assistant just asked about.
"""

# Messages that ask for information, rather than asking CareWise to do something. They skip the
# keyword shortcuts below, so "What is caregiver burnout?" reaches the resource guide instead of
# starting a check-in, and "How do I prepare for an appointment?" doesn't create a task.
_QUESTION = re.compile(
    r"^\s*(what|how|why|when|where|who|which|is|are|can|could|should|would|does|do|will)\b", re.I
)
_AFFIRMATIVE = {"yes", "yeah", "yep", "sure", "ok", "okay", "please", "yes please", "go on", "lets do it"}
HISTORY_TURNS_FOR_ROUTING = 4


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
        msg = ctx.user_message.lower().strip()

        # 1. Answering a check-in the burnout monitor just asked for: numbers, or "yes" to its offer.
        #    Without this the reply ("6 hours, stress 7...") was classified alone and often went to
        #    the symptom tracker.
        if ctx.metadata.get("last_agent") == AgentName.BURNOUT_MONITOR.value and (
            len(re.findall(r"\d+", msg)) >= 2 or msg.rstrip(".!") in _AFFIRMATIVE
        ):
            return AgentName.BURNOUT_MONITOR

        # 2. Cheap deterministic shortcuts, for requests only (see _QUESTION).
        is_question = bool(_QUESTION.match(msg))
        if any(kw in msg for kw in ["check in", "check-in", "checkin", "how am i doing"]):
            return AgentName.BURNOUT_MONITOR
        if not is_question and any(
            kw in msg for kw in ["remind me", "appointment", "add task", "add:", "to-do", "todo"]
        ):
            return AgentName.CARE_COORDINATOR

        # 3. LLM classification, with the last few turns so short replies have context.
        recent = ctx.history[-HISTORY_TURNS_FOR_ROUTING:]
        result = await self.llm.complete_json(
            system=INTENT_SYSTEM,
            messages=[*recent, {"role": "user", "content": ctx.user_message}],
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
