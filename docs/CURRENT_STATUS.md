# Current status (measured 5 Nov 2026, after the owner-approved promotion and the v12 fixes)

This page is the CURRENT state. `docs/00_STATUS.md` keeps the v4-v11 history; when they
disagree, this page wins. Every number below was queried or run on this machine.

## Phase 1 is NOT complete

Still open:
- human review: 0 verified; the benchmark sample has no gold yet;
- API validation: no successful LLM inference yet; FreeLLMAPI is wired in but its key is not set;
- detailed enrichment (concepts / what-it-tests / prerequisites);
- the 18 taxonomy gaps (LEGACY.SE decision);
- 10 OCR questions whose options are noisy (listed below);
- the auditor's 52/10/3 file (deferred by the owner).

The 9 papers without official keys stay key-less by owner decision: questions only, never the 2015
printed ticks.

## Live database `data/gate_cse.sqlite`

| | value |
| --- | --- |
| papers / questions | 29 / 1,885 (promoted 5 Nov 03:07, all 29 reconciled) |
| classifications | 1,867 = 1,493 suggested + 374 flagged; 18 unclassified SE gaps |
| human-verified | **0** |
| benchmark sample | 120 rows, all `pending_user_review`, frozen baselines intact |
| AI-review proposals | 180 (`ai-review` / claude-opus-5-5) - opinions, not verification |
| review events | 753 |
| `validate` | 10/10 PASS |

What was applied, in order (each step took its own verified backup in `backups/`):

1. `promote_to_live.py --yes` added 27 papers. The 3 pre-existing review events and 65 labels were
   proven unchanged. Backup of the pre-promotion state: `backups/gate_cse.20261105-030702.sqlite`.
2. `import_candidate_labels.py --yes` brought across:
   - 1,802 labels;
   - 413 events (377 flags, 18 taxonomy gaps, 18 syllabus audits);
   - 13 audited what-it-tests cleanups;
   - 120 benchmark rows.
   The 65 existing labels were kept. Backup: `...-030737`.
3. `repair_truncated_text.py --paper GATE-CS-2025-S1 --yes` completed Q59. Backup: `...-030744`.
4. `repair_extraction.py --paper all --yes --rebaseline-pending` (new, see below) repaired 67 questions:
   13 texts and 118 options. Backup: `...-031814`. A follow-up `papers-load` refreshed the PDF crop
   regions of 36 questions only; backup `...-031911`.
5. `ai_review.py import` ran twice. Backups: `...-032256` (2026 CS-2) and `...-032544` (benchmark).

## Extractor defects found and fixed (5 Nov 2026)

All three fixes are in `src/extraction/extract.py` and covered by `tests/test_extraction_fixes_v12.py`.

1. **Footer and running header in options.** "Page  N  of  41" uses double spaces, and the 2023
   header reads "Computer Science **and** Information Technology (CS)". Both leaked into option D in
   2022-S1 Q01-Q10 and 2023-S1 Q02, 03, 05, 06, 07, 09, 10.
2. **Two-column option detection.** Labels at x=123 and x=124 fell into different 8-pt buckets, so
   continuation lines went to the wrong option. Real D was glued onto C in 2022-S1. In 2021-S1/S2,
   C and D were glued onto B and left empty (31 questions). Detection now uses the label spread
   (> 24 pt).
3. **Centred question labels.** In 2022-S1 Q08, 2024-S2 Q11/38/42/46/47/62, 2025-S1 Q20/23/41 and
   2025-S2 Q56, the opening sentence of the stem prints above "Q.N", so it was stored at the end of
   the previous question.

`scripts/repair_extraction.py` re-extracts in memory and changes only:
- clear wins: empty options filled with real text, or page boilerplate removed;
- word-conserving moves of an opening sentence back to its own question.

It never touches a verified or human-corrected question and logs every value
(`reviewer=extraction-repair-v12`). Three pending benchmark rows were re-baselined (content hash
only; the frozen prediction is unchanged, with an event logged): 2021-S1 Q49, 2023-S1 Q06 and
2024-S2 Q38.

