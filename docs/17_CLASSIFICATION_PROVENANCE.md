# Where the 65 GATE 2026 CS-1 classifications came from

Checked on 4 Nov 2026 directly against the live database (`data/gate_cse.sqlite`), the staging database and the two scripts below.
This replaces the v4-era description in `docs/GATE_v7_docs_update/16_CLASSIFICATION_PROVENANCE.md` (the owner's draft is kept unchanged;
where it differs from the facts, this page says so).

## What the database says

| Table | Value (exactly as stored) |
| --- | --- |
| `classification_runs` id 1 | `provider=agent-analysis`, `model=claude-agent-manual-v1`, `prompt_version=agent-v1`, started 2026-11-03 00:20 UTC, stats note: *"Agent read each extracted question and classified against taxonomy gate-cs-2027. NOT an LLM API integration run; suggestions pending human verification."*, classified 65 |
| `classification_runs` id 2 | `provider=curation+audit-review`, `model=curated-concepts-v1`, `prompt_version=v1`, stats: curated 65, primary_corrections 2, note *"concept-level curation + owner-relayed audit corrections; not human verification"* |
| `classifications` | **65 rows**, all `status=suggested`, `provenance=inferred`, `model=claude-agent-manual-v1`, `prompt_version=agent-v1`, `taxonomy_version=gate-cs-2027`, self-assigned confidence 0.80-0.98 |
| `review_events` | 3 rows: Q51 `TOC.PUMP -> TOC.RCFL` and Q65 `DB.NF -> DB.REL` (reviewer `owner-relayed-audit`, note *"audit correction applied as SUGGESTION; human verification pending"*), and the 2025 Q59 type repair (`repair-script-v5`) |
| Human verifications | **0**. No row has `status=verified`; no review rubric has been saved |

The same 65 rows are in the 29-paper staging database.

**Superseded 4 Nov 2026 (v9):** all other papers now carry a topic-level first pass -
1,867 of 1,885 questions classified (0 human-verified), 18 software-engineering questions left
unclassified (taxonomy gap). See docs/handoff/classification-audit-v2.md and docs/00_STATUS.md.
The sections below remain the accurate history of the FIRST 65 rows only.

## How they were made (the source scripts)

1. **`scripts/agent_classify_2026_cs1.py`** - an earlier *coding agent* (Claude, working in a coding session) read each extracted
   2026 CS-1 question and typed a hand-written table into this script: per question a section, primary topic, a confidence it chose
   itself, and a one-line "what it tests". Running the script writes those 65 rows with `provenance=inferred`, `status=suggested`.
   It makes **no API call** and is **not** the `MockProvider` keyword stub (the stub exists for offline tests only and never produced
   these rows).
2. **`scripts/curate_concepts_2026_cs1.py`** - a second agent pass: added `concept_ids` for all 65 questions, derived
   `prerequisite_ids` from the taxonomy's concept edges, and applied two corrections relayed from an outside audit (Q51, Q65) **as
   suggestions**, each logged as a review event. Status stayed `suggested`.

## Why they are still unverified suggestions

- They are one agent's judgement, re-checked by another agent pass. That is not independent human validation.
- The confidence numbers were chosen by the agent; they are not calibrated and are not accuracy.
- Verification needs a named human to compare each question with its original PDF region and save a passing review rubric
  (see `docs/18_HUMAN_REVIEW_AND_SCORING.md`). The software now refuses to verify anything without that.

## Differences from the owner's draft (16_CLASSIFICATION_PROVENANCE.md)

- Draft: "`provider=agent-analysis`, `prompt_version=agent-v1`, `model=claude-agent-manual-v1`" - **confirmed** in the v7 database.
- Draft: "a second agent pass re-examined all 65 labels" - **confirmed** as run 2 (`curate_concepts_2026_cs1.py`); it changed 2 primaries.
- Draft: "65 remain unreviewed, 28 more papers unclassified" - **confirmed** (0 verified; 28 papers / 1,820 questions without any classification).
- Draft: the v4 status `needs_review` for ambiguous items. In v7 the statuses are `suggested`, `flagged`, `verified`; an import that asks
  for review becomes `flagged` and the question gets `needs_review=1` with the reason.
- Draft field list for chat suggestions (`reviewer_type`, `reviewed_at`, ...): implemented with existing columns, no migration:
  `classification_runs.provider=chat-assisted`, `classifications.model` = the chat model you name, `prompt_version=chat-v1`,
  `raw_response` = the exact item the chat returned plus its batch id, `status=suggested|flagged`, `provenance=inferred`. "Reviewed at"
  is the `created_at` of the human's review events.

## Status words used everywhere

| Word | Meaning |
| --- | --- |
| `suggested` | a machine or agent label; no human approval |
| `flagged` | a known problem or a request for review (invalid id, low confidence, contradicts the paper's GA/CS block, chat asked for review, or a reviewer flagged it) |
| human-corrected | `provenance=validated` while status is not yet `verified`: a human chose the value; never overwritten by any rerun or import |
| `verified` | a named human saved a passing review rubric and approved it (`provenance=validated`) |
| `confidence` | self-reported by the model/agent; never reported as accuracy |

Official answer keys are a separate thing: they come from the official key files and are never produced by a model.
