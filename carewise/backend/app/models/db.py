"""SQLAlchemy models for CareWise."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    care_recipient_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    care_recipient_relation: Mapped[str | None] = mapped_column(String(60), nullable=True)
    diagnosis_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    symptom_logs: Mapped[list["SymptomLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    medications: Mapped[list["Medication"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tasks: Mapped[list["CareTask"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    burnout_checkins: Mapped[list["BurnoutCheckin"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    agent_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class SymptomLog(Base):
    __tablename__ = "symptom_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    symptom: Mapped[str] = mapped_column(String(120))
    severity: Mapped[int] = mapped_column(Integer)  # 1-10
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    user: Mapped["User"] = relationship(back_populates="symptom_logs")


class Medication(Base):
    __tablename__ = "medications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120))
    dosage: Mapped[str] = mapped_column(String(60))
    schedule: Mapped[str] = mapped_column(String(120))  # e.g. "8am, 8pm" or "every 6 hours"
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    user: Mapped["User"] = relationship(back_populates="medications")


class CareTask(Base):
    __tablename__ = "care_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(60), default="general")  # appointment | medication | errand | general
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    user: Mapped["User"] = relationship(back_populates="tasks")


class BurnoutCheckin(Base):
    __tablename__ = "burnout_checkins"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sleep_hours: Mapped[float] = mapped_column(Float)
    stress_level: Mapped[int] = mapped_column(Integer)  # 1-10
    energy_level: Mapped[int] = mapped_column(Integer)  # 1-10
    self_care_minutes: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    burnout_score: Mapped[float] = mapped_column(Float)  # computed 0-100
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    user: Mapped["User"] = relationship(back_populates="burnout_checkins")
