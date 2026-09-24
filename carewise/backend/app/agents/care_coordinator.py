"""Care coordinator agent — manages tasks, appointments, and reminders.

Extracts task intent from natural language ("Don't let me forget Mum's
oncologist appointment Thursday at 2") and writes to the task store.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.core.tz import parse_due_at, resolve_timezone, to_local, tz_label
from app.models.db import CareTask
from app.services.llm import get_llm_client


EXTRACTION_SYSTEM = """You extract care-coordination tasks from caregiver messages.

The caregiver's timezone is {tz}. Their current local date and time is: {now}

Return JSON:
- tasks: array of {title: string, description: string|null, due_at: string|null, category: "appointment"|"medication"|"errand"|"general"}
  due_at is the caregiver's LOCAL date-time as ISO8601 with NO UTC offset or "Z" (e.g. "2026-09-22T10:00:00"). "Tuesday at 10" means 10:00 on the wall clock in {tz}.
- query: "list_tasks" | "list_today" | "list_upcoming" | null
- mark_done: array of strings (task titles or descriptions to mark complete)

Be conservative. If a date is ambiguous (e.g., "Thursday"), interpret it as the next occurrence. If no date is mentioned, leave due_at null.
"""

CATEGORIES = {"appointment", "medication", "errand", "general"}
# Shorter fragments than this could match (and complete) many unrelated tasks.
MIN_MARK_DONE_LEN = 3

NOTHING_SAVED_NOTE = (
    "\n\nNothing was added, changed or completed in the care plan for this message. Do NOT say "
    "that anything was added or saved. If the caregiver seems to want a task added, ask for the "
    "missing detail (what, and when)."
)

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
        tz = resolve_timezone(ctx.metadata.get("timezone"))
        local_now = datetime.now(timezone.utc).astimezone(tz)
        # .replace, not .format: the template contains literal JSON braces.
        system = (
            EXTRACTION_SYSTEM
            .replace("{now}", local_now.strftime("%A %Y-%m-%d %H:%M"))
            .replace("{tz}", tz_label(tz))
        )
        extraction = await self.llm.complete_json(
            system=system,
            messages=[{"role": "user", "content": ctx.user_message}],
            schema_hint='{"tasks": [...], "query": str|null, "mark_done": [...]}',
        )

        added = []
        for t in extraction.get("tasks", []) or []:
            if not t.get("title"):
                continue
            due = parse_due_at(t["due_at"], tz) if t.get("due_at") else None
            category = str(t.get("category") or "general").lower()
            task = CareTask(
                user_id=ctx.user_id,
                title=str(t["title"])[:200],
                description=t.get("description"),
                due_at=due,
                category=category if category in CATEGORIES else "general",
            )
            self.db.add(task)
            added.append(t["title"])

        # Mark done
        marked = []
        for title_fragment in extraction.get("mark_done", []) or []:
            fragment = str(title_fragment or "").strip()
            # An empty fragment matched EVERY open task ("%%") and marked them all done.
            if len(fragment) < MIN_MARK_DONE_LEN:
                continue
            escaped = fragment.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            stmt = select(CareTask).where(
                CareTask.user_id == ctx.user_id,
                CareTask.completed.is_(False),
                CareTask.title.ilike(f"%{escaped}%", escape="\\"),
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
            list_text = await self._format_task_list(ctx.user_id, query, tz)

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
                system=RESPONSE_SYSTEM + NOTHING_SAVED_NOTE,
                messages=[*ctx.history[-4:], {"role": "user", "content": ctx.user_message}],
                temperature=0.3,
            )

        return AgentResponse(
            agent=self.name,
            content=response_text,
            metadata={"added": added, "marked": marked, "extraction": extraction},
        )

    async def _format_task_list(self, user_id: int, query: str, tz) -> str:
        stmt = select(CareTask).where(
            CareTask.user_id == user_id, CareTask.completed.is_(False)
        ).order_by(CareTask.due_at.asc().nullslast())
        result = await self.db.execute(stmt)
        tasks = list(result.scalars())

        if not tasks:
            return "No open tasks right now."

        today_local = datetime.now(timezone.utc).astimezone(tz).date()
        today, upcoming, undated = [], [], []
        for t in tasks:
            if t.due_at is None:
                undated.append((t, None))
                continue
            due_local = to_local(t.due_at, tz)
            (today if due_local.date() == today_local else upcoming).append((t, due_local))

        lines = []
        if today:
            lines.append("**Today:**")
            for t, due_local in today:
                lines.append(f"  • {t.title} ({due_local.strftime('%I:%M %p')})")
        if upcoming:
            lines.append("\n**Upcoming:**")
            for t, due_local in upcoming[:5]:
                lines.append(f"  • {t.title} — {due_local.strftime('%a %d %b')}")
        if undated and query == "list_tasks":
            lines.append("\n**No date set:**")
            for t, _ in undated[:3]:
                lines.append(f"  • {t.title}")
        return "\n".join(lines)
