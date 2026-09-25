# CareWise evals

Measures how well the agents actually behave, on labelled examples of real caregiver language.
Unit tests check that code paths work; these evals check whether the AI makes the right call.

| Suite | Cases | What it measures |
|---|---|---|
| `crisis` | 48 (24 crises, 24 hard negatives) | Crisis detection: recall (crises caught) and false-positive rate. Negatives include end-of-life planning ("she doesn't want to die in hospital"), idioms ("this week is killing me") and near-keyword phrases. |
| `retrieval` | 40 (30 questions, 10 off-topic) | Resource-guide search: hit@1, recall@4, MRR, and whether off-topic questions are refused. Runs keyword-only always and hybrid too when `GEMINI_API_KEY` is set, side by side. |
| `routing` | 86 | Which agent handles a message: accuracy, per-agent precision/recall, accuracy by tag (`tricky`, `follow-up`, `mixed`, `resources-page`, ...). Six `multi` cases also check every agent for messages with several requests ("log nausea 6. Also remind me chemo Tuesday"), in order. |
| `symptoms` | 23 | Symptom and medication extraction, including "pain is really bad" (no number), which must log nothing rather than a guessed severity. |
| `tasks` | 18 | Task extraction: title, category, and due date/time in the caregiver's timezone, relative to a fixed "now" (Wed 23 Sep 2026, 9:00 Sydney) so "Tuesday at 10" has one right answer. |

## Running

From `carewise/backend`:

```bash
python -m evals.run                          # every suite the current setup can run
python -m evals.run --suite routing --limit 10
python -m evals.run --delay 4                # space out calls on the Gemini free tier
python -m evals.run --resume --delay 4       # continue a run across days of free-tier quota
python -m evals.run --provider anthropic --model claude-sonnet-5   # compare models
```

The model-based suites need `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` in `.env`; without a key they
are reported as skipped, never faked. `crisis` scores the deterministic keyword detector and always
runs. Each run writes a Markdown report and a JSON file with every case to `evals/results/`
(git-ignored; commit a report deliberately when you want to publish numbers).

If more than 20% of a suite's cases fail at the API (quota exhausted, outage, blocked reply), the
run stops with exit code 2 and writes no report: those scores would measure the outage, not the
model. Isolated failures are excluded from scoring and listed under "Excluded cases".

**When the quota is smaller than a run.** The Gemini free tier can allow as few as 20 requests per
model per day, while a full run needs about 200. `--resume` saves every successful answer to
`evals/.cache/` (git-ignored) and replays saved answers on the next run without calling the API, so
each day's quota goes only to unanswered cases. Run the same command daily until it finishes; the
report then says how many answers were replayed. Scores are the same as a single run's, and latency
is the model's original time, not the cache's. Failed calls are never saved, so they are retried.
Changing a prompt changes the key, so edited prompts are re-asked rather than scored on old answers.

`--fail-under SUITE.METRIC=MIN` turns a run into a regression gate. CI (`.github/workflows/ci.yml`)
runs the offline suites on every push and pull request and fails the build if crisis recall or
precision, or keyword retrieval recall or refusal, drops below the baselines below. When a change
improves a number, raise its gate in the workflow. The full model evals run from the Actions tab
("Run workflow", tick "model evals") using a `GEMINI_API_KEY` repository secret, and upload the
report as an artifact. Use a separate key from production: an eval run can exhaust a free-tier
daily quota and take the live app's replies down with it.

Scoring lives in `metrics.py` and is unit-tested (`tests/test_eval_metrics.py`), including an
end-to-end run of the runner against a fake model.

## Baseline

Keyword crisis detector, 24 September 2026:

| Recall (crises caught) | False-positive rate | Precision |
|---|---|---|
| **50.0%** (12/24) | 8.3% (2/24) | 85.7% |

It catches explicit phrases but misses inflections ("I've been thinking about ending my life"),
indirect language ("What's the point of living anymore?") and risk to the person being cared for
("Mum said she wants to kill herself"). It also flags end-of-life planning as a crisis. This is the
number an AI-based risk check has to beat without raising the false-positive rate much.

Retrieval, 24 September 2026 (gemini-embedding-001):

| Search | Hit@1 | Recall@4 | MRR | Off-topic refused |
|---|---|---|---|---|
| keyword | 76.7% | 86.7% | 0.817 | 90% |
| hybrid | 100% | 100% | 1.000 | 90% |

The cosine cutoff was chosen on this same set (weakest real match 0.686, strongest off-topic 0.663),
so the hybrid numbers are optimistic; add questions and a held-out set before trusting them further.

Routing and extraction baselines need a model run; add them here once measured.

## Caveats

- The datasets are hand-written by the project author, so they can't catch blind spots the author
  shares. Treat scores as regression signals and model comparisons, not absolute quality.
- Don't tune prompts or keyword lists to these exact sentences. Add new cases for any real failure
  seen in use, and keep a held-out set if you start optimising against the numbers.
