# CareWise

[![CI](https://github.com/GopikaJaideep/CareWise/actions/workflows/ci.yml/badge.svg)](https://github.com/GopikaJaideep/CareWise/actions/workflows/ci.yml)

> A calm AI companion for people caring for someone with cancer: talk things through, log symptoms, and keep appointments and medications in one place, just by typing like you'd text a friend.

CareWise is a full-stack, multi-agent application built to the standard healthcare-adjacent AI needs: a deterministic safety path, measured behaviour (an eval suite that gates CI), grounded and cited answers, and privacy by default.

**Try it:** on the home page, choose **"Try it without signing up"**. You get a private demo account pre-filled with a week of sample data (symptoms, appointments, medications, wellbeing check-ins), deleted after 24 hours.

---

## What's worth looking at

| | |
|---|---|
| **Evals, not vibes** | 215 labelled cases across routing, crisis detection, extraction and retrieval (`backend/evals/`). CI fails the build if crisis detection or retrieval regress below baseline. The runner refuses to publish scores during an API outage instead of reporting it as bad accuracy. |
| **Safety that can't be talked out of it** | Keyword crisis detection runs first and never waits for a model; an AI risk screen runs *in parallel* with routing to catch indirect language and risk to the person being cared for. Either way the crisis reply is fixed, reviewed text, never model-written. |
| **Grounded answers** | The resource guide answers only from 16 original articles (51 sections) via hybrid BM25 + embedding search, cites what it used, and says "I don't know" when nothing is relevant. Source links are attached by code, so they can't be invented. |
| **Streaming without skipping the filter** | Replies stream a sentence at a time, and each sentence passes the output safety filter (no doses, diagnoses or cure promises) *before* it's shown. |
| **Glass box** | Every turn is traced (routing method, agents, each model call's latency and tokens) and shown under the reply as "How this reply was made". Logs carry no message text or health details. |
| **Privacy by default** | Memory between chats is opt-in, fully visible and deletable; contact details and crisis content are never stored (enforced in code). |

### Measured results

From `python -m evals.run` (see [`backend/evals/README.md`](backend/evals/README.md) for methodology and caveats):

| What | Result |
|---|---|
| Retrieval, keyword only | right article first 76.7%, in top 4 86.7%, off-topic refused 90% |
| Retrieval, hybrid (+ Gemini embeddings) | right article first **100%**, in top 4 **100%**, off-topic refused 90% |
| Crisis detection, keyword layer alone | 87.5% recall (21/24) at 8.3% false alarms, up from 50%; optimistic, since the new phrases and patterns were added after seeing this set's misses |
| Routing, extraction, keyword + AI risk screen | pending a full model run |

The retrieval cutoffs were tuned on the same small set they're measured on, so treat the hybrid numbers as optimistic. The eval README spells out what these numbers can and can't tell you.

---

## How a message is handled

```mermaid
flowchart TD
    M([Caregiver's message]) --> K{Keyword crisis check<br/>deterministic, no model}
    K -- crisis --> S[Safety agent<br/>fixed, reviewed reply]
    K -- no --> P
    subgraph P [In parallel]
        R[Router<br/>shortcuts, follow-ups,<br/>up to 3 intents]
        X[AI risk screen<br/>crisis / concern / none,<br/>and who is at risk]
    end
    X -- crisis --> S
    R --> A[Agents, each on its part of the message]
    A --> E[Emotional support]
    A --> ST[Symptom tracker]
    A --> CC[Care coordinator]
    A --> RG[Resource guide<br/>hybrid search + citations]
    A --> BM[Burnout monitor]
    E & ST & CC & RG & BM --> F[Output filter<br/>no doses, diagnoses or cure promises]
    S --> SAVE
    F --> SAVE[Save reply and trace]
    F -. streamed sentence by sentence .-> U([Caregiver sees the reply])
    SAVE --> U
    SAVE -. background, if memory is on .-> MEM[(Memory update)]
```

**Agents**

| Agent | Does | Notable |
|---|---|---|
| Emotional support | Listens and validates | Never diagnoses; uses remembered context when memory is on; told to check in gently when the risk screen flags distress |
| Symptom tracker | Logs symptoms and medications from plain language | Validated structured extraction; asks for a 1-10 severity rather than guessing one; answers "what have we logged?" from the records |
| Care coordinator | Appointments, errands, reminders | Resolves "Tuesday at 10" in the caregiver's timezone |
| Resource guide | General information | Hybrid retrieval over a curated library; cites sources; refuses when nothing is relevant |
| Burnout monitor | Wellbeing check-ins and trend | Weighted score with a trend amplifier; out-of-range answers are asked again, not saved |
| Safety | Crisis content | **No model call**: fixed text with verified numbers, including a version for when the person at risk is the one being cared for |

**Every model output is validated** against a Pydantic schema (`backend/app/agents/outputs.py`) with one repair retry; a failed API call is never retried as a "repair".

---

## Tech stack

**Backend:** Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic 2, Gemini or Anthropic, Postgres (SQLite for local development), pytest.
**Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Recharts.
**Ops:** GitHub Actions (tests, eval gates, type-check and build), Render (backend), Vercel (frontend), Docker Compose for local full-stack.

---

## Running it

### Local development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env        # add GEMINI_API_KEY (free) or ANTHROPIC_API_KEY
uvicorn app.main:app --reload

# Frontend, in another terminal
cd frontend
npm install
npm run dev                    # http://localhost:5173, proxies /api to :8000
```

Without an API key, CareWise runs in demo mode: routing uses deterministic rules, the resource guide quotes its sources directly, and other replies are clearly marked as demo text.

### Docker Compose

```bash
cp .env.example .env && docker compose up --build   # http://localhost:8080
```

### Tests and evals

```bash
cd backend
python -m pytest -q                      # 242 tests
python -m evals.run --suite crisis,retrieval   # offline suites, no key needed
python -m evals.run --delay 4            # all suites, with a model key
```

---

## Deploying

### Keep your data: use Postgres

By default the backend stores data in a SQLite file on the server. Hosts such as Render reset the disk on every deploy, **which deletes every account**. For any hosted deployment, set `DATABASE_URL` to a Postgres database (Neon, Supabase and Render all have free tiers), exactly as your provider shows it:

```
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
```

A direct (unpooled) connection string is best. A pooled one (Neon's `-pooler` host, Supabase's port 6543) also works: the backend detects it and turns off the prepared-statement caching that transaction pooling breaks.

Also set a fixed `SECRET_KEY`, or everyone is signed out whenever it changes. Check a deploy at **`/health`**: `"persistent": true` means Postgres; `false` means data will be lost on the next deploy.

Migrations (Alembic) run automatically at startup. After changing a model, generate one with `alembic revision --autogenerate -m "..."` from `backend/`, and review it: a test renders every migration as Postgres SQL, because autogenerate writes SQLite spellings (like a boolean default of `'0'`) that Postgres rejects.

### Other settings

- **Separate model keys for production and evals.** An eval run can exhaust a free-tier daily quota and take the live app's replies down with it.
- **Email** (password reset, address confirmation) goes through Resend (`RESEND_API_KEY`). Until a sending domain is verified, Resend only delivers to the account owner, so address confirmation is a reminder, not a requirement.
- `LLM_PRICE_INPUT_PER_MTOK` / `LLM_PRICE_OUTPUT_PER_MTOK` (USD per million tokens) add cost estimates to traces; none are assumed.

---

## How specific parts work

### The resource guide

It answers only from original plain-language articles in `backend/app/knowledge/`, each linked to its source (Cancer Council, Carer Gateway, Services Australia, ACS, Palliative Care Australia). Search is hybrid: BM25 always runs; with `GEMINI_API_KEY` set, Gemini embeddings add semantic search, merged by reciprocal-rank fusion behind a relevance cutoff. Section vectors are cached in the database and built by a background warm-up at startup, never inside a person's request.

Similarity is computed in Python: across ~50 sections that takes well under a millisecond. At thousands of sections, the next step is pgvector (an indexed `vector` column and `ORDER BY embedding <=> :query`), which Neon, Supabase and Render Postgres all support.

To add an article, drop a Markdown file in `backend/app/knowledge/` (header lines `title:`, `source:`, `url:`, `region:`, then `## ` sections) and add questions for it to `backend/evals/datasets/retrieval.jsonl`.

### Memory between chats (opt-in)

CareWise can remember durable facts between chats (a treatment schedule, the care team, what helps) so people don't repeat themselves. It is **off until turned on** on the Home page, where every fact is listed and deletable; turning it off forgets everything. A background task updates memory every few messages, after the reply is sent. Contact details, ID numbers and anything about suicide, self-harm or a crisis are never stored: enforced in code (`backend/app/services/memory.py`), and turns that reached the safety response are skipped.

### Accounts

Sign-up rejects email domains that don't exist or don't accept mail (a DNS check), and emails a confirmation link; emails are matched ignoring case. Tokens carry a purpose, so a confirmation link can't be used to log in. The one-click demo creates a private account per visitor, capped at 20 messages, 5 new demos per address per hour and 200 live at once, and deleted after 24 hours.

---

## API

| Endpoint | Method | Description |
|---|---|---|
| `/api/auth/register`, `/login`, `/me` | POST, POST, GET | Accounts |
| `/api/auth/demo` | POST | Private, pre-filled demo account |
| `/api/auth/verify-email`, `/resend-verification` | POST | Email confirmation |
| `/api/auth/forgot-password`, `/reset-password` | POST | Password reset |
| `/api/chat` | POST | One chat turn: reply, agent trace and per-turn trace |
| `/api/chat/stream` | POST | The same turn as server-sent events (safety-filtered preview, then the final reply) |
| `/api/chat/conversations`, `/{id}` | GET | Chat history |
| `/api/symptoms`, `/api/medications`, `/api/tasks` | GET, POST | Tracking |
| `/api/burnout/checkins` | GET, POST | Wellbeing check-ins |
| `/api/memory`, `/enabled`, `/{id}` | GET, PUT, DELETE | What CareWise remembers |
| `/api/dashboard` | GET | Home page summary |
| `/health` | GET | Status, and whether data survives a redeploy |

Full OpenAPI schema at `/docs` when running.

---

## Design decisions worth defending

1. **A deterministic safety path.** A person in crisis needs the right phone numbers every time, not creative phrasing. The model may decide *that* the safety path is taken; it never writes the words.
2. **The AI risk screen can only add protection.** Keywords run first and always win; the screen runs in parallel (no added wait), and any error, timeout or unusable output falls back to the keyword result.
3. **Measure before claiming.** Every "improvement" was evaluated. A standard stemmer raised keyword ranking by 3 points but dropped off-topic refusal from 90% to 70%, so it was not shipped; the CI gate would have rejected it anyway.
4. **Fail safe, in layers.** Streaming falls back to a normal request if it can't start; the frontend falls back only when nothing reached the server (so a message is never sent twice); a sleeping server shows "waking up" instead of signing people out.
5. **No pgvector yet.** At 51 sections, in-process similarity is sub-millisecond and fully testable; pgvector is the documented next step at scale.
6. **Validation over native schema enforcement, for now.** A wrong provider schema field would fail every extraction in production and couldn't be caught by CI; Pydantic validation with one repair is fully testable today.

---

## Limitations

- **Not a clinician.** Prompts and the knowledge base are written for clarity, not clinically validated; a real deployment would need review by clinicians and people with lived caregiving experience.
- **Small, author-written eval sets.** They catch regressions and compare models; they can't catch blind spots the author shares.
- **Indirect crisis language** is harder: the keyword layer misses messages like "nobody would notice if I disappeared", and its 87.5% was measured on the set its phrases were tuned on; the AI screen's real-world recall is still to be measured. When the model is down, the keyword layer is all that's left, so every failed reply also gives 000 and Lifeline.
- **Not a compliance-reviewed product:** no HIPAA / Australian Privacy Principles review, audit log retention policy or multi-region deployment.

**In a crisis, call 000 (Australia) or your local emergency number. Lifeline: 13 11 14, 24/7.**

---

## License

MIT, see `LICENSE`.

## Author

Built by Gopika. CareWise comes from believing AI is most valuable when it shows up for the people doing invisible labour, and that healthcare-adjacent AI demands a higher bar of care than general-purpose chat.
