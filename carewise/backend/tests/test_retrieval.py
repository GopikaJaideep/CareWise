"""Retrieval over the knowledge base, and the resource guide that answers from it."""
import pytest

from app.agents.base import SessionContext
from app.agents.resource_guide import NOT_FOUND, SYSTEM_PROMPT, ResourceGuideAgent, sources_footer
from app.services.retrieval import BM25, Retriever, load_corpus, tokenize

CHUNKS = load_corpus()


def test_corpus_loads_with_a_source_and_link_for_every_section():
    assert len({c.doc_id for c in CHUNKS}) >= 15
    for c in CHUNKS:
        assert c.title and c.heading and len(c.text) > 80
        assert c.source and c.url.startswith("https://")


def test_tokenize_drops_stopwords_and_lightly_stems():
    # Short words ("having") stay whole; longer plurals lose the s ("ulcers" -> "ulcer").
    assert tokenize("She's having mouth ulcers") == ["shes", "having", "mouth", "ulcer"]


def test_bm25_prefers_documents_sharing_rare_terms():
    bm = BM25([["nausea", "vomit"], ["fatigue", "tired"], ["nausea", "fatigue"]])
    scores = bm.scores(["vomit"])
    assert scores[0] > 0 and scores[1] == 0


async def test_keyword_search_finds_the_right_article():
    hits = await Retriever(CHUNKS).search("How do I get respite care so I can have a break?")
    assert hits[0].chunk.doc_id == "respite"


async def test_off_topic_questions_retrieve_nothing():
    assert await Retriever(CHUNKS).search("Can you recommend a good pasta recipe?") == []


async def test_results_are_capped_per_article():
    hits = await Retriever(CHUNKS).search("fever infection chemotherapy temperature neutropenia", k=8)
    per_doc = {}
    for h in hits:
        per_doc[h.chunk.doc_id] = per_doc.get(h.chunk.doc_id, 0) + 1
    assert max(per_doc.values()) <= 2


class FakeEmbedder:
    """Maps text to a tiny 'topic' vector so paraphrases land near the right article."""

    model = "fake-embed"
    TOPICS = {"vomit": 0, "throw": 0, "nausea": 0, "sick": 0, "eat": 1, "appetite": 1, "food": 1}

    def __init__(self):
        self.calls = 0

    async def embed(self, texts, *, is_query):
        self.calls += 1
        vectors = []
        for t in texts:
            v = [0.0, 0.0, 0.01]
            for word, dim in self.TOPICS.items():
                if word in t.lower():
                    v[dim] += 1.0
            vectors.append(v)
        return vectors


class MemoryCache:
    def __init__(self):
        self.store = {}

    async def load(self, model):
        return dict(self.store.get(model, {}))

    async def save(self, model, vectors):
        self.store.setdefault(model, {}).update(vectors)


async def test_hybrid_search_recovers_a_paraphrase_keyword_search_misses():
    query = "He keeps throwing up after treatment, what can we do?"
    keyword = await Retriever(CHUNKS).search(query)
    assert "nausea" not in [h.chunk.doc_id for h in keyword]  # the known keyword-only miss
    retriever = Retriever(CHUNKS, embedder=FakeEmbedder())
    await retriever.prepare()  # the background warm-up
    hybrid = await retriever.search(query)
    assert "nausea" in [h.chunk.doc_id for h in hybrid]


async def test_a_search_never_embeds_the_library_itself():
    # Before the warm-up finishes, a user's search uses keywords only and doesn't wait on the API.
    embedder = FakeEmbedder()
    retriever = Retriever(CHUNKS, embedder=embedder)
    hits = await retriever.search("How do I get respite care?")
    assert hits[0].chunk.doc_id == "respite" and embedder.calls == 0


async def test_section_embeddings_are_cached_across_restarts():
    cache = MemoryCache()
    first = FakeEmbedder()
    await Retriever(CHUNKS, embedder=first, cache=cache).prepare()
    assert first.calls == 1 and len(cache.store["fake-embed"]) == len(CHUNKS)
    second = FakeEmbedder()  # a new process: everything comes from the cache
    await Retriever(CHUNKS, embedder=second, cache=cache).prepare()
    assert second.calls == 0


async def test_embedding_failure_falls_back_to_keyword_search():
    class Broken:
        model = "broken"

        async def embed(self, texts, *, is_query):
            raise RuntimeError("quota exceeded")

    retriever = Retriever(CHUNKS, embedder=Broken())
    await retriever.prepare()  # logs the failure instead of raising
    hits = await retriever.search("How do I get respite care?")
    assert hits and hits[0].chunk.doc_id == "respite"
    assert retriever.mode == "keyword"


# --- Resource guide -------------------------------------------------------------------------------

class FakeLLM:
    def __init__(self, provider="fake", reply="Small frequent meals help [1]."):
        self.provider = provider
        self.reply = reply
        self.calls = []

    async def complete(self, system, messages, **kwargs):
        self.calls.append(system)
        return self.reply


def agent_with(llm):
    agent = ResourceGuideAgent.__new__(ResourceGuideAgent)
    agent.llm = llm
    agent.retriever = Retriever(CHUNKS)
    agent.system_prompt = SYSTEM_PROMPT
    return agent


def ctx(message):
    return SessionContext(user_id=1, conversation_id=1, user_message=message)


async def test_no_relevant_sources_means_no_model_call_and_an_honest_reply():
    llm = FakeLLM()
    response = await agent_with(llm).handle(ctx("How do I renew my passport?"))
    assert response.content == NOT_FOUND
    assert llm.calls == []


async def test_answers_carry_links_to_the_sources_they_cite():
    llm = FakeLLM(reply="Pacing activity helps [1].")
    response = await agent_with(llm).handle(ctx("What helps with cancer-related fatigue?"))
    assert "Sources:" in response.content and "https://www.cancer.org.au" in response.content
    assert "Cancer-related fatigue" in llm.calls[0]  # the model was given the retrieved text
    assert response.metadata["retrieved"][0]["id"].startswith("fatigue#")


async def test_demo_mode_quotes_the_best_section_instead_of_placeholder_text():
    response = await agent_with(FakeLLM(provider=None)).handle(ctx("How do I get respite care?"))
    assert "Respite care" in response.content and "Demo mode" not in response.content


def test_sources_footer_lists_only_cited_sources():
    hits = [type("H", (), {"chunk": c})() for c in CHUNKS[:3]]
    footer = sources_footer(hits, "Something [2].")
    assert footer.count("\n[") == 1 and "[2]" in footer
