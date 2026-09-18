"""Safety guardrails for healthcare AI interactions.

This module implements responsible AI guardrails specific to caregiver support:
- Crisis detection (suicidal ideation, self-harm)
- Medical advice boundaries (no diagnosis, no dosage changes)
- PII redaction in logs
- Output validation
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.core.config import get_settings

settings = get_settings()


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SafetyCheck:
    risk_level: RiskLevel
    triggers: list[str]
    requires_intervention: bool
    suggested_response: str | None = None


CRISIS_RESOURCES = {
    "AU": {
        "Lifeline": "13 11 14",
        "Beyond Blue": "1300 22 4636",
        "Suicide Call Back Service": "1300 659 467",
        "Cancer Council": "13 11 20",
    },
    "US": {
        "988 Suicide & Crisis Lifeline": "988",
        "Crisis Text Line": "Text HOME to 741741",
        "Cancer Support Helpline": "1-888-793-9355",
    },
}

MEDICAL_BOUNDARY_PATTERNS = [
    r"\b(diagnose|diagnosis)\b.*\b(me|my|him|her)\b",
    r"\bshould (i|we|they) (take|stop|increase|decrease)\b",
    r"\b(safe|okay|ok) to (mix|combine|take with)\b",
    r"\bhow much .{0,20}(should|can) .{0,20}take\b",
]


def detect_crisis(text: str) -> SafetyCheck:
    """Detect crisis-level content requiring immediate intervention.

    Returns a SafetyCheck. If crisis keywords are present, the response
    must include crisis resources and decline to engage as a substitute
    for emergency support.
    """
    lower = text.lower()
    triggers = [kw for kw in settings.crisis_keywords if kw in lower]

    if triggers:
        return SafetyCheck(
            risk_level=RiskLevel.CRITICAL,
            triggers=triggers,
            requires_intervention=True,
            suggested_response=_format_crisis_response(),
        )

    # Secondary signals — emotional distress without explicit crisis terms
    distress_signals = ["can't go on", "give up", "no point", "everything is hopeless"]
    secondary = [s for s in distress_signals if s in lower]
    if secondary:
        return SafetyCheck(
            risk_level=RiskLevel.HIGH,
            triggers=secondary,
            requires_intervention=False,
        )

    return SafetyCheck(
        risk_level=RiskLevel.NONE, triggers=[], requires_intervention=False
    )


def detect_medical_overreach(text: str) -> SafetyCheck:
    """Detect requests that exceed CareWise's scope (diagnosis, dosing)."""
    lower = text.lower()
    triggers = []
    for pattern in MEDICAL_BOUNDARY_PATTERNS:
        if re.search(pattern, lower):
            triggers.append(pattern)

    if triggers:
        return SafetyCheck(
            risk_level=RiskLevel.MEDIUM,
            triggers=triggers,
            requires_intervention=False,
        )
    return SafetyCheck(
        risk_level=RiskLevel.NONE, triggers=[], requires_intervention=False
    )


def _format_crisis_response(region: str = "AU") -> str:
    resources = CRISIS_RESOURCES.get(region, CRISIS_RESOURCES["AU"])
    lines = [
        "I'm really concerned about what you're sharing, and I want to make sure you get support from someone trained for this.",
        "",
        "Please reach out right now to one of these services — they're free, confidential, and available 24/7:",
        "",
    ]
    for name, contact in resources.items():
        lines.append(f"  • {name}: {contact}")
    lines.extend([
        "",
        "If you or someone with you is in immediate danger, please call 000 (Australia) or your local emergency number.",
        "",
        "I'm still here when you're ready to talk about anything else.",
    ])
    return "\n".join(lines)


def redact_pii(text: str) -> str:
    """Redact obvious PII for safe logging. Not a substitute for proper PII handling."""
    # Phone numbers (US 555-555-5555, AU mobile 0412 345 678, international)
    text = re.sub(r"\b(?:\+?\d{1,3}[-.\s]?)?\d{3,4}[-.\s]?\d{3}[-.\s]?\d{3,4}\b", "[PHONE]", text)
    # Emails
    text = re.sub(r"\b[\w.-]+@[\w.-]+\.\w+\b", "[EMAIL]", text)
    # Medicare-style numbers (AU)
    text = re.sub(r"\b\d{4}\s?\d{5}\s?\d{1,2}\b", "[MEDICARE]", text)
    return text


def validate_response(text: str) -> tuple[bool, str | None]:
    """Final pass on LLM output before returning to user.

    Catches:
    - Specific dosage recommendations
    - Definitive diagnoses
    - Promises about medical outcomes
    """
    flagged_phrases = [
        (r"\btake \d+\s?(mg|ml|mcg)\b", "specific dosage"),
        (r"\byou (have|definitely have)\b.{0,30}\b(cancer|disease|disorder)\b", "diagnosis"),
        (r"\bwill (cure|fix|heal)\b", "outcome promise"),
    ]
    for pattern, reason in flagged_phrases:
        if re.search(pattern, text.lower()):
            return False, reason
    return True, None
