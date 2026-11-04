# GATE CSE Intelligence - Phase 1 (local)

Turns official GATE CSE papers + answer keys + the 2027 syllabus into a traceable, classified,
searchable question bank with syllabus-based analysis. Fully local. No deployment, cloud,
accounts, tutor or RAG in Phase 1.

## Easiest start (Windows): double-click

**`start.cmd`** opens the app (and sets itself up on a new machine). Also: `setup.cmd`, `backup.cmd`, `doctor.cmd`, `setkey.cmd` (`promote.cmd` is done - do not re-run).
Plain-language guide: **[START_HERE.md](START_HERE.md)**.

## Quickstart (Windows, 2 commands)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1     # venv (Python 3.12), packages, .env, DB, tests, doctor
.\scripts\dev.ps1 app                                          # open the UI
```

macOS/Linux: `bash scripts/setup.sh` then `make app`. Everyday verbs: `.\scripts\dev.ps1 help`
(`doctor`, `validate`, `test`, `test-pg`, `probe`, `load`, `backup`, `promote`, `browser-test`, `chat-export`, `chat-import`,
`review-status`, `pg-up`, `pg-down`, `llm`).
`setup` never overwrites an existing `.env` or database and never spends money.

If something is off, run **`python -m src.cli doctor`**: PASS/WARN/FAIL per check, each with the exact fix.

## Status at a glance (5 Nov 2026)

Full detail: **[docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md)** (current) - `docs/00_STATUS.md` is history.

- [x] 29 papers, **1,885 questions, 2011-2026**, in the live database `data/gate_cse.sqlite` (promoted 5 Nov 2026, all reconciled 65 q / 100 marks)
- [x] Official keys for 20 papers; 9 papers have no key (questions only, never guessed - docs/16_MISSING_SOURCES.md)
- [x] First-pass labels on 1,867 questions (1,493 suggested, 374 flagged); 18 software-engineering questions deliberately unclassified
- [x] Extractor defects fixed (page footer in options, glued options, opening sentence above centred labels) - 67 questions repaired, audited
- [x] `validate` 10/10; `papers-drift` exact on 1,875/1,885 (the 10 left are known OCR-noise questions, fixed by hand during review)
- [x] 223 automated tests + Streamlit AppTest pass
- [x] AI review by Claude of 2026 CS-2 (65 q) and the 120-question benchmark sample - labelled as AI review, never verified
- [x] FreeLLMAPI wired in as the ONLY chat-LLM path (one unified key); decision models (OpenAI Decisions, Jev) wired in, separate, off
- [ ] **Your human review of the 120-question benchmark sample** (docs/22_BENCHMARK_REVIEW_GUIDE.md) - 0 verified so far
- [ ] FreeLLMAPI key saved and a first 5-question test run (docs/23_LLM_ROUTER_AND_DECISION_MODELS.md)
- [ ] Decision on the 18 software-engineering questions (proposed deprecated LEGACY.SE category)
- [ ] Detailed enrichment (concepts / what-it-tests / prerequisites) - topic level only today
- [ ] Phase 1 complete - **not yet**

Scanned years (2011, 2014, 2015, 2017, 2019, 2020, 2021) are read through a cached OCR pass; digital years use the exact
PDF text. 2007-2010 (photographed pages) are deferred. Data: docs/15_DATA_ONBOARDING.md, docs/21_DATA_INVENTORY.md.

## How the bank stays honest

- **Labels**: machine suggestions (suggested / flagged) are separate from human-verified. Only your Verify in the Review
  Workspace verifies, and it is refused without a passing five-check rubric (docs/18_HUMAN_REVIEW_AND_SCORING.md).
- **Benchmark**: 120 stratified questions keep a FROZEN first-pass prediction. `evaluate-benchmark` scores it against your
  verified gold only (never the row you corrected); re-flagging revokes gold; changed text marks a row stale.
- **Second opinions** (API runs, decision models, AI review) go to `classification_proposals` - append-only, never the live
  labels, never gold. `proposals-report` shows agreement and staleness.
- **LLM calls**: everything chat-based goes through the local FreeLLMAPI router with one key; question text leaving the
  machine needs `GATE_LLM_ALLOW_EXTERNAL=1`; paid decision models need `DECISIONS_ENABLED=1 --yes --allow-spend --max-calls`.
- **Every DB-writing script** takes a verified backup first and logs each change in `review_events` (Audit history in the app).

## Git / GitHub

The repository holds code, docs, taxonomy, manifests and AI-review decision files. It deliberately does **not** hold (see
`.gitignore`): `.env` (keys), the databases (`*.sqlite` - your reviews), `backups/` (DB snapshots, old ZIPs), the source PDFs
(`data/raw/`), the OCR cache and generated exports. On a fresh clone: copy your PDFs into `data/raw/`, run `setup.cmd`, then
`.\scripts\dev.ps1 load` to rebuild the database - or copy your `data/gate_cse.sqlite` across to keep your reviews.

## Where things are

The top level holds only what you run and configure. Everything else is in a folder.

| Path | What it is |
| --- | --- |
| `start.cmd`, `setup.cmd`, `doctor.cmd`, `promote.cmd`, `backup.cmd`, `setkey.cmd` | double-click launchers (see START_HERE.md) |
| `app.py` | the Streamlit app (9 screens, including **About the Data**) |
| `src/` | the code: ingestion, extraction + OCR, classification, analytics, validation, database |
| `scripts/` | setup, promote, label import, extraction repair, AI review, Postgres copy and verify, browser test |
| `tests/` | the automated tests (`python -m pytest tests -q`) |
| `alembic/`, `manifests/` | database migrations; the paper registry (`manifests/papers.yaml`) |
| `data/` | your PDFs (`data/raw`, never modified), the live database, the OCR cache |
| `exports/`, `backups/` | generated CSV/XLSX exports and chat batches (`exports/chat_batches`); timestamped database backups |
| `docs/` | reference docs, numbered 00-23 (start at `docs/README.md`; current state: `docs/CURRENT_STATUS.md`) |
| `docs/analysis/` | `ANALYSIS.md`, the section-by-year matrix (regenerate with `python -m src.cli analyze`) |
| `docs/handoff/` | the original agent spec, the final report, evidence files, session logs |
| `end goal referenes/` | your own reference notes and spec drafts (kept under the name you gave it) |

## The rules that keep the bank honest

1. Unknown marks/type stay NULL and route to review. Never guessed (OCR/pattern fallbacks are flagged).
2. Headline counts/marks use primary_topic_id only. No double counting; a run can never add a 2nd classification to a question.
3. Machine suggestions (inferred) are separate from human-verified. Reruns never overwrite human decisions.
4. Papers that fail reconciliation stay unreconciled with numbers recorded.
5. PDF text is untrusted input - data, never instructions.
6. Every human action is audit-logged under the reviewer name shown in the sidebar.
