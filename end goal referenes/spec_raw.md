# GATE CSE PYQ Analysis + Agentic Prep Platform: End-to-End Build Spec

Save as `BUILD_SPEC.md` in the repo. Written as a repo-bound guide: what to build, why, how, with which stack, in which order.

Status: design document. Phase 1 (section 3) is specified in executable detail, ready to start. Phases 2-4 (sections 4-6) are an architectural roadmap - direction and stack choices, not step-by-step implementation specs, and nothing in them is built or deployed. Nothing in this document claims that any corpus has been ingested, any paper parsed, or any key verified. That is the Phase 1 work this document specifies.

---

## 0. Verified sources, and exactly how each was verified

Checked live on 3 Nov 2026. The verification method matters, so it is stated per source:

- GATE 2027 portal: https://gate2027.iitm.ac.in/ - page fetched. Confirms IIT Madras as organising institute and 30 test papers for GATE 2027.
- Test papers and syllabus page: https://gate2027.iitm.ac.in/exam_papers_and_syllabus - page fetched. It warns that syllabi were revised for 2027 and candidates should check the updated versions.
- Official CS syllabus PDF: https://gate2027.iitm.ac.in/static/doc/GATE2027_Syllabus/CS_GATE2027_Syllabus.pdf - downloaded and its full text extracted and read (2 pages). Title: GATE 2027, CS, Computer Science and Information Technology, IIT Madras, Organizing Institute. It contains exactly 10 sections in this order: 1 Engineering Mathematics (Discrete Mathematics, Linear Algebra, Calculus, Probability and Statistics), 2 Digital Logic, 3 Computer Organization and Architecture, 4 Programming and Data Structures, 5 Algorithms, 6 Theory of Computation, 7 Compiler Design, 8 Operating System, 9 Databases, 10 Computer Networks. This PDF is the only syllabus truth for the taxonomy; GA has a separate syllabus PDF on the same page.
- Question paper pattern: https://gate2027.iitm.ac.in/question_paper_pattern - page fetched. For GATE 2027 papers: 65 questions (10 GA + 55 subject); for CS: 100 marks = GA 15 + Engineering Mathematics 13 + subject 72; types MCQ/MSQ/NAT; 1 and 2 mark questions; negative marking only on MCQ (1-mark: -1/3, 2-mark: -2/3); no negative on MSQ/NAT; no partial credit in MSQ; CBT, English, 3 hours. IMPORTANT: this is the current pattern. Do not assume it holds for older papers (see 3.3).
- Downloads page: https://gate2027.iitm.ac.in/download - page listing verified via search result capture of the page. Year-wise question papers + answer keys for 2021-2026, one file per paper code. Two CS sessions (CS-1, CS-2) appear for 2025 and 2026; 2021-2023 show a single CS code in the same listing. Session counts per year must be recorded from these listings, not assumed (see 3.3).
- Bulk PYQ Drive folder (the link shared in chat): https://drive.google.com/drive/folders/1xUn7rGTzKlfvJDoo4SzCRi8jRlBD63ud - folder listing read via Drive tools. It is the official IIT Madras bulk archive (files owned by helpdesk@gate.iitm.ac.in), one ZIP per paper code covering 2007-2026; `CS.zip` is ~65.6 MB. No ZIP was opened; contents, year coverage inside, and whether keys are included are Phase 1 findings.
- Backup archive (NDLI, IIT Kharagpur): https://ndl.iitkgp.ac.in/cd_document/gate/gate/root - page fetched, states papers + keys 2007-2025, open access.
- GATE 2026 site (IIT Guwahati): https://gate2026.iitg.ac.in/download.html - page fetched, year-wise papers/keys back to ~2019.
- Shared gist: https://gist.github.com/madhurimarawat/376ed280655bbd1a8d712741f282a08c - fetched. Community-curated hub of free GATE CSE/DS links. Third-party, not authoritative for syllabus or keys; candidate input for the later "resources" layer only.
- Own guide: https://gs.dnextstep.in/guides/gate-exam-complete-guide - fetched. Existing branch-resource page; possible future consumer of pipeline outputs. No integration is assumed or approved in this spec.
- The two Karpathy X posts: NOT fetchable (X blocks external fetching; both returned SOURCE_NOT_AVAILABLE). Treated as inspiration for working style only. Nothing in this spec depends on their contents. Same for the quoted Claude/Opus excerpt: a way of working, not a dependency or a verified model claim.

