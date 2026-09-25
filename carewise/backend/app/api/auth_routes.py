"""Authentication routes."""
from __future__ import annotations

import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ForgotPasswordRequest, ResetPasswordRequest, TokenResponse, UserLogin, UserOut, UserRegister,
    VerifyEmailRequest,
)
from app.core.auth import (
    create_access_token, create_email_verification_token, get_current_user, hash_password,
    read_email_verification_token, verify_password,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.models.db import PasswordResetToken, User
from app.services import demo
from app.services.email import send_password_reset_email, send_verification_email

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

# Confirmation emails sent after the response; kept here so they finish.
_background: set[asyncio.Task] = set()


def _by_email(email: str):
    """Email match ignoring case: Someone@gmail.com and someone@gmail.com are one inbox, so they
    must be one account, and logging in mustn't depend on how it was capitalised."""
    return select(User).where(func.lower(User.email) == email.strip().lower())


async def _real_email(email: str) -> str:
    """The address, normalised, if its domain exists and accepts mail; otherwise a 400.

    Catches made-up and mistyped addresses ("anything@madeup.xyz", "someone@gmial.con").
    It can't prove the address belongs to this person: the confirmation link does that.
    """
    if not settings.email_check_deliverability:
        return email.strip().lower()
    try:
        # A DNS lookup: blocking, so run it off the event loop.
        result = await asyncio.to_thread(validate_email, email.strip(), check_deliverability=True)
    except EmailNotValidError:
        raise HTTPException(
            status_code=400,
            detail="That email address doesn't seem to exist. Please check it for typos.",
        )
    return result.normalized.lower()


def _send_confirmation(user: User) -> None:
    link = f"{settings.frontend_url}/verify-email?token={create_email_verification_token(user.id, user.email)}"
    task = asyncio.create_task(send_verification_email(user.email, link))
    _background.add(task)
    task.add_done_callback(_background.discard)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    email = await _real_email(payload.email)
    existing = await db.execute(_by_email(email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
        care_recipient_name=payload.care_recipient_name,
        care_recipient_relation=payload.care_recipient_relation,
        diagnosis_context=payload.diagnosis_context,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    _send_confirmation(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        display_name=user.display_name,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(_by_email(payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return TokenResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        display_name=user.display_name,
    )


@router.post("/demo", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def start_demo(request: Request, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """A private, pre-filled demo account: no sign-up, deleted after a day (app/services/demo.py)."""
    # Behind Render's proxy the client address is the first X-Forwarded-For entry. It can be
    # spoofed, so this limit is best-effort; the cap on live demos is the hard ceiling.
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    if not demo.allow_new_demo(ip):
        raise HTTPException(status_code=429, detail="You've started several demos recently. Please use the one you have, or try again in an hour.")
    try:
        user = await demo.create_demo_user(db)
    except demo.DemoUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    return TokenResponse(access_token=create_access_token(user.id), user_id=user.id, display_name=user.display_name)


@router.post("/verify-email", response_model=UserOut)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> User:
    """Confirm an address from the link emailed at sign-up. Needs no login: the link is the proof."""
    claims = read_email_verification_token(payload.token)
    user = await db.get(User, claims[0]) if claims else None
    if user is None or user.email.lower() != claims[1]:
        raise HTTPException(status_code=400, detail="This confirmation link is invalid or has expired.")
    if not user.email_verified:
        user.email_verified = True
        await db.commit()
    return user


@router.post("/resend-verification", status_code=202)
async def resend_verification(current_user: User = Depends(get_current_user)):
    if not current_user.email_verified:
        _send_confirmation(current_user)
    return {"status": "sent"}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    # Always respond identically whether or not the email exists, so this
    # endpoint can't be used to enumerate registered accounts.
    result = await db.execute(_by_email(payload.email))
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
