"""Safety agent — handles crisis-level content.

This agent does NOT use the LLM for crisis responses. It returns a deterministic,
audited response with verified resources. This is intentional: we never want
LLM creativity in a crisis path.
"""
from __future__ import annotations

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.core.safety import detect_crisis, _format_crisis_response


class SafetyAgent(BaseAgent):
    name = AgentName.SAFETY
    description = "Handles crisis-level content with verified resources, deterministically."

    def __init__(self) -> None:
        self.system_prompt = "(deterministic — no LLM)"

    async def handle(self, ctx: SessionContext) -> AgentResponse:
        check = detect_crisis(ctx.user_message)
        # Default to AU resources; in production, this would use user profile
        region = ctx.user_profile.get("region", "AU")
        content = _format_crisis_response(region=region)

        return AgentResponse(
            agent=self.name,
            content=content,
            metadata={
                "risk_level": check.risk_level.value,
                "triggers": check.triggers,
                "deterministic": True,
            },
        )
