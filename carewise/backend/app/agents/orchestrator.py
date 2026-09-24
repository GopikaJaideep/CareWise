"""Orchestrator — routes user messages to specialized agents.

Architecture:
1. Pre-flight safety check (deterministic, no LLM call)
2. Intent classification (LLM call → AgentName)
3. Agent invocation
4. Handoff handling with cycle detection (max 3 hops per turn)
5. Response synthesis if multiple agents contributed
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.agents.burnout_monitor import BurnoutMonitorAgent
from app.agents.care_coordinator import CareCoordinatorAgent
from app.agents.emotional_support import EmotionalSupportAgent
from app.agents.outputs import RouteDecision
from app.agents.resource_guide import ResourceGuideAgent
from app.agents.safety import SafetyAgent
from app.agents.symptom_tracker import SymptomTrackerAgent
from app.core.risk import RiskAssessment, assess_risk
from app.core.safety import detect_crisis
from app.core.tracing import current_trace, step
from app.services.llm import get_llm_client

logger = logging.getLogger(__name__)

MAX_HOPS = 3


INTENT_SYSTEM = """You are the routing layer for CareWise, an AI companion for cancer caregivers.

List what the user's message asks for, as 1 to 3 intents in the order they appear. For each, give the
agent and the exact part of the message it should handle. Return JSON:
{"intents": [{"agent": "<name>", "text": "<that part of the message>"}], "reason": "brief"}

Most messages have ONE intent: return a single intent with the whole message as its text. Only list
more when the message clearly asks for separate things, e.g. "Mum's nausea was a 6 this morning. Also
remind me chemo is Tuesday at 10" is symptom_tracker ("Mum's nausea was a 6 this morning") then
care_coordinator ("remind me chemo is Tuesday at 10"). Feelings mentioned alongside a task are not a
separate intent unless the person is clearly asking to talk about them.

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
MAX_INTENTS = 3

# Agents that act on their own part of a multi-request message ("log X. add Y"). Emotional support
# always gets the whole message: feelings need the full context.
SPAN_AGENTS = {
    AgentName.SYMPTOM_TRACKER, AgentName.CARE_COORDINATOR, AgentName.BURNOUT_MONITOR, AgentName.RESOURCE_GUIDE,
}

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=\S)|\n+")


def _is_single_request(message: str) -> bool:
    """One sentence. Keyword shortcuts only apply then, so a shortcut word in one sentence can't
    swallow a separate request in another ("Pain is a 7. Remind me about Tuesday")."""
    return len([p for p in _SENTENCE_BREAK.split(message.strip()) if p.strip()]) <= 1

