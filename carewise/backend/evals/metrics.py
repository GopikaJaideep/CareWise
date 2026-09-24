"""Scoring for the eval suites. Pure functions, unit-tested in tests/test_eval_metrics.py."""
from __future__ import annotations

import math
from collections import Counter
from datetime import tzinfo
from typing import Any, Iterable

from app.agents.symptom_tracker import parse_severity
from app.core.tz import parse_due_at, to_local


# --- Classification (routing) -------------------------------------------------------------------

def classification_report(pairs: Iterable[tuple[str, str]], labels: list[str]) -> dict[str, Any]:
    """Accuracy, per-label precision/recall/F1, macro-F1 and a confusion matrix.

    `pairs` are (expected, predicted). Predictions outside `labels` still count as wrong.
    """
    pairs = list(pairs)
    confusion = {e: Counter() for e in labels}
    for expected, predicted in pairs:
        confusion.setdefault(expected, Counter())[predicted] += 1

    per_label = {}
    for label in labels:
        tp = confusion.get(label, Counter())[label]
        predicted_as = sum(c[label] for c in confusion.values())
        support = sum(confusion.get(label, Counter()).values())
        precision = tp / predicted_as if predicted_as else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {"precision": precision, "recall": recall, "f1": f1, "support": support}

    correct = sum(1 for e, p in pairs if e == p)
    scored = [m["f1"] for m in per_label.values() if m["support"]]
    return {
        "n": len(pairs),
        "accuracy": correct / len(pairs) if pairs else 0.0,
        "macro_f1": sum(scored) / len(scored) if scored else 0.0,
        "per_label": per_label,
        "confusion": {e: dict(c) for e, c in confusion.items()},
    }


def binary_report(pairs: Iterable[tuple[bool, bool]]) -> dict[str, Any]:
    """For a detector where missing a positive is the costly mistake (crisis detection).

    recall = share of real crises caught; false_positive_rate = share of ordinary messages flagged.
    """
    pairs = list(pairs)
    tp = sum(1 for e, p in pairs if e and p)
    fn = sum(1 for e, p in pairs if e and not p)
    fp = sum(1 for e, p in pairs if not e and p)
    tn = sum(1 for e, p in pairs if not e and not p)
    return {
        "n": len(pairs),
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
        "accuracy": (tp + tn) / len(pairs) if pairs else 0.0,
    }


# --- Extraction ---------------------------------------------------------------------------------

def _mentions(text: Any, aliases: list[str]) -> bool:
    text = str(text or "").lower()
    return any(a.lower() in text for a in aliases)


def score_symptoms(expected: list[dict], extracted: dict) -> dict[str, Any]:
    """Compare what the agent WOULD log with the expected symptoms.

    Mirrors the agent: an item is only logged if it has a name and a usable 1-10 severity, so
    "pain is really bad" (no number) should log nothing. Each expected symptom can be matched once.
    """
    would_log = []
    for item in extracted.get("symptoms") or []:
        severity = parse_severity(item.get("severity")) if isinstance(item, dict) else None
        if isinstance(item, dict) and item.get("symptom") and severity is not None:
            would_log.append({"symptom": str(item["symptom"]), "severity": severity})

    unmatched = list(would_log)
    matched = 0
    for exp in expected:
        hit = next(
            (s for s in unmatched if _mentions(s["symptom"], exp["symptom"]) and s["severity"] == exp["severity"]),
            None,
        )
        if hit:
            matched += 1
            unmatched.remove(hit)
    return {
        "matched": matched,
        "expected": len(expected),
        "predicted": len(would_log),
        "exact": matched == len(expected) and not unmatched,
        "logged": would_log,
    }


