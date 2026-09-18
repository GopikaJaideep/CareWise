"""CareWise FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth_routes, chat_routes, tracking_routes
from app.core.config import get_settings
from app.core.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI companion for cancer caregivers — agentic, safety-first, evidence-grounded.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(chat_routes.router)
app.include_router(tracking_routes.router)


@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
