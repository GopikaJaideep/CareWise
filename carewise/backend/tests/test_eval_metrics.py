"""The eval numbers are only worth publishing if the scoring is right."""
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from evals.metrics import (
    binary_report, classification_report, extraction_summary, percentile, score_medications,
    score_symptoms, score_tasks,
)

SYDNEY = ZoneInfo("Australia/Sydney")
DATASETS = Path(__file__).resolve().parents[1] / "evals" / "datasets"


def test_classification_report_counts_precision_recall_and_confusion():
    pairs = [("a", "a"), ("a", "b"), ("b", "b"), ("b", "b"), ("c", "b")]
    r = classification_report(pairs, ["a", "b", "c"])
    assert r["accuracy"] == pytest.approx(3 / 5)
    assert r["per_label"]["a"] == pytest.approx({"precision": 1.0, "recall": 0.5, "f1": 2 / 3, "support": 2})
    assert r["per_label"]["b"]["precision"] == pytest.approx(2 / 4)
    assert r["per_label"]["c"]["recall"] == 0.0
    assert r["confusion"]["c"] == {"b": 1}


def test_binary_report_recall_and_false_positive_rate():
    r = binary_report([(True, True), (True, False), (False, True), (False, False), (False, False)])
    assert (r["tp"], r["fn"], r["fp"], r["tn"]) == (1, 1, 1, 2)
    assert r["recall"] == 0.5
    assert r["false_positive_rate"] == pytest.approx(1 / 3)


def test_symptoms_matched_by_alias_and_severity():
    expected = [{"symptom": ["nausea", "nauseous"], "severity": 6}]
    assert score_symptoms(expected, {"symptoms": [{"symptom": "Nauseous", "severity": "6/10"}]})["exact"]
    assert not score_symptoms(expected, {"symptoms": [{"symptom": "nausea", "severity": 5}]})["exact"]


def test_symptoms_without_a_number_must_log_nothing():
    # The agent skips items with no usable severity, so the model returning one isn't penalised...
    assert score_symptoms([], {"symptoms": [{"symptom": "pain", "severity": None}]})["exact"]
    # ...but inventing a number is.
    assert not score_symptoms([], {"symptoms": [{"symptom": "pain", "severity": 8}]})["exact"]


def test_extra_symptoms_break_exact_match():
    s = score_symptoms([{"symptom": ["pain"], "severity": 7}],
                       {"symptoms": [{"symptom": "pain", "severity": 7}, {"symptom": "nausea", "severity": 3}]})
    assert s["matched"] == 1 and not s["exact"]


def test_medications_need_name_dose_and_schedule():
    expected = [{"name": "ondansetron", "dosage": "8", "schedule": ["twice"]}]
    ok = {"medications": [{"action": "added", "name": "Ondansetron", "dosage": "8mg", "schedule": "twice a day"}]}
    assert score_medications(expected, ok)["exact"]
    wrong_dose = {"medications": [{"action": "added", "name": "ondansetron", "dosage": "4mg", "schedule": "twice a day"}]}
    assert not score_medications(expected, wrong_dose)["exact"]


def test_tasks_compare_due_time_in_local_time():
    expected = [{"title": ["chemo"], "due": "2026-09-29T10:00", "category": ["appointment"]}]
    local = {"tasks": [{"title": "Chemo", "due_at": "2026-09-29T10:00:00", "category": "appointment"}]}
    assert score_tasks(expected, local, SYDNEY)["exact"]
    # Same instant expressed in UTC is also right.
    utc = {"tasks": [{"title": "Chemo", "due_at": "2026-09-29T00:00:00Z", "category": "appointment"}]}
    assert score_tasks(expected, utc, SYDNEY)["exact"]
    # 10am UTC is 8pm in Sydney: wrong.
    wrong = {"tasks": [{"title": "Chemo", "due_at": "2026-09-29T10:00:00Z", "category": "appointment"}]}
    assert score_tasks(expected, wrong, SYDNEY)["fields"] == {"title": 1, "due": 0, "category": 1}


def test_tasks_date_only_and_no_date_expectations():
    tomorrow = [{"title": ["pharmacy"], "due_date": "2026-09-24", "category": ["errand"]}]
    assert score_tasks(tomorrow, {"tasks": [{"title": "Pharmacy", "due_at": "2026-09-24T17:00:00", "category": "errand"}]}, SYDNEY)["exact"]
    undated = [{"title": ["shake"], "due": None, "category": ["errand"]}]
    assert score_tasks(undated, {"tasks": [{"title": "Buy shakes", "due_at": None, "category": "errand"}]}, SYDNEY)["exact"]
    assert not score_tasks(undated, {"tasks": [{"title": "Buy shakes", "due_at": "2026-09-26T10:00:00", "category": "errand"}]}, SYDNEY)["exact"]


def test_extraction_summary_and_percentile():
    s = extraction_summary([{"matched": 1, "expected": 1, "predicted": 2, "exact": False},
                            {"matched": 0, "expected": 0, "predicted": 0, "exact": True}])
    assert s["precision"] == 0.5 and s["recall"] == 1.0 and s["exact_match"] == 0.5
    assert percentile([0.1, 0.2, 0.3, 0.4], 50) == 0.2
    assert percentile([0.1, 0.2, 0.3, 0.4], 95) == 0.4


@pytest.mark.parametrize("name", ["routing", "crisis", "symptoms", "tasks"])
def test_datasets_are_valid_jsonl_with_unique_ids(name):
    rows = [json.loads(line) for line in (DATASETS / f"{name}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)) and len(rows) >= 18


class _FakeModel:
    provider, model = "fake", "fake-model"

    async def complete_json(self, system, messages, schema_hint, max_tokens=None):
        if "routing layer" in system:
            return {"agent": "resource_guide"}
        if "care-coordination" in system:
            return {"tasks": [{"title": "Chemo", "due_at": "2026-09-29T10:00:00", "category": "appointment"}]}
        return {"symptoms": [{"symptom": "nausea", "severity": 6}]}

    async def complete(self, system, messages, **kwargs):
        return "ok"


async def test_runner_end_to_end_with_a_fake_model(monkeypatch, capsys):
    from evals import run

    monkeypatch.setattr(run, "get_llm_client", lambda: _FakeModel())
    assert await run.main(["--no-write", "--limit", "3"]) == 0
    out = capsys.readouterr().out
    for heading in ("## Crisis detection", "## Routing", "## Symptom & medication extraction", "## Task extraction"):
        assert heading in out
    assert "Skipped" not in out


class _OutageModel(_FakeModel):
    """Every call fails the way the real client does: recorded as not ok, friendly text back."""

    async def complete_json(self, system, messages, schema_hint, max_tokens=None):
        from app.core.tracing import record_call
        record_call(provider="fake", model="fake-model", latency_ms=1, ok=False)
        return {}


async def test_an_api_outage_aborts_the_run_instead_of_scoring_it(monkeypatch, capsys):
    from evals import run

    monkeypatch.setattr(run, "get_llm_client", lambda: _OutageModel())
    assert await run.main(["--no-write", "--suite", "routing", "--limit", "5"]) == 2
    assert "Aborted: 5 of 5 routing cases failed at the API" in capsys.readouterr().err
