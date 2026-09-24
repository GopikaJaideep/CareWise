"""Pydantic models for every structured (JSON) model output in CareWise.

LLMClient.complete_structured() validates the model's JSON against one of these, with one repair
retry on failure. Validators are lenient where a sensible cleanup exists ("6/10" -> 6, an unknown
task category -> "general", an out-of-range check-in number -> treated as not given) and strict
where it matters (a routing answer that isn't a real agent, a task with no title).
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


AgentChoice = Literal["emotional_support", "symptom_tracker", "care_coordinator", "resource_guide", "burnout_monitor"]


def parse_severity(value) -> int | None:
    """Model output -> 1-10, or None if it isn't a usable number.

    Handles "6", 6, 6.5 and "6/10". Rejects out-of-range values (0, 15) rather than
    saving a severity the app's 1-10 scale can't represent.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        match = re.match(r"\s*(\d+(?:\.\d+)?)", str(value))
        if not match:
            return None
        number = float(match.group(1))
    severity = round(number)
    return severity if 1 <= severity <= 10 else None


def _in_range(value: Any, low: float, high: float, cast=float) -> Any:
    """A number within [low, high], else None (the agent then asks rather than guessing)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = cast(value)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


# --- Router -------------------------------------------------------------------------------------

class RouteIntent(BaseModel):
    agent: AgentChoice
    text: str = ""  # the part of the message this agent should handle


class RouteDecision(BaseModel):
    intents: list[RouteIntent] = Field(min_length=1, max_length=3)
    reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def single_agent_form(cls, data: Any) -> Any:
        # Accept the older single-intent shape {"agent": "..."} as one intent.
        if isinstance(data, dict) and "intents" not in data and "agent" in data:
            return {"intents": [{"agent": data["agent"], "text": ""}], "reason": data.get("reason", "")}
        return data


# --- Symptom tracker ----------------------------------------------------------------------------

class SymptomItem(BaseModel):
    symptom: str = Field(min_length=1)
    severity: int | None = None
    notes: str | None = None

    @field_validator("severity", mode="before")
    @classmethod
    def clean_severity(cls, v: Any) -> int | None:
        return parse_severity(v)


class MedicationItem(BaseModel):
    action: Literal["added", "taken", "missed", "updated"]
    name: str = Field(min_length=1)
    dosage: str | None = None
    schedule: str | None = None
    notes: str | None = None

    @field_validator("action", mode="before")
    @classmethod
    def lower_action(cls, v: Any) -> Any:
        return v.lower() if isinstance(v, str) else v


class SymptomExtraction(BaseModel):
    symptoms: list[SymptomItem] = []
    medications: list[MedicationItem] = []
    query: Literal["list_symptoms", "list_medications", "trend"] | None = None
    confidence: float | None = None

    @field_validator("query", mode="before")
    @classmethod
    def unknown_query_is_none(cls, v: Any) -> Any:
        return v if v in ("list_symptoms", "list_medications", "trend") else None

    @field_validator("symptoms", "medications", mode="before")
    @classmethod
    def null_is_empty(cls, v: Any) -> Any:
        return [] if v is None else v


# --- Care coordinator ---------------------------------------------------------------------------

class TaskItem(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    due_at: str | None = None
    category: str = "general"

    @field_validator("category", mode="before")
    @classmethod
    def known_category(cls, v: Any) -> str:
        v = str(v or "general").lower()
        return v if v in ("appointment", "medication", "errand", "general") else "general"


class TaskExtraction(BaseModel):
    tasks: list[TaskItem] = []
    query: Literal["list_tasks", "list_today", "list_upcoming"] | None = None
    mark_done: list[str] = []

    @field_validator("query", mode="before")
    @classmethod
    def unknown_query_is_none(cls, v: Any) -> Any:
        return v if v in ("list_tasks", "list_today", "list_upcoming") else None

    @field_validator("tasks", "mark_done", mode="before")
    @classmethod
    def null_is_empty(cls, v: Any) -> Any:
        return [] if v is None else v


# --- Burnout monitor ----------------------------------------------------------------------------

class CheckinExtraction(BaseModel):
    """Out-of-range numbers become None, so the agent asks for them instead of saving nonsense
    (before this, "stress 15" from the model would have been saved as-is)."""

    sleep_hours: float | None = None
    stress_level: int | None = None
    energy_level: int | None = None
    self_care_minutes: int | None = None
    notes: str | None = None
    is_checkin: bool = False

    @field_validator("sleep_hours", mode="before")
    @classmethod
    def sleep_range(cls, v: Any) -> Any:
        return _in_range(v, 0, 24)

    @field_validator("stress_level", "energy_level", mode="before")
    @classmethod
    def scale_range(cls, v: Any) -> Any:
        number = _in_range(v, 1, 10)
        return None if number is None else round(number)

    @field_validator("self_care_minutes", mode="before")
    @classmethod
    def minutes_range(cls, v: Any) -> Any:
        number = _in_range(v, 0, 1440)
        return None if number is None else round(number)

    @field_validator("is_checkin", mode="before")
    @classmethod
    def truthy(cls, v: Any) -> bool:
        return v is True or str(v).lower() == "true"


# --- Risk screen --------------------------------------------------------------------------------

class RiskOutput(BaseModel):
    level: Literal["none", "concern", "crisis"]
    who: Literal["self", "care_recipient", "other", "unknown"] = "unknown"
    reason: str = ""

    @field_validator("level", mode="before")
    @classmethod
    def lower_level(cls, v: Any) -> Any:
        return v.lower() if isinstance(v, str) else v

    @field_validator("who", mode="before")
    @classmethod
    def known_who(cls, v: Any) -> str:
        v = str(v or "unknown").lower()
        return v if v in ("self", "care_recipient", "other") else "unknown"
