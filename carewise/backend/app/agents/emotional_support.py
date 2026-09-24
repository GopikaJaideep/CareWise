"""Emotional support agent — provides validating, reflective companionship.

This agent is intentionally NOT a therapist. It practices active listening,
validates feelings, and gently surfaces resources when appropriate. It will
hand off to the SafetyAgent if it detects crisis content.
"""
from __future__ import annotations

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.core.safety import detect_crisis, RiskLevel
from app.services.llm import get_llm_client


SYSTEM_PROMPT = """You are the Emotional Support specialist within CareWise, an AI companion for cancer caregivers.

Your role is to be a calm, non-judgmental presence — the kind of friend who listens without trying to fix everything.

Caregiver context: {care_context}
Recent burnout signal: {burnout_signal}

Guidelines:
1. Validate first. Reflect what the caregiver is feeling before anything else.
2. Use plain, warm language. No clinical jargon, no toxic positivity ("everything happens for a reason"), no premature problem-solving.
3. Caregiving for someone with cancer involves grief, exhaustion, anger, guilt, fear — all are normal. Name them when appropriate.
4. Never diagnose, prescribe, or speculate about prognosis. If asked about treatments or outcomes, acknowledge the question and gently note that you can pull up information resources or that those questions belong with the medical team.
5. Keep responses to 2–4 short paragraphs unless the caregiver explicitly asks for more.
6. End with a gentle, optional invitation — never a directive — when it feels right (e.g., "If it would help, I can…").
7. Never use phrases like "I understand exactly how you feel." You don't.

If the caregiver shows signs of severe distress, end your response with: [HANDOFF: safety]
"""


class EmotionalSupportAgent(BaseAgent):
    name = AgentName.EMOTIONAL_SUPPORT
    description = "Listens, validates, and offers gentle emotional companionship."

    def __init__(self) -> None:
        self.llm = get_llm_client()
        self.system_prompt = SYSTEM_PROMPT

    async def handle(self, ctx: SessionContext) -> AgentResponse:
        # Pre-check for crisis content
        crisis = detect_crisis(ctx.user_message)
        if crisis.requires_intervention:
            return AgentResponse(
                agent=self.name,
                content="",
                handoff_to=AgentName.SAFETY,
                metadata={"crisis_detected": True, "triggers": crisis.triggers},
            )

        care_context = ctx.user_profile.get("diagnosis_context") or "no specific context provided"
        burnout_signal = ctx.metadata.get("recent_burnout_score", "unknown")

        system = self.system_prompt.format(
            care_context=care_context,
            burnout_signal=burnout_signal,
        )
        memories = ctx.user_profile.get("memories") or []
        if memories:
            # Remembered from earlier chats (opt-in; see app/services/memory.py).
            system += (
                "\nWhat you know about this caregiver from earlier chats. Use it naturally where it helps; "
                "never recite the list or announce that you remember things:\n"
                + "\n".join(f"- {m}" for m in memories) + "\n"
            )
        if ctx.metadata.get("risk_concern"):
            # Set by the AI risk screen (app/core/risk.py): serious distress, not a crisis.
            system += (
                "\nThe safety screen noticed serious distress in this message. Acknowledge it gently, "
                "ask how they are holding up, and mention once, without alarm, that Lifeline "
                "(13 11 14) is there 24/7 if they want to talk to someone.\n"
            )

        messages = list(ctx.history) + [{"role": "user", "content": ctx.user_message}]
        text = await self.llm.complete(system=system, messages=messages, temperature=0.75, stream=True)

        handoff = None
        if "[HANDOFF: safety]" in text:
            text = text.replace("[HANDOFF: safety]", "").strip()
            handoff = AgentName.SAFETY

        return AgentResponse(
            agent=self.name,
            content=text,
            handoff_to=handoff,
            metadata={"risk_level": crisis.risk_level.value},
        )
