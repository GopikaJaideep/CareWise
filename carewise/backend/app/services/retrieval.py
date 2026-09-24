"""Retrieval over the curated knowledge base (app/knowledge/*.md).

Hybrid search:
- BM25 keyword ranking. Always available: no API key, no network, deterministic.
- Dense (semantic) ranking with Gemini embeddings, when GEMINI_API_KEY is set. Section vectors
  are cached in the knowledge_embeddings table, so a restart doesn't pay to re-embed.
The two rankings are merged with reciprocal-rank fusion. A relevance gate drops weak matches, so
an off-topic question gets "I don't know" instead of the nearest irrelevant section.

Similarity is computed in Python: at this size (tens of sections) that takes well under a
millisecond. pgvector becomes worthwhile at thousands of sections; see the README.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"

# Relevance gate. A section is only used if it clears at least one of these. Both were chosen on
# evals/datasets/retrieval.jsonl: with gemini-embedding-001 the weakest real question's best match
# scored 0.686 and the strongest off-topic question's 0.663. That margin is thin and was tuned on the
# same set it's measured on, so re-check with `python -m evals.run --suite retrieval` after adding
# articles or changing the embedding model.
MIN_BM25 = 4.0
MIN_COSINE = 0.675
RRF_K = 60  # standard reciprocal-rank-fusion constant
MAX_PER_DOC = 2  # keep answers from drawing on only one article when others are relevant

STOPWORDS = set(
    "a an and are as at be been but by can could do does did for from had has have he her his how i if in "
    "into is it its me my of on or our she so some that the their them then there these they this to "
    "us was we were what when where which who why will with would you your about any just more most "
    "also than too very should get got im ive dont cant mum dad".split()
)


# --- Corpus -------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    title: str
    heading: str
    text: str
    source: str
    url: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(f"{self.title}\n{self.heading}\n{self.text}".encode()).hexdigest()

    @property
    def embed_text(self) -> str:
        return f"{self.title}. {self.heading}. {self.text}"


def load_corpus(directory: Path = KNOWLEDGE_DIR) -> list[Chunk]:
    """Each file: `key: value` header lines, then `## Heading` sections. One chunk per section."""
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        header, _, body = path.read_text(encoding="utf-8").partition("\n\n")
        meta = dict(line.split(":", 1) for line in header.splitlines() if ":" in line)
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        for i, section in enumerate(re.split(r"^## ", body, flags=re.M)[1:]):
            heading, _, text = section.partition("\n")
            chunks.append(Chunk(
                id=f"{path.stem}#{i}", doc_id=path.stem, title=meta["title"], heading=heading.strip(),
                text=" ".join(text.split()), source=meta["source"], url=meta["url"],
            ))
    return chunks


# --- Lexical ------------------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower().replace("'", "").replace("’", ""))
    out = []
    for w in words:
        if w in STOPWORDS or len(w) < 2:
            continue
        # Light stemming so "feeding"/"fed"/"feeds" and "ulcers"/"ulcer" meet in the middle.
        for suffix in ("ing", "ed", "es", "s"):
            if len(w) > len(suffix) + 3 and w.endswith(suffix):
                w = w[: -len(suffix)]
                break
        out.append(w)
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = docs
        self.k1, self.b = k1, b
        self.avgdl = sum(len(d) for d in docs) / len(docs) if docs else 0.0
        self.tf = [Counter(d) for d in docs]
        df = Counter(term for d in docs for term in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        result = []
        for tf, doc in zip(self.tf, self.docs):
            s = 0.0
            for term in set(query):
                if term not in tf:
                    continue
                f = tf[term]
                s += self.idf[term] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(doc) / self.avgdl))
            result.append(s)
        return result


# --- Dense --------------------------------------------------------------------------------------

class Embedder(Protocol):
    model: str

    async def embed(self, texts: list[str], *, is_query: bool) -> list[list[float]]: ...


class GeminiEmbedder:
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
    BATCH = 100
    RETRYABLE = {429, 500, 503}
    ATTEMPTS = 4

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def embed(self, texts: list[str], *, is_query: bool) -> list[list[float]]:
        task = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for start in range(0, len(texts), self.BATCH):
                batch = texts[start:start + self.BATCH]
                body = {"requests": [
                    {"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}, "taskType": task}
                    for t in batch
                ]}
                for attempt in range(1, self.ATTEMPTS + 1):
                    response = await client.post(
                        self.URL.format(model=self.model), headers={"x-goog-api-key": self.api_key}, json=body,
                    )
                    # Free-tier rate limits (429) and overload (503) are routine: the background warm-up
                    # backs off and retries. A user's query doesn't wait; the caller falls back to keywords.
                    if response.status_code in self.RETRYABLE and not is_query and attempt < self.ATTEMPTS:
                        await asyncio.sleep(5 * attempt)
                        continue
                    break
                response.raise_for_status()
                vectors += [e["values"] for e in response.json()["embeddings"]]
        return vectors


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class EmbeddingCache(Protocol):
    async def load(self, model: str) -> dict[str, list[float]]: ...
    async def save(self, model: str, vectors: dict[str, list[float]]) -> None: ...


# --- Search -------------------------------------------------------------------------------------

@dataclass
class Hit:
    chunk: Chunk
    score: float  # fused rank score; only meaningful for ordering
    bm25: float
    cosine: float | None = None


@dataclass
class Retriever:
    chunks: list[Chunk]
    embedder: Embedder | None = None
    cache: EmbeddingCache | None = None
    _vectors: dict[str, list[float]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        self.bm25 = BM25([tokenize(f"{c.title} {c.heading} {c.text}") for c in self.chunks])

    @property
    def mode(self) -> str:
        return "hybrid" if self.embedder and self._vectors else "keyword"

    async def prepare(self) -> None:
        """Embed any sections not already cached. Safe to call repeatedly; failures fall back to keyword search.

        Run in the background at startup (app/main.py), never inside a user's request: embedding the
        whole library there would make that person wait, and on SQLite the cache write would contend
        with the request's own open transaction."""
        if not self.embedder or len(self._vectors) == len(self.chunks):
            return
        async with self._lock:
            try:
                cached = await self.cache.load(self.embedder.model) if self.cache else {}
                missing = [c for c in self.chunks if c.content_hash not in cached]
                if missing:
                    fresh = await self.embedder.embed([c.embed_text for c in missing], is_query=False)
                    new = {c.content_hash: v for c, v in zip(missing, fresh)}
                    if self.cache:
                        await self.cache.save(self.embedder.model, new)
                    cached.update(new)
                    logger.info("Embedded %d knowledge sections with %s", len(missing), self.embedder.model)
                self._vectors = {c.id: cached[c.content_hash] for c in self.chunks}
            except Exception as e:  # network, quota, bad key: keyword search still works
                logger.warning("Semantic search unavailable, using keyword search only: %s", e)

    async def search(self, query: str, k: int = 4) -> list[Hit]:
        lexical = self.bm25.scores(tokenize(query))
        dense: list[float] | None = None
        # Semantic search only once the background warm-up has the section vectors ready.
        if self.embedder and self._vectors:
            try:
                (qvec,) = await self.embedder.embed([query], is_query=True)
                dense = [cosine(qvec, self._vectors[c.id]) for c in self.chunks]
            except Exception as e:
                logger.warning("Query embedding failed, using keyword search only: %s", e)

        candidates = [
            i for i in range(len(self.chunks))
            if lexical[i] >= MIN_BM25 or (dense is not None and dense[i] >= MIN_COSINE)
        ]
        if not candidates:
            return []

        def ranks(scores: list[float]) -> dict[int, int]:
            ordered = sorted(candidates, key=lambda i: scores[i], reverse=True)
            return {i: r for r, i in enumerate(ordered, start=1)}

        lex_rank = ranks(lexical)
        dense_rank = ranks(dense) if dense is not None else {}
        fused = {
            i: 1 / (RRF_K + lex_rank[i]) + (1 / (RRF_K + dense_rank[i]) if dense_rank else 0.0)
            for i in candidates
        }

        hits: list[Hit] = []
        per_doc: Counter = Counter()
        for i in sorted(candidates, key=lambda i: fused[i], reverse=True):
            chunk = self.chunks[i]
            if per_doc[chunk.doc_id] >= MAX_PER_DOC:
                continue
            per_doc[chunk.doc_id] += 1
            hits.append(Hit(chunk, fused[i], lexical[i], dense[i] if dense is not None else None))
            if len(hits) == k:
                break
        return hits


