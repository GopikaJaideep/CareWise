"""LLM client wrapper: Gemini (free tier) or Anthropic, with a demo-mode fallback."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, TypeVar

from pydantic import BaseModel, ValidationError

import httpx
from anthropic import AsyncAnthropic, APIError

from app.core.config import get_settings
from app.core.streaming import ReplySink, current_sink
from app.core.tracing import record_call

logger = logging.getLogger(__name__)
settings = get_settings()

T = TypeVar("T", bound=BaseModel)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_STREAM_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
ERROR_MESSAGE = "I'm having trouble responding right now. Could you try again in a moment?"
RETRYABLE_STATUS = {429, 500, 503}
GEMINI_MAX_ATTEMPTS = 3


def resolve_provider(requested: str, gemini_key: str, anthropic_key: str) -> str | None:
    """Pick the provider. "auto" prefers Gemini (free tier), then Anthropic."""
    requested = (requested or "auto").lower()
    if requested == "gemini":
        return "gemini" if gemini_key else None
    if requested == "anthropic":
        return "anthropic" if anthropic_key else None
    if gemini_key:
        return "gemini"
    if anthropic_key:
        return "anthropic"
    return None


def build_gemini_payload(
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    json_mode: bool,
    model: str,
) -> dict[str, Any]:
    contents: list[dict[str, Any]] = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        # Gemini expects alternating roles, so merge adjacent same-role turns.
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n\n" + m["content"]
        else:
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

    generation_config: dict[str, Any] = {"maxOutputTokens": max_tokens, "temperature": temperature}
    if json_mode:
        generation_config["responseMimeType"] = "application/json"
    if "flash" in model:
        # Thinking tokens count against maxOutputTokens and can starve the actual reply: with
        # gemini-3.6-flash a short answer used ~500 of 1024 tokens on thinking, and longer answers
        # were cut off mid-sentence. These prompts don't need extended reasoning. (Every Flash
        # model, not just 2.5: that narrower check is how 3.x replies got truncated.)
        generation_config["thinkingConfig"] = {"thinkingBudget": 0}

    return {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": generation_config,
    }


def parse_gemini_text(data: dict[str, Any]) -> str | None:
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return None
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    return text or None


class LLMClient:
    """Thin wrapper over Gemini or Anthropic with CareWise defaults."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        if provider and api_key:
            self.provider: str | None = provider
            self.api_key = api_key
        else:
            self.provider = resolve_provider(
                settings.llm_provider, settings.gemini_api_key, settings.anthropic_api_key
            )
            self.api_key = (
                settings.gemini_api_key if self.provider == "gemini" else settings.anthropic_api_key
            )

        if self.provider == "gemini":
            self.model = model or settings.gemini_model
        else:
            self.model = model or settings.llm_model
        self.client = AsyncAnthropic(api_key=self.api_key) if self.provider == "anthropic" else None

        if self.provider is None:
            logger.warning("No LLM API key configured — running in demo mode.")
        else:
            logger.info("LLM provider: %s (model=%s)", self.provider, self.model)

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        stream: bool = False,
    ) -> str:
        """Plain text completion.

        stream=True marks text a person will read. If the current request is streaming (a ReplySink
        is open, see app/core/streaming.py), chunks are passed to it as they arrive; the full text is
        still returned, so callers don't change. Never used for JSON (routing, extraction).
        """
        sink = current_sink() if stream and not json_mode else None
        if self.provider is None:
            text = self._fallback_response(messages)
            if sink is not None:
                sink.start()
                sink.feed(text)
                sink.end()
            return text

        max_tokens = max_tokens or settings.llm_max_tokens
        temperature = temperature if temperature is not None else settings.llm_temperature

        start = time.perf_counter()
        if sink is not None:
            text, usage, ok = await self._complete_streamed(sink, system, messages, max_tokens, temperature)
        elif self.provider == "gemini":
            text, usage, ok = await self._complete_gemini(system, messages, max_tokens, temperature, json_mode)
        else:
            text, usage, ok = await self._complete_anthropic(system, messages, max_tokens, temperature)
        # Recorded against the current chat turn's trace, if any (see app/core/tracing.py).
        record_call(
            provider=self.provider, model=self.model, ok=ok,
            latency_ms=round((time.perf_counter() - start) * 1000), **usage,
        )
        return text

    async def _complete_anthropic(
        self, system: str, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> tuple[str, dict[str, Any], bool]:
        assert self.client is not None
        try:
            response = await self.client.messages.create(
                model=self.model,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
            return response.content[0].text, usage, True
        except APIError as e:
            logger.error("Anthropic API error: %s", e)
            return ERROR_MESSAGE, {}, False

    async def _complete_gemini(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        json_mode: bool,
    ) -> tuple[str, dict[str, Any], bool]:
        payload = build_gemini_payload(system, messages, max_tokens, temperature, json_mode, self.model)
        try:
            data = await self._gemini_request(payload)
        except httpx.HTTPStatusError as e:
            logger.error("Gemini API error %s: %s", e.response.status_code, e.response.text[:300])
            return ERROR_MESSAGE, {}, False
        except httpx.HTTPError as e:
            logger.error("Gemini request failed: %s", e)
            return ERROR_MESSAGE, {}, False

        meta = data.get("usageMetadata") or {}
        usage = {
            "input_tokens": meta.get("promptTokenCount"),
            "output_tokens": meta.get("candidatesTokenCount"),
            "thinking_tokens": meta.get("thoughtsTokenCount"),
        }
        text = parse_gemini_text(data)
        if text is None:
            finish = (data.get("candidates") or [{}])[0].get("finishReason")
            logger.warning(
                "Gemini returned no text (finishReason=%s, promptFeedback=%s)",
                finish, data.get("promptFeedback"),
            )
            return ERROR_MESSAGE, usage, False
        finish = (data.get("candidates") or [{}])[0].get("finishReason")
        if finish == "MAX_TOKENS":
            # Still return the partial reply, but make truncation visible in the logs.
            logger.warning("Gemini reply hit maxOutputTokens and was cut off (usage=%s)", data.get("usageMetadata"))
        return text, usage, True

    async def _complete_streamed(
        self, sink: ReplySink, system: str, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> tuple[str, dict[str, Any], bool]:
        """Stream into the sink. If streaming fails before any text arrives (unsupported, rate
        limited, network), fall back to a normal request, so a streaming problem costs speed,
        never the reply."""
        sink.start()
        parts: list[str] = []
        usage: dict[str, Any] = {}
        chunks = (
            self._stream_gemini(system, messages, max_tokens, temperature)
            if self.provider == "gemini"
            else self._stream_anthropic(system, messages, max_tokens, temperature)
        )
        try:
            async for text, chunk_usage in chunks:
                if text:
                    parts.append(text)
                    sink.feed(text)
                if chunk_usage:
                    usage = chunk_usage
        except Exception as e:  # noqa: BLE001 - any failure here has the same safe outcome
            if not parts:
                logger.warning("Streaming unavailable (%s); using a normal request", type(e).__name__)
                if self.provider == "gemini":
                    text, usage, ok = await self._complete_gemini(system, messages, max_tokens, temperature, False)
                else:
                    text, usage, ok = await self._complete_anthropic(system, messages, max_tokens, temperature)
                if ok:
                    sink.feed(text)
                sink.end()
                return text, usage, ok
            logger.error("Stream broke off after partial text: %s", e)
            sink.end()
            return ERROR_MESSAGE, usage, False
        sink.end()
        text = "".join(parts)
        return (text, usage, True) if text else (ERROR_MESSAGE, usage, False)

    async def _stream_gemini(
        self, system: str, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> AsyncIterator[tuple[str, dict[str, Any] | None]]:
        payload = build_gemini_payload(system, messages, max_tokens, temperature, False, self.model)
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", GEMINI_STREAM_URL.format(model=self.model), json=payload,
                headers={"x-goog-api-key": self.api_key},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = json.loads(line[5:].strip())
                    meta = data.get("usageMetadata")
                    usage = {
                        "input_tokens": meta.get("promptTokenCount"),
                        "output_tokens": meta.get("candidatesTokenCount"),
                        "thinking_tokens": meta.get("thoughtsTokenCount"),
                    } if meta else None
                    yield parse_gemini_text(data) or "", usage

    async def _stream_anthropic(
        self, system: str, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> AsyncIterator[tuple[str, dict[str, Any] | None]]:
        assert self.client is not None
        async with self.client.messages.stream(
            model=self.model, system=system, messages=messages, max_tokens=max_tokens, temperature=temperature,
        ) as stream:
            async for text in stream.text_stream:
                yield text, None
            final = await stream.get_final_message()
            yield "", {"input_tokens": final.usage.input_tokens, "output_tokens": final.usage.output_tokens}

    async def _gemini_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = GEMINI_URL.format(model=self.model)
        # Key goes in a header, not the query string, so it can't leak via logged URLs.
        headers = {"x-goog-api-key": self.api_key}
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(1, GEMINI_MAX_ATTEMPTS + 1):
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code in RETRYABLE_STATUS and attempt < GEMINI_MAX_ATTEMPTS:
                    await asyncio.sleep(1.5 * attempt)
                    continue
                response.raise_for_status()
                return response.json()
        raise RuntimeError("unreachable")

    async def complete_json(
        self,
        system: str,
        messages: list[dict[str, str]],
        schema_hint: str,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Force JSON output using a schema instruction (plus native JSON mode on Gemini)."""
        full_system = (
            f"{system}\n\n"
            f"You MUST respond with valid JSON matching this schema: {schema_hint}\n"
            "Do NOT include markdown fences, prose, or any text outside the JSON object."
        )
        text = await self.complete(
            full_system, messages, max_tokens=max_tokens, temperature=0.2, json_mode=True
        )
        return parse_json_object(text)

    async def complete_structured(
        self,
        system: str,
        messages: list[dict[str, str]],
        output: type[T],
        max_tokens: int | None = None,
    ) -> T | None:
        """JSON output validated against a Pydantic model (app/agents/outputs.py).

        If the reply doesn't validate, the validation errors are sent back once for a corrected
        reply. Returns None if it still doesn't validate, or if the call itself failed (quota,
        outage): then there is nothing to repair, so no second call is made.
        """
        if self.provider is None:
            return None
        schema_hint = json.dumps(output.model_json_schema(), separators=(",", ":"))
        full_system = (
            f"{system}\n\n"
            f"You MUST respond with valid JSON matching this JSON Schema: {schema_hint}\n"
            "Do NOT include markdown fences, prose, or any text outside the JSON object."
        )
        text = await self.complete(full_system, messages, max_tokens=max_tokens, temperature=0.2, json_mode=True)
        if text == ERROR_MESSAGE:
            return None
        result = _validate(output, text)
        if not isinstance(result, str):
            return result
        logger.info("Structured output failed validation (%s); asking for a correction", result[:200])
        repair = [
            *messages,
            {"role": "assistant", "content": text},
            {"role": "user", "content": f"That JSON didn't match the schema: {result}\nReply with corrected JSON only."},
        ]
        retry_text = await self.complete(full_system, repair, max_tokens=max_tokens, temperature=0.0, json_mode=True)
        if retry_text == ERROR_MESSAGE:
            return None
        fixed = _validate(output, retry_text)
        if isinstance(fixed, str):
            logger.warning("Structured output still invalid after one repair: %s", fixed[:200])
            return None
        return fixed

    def _fallback_response(self, messages: list[dict[str, str]]) -> str:
        """Used when no API key is configured (demo mode)."""
        last = messages[-1]["content"] if messages else ""
        return (
            "[Demo mode — no LLM key configured]\n\n"
            f"You said: \"{last[:120]}{'...' if len(last) > 120 else ''}\"\n\n"
            "In production, this would route through the appropriate specialist agent "
            "(emotional support, symptom tracking, care coordination, resources, or burnout). "
            "Set GEMINI_API_KEY (free) or ANTHROPIC_API_KEY to enable real responses."
        )


def parse_json_object(text: str) -> dict[str, Any]:
    """The model's reply as a JSON object, or {} if it isn't one."""
    text = text.strip()
    # Strip accidental fences
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse JSON response: %s\nRaw: %s", e, text[:200])
        return {}
    # Models sometimes wrap the one requested object in a list: [{...}].
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        logger.warning(
            "Expected a JSON object, got %s; discarding. Raw: %s", type(parsed).__name__, text[:200]
        )
        return {}
    return parsed


def _validate(output: type[T], text: str) -> T | str:
    """The validated model, or a short description of what's wrong (for the repair prompt)."""
    data = parse_json_object(text)
    if not data:
        return "the reply was not a JSON object"
    try:
        return output.model_validate(data)
    except ValidationError as e:
        return "; ".join(f"{'.'.join(map(str, err['loc'])) or 'root'}: {err['msg']}" for err in e.errors()[:5])


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
