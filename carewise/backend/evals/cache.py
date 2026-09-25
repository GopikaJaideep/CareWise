"""Resumable eval runs: save every successful model answer, and replay it on the next run.

The Gemini free tier allows a small number of requests per model per day, far fewer than a full
run needs. With --resume, each answer that came back OK is appended to evals/.cache/<model>.jsonl,
keyed by exactly what was sent (model, system prompt, messages, settings). Re-running replays saved
answers without calling the API, so each day's quota goes only to cases not yet answered, and a
run spread over several days scores the same answers a single run would have. Failed calls are
never saved, so they are retried next time.

A replayed answer records its original latency and token counts in the trace, so reported latency
is the model's, not the cache's.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.tracing import record_call
from app.services.llm import LLMClient

CACHE_DIR = Path(__file__).parent / ".cache"


class CachingLLMClient(LLMClient):
    def __init__(self, base: LLMClient, path: Path | None = None) -> None:
        # Share the configured client's provider, key and model rather than resolving them again.
        self.__dict__.update(base.__dict__)
        self.path = path or CACHE_DIR / f"{self.provider}-{self.model.replace('/', '_')}.jsonl"
        self.entries: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.entries[row["key"]] = row
        self.hits = self.misses = 0

    def key(self, *parts: Any) -> str:
        return hashlib.sha256(json.dumps([self.provider, self.model, *parts], sort_keys=True).encode()).hexdigest()

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        stream: bool = False,
    ) -> str:
        settings = get_settings()
        max_tokens = max_tokens or settings.llm_max_tokens
        temperature = temperature if temperature is not None else settings.llm_temperature
        key = self.key(system, messages, max_tokens, temperature, json_mode)
        saved = self.entries.get(key)
        if saved is not None:
            self.hits += 1
            record_call(provider=self.provider, model=self.model, ok=True,
                        latency_ms=saved["latency_ms"], **saved["usage"])
            return saved["text"]

        self.misses += 1
        start = time.perf_counter()
        if self.provider == "gemini":
            text, usage, ok = await self._complete_gemini(system, messages, max_tokens, temperature, json_mode)
        else:
            text, usage, ok = await self._complete_anthropic(system, messages, max_tokens, temperature)
        latency_ms = round((time.perf_counter() - start) * 1000)
        record_call(provider=self.provider, model=self.model, ok=ok, latency_ms=latency_ms, **usage)
        if ok:
            row = {"key": key, "text": text, "usage": usage, "latency_ms": latency_ms}
            self.entries[key] = row
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        return text