Left alone deliberately (OCR noise only moves between options; fix by hand in the Review Workspace):
2014-S2 Q63, 2014-S3 Q22, 2015-S1 Q11, 2015-S2 Q07/Q22/Q28/Q62, 2015-S3 Q29/Q52, 2017-S2 Q42.

The candidate DB (`data/gate_cse.candidate.sqlite`) was not repaired; it is staging only.

## AI review by Claude (5 Nov 2026; chat, no API call)

`scripts/ai_review.py` exports questions as JSON and imports an AI reviewer's verdicts:
- each verdict becomes a `classification_proposals` row (`ai-review`) plus an `ai_review` event, labelled
  "claude-opus-5-5 (AI review - not human verification)";
- the verdicts show in the Review Workspace as an "AI review" box;
- nothing is ever verified and no gold is written.

- **2026 CS-2, end to end (65 questions):** 58 agree.
  - 5 labels corrected in live: Q09 → GA.AA, Q21 → CN.LAYER, Q22 → CN.ROUTE, Q36 → EM.DM, Q64 → EM.CAL.
  - 2 flagged: Q15 (three-schema architecture is not in the syllabus), Q39 (algorithm listings glued
    into option D).
  - About 30 official keys were recomputed and match.
- **Benchmark sample (120 questions):** 85 agree, 5 topic corrections, 30 flags (mostly extraction:
  2015 response-sheet residue, "END OF THE QUESTION PAPER" leaks, garbled OCR formulas/code; plus the
  SE gap and RSA). On sampled questions the live label and status were deliberately NOT changed, so
  your gold review stays independent. Claude's accuracy is measured against your gold later with
  `evaluate-benchmark --provider ai-review`.

Decision files: `exports/ai_review/*.decisions.json`.

## LLM access

- **FreeLLMAPI** is the single chat-LLM path (`GATE_LLM_ROUTER_ONLY=1`). The router runs on :3001
  and answers 401 without a key. `FREELLMAPI_API_KEY` is still empty: set it with
  `python -m src.cli set-key freellmapi`. Gemini direct is ignored in router-only mode. No call has
  been made.
- **Decision models** (OpenAI Decisions gpt-6-luna, TypeSafe Jev) are a separate, paid path, off by
  default (`DECISIONS_ENABLED=0`, no keys). Dry-run estimate for the 120-question sample: Jev
  $0.007, Decisions $0.017. Nothing has been sent.

Details: `docs/23_LLM_ROUTER_AND_DECISION_MODELS.md`.

## Tests (5 Nov 2026)

- `pytest`: **223 passed**. That includes 5 extractor-fix tests and 6 router/decision tests; owner
  routing settings are neutralised in tests by `tests/conftest.py`.
- `scripts/ui_apptest.py`: all checks pass.
- AppTest on a copy of live: the AI-review box renders for a correction (2026-S2 Q09), a taxonomy gap
  (2013-S4 Q27) and an extraction flag (2015-S3 Q55).

## Rollback

Close the app first. Then copy the backup you want over `data/gate_cse.sqlite`:
- `backups/gate_cse.20261105-030702.sqlite` = just before promotion (2 papers);
- `backups/gate_cse.20261104-174315.sqlite` = before the v11 merge upgrade.

Code before the v11 merge: `backups/pre-v11-merge-20261104-173745/files/`.

## Repository (5 Nov 2026)

Git repository initialised; remote `origin` = https://github.com/THARUN7474/gate-hub (branch `main`).
Not in git (see `.gitignore`): `.env`, `*.sqlite` databases, `backups/` (DB snapshots + old ZIPs in
`backups/zips/`), `data/raw/` PDFs, OCR cache, generated exports. Keep `data/gate_cse.sqlite` backed
up yourself (`backup.cmd`) - it holds your reviews and is not on GitHub.

## Cleanup (5 Nov 2026, second commit)

