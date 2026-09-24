"""Long-term memory: durable facts CareWise remembers between chats.

Opt-in (User.memory_enabled, off by default) and fully in the person's control: everything
remembered is listed on their Home page, each item can be deleted, and turning memory off
forgets everything (app/api/memory_routes.py).

After a chat turn, a background task (never delaying the reply) asks the model, every few
messages, what durable facts the conversation added or made outdated. What is never stored is
enforced in code, not just in the prompt: anything that trips the crisis check, and anything
containing phone numbers, email addresses or Medicare-style numbers. Turns that reached the
safety response are skipped entirely.
"""
from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.outputs import MemoryUpdate
from app.core.safety import detect_crisis, redact_pii
from app.models.db import Message, User, UserMemory

logger = logging.getLogger(__name__)

MEMORY_LIMIT = 40  # the oldest are dropped beyond this
UPDATE_EVERY = 3  # user messages per conversation between memory updates
RECENT_MESSAGES = 12

MEMORY_SYSTEM = """You keep a short list of durable facts that help CareWise, a support app, look after a person caring for someone with cancer. You are given the facts already remembered (with ids) and a recent conversation.

Return JSON: {"add": [{"text": "...", "category": "care_recipient" | "caregiver" | "care_team" | "routine" | "what_helps" | "other"}], "remove": [ids of remembered facts the conversation shows are now wrong or outdated]}

Worth remembering: who they care for and their situation (diagnosis, treatment and its schedule); the caregiver's circumstances (work, family, general area); the care team (roles and first names); routines; and what helps them cope.

Never remember: anything about suicide, self-harm or a crisis; phone numbers, email or street addresses, Medicare or other ID numbers; passing moods ("felt tired today"); individual symptom scores or medication doses (logged elsewhere); anything they asked you not to remember.

Write each fact as a short third-person statement of at most 20 words, e.g. "Their mum, Anne, has breast cancer and chemo every third Tuesday." Don't repeat facts already remembered. Use empty lists when there is nothing new."""


# Memories are third-person statements ("they want to kill themselves"), which the first-person
# crisis keywords ("kill myself") don't match. For memory a false positive only means a fact isn't
# remembered, so this filter is deliberately broad.
_NEVER_REMEMBER = re.compile(
    r"suicid|self[- ]?harm|overdos|kill (?:them|him|her|my)sel(?:f|ves)|hurt(?:ing)? (?:them|him|her|my)sel(?:f|ves)"
    r"|end(?:ing)? (?:their|his|her|my) (?:own )?life|want(?:s|ed)? to die|better off dead|cutting (?:them|him|her|my)sel",
    re.I,
)


def is_storable(text: str) -> bool:
    """Code-level guard on top of the prompt: no contact or ID numbers, no crisis content."""
    return (
        redact_pii(text) == text
        and not detect_crisis(text).requires_intervention
        and not _NEVER_REMEMBER.search(text)
    )


async def load_memories(db: AsyncSession, user_id: int) -> list[UserMemory]:
    result = await db.execute(
        select(UserMemory).where(UserMemory.user_id == user_id).order_by(UserMemory.created_at, UserMemory.id)
    )
    return list(result.scalars())


async def update_memories(llm, db: AsyncSession, user: User, conversation_id: int) -> dict[str, int]:
    """Ask the model what the recent conversation adds or makes outdated, and apply it."""
    if not user.memory_enabled:
        return {"added": 0, "removed": 0}
    existing = await load_memories(db, user.id)
    rows = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc()).limit(RECENT_MESSAGES)
    )
    conversation = "\n".join(f"{m.role}: {m.content}" for m in reversed(list(rows.scalars())))
    remembered = "\n".join(f"{m.id}: {m.text}" for m in existing) or "(nothing yet)"
    update = await llm.complete_structured(
        system=MEMORY_SYSTEM,
        messages=[{"role": "user", "content": f"Already remembered:\n{remembered}\n\nRecent conversation:\n{conversation}"}],
        output=MemoryUpdate,
    )
    if update is None:
        return {"added": 0, "removed": 0}
    return await apply_update(db, user.id, existing, update)


async def apply_update(db: AsyncSession, user_id: int, existing: list[UserMemory], update: MemoryUpdate) -> dict[str, int]:
    by_id = {m.id: m for m in existing}
    removed = 0
    for memory_id in set(update.remove):
        if memory_id in by_id:  # only this user's own memories
            await db.delete(by_id.pop(memory_id))
            removed += 1

    known = {m.text.strip().lower() for m in by_id.values()}
    added = 0
    for item in update.add:
        text = " ".join(item.text.split())
        if text.lower() in known or not is_storable(text):
            continue
        db.add(UserMemory(user_id=user_id, text=text, category=item.category))
        known.add(text.lower())
        added += 1
    await db.flush()

    # Keep the list short: drop the oldest beyond the limit.
    remaining = await load_memories(db, user_id)
    for old in remaining[: max(0, len(remaining) - MEMORY_LIMIT)]:
        await db.delete(old)
    await db.commit()
    return {"added": added, "removed": removed}


# --- After each chat turn ---------------------------------------------------------------------------

_background: set[asyncio.Task] = set()


def after_turn(user: User, conversation_id: int, reached_safety: bool) -> None:
    """Schedule a memory update in the background, so it never delays the reply."""
    if not user.memory_enabled or reached_safety:
        return
    task = asyncio.create_task(_refresh(user.id, conversation_id))
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _refresh(user_id: int, conversation_id: int) -> None:
    from app.core.database import get_session_factory
    from app.services.llm import get_llm_client

    try:
        async with get_session_factory()() as db:
            user = await db.get(User, user_id)
            if user is None or not user.memory_enabled:
                return
            user_messages = await db.scalar(
                select(func.count()).select_from(Message)
                .where(Message.conversation_id == conversation_id, Message.role == "user")
            )
            if not user_messages or user_messages % UPDATE_EVERY:
                return
            result = await update_memories(get_llm_client(), db, user, conversation_id)
            logger.info("memory_update %s", {"user_id": user_id, **result})
    except Exception:  # background work: never let it surface to the person
        logger.exception("Memory update failed")
