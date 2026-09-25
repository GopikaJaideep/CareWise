"""Authentication: password hashing and JWT tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.db import User

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire, "purpose": "access"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_email_verification_token(user_id: int, email: str) -> str:
    """Signed link token for confirming an email address. Tied to the address, so changing the
    email invalidates it, and marked with its purpose so it can't be used to log in."""
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.verify_email_expire_hours)
    payload = {"sub": str(user_id), "email": email.lower(), "exp": expire, "purpose": "verify_email"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def read_email_verification_token(token: str) -> tuple[int, str] | None:
    """(user id, email) if the token is a valid, unexpired confirmation token; else None."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
    if payload.get("purpose") != "verify_email":
        return None
    try:
        return int(payload["sub"]), str(payload["email"])
    except (KeyError, TypeError, ValueError):
        return None


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    creds_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise creds_error
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        # Only access tokens log in (tokens issued before purposes existed have none: still fine).
        if payload.get("purpose", "access") != "access":
            raise creds_error
        user_id = int(payload.get("sub", 0))
        if not user_id:
            raise creds_error
    except (JWTError, ValueError):
        raise creds_error

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise creds_error
    return user
