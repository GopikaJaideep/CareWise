"""Tests for the burnout scoring algorithm."""
import pytest

from app.agents.burnout_monitor import categorise, compute_burnout_score


class TestBurnoutScore:
    def test_well_rested_caregiver(self):
        score = compute_burnout_score(
            sleep_hours=8, stress_level=2, energy_level=8, self_care_minutes=60
        )
        assert score < 30
        assert categorise(score) == "low"

    def test_severely_burnt_out(self):
        score = compute_burnout_score(
            sleep_hours=3, stress_level=10, energy_level=1, self_care_minutes=0
        )
        assert score >= 75
        assert categorise(score) == "very high"

    def test_moderate_burnout(self):
        score = compute_burnout_score(
            sleep_hours=6, stress_level=6, energy_level=5, self_care_minutes=15
        )
        assert 30 <= score < 75

    def test_trend_amplifies_score(self):
        baseline = compute_burnout_score(
            sleep_hours=5, stress_level=7, energy_level=4, self_care_minutes=10
        )
        with_trend = compute_burnout_score(
            sleep_hours=5, stress_level=7, energy_level=4, self_care_minutes=10,
            recent_trend=[40, 50, 60],
        )
        assert with_trend > baseline

    def test_score_capped_at_100(self):
        score = compute_burnout_score(
            sleep_hours=0, stress_level=10, energy_level=1, self_care_minutes=0,
            recent_trend=[10, 50, 90],
        )
        assert score <= 100

    def test_categorise_boundaries(self):
        assert categorise(0) == "low"
        assert categorise(29.9) == "low"
        assert categorise(30) == "moderate"
        assert categorise(54.9) == "moderate"
        assert categorise(55) == "high"
        assert categorise(74.9) == "high"
        assert categorise(75) == "very high"
        assert categorise(100) == "very high"
