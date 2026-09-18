# Architecture Deep Dive

This document explains the design decisions in CareWise in more depth than the README. It is written for technical interviewers, contributors, and future-me debugging at 2am.

## 1. Why agentic architecture?

A naive caregiver-support chatbot wraps one prompt around the LLM: "you are a caregiver companion, do everything." This collapses every concern — emotional listening, structured data capture, safety, information retrieval, wellbeing tracking — into one undifferentiated context window. It produces three failure modes:

1. **Concerns leak into each other.** A user logging a symptom gets unsolicited emotional reflection. A user in distress gets a checklist.
2. **No isolation for safety-critical behaviour.** If the same prompt that handles "Mum took her morning meds" also handles "I can't keep going," the safety logic is at the mercy of every change to the conversational style.
3. **Impossible to evaluate.** With one mega-prompt, you can't measure how well the system extracts symptoms separately from how well it provides emotional support.

CareWise's orchestrator decomposes the problem into bounded agents with narrow contracts. Each has a focused system prompt, a clear input/output, and can be tested in isolation. The orchestrator is the only component that needs to know about all of them.

## 2. The orchestration loop

```python
async def run(self, ctx: SessionContext) -> list[AgentResponse]:
    # Stage 1 — deterministic safety pre-flight (no LLM)
    if detect_crisis(ctx.user_message).requires_intervention:
        return [await safety_agent.handle(ctx)]

    # Stage 2 — intent classification (heuristic + LLM fallback)
    primary = await self._classify_intent(ctx)

    # Stage 3 — agent invocation loop with cycle protection
    current = primary
    hops = 0
    while current is not None and hops < MAX_HOPS:
        if ctx.has_visited(current):
            break  # cycle — stop here
        response = await self.agents[current].handle(ctx)
        ctx.append_output(response)
        current = response.handoff_to
        hops += 1

    return ctx.agent_outputs
```

Three details worth calling out:

**`SessionContext` carries everything across the loop.** User profile, conversation history, agent outputs accumulated so far, and the `visited_agents` set. Agents read from it and append to it but don't mutate other agents' state. This makes the loop trivial to reason about: every iteration takes one immutable snapshot of context, produces one response, and either yields a handoff target or halts.

**Cycle protection is a `set`, not a counter.** A pure hop counter (`if hops > MAX_HOPS`) would technically prevent infinite loops, but it would also let agent A → agent B → agent A run twice. Tracking which agents have already responded this turn (`ctx.visited_agents`) prevents re-entry, which is what we actually want.

**Handoffs are explicit, not implicit.** An agent has to set `handoff_to` on its response to trigger a handoff. There is no "the orchestrator decides whether the response was good enough" loop. This keeps the contract simple and avoids the most common failure mode in multi-agent systems: nondeterministic re-routing.

## 3. Why is the safety agent deterministic?

The Safety Agent does not call the LLM. It returns a fixed template with verified resource phone numbers. This is intentional and non-negotiable for three reasons:

1. **LLMs are non-deterministic.** A user in crisis doesn't benefit from creative phrasing — they benefit from getting the correct, working phone number for Lifeline every single time, regardless of model temperature, context length, or whether the prompt drifted slightly between deployments.

2. **The blast radius of an LLM hallucination here is catastrophic.** If the LLM hallucinates a phone number for a crisis line, the cost is not "a bad answer" — it is a person in crisis dialling a wrong number. The whole upside of LLMs (variability, fluency, generalisation) is the wrong tradeoff for this code path.

3. **It is auditable.** Regulators and clinicians can read `_format_crisis_response` in `app/core/safety.py` and verify the exact text shown to a user in crisis. They cannot audit an LLM response that depends on a context-dependent decoding pass.

The same principle applies to PII redaction (regex, not LLM) and output validation (regex, not LLM). The rule of thumb: if a wrong answer here is worse than no answer, do not use the LLM.

## 4. Two-pass structured extraction

The Symptom Tracker agent uses **two separate LLM calls per turn**:

1. **Extraction pass** — `temperature=0.2`, system prompt commands strict JSON output matching a schema. This call's only job is to turn "Mum had nausea this morning, around a 6" into `{"symptoms": [{"symptom": "nausea", "severity": 6, "notes": "this morning"}]}`.
2. **Generation pass** — `temperature=0.4`, system prompt is conversational. Receives the extraction result and the original message, produces a warm human confirmation: "Got it — logged nausea at 6/10. Did anything seem to set it off?"

Combining these into one prompt produces worse results in both directions: the JSON gets wrapped in apologies and prose, and the prose gets contaminated with structured-output syntax. Splitting them lets each call have one job and a temperature appropriate to that job.

