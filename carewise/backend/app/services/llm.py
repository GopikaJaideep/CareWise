"""Anthropic LLM client wrapper with retry logic and structured output helpers."""
from __future__ import annotations

import json
import logging
from typing import Any

from anthropic import AsyncAnthropic, APIError, APIStatusError

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMClient:
    """Thin wrapper around the Anthropic SDK with CareWise defaults."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key or settings.anthropic_api_key
        if not key:
            logger.warning("No Anthropic API key configured — LLM calls will fail.")
        self.client = AsyncAnthropic(api_key=key) if key else None
        self.model = model or settings.llm_model

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Plain text completion."""
        if self.client is None:
            return self._fallback_response(messages)

        try:
            response = await self.client.messages.create(
                model=self.model,
                system=system,
                messages=messages,
                max_tokens=max_tokens or settings.llm_max_tokens,
                temperature=temperature if temperature is not None else settings.llm_temperature,
            )
            return response.content[0].text
        except APIStatusError as e:
            logger.error("LLM API error: %s", e)
            return "I'm having trouble responding right now. Could you try again in a moment?"
        except APIError as e:
            logger.error("LLM API error: %s", e)
            return "I'm having trouble responding right now. Could you try again in a moment?"

    async def complete_json(
        self,
        system: str,
        messages: list[dict[str, str]],
        schema_hint: str,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Force JSON output using prefill + schema instruction."""
        full_system = (
            f"{system}\n\n"
            f"You MUST respond with valid JSON matching this schema: {schema_hint}\n"
            "Do NOT include markdown fences, prose, or any text outside the JSON object."
        )
        text = await self.complete(full_system, messages, max_tokens=max_tokens, temperature=0.2)
        text = text.strip()
        # Strip accidental fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse JSON response: %s\nRaw: %s", e, text[:200])
            return {}

    def _fallback_response(self, messages: list[dict[str, str]]) -> str:
        """Used when no API key is configured (demo mode)."""
        last = messages[-1]["content"] if messages else ""
        return (
            "[Demo mode — no LLM key configured]\n\n"
            f"You said: \"{last[:120]}{'...' if len(last) > 120 else ''}\"\n\n"
            "In production, this would route through the appropriate specialist agent "
            "(emotional support, symptom tracking, care coordination, resources, or burnout). "
            "Set ANTHROPIC_API_KEY in .env to enable real responses."
        )


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
