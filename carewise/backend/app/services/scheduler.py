"""Background jobs: morning motivational pushes, and 5-min-before task reminders.

Runs in-process via APScheduler, started from the FastAPI lifespan. This only
fires while the app instance is awake — on a host that spins down when idle
(e.g. a free-tier dyno), a reminder due while the instance is asleep will be
missed rather than queued, since there is no separate always-on worker here.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import or_, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.quotes import quote_of_the_day, random_quote
from app.models.db import CareTask, PushSubscription
from app.services.push import send_push_to_user

logger = logging.getLogger(__name__)
settings = get_settings()

_scheduler: AsyncIOScheduler | None = None


async def _send_morning_reminders() -> None:
    today_str = date.today().isoformat()
    async with SessionLocal() as db:
        result = await db.execute(
            select(PushSubscription).where(
                or_(
                    PushSubscription.last_morning_reminder_date.is_(None),
                    PushSubscription.last_morning_reminder_date != today_str,
                )
            )
        )
        subs = list(result.scalars())
        if not subs:
            return

        by_user: dict[int, list[PushSubscription]] = {}
        for sub in subs:
            by_user.setdefault(sub.user_id, []).append(sub)

        for user_id, user_subs in by_user.items():
            quote = quote_of_the_day(seed_key=str(user_id))
            await send_push_to_user(
                db, user_id,
                title="Good morning 🌿",
                body=f"{quote}",
                tag="carewise-morning",
            )
            for sub in user_subs:
                sub.last_morning_reminder_date = today_str
        await db.commit()

    logger.info("Sent morning reminders to %s user(s).", len(by_user))


async def _send_task_reminders() -> None:
    now = datetime.now(timezone.utc)
    window_start = now + timedelta(minutes=4)
    window_end = now + timedelta(minutes=6)

    async with SessionLocal() as db:
        result = await db.execute(
            select(CareTask).where(
                CareTask.completed.is_(False),
                CareTask.reminded_at.is_(None),
                CareTask.due_at.is_not(None),
                CareTask.due_at >= window_start,
                CareTask.due_at <= window_end,
            )
        )
        tasks = list(result.scalars())
        if not tasks:
            return

        for task in tasks:
            quote = random_quote()
            await send_push_to_user(
                db, task.user_id,
                title="Coming up in 5 minutes",
                body=f"{task.title}\n\n{quote}",
                tag=f"carewise-task-{task.id}",
            )
            task.reminded_at = now
        await db.commit()

    logger.info("Sent %s task reminder(s).", len(tasks))


async def _purge_demos() -> None:
    """Delete demo accounts older than a day, with all their data."""
    from app.services.demo import purge_expired_demos

    async with SessionLocal() as db:
        removed = await purge_expired_demos(db)
    if removed:
        logger.info("Deleted %d expired demo accounts", removed)


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    scheduler.add_job(
        _send_morning_reminders,
        CronTrigger(hour=settings.morning_reminder_hour_utc, minute=0),
        id="morning_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        _send_task_reminders,
        IntervalTrigger(minutes=1),
        id="task_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        _purge_demos,
        IntervalTrigger(hours=1),
        id="purge_demos",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("Reminder scheduler started (morning hour UTC=%s).", settings.morning_reminder_hour_utc)
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
