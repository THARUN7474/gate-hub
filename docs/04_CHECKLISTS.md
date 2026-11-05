# Checklists

## Day-0 input checklist

- [x] 2027 CS syllabus PDF (`data/raw/syllabus/CS_GATE2027_Syllabus.pdf`; sha256 matches taxonomy.yaml - tested)
- [x] 2027 GA syllabus PDF (`data/raw/syllabus/GA_GATE2027_Syllabus.pdf`, added 5 Nov 2026; sha256 recorded in taxonomy.yaml,
  GA text verified verbatim by `tests/test_syllabus_sources.py`; 4 syllabus items that lacked a concept were added:
  GA.VA.SEQ, GA.QA.GEOM, GA.AA.ANALOGY, GA.SA.TRANSFORM)
- [x] Papers 2007-2026 in `data/raw/papers/` (2007-2010 photographed pages deferred)
- [x] Year-wise papers + keys 2021-2026 in `data/raw/` (20 papers with official keys in total)
- [ ] Optional: PYQ books/solutions - local only, never cloud-processed without consent
- [x] Docker Desktop, Python 3.12+, git installed; repo tests pass (234, 5 Nov 2026)

## Per-paper reconciliation checklist (every paper, every run) - all 29 papers, 5 Nov 2026

- [x] Manifest exists with expected counts (or explicitly null = derive)
- [x] Extracted count/marks match manifest - 29/29 reconciled (65 questions / 100 marks each)
- [x] Zero unexplained NULL marks/type (24 NULL questions, all flagged with a reason - `validate`)
- [x] Every question joins to a key where a key exists (1,300 key rows); the 9 key-less papers are listed in docs/16
- [x] NAT ranges / MSQ sets / dropped questions modelled, not flattened (covered by tests)
- [ ] 5 random crops per paper eyeballed against the PDF (spot checks only so far; part of your review)

## Definition of done (mirrored by automated tests) - status 5 Nov 2026

Ticked = verified by running the tests / checks on this machine (5 Nov 2026: 223 pytest on SQLite, Streamlit AppTest all PASS,
`validate` 10/10 on the promoted live database; PostgreSQL and the Playwright browser test last ran 4 Nov 2026).

- [x] Importing the same PDF twice doesn't duplicate questions
- [x] No question is associated with the wrong session or master key
- [x] Missing extraction data is flagged, not invented
- [x] All classification IDs exist in the approved taxonomy (also enforced on every human correction and chat import)
- [x] Editing + verifying a classification survives an ingestion rerun (and an extraction correction survives a `--refresh` reload)
- [x] Subject totals reconcile with primary-classified questions (secondary topics are tags and never add marks)
- [x] A question opens its correct original page crop
- [x] Every matrix drill-down lists exactly the contributing questions
- [x] Exported CSVs match database queries
- [x] `python -m src.cli validate` passes on the live database (10/10, 5 Nov 2026, after promotion)
- [x] 2025 CS-1 Q59 text completed (5 Nov 2026)
- [ ] `papers-drift` byte-identical on all questions - 1,875/1,885; the 10 open are OCR-noise options left for a hand fix
  (2014-S2 Q63, 2014-S3 Q22, 2015-S1 Q11, 2015-S2 Q07/Q22/Q28/Q62, 2015-S3 Q29/Q52, 2017-S2 Q42)

## Quality gates before any number leaves the app

- [ ] Gold-set (blind, dev/holdout split) accuracy measured; holdout untouched by tuning
- [ ] Suggested bar: >=90% section-level, >=80% topic-level on the holdout
- [ ] Review-queue agreement tracked separately (anchoring-biased; never reported as accuracy)
- [ ] Coverage report states measured coverage; nothing unverified labelled complete

## Human review checklist (per question - docs/18_HUMAN_REVIEW_AND_SCORING.md)

- [ ] Reviewer name set in the sidebar (every decision is logged under it)
- [ ] Original PDF region looked at **before** reading the suggestion
- [ ] Question number, diagram, text, options, marks and type match the original (fix via "Correct the extraction" with a reason)
- [ ] Official key aligned, or the paper is listed as having no key (never claim a missing key as verified)
- [ ] Primary section/topic, concepts, secondary topics and what-it-tests chosen
- [ ] All five review checks answered; Verify only if Source fidelity and Primary topic pass, else Flag / Save without verifying
- [ ] After a batch: reload and spot-check persistence; `python -m src.cli validate`; `python -m src.cli review-status`

Progress (5 Nov 2026): 0 of 1,867 classified questions verified; 0 rubrics saved (18 more questions deliberately unclassified - taxonomy gap).
AI review (Claude, labelled as such, NOT verification): 65 questions of 2026 CS-2 + the 120 benchmark questions.

## Chat-assisted batch checklist (no API key - docs/20_CHAT_ASSISTED_CLASSIFICATION.md)

- [ ] `chat-export` 10-25 questions; new chat per batch; paste prompt.md; attach every image
- [ ] Reply saved as answers.json in the batch folder
- [ ] `chat-import` dry run read: rejected rows corrected or left out on purpose
- [ ] `chat-import --yes` (backs up first); imported rows show as suggestions, none verified
- [ ] Suggestions reviewed in the Review Workspace

