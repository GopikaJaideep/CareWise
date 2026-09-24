"""AI risk screening, alongside the deterministic keyword check in app/core/safety.py.

The keyword list catches explicit phrases instantly and never depends on a model, but it misses
inflections, indirect language ("what's the point of living anymore?") and risk to the person being
cared for ("Mum said she wants to kill herself"): 12 of 24 crisis messages in the eval set.

This screen reads the whole message and says whether it signals a crisis, a concern, or neither,
and who is at risk. It can only ADD protection: the keyword check runs first and always wins, and
if the model is unavailable, slow or returns something unusable, the result is "unknown" and the
keyword result stands. It never writes the reply; a crisis still gets the fixed, reviewed response.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

Level = Literal["none", "concern", "crisis"]
Who = Literal["self", "care_recipient", "other", "unknown"]

# Long enough for a normal call, short enough that a hung request can't hold up a reply.
TIMEOUT_S = 8.0

RISK_SYSTEM = """You screen messages sent to CareWise, a support app for people caring for someone with cancer, for risk of suicide or self-harm. You do not reply to the person; you only classify.

Return JSON: {"level": "none" | "concern" | "crisis", "who": "self" | "care_recipient" | "other" | "unknown", "reason": "a few words"}

level:
- "crisis": suicidal thoughts, wanting to die or not wanting to be alive, plans or means (e.g. stockpiling or taking extra pills), self-harm (including "cutting"), or an overdose, whether current, recent or considered. Includes indirect wording such as "what's the point of living", "everyone would be better off without me", "I want it all to end".
- "concern": serious distress without signs of self-harm or suicide, e.g. hopelessness, "I can't cope", "I'm falling apart".
- "none": everything else, including ordinary tiredness and venting.

Not a crisis: end-of-life planning and prognosis ("she doesn't want to die in hospital", "the doctor says he may die within months", voluntary assisted dying questions, "she's at peace with dying when it's her time"), grief, idioms ("this week is killing me", "dead tired"), and mentions of the topic in another context (a documentary, work training).

who: "self" if the person writing is at risk; "care_recipient" if it is the person they care for; "other" for someone else; "unknown" if unclear.

When unsure whether a message signals suicide or self-harm, choose "crisis": a false alarm shows helpline numbers, a miss can cost a life."""


@dataclass(frozen=True)
class RiskAssessment:
    level: Level | Literal["unknown"]  # "unknown": the screen couldn't run; rely on keywords
    who: Who = "unknown"
    reason: str = ""


UNKNOWN = RiskAssessment("unknown")


async def assess_risk(llm, message: str, history: list[dict[str, str]] | None = None) -> RiskAssessment:
    if getattr(llm, "provider", None) is None:
        return UNKNOWN
    try:
        result = await asyncio.wait_for(
            llm.complete_json(
                system=RISK_SYSTEM,
                messages=[*(history or [])[-2:], {"role": "user", "content": message}],
                schema_hint='{"level": str, "who": str, "reason": str}',
            ),
            timeout=TIMEOUT_S,
        )
    except Exception as e:  # timeout or client error: the keyword check still stands
        logger.warning("Risk screen unavailable (%s); relying on keyword check", type(e).__name__)
        return UNKNOWN
    level = str(result.get("level", "")).lower()
    who = str(result.get("who", "unknown")).lower()
    if level not in ("none", "concern", "crisis"):
        return UNKNOWN
    return RiskAssessment(
        level=level,  # type: ignore[arg-type]
        who=who if who in ("self", "care_recipient", "other") else "unknown",  # type: ignore[arg-type]
        reason=str(result.get("reason", ""))[:120],
    )
