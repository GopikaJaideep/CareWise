"""Burnout monitor — runs structured check-ins and computes burnout risk score.

The score is a weighted heuristic across:
- Sleep deficit (vs 7h baseline)
- Stress level (1-10)
- Energy level (1-10, inverted)
- Self-care minutes (0-120 typical, inverted)
- Streak: declining trend over recent check-ins amplifies score

Score is clinical-style triage only, NOT a diagnostic instrument.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.models.db import BurnoutCheckin
from app.services.llm import get_llm_client


EXTRACTION_SYSTEM = """Extract a caregiver burnout check-in from the message.

Return JSON:
- sleep_hours: float | null   (hours slept last night)
- stress_level: int 1-10 | null
- energy_level: int 1-10 | null
- self_care_minutes: int | null   (minutes spent on anything purely for themselves today)
- notes: string | null
- is_checkin: bool   (true if the message is providing check-in data; false if asking for status/trend)

Only extract values that are clearly stated. Leave null otherwise.
"""

RESPONSE_SYSTEM = """You are the Burnout Monitor specialist within CareWise.

Your role:
1. After a check-in, reflect what you heard in 1-2 sentences and share the burnout score with brief context (low / moderate / high / very high).
2. If the score is moderate or higher, name one specific, low-effort thing the caregiver could try (e.g., "even 10 minutes outside today counts"). Never lecture.
3. If the score is high or very high for 2+ check-ins, gently mention respite resources (Carer Gateway 1800 422 737 in Australia) and Cancer Council support.
4. Never minimise ("at least…") and never catastrophise. Match the caregiver's tone.
5. Be brief — caregivers in burnout don't have bandwidth for long replies.
"""


def compute_burnout_score(
    sleep_hours: float,
    stress_level: int,
    energy_level: int,
    self_care_minutes: int,
    recent_trend: list[float] | None = None,
) -> float:
    """0-100 burnout risk score. Higher = worse."""
    # Sleep deficit (capped at 4h deficit = max contribution)
    sleep_deficit = max(0.0, 7.0 - sleep_hours)
    sleep_score = min(sleep_deficit / 4.0, 1.0) * 25

    # Stress (1-10 -> 0-25)
    stress_score = ((stress_level - 1) / 9.0) * 25

    # Energy (1-10 -> 0-25, inverted)
    energy_score = ((10 - energy_level) / 9.0) * 25

    # Self-care (cap at 60 min for full credit)
    sc_score = (1.0 - min(self_care_minutes / 60.0, 1.0)) * 15

    base = sleep_score + stress_score + energy_score + sc_score

    # Trend amplifier: if last 3 scores are increasing, add up to 10
    trend_bonus = 0.0
    if recent_trend and len(recent_trend) >= 2:
        diffs = [recent_trend[i] - recent_trend[i - 1] for i in range(1, len(recent_trend))]
        if all(d > 0 for d in diffs):
            trend_bonus = min(sum(diffs) / 2.0, 10.0)

    return round(min(base + trend_bonus, 100.0), 1)


def categorise(score: float) -> str:
    if score < 30:
        return "low"
    if score < 55:
        return "moderate"
    if score < 75:
        return "high"
    return "very high"


class BurnoutMonitorAgent(BaseAgent):
    name = AgentName.BURNOUT_MONITOR
    description = "Runs structured burnout check-ins and tracks trend over time."

    def __init__(self, db: AsyncSession) -> None:
        self.llm = get_llm_client()
        self.db = db
        self.system_prompt = RESPONSE_SYSTEM

    async def handle(self, ctx: SessionContext) -> AgentResponse:
        extraction = await self.llm.complete_json(
            system=EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": ctx.user_message}],
            schema_hint='{"sleep_hours": float|null, "stress_level": int|null, "energy_level": int|null, "self_care_minutes": int|null, "notes": str|null, "is_checkin": bool}',
        )

        if not extraction.get("is_checkin"):
            # User is asking for status — return trend
            return await self._handle_trend_query(ctx)

        # Need all four fields to compute a score
        required = ["sleep_hours", "stress_level", "energy_level", "self_care_minutes"]
        missing = [k for k in required if extraction.get(k) is None]

        if missing:
            prompt = (
                "I can run a burnout check-in if you share a few quick numbers:\n\n"
                "  • Hours of sleep last night\n"
                "  • Stress level today (1–10)\n"
                "  • Energy level today (1–10)\n"
                "  • Minutes spent on anything purely for yourself today\n\n"
                "You can answer in one line — e.g., \"5 hours sleep, stress 8, energy 3, 0 minutes for me.\""
            )
            return AgentResponse(
                agent=self.name,
                content=prompt,
                metadata={"missing_fields": missing},
                requires_followup=True,
            )

        # Compute trend
        recent_stmt = (
            select(BurnoutCheckin)
            .where(BurnoutCheckin.user_id == ctx.user_id)
            .order_by(BurnoutCheckin.created_at.desc())
            .limit(3)
        )
        result = await self.db.execute(recent_stmt)
        recent = list(result.scalars())
        recent_trend = [c.burnout_score for c in reversed(recent)]

        score = compute_burnout_score(
            sleep_hours=float(extraction["sleep_hours"]),
            stress_level=int(extraction["stress_level"]),
            energy_level=int(extraction["energy_level"]),
            self_care_minutes=int(extraction["self_care_minutes"]),
            recent_trend=recent_trend,
        )

        # Persist
        checkin = BurnoutCheckin(
            user_id=ctx.user_id,
            sleep_hours=float(extraction["sleep_hours"]),
            stress_level=int(extraction["stress_level"]),
            energy_level=int(extraction["energy_level"]),
            self_care_minutes=int(extraction["self_care_minutes"]),
            notes=extraction.get("notes"),
            burnout_score=score,
        )
        self.db.add(checkin)
        await self.db.commit()

        category = categorise(score)
        prior_high = sum(1 for s in recent_trend if s >= 55)

        # Compose response via LLM with structured context
        prompt = (
            f"The caregiver just completed a burnout check-in.\n"
            f"Score: {score}/100 ({category})\n"
            f"Recent scores (oldest → newest, before this one): {recent_trend}\n"
            f"This is check-in #{len(recent) + 1}.\n"
            f"Prior moderate-or-higher check-ins in last 3: {prior_high}\n\n"
            f"Their original message: \"{ctx.user_message}\"\n\n"
            "Write the response according to your guidelines."
        )
        text = await self.llm.complete(
            system=RESPONSE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )

        return AgentResponse(
            agent=self.name,
            content=text,
            metadata={
                "burnout_score": score,
                "category": category,
                "trend": recent_trend + [score],
            },
        )

    async def _handle_trend_query(self, ctx: SessionContext) -> AgentResponse:
        stmt = (
            select(BurnoutCheckin)
            .where(BurnoutCheckin.user_id == ctx.user_id)
            .order_by(BurnoutCheckin.created_at.desc())
            .limit(7)
        )
        result = await self.db.execute(stmt)
        checkins = list(result.scalars())

        if not checkins:
            return AgentResponse(
                agent=self.name,
                content="No check-ins yet. Want to run one now? It takes about 30 seconds.",
            )

        latest = checkins[0]
        trend = [c.burnout_score for c in reversed(checkins)]
        category = categorise(latest.burnout_score)

        text = (
            f"Latest check-in: {latest.burnout_score}/100 — **{category}**.\n"
            f"Last {len(trend)} check-ins: {' → '.join(str(s) for s in trend)}\n\n"
        )
        if category in ("high", "very high"):
            text += (
                "That's been sitting in the high range. If you haven't already, "
                "Carer Gateway (1800 422 737) can arrange free respite — even a few hours. "
                "Cancer Council 13 11 20 also has free counselling for caregivers."
            )

        return AgentResponse(
            agent=self.name,
            content=text,
            metadata={"trend": trend, "latest_score": latest.burnout_score},
        )