## Promotion checklist (live database) - DONE 5 Nov 2026

- [x] Backup of the live DB taken and integrity-checked (`backups/gate_cse.20261105-030702.sqlite`)
- [x] Dry run read: 29 in manifest, 2 live, 27 to add
- [x] Rehearsal on a copy: 29 papers / 1,885 questions; existing review events and classifications unchanged
- [x] **Owner approval and the real promotion** (5 Nov 2026, 03:07) - 29/29 reconciled, pre-existing rows proven unchanged
- [x] Candidate labels imported (`scripts/import_candidate_labels.py --yes`; the script was removed after use, recoverable from git commit 71d0558; candidate DB retired to `backups/`): 1,802 labels, 413 events, 13 cleanups, 120 benchmark rows
- [x] `repair-text --paper GATE-CS-2025-S1 --yes` (Q59 completed)
- [x] Extractor fixes applied (`scripts/repair_extraction.py --paper all --yes --rebaseline-pending`): 67 questions, audited

## Benchmark gold review checklist (docs/22_BENCHMARK_REVIEW_GUIDE.md)

- [x] 120-question stratified sample drawn; frozen baselines intact (3 re-baselined after audited extraction fixes)
- [x] AI review of all 120 recorded as a separate, scoreable opinion (live labels untouched on sampled questions)
- [ ] Owner reviews the sample in Review Workspace -> Show: "benchmark sample (gold review)"
- [ ] `evaluate-benchmark` with >= 50 gold rows (first honest accuracy number)
- [ ] `evaluate-benchmark --provider ai-review` (how often the AI reviewer agreed with you)

## LLM access checklist (docs/23_LLM_ROUTER_AND_DECISION_MODELS.md)

- [x] FreeLLMAPI provider added; `.env` routes every chat-LLM call through it (`GATE_LLM_ROUTER_ONLY=1`)
- [x] FreeLLMAPI router running on http://127.0.0.1:3001 (answers 401 without the key, as expected)
- [ ] Unified key saved: `python -m src.cli set-key freellmapi`; `llm-status` shows it as set
- [ ] First 5-question `classify-compare freellmapi` test (writes nothing)
- [x] Decision models (OpenAI Decisions, Jev) wired in separately, dry-run only, `DECISIONS_ENABLED=0`
- [ ] Decision-model run on the benchmark - only after gold exists and you approve the estimate (~$0.007 Jev / ~$0.017 Decisions)

## v12 UI + full coverage checklist (5 Nov 2026)

- [x] Every question classified: 1,885 / 1,885 (18 historical software-engineering questions under `LEGACY.SE`, out of the 2027 syllabus)
- [x] Pipeline Status: score cards, horizontal progress bars (classified / AI-reviewed / human-verified / benchmark gold), papers table, review-progress-per-paper table
- [x] Every screen: icon + title + one-line purpose; long explanations moved into collapsed "How to read this page" toggles (nothing removed)
- [x] Theme: Inter font, tighter heading sizes, bordered metrics (`.streamlit/config.toml`)
- [x] LLM Classify browser freeze fixed (a `$` in two labels was parsed as LaTeX); regression test `tests/test_ui_v12.py`

## v13 UI: stages, second opinions, clearer review (5 Nov 2026)

- [x] Pipeline Status: six stage cards (read from PDFs / machine label / AI review / decision models / benchmark gold / human-verified), each with a bar, a "what to do" note and a button that opens the right screen with filters preset
- [x] Extraction issues (165) shown as a stage, with a direct "Fix extraction issues" filter
- [x] New **Second Opinions** screen: every AI-review verdict (agree / flag / correct) beside the current label, filterable, click to review; decision-model answers tab
- [x] Review Workspace: Show filter gains "extraction issues" and "AI-reviewed"; status strip per question (extraction, machine label, AI review, decision models, human review, with sources); numbered sections; step-by-step "What you do here"; optional fields folded away
- [x] Full names in every subject/topic dropdown (codes still used underneath)
- [x] Question Browser: no 500-row cap (all 1,885 listed), extraction filter, results breakdown by subject/status
- [x] Analysis Matrix: Marks and Questions tabs (1,885 questions = 2,900 marks), column totals row + grand total, full names under codes
- [x] Glossary: Sections table fixed (was blank - long text column), syllabus file paths + checksum check
- [x] Approve Queue explains when to use it; shows only ready-to-approve questions by default
- [x] LLM Classify split into tabs; new Decision models tab (status, benchmark cost estimate, exact commands)
- [x] "What this page gives you" guide on every screen
- [x] Tests: 234 passed (`tests/test_ui_v13.py`; 235 after the Questions tab), AppTest all PASS, browser-checked

## Repository checklist

- [x] `.gitignore` keeps out `.env`, databases, `backups/` (incl. old ZIPs), `data/raw/` PDFs, caches, exports
- [x] Old ZIP packages moved to `backups/zips/`
- [x] `git init`, first commit, `main` branch, remote `origin` = github.com/THARUN7474/gate-hub
