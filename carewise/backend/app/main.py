"""CareWise FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth_routes, chat_routes, memory_routes, tracking_routes
from app.core.config import get_settings
from app.core.database import IS_SQLITE, SessionLocal, init_db
from app.services.retrieval import get_retriever
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    # Embed the knowledge base in the background (a no-op without GEMINI_API_KEY, and cached in
    # the database after the first deploy), so the first resource question isn't slow.
    warmup = asyncio.create_task(get_retriever().prepare())
    yield
    warmup.cancel()
    stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI companion for cancer caregivers — agentic, safety-first, evidence-grounded.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def server_timing(request: Request, call_next):
    """How long the server spent on each request, in a standard Server-Timing header (visible in
    the browser's network panel), so slowness can be split between network and server. For a
    streamed reply it covers the time until streaming starts."""
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - start) * 1000:.1f}"
    return response

app.include_router(auth_routes.router)
app.include_router(chat_routes.router)
app.include_router(tracking_routes.router)
app.include_router(memory_routes.router)


# HEAD too: uptime monitors (UptimeRobot and others) check with HEAD by default, and a 405 there
# would report the site as down.
@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
        "docs": "/docs",
    }


@app.api_route("/health", methods=["GET", "HEAD"])
async def health(db: bool = False):
    """Also says where data lives, so a deploy can be checked from a browser. Never credentials.

    "persistent": false means a SQLite file on the server: on hosts that reset the disk on each
    deploy (Render's default), every account is lost on redeploy. Set DATABASE_URL to Postgres.

    ?db=true also times three trivial queries, to tell a slow database connection apart from a
    slow server. Off by default, so uptime monitors don't keep a scale-to-zero database awake.
    """
    body: dict = {
        "status": "healthy",
        "database": "sqlite" if IS_SQLITE else "postgres",
        "persistent": not IS_SQLITE,
    }
    if db:
        timings = []
        async with SessionLocal() as session:
            for _ in range(3):
                start = time.perf_counter()
                await session.execute(text("SELECT 1"))
                timings.append(round((time.perf_counter() - start) * 1000, 1))
        body["db_query_ms"] = timings  # the first may include connecting or waking the database
    return body
