"""Direct CRUD routes for tracking entities (symptoms, meds, tasks, burnout, dashboard)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.burnout_monitor import categorise
from app.api.schemas import (
    BurnoutCheckinOut, CareTaskCreate, CareTaskOut, DashboardSummary,
    MedicationOut, SymptomLogOut,
)
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.db import BurnoutCheckin, CareTask, Medication, SymptomLog, User

router = APIRouter(prefix="/api", tags=["tracking"])


@router.get("/symptoms", response_model=list[SymptomLogOut])
async def list_symptoms(
    days: int = 14,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(SymptomLog)
        .where(SymptomLog.user_id == current_user.id, SymptomLog.logged_at >= cutoff)
        .order_by(SymptomLog.logged_at.desc())
    )
    return list(result.scalars())


@router.get("/medications", response_model=list[MedicationOut])
async def list_medications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Medication)
        .where(Medication.user_id == current_user.id, Medication.active.is_(True))
        .order_by(Medication.created_at.desc())
    )
    return list(result.scalars())


@router.get("/tasks", response_model=list[CareTaskOut])
async def list_tasks(
    include_completed: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CareTask).where(CareTask.user_id == current_user.id)
    if not include_completed:
        stmt = stmt.where(CareTask.completed.is_(False))
    stmt = stmt.order_by(CareTask.due_at.asc().nullslast())
    result = await db.execute(stmt)
    return list(result.scalars())


@router.post("/tasks", response_model=CareTaskOut)
async def create_task(
    payload: CareTaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = CareTask(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        due_at=payload.due_at,
        category=payload.category,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/tasks/{task_id}/complete", response_model=CareTaskOut)
async def complete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CareTask).where(CareTask.id == task_id, CareTask.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.completed = True
    await db.commit()
    await db.refresh(task)
    return task


@router.get("/burnout/checkins", response_model=list[BurnoutCheckinOut])
async def list_burnout(
    limit: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BurnoutCheckin)
        .where(BurnoutCheckin.user_id == current_user.id)
        .order_by(BurnoutCheckin.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


@router.get("/dashboard", response_model=DashboardSummary)
async def dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    week_ago = now - timedelta(days=7)

    open_count = await db.scalar(
        select(func.count(CareTask.id)).where(
            CareTask.user_id == current_user.id, CareTask.completed.is_(False)
        )
    ) or 0

    today_count = await db.scalar(
        select(func.count(CareTask.id)).where(
            CareTask.user_id == current_user.id,
            CareTask.completed.is_(False),
            CareTask.due_at >= today_start,
            CareTask.due_at < today_end,
        )
    ) or 0

    symptom_count = await db.scalar(
        select(func.count(SymptomLog.id)).where(
            SymptomLog.user_id == current_user.id,
            SymptomLog.logged_at >= week_ago,
        )
    ) or 0

    med_count = await db.scalar(
        select(func.count(Medication.id)).where(
            Medication.user_id == current_user.id, Medication.active.is_(True)
        )
    ) or 0

    bc_result = await db.execute(
        select(BurnoutCheckin)
        .where(BurnoutCheckin.user_id == current_user.id)
        .order_by(BurnoutCheckin.created_at.desc())
        .limit(7)
    )
    checkins = list(bc_result.scalars())
    latest = checkins[0] if checkins else None
    trend = [c.burnout_score for c in reversed(checkins)]

    return DashboardSummary(
        open_tasks_count=open_count,
        today_tasks_count=today_count,
        recent_symptom_count=symptom_count,
        latest_burnout_score=latest.burnout_score if latest else None,
        burnout_category=categorise(latest.burnout_score) if latest else None,
        burnout_trend=trend,
        active_medications=med_count,
    )
