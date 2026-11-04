# Setup + Input Gathering

## Fast path (v7) - Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1     # Python 3.12 venv (via uv), packages, .env, DB, tests, doctor
.\scripts\dev.ps1 doctor                                       # PASS/WARN/FAIL with the fix for each
.\scripts\dev.ps1 app                                          # the UI
.\scripts\dev.ps1 pg-up                                        # optional: PostgreSQL 17 + pgvector in Docker (Docker Desktop must be running)
```
macOS/Linux: `bash scripts/setup.sh`, then `make app`. `setup` never overwrites `.env` or a database, and generates a random
local `POSTGRES_PASSWORD` the first time it creates `.env`. Raw data layout and how to add a paper: docs/15_DATA_ONBOARDING.md.
Postgres evidence and commands: docs/14_POSTGRES_E2E.md. Everything below is the older (v4-v6) detail.

## Machine prerequisites

- Python 3.12+ (python3.12 --version)
- Docker Desktop (for PostgreSQL) - or use the SQLite fallback below
- git

## Install

```bash
git clone <your repo> && cd gate-cse-intelligence
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env     # then fill in what you have; never commit .env
```

Everything (CLI, app, scripts) loads `.env` automatically. The template is
fully annotated: database (SQLite default, PostgreSQL via Docker), LLM
provider keys (Gemini/Groq/OpenRouter free tiers, Anthropic/OpenAI paid),
and the consent gates. See docs/13_LLM_SETUP.md.

## Database

Primary (locked): PostgreSQL 17 + pgvector.

Quickest start (offline, no Docker, no network, no spend):

```bash
pytest tests/ -q            # 81 tests
python -m src.cli quickstart   # synthetic-fixture end-to-end smoke on SQLite
```

With neither --db-url nor GATE_DB_URL set, every command runs offline on
`sqlite:///data/gate_cse.sqlite` (a notice is printed). This is the default
since v4: a fresh checkout works with zero setup.

Primary (locked): PostgreSQL 17 + pgvector.

```bash
docker compose up -d
docker compose exec postgres psql -U gate_user -d gate_cse -c "CREATE EXTENSION IF NOT EXISTS vector;"
export GATE_DB_URL="postgresql+psycopg://gate_user:$POSTGRES_PASSWORD@127.0.0.1:5432/gate_cse"
alembic upgrade head        # schema + pgvector + FTS index
pytest tests/ -q            # 81 tests
```

Explicit SQLite (same as the default, stated): `export GATE_DB_URL="sqlite:///data/gate_cse.sqlite"`,
`python -m src.cli init` instead of Alembic. Full-text search falls back to
LIKE; pgvector features are Postgres-only.

## Getting the inputs (owner, Day 0/1)

| Input | Where | Into |
| --- | --- | --- |
| 2027 CS syllabus PDF | gate2027.iitm.ac.in/static/doc/GATE2027_Syllabus/CS_GATE2027_Syllabus.pdf | data/raw/syllabus/ |
| 2027 GA syllabus PDF | same folder, GA_GATE2027_Syllabus.pdf | data/raw/syllabus/ |
| Papers 2007-2026 bulk | official Drive folder CS.zip (~66 MB) | download, then extract into data/raw/papers/ |
| Year-wise papers + keys 2021-2026 | gate2027.iitm.ac.in/download | data/raw/papers/<year>/, data/raw/keys/<year>/ |
| Optional PYQ books | owner-provided | data/raw/references/ (local only) |

You do not need to rename files perfectly: ingestion hashes, dedups and
detects roles; ambiguous files are flagged for you to confirm. Then write one
manifest per paper (year, session, expected counts from the official listing
where available - null means derive and reconcile).

## Keys

Keys vary in format by year. The reliable path: read the official key PDF,
produce one CSV per paper (`qno,kind,answer[,min,max,notes]`,
kind in mcq_single|msq_set|nat_range|nat_value|dropped), then
`python -m src.cli keys GATE-CS-2026-S1 path/to/key.csv`. Agents can do this
transcription; spot-check against the PDF.

## LLM provider (Day 3, owner decision)

Pick ONE: Anthropic or OpenAI. Put the key in .env. Run
`python -m src.cli classify --estimate-cost --price-in X --price-out Y` with
prices from the provider's current pricing page; approve the estimate; only
then run the real classification. A Claude Code subscription is NOT API
credit. Until then, the mock provider keeps the whole pipeline testable.

## No-Docker Postgres (verified fallback)

If Docker Desktop is not an option, the pip package `pgserver` runs a real
PostgreSQL without root or Docker. The repo's migration, full test suite and
tsvector FTS were verified this way on PostgreSQL 16.2 + pgvector 0.6.2:
`pip install pgserver`, then `python -c "import pgserver; print(pgserver.get_server('data/pg').get_uri())"`
and point GATE_DB_URL at it (SQLAlchemy form: postgresql+psycopg://postgres@/postgres?host=data/pg).
