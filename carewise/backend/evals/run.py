"""CareWise eval runner.

    python -m evals.run                       # every suite the current setup can run
    python -m evals.run --suite routing,tasks --limit 10
    python -m evals.run --delay 4             # space out calls for the Gemini free tier

Suites that need a model (routing, symptoms, tasks) run when GEMINI_API_KEY or
ANTHROPIC_API_KEY is set; without one they are skipped, not faked. The crisis suite scores
the deterministic keyword detector and always runs. Reports go to evals/results/.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.agents.base import AgentName, SessionContext
from app.agents.care_coordinator import CareCoordinatorAgent
from app.agents.orchestrator import Orchestrator
from app.agents.symptom_tracker import SymptomTrackerAgent
from app.core.config import get_settings
from app.core.safety import detect_crisis
from app.services.llm import LLMClient, get_llm_client
from app.services.retrieval import GeminiEmbedder, Retriever, load_corpus
from evals.metrics import (
    binary_report, classification_report, extraction_summary, percentile, retrieval_report,
    score_medications, score_symptoms, score_tasks,
)

HERE = Path(__file__).parent
DATASETS = HERE / "datasets"
RESULTS = HERE / "results"
SUITES = ["crisis", "retrieval", "routing", "symptoms", "tasks"]
NEEDS_MODEL = {"routing", "symptoms", "tasks"}

# Every task case is written relative to this moment, so "Tuesday at 10" has one right answer.
EVAL_TZ = ZoneInfo("Australia/Sydney")
EVAL_NOW = datetime(2026, 9, 23, 9, 0, tzinfo=EVAL_TZ)  # a Wednesday morning

ROUTING_LABELS = [a.value for a in AgentName if a != AgentName.SAFETY]


def load(name: str, limit: int | None) -> list[dict]:
    rows = [json.loads(line) for line in (DATASETS / f"{name}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[:limit] if limit else rows


class Timer:
    def __init__(self) -> None:
        self.samples: list[float] = []

    async def run(self, coro):
        start = time.perf_counter()
        try:
            return await coro
        finally:
            self.samples.append(time.perf_counter() - start)

    def summary(self) -> dict[str, float]:
        return {"p50_s": round(percentile(self.samples, 50), 3), "p95_s": round(percentile(self.samples, 95), 3)}


async def run_crisis(cases: list[dict], _llm, _delay) -> dict[str, Any]:
    rows = []
    for case in cases:
        check = detect_crisis(case["message"])
        rows.append({**case, "predicted": check.requires_intervention, "triggers": check.triggers})
    report = binary_report((r["crisis"], r["predicted"]) for r in rows)
    report["layer"] = "keyword detector (deterministic)"
    report["misses"] = [r for r in rows if r["crisis"] and not r["predicted"]]
    report["false_alarms"] = [r for r in rows if not r["crisis"] and r["predicted"]]
    return {"report": report, "cases": rows}


async def run_routing(cases: list[dict], llm, delay: float) -> dict[str, Any]:
    orch = Orchestrator.__new__(Orchestrator)  # routing only; no agents or database needed
    orch.llm = llm
    timer = Timer()
    rows = []
    for case in cases:
        ctx = SessionContext(
            user_id=0, conversation_id=0, user_message=case["message"],
            history=case.get("history", []), metadata={"last_agent": case.get("last_agent")},
        )
        predicted = (await timer.run(orch._classify_intent(ctx))).value
        rows.append({**case, "predicted": predicted, "correct": predicted == case["expected"]})
        await asyncio.sleep(delay)
    report = classification_report(((r["expected"], r["predicted"]) for r in rows), ROUTING_LABELS)
    report["latency"] = timer.summary()
    by_tag: dict[str, list[bool]] = {}
    for r in rows:
        for tag in r.get("tags", []):
            by_tag.setdefault(tag, []).append(r["correct"])
    report["accuracy_by_tag"] = {t: round(sum(v) / len(v), 3) for t, v in sorted(by_tag.items()) if len(v) >= 3}
    report["failures"] = [r for r in rows if not r["correct"]]
    return {"report": report, "cases": rows}


async def run_symptoms(cases: list[dict], llm, delay: float) -> dict[str, Any]:
    agent = SymptomTrackerAgent(db=None)
    agent.llm = llm
    timer = Timer()
    rows, sym_scores, med_scores = [], [], []
    for case in cases:
        extracted = await timer.run(agent.extract(case["message"]))
        s = score_symptoms(case["expected"], extracted)
        row = {**case, "extracted": extracted, "symptom_score": s, "correct": s["exact"]}
        sym_scores.append(s)
        if "medications" in case:
            m = score_medications(case["medications"], extracted)
            med_scores.append(m)
            row["medication_score"] = m
            row["correct"] = row["correct"] and m["exact"]
        if "query" in case:
            row["query_ok"] = extracted.get("query") == case["query"]
            row["correct"] = row["correct"] and row["query_ok"]
        rows.append(row)
        await asyncio.sleep(delay)
    report = {
        "case_accuracy": sum(r["correct"] for r in rows) / len(rows) if rows else 0.0,
        "symptoms": extraction_summary(sym_scores),
        "medications": extraction_summary(med_scores) if med_scores else None,
        "no_number_cases_logged_nothing": _share(
            [r["symptom_score"]["predicted"] == 0 for r in rows if not r["expected"] and "query" not in r and "medications" not in r]
        ),
        "latency": timer.summary(),
        "failures": [r for r in rows if not r["correct"]],
    }
    return {"report": report, "cases": rows}


async def run_tasks(cases: list[dict], llm, delay: float) -> dict[str, Any]:
    agent = CareCoordinatorAgent(db=None)
    agent.llm = llm
    timer = Timer()
    rows, scores = [], []
    for case in cases:
        extracted = await timer.run(agent.extract(case["message"], EVAL_TZ, now_utc=EVAL_NOW))
        s = score_tasks(case["expected"], extracted, EVAL_TZ)
        correct = s["exact"]
        if "query" in case:
            correct = correct and extracted.get("query") in case["query"]
        if "mark_done" in case:
            done = [str(x).lower() for x in extracted.get("mark_done") or []]
            correct = correct and all(any(k in d for d in done) for k in case["mark_done"])
        scores.append(s)
        rows.append({**case, "extracted": extracted, "score": s, "correct": correct})
        await asyncio.sleep(delay)
    fields = {f: sum(r["score"]["fields"].get(f, 0) for r in rows) for f in ("title", "due", "category")}
    expected_total = sum(len(r["expected"]) for r in rows) or 1
    report = {
        "case_accuracy": sum(r["correct"] for r in rows) / len(rows) if rows else 0.0,
        "tasks": extraction_summary(scores),
        "field_accuracy": {f: round(v / expected_total, 3) for f, v in fields.items()},
        "fixed_now": EVAL_NOW.isoformat(),
        "latency": timer.summary(),
        "failures": [r for r in rows if not r["correct"]],
    }
    return {"report": report, "cases": rows}


def _share(flags: list[bool]) -> float | None:
    return round(sum(flags) / len(flags), 3) if flags else None


async def run_retrieval(cases: list[dict], _llm, delay: float) -> dict[str, Any]:
    """Keyword-only always; hybrid (keyword + Gemini embeddings) too when GEMINI_API_KEY is set,
    so the report shows what semantic search adds rather than assuming it."""
    settings = get_settings()
    chunks = load_corpus()
    modes = {"keyword": Retriever(chunks)}
    if settings.gemini_api_key:
        modes["hybrid"] = Retriever(chunks, embedder=GeminiEmbedder(settings.gemini_api_key, settings.embedding_model))
    reports, all_rows = {}, {}
    for mode, retriever in modes.items():
        await retriever.prepare()  # what the app's startup warm-up does
        if mode != "keyword" and retriever.mode != "hybrid":
            reports[mode] = {"error": "embeddings unavailable (see warnings above)"}
            continue
        timer = Timer()
        rows = []
        for case in cases:
            hits = await timer.run(retriever.search(case["query"]))
            docs = list(dict.fromkeys(h.chunk.doc_id for h in hits))
            rows.append({**case, "retrieved": docs})
            if mode != "keyword":
                await asyncio.sleep(delay)
        report = retrieval_report(rows, k=4)
        report["latency"] = timer.summary()
        report["misses"] = [r for r in rows if r["relevant"] and not set(r["retrieved"][:4]) & set(r["relevant"])]
        report["not_refused"] = [r for r in rows if not r["relevant"] and r["retrieved"]]
        reports[mode], all_rows[mode] = report, rows
    return {"report": reports, "cases": all_rows}


RUNNERS = {"crisis": run_crisis, "retrieval": run_retrieval, "routing": run_routing, "symptoms": run_symptoms, "tasks": run_tasks}


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def render_markdown(meta: dict, results: dict[str, dict]) -> str:
    lines = [f"# CareWise eval report", "", f"- Run: {meta['run_at']}", f"- Model: {meta['model']}", ""]
    if "crisis" in results:
        r = results["crisis"]["report"]
        lines += [
            "## Crisis detection", f"Layer: {r['layer']}. {r['n']} cases.", "",
            "| Recall (crises caught) | False-positive rate | Precision |", "|---|---|---|",
            f"| {pct(r['recall'])} ({r['tp']}/{r['tp'] + r['fn']}) | {pct(r['false_positive_rate'])} ({r['fp']}/{r['fp'] + r['tn']}) | {pct(r['precision'])} |", "",
        ]
        if r["misses"]:
            lines += ["Missed crises:", *[f"- `{m['id']}` {m['message']}" for m in r["misses"]], ""]
        if r["false_alarms"]:
            lines += ["False alarms:", *[f"- `{m['id']}` {m['message']} (matched: {', '.join(m['triggers'])})" for m in r["false_alarms"]], ""]
    if "retrieval" in results:
        lines += ["## Retrieval (resource guide)", "", "| Search | Hit@1 | Recall@4 | MRR | Real questions refused | Off-topic refused | p50 |",
                  "|---|---|---|---|---|---|---|"]
        for mode, r in results["retrieval"]["report"].items():
            if "error" in r:
                lines.append(f"| {mode} | {r['error']} | | | | | |")
                continue
            lines.append(f"| {mode} | {pct(r['hit_at_1'])} | {pct(r['recall_at_k'])} | {r['mrr']:.3f} | {pct(r['wrongly_refused'])} | {pct(r['correctly_refused'])} | {r['latency']['p50_s']}s |")
        lines.append("")
        for mode, r in results["retrieval"]["report"].items():
            if r.get("misses"):
                lines += [f"{mode}: right article not in top 4:", *[f"- `{m['id']}` {m['query']} → {', '.join(m['retrieved']) or 'nothing'}" for m in r["misses"]], ""]
            if r.get("not_refused"):
                lines += [f"{mode}: off-topic but answered:", *[f"- `{m['id']}` {m['query']} → {', '.join(m['retrieved'])}" for m in r["not_refused"]], ""]
    if "routing" in results:
        r = results["routing"]["report"]
        lines += ["## Routing", f"{r['n']} cases. Accuracy **{pct(r['accuracy'])}**, macro-F1 {r['macro_f1']:.3f}, latency p50 {r['latency']['p50_s']}s / p95 {r['latency']['p95_s']}s.", "",
                  "| Agent | Precision | Recall | F1 | Cases |", "|---|---|---|---|---|"]
        lines += [f"| {k} | {pct(v['precision'])} | {pct(v['recall'])} | {v['f1']:.2f} | {v['support']} |" for k, v in r["per_label"].items()]
        lines += ["", "Accuracy by tag: " + ", ".join(f"{k} {pct(v)}" for k, v in r["accuracy_by_tag"].items()), ""]
        if r["failures"]:
            lines += ["Misrouted:", *[f"- `{f['id']}` expected **{f['expected']}**, got {f['predicted']}: {f['message']}" for f in r["failures"]], ""]
    if "symptoms" in results:
        r = results["symptoms"]["report"]
        s = r["symptoms"]
        lines += ["## Symptom & medication extraction", f"Cases fully correct: **{pct(r['case_accuracy'])}**. Symptoms: precision {pct(s['precision'])}, recall {pct(s['recall'])}. "
                  f"No-number messages that correctly logged nothing: {pct(r['no_number_cases_logged_nothing'])}. Latency p50 {r['latency']['p50_s']}s.", ""]
        if r["failures"]:
            lines += ["Incorrect:", *[f"- `{f['id']}` {f['message']} → logged {f['symptom_score']['logged']}" for f in r["failures"]], ""]
    if "tasks" in results:
        r = results["tasks"]["report"]
        lines += ["## Task extraction", f"Relative to {r['fixed_now']}. Cases fully correct: **{pct(r['case_accuracy'])}**. "
                  f"Field accuracy: title {pct(r['field_accuracy']['title'])}, due date/time {pct(r['field_accuracy']['due'])}, category {pct(r['field_accuracy']['category'])}. "
                  f"Latency p50 {r['latency']['p50_s']}s.", ""]
        if r["failures"]:
            lines += ["Incorrect:", *[f"- `{f['id']}` {f['message']} → {f['score']['tasks'] or f['extracted']}" for f in r["failures"]], ""]
    for name in meta["skipped"]:
        lines += [f"## {name.capitalize()}", "Skipped: needs a model (set GEMINI_API_KEY or ANTHROPIC_API_KEY).", ""]
    return "\n".join(lines)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", default="all", help="comma-separated: " + ",".join(SUITES))
    parser.add_argument("--limit", type=int, default=None, help="only the first N cases of each suite")
    parser.add_argument("--delay", type=float, default=0.0, help="seconds between model calls (rate limits)")
    parser.add_argument("--provider", choices=["gemini", "anthropic"], help="override the configured provider")
    parser.add_argument("--model", help="override the model name")
    parser.add_argument("--no-write", action="store_true", help="print only; don't write report files")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    # Windows consoles default to cp1252, which can't print the report's arrows and quotes.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    wanted = SUITES if args.suite == "all" else [s.strip() for s in args.suite.split(",")]
    unknown = set(wanted) - set(SUITES)
    if unknown:
        parser.error(f"unknown suite(s): {', '.join(sorted(unknown))}")

    llm = get_llm_client()
    if args.provider or args.model:
        settings = get_settings()
        provider = args.provider or llm.provider
        key = settings.gemini_api_key if provider == "gemini" else settings.anthropic_api_key
        if not key:
            parser.error(f"no API key configured for {provider}")
        llm = LLMClient(provider=provider, api_key=key, model=args.model)
    has_model = llm.provider is not None
    run_now = [s for s in wanted if has_model or s not in NEEDS_MODEL]
    skipped = [s for s in wanted if s not in run_now]

    meta = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": f"{llm.provider}/{llm.model}" if has_model else "none (offline)", "skipped": skipped}
    results = {}
    for suite in run_now:
        print(f"running {suite}...", file=sys.stderr)
        results[suite] = await RUNNERS[suite](load(suite, args.limit), llm, args.delay)

    markdown = render_markdown(meta, results)
    print(markdown)
    if not args.no_write:
        RESULTS.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        tag = llm.model.replace("/", "_") if has_model else "offline"
        (RESULTS / f"{stamp}-{tag}.md").write_text(markdown, encoding="utf-8")
        (RESULTS / f"{stamp}-{tag}.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2, default=str), encoding="utf-8")
        print(f"\nwrote {RESULTS / (stamp + '-' + tag)}.md/.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
