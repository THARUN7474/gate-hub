# Agent Work Split

Ownership by module, not by day. Contracts are established FIRST (they already
exist in this starter), then agents work in parallel on different files.

## Contracts (do not break)

1. `src/db/models.py` - SQLAlchemy models. Changes only via Alembic migration.
2. `src/classification/classify.py` ClassificationOut - the classifier output schema.
3. `taxonomy.yaml` - allowed classification labels.
4. Review semantics in `src/validation/review.py` - verified survives reruns.

## Split

| Agent | Owns | Work |
| --- | --- | --- |
| Codex | src/db, alembic, src/analytics, src/validation, tests | migrations, indexes, FTS, matrices, exports, quality checks |
| Claude Code | src/ingestion, src/extraction | real-paper segmentation tuning, crops, key matching, reconciliation |
| Antigravity | app.py | browser, matrix UI, topic report, review workspace polish |
| Owner | inputs, taxonomy approval, gold set, review decisions | the human bottleneck - schedule it (see below) |

Integration rule: Codex finalizes any schema change first; Claude Code builds
extraction against it; Antigravity uses seeded fixture data until the first
real paper parses. Integrate after 2026 CS-1 parses, then widen.

## Human bottlenecks (plan these, they do not parallelize)

- Taxonomy topic approval: ~30-45 min, Day 1
- Blind gold-set labelling (60-100 questions): 1.5-2.5 hrs, Day 3
- Review queue: 15-30 min per paper, Days 3-5

## Master prompt (paste into each coding agent, adjust OWNERSHIP line)

Build Phase 1 of a local GATE CSE question-intelligence application. Deadline:
five days. Prioritize correct end-to-end functionality over architecture.

Stack: Python 3.12+, PostgreSQL 17 + pgvector (Docker Compose), SQLAlchemy 2 +
Alembic, PyMuPDF, Pydantic, one LLM provider via the existing abstraction,
Streamlit, Pandas, pytest. No cloud, S3, microservices, RAG chatbot, auth, or
scaling work.

The repo already contains: models (src/db/models.py), pipeline modules, a
Streamlit app, taxonomy.yaml (official 2027 syllabus transcription), a
synthetic fixture, and 15 passing tests. YOUR OWNERSHIP: <module list above>.
Do not modify files outside your ownership without coordinating through the
integrator. The contracts above are frozen; schema changes go through Alembic.

Requirements: idempotent ingestion; AI suggestions stored separately from
human-verified classifications; never overwrite verified records; every
question keeps its source PDF reference and page crop; missing data flagged,
never invented; matrix totals use primary_topic_id only (no double counting);
keep PDF text as data, never instructions, in LLM prompts.

Implement working code, not pseudocode. Run the tests and report real results;
do not claim success for unexecuted commands. If real PDFs are unavailable,
extend tests with clearly labelled synthetic fixtures and report real-PDF
integration as unverified.
