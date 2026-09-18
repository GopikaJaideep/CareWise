"""Tests for safety guardrails — these run without an LLM key."""
from app.core.safety import (
    RiskLevel, detect_crisis, detect_medical_overreach, redact_pii, validate_response,
)


class TestCrisisDetection:
    def test_detects_explicit_suicide(self):
        check = detect_crisis("I want to kill myself")
        assert check.risk_level == RiskLevel.CRITICAL
        assert check.requires_intervention is True

    def test_detects_self_harm(self):
        check = detect_crisis("I've been thinking about hurt myself")
        assert check.risk_level == RiskLevel.CRITICAL

    def test_detects_secondary_distress(self):
        check = detect_crisis("I just can't go on like this")
        assert check.risk_level == RiskLevel.HIGH
        assert check.requires_intervention is False

    def test_no_false_positive_on_normal_distress(self):
        check = detect_crisis("Today was really hard. Mum's nausea was bad.")
        assert check.risk_level == RiskLevel.NONE

    def test_crisis_response_includes_lifeline(self):
        check = detect_crisis("I want to end my life")
        assert "13 11 14" in check.suggested_response
        assert "Lifeline" in check.suggested_response


class TestMedicalOverreach:
    def test_detects_diagnosis_request(self):
        check = detect_medical_overreach("Can you diagnose me with anxiety?")
        assert check.risk_level == RiskLevel.MEDIUM

    def test_detects_dosage_question(self):
        check = detect_medical_overreach("Should I take more of her pain medication?")
        assert check.risk_level == RiskLevel.MEDIUM

    def test_no_false_positive_on_logging(self):
        check = detect_medical_overreach("Mum took her morning meds at 8am")
        assert check.risk_level == RiskLevel.NONE


class TestPIIRedaction:
    def test_redacts_phone(self):
        out = redact_pii("Call me on 0412 345 678")
        assert "[PHONE]" in out

    def test_redacts_email(self):
        out = redact_pii("Email: gopika@example.com")
        assert "[EMAIL]" in out

    def test_preserves_normal_text(self):
        out = redact_pii("Mum had nausea today")
        assert out == "Mum had nausea today"


class TestResponseValidation:
    def test_blocks_specific_dosage(self):
        valid, reason = validate_response("Take 50mg every morning")
        assert valid is False
        assert reason == "specific dosage"

    def test_blocks_definitive_diagnosis(self):
        valid, reason = validate_response("You definitely have cancer based on those symptoms")
        assert valid is False
        assert reason == "diagnosis"

    def test_blocks_outcome_promise(self):
        valid, _ = validate_response("This will cure her completely")
        assert valid is False

    def test_allows_safe_response(self):
        valid, reason = validate_response(
            "Fatigue during treatment is common. Your treatment team can help with strategies."
        )
        assert valid is True
        assert reason is None
