"""Reminders without keeping the database awake.

A job that queried every minute kept Neon's scale-to-zero database awake around the clock and used
up the month's free compute, which took the whole app down. These tests pin the replacement: one
hourly plan, exact timers, and no query between plans.
"""
from datetime import datetime, timedelta, timezone

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.db import CareTask
from app.services import scheduler


@pytest.fixture
async def running(db, monkeypatch):
    """A started scheduler whose jobs use the test database."""
    monkeypatch.setattr(scheduler, "SessionLocal", async_sessionmaker(db.bind, expire_on_commit=False))
    sent = []

    async def fake_push(_db, user_id, title, body, tag):
        sent.append((user_id, tag))

    monkeypatch.setattr(scheduler, "send_push_to_user", fake_push)
    scheduler.start_scheduler()
    yield sent
    scheduler.stop_scheduler()


def timer(task_id):
    return scheduler._scheduler.get_job(f"task_reminder_{task_id}")


async def add(db, **fields):
    task = CareTask(user_id=1, title=fields.pop("title", "Chemo"), **fields)
    db.add(task)
    await db.commit()
    return task


def test_no_job_reads_the_database_more_than_once_an_hour(running):
    for job in scheduler._scheduler.get_jobs():
        trigger = job.trigger
        assert isinstance(trigger, (CronTrigger, IntervalTrigger)), job.id
        if isinstance(trigger, IntervalTrigger):
            assert trigger.interval >= timedelta(hours=1), f"{job.id} runs every {trigger.interval}"


async def test_the_hourly_plan_sets_timers_only_for_reminders_due_before_the_next_plan(db, running):
    now = datetime.now(timezone.utc)
    soon = await add(db, due_at=now + timedelta(minutes=30))
    later = await add(db, due_at=now + timedelta(hours=3))
    done = await add(db, due_at=now + timedelta(minutes=30), completed=True)
    reminded = await add(db, due_at=now + timedelta(minutes=30), reminded_at=now)
    await add(db, title="No due time")

    assert await scheduler._plan_reminders() == 1
    run_at = timer(soon.id).next_run_time
    assert abs(run_at - (soon.due_at.replace(tzinfo=timezone.utc) - timedelta(minutes=5))) < timedelta(seconds=2)
    assert timer(later.id) is None and timer(done.id) is None and timer(reminded.id) is None


def test_a_task_saved_between_plans_gets_its_timer_without_a_query(running):
    now = datetime.now(timezone.utc)
    scheduler.note_task_due(41, now + timedelta(minutes=20))
    scheduler.note_task_due(42, now + timedelta(minutes=2))  # under 5 minutes away: remind now
    scheduler.note_task_due(43, now + timedelta(days=2))  # the hourly plan will get to it
    scheduler.note_task_due(44, None)
    assert timer(41) is not None
    assert timer(42).next_run_time - now < timedelta(seconds=5)
    assert timer(43) is None and timer(44) is None


async def test_a_reminder_is_sent_once_and_skipped_if_the_task_changed(db, running):
    sent = running
    now = datetime.now(timezone.utc)
    due = await add(db, due_at=now + timedelta(minutes=4))
    await scheduler._send_task_reminder(due.id)
    await scheduler._send_task_reminder(due.id)  # a second timer must not send it twice
    assert sent == [(1, f"carewise-task-{due.id}")]

    done = await add(db, due_at=now + timedelta(minutes=4), completed=True)
    moved = await add(db, due_at=now + timedelta(hours=2))  # due time moved after the timer was set
    await scheduler._send_task_reminder(done.id)
    await scheduler._send_task_reminder(moved.id)
    await scheduler._send_task_reminder(999)  # deleted
    assert len(sent) == 1