# Added (fixed text, not model-written) when the risk screen flags serious distress without
# a crisis and the reply came from an agent other than emotional support.
CONCERN_NOTE = (
    "It sounds like a lot right now. If you'd like to talk it through, I'm here. "
    "And Lifeline is available any time on 13 11 14."
)


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
            self._trace_route(AgentName.SAFETY, "safety")
            response = await self.agents[AgentName.SAFETY].handle(ctx)
            ctx.append_output(response)
            self._trace_agent(response)
            return ctx.agent_outputs

        # 2. Intent classification, with the AI risk screen running at the same time so it adds
        #    no wait. The screen can only add protection: the keyword check above always wins.
        screen = asyncio.create_task(self._screen_risk(ctx))
        with step("router"):
            intents = await self._route(ctx)
        primary = intents[0][0]
        risk = await screen
        self._trace_risk(risk)

        if risk.level == "crisis":
            logger.warning("AI risk screen flagged crisis for user_id=%s (who=%s)", ctx.user_id, risk.who)
            ctx.metadata["risk"] = {"who": risk.who}
            self._trace_route(AgentName.SAFETY, "safety-ai-screen")
            response = await self.agents[AgentName.SAFETY].handle(ctx)
            ctx.append_output(response)
            self._trace_agent(response)
            return ctx.agent_outputs
        if risk.level == "concern":
            ctx.metadata["risk_concern"] = True

        self._trace_route(primary, ctx.metadata.get("route_method"))
        if len(intents) > 1:
            trace = current_trace()
            if trace is not None:
                trace.extra["intents"] = [agent.value for agent, _ in intents]
        logger.info("Routing user_id=%s to %s", ctx.user_id, [agent.value for agent, _ in intents])

        # 3. Each intent in order, each with cycle-protected handoffs. A task agent sees only its
        #    part of the message, so "log nausea 6. add chemo Tuesday" doesn't log chemo as a symptom.
        for agent_name, text in intents:
            part = dataclasses.replace(ctx, user_message=text) if text and agent_name in SPAN_AGENTS else ctx
            current = agent_name
            hops = 0
            while current is not None and hops < MAX_HOPS:
                if ctx.has_visited(current):
                    logger.warning("Cycle detected: %s already visited. Halting handoff loop.", current.value)
                    break

                agent = self.agents[current]
                with step(current.value):
                    response = await agent.handle(part)
                ctx.append_output(response)
                self._trace_agent(response)

                # If the agent yielded an empty response and a handoff, follow the handoff
                current = response.handoff_to
                hops += 1

        # Serious distress, but the reply came from a task agent: add a gentle, fixed check-in.
        # (Emotional support handles it itself; see its prompt.)
        concern = ctx.metadata.get("risk_concern")
        if concern and ctx.agent_outputs and not ctx.has_visited(AgentName.EMOTIONAL_SUPPORT):
            last = ctx.agent_outputs[-1]
            last.content = f"{last.content.rstrip()}\n\n{CONCERN_NOTE}"
        return ctx.agent_outputs

    async def _screen_risk(self, ctx: SessionContext) -> RiskAssessment:
        with step("risk_screen"):
            return await assess_risk(self.llm, ctx.user_message, ctx.history)

    @staticmethod
    def _trace_risk(risk: RiskAssessment) -> None:
        trace = current_trace()
        if trace is not None:
            trace.extra["risk_screen"] = {"level": risk.level, "who": risk.who}

    @staticmethod
    def _trace_route(agent: AgentName, method: str | None) -> None:
        trace = current_trace()
        if trace is not None:
            trace.route, trace.route_method = agent.value, method

    @staticmethod
    def _trace_agent(response: AgentResponse) -> None:
        trace = current_trace()
        if trace is None:
            return
        trace.agents.append(response.agent.value)
        if "retrieval_mode" in response.metadata:  # resource guide: how it searched, what it found
            trace.extra["retrieval"] = {
                "mode": response.metadata["retrieval_mode"],
                "sections": [r["id"] for r in response.metadata.get("retrieved", [])],
            }

    async def _classify_intent(self, ctx: SessionContext) -> AgentName:
        """The first agent to handle the message (see _route)."""
        return (await self._route(ctx))[0][0]

    async def _route(self, ctx: SessionContext) -> list[tuple[AgentName, str]]:
        """The agents to run, in order, each with the part of the message it handles ("" = all
        of it). Records how it decided in ctx.metadata["route_method"]."""
        msg = ctx.user_message.lower().strip()
        single = _is_single_request(ctx.user_message)

        def method(name: str) -> None:
            ctx.metadata["route_method"] = name

        # 1. Answering a check-in the burnout monitor just asked for: numbers, or "yes" to its offer.
        #    Without this the reply ("6 hours, stress 7...") was classified alone and often went to
        #    the symptom tracker.
        if ctx.metadata.get("last_agent") == AgentName.BURNOUT_MONITOR.value and (
            len(re.findall(r"\d+", msg)) >= 2 or msg.rstrip(".!") in _AFFIRMATIVE
        ):
            method("follow-up")
            return [(AgentName.BURNOUT_MONITOR, "")]

        # 2. Cheap deterministic shortcuts, for single-sentence requests only (see _QUESTION and
        #    _is_single_request).
        is_question = bool(_QUESTION.match(msg))
        if single and any(kw in msg for kw in ["check in", "check-in", "checkin", "how am i doing"]):
            method("shortcut")
            return [(AgentName.BURNOUT_MONITOR, "")]
        if single and not is_question and any(
            kw in msg for kw in ["remind me", "appointment", "add task", "add:", "to-do", "todo"]
        ):
            method("shortcut")
            return [(AgentName.CARE_COORDINATOR, "")]

        # 3. No model (demo mode): questions go to the resource guide, which answers from the
        #    knowledge base without a model and says so when it has nothing relevant.
        if self.llm.provider is None:
            method("demo-fallback")
            return [(AgentName.RESOURCE_GUIDE if is_question else AgentName.EMOTIONAL_SUPPORT, "")]

        # 4. LLM classification, with the last few turns so short replies have context.
        recent = ctx.history[-HISTORY_TURNS_FOR_ROUTING:]
        decision = await self.llm.complete_structured(
            system=INTENT_SYSTEM,
            messages=[*recent, {"role": "user", "content": ctx.user_message}],
            output=RouteDecision,
        )
        method("model")
        if decision is None:
            logger.warning("Router output unusable; defaulting to emotional_support")
            return [(AgentName.EMOTIONAL_SUPPORT, "")]
        intents: list[tuple[AgentName, str]] = []
        for intent in decision.intents[:MAX_INTENTS]:
            agent = AgentName(intent.agent)
            if any(agent == seen for seen, _ in intents):
                continue  # the same agent twice: once is enough, with the first part
            # A single intent handles the whole message; only split when there are several.
            intents.append((agent, intent.text.strip() if len(decision.intents) > 1 else ""))
        return intents

    @staticmethod
    def synthesize(responses: Iterable[AgentResponse]) -> str:
        """If multiple agents contributed, join their outputs cleanly."""
        non_empty = [r for r in responses if r.content.strip()]
        if not non_empty:
            return "I'm not sure how to help with that yet — could you tell me a bit more?"
        if len(non_empty) == 1:
            return non_empty[0].content
        return "\n\n".join(r.content.strip() for r in non_empty)
