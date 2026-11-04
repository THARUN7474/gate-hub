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
