# CareWise evals

Measures how well the agents actually behave, on labelled examples of real caregiver language.
Unit tests check that code paths work; these evals check whether the AI makes the right call.

| Suite | Cases | What it measures |
|---|---|---|
| `crisis` | 48 (24 crises, 24 hard negatives) | Crisis detection: recall (crises caught) and false-positive rate. Negatives include end-of-life planning ("she doesn't want to die in hospital"), idioms ("this week is killing me") and near-keyword phrases. |
| `routing` | 80 | Which agent handles a message: accuracy, per-agent precision/recall, accuracy by tag (`tricky`, `follow-up`, `mixed`, `resources-page`, ...). |
| `symptoms` | 23 | Symptom and medication extraction, including "pain is really bad" (no number), which must log nothing rather than a guessed severity. |
| `tasks` | 18 | Task extraction: title, category, and due date/time in the caregiver's timezone, relative to a fixed "now" (Wed 23 Sep 2026, 9:00 Sydney) so "Tuesday at 10" has one right answer. |

## Running

From `carewise/backend`:

```bash
python -m evals.run                          # every suite the current setup can run
python -m evals.run --suite routing --limit 10
python -m evals.run --delay 4                # space out calls on the Gemini free tier
python -m evals.run --provider anthropic --model claude-sonnet-5   # compare models
```

The model-based suites need `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` in `.env`; without a key they
are reported as skipped, never faked. `crisis` scores the deterministic keyword detector and always
runs. Each run writes a Markdown report and a JSON file with every case to `evals/results/`
(git-ignored; commit a report deliberately when you want to publish numbers).

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

Routing and extraction baselines need a model run; add them here once measured.

## Caveats

- The datasets are hand-written by the project author, so they can't catch blind spots the author
  shares. Treat scores as regression signals and model comparisons, not absolute quality.
- Don't tune prompts or keyword lists to these exact sentences. Add new cases for any real failure
  seen in use, and keep a held-out set if you start optimising against the numbers.
