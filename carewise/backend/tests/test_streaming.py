"""Streaming replies: sentence-by-sentence previews that never skip the output safety filter."""
import json

import httpx
from fastapi import FastAPI

from app.core.streaming import ReplySink, open_sink
from app.services import llm

# Captured before any test patches httpx.AsyncClient to mock the Gemini API (llm.httpx is the same
# module), so the test's own client to the app isn't routed to the mock.
REAL_ASYNC_CLIENT = httpx.AsyncClient


def drain(sink: ReplySink) -> list[tuple[str, str]]:
    items = []
    while not sink.queue.empty():
        items.append(sink.queue.get_nowait())
    return items


# --- The sink ------------------------------------------------------------------------------------

def test_text_is_released_a_sentence_at_a_time():
    sink = ReplySink()
    sink.start()
    sink.feed("That sounds really hard. How are")
    assert drain(sink) == [("delta", "That sounds really hard. ")]
    sink.feed(" you holding up")
    assert drain(sink) == []  # no sentence end yet
    sink.end()
    assert drain(sink) == [("delta", "How are you holding up")]


def test_a_sentence_that_fails_the_safety_filter_is_never_shown():
    sink = ReplySink()
    sink.start()
    sink.feed("Rest can help. You should take 8 mg of it now. Drink water too. ")
    sink.end()
    events = drain(sink)
    assert events[0] == ("delta", "Rest can help. ")
    assert events[1][0] == "blocked"
    assert all("8 mg" not in text for _, text in events) and len(events) == 2


def test_handoff_markers_never_leak():
    sink = ReplySink()
    sink.start()
    sink.feed("I'm really glad you told me. [HANDOFF: safety]")
    sink.end()
    released = "".join(text for kind, text in drain(sink) if kind == "delta")
    assert "HANDOFF" not in released and "glad you told me" in released


def test_a_second_streamed_reply_starts_a_new_paragraph():
    sink = ReplySink()
    for part in ("Logged nausea at 6/10.", "Added chemo on Tuesday."):
        sink.start()
        sink.feed(part)
        sink.end()
    assert "".join(t for _, t in drain(sink)) == "Logged nausea at 6/10.\n\nAdded chemo on Tuesday."


# --- The client: Gemini streaming, and falling back when it isn't available ---------------------

def sse_body(*texts, usage=None):
    lines = []
    for i, t in enumerate(texts):
        chunk = {"candidates": [{"content": {"parts": [{"text": t}]}}]}
        if usage and i == len(texts) - 1:
            chunk["usageMetadata"] = usage
        lines.append(f"data: {json.dumps(chunk)}\n\n")
    return "".join(lines)


