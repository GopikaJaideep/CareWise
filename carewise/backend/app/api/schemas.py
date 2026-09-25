"""Pydantic schemas for request/response validation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BaseModel, EmailStr, Field, PlainSerializer


def _as_utc_iso(dt: datetime) -> str:
    """SQLite drops tzinfo on round-trip, so every stored datetime here is
    implicitly UTC (everything is written via utcnow()-style helpers or a
    client-supplied ISO string that's already UTC) but comes back naive.
    Serializing it without a UTC marker makes JS `new Date(...)` on the
    frontend silently reinterpret it as *local* time instead of UTC —
    stamping the marker back on here is what fixes that.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


UTCDateTime = Annotated[datetime, PlainSerializer(_as_utc_iso, return_type=str)]


# --- Auth ---
class VerifyEmailRequest(BaseModel):
    token: str


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str
    care_recipient_name: str | None = None
    care_recipient_relation: str | None = None
    diagnosis_context: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    display_name: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    care_recipient_name: str | None
    care_recipient_relation: str | None
    diagnosis_context: str | None
    email_verified: bool = False
    is_demo: bool = False

    class Config:
        from_attributes = True


# --- Chat ---
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
    # IANA name from the browser (e.g. "Australia/Sydney"); used to interpret
    # "Tuesday at 10". Unknown or missing falls back to UTC.
    timezone: str | None = Field(default=None, max_length=64)


class AgentTrace(BaseModel):
    agent: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    conversation_id: int
    message_id: int
    content: str
    agent_trace: list[AgentTrace]
    risk_level: str | None = None
    # How this reply was made: routing, agents, model calls, tokens, timing. No message text.
    turn: dict[str, Any] | None = None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    agent_used: str | None
    created_at: UTCDateTime
    turn: dict[str, Any] | None = None  # trace summary, for assistant messages

    class Config:
        from_attributes = True


class ConversationSummary(BaseModel):
    """List view: no messages, so building it never touches the lazy relationship."""
    id: int
    title: str
    created_at: UTCDateTime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: UTCDateTime
    messages: list[MessageOut] = []

    class Config:
        from_attributes = True


# --- Tracking ---
class SymptomLogCreate(BaseModel):
    symptom: str = Field(min_length=1, max_length=120)
    severity: int = Field(ge=1, le=10)
    notes: str | None = None
    logged_at: datetime | None = None


class SymptomLogOut(BaseModel):
    id: int
    symptom: str
    severity: int
    notes: str | None
    logged_at: UTCDateTime

    class Config:
        from_attributes = True


class MedicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dosage: str = Field(min_length=1, max_length=60)
    schedule: str = Field(min_length=1, max_length=120)
    notes: str | None = None


class MedicationOut(BaseModel):
    id: int
    name: str
    dosage: str
    schedule: str
    notes: str | None
    active: bool

    class Config:
        from_attributes = True


class CareTaskCreate(BaseModel):
    title: str
    description: str | None = None
    due_at: datetime | None = None
    category: str = "general"


class CareTaskOut(BaseModel):
    id: int
    title: str
    description: str | None
    due_at: UTCDateTime | None
    completed: bool
    category: str

    class Config:
        from_attributes = True


class BurnoutCheckinCreate(BaseModel):
    sleep_hours: float = Field(ge=0, le=24)
    stress_level: int = Field(ge=1, le=10)
    energy_level: int = Field(ge=1, le=10)
    self_care_minutes: int = Field(ge=0, le=1440)
    notes: str | None = Field(default=None, max_length=1000)


class BurnoutCheckinOut(BaseModel):
    id: int
    sleep_hours: float
    stress_level: int
    energy_level: int
    self_care_minutes: int
    notes: str | None
    burnout_score: float
    created_at: UTCDateTime

    class Config:
        from_attributes = True


class BurnoutCheckinResult(BurnoutCheckinOut):
    category: str


# --- Push notifications ---
class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys


class VapidPublicKeyOut(BaseModel):
    public_key: str


class DashboardSummary(BaseModel):
    open_tasks_count: int
    today_tasks_count: int
    recent_symptom_count: int
    latest_burnout_score: float | None
    burnout_category: str | None
    burnout_trend: list[float]
    active_medications: int
    quote_of_the_day: str
