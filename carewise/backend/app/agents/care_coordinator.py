"""Care coordinator agent — manages tasks, appointments, and reminders.

Extracts task intent from natural language ("Don't let me forget Mum's
oncologist appointment Thursday at 2") and writes to the task store.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.models.db import CareTask
from app.services.llm import get_llm_client


EXTRACTION_SYSTEM = """You extract care-coordination tasks from caregiver messages.

Today's date and time (UTC): {now}

Return JSON:
- tasks: array of {title: string, description: string|null, due_at: ISO8601 string|null, category: "appointment"|"medication"|"errand"|"general"}
- query: "list_tasks" | "list_today" | "list_upcoming" | null
- mark_done: array of strings (task titles or descriptions to mark complete)

Be conservative. If a date is ambiguous (e.g., "Thursday"), interpret it as the next occurrence. If no date is mentioned, leave due_at null.
"""

RESPONSE_SYSTEM = """You are the Care Coordinator specialist within CareWise.

Your role:
1. Confirm what was added/updated in 1-2 sentences.
2. When listing tasks, group by today / upcoming / no date, and sort chronologically.
3. Never make up tasks the caregiver didn't mention.
4. Be warm but efficient — caregivers are usually time-pressed.
"""


class CareCoordinatorAgent(BaseAgent):
    name = AgentName.CARE_COORDINATOR
    description = "Manages tasks, appointments, and reminders for the care plan."

    def __init__(self, db: AsyncSession) -> None:
        self.llm = get_llm_client()
        self.db = db
        self.system_prompt = RESPONSE_SYSTEM

    async def handle(self, ctx: SessionContext) -> AgentResponse:
        now = datetime.now(timezone.utc)
        extraction = await self.llm.complete_json(
            system=EXTRACTION_SYSTEM.replace("{now}", now.isoformat()),
            messages=[{"role": "user", "content": ctx.user_message}],
            schema_hint='{"tasks": [...], "query": str|null, "mark_done": [...]}',
        )

        added = []
        for t in extraction.get("tasks", []) or []:
            if not t.get("title"):
                continue
            due = None
            if t.get("due_at"):
                try:
                    due = datetime.fromisoformat(t["due_at"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    due = None
            task = CareTask(
                user_id=ctx.user_id,
                title=t["title"],
                description=t.get("description"),
                due_at=due,
                category=t.get("category", "general"),
            )
            self.db.add(task)
            added.append(t["title"])

        # Mark done
        marked = []
        for title_fragment in extraction.get("mark_done", []) or []:
            stmt = select(CareTask).where(
                CareTask.user_id == ctx.user_id,
                CareTask.completed.is_(False),
                CareTask.title.ilike(f"%{title_fragment}%"),
            )
            result = await self.db.execute(stmt)
            for task in result.scalars():
                task.completed = True
                marked.append(task.title)

        await self.db.commit()

        # Handle queries
        query = extraction.get("query")
        list_text = ""
        if query in ("list_tasks", "list_today", "list_upcoming"):
            list_text = await self._format_task_list(ctx.user_id, query)

        # Compose response
        parts = []
        if added:
            parts.append(f"Added: {', '.join(added)}.")
        if marked:
            parts.append(f"Marked done: {', '.join(marked)}.")
        if list_text:
            parts.append(list_text)

        if parts:
            response_text = "\n\n".join(parts)
        else:
            response_text = await self.llm.complete(
                system=RESPONSE_SYSTEM,
                messages=[{"role": "user", "content": ctx.user_message}],
                temperature=0.3,
            )

        return AgentResponse(
            agent=self.name,
            content=response_text,
            metadata={"added": added, "marked": marked, "extraction": extraction},
        )

    async def _format_task_list(self, user_id: int, query: str) -> str:
        stmt = select(CareTask).where(
            CareTask.user_id == user_id, CareTask.completed.is_(False)
        ).order_by(CareTask.due_at.asc().nullslast())
        result = await self.db.execute(stmt)
        tasks = list(result.scalars())

        if not tasks:
            return "No open tasks right now."

        now = datetime.now(timezone.utc)
        today, upcoming, undated = [], [], []
        for t in tasks:
            if t.due_at is None:
                undated.append(t)
            elif t.due_at.date() == now.date():
                today.append(t)
            else:
                upcoming.append(t)

        lines = []
        if today:
            lines.append("**Today:**")
            for t in today:
                lines.append(f"  • {t.title} ({t.due_at.strftime('%I:%M %p')})")
        if upcoming:
            lines.append("\n**Upcoming:**")
            for t in upcoming[:5]:
                lines.append(f"  • {t.title} — {t.due_at.strftime('%a %d %b')}")
        if undated and query == "list_tasks":
            lines.append("\n**No date set:**")
            for t in undated[:3]:
                lines.append(f"  • {t.title}")
        return "\n".join(lines)