def use_handler(monkeypatch, handler):
    monkeypatch.setattr(llm.httpx, "AsyncClient",
                        lambda **kw: REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(llm.asyncio, "sleep", _no_sleep)


async def _no_sleep(*_):
    return None


async def test_gemini_stream_feeds_the_sink_and_returns_the_full_text(monkeypatch):
    def handler(request):
        assert "streamGenerateContent" in str(request.url) and "alt=sse" in str(request.url)
        return httpx.Response(200, text=sse_body("That sounds ", "hard. Rest ", "when you can.",
                                                 usage={"promptTokenCount": 9, "candidatesTokenCount": 7}))

    use_handler(monkeypatch, handler)
    client = llm.LLMClient(provider="gemini", api_key="k", model="gemini-3.6-flash")
    sink = ReplySink()
    open_sink(sink)
    text = await client.complete("sys", [{"role": "user", "content": "x"}], stream=True)
    assert text == "That sounds hard. Rest when you can."
    assert "".join(t for _, t in drain(sink)) == text


async def test_streaming_failure_falls_back_to_a_normal_request(monkeypatch):
    def handler(request):
        if "streamGenerateContent" in str(request.url):
            return httpx.Response(404, json={"error": {"message": "not found"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Still here."}]}}]})

    use_handler(monkeypatch, handler)
    client = llm.LLMClient(provider="gemini", api_key="k", model="gemini-3.6-flash")
    sink = ReplySink()
    open_sink(sink)
    assert await client.complete("sys", [{"role": "user", "content": "x"}], stream=True) == "Still here."
    assert drain(sink) == [("delta", "Still here.")]


async def test_without_a_sink_or_for_json_nothing_streams(monkeypatch):
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    use_handler(monkeypatch, handler)
    client = llm.LLMClient(provider="gemini", api_key="k", model="gemini-3.6-flash")
    await client.complete("sys", [{"role": "user", "content": "x"}], stream=True)  # no sink open
    sink = ReplySink()
    open_sink(sink)
    await client.complete("sys", [{"role": "user", "content": "x"}], json_mode=True, stream=True)
    assert not any("streamGenerateContent" in u for u in urls) and drain(sink) == []


# --- The endpoint --------------------------------------------------------------------------------

def gemini_endpoint(streamed_reply: str):
    """generateContent answers the router and risk screen; streamGenerateContent streams the reply."""

    def handler(request):
        if "streamGenerateContent" in str(request.url):
            words = streamed_reply.split(" ")
            return httpx.Response(200, text=sse_body(*[w + " " for w in words[:-1]], words[-1]))
        system = json.loads(request.content)["systemInstruction"]["parts"][0]["text"]
        if "screen messages" in system:
            reply = {"level": "none", "who": "unknown", "reason": ""}
        else:
            reply = {"intents": [{"agent": "emotional_support", "text": ""}], "reason": "feelings"}
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(reply)}]}}]})

    return handler


def stream_app(db):
    from app.api import chat_routes
    from app.core.auth import get_current_user
    from app.core.database import get_db, get_session_factory
    from app.models.db import User

    app = FastAPI()
    app.include_router(chat_routes.router)

    async def current_user():
        return await db.get(User, 1)

    async def session():
        yield db

    class TestSession:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return False

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_session_factory] = lambda: TestSession
    return app


def parse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def test_stream_endpoint_previews_then_sends_the_saved_final_reply(db, monkeypatch):
    use_handler(monkeypatch, gemini_endpoint("That sounds exhausting. You're doing a lot. How are you sleeping?"))
    monkeypatch.setattr(llm, "_client", llm.LLMClient(provider="gemini", api_key="k", model="gemini-3.6-flash"))
    async with REAL_ASYNC_CLIENT(transport=httpx.ASGITransport(app=stream_app(db)), base_url="http://t") as c:
        r = await c.post("/api/chat/stream", json={"message": "I'm so tired of everything today"})
        events = parse_events(r.text)
        done = events[-1][1]
        history = await c.get(f"/api/chat/conversations/{done['conversation_id']}")

    assert r.headers["content-type"].startswith("text/event-stream")
    kinds = [k for k, _ in events]
    assert kinds[-1] == "done" and kinds.count("delta") >= 2  # arrived in pieces
    preview = "".join(d["text"] for k, d in events if k == "delta")
    assert preview == done["content"] == "That sounds exhausting. You're doing a lot. How are you sleeping?"
    assert done["turn"]["route"] == "emotional_support"
    saved = [m for m in history.json()["messages"] if m["role"] == "assistant"]
    assert saved[0]["content"] == done["content"]


async def test_stream_endpoint_never_previews_unsafe_text(db, monkeypatch):
    use_handler(monkeypatch, gemini_endpoint("Rest helps. You should take 8 mg tonight. Sleep well."))
    monkeypatch.setattr(llm, "_client", llm.LLMClient(provider="gemini", api_key="k", model="gemini-3.6-flash"))
    async with REAL_ASYNC_CLIENT(transport=httpx.ASGITransport(app=stream_app(db)), base_url="http://t") as c:
        events = parse_events((await c.post("/api/chat/stream", json={"message": "I can't sleep"})).text)

    assert "blocked" in [k for k, _ in events]
    shown = "".join(d.get("text", "") for k, d in events if k == "delta")
    assert "8 mg" not in shown
    final = events[-1][1]["content"]
    assert "8 mg" not in final and "treatment team" in final  # the existing filter's safe reply
