"""One-click demo accounts, so someone can try CareWise without signing up.

Each visitor gets their own private account (never a shared one, where strangers would read each
other's messages), pre-filled with a realistic week so every page has something to show. Demo
accounts use a .invalid address (a domain reserved so it can never receive mail), are deleted
after DEMO_TTL_HOURS by the scheduler, and are capped so anonymous visitors can't run up the
database or the model quota: DEMO_MESSAGE_LIMIT chat messages each, DEMO_PER_IP_PER_HOUR new demos
per address, and at most MAX_LIVE_DEMOS at once as a hard ceiling (the per-address limit is
best-effort, since forwarded addresses can be spoofed).
"""
from __future__ import annotations

import secrets
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.burnout_monitor import compute_burnout_score
from app.core.auth import hash_password
from app.models.db import (
    BurnoutCheckin, CareTask, Conversation, Medication, Message, SymptomLog, User,
)

DEMO_TTL_HOURS = 24
DEMO_MESSAGE_LIMIT = 20
DEMO_PER_IP_PER_HOUR = 5
MAX_LIVE_DEMOS = 200
DEMO_EMAIL_DOMAIN = "demo.carewise.invalid"

_recent_by_ip: dict[str, deque[float]] = {}


class DemoUnavailable(Exception):
    """Too many demos right now; the message is safe to show."""


def allow_new_demo(ip: str, now: float | None = None) -> bool:
    """In-memory sliding window per address. Per process, which is fine for one instance."""
    now = time.monotonic() if now is None else now
    window = _recent_by_ip.setdefault(ip, deque())
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= DEMO_PER_IP_PER_HOUR:
        return False
    window.append(now)
    return True


async def create_demo_user(db: AsyncSession, now: datetime | None = None) -> User:
    live = await db.scalar(select(func.count()).select_from(User).where(User.is_demo.is_(True)))
    if live >= MAX_LIVE_DEMOS:
        raise DemoUnavailable("The demo is very busy right now. Please try again later, or create a free account.")

    now = now or datetime.now(timezone.utc)
    user = User(
        email=f"demo-{uuid.uuid4().hex[:12]}@{DEMO_EMAIL_DOMAIN}",
        hashed_password=hash_password(secrets.token_urlsafe(32)),  # nobody knows it: demo-only login
        display_name="Sam",
        care_recipient_name="Anne",
        care_recipient_relation="mum",
        diagnosis_context="Breast cancer, on chemotherapy every three weeks",
        is_demo=True,
        email_verified=True,  # nothing to confirm: the address can't receive mail
    )
    db.add(user)
    await db.flush()
    _seed(db, user.id, now)
    await db.commit()
    await db.refresh(user)
    return user


def _seed(db: AsyncSession, user_id: int, now: datetime) -> None:
    """A realistic week in the life of a carer, so each page has something to show."""
    day = timedelta(days=1)
    for days_ago, symptom, severity, notes in [
        (6, "fatigue", 5, None), (5, "nausea", 6, "after chemo"), (5, "fatigue", 7, None),
        (4, "nausea", 4, None), (3, "mouth sores", 3, None), (2, "fatigue", 8, "slept most of the day"),
        (1, "nausea", 3, None), (0, "fatigue", 6, None),
    ]:
        db.add(SymptomLog(user_id=user_id, symptom=symptom, severity=severity, notes=notes,
                          logged_at=now - days_ago * day))
    db.add_all([
        Medication(user_id=user_id, name="ondansetron", dosage="8mg", schedule="twice a day", notes="for nausea"),
        Medication(user_id=user_id, name="dexamethasone", dosage="4mg", schedule="each morning"),
    ])
    next_chemo = (now + 5 * day).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=10)
    db.add_all([
        CareTask(user_id=user_id, title="Chemo cycle 4", category="appointment", due_at=next_chemo),
        CareTask(user_id=user_id, title="Pick up prescription from pharmacy", category="errand", due_at=now + day),
        CareTask(user_id=user_id, title="Call the breast care nurse about mouth sores", category="general"),
        CareTask(user_id=user_id, title="Buy nutrition shakes", category="errand"),
    ])
    trend: list[float] = []
    for days_ago, sleep, stress, energy, minutes in [(6, 6.5, 6, 5, 20), (3, 5.0, 7, 4, 10), (0, 4.5, 8, 3, 0)]:
        score = compute_burnout_score(sleep, stress, energy, minutes, recent_trend=trend[-3:])
        trend.append(score)
        db.add(BurnoutCheckin(user_id=user_id, sleep_hours=sleep, stress_level=stress, energy_level=energy,
                              self_care_minutes=minutes, burnout_score=score, created_at=now - days_ago * day))
    conversation = Conversation(user_id=user_id, title="Mum had nausea this morning, around a 6.",
                                created_at=now - 5 * day)
    db.add(conversation)
    conversation.messages = [
        Message(role="user", content="Mum had nausea this morning, around a 6.", created_at=now - 5 * day),
        Message(role="assistant", agent_used="symptom_tracker",
                content="I've logged nausea at 6/10 for this morning. If it keeps up, her team can suggest "
                        "anti-nausea options. How are you holding up?",
                created_at=now - 5 * day + timedelta(seconds=4)),
    ]


async def purge_expired_demos(db: AsyncSession, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=DEMO_TTL_HOURS)
    expired = (await db.execute(
        select(User).where(User.is_demo.is_(True), User.created_at < cutoff)
    )).scalars().all()
    for user in expired:
        await db.delete(user)  # cascades to all their data
    await db.commit()
    return len(expired)


async def demo_messages_used(db: AsyncSession, user_id: int) -> int:
    return await db.scalar(
        select(func.count()).select_from(Message).join(Conversation)
        .where(Conversation.user_id == user_id, Message.role == "user")
    ) or 0
