# Response to the independent audit (3 Nov 2026, v4)

An independent audit (relayed by the owner) extracted the v2 ZIP, ran the
tests, re-extracted the paper, reviewed 12 classifications and listed 7
priority fixes. It inspected **v2**; v3 had already replaced stored image
crops with source-PDF regions + on-demand rendering, so crop-related findings
were stale. This document is the per-finding disposition for v4. Nothing in
the audit was taken on faith: every claim was re-verified against the code,
the database and the source PDFs before acting.

## Verified-true findings and what changed

1. **Corrupted taxonomy topic names (root cause of several review notes).**
   TRUE, and worse than the audit stated: 13 of 49 topic names were split by
   unquoted multi-part YAML (`ALGO.SORT` was just "Searching", hashing/sorting
   lost; `PDS.LIN` just "Arrays"; `CN.ROUTE` just "Routing"; `DB.NF` just
   "Integrity constraints"...). FIXED: taxonomy.yaml rewritten with quoted
   full syllabus names; `validate_taxonomy` now REJECTS stray keys and
   non-string names (regression test). This directly addresses priority fix 2.
2. **No concept-level data / prerequisite edges.** TRUE: all `concept_ids`
   were empty, 0 edges. FIXED: 108 concept nodes under topics (from the
   verbatim syllabus text, provenance=inferred) + 29 curated prerequisite
   edges with per-edge source notes ("curated from standard CS curriculum
   ordering; unverified curation"). All 65 questions now carry curated
   concept_ids (scripts/curate_concepts_2026_cs1.py is the curation record)
   and prerequisite_ids derived mechanically from the edge set. Concepts and
   edges are exported (concepts.csv, prerequisite_edges.csv) and shown in the
   workbook and the Review Workspace. They are marked curation, not
   verification: everything remains provenance=inferred, status=suggested.
3. **Q65 primary topic.** AGREED with the audit: superkeys/candidate keys are
   relational-model keys content, not integrity constraints/normal forms.
   CORRECTED: primary DB.NF -> DB.REL with concept DB.REL.KEYS, logged in
   review_events (reviewer "owner-relayed-audit"). Keys are now a distinct
   concept from FDs/normal forms (priority fix 1).
4. **Q51 misleading id.** AGREED: node renamed TOC.PUMP -> TOC.RCFL; the old
   id is kept as a deprecated node so historical rows stay resolvable, and a
   validation check fails if any active classification points at a deprecated
   node.
5. **Microtopics requested by the audit** (Q24 hashing/linear probing, Q39
   linked-list + recursion, Q47 vertex cover/graph theory, Q54 cache
   secondary, Q55 bipartite/graph colouring, Q56 CIDR/subnetting): all added
   as concept_ids on those questions. Vertex cover is not verbatim in the
   syllabus; its concept (ALGO.GRAPH.VC) is explicitly named as a curation
   extension.
6. **Count reconciliation misses content drift; 9 stored strings differed
   from re-extraction (Q13,Q20,Q21,Q32,Q36,Q38,Q46,Q50,Q53).** TRUE for the
   v2 package the auditor ran (its stored texts predate the v3 extraction
   fixes). FIXED structurally: new src/validation/drift.py compares
   re-extraction against stored rows at exact and Unicode-normalized
   (glyph/spacing) levels; `persist_records` now compares BEFORE upserting and
   never silently overwrites differing stored text (keeps it, flags
   needs_review, counts drift); new `drift-check` CLI command. On this v4
   rebuild drift-check reports 65/65 exact, 0 changed.
7. **Default CLI pointed at PostgreSQL and failed without psycopg.** TRUE.
   FIXED: with no --db-url and no GATE_DB_URL the pipeline runs offline on
   sqlite:///data/gate_cse.sqlite (notice printed). New `quickstart` command
   builds the synthetic fixture end-to-end (init->taxonomy->ingest->extract->
   keys->classify->validate) with zero Docker/network/spend. New UI smoke test
   (py_compile always; full import when streamlit is installed).
8. **Real LLM provider not implemented.** TRUE. FIXED as far as possible
   without spend: AnthropicProvider and OpenAIProvider are real stdlib-HTTP
   implementations (no SDK needed) with Pydantic-validated output, taxonomy-id
   enforcement, error flagging, redacted --dry-run payload preview, and TWO
   spend gates (env key + explicit --allow-spend). Tested offline with fake
   transports (request shape, malformed-response flagging, invalid-id
   flagging, both gates). A live paid pass remains owner-gated, and the model
   name must be set explicitly (GATE_LLM_MODEL) - we never assume a current
   model name.
9. **Empty figure options / flattened fractions.** TRUE (Q2's four options
   are figures). FIXED for flagging: extraction now marks any question with an
   empty option needs_review="empty option content (likely figure-only
   option...)", and a validation check fails if any empty option is
   unflagged. Fraction/exponent flattening in TEXT remains a known limitation
   by design: the PDF region (rendered on demand) is the source of truth, text
   is the searchable copy - this is called out in the workbook DATA CAVEATS
   column and docs/09.

## Stale (v2-only) findings - no action needed in v4

- "Original question crops: 65 files present" - v3 removed stored crops by
  design (owner's request): regions + on-demand render instead.
- "19/19 tests" - v4 has 45 tests.
- "Streamlit dependency unavailable" - the auditor's environment lacked
  streamlit; not a defect. v4 adds a UI smoke test and the app was booted
  headless against the v4 database (HTTP 200) during this build.

## Still pending (honest)

- **Human verification: 0/65.** All classifications, concepts and edges remain
  provenance=inferred, status=suggested. The audit's semantic review was
  applied as suggestions with review-event provenance - NOT as human
  verification. Verification happens only in the Review Workspace by the owner.
- **Live LLM API pass**: implementation done, owner approval + key + model
  choice pending. Run `--estimate-cost`/`--dry-run` first.
- **PostgreSQL re-verification of the current code** (earlier Postgres check
  covered v1): rerun alembic + tests on Postgres before relying on it.
- **More years**: per audit fix 7 and owner scope, importing historical papers
  waits until the extractor is validated against at least two historical
  layouts. No additional papers were supplied; coverage remains GATE 2026 CS-1.
