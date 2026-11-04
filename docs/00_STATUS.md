> **Current state: see `docs/CURRENT_STATUS.md`** (measured after the v11 merge on the owner's machine).
> Everything on this page is HISTORY (v4-v11 build notes); where it disagrees, CURRENT_STATUS wins.

# Status: implemented vs scaffold vs unverified (4 Nov 2026, v10; older sections kept below as history)

**v10 update (4 Nov 2026, ~15:45 - review-driven UI fixes, marks audit, Gemini smoke test):**

*Marks audit (queried today on staging):* all 1,885 questions carry marks in {1.0, 2.0}
(1-mark: 870, 2-mark: 1,015); every one of the 29 papers sums to exactly 100.0 marks. No anomalies.
*UI:* Topic x Year matrix cells are clickable and drill to the contributing questions, which open
directly in the Review Workspace; Subject Overview reworked to a compact per-subject table with
per-topic expanders (readable concept names, what-it-tests samples, prerequisite edges from taxonomy.yaml).
*Gemini API smoke test (bounded, free tier, owner-supplied key) - what is proven and what is not:*
PROVEN: the API key is valid and the connection works - `llm-models gemini` listed 46 models including
gemini-3.8-flash (free-tier existence per ai.google.dev/gemini-api/docs/pricing and /models, 4 Nov 2026).
NOT PROVEN: a single successful inference. A bounded run (classify --provider gemini --paper-id
GATE-CS-2011-S1 --max-calls 2) made 2 attempts; BOTH returned HTTP 503 UNAVAILABLE ("model is currently
experiencing high demand"). The guard retried (5s + 15s) and stopped cleanly at the cap: 0 rows written,
classifications table untouched. A single-question probe 75s later also returned 503. The run's internal
usage counters recorded no completed call, but that is our own accounting - a 503 says nothing about
provider-side quota, and the 503 alone does not say whether the cause is temporary or when it clears.
No further API retries without an explicit owner instruction. When a retry is wanted, the
classification_proposals workflow (below) is the one to use.
*Independent provider proposals (v10):* `classify --provider X --proposals` writes each provider's
answer as a SEPARATE row in classification_proposals (keyed per question/provider/model/prompt) and
NEVER touches the classifications table - the 1,867 agent labels and any human review stay exactly as
they are, and headline analytics cannot double-count. `proposals-report` compares every provider with
the current labels (agree / disagree / fills_unclassified / against_verified). Covered by
tests/test_proposals.py (5 tests, incl. resume and multi-provider independence).
*Region previews:* the Review Workspace renders each question's stored region from the original PDF
(verified for scanned 2011-S1 Q64 against the owner-supplied source PDF, sha256-matched to the
registered document: full question + all 4 options, correctly aligned). When the PDF file is not on
the machine the message now says so honestly and names the file ("the region IS stored; place the
original PDF anywhere under data/raw/") instead of claiming no region exists.
*What-it-tests honesty:* the v2 pass recorded no per-question prose; a placeholder ("agent: <keywords>")
leaked into 1,589 rows and is now removed - v2 what_it_tests is NULL (v1's 65 real descriptions kept).
The UI says "not recorded for this suggestion - add during review" instead of showing placeholders.
*Model column meaning:* values like `claude-agent-manual-v2` are descriptive labels of the LABELING
METHOD (which pass produced the row), not a verified identity of any underlying provider model.

**v9 update (4 Nov 2026, ~15:30 - agent first-pass classification of ALL papers done; this block supersedes anything below that contradicts it):**

*Database facts (queried today on staging `data/gate_cse.candidate.sqlite`):*
| | live `data/gate_cse.sqlite` | staging `data/gate_cse.candidate.sqlite` |
| --- | --- | --- |
| papers / questions | 2 / 130 (unchanged - promotion is still your decision) | 29 / 1,885 |
| classified questions | 65 (2026 CS-1) | **1,867 classified (1,490 suggested, 377 flagged) + 18 UNCLASSIFIED taxonomy-gap** |
| classification provenance | 65 x agent-manual-v1 (inferred) | 65 v1 + 1,802 v2, ALL provenance=inferred; per-question evidence in docs/handoff/labels-v2/*.tsv |
| human-verified | **0** | **0 - nothing is verified; every label awaits human review** |
| taxonomy gap | - | 18 software-engineering questions left unclassified (review_events field=taxonomy_gap), NOT forced into PDS.C |
| review events | 3 | 398 (377 flags + 18 taxonomy-gap + 3 prior) |

*What the v2 pass is:* the same manual agent analysis as the 65 (agent reads each question, picks the topic),
written by `scripts/apply_agent_classifications.py` (model=claude-agent-manual-v2, provenance=inferred). NOT an LLM API
run, NOT human verification. **It is a TOPIC-LEVEL first pass only:** it assigns section + primary topic + confidence.
It does NOT supply what-it-tests prose (NULL for all v2 rows), prerequisite lists, or concept-level detail -
except 113 rows whose concept ids come from the keyword heuristic agreeing with the agent topic (grounded in
question text, recorded in evidence_quote). Do not read v2 as full-schema completion: the remaining detail comes
from the API proposals pass (`classify --proposals`) or human review, and those gaps stay open until then. 2013 S2/S3/S4 are shuffles of S1: labels carried by exact text match where identical,
assigned individually otherwise. Full method + audit: docs/handoff/classification-audit-v2.md.
*Quality signal:* offline keyword heuristic (`classify-local`) agrees with the agent topic on 1,083 / 1,867 (58%)
- a weak second opinion, not validation. Independent API agreement pending your key + consent.
*New in v9:* `classify-local` CLI + heuristic tests; 193 pytest pass / 1 skipped; scripts/ui_apptest.py green
(all 9 screens, full review workflows); clickable Topic x Year matrix with drilldown, Topic drilldown on Topic
Report, Topic + Classification-status filters on Question Browser, new Subject Overview screen (topics, concepts,
prerequisites), suggested-vs-verified everywhere (verified-only matrix toggle, per-model suggestion breakdown),
2011 included by default; ANALYSIS.md + exports/ regenerated.
*Still OPEN (unchanged, yours):* live-DB promotion, Q59 text completion, all human review (0/1,885), auditor's 52/10/3
file, keys for 9 papers, bulk API classification run (smoke test: key + model list OK, inference unsuccessful - HTTP 503 on all attempts, cause/duration unknown; use --proposals when retried, needs your go-ahead), concept-level accuracy metrics.

# --- v8 history below ---

# Status: v8 (4 Nov 2026, ~14:00)

**v8 update (4 Nov 2026, ~14:00 - the owner's docs pack reconciled; this block supersedes anything below that contradicts it):**

*Database facts (queried today):*
| | live `data/gate_cse.sqlite` | staging `data/gate_cse.candidate.sqlite` |
| --- | --- | --- |
| papers / questions | 2 / 130 (2025 CS-1, 2026 CS-1) | 29 / 1,885 |
| official key rows | 130 | 1,300 (20 papers; 9 papers have no key - docs/16) |
| classified questions | 65 (2026 CS-1) | 65 (2026 CS-1) |
| human-verified / with a review rubric | **0 / 0** | **0 / 0** |
| review events | 3 (2 audit-relayed topic suggestions, 1 repair script) | 3 |
| schema | current since 14:15:23 - the in-app "Back up the database, then upgrade it" button was used (backup `backups/gate_cse.20261104-141523.sqlite`); only the empty `printed_label` column was added, every existing table identical to the 14:05 backup | current |
| `validate` | 10/10 PASS (run on a schema-upgraded copy) | 10/10 PASS |

*Verified by running it today:* 188 pytest on SQLite; 187 + 1 SQLite-only skipped on PostgreSQL 17; the real-browser test **60/60** (Playwright + Chromium on a throwaway copy; source and live DB files byte-identical afterwards); `doctor` 16 pass / 1 warn (the live schema) / 0 fail; `papers-drift` on staging 28/29 byte-identical (2025 CS-1 Q59 differs);
the Q21/Q37/Q48/Q59 comparison re-run against the live DB (docs/handoff/extraction-discrepancies.md); backup
`backups/gate_cse.20261104-140559.sqlite` (integrity ok); promotion **dry run** (27 papers to add). The app answered on
http://localhost:8501 (HTTP 200).

*New in v8:* five-check review rubric and separate approval scopes, **enforced** (no verification without a passing rubric - buttons,
shortcuts, batch queue and CLI); extraction corrections (text/options/marks/type), secondary topics, editable what-it-tests, on-screen
audit history; human-corrected rows protected from reruns/imports; no-API chat-assisted classification (`chat-export` / `chat-import`,
docs/20); `review-status`; CLI commands explain an old-schema database instead of crashing. Provenance of the 65: docs/17.

*Still OPEN:* promotion of the live DB (your approval), then the Q59 text completion; all human review (0/65); classification of
1,820 questions (chat batches or API batches); the auditor's 52/10/3 file; keys for 9 papers; concept-level accuracy metrics.

**v7.3 update (4 Nov 2026, Phase 1 decisions round - details in docs/13 "v7.3", docs/16, docs/handoff/extraction-discrepancies.md):**

*Verified by running it:*
- **Run safety for real LLM calls** (offline, fake transports + fake clock): pacing to `GATE_LLM_RPM`, conservative retry, stop on
  quota/billing/auth, call cap, checkpoint every 10, resume by skipping classified questions, actual token usage recorded, malformed
  JSON can no longer crash a run, `--years` selection, evenly spread pilot sample. 170 tests pass on SQLite (157 + 1 skipped on PostgreSQL 17 before prompt v2; not re-run on PG since).
- **Promotion rehearsal** on a copy of the live database: 29 papers / 1,885 questions / 1,300 keys / 5,542 options, identical to the
  staging database (content hashes equal); all 3 existing review events and 65 classifications byte-unchanged; backup integrity ok.
  The real promotion has NOT been run.
- **2025 CS-1 Q59** was the only text difference in 1,885 questions (80 trailing characters of a state table). `scripts/repair_truncated_text.py`
  completes it (audited, only a pure truncation, never a verified question). On the copy, drift is then **65/65 exact on all 29 papers**.
  Q21/Q37/Q48 stored text equals the PDF text layer; the printed options reproduce the official keys; text deliberately not rewritten.
- **Live pilots (gemini-3.5-flash-lite, free plan attested by the owner, 7 questions of 2026 CS-1, nothing written):** v1 (text only) 6/7 topic agreement,
  the miss a General Aptitude question filed as discrete maths. **Prompt v2** (adds the answer options and a GA-block/CS-block position hint, checked on
  all 29 papers) 7/7, 0 errors, 0 retries; ~6.1k input + ~0.17k output tokens per call -> full run ~11.1M input / 0.32M output, ~3 h 50 min at 8 requests/min.
  n=7 and agreement with unverified suggestions: not an accuracy figure.

*Settings applied at the owner's instruction (in-session, 4 Nov 2026):* `GATE_LLM_ALLOW_EXTERNAL=1` and `GATE_LLM_FREE_PLAN_CONFIRMED=1`
(the owner's own statement that the Google project has no billing linked). **The Gemini key is now saved and the 7-call pilot has run (see above); no batch has run and nothing was written to any database.**

*Still OPEN:* the real promotion (blocked by a permission check on 4 Nov, run it yourself or allow it) and then the three classification batches, G3 human review (0 verified), promotion approval, keys for the 9 papers (docs/16),
auditor's 52/10/3 artifact, whether the free tier serves the chosen model (only a live call shows).

**v7 update (4 Nov 2026, this build - evidence in docs/handoff/REPORT.md):**

*Verified by running it on this machine:*
- **G1 PostgreSQL 17 + pgvector via Docker**: `pgvector/pgvector:pg17` -> PostgreSQL 17.11, pgvector 0.8.7, Alembic head 0005.
  Found and fixed 5 real defects the docs had not known about (migration crash on a fresh DB, VARCHAR(20) provider column,
  unordered exports, a hanging test fixture, FK-violating tests). 113 tests pass on Postgres (1 SQLite-only skipped), 114 on SQLite.
  All 13 tables match by content checksum; backup/restore drilled. Details: docs/14_POSTGRES_E2E.md.
- **G6 real-browser UI**: Playwright + Chromium, 49/49 checks on a throwaway DB copy (matrix drill-down == cell count,
  Verify / Verify with correction / Flag / Approve & next / the four keyboard shortcuts / batch approve, persistence across a page RELOAD,
  audit events attributed to `TEST-AUTOMATION`, all 8 screens, source+live DB files byte-identical afterwards). It found a
  real bug the old programmatic test could not (the Question dropdown snapped back to Q1 after any deep link) - fixed.
- **G7 Python**: full suite passes on 3.12.9 and 3.13.2.
- **G8 more years / layouts**: 29 papers (2011-2026) load; every one reconciles to 65 questions / 100 marks; drift-check
  re-extracts 28/29 papers byte-identical (the 29th is explained: 2025-CS1 Q59). Seven layout families. See docs/15.
- **G5**: drift-check on 2026 CS-1 = 65/65 exact on this environment (PyMuPDF 1.28.2). The auditor's original 52/10/3 artifact
  is still not available, so that discrepancy is still unexplained. Proposed notation for Q21/Q37/Q48 is in
  docs/handoff/notation-proposals.md; the database was NOT changed.

*Built:* multi-year loader (`manifests/papers.yaml`, `papers-probe|load|drift`), OCR layer with cache, sequence-aware
extractor, row-geometry key parsers (20 keys, 0 marks mismatches), `doctor`, `backup`, `promote_to_live.py`, setup/dev scripts,
UI: reviewer name, paper/status filters, "N of M verified" progress, per-provider status from recorded attempts,
plain-language provider errors, backup button, schema-upgrade prompt, keyboard shortcuts. Safety: a classification run can
no longer add a 2nd row to a question (`--reclassify` replaces unverified rows with an audit event).

*Still OPEN (do not assume otherwise):*
- **G2 live LLM calls (SUPERSEDED - see the v7.3 block above: key saved, 14 pilot calls made): was BLOCKED-NEEDS-KEY.** No key existed in `.env` then; provider adapters were
  still verified only with fake transports. Dry-run/cost tooling and a no-write `classify-compare` are ready.
- **G3 human review**: 0 of the 65 suggestions are human-verified in the live DB; the other 28 papers are unclassified.
  Only a human closes this.
- **G4**: 2025 CS-1 is extracted + keyed but unclassified (unchanged policy); so are the 27 other papers.
- 2007-2010 (photographed) are not imported (owner decision). 9 papers have no key file. OCR text of scanned years can be
  wrong in formulas (flagged; the source image is always shown).
- The live `data/gate_cse.sqlite` has NOT been modified; the full dataset sits in `data/gate_cse.candidate.sqlite` until you run
  `.\scripts\dev.ps1 promote --yes`.

**v6 update (LLM setup + approval UX, this build, SQLite):** 81/81 pytest
tests pass. Gemini/Groq/OpenRouter providers added next to Anthropic/OpenAI
(all stdlib HTTP, offline-tested with fake transports; NO live/paid call
made). Provider terms verified against official docs on 3 Nov 2026
(docs/13_LLM_SETUP.md carries the per-provider billing reality: only
OpenRouter ':free' is a provider-stated $0 route; gemini/groq are
free-IF-your-plan-is-free, which a key cannot prove). Gates: any external
call needs GATE_LLM_ALLOW_EXTERNAL=1; gemini/groq additionally need the
owner's free-plan attestation (GATE_LLM_FREE_PLAN_CONFIRMED=1) or per-run
spend approval - silent billable calls through the free path are impossible;
the paid --allow-spend gate is unchanged. `auto` runs availability-aware
classification with bounded per-question failover inside the consented set
(every attempt recorded; never a silent paid fallback). Ensemble
classification with consensus + combined score (agreement x mean confidence,
heuristic); single-provider and pre-v6 rows show agreement=NULL and are
labelled "single provider - no ensemble agreement" (no fake ensemble
signal). One-file `.env` setup auto-loaded by CLI/app/scripts. Analysis
Matrix cells are real clickable links to drill-downs, drill-down questions
link into the Review Workspace. Review Workspace gains dropdown corrections
(section/topic/concepts with full names), Verify as-is / Verify with
correction / Approve & next; new Approve Queue screen for batch approval
with full audit events. UI verified two ways: Streamlit AppTest (all 8
screens, persistence checks incl. batch approve) and real-browser Playwright
screenshots exercising the matrix link -> drill-down -> Review Workspace
click path (docs/screenshots/v6/). Still pending (unchanged from v5): human
verification of the 65 suggestions, live LLM pass (owner-gated), PostgreSQL
17 Docker E2E, multi-year import.

**v4 update (independent-audit response, this build, SQLite):** 45/45 pytest
tests pass. Taxonomy names repaired (13 corrupted nodes), 108 concept nodes +
29 curated prerequisite edges loaded, all 65 questions carry curated
concept_ids (+mechanically derived prerequisite_ids), Q65 primary corrected
DB.NF -> DB.REL and TOC.PUMP renamed TOC.RCFL (both logged in review_events,
still suggestions), re-extraction drift detection + compare-before-upsert
protection added (drift-check on CS1: 65/65 exact), offline-SQLite default +
`quickstart` smoke command, empty figure options auto-flagged, REAL
Anthropic/OpenAI provider implementations with dry-run + double spend gate
(tested offline with fake transports; no live/paid call made). Full per-finding
disposition: docs/11_AUDIT_RESPONSE.md. Still pending: human verification
(0/65), live LLM pass (owner-gated), PostgreSQL re-verification of current
code, multi-year import (needs two-layout validation; no new papers supplied).

Read this before trusting anything else in the repo.

## IMPLEMENTED and TESTED

Verified twice: on SQLite, and on a REAL PostgreSQL (16.2, non-Docker
`pgserver` runtime) with pgvector 0.6.2 enabled.

- Full pipeline end-to-end: ingest -> extract -> keys -> classify -> review ->
  analyze -> export -> validate. (v1 note: 15/15 at the time; 43/43 on SQLite in v4, PostgreSQL re-run pending.)
- Alembic migration 0001 on real PostgreSQL: schema, pgvector extension
  (ENABLED), tsvector generated column, GIN FTS index - all applied.
- Real tsvector full-text search through the app search layer (verified query).
- Definition-of-done behaviors have tests: idempotent re-import (no duplicate
  questions), no orphan/wrong-session links, NULLs flagged not invented,
  taxonomy-ID enforcement, verified corrections survive reruns, matrix totals
  equal paper totals, drill-down contributors match cell counts, exports match
  the database.
- Streamlit app: all 5 screens render against a live database (verified with
  rendered screenshots, not just framework tests).
- taxonomy.yaml: all 11 sections (10 CS + GA) transcribed VERBATIM from the
  official 2027 syllabus PDFs, downloaded and read this build (sha256 in file
  header); every syllabus_text fragment programmatically checked against the
  PDF text. Topic splits below sections are curation (provenance=inferred)
  pending owner approval.
- Ingestion security: zip-slip rejection, zip-bomb caps, magic-bytes checks,
  sha256 dedup, paper identity-conflict flagging. All tested.

## SCAFFOLD (structure real, function stubbed - do not rely on)

- LLM classification: v4 implements REAL Anthropic/OpenAI providers over
  stdlib HTTP with Pydantic-validated output, `--dry-run` payload preview and
  two spend gates (env key + explicit --allow-spend); tested offline with fake
  transports. A live pass still requires the owner to pick ONE provider, set
  the key + GATE_LLM_MODEL, run --estimate-cost and approve spend. MockProvider
  remains for offline dev; its output is placeholder plumbing, NEVER real
  classification.
- Answer keys: CSV import path works and is tested (incl. NAT ranges, MSQ
  sets, dropped questions). There is NO official key-PDF parser - a human or
  agent transcribes each official key PDF to the CSV format in docs/06_SETUP.md.
- Embeddings: question_embeddings is a placeholder; the native vector column
  is added by a later migration once the embedding model is chosen.
- Foundation-first learning order: requires curated prerequisite edges; not
  fabricated - only score-first ranking is computed.

## REAL-PAPER VALIDATION (new, 3 Nov 2026 - see docs/09_REAL_PAPER_VALIDATION.md)

- GATE 2026 CS-1 (official paper + official key, supplied by owner) ran
  end-to-end: 65 questions / 100 marks extracted and reconciled, all 65 types
  and marks cross-checked against the official key, 65/65 keys imported, all
  validation checks PASS, 19/19 tests pass, all 5 app screens run on the real
  database. The real paper needed the predicted parser tuning (label-only
  option lines, section-header exclusion, header/footer filtering) - now in
  src/extraction/extract.py.
- All 65 questions classified against the 2027 taxonomy by AGENT ANALYSIS
  (provider=agent-analysis, prompt_version=agent-v1) - NOT a paid LLM run,
  NOT human-verified. All rows are provenance=inferred/status=suggested and
  await review in the Review Workspace.
- Supplied syllabus PDF verified byte-identical (sha256) to the official
  2027 CS syllabus behind taxonomy.yaml.

## UNVERIFIED (no evidence yet - treated as open work)

- ~~Real-paper extraction is verified on ONE paper~~ **(superseded in v7: 29 papers, 2011-2026, all reconcile; see v7 section).**
  Still true: no accuracy claim exists for OCR-read text or for any classification.
- ~~Postgres 17 specifically: tested on 16.2~~ **(superseded in v7: verified on PostgreSQL 17.11 + pgvector 0.8.7 in Docker).**
- ~~Python 3.12~~ **(superseded in v7: tested on 3.12.9 and 3.13.2).**
- ~~The pgvector Docker Compose setup was not launched~~ **(superseded in v7: launched, migrated, backed up, restored).**

## Known wrinkles (honest list)

- Source previews are rendered on demand from the original PDF (see
  docs/10_REGION_STORAGE.md). Region bounds come from text lines, so a figure
  sitting far below a question's last text line with no following text would
  be clipped; every figure/table question in the 2026 CS-1 paper was visually
  verified to render completely (Q2, Q7, Q8, Q37, Q42, Q53, Q60).

## Fixed during QA (with regression tests)

- Review queue and Pipeline Status previously counted only
  `questions.needs_review`, which a re-extraction could clear, hiding
  classifier-flagged and unverified records. The queue is now the UNION of
  extraction issues + classifier-flagged + unverified suggestions +
  unclassified questions; verified counts are kept distinct
  (src/validation/review.py, tests/test_review_contract.py).
- Synthetic fixture data previously rendered as "Official key". The UI now
  shows a prominent SYNTHETIC FIXTURE banner on every screen whenever fixture
  documents exist, and fixture keys are labelled "Fixture key (SYNTHETIC - not
  a real GATE key)". 'Official' is asserted only for official source documents.