Inputs as stated in the request: official syllabus PDF, PYQ papers, official keys, plus privately held PYQ books/solution PDFs. Stated time frames (100 days, 200 days) are treated as example plan lengths a user enters, not a fixed exam countdown.

---

## 1. The product idea and the rules that govern it

A pipeline + platform where anyone drops in an exam's syllabus, previous papers and keys, and gets back a fully traceable analysis: every question extracted and identified (year, session, question number, page, marks, type), classified against the official syllabus (subject -> section -> topic -> concept), and rolled up into matrices, priorities, prerequisite maps and learning orders. On top of that indexed corpus sits a constrained AI tutor that answers only from this verified context. GATE CSE is the proof case; the engine is then generalised.

Three rules govern everything:

1. Traceability before intelligence. Every question record points to its source file, page and region. Every classification carries evidence. Every report number can be drilled back to actual questions. If the bank is wrong, everything above it is wrong invisibly, so the bank gets the quality gates.
2. Provenance on everything. Every fact is tagged: `official` (read from an official document), `extracted` (parsed from a paper/key), `inferred` (model or heuristic guess), or `validated` (a human confirmed it). Reports and tutor answers show this.
3. Historical, not predictive. "Databases carried X% of marks in 2021-2026" is computable fact. "It will carry X% in 2027" is a prediction this system does not make. Reports describe what was asked, how often, and how the mix shifted recently. No score promises.

---

## 2. Phases

- Phase 1 (proof, GATE CSE only): ingest -> extract -> classify -> analyse, locally, with human review loops. Fully specified in section 3.
- Phase 2 (generalise): config-driven engine; "GATE CSE" becomes one exam config. Section 4.
- Phase 3 (agentic layer): RAG, constrained tutor, diagnostic, mastery tracking, plan generator. Section 5.
- Phase 4 (product): UI, backend, storage, deployment, security, evals, monitoring, scaling, distribution. Section 6.

Do not start Phase 3's tutor before Phase 1's bank passes its release gates (3.12).

---

## 3. Phase 1: the GATE CSE proof pipeline

### 3.1 Inputs

| Input | Source | Access | Notes |
| --- | --- | --- | --- |
| CS syllabus (2027) | Official PDF (section 0) | Direct download | Parse and hand-curate into taxonomy data |
| GA syllabus (2027) | Same page | Direct download | Common to all 30 papers |
| Papers + keys 2021-2026 | gate2027.iitm.ac.in/download | Per-file downloads | Sessions as listed there |
| Papers 2007-2026 bulk | Drive folder `CS.zip` | Drive download | Official IITM archive; contents inspected in Phase 1 |
| Private PYQ books / solution PDFs | Provided by the owner (Drive/ZIP/upload) | Private, local only | For solutions and cross-checking; never redistributed; cloud-processing consent per 3.9 |

Default analysis window: 2012-2026 inclusive (the requested 15 years), all sessions, with the pipeline able to ingest anything older that the bulk ZIP contains. The window is a filter, not an ingestion limit.

### 3.2 Corpus layout, immutability, dedup

```
corpus/
  raw/
    syllabus/                     # official syllabus PDFs
    papers/<year>/<session>.pdf
    keys/<year>/<session>_key.pdf
    books/                        # private, gitignored, access-controlled
  manifests/                      # per-year/session format manifests (see 3.3)
  extracted/                      # parser output JSON per paper
  classified/                     # classification output (JSON/Parquet)
  assets/<question_uid>/          # cropped diagrams/tables/equations as images
  db/gate.duckdb
  taxonomy/
```

