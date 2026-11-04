# 12 - Response to the v4 independent audit (this build, v5)

> **Historical record (v5 audit; the exports/semantic_review_2026_cs1.* files it mentions were stale generated output and were removed 5 Nov 2026).** Kept for provenance; it is not the current state. Current state: `docs/CURRENT_STATUS.md`.

Scope: glossary/docs page request + the user's pasted v4 audit. Everything below
was run locally on this build; what could not be run here is marked UNVERIFIED.

## 1. Extraction drift (P0)

- Re-ran `python -m src.cli drift-check GATE-CS-2026-S1 data/raw/papers/2026/CS1.pdf`
  on the bundled DB: **65 exact / 0 normalized / 0 changed / 0 missing**
  (Python 3.10.12, PyMuPDF 1.28.2, Linux x86-64). This reproduces the v4 doc's
  claim *in this environment*.
- The auditor's 52/10/3 result does **not** reproduce here. Extraction output
  depends on the PyMuPDF version, so "different PyMuPDF in the auditor's
  environment" is a plausible **hypothesis, not proven**. The tested version is
  now pinned in requirements.txt, and docs/09 no longer claims an
  environment-independent 65/65.
- Q21, Q37, Q48 (the auditor's three changed records): stored text and options
  compared against the rendered PDF regions, 2026-11-03. All content is
  faithful. Real, specific limitations: Q21 option A's overline spans the whole
  expression in the PDF but flattens ambiguously in text; Q37's next-state
  table loses its structure in text (values preserved in order); Q48 relies on
  per-literal combining overbars. All three are now `needs_review` with precise
  reasons; the PDF region render stays the source of truth. Originals were not
  modified - only flags were added.
- Auto-flagging on real drift already exists in `persist_records` (keeps stored
  text, flags, reports) and is covered by tests/test_drift.py.

## 2. PostgreSQL 17 + pgvector (P0) - UNVERIFIED

No Docker in this build environment, so the pg17/pgvector migrations and E2E
were **not executed here** and remain unverified. v4's PostgreSQL notes
referenced pg16; nothing in this build claims pg17 works. SQLite results above
say nothing about PostgreSQL.

## 3. UI interaction (P1)

- **Row selection -> detail (done)**: the Question Browser table now supports
  single-row selection (Streamlit dataframe `on_select`); selecting a row
  opens that exact question in the Review Workspace (source region, key,
  editable classification). Verified end-to-end in a real browser: clicking
  the GATE-CS-2025-S1-Q01 row lands on that question in the Review Workspace.
  The dropdown jump is kept as an explicitly labelled fallback.
- **Verify / Flag / Save-correction persistence (done, AppTest)**:
  scripts/ui_apptest.py drives the app in-process via Streamlit's AppTest
  harness against a scratch DB copy: select GATE-CS-2026-S1-Q03, Flag ->
  status 'flagged' persisted; Verify -> 'verified'; Correct topic -> DL.NUM +
  Save correction -> primary_topic_id persisted, and every change wrote a
  review_events row. This is AppTest-level, not browser-level clicking:
  headless Chrome in this environment cannot open Streamlit's select-option
  dropdowns (automation limitation only).
- Matrix cells stay non-clickable (drilldown selectors remain); cell-click is
  not supported by the table widget in this Streamlit version.

## 4. Stratified semantic review (P1)

exports/semantic_review_2026_cs1.md: 24 questions across graph algorithms, OS
memory, DBMS, math and diagram/table questions, judged against actual content.
24/24 consistent; 2 boundary notes (Q11, Q55). Provenance: non-human AI review,
statuses unchanged, no bulk verification. A keyword-screening pass
(exports/semantic_review_2026_cs1.csv) is kept as a mechanical artifact only -
it is not a correctness review.

## 5. Second official paper, different year/layout (P1)

GATE **2025 CS1** (IIT Roorkee layout; paper via the official IITG mirror
`gate2026.iitg.ac.in/doc/download/2025/CS12025.pdf`, key via
`gate2025.iitr.ac.in/doc/2025/2025_Key/CS1_Keys.pdf`):
ingest -> extract -> key import -> drift-check -> validate all ran on this build.

- 65 questions extracted and reconciled; 65/65 keys matched and imported.
- Drift-check: 65 exact / 0 changed. All 10 validation checks PASS.
- **New extraction defect found and handled**: Q59 (a NAT with a state table)
  was typed MCQ with the table misread as 4 phantom options. q_type corrected
  to NAT from the official final key, phantom options removed (source intact in
  the region render), question flagged needs_review.
- Classification for 2025 is deliberately absent: no live LLM provider is
  authorized (audit P2), and mock labels would be fabrication. 2025 questions
  appear as unclassified/pending review.
- New generic key parser `scripts/keypdf_to_csv.py` handles the tabular
  official key layout (2024/2025/2026 family) and fails loudly on anything
  else; the paper-specific 2026 helper is superseded for that layout family.

## 6. Test count (44+1 vs 45) and v5 regression tests

tests/test_ui_smoke.py uses `pytest.importorskip("streamlit")`: it **skips**
when streamlit is not installed (the auditor's environment) and passes when it
is (this one). 44 passed + 1 skipped vs 45 passed is an environment difference,
not a product failure. Current suite: **54 passed** - v5 adds:
tests/test_glossary.py (glossary expansions, SORT scope, deprecated ids,
provenance, escaping), tests/test_keypdf_parser.py (real bundled 2025 key +
synthetic NAT range streams), tests/test_repair_nat.py (NAT repair helper:
corrects, flags, logs, idempotent).

## 8. Reproducible repairs and analytics honesty (v5)

- scripts/repair_nat_type_options.py: key-driven repair for the Q59 defect
  class (key says NAT but extraction typed otherwise / phantom options).
  Idempotent; logs review_events; covered by tests/test_repair_nat.py. The
  manual Q59 repair from section 5 is logged in review_events and the helper
  confirms the whole DB consistent (35 NAT questions already clean).
- Analysis screens state that only classified questions are included and that
  ingested-but-unclassified papers (2025 CS1) are excluded, so 2026 totals are
  never presented as full coverage of both papers. The Question Browser does
  show the 2025 rows (with empty classification columns) - deliberately, so
  the pending work is visible.
- Mobile code explanations now render as wrapping text lists (full names never
  clipped), not a clipped grid.

## 7. Glossary & Syllabus (user request alongside the audit)

New "Glossary & Syllabus" screen + hover tooltips / tap expanders on every
screen; built from taxonomy.yaml at runtime with official vs inferred
provenance preserved. See the report to main for screenshots.

## Not done here

- PostgreSQL 17 + pgvector E2E (no Docker - see section 2).
- Live LLM provider runs (audit P2; requires chosen model + spend limit +
  held-out human-reviewed data first - none authorized).
- Clickable matrix cells (widget limitation, section 3).
