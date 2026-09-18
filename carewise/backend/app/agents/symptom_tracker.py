"""Symptom & medication tracking agent.

Captures structured data from natural language ("Mum had nausea this morning,
about a 6 out of 10") and maintains the symptom/medication ledger.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.models.db import Medication, SymptomLog
from app.services.llm import get_llm_client


EXTRACTION_SYSTEM = """You extract structured tracking data from caregiver messages.

Return JSON with these optional fields:
- symptoms: array of {symptom: string, severity: int 1-10, notes: string|null}
- medications: array of {action: "added"|"taken"|"missed"|"updated", name: string, dosage: string|null, schedule: string|null, notes: string|null}
- query: "list_symptoms" | "list_medications" | "trend" | null  (set if the caregiver is ASKING about tracked data rather than logging new data)
- confidence: float 0-1

Only extract data that is explicitly stated. Severity must be inferred carefully — "really bad" is not a number; ask if unclear by leaving severity null.
"""

RESPONSE_SYSTEM = """You are the Symptom Tracker specialist within CareWise.

Your role:
1. Confirm what you logged in plain language ("Got it — logged nausea at 6/10 this morning.")
2. If trends are notable (e.g., 3+ entries showing worsening), gently surface the pattern WITHOUT alarming and suggest mentioning it to the care team.
3. Never interpret symptoms medically. Never suggest medication changes. If asked "is this normal?", redirect to the care team.
4. Be brief — 1-3 sentences unless showing a list.
"""


class SymptomTrackerAgent(BaseAgent):
    name = AgentName.SYMPTOM_TRACKER
    description = "Logs symptoms, medications, and surfaces patterns over time."

    def __init__(self, db: AsyncSession) -> None:
        self.llm = get_llm_client()
        self.db = db
        self.system_prompt = RESPONSE_SYSTEM

    async def handle(self, ctx: SessionContext) -> AgentResponse:
        # Step 1: Extract structured data
        extraction = await self.llm.complete_json(
            system=EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": ctx.user_message}],
            schema_hint='{"symptoms": [...], "medications": [...], "query": str|null, "confidence": float}',
        )

        logged_summary = []
        # Step 2: Persist symptoms
        for s in extraction.get("symptoms", []) or []:
            if not s.get("symptom") or s.get("severity") is None:
                continue
            log = SymptomLog(
                user_id=ctx.user_id,
                symptom=s["symptom"],
                severity=int(s["severity"]),
                notes=s.get("notes"),
                logged_at=datetime.now(timezone.utc),
            )
            self.db.add(log)
            logged_summary.append(f"{s['symptom']} ({s['severity']}/10)")

        # Step 3: Persist medications
        for m in extraction.get("medications", []) or []:
            action = m.get("action")
            if action == "added" and m.get("name"):
                med = Medication(
                    user_id=ctx.user_id,
                    name=m["name"],
                    dosage=m.get("dosage") or "as prescribed",
                    schedule=m.get("schedule") or "as needed",
                    notes=m.get("notes"),
                )
                self.db.add(med)
                logged_summary.append(f"medication: {m['name']}")

        await self.db.commit()

        # Step 4: Compose human response
        if logged_summary:
            confirmation = f"Logged: {', '.join(logged_summary)}."
            response_text = await self._compose_response(ctx, confirmation)
        else:
            response_text = await self.llm.complete(
                system=RESPONSE_SYSTEM,
                messages=[{"role": "user", "content": ctx.user_message}],
                temperature=0.3,
            )

        return AgentResponse(
            agent=self.name,
            content=response_text,
            metadata={"extracted": extraction, "logged": logged_summary},
        )

    async def _compose_response(self, ctx: SessionContext, confirmation: str) -> str:
        prompt = (
            f"The caregiver said: \"{ctx.user_message}\"\n\n"
            f"You just logged the following: {confirmation}\n\n"
            "Write a brief, warm confirmation (1-2 sentences). If appropriate, "
            "ask one gentle follow-up question (e.g., did they take anything for it, when did it start)."
        )
        return await self.llm.complete(
            system=RESPONSE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
