# Docs index

New here? Read **[../START_HERE.md](../START_HERE.md)** first (double-click `start.cmd`).

## Start here

- **CURRENT_STATUS.md** - what is true TODAY (5 Nov 2026), measured. Read this first.
- **22_BENCHMARK_REVIEW_GUIDE.md** - step by step: review the 120-question sample into gold (your next job).
- **23_LLM_ROUTER_AND_DECISION_MODELS.md** - FreeLLMAPI single-key setup; OpenAI Decisions / Jev (separate, paid, off).
- **00_STATUS.md** - history of v4-v11 (superseded by CURRENT_STATUS where they differ).
- **06_SETUP.md** - install and the database options.
- **18_HUMAN_REVIEW_AND_SCORING.md** - how to review and verify a question (the main human job).
- **20_CHAT_ASSISTED_CLASSIFICATION.md** - add suggestions with ChatGPT/Claude chat, no API key.
- **13_LLM_SETUP.md** - consent gates and run safety (provider details now in 23; direct Gemini is off in router-only mode).

## Reference (numbered)

| File | What it covers |
| --- | --- |
| 01_PRD.md | what Phase 1 is, success definition, frozen scope |
| 02_ARCHITECTURE.md | stack, data architecture, search, seams |
| 03_DAYWISE_PLAN.md | the original five-day plan with exit criteria |
| 04_CHECKLISTS.md | every checklist with ticks: inputs, reconciliation, definition of done, promotion, benchmark, LLM, repository |
| 05_AGENT_TASKS.md | how work was split between agents |
| 07_SOURCES.md | source registry with verification levels |
| 08_DECISIONS_NEEDED.md | owner decisions: made and still open (5 Nov 2026) |
| 09_REAL_PAPER_VALIDATION.md | first real paper end to end (2026 CS-1) |
| 10_REGION_STORAGE.md | source-PDF regions and on-demand previews (no stored images) |
| 11_AUDIT_RESPONSE.md, 12_AUDIT2_RESPONSE.md | responses to the independent audits |
| 14_POSTGRES_E2E.md | PostgreSQL 17 + pgvector verified end to end |
| 15_DATA_ONBOARDING.md | raw PDFs to questions, layouts, OCR, keys, and how to add a paper |
| 16_MISSING_SOURCES.md | the 9 papers without official keys, the deferred 2007-2010 scans, and what you can supply |
| 17_CLASSIFICATION_PROVENANCE.md | where the 65 GATE 2026 CS-1 suggestions came from (script, model label, run ids) and why none is verified |
| 18_HUMAN_REVIEW_AND_SCORING.md | the Review Workspace, the five-check rubric, approval scopes, what is enforced, priority order |
| 19_LOCAL_RESTART_5_STEPS.md | reopen VS Code / restart safely: stop only this app, back up, doctor, start, git push |
| 20_CHAT_ASSISTED_CLASSIFICATION.md | classify with ChatGPT/Claude chat, no API key: export a batch, import the answers as suggestions |
| 21_DATA_INVENTORY.md | all papers 2007-2026: 33 sessions in 24 PDFs, which PDF holds which session, where each key comes from (also the **About the Data** screen) |
| 22_BENCHMARK_REVIEW_GUIDE.md | reviewing the 120-question benchmark sample into gold, step by step |
| 23_LLM_ROUTER_AND_DECISION_MODELS.md | FreeLLMAPI as the single chat-LLM path; decision models (separate, paid, off); AI review |

Historical records (kept for provenance, not current): 00_STATUS, 03, 05, 09, 11, 12 and `handoff/`. The owner's v7 draft pack and its
reconciliation notes were removed 5 Nov 2026 (recoverable from git history); 17-20 are the reconciled versions.

## Generated

- **analysis/ANALYSIS.md** - section-by-year marks matrix and coverage. Regenerate: `python -m src.cli analyze`.

## Handoff material

- **handoff/REPORT.md** - the final report of the last working session: gaps, tests, decisions, click-through checklist.
- **handoff/GATE-v6-agent-handoff.md** - the original agent handoff spec the work followed.
- **handoff/notation-proposals.md** - proposed notation for three 2026 questions (a reading aid; not applied).
- **handoff/extraction-discrepancies.md** - exact differences for 2026 Q21/Q37/Q48 and 2025 Q59, what was executed, what is still open.
- **handoff/evidence/** - the original PDF regions of those questions and the raw output of the re-run (4 Nov 2026).
- **handoff/baseline.txt**, **handoff/final-state.txt** - command output recorded at the start and end of the session.
