"""Background jobs: morning motivational pushes, 5-min-before task reminders, demo clean-up.

Runs in-process via APScheduler, started from the FastAPI lifespan. This only fires while the
app instance is awake: on a host that spins down when idle, a reminder due while it sleeps is
missed rather than queued, since there is no separate always-on worker.

Built to leave the database idle. Serverless Postgres (Neon's free tier) pauses after a few idle
minutes and bills compute while awake, and a job that queried every minute kept it awake around
the clock and used up the month's free compute in a few weeks. Instead, the database is read
about once an hour: an hourly plan schedules an exact timer for each reminder due before the
next plan, and a task saved in between gets its timer straight away (note_task_due), with no
query. A timer reads the database only when there is a reminder to send.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
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


PLAN_EVERY = timedelta(hours=1)
# Plan a little past the next plan, so a reminder due just after it isn't missed.
PLAN_AHEAD = PLAN_EVERY + timedelta(minutes=10)
REMIND_BEFORE = timedelta(minutes=5)


def _schedule_reminder(task_id: int, due_at: datetime, now: datetime | None = None) -> bool:
    """Set (or move) the timer for one task's reminder. No database access."""
    if _scheduler is None:
        return False
    now = now or datetime.now(timezone.utc)
    if due_at.tzinfo is None:  # SQLite returns naive datetimes; they are stored as UTC
        due_at = due_at.replace(tzinfo=timezone.utc)
    if not (now < due_at <= now + PLAN_AHEAD):
        return False
    _scheduler.add_job(
        _send_task_reminder,
        DateTrigger(run_date=max(due_at - REMIND_BEFORE, now)),  # due in under 5 minutes: remind now
        args=[task_id],
        id=f"task_reminder_{task_id}",
        replace_existing=True,
        misfire_grace_time=300,
    )
    return True


def note_task_due(task_id: int, due_at: datetime | None) -> None:
    """Call after saving a task with a due time, so a reminder due before the next hourly plan
    still fires. Cheap and safe to call for any task."""
    if due_at is not None:
        _schedule_reminder(task_id, due_at)


async def _plan_reminders() -> int:
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        result = await db.execute(
            select(CareTask.id, CareTask.due_at).where(
                CareTask.completed.is_(False),
                CareTask.reminded_at.is_(None),
                CareTask.due_at.is_not(None),
                CareTask.due_at > now,
                CareTask.due_at <= now + PLAN_AHEAD,
            )
        )
        planned = sum(_schedule_reminder(task_id, due_at, now) for task_id, due_at in result.all())
    if planned:
        logger.info("Planned %s task reminder(s).", planned)
    return planned


async def _send_task_reminder(task_id: int) -> None:
    async with SessionLocal() as db:
        task = await db.get(CareTask, task_id)
        if task is None or task.completed or task.reminded_at is not None or task.due_at is None:
            return
        due = task.due_at if task.due_at.tzinfo else task.due_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if due - now > REMIND_BEFORE + timedelta(minutes=1):
            # The due time moved later since this timer was set; the next plan picks it up.
            return
        await send_push_to_user(
            db, task.user_id,
            title="Coming up in 5 minutes",
            body=f"{task.title}\n\n{random_quote()}",
            tag=f"carewise-task-{task.id}",
        )
        task.reminded_at = now
        await db.commit()
    logger.info("Sent a task reminder.")


async def _purge_demos() -> None:
    """Delete demo accounts older than a day, with all their data."""
    from app.services.demo import purge_expired_demos

    async with SessionLocal() as db:
        removed = await purge_expired_demos(db)
    if removed:
        logger.info("Deleted %d expired demo accounts", removed)


async def _hourly() -> None:
    """The one regular database visit: plan the next hour's reminders and clear old demos."""
    await _plan_reminders()
    await _purge_demos()


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
        _hourly,
        IntervalTrigger(hours=1),
        id="hourly",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30),  # plan soon after start
    )
    _scheduler = scheduler  # before start, so the first plan can add timers
    scheduler.start()
    logger.info("Reminder scheduler started (morning hour UTC=%s).", settings.morning_reminder_hour_utc)
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
