# Reconciliation of this pack against the actual v7 repository (4 Nov 2026)

> **Superseded 4 Nov 2026 (v9/v10):** rows below about "28 papers unclassified / 1,820 questions" describe the
> pre-v9 state. Current state: 1,867 of 1,885 questions classified (topic-level first pass, 0 verified),
> 18 software-engineering questions unclassified (taxonomy gap). See docs/00_STATUS.md.

The four drafts in this folder are kept exactly as supplied. Each was checked against the code, the live database
(`data/gate_cse.sqlite`, 2 papers) and the staging database (`data/gate_cse.candidate.sqlite`, 29 papers). The reconciled, maintained
versions are docs/17_CLASSIFICATION_PROVENANCE.md, 18_HUMAN_REVIEW_AND_SCORING.md, 19_LOCAL_RESTART_5_STEPS.md and 20_CHAT_ASSISTED_CLASSIFICATION.md.

| Draft | Claim | Finding | Where now |
| --- | --- | --- | --- |
| 16 | 65 records by `scripts/agent_classify_2026_cs1.py`, `provider=agent-analysis`, `prompt_version=agent-v1`, `model=claude-agent-manual-v1` | **True** (classification_runs id 1; 65 rows) | docs/17 |
| 16 | a second agent pass re-examined all 65 | **True**: run id 2 `curation+audit-review`, `scripts/curate_concepts_2026_cs1.py`; 2 primaries changed as suggestions | docs/17 |
| 16 | 65 unreviewed, 28 papers unclassified | **True**: 0 verified, 0 rubrics; 1,820 questions / 28 papers have no classification | docs/17, docs/00 |
| 16 | chat-assisted suggestions keep question_id ... `reviewer_type`, `status=suggested`, `reviewed_at=null`; ambiguity -> `needs_review` | **Implemented** without a migration (field mapping in docs/17; `needs_review` -> status `flagged` + question flag) | docs/20 |
| 17 | review UI shows PDF crop, text, options, paper/number, marks, type, key + provenance, subject/topic/concepts, secondary concepts, what-it-tests, prerequisites, confidence, evidence | **Was partly true; gaps fixed**: added secondary topics, editable what-it-tests, extraction corrections (text/options/marks/type), audit history | docs/18 |
| 17 | correct marks/type/key alignment | marks/type: **added**. Key alignment: **not editable** (keys only come from official files); recorded via the rubric's key check + note | docs/18 "Not implemented" |
| 17 | every change = review_event with old, new, reason, reviewer, UTC time, taxonomy version | **True** after this update (taxonomy version added to classification corrections' note; extraction events carry no taxonomy) | docs/18 |
| 17 | five-check rubric, failed fidelity/primary blocks approval, scopes extraction/classification/key | **Implemented and enforced in code** (also in batch approval and CLI) | docs/18 |
| 17 | gold-set metrics: topic accuracy, concept micro-F1, disagreement | **Not implemented** (review coverage is; accuracy vs verified via `classify-compare`) | docs/18 |
| 18 | `./backup.cmd`, `./doctor.cmd`, `./promote.cmd` then type YES, `./start.cmd` | **True** as written; `promote.cmd` previews first and only applies on `YES` | docs/19 |
| 18 | "live DB has only two papers until promotion" | **True** (checked 4 Nov 2026) | docs/19, README |
| 18 | "commands have not been executed" | They have now been executed on this machine (except the YES/`--yes` promotion) | docs/19 |
| 19 | "inspect current git status" | the project is **not a git repository**; changes are listed in the session report instead | - |
| 19 | reconcile Q21/Q37/Q48 + Q59 with exact diffs and source image | **Done**; Q21/37/48 identical to the PDF text layer; Q59 still 80 chars short in both DBs (fix prepared, not applied); auditor's 52/10/3 not reproducible without their file | docs/handoff/extraction-discrepancies.md |
