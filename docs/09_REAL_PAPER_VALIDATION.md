# Real-paper validation: GATE 2026 CS-1 (3 Nov 2026)

> **Historical record (3 Nov 2026).** Kept for provenance; it is not the current state. Current state: `docs/CURRENT_STATUS.md`.

The first real paper run through the pipeline. Inputs supplied by the owner
(stored in `data/raw/`):

| File | Role | sha256 |
|---|---|---|
| `data/raw/papers/2026/CS1_2026.pdf` (named `CS1.pdf` when this was written) | GATE 2026 CS-1 question paper, 46 pages, IIT Guwahati | `ccfa649c...09ed96` |
| `data/raw/keys/2026/CS1_Keys_2026.pdf` (was `CS1_answer_key.pdf`) | Official answer key (65 rows, Session 3) | `7386d012...b2f28` |
| `data/raw/keys/2026/CS1_keys_2026.csv` (was `CS1_key.csv`) | Key transcription into pipeline CSV format (generated, cross-checked) | - |
| `data/raw/syllabus/CS_GATE2027_Syllabus.pdf` | Official 2027 CS syllabus | `81b23f40...70bc0` |

The supplied syllabus PDF is **byte-identical** (sha256 match) to the official
2027 CS syllabus that `taxonomy.yaml` was transcribed from.

## What the pipeline did, and how each step was verified

1. **Ingest + extract** (`src/cli ingest`, `src/cli extract`): 65 questions,
   100.0 marks, reconciled against expected 65/100. Zero NULL marks/type.
   The real paper needed the predicted pattern tuning (see below).
2. **Key import**: the key PDF table was transcribed to CSV programmatically
   (`scripts/keypdf_to_csv_2026_cs1.py`, (removed 5 Nov 2026 after use; recoverable from git history, commit 71d0558)) and imported through the tested CSV
   path: 65/65 imported, 0 unmatched. Before import, every key row was
   cross-checked against extraction: **question type matches for all 65**
   (MSQ reads as MCQ pre-import by design), **marks match for all 65**, and
   the extracted NAT set is exactly the key's NAT set
   {32,33,34,35,57,58,59,60,61,62,63,64,65}.
3. **Classification**: all 65 questions classified against the 2027 taxonomy
   by agent analysis (`scripts/agent_classify_2026_cs1.py` (removed 5 Nov 2026 after use; recoverable from git history, commit 71d0558),
   provider=`agent-analysis`, prompt_version=`agent-v1`, model=
   `claude-agent-manual-v1`). **This is not a paid LLM API run and not the
   MockProvider; it is an independent agent pass.** Every row is
   provenance=inferred, status=suggested: pending human verification in the
   Review Workspace. Section totals (marks): GA 15, ALGO 12, EM 11, PDS 11,
   OS 10, CN 8, DL 8, COA 7, TOC 6, CD 6, DB 6 = 100.
4. **Analyze / export / validate**: all 6 validation checks PASS (no
   duplicates, no orphans, no unexplained NULLs, taxonomy IDs valid, paper
   reconciled, matrix totals = paper totals). `docs/analysis/ANALYSIS.md` and `exports/`
   regenerated from the real database.
5. **App**: all 5 Streamlit screens run against the real database (AppTest:
   Papers 1, Questions 65, With keys 65, Classified 65, Verified 0, Pending
   review 65). No SYNTHETIC banner, correctly: this paper's document role is
   `official`. Question source previews visually inspected (e.g. Q7 figure,
   Q44): each shows exactly its own question region. NOTE (v3): stored crop
   PNGs were replaced by stored PDF region references + on-demand rendering;
   see docs/10_REGION_STORAGE.md.
6. **Test suite**: 19/19 pytest tests pass after the parser tuning.

## Parser tuning the real paper required (src/extraction/extract.py)

Exactly the Day 1-2 spike the docs predicted:

- Real papers print options as a label-only line `(A)` followed by content on
  the next line(s). Options are now accumulated: label-only lines open an
  option, following lines append to it (multi-line text, stacked fractions).
- Option labels are only accepted in sequence (A then B then C then D), so a
  bare "A" inside a stem cannot become a phantom option.
