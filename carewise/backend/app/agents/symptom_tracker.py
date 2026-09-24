"""Symptom & medication tracking agent.

Captures structured data from natural language ("Mum had nausea this morning,
about a 6 out of 10") and maintains the symptom/medication ledger.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.agents.outputs import SymptomExtraction, parse_severity  # noqa: F401  (parse_severity re-exported for evals)
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


NOTHING_SAVED_NOTE = (
    "\n\nNothing was logged for this message. Do NOT say that anything was logged or saved. "
    "If the caregiver described a symptom without a clear 1-10 severity, ask how bad it is on a "
    "scale of 1 to 10 so it can be logged."
)


class SymptomTrackerAgent(BaseAgent):
    name = AgentName.SYMPTOM_TRACKER
    description = "Logs symptoms, medications, and surfaces patterns over time."

    def __init__(self, db: AsyncSession) -> None:
        self.llm = get_llm_client()
        self.db = db
        self.system_prompt = RESPONSE_SYSTEM

    async def extract(self, message: str) -> dict:
        """Model step only: message -> {symptoms, medications, query}. No database writes.

        Separate from handle() so the eval suite can score extraction on its own.
        """
        result = await self.llm.complete_structured(
            system=EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": message}],
            output=SymptomExtraction,
        )
        return result.model_dump() if result else {}

    async def handle(self, ctx: SessionContext) -> AgentResponse:
        # Step 1: Extract structured data
        extraction = await self.extract(ctx.user_message)

        logged_summary = []
        # Step 2: Persist symptoms
        for s in extraction.get("symptoms", []) or []:
            severity = parse_severity(s.get("severity"))
            if not s.get("symptom") or severity is None:
                continue
            name = str(s["symptom"]).strip()[:120]
            log = SymptomLog(
                user_id=ctx.user_id,
                symptom=name,
                severity=severity,
                notes=s.get("notes"),
                logged_at=datetime.now(timezone.utc),
            )
            self.db.add(log)
            logged_summary.append(f"{name} ({severity}/10)")

        # Step 3: Persist medications
        for m in extraction.get("medications", []) or []:
            action = m.get("action")
            if action == "added" and m.get("name"):
                med = Medication(
                    user_id=ctx.user_id,
                    name=str(m["name"])[:120],
                    dosage=m.get("dosage") or "as prescribed",
                    schedule=m.get("schedule") or "as needed",
                    notes=m.get("notes"),
                )
                self.db.add(med)
                logged_summary.append(f"medication: {m['name']}")

        await self.db.commit()

        # Step 4: Compose human response
        query = extraction.get("query")
        if logged_summary:
            confirmation = f"Logged: {', '.join(logged_summary)}."
            response_text = await self._compose_response(ctx, confirmation)
        elif query in ("list_symptoms", "list_medications", "trend"):
            # Answer from the saved records. Before, the model answered without them and could
            # invent a history.
            response_text = await self._answer_from_records(ctx, query)
        else:
            response_text = await self.llm.complete(
                system=RESPONSE_SYSTEM + NOTHING_SAVED_NOTE,
                messages=[*ctx.history[-4:], {"role": "user", "content": ctx.user_message}],
                temperature=0.3,
                stream=True,
            )

        return AgentResponse(
            agent=self.name,
            content=response_text,
            metadata={"extracted": extraction, "logged": logged_summary},
        )

    async def _answer_from_records(self, ctx: SessionContext, query: str) -> str:
        since = datetime.now(timezone.utc) - timedelta(days=14)
        symptoms = list((await self.db.execute(
            select(SymptomLog)
            .where(SymptomLog.user_id == ctx.user_id, SymptomLog.logged_at >= since)
            .order_by(SymptomLog.logged_at.desc())
            .limit(30)
        )).scalars())
        meds = list((await self.db.execute(
            select(Medication).where(Medication.user_id == ctx.user_id, Medication.active.is_(True))
        )).scalars())

        if query == "list_medications":
            if not meds:
                return "There are no medications tracked yet. You can add one on the Symptoms page, or tell me here."
            return "Medications you're tracking:\n" + "\n".join(
                f"  • {m.name} ({m.dosage}, {m.schedule})" for m in meds
            )

        if not symptoms:
            return "Nothing has been logged in the last 14 days. Tell me what you've noticed and how bad it is (1-10), and I'll log it."
        records = "\n".join(
            f"- {s.logged_at:%a %d %b}: {s.symptom} {s.severity}/10" + (f" ({s.notes})" if s.notes else "")
            for s in symptoms
        )
        prompt = (
            f"The caregiver asked: \"{ctx.user_message}\"\n\n"
            f"These are ALL the symptoms logged in the last 14 days, newest first:\n{records}\n\n"
            "Answer using only these records. Summarise briefly; if a symptom is logged 3+ times and "
            "getting worse, mention the pattern gently and suggest raising it with the care team."
        )
        return await self.llm.complete(
            system=RESPONSE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            stream=True,
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
            stream=True,
        )