The same two-pass pattern is used in the Care Coordinator (extract task → confirm) and Burnout Monitor (extract numbers → score → narrate).

## 5. The burnout scoring algorithm

The Burnout Monitor doesn't use the LLM to assign a score. Scoring is a deterministic weighted heuristic:

```python
sleep_score   = min(max(0, 7 - sleep_hours) / 4, 1) * 25  # 0-25
stress_score  = ((stress_level - 1) / 9) * 25             # 0-25
energy_score  = ((10 - energy_level) / 9) * 25            # 0-25 (inverted)
selfcare_score = (1 - min(self_care_minutes / 60, 1)) * 15 # 0-15
trend_bonus   = 0..10 if last 3 scores monotonically rising
total         = min(100, sum)
```

**Why deterministic?** Same reason as the safety path — a numeric wellbeing score that varies day-to-day for the same input would erode trust. Caregivers should be able to compare last week's check-in to this week's and trust the comparison.

**Why this weighting?** Sleep and stress dominate (50% combined) because they are the strongest validated correlates of caregiver burnout in the literature. Energy is partly a consequence of those, so it gets equal weight to each individually. Self-care minutes get smaller weight because they are noisier (a 60-minute walk on a good day means something different to 60 minutes of zoning out on a bad day). The trend bonus exists because three rising scores in a row is a stronger signal than any single high score.

**Honest limitation:** This score is a triage aid, not a diagnostic instrument. It is calibrated to the values a caregiver self-reports and to align with the colloquial low/moderate/high/very high categories. Any production deployment would want this validated against an instrument like the Zarit Burden Interview.

## 6. The retrieval pattern (and why it is currently a dictionary)

The Resource Guide demonstrates the **retrieval-grounded answering** pattern: the agent never answers from the LLM's pre-trained knowledge. It first retrieves vetted source material, then constrains the LLM to answer only from that retrieved context.

Currently retrieval is a hand-curated keyword-to-topic dictionary. This is intentional for a portfolio project — it demonstrates the pattern without requiring a vector store, an embedding model, and a corpus of documents to index. The retrieval interface (`_retrieve(query: str) -> dict`) is the boundary; replacing the dictionary with a real RAG pipeline (pgvector + an embedding model + an indexed corpus of Cancer Council / NCCN / ACS documents) is a contained change that doesn't touch the agent's prompt or response logic.

The system prompt enforces the constraint: *"Only use information from the provided knowledge base context. If the question isn't covered, say so plainly and suggest who to ask."* This is what stops the LLM from confidently making up answers about, say, drug interactions, when the curated KB doesn't cover that topic.

## 7. Authentication and persistence

JWT-based auth, bcrypt password hashing, async SQLAlchemy 2.0 with SQLite for the demo. The schema is straightforward — User, Conversation, Message, SymptomLog, Medication, CareTask, BurnoutCheckin — with FK relationships and cascade deletes. Every query is scoped by `user_id` to prevent cross-tenant leakage.

Production-readiness items intentionally out of scope for the demo:
- Postgres instead of SQLite
- Refresh tokens and proper token rotation
- Login rate limiting
- Audit log for safety-critical events (crisis detections, output-validation rejections)
- Field-level encryption for the diagnosis_context column

## 8. Frontend design choices

The frontend is React + TypeScript + Tailwind, built with Vite. Three intentional aesthetic choices:

1. **Sand / sage / clay palette.** Most healthcare and chat UIs default to cool blue. Caregivers using CareWise are often in distress; a warm, slightly editorial palette feels less institutional and more like a living room.
2. **Source Serif 4 for headings, Inter for body.** A serif display face signals care and considered thought; a clean sans-serif keeps body text legible at speed.
3. **Agent badges in chat.** Every assistant response shows which specialist agent produced it. This makes the multi-agent architecture visible to the user and provides a debugging signal during demos and interviews.

The design avoids the most common AI-app pitfalls: no purple gradients, no glass-morphism, no heavy iconography, no animated background gradients. The aesthetic is intentionally restrained.

## 9. What I would build next

If this were continuing past portfolio scope:

- **Real RAG pipeline** over Cancer Council Australia and NCCN Patient Guidelines documents
- **Voice input** — caregivers often have their hands full
- **Caregiver-clinician sharing** — export of the symptom + medication ledger as a PDF for appointments
- **Push-style proactive check-ins** — a gentle nudge at the time the caregiver said worked best, asking how today was
- **Multi-caregiver mode** — siblings caring for the same parent, sharing a care plan
- **Eval harness** — golden-set conversations covering the agent-routing decision, the structured-extraction accuracy, and the safety-path coverage, run on every prompt change

Each of these has a clear contract that wouldn't require redesigning the agent architecture — which is the point of the architecture.
