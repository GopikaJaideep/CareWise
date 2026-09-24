# CareWise

> An AI companion for cancer caregivers — agentic, safety-first, evidence-grounded.

CareWise is a full-stack application built around an **agentic orchestration architecture** with five specialised LLM agents and a deterministic safety layer. It is designed for the people who hold someone else up: tracking symptoms, coordinating care, surfacing trustworthy information, monitoring caregiver burnout, and offering a calm, non-judgmental presence.

This is a portfolio project demonstrating production-grade patterns for healthcare-adjacent AI: explicit medical-boundary enforcement, deterministic crisis paths (no LLM creativity in the safety code path), retrieval-grounded resource answers with source citation, structured-output extraction, and cycle-protected agent handoffs.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         User message                              │
└────────────────────────────────┬─────────────────────────────────┘
                                 ▼
                 ┌───────────────────────────────┐
                 │   Pre-flight safety check     │   ← deterministic
                 │   (regex-based crisis detect) │     (no LLM)
                 └──────────────┬────────────────┘
                                │ crisis?  ──► Safety Agent ──► verified resources
                                ▼
                 ┌───────────────────────────────┐
                 │      Intent classification     │   ← cheap heuristic
                 │   (heuristic + LLM fallback)   │     + LLM
                 └──────────────┬────────────────┘
                                ▼
        ┌───────────────────────┴────────────────────────┐
        │                                                │
        ▼                ▼               ▼               ▼               ▼
 Emotional        Symptom          Care            Resource         Burnout
 Support          Tracker          Coordinator     Guide            Monitor
 (LLM)            (LLM + DB)       (LLM + DB)      (RAG-style       (LLM + DB +
                                                    KB + LLM)        scoring algo)
        │                                                │
        └─────────────► Handoff loop (max 3 hops) ◄──────┘
                       Cycle-protected via visited set
                                │
                                ▼
                     ┌──────────────────────┐
                     │  Output validation   │   ← regex-based
                     │  (dosage, diagnosis, │     final pass
                     │   outcome promises)  │
                     └──────────┬───────────┘
                                ▼
                       Persisted response
```

### Agents

| Agent | Responsibility | Notable design choice |
|---|---|---|
| **Emotional Support** | Listens, validates, reflects | Hands off to Safety Agent on crisis signals; informed by recent burnout score |
| **Symptom Tracker** | Extracts structured symptom/medication data from natural language | Two-step pipeline: JSON extraction → DB write → human-language confirmation |
| **Care Coordinator** | Tasks, appointments, reminders | Handles add / list / mark-done in one turn; resolves relative dates ("Thursday") to absolute |
| **Resource Guide** | General information from vetted sources | Curated knowledge base (Cancer Council AU, NCCN, ACS); always cites; refuses out-of-scope questions |
| **Burnout Monitor** | Structured wellbeing check-ins, weighted score, trend tracking | Trend amplification when last 3 scores increasing; deterministic resource surfacing at high scores |
| **Safety** | Crisis-level content | **Deterministic — no LLM call**. Verified Lifeline / Beyond Blue / Carer Gateway numbers |

### Safety guardrails

CareWise treats safety as a separate concern from helpfulness, layered at every stage:

1. **Pre-flight** — keyword-based crisis detection runs before any LLM call. Crisis content short-circuits the orchestrator and returns a deterministic response with verified resources.
2. **Per-agent** — the emotional support agent's system prompt explicitly forbids diagnosis, prognosis, and toxic positivity. The resource guide is restricted to retrieved context.
3. **Output validation** — every LLM response runs through a final regex pass that blocks specific dosages, definitive diagnoses, and outcome promises ("this will cure her").
4. **Logging** — PII redaction (phone numbers, emails, Medicare numbers) before any log line is written.

The full rationale and the test suite verifying this behaviour live in `backend/app/core/safety.py` and `backend/tests/test_safety.py`.

---

## Tech stack

**Backend** — Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Anthropic SDK, JWT auth, Pytest

**Frontend** — React 18 + TypeScript, Vite, Tailwind CSS, Recharts, React Router

**Deployment** — Docker Compose (backend + frontend with nginx reverse proxy)

---

## Quickstart

### Option 1 — Docker Compose (recommended)

```bash
# 1. Clone and configure
git clone <your-fork-url> carewise && cd carewise
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 2. Build and run
docker compose up --build

