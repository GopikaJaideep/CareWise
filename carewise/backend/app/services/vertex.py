"""Gemini through Vertex AI on Google Cloud, instead of an AI Studio API key.

Same models and the same request and response format as the Gemini API; only the address and the
sign-in differ. There is no key to store: Application Default Credentials supply a short-lived
OAuth token, which on Cloud Run comes from the service's own service account and on a laptop from
`gcloud auth application-default login`. Billing is per use on the Google Cloud project, so there's
no free-tier daily cap to run into.

Enabled with LLM_PROVIDER=vertex and GOOGLE_CLOUD_PROJECT. VERTEX_LOCATION defaults to "global",
where the newest Gemini and embedding models are served; prompts may then be processed in any
Google region. Set a region (e.g. "australia-southeast1") instead if data must stay in one place
and the model is offered there.
"""
from __future__ import annotations

import asyncio
from typing import Any

SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def model_url(project: str, location: str, model: str, method: str) -> str:
    """e.g. method="generateContent", "streamGenerateContent?alt=sse" or "predict"."""
    host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
    return f"https://{host}/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:{method}"


class VertexAuth:
    """Caches Application Default Credentials and refreshes the token shortly before it expires.

    google-auth is synchronous, so loading and refreshing run in a thread; a lock stops several
    concurrent requests from all refreshing at once.
    """

    def __init__(self) -> None:
        self._credentials: Any = None
        self._lock = asyncio.Lock()

    async def headers(self) -> dict[str, str]:
        async with self._lock:
            if self._credentials is None:
                import google.auth

                self._credentials, _ = await asyncio.to_thread(google.auth.default, scopes=[SCOPE])
            if not self._credentials.valid:  # also true when the token is about to expire
                from google.auth.transport.requests import Request

                await asyncio.to_thread(self._credentials.refresh, Request())
            return {"Authorization": f"Bearer {self._credentials.token}"}


_auth: VertexAuth | None = None


def get_auth() -> VertexAuth:
    global _auth
    if _auth is None:
        _auth = VertexAuth()
    return _auth
