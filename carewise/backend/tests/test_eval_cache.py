"""Resumable eval runs: successful answers are saved and replayed; failures are retried."""
from app.core.tracing import start_trace
from app.services.llm import LLMClient
from evals.cache import CachingLLMClient


def client_with(tmp_path, replies):
    """A Gemini client whose API returns `replies` in order; records how often it was called."""
    base = LLMClient(provider="gemini", api_key="test-key", model="test-model")
    llm = CachingLLMClient(base, path=tmp_path / "cache.jsonl")
    llm.api_calls = 0

    async def fake_gemini(system, messages, max_tokens, temperature, json_mode):
        llm.api_calls += 1
        return replies.pop(0)

    llm._complete_gemini = fake_gemini
    return llm


async def test_answers_are_saved_and_replayed_without_calling_the_api(tmp_path):
    first = client_with(tmp_path, [("routed: emotional", {"input_tokens": 10, "output_tokens": 3}, True)])
    msgs = [{"role": "user", "content": "I'm so tired"}]
    assert await first.complete("route this", msgs, json_mode=True) == "routed: emotional"

    second = client_with(tmp_path, [])  # a later run: the API must not be called
    with start_trace() as trace:
        assert await second.complete("route this", msgs, json_mode=True) == "routed: emotional"
    assert second.api_calls == 0 and second.hits == 1
    assert trace.calls[0].ok and trace.calls[0].input_tokens == 10  # scored like the original call


async def test_failed_calls_are_not_saved_so_the_next_run_retries_them(tmp_path):
    msgs = [{"role": "user", "content": "hello"}]
    first = client_with(tmp_path, [("error text", {}, False)])
    with start_trace() as trace:
        await first.complete("sys", msgs)
    assert not trace.calls[0].ok  # the runner sees the failure and excludes the case

    retry = client_with(tmp_path, [("hi there", {}, True)])
    assert await retry.complete("sys", msgs) == "hi there" and retry.api_calls == 1


async def test_a_different_prompt_is_a_different_answer(tmp_path):
    first = client_with(tmp_path, [("a", {}, True)])
    await first.complete("prompt v1", [{"role": "user", "content": "x"}])
    changed = client_with(tmp_path, [("b", {}, True)])
    assert await changed.complete("prompt v2", [{"role": "user", "content": "x"}]) == "b"
