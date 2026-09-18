"""Authentication routes."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ForgotPasswordRequest, ResetPasswordRequest, TokenResponse, UserLogin, UserOut, UserRegister,
)
from app.core.auth import create_access_token, get_current_user, hash_password, verify_password
from app.core.config import get_settings
from app.core.database import get_db
from app.models.db import PasswordResetToken, User
from app.services.email import send_password_reset_email

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
        care_recipient_name=payload.care_recipient_name,
        care_recipient_relation=payload.care_recipient_relation,
        diagnosis_context=payload.diagnosis_context,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        display_name=user.display_name,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return TokenResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        display_name=user.display_name,
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    # Always respond identically whether or not the email exists, so this
    # endpoint can't be used to enumerate registered accounts.
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user:
        raw_token = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.reset_token_expire_minutes),
        ))
        await db.commit()

        reset_link = f"{settings.frontend_url}/reset-password?token={raw_token}"
        await send_password_reset_email(user.email, reset_link)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    token_hash = _hash_token(payload.token)
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    reset_token = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    expires_at = reset_token.expires_at.replace(tzinfo=timezone.utc) if reset_token else None
    if not reset_token or reset_token.used or (expires_at and expires_at < now):
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user_result = await db.execute(select(User).where(User.id == reset_token.user_id))
    user = user_result.scalar_one()
    user.hashed_password = hash_password(payload.new_password)
    reset_token.used = True
    await db.commit()
