"""Resource guide agent — surfaces vetted information without giving medical advice.

Uses a curated knowledge base (in production this would be RAG over reputable
sources like Cancer Council, NCCN, ACS). Always cites and always reminds the
caregiver that this is general information, not advice for their specific case.
"""
from __future__ import annotations

from app.agents.base import AgentName, AgentResponse, BaseAgent, SessionContext
from app.services.llm import get_llm_client


# In production, this would be replaced with retrieval from a vector store
# of vetted, region-appropriate sources. The current curated set demonstrates
# the pattern and lets the demo work without a live RAG pipeline.
KNOWLEDGE_BASE = {
    "fatigue": {
        "summary": "Cancer-related fatigue is one of the most common side effects of treatment. It is different from ordinary tiredness — rest may not relieve it. Pacing activity, gentle movement, hydration, and short structured rest periods can help.",
        "sources": [
            "Cancer Council Australia — Fatigue and cancer (cancer.org.au/cancer-information/managing-side-effects/fatigue)",
            "American Cancer Society — Fatigue in people with cancer (cancer.org)",
        ],
    },
    "nausea": {
        "summary": "Nausea during treatment can often be managed with prescribed anti-emetic medications taken on schedule rather than only when symptoms appear. Small frequent meals, ginger, and avoiding strong food smells can help.",
        "sources": [
            "Cancer Council Australia — Nausea and vomiting",
            "NCCN Guidelines for Patients — Antiemesis",
        ],
    },
    "appetite": {
        "summary": "Appetite loss is common during treatment. Small, calorie-dense meals throughout the day are usually more manageable than three large ones. A dietitian referral through the treatment team can help.",
        "sources": ["Cancer Council Australia — Nutrition and cancer"],
    },
    "caregiver_burnout": {
        "summary": "Caregiver burnout is a recognised condition characterised by physical, emotional, and mental exhaustion. It is not a personal failing. Respite care, peer support groups, and brief structured breaks are evidence-based interventions.",
        "sources": [
            "Carers Australia — Caring for the carer (carersaustralia.com.au)",
            "Cancer Council — Caring for someone with cancer",
        ],
    },
    "communication_with_team": {
        "summary": "Keeping a single notebook (paper or digital) with symptoms, medications, questions, and appointment summaries makes consultations more productive. Bringing a second person to appointments helps with recall.",
        "sources": ["Cancer Council Australia — Talking with your doctors"],
    },
    "financial_support_au": {
        "summary": "In Australia, caregivers may be eligible for the Carer Payment, Carer Allowance, or Carer Supplement through Services Australia. Cancer Council also runs a free financial counselling service.",
        "sources": [
            "Services Australia — Carer payments",
            "Cancer Council 13 11 20 — Pro bono financial counselling",
        ],
    },
}


SYSTEM_PROMPT = """You are the Resource Guide specialist within CareWise.

Your role: provide clear, general, evidence-based information from vetted sources to help caregivers understand what they're navigating. You are NOT a substitute for the medical team.

Strict rules:
1. Only use information from the provided knowledge base context. If the question isn't covered, say so plainly and suggest who to ask (oncology nurse, GP, Cancer Council 13 11 20).
2. Always include sources at the end as a "Sources:" line.
3. Always include this reminder when discussing symptoms or treatment: "This is general information — your treatment team knows your specific situation best."
4. Never give specific dosages, never diagnose, never predict outcomes.
5. Keep responses concise (3-5 short paragraphs maximum).

Knowledge base context for this query:
{kb_context}
"""


class ResourceGuideAgent(BaseAgent):
    name = AgentName.RESOURCE_GUIDE
    description = "Provides general, sourced information without giving medical advice."

    def __init__(self) -> None:
        self.llm = get_llm_client()
        self.system_prompt = SYSTEM_PROMPT

    async def handle(self, ctx: SessionContext) -> AgentResponse:
        relevant = self._retrieve(ctx.user_message)

        if not relevant:
            kb_context = "(No directly matching entries in the knowledge base.)"
        else:
            kb_context = "\n\n".join(
                f"Topic: {topic}\nSummary: {data['summary']}\nSources: {'; '.join(data['sources'])}"
                for topic, data in relevant.items()
            )

        system = self.system_prompt.format(kb_context=kb_context)
        text = await self.llm.complete(
            system=system,
            messages=[{"role": "user", "content": ctx.user_message}],
            temperature=0.3,
        )

        return AgentResponse(
            agent=self.name,
            content=text,
            metadata={"retrieved_topics": list(relevant.keys())},
        )

    def _retrieve(self, query: str) -> dict[str, dict]:
        """Simple keyword retrieval. In production: vector search over RAG corpus."""
        q = query.lower()
        keyword_map = {
            "fatigue": ["tired", "exhaust", "fatigue", "no energy", "wiped out"],
            "nausea": ["nausea", "nauseous", "vomit", "sick to", "throwing up"],
            "appetite": ["appetite", "won't eat", "not eating", "no hunger", "can't eat"],
            "caregiver_burnout": ["burnt out", "burnout", "overwhelm", "can't cope", "exhausted myself"],
            "communication_with_team": ["doctor", "oncologist", "appointment prep", "what to ask", "consultation"],
            "financial_support_au": ["financial", "money", "carer payment", "centrelink", "afford"],
        }
        matched = {}
        for topic, keywords in keyword_map.items():
            if any(kw in q for kw in keywords):
                matched[topic] = KNOWLEDGE_BASE[topic]
        return matched
