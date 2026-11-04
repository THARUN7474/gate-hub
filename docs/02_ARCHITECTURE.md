# Phase 1 Architecture (locked by owner 2026-11-03)

## Stack

Python 3.12+ | PostgreSQL 17 + pgvector (Docker Compose) | SQLAlchemy 2 +
Alembic | PyMuPDF | Pydantic | one LLM provider (Claude OR OpenAI, configurable)
| Streamlit | Pandas | pytest.

Why this and not Next.js/FastAPI/Redis: five days go to extraction,
classification and verification quality, not web plumbing. One Python codebase
serves pipeline + UI. Streamlit covers explorer + review natively.

Why Postgres over SQLite (owner's call, locked): relational integrity, real
full-text search (tsvector + GIN), indexed filtering, optional vector
similarity later - one database. SQLite remains the no-Docker dev/test
fallback through the same SQLAlchemy models; the migration adds the
Postgres-only pieces conditionally.

## Data architecture (the part worth doing properly)

documents -> papers -> questions -> options / answer_keys / classifications /
question_metadata / question_embeddings(optional)
taxonomy_nodes -> concept_prerequisites
classification_runs, processing_runs, review_events (audit)

Three non-negotiable rules:
1. Never lose the original PDF reference (file, page span, crop image).
2. AI suggestions stored separately from human-verified classifications
   (provenance + status columns; review_events audit).
3. Re-ingestion never duplicates questions and never erases manual corrections
   (unique constraints + preservation logic in persist_records).

## Search: four layers, first two now

1. Structured filters (B-tree: year, session, marks, type, status, taxonomy).
2. Full-text search: Postgres tsvector + GIN (migration 0001); SQLite LIKE
   fallback in src/analytics/search.py.
3. Semantic similarity: pgvector LATER. question_embeddings is a placeholder;
   the native vector column is added by a follow-up migration once the
   embedding model (and dimension) is chosen.
4. Hybrid retrieval: optional Day 5+, only after extraction/classification
   tests pass.

## Security / trust

Raw PDFs are untrusted input: safe ZIP extraction (zip-slip, bomb caps, magic
bytes); PDF text is data, never instructions, in any LLM prompt. API keys in
.env only (gitignored). Private books: local only, never sent to a cloud LLM
without explicit owner consent (config: allow_private_corpus_cloud: false).

## Migration seams (post-Phase-1, not built)

FastAPI in front of the same models; Next.js replacing Streamlit; S3 for
data/assets; embeddings -> native vector column; exam configs generalize
taxonomy/manifests (EAPCET later gets its own, likely its own parser).