Removed because they had already run and nothing uses them any more (all recoverable from git commit `71d0558`):
`scripts/agent_classify_2026_cs1.py`, `apply_agent_classifications.py`, `build_workbook.py`,
`curate_concepts_2026_cs1.py`, `keypdf_to_csv_2026_cs1.py`, `semantic_review_2026_cs1.py`,
`import_candidate_labels.py`; the old UI screenshots (`docs/screenshots/`, v6-v9, earlier data);
agent session logs (`docs/handoff/session-logs/`); `docs/RECONCILIATION.md` (for a draft pack no longer present).
Local only (never in git): the candidate DB was retired to `backups/gate_cse.candidate.retired-20261105.sqlite`;
stale chat batches and exports were deleted and the exports regenerated from the live DB; caches cleared.
`scripts/ui_apptest.py`, `scripts/ui_browser_test.py` and `tests/test_prompt_v2.py` now read a copy of the live DB.
Tests after cleanup: 223 passed, AppTest all PASS, `validate` 10/10.

## GA syllabus PDF added (5 Nov 2026)

`data/raw/syllabus/GA_GATE2027_Syllabus.pdf` (sha256 `3708769a...b7603`) is now recorded in `taxonomy.yaml` (`ga_source_pdf`, `ga_source_sha256`) next to the CS PDF (path corrected from the old `corpus/raw/...`). The GA section text was already verbatim from this PDF - verified by `tests/test_syllabus_sources.py` - so no topic or label changed. Four syllabus items had no concept and were added (official wording): GA.VA.SEQ Narrative sequencing, GA.QA.GEOM Mensuration and geometry, GA.AA.ANALOGY Analogy, GA.SA.TRANSFORM Transformation of shapes. Loaded into the live DB (backup `backups/gate_cse.20261105-035940.sqlite`): 112 concepts (was 108), 49 topics, 11 sections; classifications unchanged; `validate` 10/10.

## Full coverage + app redesign (5 Nov 2026)

- **1,885 / 1,885 classified.** The 18 unclassified questions were historical software engineering (pre-2016 syllabus). Owner asked for them to be classified: `taxonomy.yaml` gained a section `LEGACY` ("Out of 2027 syllabus (historical)", provenance `historical`, text from the pre-2016 CS&IT syllabus) with topic `LEGACY.SE` and 5 concepts; the 18 got AI-review labels there (`exports/ai_review/legacy-se.decisions.json`, status suggested). Backup before: `backups/gate_cse.20261105-042729.sqlite`. Live now: 1,510 suggested + 374 flagged + 1 verified; `validate` 10/10.
- **Your first verification**: 2011-S1 Q01 verified by `owner` as CD.LEX (all five checks pass).
- **App**: every screen has an icon, title and one-line purpose; long explanations sit in collapsed "How to read this page" toggles; Pipeline Status has score cards, four progress bars and a new **Review progress per paper** table (`analyze.paper_review_table`). Theme in `.streamlit/config.toml` (Inter).
- **Bug fixed**: opening LLM Classify froze the browser - the labels "Input $/M tokens" / "Output $/M tokens" were parsed as LaTeX (pre-existing; found by bisecting in a real browser). Labels now say USD; a test forbids bare `$`.
- Tests: 230 passed; AppTest all PASS.

## App v13: stages, second opinions, clearer review (5 Nov 2026)