# --- App wiring ---------------------------------------------------------------------------------

class DatabaseEmbeddingCache:
    """Section vectors in the knowledge_embeddings table, keyed by content hash and model."""

    async def load(self, model: str) -> dict[str, list[float]]:
        from sqlalchemy import select

        from app.core.database import SessionLocal
        from app.models.db import KnowledgeEmbedding

        async with SessionLocal() as db:
            rows = await db.execute(select(KnowledgeEmbedding).where(KnowledgeEmbedding.model == model))
            return {r.content_hash: r.vector for r in rows.scalars()}

    async def save(self, model: str, vectors: dict[str, list[float]]) -> None:
        from app.core.database import SessionLocal
        from app.models.db import KnowledgeEmbedding

        async with SessionLocal() as db:
            for content_hash, vector in vectors.items():
                await db.merge(KnowledgeEmbedding(content_hash=content_hash, model=model, vector=vector))
            await db.commit()


_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        settings = get_settings()
        embedder = GeminiEmbedder(settings.gemini_api_key, settings.embedding_model) if settings.gemini_api_key else None
        _retriever = Retriever(load_corpus(), embedder=embedder, cache=DatabaseEmbeddingCache() if embedder else None)
        logger.info("Knowledge base: %d sections, %s search", len(_retriever.chunks),
                    "hybrid" if embedder else "keyword")
    return _retriever