# 3. Open http://localhost:8080
```

The first build takes ~2 minutes. Backend runs on `:8000`, frontend on `:8080`.

### Option 2 — Local development

**Backend:**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn app.main:app --reload
```

**Frontend (in a separate terminal):**
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api/*` to the backend on `:8000`.

### Without an API key

CareWise will run without `ANTHROPIC_API_KEY` set — agents return clearly-marked demo responses so you can explore the UI, auth, persistence, and routing without spending tokens.

### Deploying the backend: keep your data

By default the backend stores everything in a SQLite file inside the server. Most hosts (Render, Railway, Koyeb, Fly without a volume) reset the server's disk on every deploy, which **deletes every account and record**. For any hosted deployment, point `DATABASE_URL` at a Postgres database instead (Neon, Supabase and Render all have free tiers):

```
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
```

Paste the URL exactly as your provider shows it; `postgres://` and `sslmode=` are converted for the async driver automatically. Tables are created on first start. Also set a fixed `SECRET_KEY`, or everyone is signed out whenever it changes. The startup log says which database is in use.

### How the resource guide finds answers

The resource guide answers only from a curated library of original plain-language articles in `backend/app/knowledge/`, each linked to its source (Cancer Council, Carer Gateway, Services Australia, ACS...). Every answer cites the sections it used, and the source list is added by code, not written by the model, so links can't be invented. If nothing relevant is found, it says so rather than guessing.

Search is hybrid: BM25 keyword ranking always runs; with `GEMINI_API_KEY` set, Gemini embeddings add semantic search, merged by reciprocal-rank fusion, behind a relevance cutoff. Section vectors are cached in the database, so restarts don't re-embed. Measured with `python -m evals.run --suite retrieval` on 30 questions and 10 off-topic ones:

| Search | Right article first | Right article in top 4 | Off-topic refused | Median search time |
|---|---|---|---|---|
| Keyword only | 76.7% | 86.7% | 90% | <1 ms |
| Hybrid (+ Gemini embeddings) | 100% | 100% | 90% | ~1 s |

Keyword search misses paraphrases ("he keeps throwing up", "she won't eat"); semantic search recovers all of them. The relevance cutoffs were tuned on this same small set, so treat the hybrid numbers as optimistic until more questions (and a held-out set) are added. Embeddings are built in the background at startup, never inside a user's request, and until they're ready search uses keywords.

Similarity is computed in Python: across ~50 sections that takes well under a millisecond. At thousands of sections, the next step is pgvector (an indexed `vector` column and `ORDER BY embedding <=> :query`), which Neon, Supabase and Render Postgres all support.

To add an article, drop a Markdown file in `backend/app/knowledge/` (header lines `title:`, `source:`, `url:`, `region:`, then `## ` sections) and add a few questions for it to `evals/datasets/retrieval.jsonl`.

### Changing the database schema

Migrations (Alembic) run automatically when the backend starts, so deploys need no manual step. After changing a model in `app/models/db.py`, generate and commit a migration from `backend/`:

```
alembic revision --autogenerate -m "add notes to care tasks"
```

Review the generated file in `migrations/versions/`. `tests/test_migrations.py` fails if the models and migrations ever drift apart. Databases created before migrations were introduced are adopted automatically on first start.

---

## Repository layout

```
carewise/
├── backend/
│   ├── app/
│   │   ├── agents/          # The orchestrator + 6 specialist agents
│   │   │   ├── orchestrator.py
│   │   │   ├── emotional_support.py
│   │   │   ├── symptom_tracker.py
│   │   │   ├── care_coordinator.py
│   │   │   ├── resource_guide.py
│   │   │   ├── burnout_monitor.py
│   │   │   └── safety.py
│   │   ├── api/             # FastAPI routes (auth, chat, tracking)
│   │   ├── core/            # Config, auth, DB, safety guardrails
│   │   ├── models/          # SQLAlchemy ORM models
│   │   └── services/        # LLM client wrapper
│   └── tests/               # 25 tests — safety, burnout, orchestrator
├── frontend/
│   ├── src/
│   │   ├── components/      # Shared UI (AppShell, AgentBadge)
│   │   ├── pages/           # Landing, auth, dashboard, chat, tasks, symptoms, resources
│   │   ├── lib/             # API client, auth context
│   │   └── App.tsx
│   └── nginx.conf
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Testing

```bash
cd backend
pytest -v
```

The test suite covers what matters most for a healthcare-adjacent AI system:

- **Crisis detection** — explicit suicide language, self-harm, secondary distress signals, no-false-positive cases
- **Medical overreach detection** — diagnosis requests, dosage questions, distinguishing from normal logging
- **Output validation** — blocks dosages, diagnoses, outcome promises; allows safe responses
- **PII redaction** — phone numbers (US + AU mobile formats), emails, Medicare numbers
- **Burnout scoring** — boundary cases, score-cap, trend amplification
- **Orchestrator** — handoff handling, **cycle detection** when agents try to hand off to each other in a loop, crisis short-circuit

```
============================== 25 passed in 1.37s ==============================
```

---

## API surface

| Endpoint | Method | Description |
|---|---|---|
| `/api/auth/register` | POST | Create account with caregiver context |
| `/api/auth/login` | POST | Returns JWT |
| `/api/auth/me` | GET | Current user |
| `/api/chat` | POST | **Primary entry point** — runs orchestrator, returns response with agent trace |
| `/api/chat/conversations` | GET | List conversations |
| `/api/chat/conversations/{id}` | GET | Conversation with messages |
| `/api/symptoms` | GET | Recent symptom logs |
| `/api/medications` | GET | Active medications |
| `/api/tasks` | GET / POST | List / create care tasks |
| `/api/tasks/{id}/complete` | PATCH | Mark task done |
| `/api/burnout/checkins` | GET | Burnout check-in history |
| `/api/dashboard` | GET | Aggregated summary |

Full OpenAPI schema at `http://localhost:8000/docs` when running.

---

## Design decisions worth defending

1. **Why a deterministic safety path?** LLMs are non-deterministic by design. A user in crisis doesn't need creative phrasing — they need correct, vetted resources every time. The Safety Agent never calls the LLM; it returns a fixed template with verified phone numbers.

2. **Why intent classification before agent invocation?** Letting one big "do everything" prompt handle every caregiver message conflates concerns and makes evaluation impossible. With explicit routing, each agent has a narrow contract, a focused system prompt, and is independently testable.

3. **Why cycle protection?** Agents can hand off to each other (emotional support → safety, for example). Without a `visited` set and hop limit, two agents that hand off to each other would loop forever on a single user turn. The `visited` set in `SessionContext` prevents this.

4. **Why structured extraction in two LLM passes?** The Symptom Tracker agent first runs a JSON-extraction pass (`temperature=0.2`, schema-constrained) to capture data, then a separate generation pass (`temperature=0.4`) to produce a warm confirmation. Mixing data extraction and conversational generation in one prompt produces unreliable JSON.

5. **Why a curated knowledge base instead of a general RAG?** For a portfolio demo, a curated dictionary of Cancer Council / NCCN / ACS topics demonstrates the citation pattern and refusal-when-out-of-scope behaviour without requiring a vector store and document corpus. The retrieval interface is abstracted so it can be swapped for a real RAG pipeline (e.g., pgvector or Pinecone) without changing the agent.

---

## Limitations & honest disclaimers

- Demo-grade RAG (curated dictionary, not a real retrieval pipeline)
- SQLite for the demo; would use PostgreSQL in production
- Bcrypt password hashing (rate-limit login attempts in production — not implemented here)
- No multi-region deployment, no audit log retention policy, no HIPAA / Australian Privacy Principles (APP) compliance review — this is a portfolio project, not a production healthcare product
- The agent system prompts are tuned for clarity, not for clinical validation. A real deployment would require review by clinicians and people with lived caregiving experience.

**CareWise is not a clinician.** In a crisis, call Lifeline on 13 11 14 (AU) or your local emergency number.

---

## License

MIT — see `LICENSE`.

## Author

Built by Gopika as a portfolio project. The motivation for CareWise comes from believing AI is most valuable when it shows up for the people doing invisible labour — and that healthcare-adjacent AI demands a different bar of care than general-purpose chat.
