# Human review and scoring (as implemented, 4 Nov 2026)

Reconciled from the owner's draft `docs/GATE_v7_docs_update/17_HUMAN_REVIEW_AND_SCORING.md`. Everything below exists in the app and is
covered by tests (`tests/test_review_rubric.py`, `scripts/ui_browser_test.py`). What is NOT implemented is listed at the end.

## The Review Workspace, one question at a time

**Left column**
- the original PDF region of the question, rendered from the source PDF (the truth; trust it over the text)
- an OCR notice for scanned papers
- the extracted question text and options
- the official key with its provenance, or "no official key loaded" (never guessed)
- the extraction flag, if any (for example Q21's notation note)
- **Correct the extraction**: edit the question text, any option, marks or type, with a reason. Each change is one audit event. A corrected
  question is protected: re-loading the PDF never overwrites it.

**Right column**
- section, primary topic, confidence (self-reported), status, what it tests, concepts, prerequisites
- dropdowns to correct section / primary topic / concepts, **secondary topics** (tags only: never counted in marks) and the
  what-it-tests sentence
- **Review checks** (the five-point rubric below)
- "Approved so far": classification / extraction / official key, kept separate
- buttons: Verify as-is, Flag, **Save without verifying**, Verify with correction, Approve & next, Skip to next pending
  (keys: Ctrl+Enter, Alt+V, Alt+X, Alt+N)

**Below both**: **Audit history** - every change to this question, oldest first: when (UTC), field, before, after, reviewer, note.

## The rubric (a reviewer's record - not a GATE score, not model confidence)

| Check | fail (0) | pass (1) |
| --- | --- | --- |
| Source fidelity | text/options/diagram/notation wrong or insufficient | checked against the original and acceptable |
| Answer/key provenance | key absent but claimed, misaligned or uncertain | official key correctly aligned, or explicitly not available |
| Primary section/topic | primary mapping wrong or ambiguous | correct |
| Concept depth | critical concepts missing/wrong | accurate enough |
| Explanation/evidence | unsupported or wrong tested-skill | supports the mapping |

`review_quality_score` = 0-5, stored as a `review_events` row (`field=rubric`) with the taxonomy version.

**Rules enforced in code (not just on screen):**
- `verified` needs a saved rubric in which **Source fidelity** and **Primary topic** both pass. Without it, Verify is refused and nothing is
  written. This applies to the buttons, the keyboard shortcuts, the Approve Queue and the CLI alike.
- On verification, the scope is recorded separately: `extraction_verified` (from Source fidelity), `key_verified` (only if an official key
  is loaded and the key check passed); a paper without a key stays `key_status = missing` - classification-only approval, never a key claim.
- A correction is not a verification. "Save without verifying" stores corrections and the rubric with status unchanged.
- A human-corrected row (`provenance=validated`) and a verified row are never replaced by a classifier rerun, `--reclassify`, or a chat import.
- No code path sets `verified` for AI output. 0 of 65 are verified today.

## Approve Queue (batch)
Same rule: only questions that already have a saved passing rubric are approved; the rest are refused and counted on screen
("NOT approved because they have no passing review rubric"). Never bulk-verify on the strength of an AI suggestion.

## Priority order for reviewing (recommended)
1. Flagged extraction records: 2026 CS-1 Q21, Q37, Q48 (notation), 2025 CS-1 Q59 (text cut short until repaired - see
   `docs/handoff/extraction-discrepancies.md`).
2. Figure/formula/OCR-heavy questions (scanned years 2011, 2014, 2015, 2017, 2019, 2020, 2021).
3. Low-confidence, flagged or GA/CS-block-conflicting suggestions.
4. A stratified sample per section/year, then the rest of 2026 CS-1.
5. Bulk archive review once the pilot quality is acceptable.

## Acceptance workflow (per question)
1. Review Workspace -> Paper -> Show "suggestion awaiting my decision" -> pick the question.
2. Look at the original region **before** reading the suggestion.
3. Check number, diagram, text/options, marks, type and the official key; fix the extraction if needed.
4. Choose the correct section/topic/concepts/secondary topics; write a note for anything uncertain.
5. Answer the five checks. Verify only if Source fidelity and Primary topic pass; otherwise Flag or Save without verifying.
6. Reload the page and reopen the question: status, rubric and audit history persist.
7. After a batch: `python -m src.cli validate` and `python -m src.cli review-status`.

## Measuring quality (numerators and denominators)
- `python -m src.cli review-status` -> questions, classified, unclassified, verified, with_rubric, by status.
  `verified / classified` is **review coverage**, not model accuracy.
- Accuracy needs a human-checked gold set: once some questions are verified, `classify-compare` reports
  `topic_agreement_vs_verified` for an API provider. Concept micro-F1 and double-review disagreement are **not implemented yet**.

## Not implemented (deliberately, to avoid schema changes)
- Editing the official answer key in the UI (keys come only from official key files; a misaligned key is recorded via the rubric and a note).
- Double review / adjudication tracking.
- Per-field "uncertainty" flags beyond the free-text note.
