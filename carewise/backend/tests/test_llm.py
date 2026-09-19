"""Tests for the LLM client: provider selection, Gemini payloads/parsing, retries, fallbacks."""
import httpx
import pytest

from app.services import llm
from app.services.llm import (
    ERROR_MESSAGE,
    LLMClient,
    build_gemini_payload,
    parse_gemini_text,
    resolve_provider,
)


def gemini_reply(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}


def use_transport(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(
        llm.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )

    async def no_sleep(_):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)


class TestResolveProvider:
    def test_auto_prefers_gemini(self):
        assert resolve_provider("auto", "g", "a") == "gemini"

    def test_auto_falls_back_to_anthropic(self):
        assert resolve_provider("auto", "", "a") == "anthropic"

    def test_auto_with_no_keys_is_demo(self):
        assert resolve_provider("auto", "", "") is None

    def test_forced_provider_without_its_key_is_demo(self):
        assert resolve_provider("gemini", "", "a") is None
        assert resolve_provider("anthropic", "g", "") is None


class TestGeminiPayload:
    def test_maps_roles_and_system_prompt(self):
        payload = build_gemini_payload(
            "be kind",
            [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
            256, 0.5, False, "gemini-2.5-flash",
        )
        assert payload["systemInstruction"]["parts"][0]["text"] == "be kind"
        assert [c["role"] for c in payload["contents"]] == ["user", "model"]

    def test_merges_adjacent_same_role_turns(self):
        payload = build_gemini_payload(
            "s",
            [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}],
            256, 0.5, False, "gemini-2.5-flash",
        )
        assert len(payload["contents"]) == 1
        assert payload["contents"][0]["parts"][0]["text"] == "a\n\nb"

    def test_json_mode_sets_mime_type(self):
        payload = build_gemini_payload("s", [{"role": "user", "content": "x"}], 256, 0.2, True, "gemini-2.5-flash")
        assert payload["generationConfig"]["responseMimeType"] == "application/json"

    def test_thinking_disabled_only_for_25_flash(self):
        flash = build_gemini_payload("s", [{"role": "user", "content": "x"}], 256, 0.2, False, "gemini-2.5-flash")
        other = build_gemini_payload("s", [{"role": "user", "content": "x"}], 256, 0.2, False, "gemini-pro-latest")
        assert flash["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
        assert "thinkingConfig" not in other["generationConfig"]


class TestParseGeminiText:
    def test_extracts_text(self):
        assert parse_gemini_text(gemini_reply("hello")) == "hello"

    def test_blocked_response_has_no_text(self):
        assert parse_gemini_text({"promptFeedback": {"blockReason": "SAFETY"}}) is None

    def test_empty_parts_has_no_text(self):
        assert parse_gemini_text({"candidates": [{"content": {"parts": []}}]}) is None


class TestGeminiClient:
    async def test_complete_returns_text_and_keeps_key_out_of_url(self, monkeypatch):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["key_header"] = request.headers.get("x-goog-api-key")
            return httpx.Response(200, json=gemini_reply("warm reply"))

        use_transport(monkeypatch, handler)
        client = LLMClient(provider="gemini", api_key="secret-key", model="gemini-2.5-flash")
        out = await client.complete("sys", [{"role": "user", "content": "hi"}])

        assert out == "warm reply"
        assert seen["key_header"] == "secret-key"
        assert "secret-key" not in seen["url"]

    async def test_complete_json_parses_object(self, monkeypatch):
        use_transport(monkeypatch, lambda r: httpx.Response(200, json=gemini_reply('{"agent": "symptom_tracker"}')))
        client = LLMClient(provider="gemini", api_key="k")
        out = await client.complete_json("sys", [{"role": "user", "content": "x"}], "{}")
        assert out == {"agent": "symptom_tracker"}

    async def test_complete_json_bad_output_returns_empty_dict(self, monkeypatch):
        use_transport(monkeypatch, lambda r: httpx.Response(200, json=gemini_reply("not json")))
        client = LLMClient(provider="gemini", api_key="k")
        assert await client.complete_json("sys", [{"role": "user", "content": "x"}], "{}") == {}

    async def test_retries_rate_limit_then_succeeds(self, monkeypatch):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(429, json={"error": {"message": "rate limited"}})
            return httpx.Response(200, json=gemini_reply("ok"))

        use_transport(monkeypatch, handler)
        client = LLMClient(provider="gemini", api_key="k")
        assert await client.complete("sys", [{"role": "user", "content": "x"}]) == "ok"
        assert len(calls) == 2

    async def test_persistent_error_returns_friendly_message(self, monkeypatch):
        use_transport(monkeypatch, lambda r: httpx.Response(400, json={"error": {"message": "bad key"}}))
        client = LLMClient(provider="gemini", api_key="k")
        assert await client.complete("sys", [{"role": "user", "content": "x"}]) == ERROR_MESSAGE

    async def test_blocked_response_returns_friendly_message(self, monkeypatch):
        use_transport(monkeypatch, lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
        client = LLMClient(provider="gemini", api_key="k")
        assert await client.complete("sys", [{"role": "user", "content": "x"}]) == ERROR_MESSAGE


class TestDemoMode:
    async def test_no_keys_means_demo_response(self, monkeypatch):
        monkeypatch.setattr(llm.settings, "gemini_api_key", "")
        monkeypatch.setattr(llm.settings, "anthropic_api_key", "")
        monkeypatch.setattr(llm.settings, "llm_provider", "auto")
        client = LLMClient()
        assert client.provider is None
        out = await client.complete("sys", [{"role": "user", "content": "hello there"}])
        assert "Demo mode" in out and "hello there" in out