- `Q.1 - Q.5 Carry ONE mark Each` section headers matched the question-start
  pattern; they are now excluded from question starts (they remain marks
  headers).
- Running headers/footers (`Computer Science & Information Technology (CS1)`,
  `Organizing Institute: IIT Guwahati`, `Page N of 46`,
  `General Aptitude (GA)`) are filtered out of question bodies.

## Honest limits of this run

- Classification is **agent judgment, unverified by a human**. Judgment-call
  topic assignments to review first: Q23, Q24, Q39, Q47, Q51, Q54, Q55, Q56,
  Q57, Q59, Q65.
- Fractions in option *text* merge lines (Q10 option C renders as `7 18` for
  7/18). The on-demand PDF preview always shows the true layout; use it for anything
  mathematical.
- Q2/Q7 options are figures: option text is empty, see the on-demand PDF preview.
- Ran on SQLite (documented dev fallback). Postgres re-verification of this
  real dataset is a Day-1 task (`alembic upgrade head` + re-run scripts).
- One paper, one session. No multi-year corpus claims.

## Second-pass classification re-review (3 Nov 2026)

Every one of the 65 mappings was re-examined against the taxonomy syllabus
text in a second pass (same reviewer: the agent; still NOT human-verified).

- Confidence adjustments: Q39 (0.75 -> 0.80, recursion is the mechanism, the
  linked-list traversal is the tested concept), Q57 (0.90 -> 0.95, "matching"
  is verbatim in the DM syllabus text).
- Re-affirmed judgment calls with documented alternatives, recorded in each
  row's what_it_tests: Q23, Q24, Q47, Q51, Q54, Q55 (kept ALGO.GRAPH, EM.DM
  alternative documented), Q56, Q59, Q65, Q10, Q12.
- No section/topic assignment changed in the second pass.

Per-row data caveats (figures, flattened fractions) are now marked on the
affected rows of the workbook's Question Bank sheet (orange DATA CAVEATS
column), not only here: Q2 (options are figures), Q7/Q8/Q37/Q42/Q53/Q60
(figures/tables in stem), Q10 (all four options are flattened fractions).

## v4 addendum (independent-audit response, this build)

- Rebuilt from scratch with the v4 pipeline on offline SQLite: ingest ->
  extract (regions, no stored crops) -> keys -> agent classification ->
  concept curation. 65 questions, 100.0 marks, reconciled=true, 65/65 keys.
- **Drift-check** (new): re-extraction vs stored rows = 65/65 exact, 0
  normalized-only, 0 changed, 0 missing **as run on this build (PyMuPDF
  1.28.2, now pinned in requirements.txt)**. Extraction output varies with the
  PDF-library version, so this figure is environment-specific, not a universal
  invariant: a later independent audit on a different environment measured
  52 exact / 10 normalized / 3 changed (Q21, Q37, Q48). Those three questions
  were visually checked against the PDF regions (content faithful; notation
  flattening only) and are now flagged needs_review - see docs/12. The 9
  string differences the earlier auditor saw were against the v2 package
  (stored texts predating the v3 extraction fixes); persist_records compares
  before upsert and refuses to silently overwrite drifted text.
- **Empty figure options**: Q2's four options are figures; the question is now
  auto-flagged needs_review ("empty option content...") and a validation check
  enforces the flag. Fractions/exponents remain flattened in TEXT (known
  limitation): the on-demand PDF region render is the source of truth for
  those questions - verify them in the Review Workspace.
- **Concept layer**: all 65 questions carry curated concept_ids;
  prerequisite_ids derive mechanically from 29 curated edges. Audit-requested
  microtopics applied (Q24 hashing, Q39 linked-list+recursion, Q47 vertex
  cover, Q51 closure + id rename, Q54 cache secondary, Q55 bipartite, Q56
  CIDR, Q65 primary corrected to DB.REL/keys). All remain
  provenance=inferred / status=suggested; human verification is still 0/65.
- 45/45 pytest; `validate` CLI: 10/10 checks pass; app booted headless
  against this database (HTTP 200).
