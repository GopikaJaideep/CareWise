"""Pydantic schemas for request/response validation."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


# --- Auth ---
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

    class Config:
        from_attributes = True


# --- Chat ---
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None


class AgentTrace(BaseModel):
    agent: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    conversation_id: int
    message_id: int
    content: str
    agent_trace: list[AgentTrace]
    risk_level: str | None = None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    agent_used: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
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
    logged_at: datetime

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
    due_at: datetime | None
    completed: bool
    category: str

    class Config:
        from_attributes = True


class BurnoutCheckinOut(BaseModel):
    id: int
    sleep_hours: float
    stress_level: int
    energy_level: int
    self_care_minutes: int
    notes: str | None
    burnout_score: float
    created_at: datetime

    class Config:
        from_attributes = True


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
