"""Resource guide agent: answers general questions from the curated knowledge base only.

Retrieval (app/services/retrieval.py) finds relevant sections of the articles in app/knowledge/.
The model writes a plain-language answer from those sections and cites them as [1], [2]...; the
"Sources" list is then added by code from what was actually retrieved, so it can't be invented.
If nothing relevant is found, the reply says so instead of guessing.
"""
from __future__ import annotations

import re

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.services.llm import get_llm_client
from app.services.retrieval import Hit, get_retriever

SYSTEM_PROMPT = """You are the Resource Guide specialist within CareWise, an AI companion for cancer caregivers.

Answer the caregiver's question using ONLY the numbered sources below. You are not a substitute for the medical team.

Rules:
1. Use only facts stated in the sources. If they don't answer the question, say so plainly and suggest the treatment team or Cancer Council on 13 11 20.
2. Cite the source numbers you used in square brackets, e.g. "Small, frequent meals often help [2]." Do not write a sources list or URLs; they are added automatically.
3. Never give specific doses, never diagnose, never predict outcomes. Where the sources describe urgent warning signs, keep that advice clear and prominent.
4. Plain, warm language. 2-4 short paragraphs.
5. End with: "This is general information. The treatment team knows your situation best."

Sources:
{sources}
"""

NOT_FOUND = (
    "I don't have trusted information on that in my library, so I'd rather not guess.\n\n"
    "The treatment team is the best place to ask. Cancer Council's information and support line, "
    "13 11 20, can also help, and for carer support Carer Gateway is on 1800 422 737."
)

DISCLAIMER = "This is general information. The treatment team knows your situation best."


def format_sources(hits: list[Hit]) -> str:
    return "\n\n".join(
        f"[{n}] {h.chunk.title}: {h.chunk.heading}\n{h.chunk.text}" for n, h in enumerate(hits, start=1)
    )


def sources_footer(hits: list[Hit], answer: str | None = None) -> str:
    """List the sources the answer cites (or all retrieved ones if it cites none), each with its link."""
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer or "")}
    lines, seen = [], set()
    for n, h in enumerate(hits, start=1):
        if cited and n not in cited:
            continue
        key = (h.chunk.title, h.chunk.url)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"[{n}] {h.chunk.title} ({h.chunk.source}): {h.chunk.url}")
    return "Sources:\n" + "\n".join(lines)


class ResourceGuideAgent(BaseAgent):
    name = AgentName.RESOURCE_GUIDE
    description = "Provides general, sourced information without giving medical advice."

    def __init__(self) -> None:
        self.llm = get_llm_client()
        self.retriever = get_retriever()
        self.system_prompt = SYSTEM_PROMPT

    async def handle(self, ctx: SessionContext) -> AgentResponse:
        hits = await self.retriever.search(ctx.user_message)
        metadata = {
            "retrieval_mode": self.retriever.mode,
            "retrieved": [
                {"id": h.chunk.id, "bm25": round(h.bm25, 2),
                 "cosine": None if h.cosine is None else round(h.cosine, 3)}
                for h in hits
            ],
        }
        if not hits:
            return AgentResponse(agent=self.name, content=NOT_FOUND, metadata=metadata)

        if self.llm.provider is None:
            # Demo mode: no model to summarise, so quote the best-matching section directly.
            top = hits[0].chunk
            answer = f"**{top.title}: {top.heading}**\n\n{top.text} [1]\n\n{DISCLAIMER}"
        else:
            answer = await self.llm.complete(
                system=self.system_prompt.format(sources=format_sources(hits)),
                messages=[{"role": "user", "content": ctx.user_message}],
                temperature=0.3,
                stream=True,
            )
        return AgentResponse(
            agent=self.name,
            content=f"{answer.strip()}\n\n{sources_footer(hits, answer)}",
            metadata=metadata,
        )