- Raw files are immutable. Every derived artefact stores the SHA-256 of the raw file it came from.
- Duplicate mirrors: the same paper can appear in the bulk ZIP, the year-wise download page and the NDLI mirror. Ingestion hashes every file; identical hashes are stored once with multiple source refs; differing files that claim the same identity (year+session) are flagged for human reconciliation, never silently merged.

### 3.3 Per-year/session format manifests (do not assume a uniform format)

The current 65-question / 100-mark / GA-included pattern is verified for GATE 2027 only. Older papers differ: the pre-online era used different paper structures, GA was not always present in the same form, marks totals differed in early years, and legacy papers contain constructs the current pattern does not (common-data question groups and linked question pairs, where two questions share a stem; these existed in pre-2014 papers). Session counts also vary by year.

So every paper is ingested against a manifest, written when the paper is added, from the official listing and the file itself:

```yaml
# manifests/2015-CS2.yaml (illustrative example, not verified data)
year: 2015
session: CS-2
source_files: ["corpus/raw/papers/2015/CS2.pdf"]
expected_questions: null        # fill from the paper itself or official listing
expected_marks: null            # null means: derive, then reconcile
has_general_aptitude: null      # true/false/null
structure_notes: ""             # e.g. "contains linked-answer pairs Q52-Q53"
key_file: "corpus/raw/keys/2015/CS2_key.pdf"
key_notes: ""                   # e.g. "contains NAT ranges; one dropped question"
```

Rules:

- `expected_questions`/`expected_marks` set from an official source (listing, paper front page) where available; otherwise derived from the parsed paper and recorded as derived.
- Extraction reconciles against the manifest. A paper whose parsed question count or mark total disagrees with its manifest goes to `needs_review/` with the discrepancy recorded. No silent fixes.
- Unknown is a first-class value. If the parser cannot determine marks or type for a question, the field is `null` and the question is queued for review, not guessed.
- Key anomalies are modelled explicitly: answer challenges resolved in final keys (record which key version is stored and its date), dropped/bonus questions (a `status: dropped` flag with source note), NAT answers that are ranges (store `answer_min`/`answer_max`), MSQ answers that are sets (store an ordered list).

### 3.4 Syllabus taxonomy as data

Download the official CS syllabus PDF and hand-curate it into version-controlled YAML. The structure below is an ILLUSTRATIVE EXAMPLE ONLY; the real file is transcribed from the official PDF and diffed against it in review.

```yaml
# taxonomy/gate-cs-2027.yaml (ILLUSTRATIVE - transcribe from the official PDF)
exam: GATE
paper: CS
syllabus_year: 2027
source_pdf: corpus/raw/syllabus/CS_GATE2027_Syllabus.pdf
source_sha256: "<hash of the downloaded file>"
sections:
  - id: EM
    name: Engineering Mathematics
    topics:
      - id: EM.DM
        name: Discrete Mathematics
        syllabus_text: "<verbatim clause from the official PDF>"
        concepts: []              # filled during curation; each tagged provenance
```

- Sections and topics are `official` provenance, transcribed verbatim with the clause text kept.
- The concept level is finer than the syllabus wording. Concept nodes start empty and are proposed from actual questions during classification; each carries `provenance: inferred` until a human accepts it (`validated`).
- Taxonomy is versioned (`taxonomy_version` on every classification). The official syllabus page states that the 2027 syllabi were revised; the taxonomy therefore follows the downloaded 2027 PDF (verified above), not any older list. Any topic found in old papers or coaching lists but absent from the 2027 PDF is kept as `deprecated: true` so old questions still classify, while reports can show "no longer in syllabus".
- A GA node tree exists too, from the official GA syllabus PDF.

### 3.5 Extraction: questions as records, diagrams as assets

Per question, one JSON record:

