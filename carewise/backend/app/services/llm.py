"""LLM client wrapper: Gemini (free tier) or Anthropic, with a demo-mode fallback."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
from anthropic import AsyncAnthropic, APIError

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
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
    if "2.5-flash" in model:
        # Thinking tokens count against maxOutputTokens and can starve the
        # actual reply; these prompts don't need extended reasoning.
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
    ) -> str:
        """Plain text completion."""
        if self.provider is None:
            return self._fallback_response(messages)

        max_tokens = max_tokens or settings.llm_max_tokens
        temperature = temperature if temperature is not None else settings.llm_temperature

        if self.provider == "gemini":
            return await self._complete_gemini(system, messages, max_tokens, temperature, json_mode)
        return await self._complete_anthropic(system, messages, max_tokens, temperature)

    async def _complete_anthropic(
        self, system: str, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> str:
        assert self.client is not None
        try:
            response = await self.client.messages.create(
                model=self.model,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.content[0].text
        except APIError as e:
            logger.error("Anthropic API error: %s", e)
            return ERROR_MESSAGE

    async def _complete_gemini(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        json_mode: bool,
    ) -> str:
        payload = build_gemini_payload(system, messages, max_tokens, temperature, json_mode, self.model)
        try:
            data = await self._gemini_request(payload)
        except httpx.HTTPStatusError as e:
            logger.error("Gemini API error %s: %s", e.response.status_code, e.response.text[:300])
            return ERROR_MESSAGE
        except httpx.HTTPError as e:
            logger.error("Gemini request failed: %s", e)
            return ERROR_MESSAGE

        text = parse_gemini_text(data)
        if text is None:
            finish = (data.get("candidates") or [{}])[0].get("finishReason")
            logger.warning(
                "Gemini returned no text (finishReason=%s, promptFeedback=%s)",
                finish, data.get("promptFeedback"),
            )
            return ERROR_MESSAGE
        return text

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


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
