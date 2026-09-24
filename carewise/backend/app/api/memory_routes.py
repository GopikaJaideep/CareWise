"""What CareWise remembers between chats, under the person's control (see app/services/memory.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import UTCDateTime
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.db import User, UserMemory
from app.services.memory import load_memories

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryOut(BaseModel):
    id: int
    text: str
    category: str
    created_at: UTCDateTime

    class Config:
        from_attributes = True


class MemoryState(BaseModel):
    enabled: bool
    items: list[MemoryOut]


class MemorySetting(BaseModel):
    enabled: bool


async def _state(db: AsyncSession, user: User) -> MemoryState:
    return MemoryState(enabled=user.memory_enabled, items=await load_memories(db, user.id))


@router.get("", response_model=MemoryState)
async def get_memory(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _state(db, user)


@router.put("/enabled", response_model=MemoryState)
async def set_memory_enabled(
    payload: MemorySetting, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Turning memory off also forgets everything remembered so far."""
    user.memory_enabled = payload.enabled
    if not payload.enabled:
        await db.execute(delete(UserMemory).where(UserMemory.user_id == user.id))
    await db.commit()
    return await _state(db, user)


@router.delete("/{memory_id}", status_code=204)
async def forget_one(memory_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    memory = await db.scalar(select(UserMemory).where(UserMemory.id == memory_id, UserMemory.user_id == user.id))
    if memory is None:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(memory)
    await db.commit()


@router.delete("", status_code=204)
async def forget_everything(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(UserMemory).where(UserMemory.user_id == user.id))
    await db.commit()
