"""Safety agent — handles crisis-level content.

This agent does NOT use the LLM for crisis responses. It returns a deterministic,
audited response with verified resources. This is intentional: we never want
LLM creativity in a crisis path.

It is reached two ways: the keyword check (app/core/safety.py) or the AI risk screen
(app/core/risk.py). The screen can only decide THAT this path is taken, and whether the person at
risk is the writer or someone else; the words of the reply are always the fixed text.
"""
from __future__ import annotations

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.core.safety import _format_crisis_response, _format_third_party_crisis_response, detect_crisis


class SafetyAgent(BaseAgent):
    name = AgentName.SAFETY
    description = "Handles crisis-level content with verified resources, deterministically."

    def __init__(self) -> None:
        self.system_prompt = "(deterministic — no LLM)"

    async def handle(self, ctx: SessionContext) -> AgentResponse:
        check = detect_crisis(ctx.user_message)
        # Default to AU resources; in production, this would use user profile
        region = ctx.user_profile.get("region", "AU")
        risk = ctx.metadata.get("risk") or {}
        someone_else = (
            check.someone_else if check.requires_intervention else risk.get("who") in ("care_recipient", "other")
        )
        content = (
            _format_third_party_crisis_response(region=region) if someone_else else _format_crisis_response(region=region)
        )

        return AgentResponse(
            agent=self.name,
            content=content,
            metadata={
                "risk_level": "critical",
                "detected_by": "keyword" if check.requires_intervention else "ai_screen",
                "triggers": check.triggers,
                "at_risk": "someone_else" if someone_else else "writer",
                "deterministic": True,
            },
        )