def score_medications(expected: list[dict], extracted: dict) -> dict[str, Any]:
    added = [m for m in extracted.get("medications") or [] if isinstance(m, dict) and m.get("action") == "added"]
    matched = 0
    for exp in expected:
        if any(
            _mentions(m.get("name"), [exp["name"]])
            and _mentions(m.get("dosage"), [exp["dosage"]])
            and _mentions(m.get("schedule"), exp["schedule"])
            for m in added
        ):
            matched += 1
    return {"matched": matched, "expected": len(expected), "predicted": len(added),
            "exact": matched == len(expected) and len(added) == len(expected)}


def score_tasks(expected: list[dict], extracted: dict, tz: tzinfo) -> dict[str, Any]:
    """Title keyword, due date/time (in the caregiver's local time) and category, per task."""
    predicted = []
    for t in extracted.get("tasks") or []:
        if not isinstance(t, dict) or not t.get("title"):
            continue
        due = parse_due_at(t["due_at"], tz) if t.get("due_at") else None
        predicted.append({
            "title": str(t["title"]),
            "due_local": to_local(due, tz).strftime("%Y-%m-%dT%H:%M") if due else None,
            "category": str(t.get("category") or "general").lower(),
        })

    unmatched = list(predicted)
    fields = Counter()
    matched = 0
    for exp in expected:
        candidate = next((p for p in unmatched if _mentions(p["title"], exp["title"])), None)
        if not candidate:
            continue
        unmatched.remove(candidate)
        fields["title"] += 1
        if "due" in exp:
            due_ok = candidate["due_local"] == exp["due"]
        else:  # only the date is pinned down ("tomorrow", "Monday")
            due_ok = bool(candidate["due_local"]) and candidate["due_local"][:10] == exp["due_date"]
        fields["due"] += due_ok
        category_ok = candidate["category"] in exp["category"]
        fields["category"] += category_ok
        matched += due_ok and category_ok
    return {
        "matched": matched,
        "expected": len(expected),
        "predicted": len(predicted),
        "exact": matched == len(expected) and not unmatched,
        "fields": dict(fields),
        "tasks": predicted,
    }


def extraction_summary(scores: list[dict]) -> dict[str, Any]:
    """Micro precision/recall over items, plus the share of cases that were exactly right."""
    matched = sum(s["matched"] for s in scores)
    expected = sum(s["expected"] for s in scores)
    predicted = sum(s["predicted"] for s in scores)
    precision = matched / predicted if predicted else (1.0 if not expected else 0.0)
    recall = matched / expected if expected else 1.0
    return {
        "n": len(scores),
        "exact_match": sum(1 for s in scores if s["exact"]) / len(scores) if scores else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


# --- Retrieval ----------------------------------------------------------------------------------

def retrieval_report(rows: list[dict], k: int) -> dict[str, Any]:
    """rows: {"relevant": [doc ids], "retrieved": [doc ids in rank order]}.

    In-scope questions: hit@1, recall@k (any relevant doc in the top k) and MRR, plus how often a
    real question was wrongly refused (nothing retrieved). Out-of-scope questions should retrieve
    nothing, so the agent says "I don't know" instead of answering from an unrelated article.
    """
    in_scope = [r for r in rows if r["relevant"]]
    out_scope = [r for r in rows if not r["relevant"]]

    def first_hit(r: dict) -> int | None:
        return next((i for i, d in enumerate(r["retrieved"][:k], start=1) if d in r["relevant"]), None)

    ranks = [first_hit(r) for r in in_scope]
    n = len(in_scope) or 1
    return {
        "k": k,
        "in_scope": len(in_scope),
        "out_of_scope": len(out_scope),
        "hit_at_1": sum(1 for x in ranks if x == 1) / n,
        "recall_at_k": sum(1 for x in ranks if x) / n,
        "mrr": sum(1 / x for x in ranks if x) / n,
        "wrongly_refused": sum(1 for r in in_scope if not r["retrieved"]) / n,
        "correctly_refused": (sum(1 for r in out_scope if not r["retrieved"]) / len(out_scope)) if out_scope else None,
    }


# --- Latency ------------------------------------------------------------------------------------

def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (pct in 0-100)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]
