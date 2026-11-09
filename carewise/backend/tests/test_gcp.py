"""Running on Google Cloud: Gemini through Vertex AI, Cloud SQL, and Cloud Scheduler jobs."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.models.db import CareTask
from app.services import llm as llm_module
from app.services import retrieval, scheduler, vertex


class FakeAuth:
    async def headers(self):
        return {"Authorization": "Bearer test-token"}


@pytest.fixture
def on_vertex(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_provider", "vertex")
    monkeypatch.setattr(s, "google_cloud_project", "carewise-test")
    monkeypatch.setattr(s, "vertex_location", "global")
    monkeypatch.setattr(vertex, "_auth", FakeAuth())
    return s


def test_vertex_addresses():
    assert vertex.model_url("p", "global", "gemini-x", "generateContent") == (
        "https://aiplatform.googleapis.com/v1/projects/p/locations/global/publishers/google/models/gemini-x:generateContent"
    )
    assert vertex.model_url("p", "australia-southeast1", "m", "predict").startswith(
        "https://australia-southeast1-aiplatform.googleapis.com/v1/projects/p/locations/australia-southeast1/"
    )


async def test_vertex_is_gemini_with_a_different_address_and_sign_in(on_vertex):
    client = llm_module.LLMClient()
    assert client.provider == "gemini" and client.vertex and client.api_key == ""
    url, headers = await client._gemini_target()
    assert url.endswith("/projects/carewise-test/locations/global/publishers/google/models/" + client.model + ":generateContent")
    assert headers == {"Authorization": "Bearer test-token"}  # no API key anywhere
    stream_url, _ = await client._gemini_target(stream=True)
    assert stream_url.endswith(":streamGenerateContent?alt=sse")


async def test_vertex_without_a_project_falls_back_to_demo_mode(on_vertex, monkeypatch):
    monkeypatch.setattr(on_vertex, "google_cloud_project", "")
    assert llm_module.LLMClient().provider is None


async def test_a_sign_in_failure_is_a_failed_call_not_a_crash(on_vertex, monkeypatch):
    class Broken:
        async def headers(self):
            raise RuntimeError("no credentials")

    monkeypatch.setattr(vertex, "_auth", Broken())
    text = await llm_module.LLMClient().complete("sys", [{"role": "user", "content": "hi"}])
    assert text == llm_module.ERROR_MESSAGE


async def test_vertex_embeddings_send_one_text_per_request(on_vertex):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        seen.append((request.url.path, request.headers["authorization"], body))
        n = float(len(body["instances"][0]["content"]))
        return httpx.Response(200, json={"predictions": [{"embeddings": {"values": [n, 1.0]}}]})

    embedder = retrieval.VertexEmbedder("carewise-test", "global", "gemini-embedding-001", transport=httpx.MockTransport(handler))
    vectors = await embedder.embed(["a", "bbb"], is_query=False)
    assert vectors == [[1.0, 1.0], [3.0, 1.0]]  # in input order
    assert all(path.endswith("/models/gemini-embedding-001:predict") for path, _, _ in seen)
    assert all(len(body["instances"]) == 1 and body["instances"][0]["task_type"] == "RETRIEVAL_DOCUMENT" for *_, body in seen)
    assert {auth for _, auth, _ in seen} == {"Bearer test-token"}


def test_the_app_and_evals_pick_vertex_embeddings_when_on_vertex(on_vertex):
    assert isinstance(retrieval.make_embedder(on_vertex), retrieval.VertexEmbedder)


# --- Cloud Scheduler --------------------------------------------------------------------------

@pytest.fixture
async def api(db, monkeypatch):
    from app.main import app

    monkeypatch.setattr(scheduler, "SessionLocal", async_sessionmaker(db.bind, expire_on_commit=False))
    sent = []

    async def fake_push(_db, user_id, title, body, tag):
        sent.append(tag)

    monkeypatch.setattr(scheduler, "send_push_to_user", fake_push)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c, sent


async def test_cron_jobs_are_off_without_a_secret_and_refuse_a_wrong_one(api, monkeypatch):
    client, _ = api
    s = get_settings()
    monkeypatch.setattr(s, "cron_secret", "")
    assert (await client.post("/internal/cron/reminders")).status_code == 404
    monkeypatch.setattr(s, "cron_secret", "right")
    assert (await client.post("/internal/cron/reminders")).status_code == 403
    assert (await client.post("/internal/cron/reminders", headers={"X-Cron-Secret": "wrong"})).status_code == 403
    assert (await client.post("/internal/cron/nope", headers={"X-Cron-Secret": "right"})).status_code == 404
    assert (await client.post("/internal/cron/reminders", headers={"X-Cron-Secret": "right"})).json() == {"ran": "reminders"}


async def test_the_every_minute_check_sends_each_due_reminder_once(db, api, monkeypatch):
    client, sent = api
    monkeypatch.setattr(get_settings(), "cron_secret", "right")
    now = datetime.now(timezone.utc)
    due = CareTask(user_id=1, title="Chemo", due_at=now + timedelta(minutes=5))
    later = CareTask(user_id=1, title="Scan", due_at=now + timedelta(hours=2))
    db.add_all([due, later])
    await db.commit()
    for _ in range(2):  # two ticks: still one reminder
        await client.post("/internal/cron/reminders", headers={"X-Cron-Secret": "right"})
    assert sent == [f"carewise-task-{due.id}"]


def test_external_mode_starts_no_in_app_scheduler(monkeypatch):
    monkeypatch.setattr(get_settings(), "scheduler_mode", "external")
    assert scheduler.start_scheduler() is None and scheduler._scheduler is None


def test_cloud_sql_socket_urls_work():
    from sqlalchemy.engine import make_url

    from app.core.database import describe_database, normalize_database_url

    url = normalize_database_url("postgresql://carewise:p%40ss@/carewise?host=/cloudsql/proj:australia-southeast1:db")
    assert url.startswith("postgresql+asyncpg://")
    assert make_url(url).query["host"] == "/cloudsql/proj:australia-southeast1:db"
    assert make_url(url).password == "p@ss"
    assert describe_database(url) == "Postgres at /cloudsql/proj:australia-southeast1:db/carewise"