- **Pipeline Status** is now six stage cards in work order. Each has a bar, a "what to do" note and a button that opens the right screen with the filters set: extraction issues (165) -> Review Workspace filtered to them; AI review -> new Second Opinions screen; decision models -> LLM Classify tab; benchmark -> Review Workspace on the 120 sample; human-verified -> priority order.
- **Second Opinions** (new screen): all 198 AI-review opinions (139 agree, 31 flag, 28 correct) beside the live label, filterable by verdict/paper/"different topic", click a row to review. Decision-model answers appear in their own tab once run.
- **Review Workspace**: filters for extraction issues and AI-reviewed; per-question status strip (extraction / machine label / AI review / decision models / human review, each with where the fact comes from); numbered sections 1 Original source, 2 Machine label, 3 Second opinions, 4 Your decision; a step-by-step guide of what a human does and what changes.
- **Full names** in every subject/topic dropdown; codes stay the filter values.
- **Question Browser** lists every match (the old 500-row cap is gone) and breaks results down by subject and status.
- **Analysis Matrix** has Marks and Questions tabs (1,885 questions = 2,900 marks = 29 papers x 65 / x 100), each with a column-totals row and grand total.
- **Glossary**: the blank Sections table is fixed (one very long text column broke the grid); syllabus PDF paths and checksum check shown.
- **Decision models**: code and `.env` settings were already in place (OpenAI `/v1/decisions` gpt-6-luna, TypeSafe Jev jev-1.14.0; docs checked 4-5 Nov). LLM Classify now shows their status, a benchmark cost estimate and the exact commands. Still off until you add a key and set `DECISIONS_ENABLED=1`.
- Helpers: `src/analytics/opinions.py`; `search_questions(limit=None, extraction_issue=...)`; matrix totals in `links.py`.
- Tests: 234 passed; AppTest all PASS (new checks: extraction filter, stage buttons, all 1,885 listed); every screen checked in a real browser on a copy of the DB.

- **Statuses explained** (5 Nov): suggested / flagged / verified / unclassified + related terms (classified, awaiting your decision, extraction issue, AI review, benchmark gold) - one shared text with live counts, shown as a "What the statuses mean" toggle wherever statuses appear and in full on the Glossary; dropdowns show "status (short meaning)".
- **Engine & Pipeline screen** (5 Nov): Graphviz diagrams from live counts - the end-to-end pipeline coloured by state (you are at benchmark gold 0/120), what one question record holds, a live diagram for any question, the syllabus tree per subject, the label lifecycle. States precisely how labels were made: 1,796 first-pass labels by Claude via chat batches; AI review = parallel second opinion on 198 (created the 18 SE labels, corrected 5); FreeLLMAPI proposals and decision models not run, and only ever proposals; humans alone verify. Includes a live 15-stage CSE checklist and a full "another branch (ECE)" guide: collect PDFs + EC syllabus, own DB, taxonomy-ec.yaml, papers-ec.yaml (`papers-load --manifest`), one-time change to make the fixed `gate-cs-2027` taxonomy version configurable, load/validate, classify, benchmark, analyse. Helpers: `src/analytics/engine.py`. Tests 236.

- **AI review v2 + question type** (6 Nov): new prompt `prompts/ai_review_v2.md` (type, solution, reasons, rejected alternatives, key check). `scripts/ai_review.py export --next 20` / `progress`; v2 only flags labels, never changes them. Question type is now visible per source (extractor / AI / you) and is part of the human decision. Pilot: 20 questions of 2011 CS-1 reviewed (12 agree, 4 correct, 4 flag). Held back: 165 extraction issues (until fixed), 110 benchmark questions (until your gold review), your 1 verified question. Tests 238.

- **Reset + gold set 385** (6 Nov): at your request all human verification was withdrawn (only 2011-S1-Q01 was verified; its label is kept as a suggestion, the change is audited) and the gold set was topped up from 120 to 385 (stratified). The AI review v2 queue now takes the whole gold set first; all 385 are reviewed (295 agree, 18 correct, 72 flag - mostly figure/extraction problems), shown in the Review Workspace with "Why the AI thinks so". Verifying a gold question records your label as gold and as human-verified. Data issue found: 2013 S1-S4 are four shuffled sets of the same exam (60/65 shared texts) - decision pending.

- **Duplicate papers** (6 Nov): GATE 2013 CS was one exam in four shuffled sets; all four are loaded. Kept, but: 1,885 questions = 1,690 unique + 195 copies; every screen with totals says so; reviews/classification run on unique questions and copies follow their original (verify the original -> copies get the same label, audited). Gold set = 385 originals. Analysis Matrix has a 'Count each question once' switch. Rules: About the Data / Glossary -> Special cases. Tests 243.