```json
{
  "question_uid": "GATE-CS-2024-S1-Q17",
  "year": 2024, "session": "CS-1", "qno_in_paper": 17,
  "page_span": [4, 5],
  "marks": 2, "qtype": "MCQ",
  "stem_text": "...",
  "options": [{"label": "A", "text": "..."}],
  "assets": [
    {"kind": "diagram", "file": "assets/GATE-CS-2024-S1-Q17/fig1.png",
     "page": 4, "bbox": [72.0, 130.5, 540.0, 310.2]},
    {"kind": "equation", "file": "assets/GATE-CS-2024-S1-Q17/eq1.png",
     "page": 4, "bbox": [96.0, 320.0, 400.0, 356.8]}
  ],
  "answer": {"kind": "mcq_single", "value": ["B"], "key_source": "corpus/raw/keys/2024/CS1_key.pdf"},
  "source_file": "corpus/raw/papers/2024/CS1.pdf",
  "source_sha256": "...",
  "extraction": {"method": "pymupdf", "confidence": 0.98, "needs_review": false}
}
```

Method:

1. Digital extraction first: PyMuPDF (https://pymupdf.readthedocs.io/) for text spans with layout coordinates; pdfplumber (https://github.com/jsvine/pdfplumber) where tables need structure. Recent GATE PDFs are digital; verify per file.
2. Segmentation: split on question numbering patterns, tracking page numbers and bounding boxes. Questions routinely span pages (stem on one page, options or a diagram on the next), so segmentation must carry a `page_span` and pull asset regions from every page in the span. Linked/common-data groups (legacy years) are segmented as a shared stem plus child questions, each child with its own uid and a `group_id`.
3. Assets, not just text: diagrams, tables, equation images and option images are cropped by bounding box into `assets/` and referenced from the record. Text-only chunking loses exactly the content (graphs, timing diagrams, parse trees, tables) that CS questions lean on, and the Phase 3 tutor needs these images. Equations may be transcribed to LaTeX as `inferred` text while the image stays the source of truth.
4. Marks/type detection: papers print mark-section headers and NAT questions lack options, but option absence is a hint, not a rule (a malformed extraction also lacks options). Type is decided by combining explicit cues (section headers, "NAT" markers in keys) with option structure; conflicts and low confidence set `needs_review`.
5. OCR fallback: `ocrmypdf` (https://ocrmypdf.readthedocs.io/) for image-only pages, then the same pipeline. Older papers may be scans; decide per file after inspection, not by assumption.
6. Key parsing: key tables parsed with pdfplumber; join on (year, session, qno). Model the key anomalies from 3.3 (ranges, sets, dropped, corrected versions).
7. Reconciliation: per 3.3. Any paper failing count/marks reconciliation is parked in `needs_review/` with the numbers it produced.

### 3.6 Classification: two stages, no double counting, measured accuracy

Stage A: section. Combine position rules where the manifest says GA occupies known question numbers, keyword/structure cues, and the LLM for the remainder. Position rules come from the manifest, never hardcoded globally.

Stage B: topic + concept. LLM with structured output (JSON schema enforced):

```
Input: question record (text + asset image references), taxonomy subtree
Output: section_id, topic_id, concept_ids[],
        primary_topic_id,             # exactly one
        topic_weight: {topic_id: fraction summing to 1},
        what_it_tests,                # one line
        prerequisite_concept_ids[],
        confidence, evidence_quote
```

Multi-topic questions: many GATE questions genuinely span topics. To keep every matrix honest:

- Headline counts and mark totals use `primary_topic_id` only, so subject x year totals always equal the paper's real totals. No double counting anywhere.
- A fractional view uses `topic_weight` for "topic involvement" analysis, clearly labelled as fractional.
- Low-confidence or multi-topic-conflict cases go to the review queue.

Human evaluation, two different measurements kept separate:

- Gold-set accuracy: before trusting the classifier, a person labels a stratified gold set (suggest 200-250 questions, spread across sections and years) WITHOUT seeing the model's answers. Split it in two at creation: a dev set (about 60%) used freely while tuning prompts and heuristics, and a holdout test set (about 40%) that is scored rarely - never tuned against - so the release number stays honest. Repeatedly adjusting the classifier until the test set looks good silently turns it into a dev set. Report per-section precision/recall and topic-level accuracy on the holdout. This is the number that gates release.
- Review-queue agreement: in the day-to-day review UI the reviewer sees the model's suggestion; agreement here is cheaper to collect but biased upward (anchoring). It is used to find weak spots, never reported as accuracy.

### 3.7 Ingestion security (papers are untrusted input)

- Prompt injection: PDF text is untrusted content. Extraction and classification prompts treat paper text as data, never as instructions; a system-prompt boundary states this, and any PDF text resembling instructions ("ignore...", "classify everything as...") is logged and left inert. This matters more once agentic tools arrive in Phase 3.
- Archive handling: ZIPs are extracted with a safe extractor that rejects path traversal (zip-slip), enforces file-count and total-size caps (zip bombs), and verifies actual file type by magic bytes, not extension.
- PDF handling: parse in a sandboxed worker; disable embedded JavaScript/actions; cap pages and memory per file.
- SSRF: any component that fetches URLs (download helper now, web tools later) allows only an allowlist of hosts (gate2027.iitm.ac.in, the user's Drive, NDLI) and refuses redirects off-allowlist.

### 3.8 Storage: minimal schemas

DuckDB (https://duckdb.org/docs/) single file; rebuildable from raw + manifests + taxonomy at any time.

```sql
CREATE TABLE papers(
  paper_id TEXT PRIMARY KEY,        -- e.g. GATE-CS-2024-S1
  year INT, session TEXT,
  manifest_path TEXT, source_sha256 TEXT,
  expected_questions INT, expected_marks INT,
  derived_questions INT, derived_marks INT,
  reconciled BOOLEAN, ingest_run_id TEXT);

CREATE TABLE questions(
  question_uid TEXT PRIMARY KEY, paper_id TEXT, qno_in_paper INT,
  page_span INT[], marks DOUBLE, qtype TEXT,        -- null marks/type => review
  stem_text TEXT, options JSON, group_id TEXT,
  source_file TEXT, source_sha256 TEXT,
  extraction_confidence DOUBLE, needs_review BOOLEAN);

CREATE TABLE question_assets(
  question_uid TEXT, kind TEXT, file TEXT, page INT, bbox DOUBLE[]);

CREATE TABLE keys(
  question_uid TEXT, answer_kind TEXT,             -- mcq_single | msq_set | nat_range | dropped
  answer_list TEXT[], answer_min DOUBLE, answer_max DOUBLE,
  key_version TEXT, key_source TEXT, notes TEXT);

CREATE TABLE classifications(
  question_uid TEXT, taxonomy_version TEXT,
  section_id TEXT, topic_id TEXT, concept_ids TEXT[],
  primary_topic_id TEXT, topic_weight JSON,
  what_it_tests TEXT, prerequisite_concept_ids TEXT[],
  confidence DOUBLE, evidence_quote TEXT,
  provenance TEXT,                                 -- inferred | validated
  model TEXT, prompt_version TEXT);

CREATE TABLE taxonomy_nodes(
  node_id TEXT, parent_id TEXT, level TEXT, name TEXT,
  syllabus_text TEXT, provenance TEXT, deprecated BOOLEAN);

CREATE TABLE prerequisites(
  concept_id TEXT, requires_concept_id TEXT,
  provenance TEXT, source_note TEXT);

CREATE TABLE ingest_runs(
  ingest_run_id TEXT, started_at TIMESTAMP,
  parser_version TEXT, files JSON);
```

### 3.9 Private books: isolation and consent

- Book PDFs live in `corpus/raw/books/`, gitignored, filesystem-permissioned, excluded from any artefact that could be published.
- Embeddings and chunks derived from books go to a separate `private` namespace/collection, never mixed into anything that could be served to other users later.
- Sending book text to a cloud LLM (for classification support or later RAG) means uploading privately held, copyrighted content to a third party. That requires an explicit config flag (`allow_private_corpus_cloud: false` default) and owner consent per provider. The default path classifies papers only; book content is processed locally.

### 3.10 CLI contract and example outputs

One CLI (`gatepipe`) so Claude Code or a human runs the same steps. These commands are the PROPOSED interface - none of this exists as installed, runnable tooling yet; Phase 1 builds it:

```
gatepipe ingest  --exam gate-cs --file corpus/raw/papers/2024/CS1.pdf \
                 --manifest manifests/2024-CS1.yaml
gatepipe extract --paper GATE-CS-2024-S1
gatepipe keys    --paper GATE-CS-2024-S1 --key-file corpus/raw/keys/2024/CS1_key.pdf
gatepipe classify --exam gate-cs [--year 2024] [--sample 0.15] \
                  --model claude-... --prompt-version v3
gatepipe review  --queue needs_review      # launches the Streamlit review app
gatepipe analyze --exam gate-cs --window 2012-2026 --out ANALYSIS.md
gatepipe rebuild                           # raw + manifests + taxonomy -> fresh db
```

Example analysis output (structure only; numbers come from the bank):

```
## Section x Year (marks, primary topic only)   [window 2012-2026, all sessions]
| Section        | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | ... |
| Databases      |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |     |
...
Drill-down: Databases 2024 -> GATE-CS-2024-S1-Q17 (2m, MCQ) [pdf page 4]
                             GATE-CS-2024-S2-Q31 (1m, NAT) [pdf page 7]
```

### 3.11 Analysis outputs (all generated from the bank)

1. Section x Year matrix: question counts and marks, primary topic only, filterable by window (default 2012-2026), session, marks, type.
2. Topic/concept heat within each subject, with drill-down to the question and its PDF page and assets.
3. Trend view: recent-years vs older mix, labelled historical.
4. Type/marks mix by subject (MCQ/MSQ/NAT; relevant because MSQ/NAT carry no negative marking).
5. What-they-test notes per topic, aggregated from classifier lines, promoted to `validated` only by human edit.
6. Prerequisite map: seed edges from taxonomy order and the owner's book chapter order; classifier-proposed edges stay `inferred` until accepted. Rendered as Mermaid/Graphviz.
7. Two learning orders: scoring focus (historical marks share, recency-weighted, minimum-cover set first) and concept strength (topological order over validated prerequisites). Clearly labelled as the two different things they are.
8. Per-subject starter sheet: assumed basics (maths for probability, C pointers for data structures), sourced from syllabus wording + book prefaces + validated edits.

### 3.12 Phase 1 release gates

- Extraction: every ingested paper reconciles against its manifest or sits in `needs_review/` with a recorded discrepancy. Zero questions with unexplained null marks/type.
- Identity: every question has year, session, qno, source file, page span. Zero orphans. Duplicates across mirrors resolved.
- Keys: every question joins to a key where one exists; missing keys are listed; dropped/corrected/range answers modelled per 3.3.
- Classification: gold-set accuracy (blind, per 3.6) meets the bar set in the repo (suggest >= 90% section-level, >= 80% topic-level) before any rollup is published, even to the owner.
- Provenance: every classification and prerequisite edge tagged.
- Rebuild: `gatepipe rebuild` regenerates db + reports from raw + manifests + taxonomy with matching hashes.

### 3.13 Stack, setup, and honest cost estimation

- Python 3.11+, uv (https://docs.astral.sh/uv/), PyMuPDF, pdfplumber, ocrmypdf, DuckDB + Parquet, Streamlit (https://streamlit.io/) for review UI, pytest, ruff.
- Raw-file storage: gitignored folders + Drive; DVC (https://dvc.org/doc) when versioning large files becomes painful.
- LLM classification via the Anthropic API with structured outputs (docs root: https://docs.claude.com/). A Claude Code subscription is not API credit; API usage is billed separately per token, so treat them as two different things when planning.
- Do not pre-guess corpus question counts or that "LLM passes are cheap". Measure instead: after extraction, count actual questions and tokens (`gatepipe stats`), get current per-token prices from the provider's pricing page, estimate cost per classification pass, and record the estimate in the repo before the first full run. Use prompt caching and only reclassify questions whose hash or taxonomy version changed. A local model via Ollama is a valid learning exercise for a first pass, with accuracy measured against the gold set the same way.

```bash
uv init gate-cse-analyzer && cd gate-cse-analyzer
uv add pymupdf pdfplumber duckdb streamlit anthropic pytest ruff
mkdir -p corpus/{raw/{syllabus,papers,keys,books},manifests,extracted,classified,assets,db,taxonomy}
```

Claude Code workflow: keep this spec in the repo, run one stage at a time (extract 2026 CS-1 first), verify against the gates, then widen. Small verified steps, matching the working style that inspired the project.

### 3.14 Phase 1 week plan (suggested)

- Week 1: repo + env; download syllabus and 2024-2026 papers/keys; write manifests for those years; transcribe taxonomy v1 from the official PDF; extract one paper; reconcile.
- Week 2: extraction + keys for 2021-2026 all sessions; linked-question and asset handling; OCR fallback where needed; review queue flow.
- Week 3: open and inventory CS.zip; manifests for 2007-2020 discovered from actual contents; ingest the 2012-2020 window (and older if present and wanted); full reconciliation.
- Week 4: build the blind gold set; classify the bank; measure accuracy; review loop; first `ANALYSIS.md` with all matrices, prerequisite map v1, both learning orders, per-subject starter sheets.

Exit only when the gates in 3.12 pass.

---

## 4. Phase 2: generalise into a reusable exam engine

Not "trivial for other branches" - each new exam is real work, but it is config work, not engine work:

- `exams/<exam-id>/exam.yaml`: paper structure rules, session naming, GA rules, key conventions, parser selection, source links.
- `exams/<exam-id>/manifests/*.yaml` and `taxonomy/*.yaml`: per-exam, per the same rules as Phase 1. A taxonomy validator checks the transcribed YAML against the official syllabus PDF (every official clause present, verbatim).
- A `PaperParser` interface; the GATE parser is one implementation. Exams with different layouts add a parser, keyed by config.
- Reports read config, so matrices and learning orders generate for any ingested exam.
- GATE branches reuse the GATE parser and the same bulk folder (it has every branch's ZIP), but each still needs its own taxonomy transcription, manifests, gold set and accuracy measurement. That per-exam validation is the unavoidable part.
- Named next reuse target (from the owner): EAPCET, after GATE CSE Phase 1 proves out. Nothing about EAPCET is resolved in this document - which EAPCET (AP or TS), which stream, which years, its syllabus structure, paper format, marking scheme and where official papers/keys are published are all open questions to research when that work starts. The right expectation: EAPCET gets its own exam config, manifests, taxonomy and gold set, and likely its own parser, since it is not a GATE-format exam.

## 5. Phase 3: the agentic layer

### 5.1 Retrieval vs finetuning: a measured decision, not a doctrine

Default architecture: classification (Phase 1) + retrieval-augmented answering. Reasons that apply to this product specifically: answers must cite question IDs and PDF pages, which retrieval supports structurally; the knowledge base changes (syllabus revisions, new papers), and a retrieval index updates by re-ingestion while a trained model needs retraining; and the corpus is small enough that retrieval quality is easy to evaluate.

Finetuning remains a legitimate tool for behaviour, not knowledge: if evals (6.4) show persistent format or style failures after prompt and retrieval fixes, measure a small finetune against the same eval set and compare cost and quality honestly (training + hosting vs retrieval operations). Decide from those numbers, not from a rule either way.

Stack: sentence-transformers for local embeddings; pgvector inside Postgres (https://github.com/pgvector/pgvector) or Qdrant self-hosted; chunking tied to the taxonomy, with question assets (images) attached to their chunks so the tutor can show diagrams, not just describe them.

### 5.2 The constrained tutor

"Only this exam's context" is an architecture, not a prompt hope:

- Retrieval scope: context comes only from the indexed corpus (questions, keys, solutions, taxonomy, and - with consent per 3.9 - private books). No open web in the default answering path.
- Answering contract: every answer cites the question uids / taxonomy nodes used. Empty retrieval means the tutor says it does not have that, instead of inventing.
- Scope check before answering; out-of-scope asks get a fixed refusal. Every retrieval + answer logged for evals.
- Injection defence extends here: retrieved chunks are data; corpus text that looks like instructions is never executed.
- Memory: per-user mastery state and history in Postgres, injected as structured context, so context control stays explicit and inspectable.

### 5.3 Diagnostic, mastery, plans (with contracts)

- Diagnostic: ~30 questions sampled from the bank, stratified by section and difficulty, each mapped to taxonomy nodes. Selection query: stratified sample over `classifications` where `provenance = validated`.
- Mastery model: per taxonomy node, `self_declared` (checkbox checklist over chapter -> topic -> concept) and `tested` (diagnostic + PYQ performance) kept as separate scores.
- Plan generator: inputs = days available (100/200 are examples), hours per day, mastery state, track (scoring focus / concept strength). Output = week-by-week schedule allocating topics by priority and prerequisites, with PYQ sets referenced by question_uid. Days are user input; no baked-in exam countdown.

## 6. Phase 4: product and platform

- Backend: FastAPI (https://fastapi.tiangolo.com/) over Postgres (DuckDB stays as the offline analytics engine).
- Frontend: Next.js (https://nextjs.org/docs). Until the product shape settles, keep the Streamlit UI; do not maintain two frontends.
- Object storage: S3-compatible for PDFs and assets (AWS S3, or self-hosted MinIO https://min.io/ for the self-hosting path).
- Auth: none for local phases; email/OAuth (Clerk or Auth.js) once multi-user.
- Deployment: one VPS + Docker Compose is enough for a long time; add managed Postgres/S3 when load demands. CI via GitHub Actions: tests, lint, extraction reconciliation on a fixture paper, eval suite.
- Backups and restore: nightly Postgres dumps + object-store versioning, and a documented, tested restore runbook (a backup that was never restored is not a backup).
- Secrets: no keys in the repo or env files committed anywhere; a `.env` locally gitignored, then a secrets manager (Doppler/SOPS/Vault) at deployment. API keys scoped per environment.
- Network policy: outbound allowlist for any service that fetches (per 3.7); inbound only through the app.
- Worker queue: ingestion, classification and embedding are offline batch jobs; move them to a queue (Celery/RQ with Redis) so the web path stays read-only and fast.
- Cost guardrails: per-run token budgets in the classifier, cached answers keyed by question+context hash, and spend alerts at the provider.
- Monitoring: structured logs, Uptime Kuma for liveness, Sentry for errors; Prometheus/Grafana only when traffic justifies them.
- Distribution/revenue: decide late. Free + paid plans, institutional licences, or open-source the engine and charge for hosting. Open-sourcing is compatible with keeping user data and private book content out of the repo.

### 6.4 Evals (first-class, not an afterthought)

- Golden tutor set: questions with expected citations, run on every prompt/retrieval/embedding change (promptfoo https://www.promptfoo.dev/ or a small custom harness).
- Classification accuracy re-measured against the blind gold set on every taxonomy or prompt version change.
- Extraction reconciliation in CI on a known fixture paper.
- All eval results committed to the repo with the model/prompt versions they came from.

## 7. Rights and data care

- Official GATE papers/keys: published by IITs for candidate use. Building a local, personal analysis tool is low-risk, but that is a risk assessment, not legal clearance: re-hosting official papers or keys inside a public or commercial product needs an explicit rights review (or legal advice) before launch. Safest default: analyse locally, link out to official download pages for raw files.
- Private books/solution PDFs: local ingestion only, never redistributed, never served to other users, cloud processing only per 3.9.
- Community resources (the gist, the gs.dnextstep.in pages): ingest as links and short references, not copied content.

## 8. Honest limits

- Verified levels are stated per source in section 0: the syllabus PDF was downloaded and read; CS.zip contents are uninspected; no question paper or key has been parsed. Extraction feasibility for the oldest years (scan quality, OCR need, legacy formats) is a Phase 1 finding.
- The 2027 pattern facts apply to GATE 2027. Historical formats are discovered per manifest, not assumed.
- The taxonomy YAML in this document is illustrative; only the official PDF is syllabus truth.
- The Karpathy posts could not be fetched; nothing here depends on them.
- Weightage outputs describe history and recent drift. They do not predict GATE 2027.
- "Which chapters to skip" style advice stays labelled as historical-pattern inference validated by a human, never exam authority.
