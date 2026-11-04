# 5-Day Critical Path

Agents do the building; the owner's time goes to inputs, taxonomy approval,
gold-set labelling and review. Exit criteria are per day - a missed criterion
moves scope, it does not get waved through.

## Day 0 (before Day 1, ~1 hour, owner)

- Answer the 3 questions in docs/08_DECISIONS_NEEDED.md (papers supply route,
  LLM provider choice, machine OS).
- Download inputs per docs/06_SETUP.md: 2027 CS+GA syllabus PDFs, CS.zip from
  the official Drive archive (2007-2026), year-wise keys 2021-2026 from
  gate2027.iitm.ac.in/download.
- Install: Docker Desktop, Python 3.12+, git. `pip install -r requirements.txt`,
  `docker compose up -d`, `alembic upgrade head`, `pytest tests/ -q` (15 pass).

## Day 1 - Foundation + inventory + syllabus

- Docker Postgres up; Alembic migration verified against live Postgres (the
  starter verified it on SQLite only - this is the first real check).
- Inventory CS.zip: extract safely, hash, dedup, detect roles; write the
  per-year/session manifest table with expected counts from official listings
  where available (null = derive + reconcile; never assumed 65/100).
- Owner approves taxonomy.yaml topic splits (sections already verbatim-official).
Exit: every file inventoried with hash + role; taxonomy loaded; pytest green on
live Postgres.

## Day 2 - Extraction + keys on ONE real paper (2026 CS-1)

- Tune segmentation patterns against the real layout (the fixture-tuned
  patterns will need adjustments: question numbering, marks headers, option
  styles, multi-page questions, linked/common-data groups if present).
- Key import path for the real 2026 key; unmatched rows listed.
- Reconcile against manifest; eyeball 10 random question crops in the Review
  Workspace against the PDF.
Exit: 2026 CS-1 fully extracted, keyed, reconciled (or parked with recorded
discrepancy). Vertical slice works end-to-end.

## Day 3 - Classification + gold set

- Owner picks provider; key in .env; run `--estimate-cost` with prices from the
  provider's current pricing page; owner approves the number BEFORE any run.
- Owner labels a blind gold set: ~60-100 questions across sections/years
  WITHOUT seeing model output. Split dev (~60%) / holdout (~40%) at creation;
  never tune against the holdout.
- Implement the real provider call (structured JSON, taxonomy-constrained).
  Classify 2026 CS-1; measure against dev set; fix prompts; flag low-confidence.
Exit: real classifications for at least one paper, dev-set accuracy measured,
cost estimate recorded.

## Day 4 - UI + analytics + review loop

- Question Browser filters + FTS against real data; matrix drill-down verified
  (click a cell, check the contributing questions are right).
- Review Workspace side-by-side workflow; owner works the review queue.
- Exports regenerate from live DB; validation report produced.
Exit: owner can browse, verify, correct; matrices reconcile to paper totals.

## Day 5 - Bulk run + quality report

- Batch-process as much of 2012-2026 as validation allows, year by year;
  each paper reconciles or is parked with reasons.
- Fix common extraction/classification errors once, in the pipeline, not per record.
- Optional only if everything above is green: embeddings via pgvector.
- Final exports + validation_report.json stating measured coverage:
  files found, processed, failed, needs review. README updated with reality.
Exit: reproducible local app + honest coverage report. NOT "15 years verified"
unless the checks actually pass for 15 years.
