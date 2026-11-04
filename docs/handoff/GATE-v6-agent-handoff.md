# AGENT HANDOFF: make GATE CSE Intelligence v6 plug-and-play

You are a coding agent with a shell, a browser and internet access. Do the work yourself. Do not just suggest steps. Work through the phases in order, run every command, and record what happened.

Input: the ZIP `gate-cse-intelligence-phase1-v6-*.zip` (project folder `gate-cse-intelligence/`). Unzip it and keep the original ZIP untouched. Do all testing on copies of the data by default (see rule 4). The live originals are only changed by an explicit, backed-up, human-approved step.

note : this part is dne already few of stuff i have done in this so check accoridnlgy

## 0. Ground rules (read first, they override everything below)

1. **Credentials.** Never ask for, print, log or commit an API key. Keys live only in the local `.env` (gitignored). If a step needs a key and `.env` lacks it, mark that step BLOCKED-NEEDS-KEY, continue with everything else, and list it in the final report. If you need the human to create a key, give them the signup URL and the exact `.env` variable name.
2. **Spending.** Do not enable paid usage, add billing, create paid accounts, or pass `--allow-spend` unless the human has said so in this session for a named provider and a cap. Having a key does not mean the call is free: Gemini and Groq free tiers depend on the account's billing plan, and the tool cannot see that. Only OpenRouter models ending in `:free` are stated as $0 by the provider. Never promise "zero cost". Before any live call, run the dry-run and the cost estimate, and show them in the report.
3. **External transmission.** Live LLM calls send question text off this machine. Set `GATE_LLM_ALLOW_EXTERNAL=1` only for the live test phase, and only after the human has OK'd it. For Gemini/Groq on a free plan, `GATE_LLM_FREE_PLAN_CONFIRMED=1` is the human's own statement. Do not set it yourself unless the human confirms the plan is free.
4. **Data safety.** Preserve existing data: `data/gate_cse.sqlite`, all classifications and `review_events` (including any human reviews done since this ZIP was made), `data/raw/*`, `exports/*`. Make a timestamped backup (`backups/gate_cse.<timestamp>.sqlite`) BEFORE running anything that could write to the DB, including baseline commands. Run integration, UI and live-LLM tests against a copy (`GATE_DB_URL` pointing at the copy) by default; touch the original only for a final, human-approved step. Never delete, reset or overwrite the DB, drop tables, or force-push without asking. Never mark any real question human-verified on the human's behalf. Synthetic approval or verify clicks used to test the UI must run only on a disposable test copy, be clearly marked as test actions (for example reviewer name `TEST-AUTOMATION`), never be attributed as human reviews, and never be merged back into real data.
5. **Honesty.** Do not claim something works unless you ran it and saw it pass. Separate "verified by me, just now" from "assumed". Keep the existing wording that the combined score is a review-priority heuristic, not a probability of being correct.
6. **Scope.** No deployment, no cloud hosting, no tutor/RAG, no new paid services. Local only.
7. If something is ambiguous and a wrong guess is costly (money, data loss, sending data out), stop and ask. Otherwise decide, note the decision, and continue.

## 1. Known state of v6 (so you do not rediscover it)

Working and tested on SQLite (81 tests passed at handoff):

- Pipeline: ingest, extract, keys, classify, review, analyze, export, validate (`python -m src.cli --help`).
- Streamlit app `app.py`: Pipeline Status, Question Browser, Analysis Matrix (clickable cells), Topic Report, Review Workspace (dropdown corrections, Verify as-is, Verify with correction, Approve & next), Approve Queue (batch approve), LLM Classify.
- Providers: mock, gemini, groq, openrouter, anthropic, openai. Selection: `GATE_LLM_PROVIDER` (auto/free/mock/named) and `GATE_LLM_PRIORITY`. `auto` tries consented providers in order with per-question failover, never falling back silently to paid.
- Ensemble: `classify-ensemble` stores per-provider votes, agreement, combo = agreement x mean confidence.
- `python -m src.cli llm-status` shows which keys/gates are set without revealing keys.

Known gaps you must close or report on:

- G1. **PostgreSQL 17 + pgvector via Docker has not been run end to end** with the current code. The repo's own docs (`docs/00_STATUS.md`, `docs/06_SETUP.md`) say an earlier version was checked on PostgreSQL 16.2 + pgvector 0.6.2 using the `pgserver` package, not Docker. Treat that as a historical note from the docs, not as proof for v6.
- G2. **No live LLM call has ever been made.** Provider adapters are tested only with fake transports. Real response formats, model names, rate limits and JSON-contract compliance are unverified.
- G3. **Human review is open and stays open.** At packaging time 0 of the 65 GATE 2026 CS-1 suggestions were human-verified, and they have no provider-run provenance (labelled "Legacy inferred suggestion"). The human may have reviewed some since: read the current counts from the DB, never assume 0. You never verify or approve anything yourself, and you do not relabel these as model output.
- G4. **GATE 2025 CS-1 is extracted (65 questions, 100 marks) but intentionally unclassified and excluded from analytics.** GATE 2026 CS-1 is also 65 questions / 100 marks and is the only paper classified. Do not classify 2025 unless the human asks.
- G5. An outside audit reported 52 exact / 10 normalized / 3 changed against the local 65, but `docs/12_AUDIT2_RESPONSE.md` says that result did NOT reproduce locally (drift-check 65 exact). The auditor's original artifact is not in the ZIP, so the discrepancy cannot be checked without it. Q21, Q37, Q48 have notation flags still open.
- G6. Browser-driven edit persistence (click a dropdown, press Verify, reload, see it saved) was only checked via Streamlit AppTest, not by a real browser edit.
- G7. Built on Python 3.10; target is 3.12+. Not verified on 3.12.
- G8. Two real papers are extracted (2025 CS-1 and 2026 CS-1); only 2026 is classified. Other years or sessions may need extraction tuning. Do not import more years until `drift-check` is validated on at least two layouts.
- G9. Model names change. `GEMINI_MODEL` and `OPENAI_MODEL` have no assumed default; `GROQ_MODEL` defaults to `openai/gpt-oss-120b`. Check current official model lists before use.

## 2. Phase A: install and baseline

1. Detect OS. Install Python 3.12+ if missing (pyenv, uv, brew, apt or the python.org installer, whichever fits). Install Docker (Docker Desktop, or Docker Engine + compose plugin) if missing. If installing Docker needs admin rights or a reboot, tell the human exactly what to run and continue with SQLite work.
2. `unzip`, `cd gate-cse-intelligence`, `python3.12 -m venv .venv`, activate, `pip install -r requirements.txt`. Fix any version conflicts (note PyMuPDF is pinned to 1.28.2 on purpose, because extraction results depend on it).
3. If `.env` does not exist, `cp .env.example .env`; if it exists, leave it as is. Never overwrite it. Leave all keys empty for now.
4. Back up the live DB BEFORE running tests or any baseline command. Stop any running app first. Do not use a raw `cp` on a live SQLite file (WAL files and open connections can give a torn copy). Use the SQLite backup API: `python - <<'PY'` with `src=sqlite3.connect('data/gate_cse.sqlite'); dst=sqlite3.connect('backups/gate_cse.<timestamp>.sqlite'); src.backup(dst)`, or `sqlite3 data/gate_cse.sqlite ".backup 'backups/gate_cse.<timestamp>.sqlite'"`. Then run `PRAGMA integrity_check` on the backup and record its row counts, including review_events and the verified count.
5. Make the working copy from that backup (`cp backups/<file> /tmp/gate_work.sqlite`) and set the URL in the environment so every child process (CLI, pytest, streamlit, Playwright) uses it: `export GATE_DB_URL=sqlite:////tmp/gate_work.sqlite`. Check it took effect (`python -m src.cli stats` must show the copy path/counts, and `.env` must not override it with another `GATE_DB_URL`). Everything below uses this copy unless a step says otherwise. The copy is for testing only and is never merged back.
6. Run `pytest tests/ -q`. Expect 81 passed. Investigate and report any failure (especially anything Python 3.12 related) before moving on.
7. Run `python -m src.cli llm-status`, `python -m src.cli validate`, `python -m src.cli stats`. Save outputs in `docs/handoff/baseline.txt`.
8. Start the app: `streamlit run app.py`. Open it in your browser and confirm all 8 screens load. (using the copy).

## 3. Phase B: PostgreSQL 17 + pgvector, real end to end (closes G1)

1. In `.env` set `POSTGRES_PASSWORD` to a strong random local value (generate it, do not print it into the report), and set `GATE_DB_URL=postgresql+psycopg://gate_user:<password>@127.0.0.1:5432/gate_cse`.
2. `docker compose up -d`; wait until the container is healthy (`docker compose ps`). Confirm image `pgvector/pgvector:pg17` and that `SELECT version();` says 17.x and `CREATE EXTENSION IF NOT EXISTS vector;` works (the migration should do this).
3. `alembic upgrade head`. Confirm tables, the pgvector extension, the tsvector FTS column and its GIN index exist.
4. Load the same data into Postgres without touching the SQLite file. Options: run the pipeline against Postgres from the raw files in `data/raw` (ingest, extract, keys), then re-create the 65 classifications and review state by exporting from SQLite and importing, or write a careful one-off migration script (`scripts/sqlite_to_postgres.py`) that copies every table including `review_events` and `provider_votes`. Pick whichever you can verify. Keep it idempotent.
5. Verify parity against the SQLite source you read: row counts per table equal; question counts per paper (expect 65 for 2025 CS-1 and 65 for 2026 CS-1, 130 total, if the source still says so); review and verified counts equal the CURRENT SQLite values (read them, do not hardcode 0); `review_events` and `provider_votes` copied in full; analytics matrix totals (marks) equal paper totals and drill-down question counts match the cell counts, noting that a cell's marks and its question count are different numbers; `python -m src.cli validate` clean; exports match `exports/*.csv` where the DB is unchanged (otherwise explain the diff).
6. Run the full pytest suite against Postgres (`GATE_DB_URL` set). Fix any Postgres-only failures (types, JSON columns, boolean/NULL handling, ordering).
7. Test real full-text search through the app's search box.
8. Restart the container and confirm data persists (volume `gate_pgdata`).
9. Add a short `docs/14_POSTGRES_E2E.md` with the exact commands that worked and the observed outputs. Update `docs/00_STATUS.md` G1 to "verified on <date>, PG <version>, pgvector <version>" only if it truly passed.

If Docker cannot run on this machine, do not fake it. Report G1 as still open and say why.

## 4. Phase C: real-browser UI test (closes G6)

Use Playwright (`pip install playwright && playwright install chromium`). Against the running app, on a COPY of the database (set `GATE_DB_URL` to a copy, not the real one):

1. Analysis Matrix: click a cell, confirm the contributing questions list matches the cell's question count (not its marks value; the matrix may show marks, check which), click a question, confirm Review Workspace opens on that question.
2. Review Workspace: change section/topic/concepts using the dropdowns, press "Verify with correction", reload the page, confirm the change and a `review_events` row persisted. Repeat for "Verify as-is", "Flag", and "Approve & next".
3. Approve Queue: select a few, confirm, check audit events written.
4. Take screenshots into `docs/screenshots/v7/`. Look at them for clipped text or broken layouts and fix UI issues you find (the LLM priority text must be fully readable).
5. Then discard the copy. The real DB remains unchanged by tests.

## 5. Phase D: live LLM classification, gated (closes G2)

Do this phase only after the human has (a) put at least one key in `.env`, (b) said external calls are OK, and (c) for any paid provider, named it and set a spend cap. Otherwise mark BLOCKED and skip to Phase E.

1. Check current official docs for each provider you will test: free-tier availability, current model IDs, rate limits, pricing. Record the URL and date you checked in `docs/13_LLM_SETUP.md`. Start with the free-capable routes if the human has keys for them:
   - Gemini: key from https://aistudio.google.com/apikey, set `GEMINI_API_KEY` and `GEMINI_MODEL` (a current model).
   - Groq: https://console.groq.com/keys, `GROQ_API_KEY`.
   - OpenRouter: https://openrouter.ai/keys, `OPENROUTER_API_KEY`, model ending `:free`.
   - Anthropic / OpenAI: paid; only with explicit human approval and cap.
2. `python -m src.cli llm-status` should show the key as set with no value shown.
3. For each provider, in order: run `classify --dry-run` (inspect the exact payload; confirm no secrets or anything beyond question text and taxonomy is sent), then the cost estimate (`classify --estimate-cost --price-in X --price-out Y` with prices from the provider's current page), then a **tiny live test**: `--provider <name> --sample 0.08` (sample is a fraction; 0.08 of 65 is about 5 questions; confirm the count from the dry-run), on a DB copy first.
4. Check: the response parses to the expected JSON contract; the topic IDs exist in `taxonomy.yaml`; confidence is in 0..1; errors (401, 404 model, 429 rate limit, timeouts) give clear messages and are recorded; failover to the next provider works and never crosses into paid without approval. Fix adapter bugs you find (real response shapes often differ from fakes) and add regression tests using recorded sanitized fixtures.
5. Run `classify-ensemble` on a small sample with two or more providers. Confirm `provider_votes`, agreement and combo score are stored and displayed, rows with combo < 0.5 are flagged for review, and legacy rows still show "no ensemble run recorded".
6. Measure quality honestly: compare each provider's pick with the 65 existing suggestions on the sampled questions and report agreement. Say clearly that the 65 are themselves unverified, so this is agreement, not accuracy. If the human provides a gold set later, compute real accuracy then.
7. Only after the tiny tests pass, and the human approves the printed estimate, run the full 65 on the real DB (backup first). Never overwrite human-verified rows; new model output must be stored as suggestions with provenance.
8. Report tokens used and, where known, cost per provider. Do not guess costs.

## 6. Phase E: plug-and-play improvements

Do these, keeping every change tested and the 81 existing tests green:

1. `scripts/setup.sh` (and a `setup.ps1` for Windows if easy): create venv, install, copy `.env.example` if no `.env`, run migrations, run tests, print next steps. It must never overwrite an existing `.env` or DB.
2. A `python -m src.cli doctor` command: checks Python version, deps, DB connectivity and type, migrations at head, taxonomy loaded, PDFs present, each provider's key presence and gate state, and prints PASS/WARN/FAIL with a fix hint. No secrets printed.
3. A `Makefile` or `justfile` with `setup`, `test`, `app`, `pg-up`, `pg-down` (down must not remove the volume), `backup`.
4. Make the LLM Classify screen show clear per-provider status (key set, gate state, last error, last success time) from the recorded attempts, not from key presence alone.
5. Make provider errors visible in the UI with a plain-language message and the fix.
6. Review Workspace: keyboard-friendly flow and a visible "N of 65 verified" progress counter.
7. Add a DB backup button/command that writes a timestamped copy.
8. Check the app on Python 3.12 and, if possible, 3.13 (G7).
9. Keep the README quickstart accurate and short. Update `docs/00_STATUS.md` with what is now verified versus still open.

## 7. Phase F: open data issues (G3 to G5: report and prepare only, do not resolve by decree; G3 human review is closed only by the human)

- G5: Re-run `drift-check` on 2026 CS-1 and record the result. Ask the human for the original auditor artifact (the file or message with the 52/10/3 comparison). If it is available, compare it with the local extraction and list each real difference in `docs/handoff/auditor-diff.csv`. If it is not available, say so and compare only what you can: re-extract with the pinned PyMuPDF, check against the official PDF pages, and report real differences found. Never invent rows and never force the numbers to match 52/10/3. For Q21, Q37, Q48, look at the source PDF page and propose the correct notation, but leave the DB unchanged. The human decides.
- G4: Leave 2025 unclassified. If asked, first confirm the extraction is sound (question and key counts, the reproducible Q59 repair).
- G8: Do not import other years. If the human supplies more papers, run `drift-check` first.

## 8. Final report (write to `docs/handoff/REPORT.md`)

Include:

1. Table of gaps G1 to G9: status (VERIFIED / FIXED / BLOCKED / OPEN), evidence (command and result), and date.
2. What you installed (names and versions).
3. Test results (SQLite and Postgres, Python versions) with counts.
4. Live LLM results per provider, or BLOCKED-NEEDS-KEY, with tokens and any cost actually incurred.
5. Files changed and why. Confirm the real DB was backed up and no human-verified rows changed.
6. A **human testing checklist** (10 to 15 items, click by click): start commands, open the matrix and drill down, correct and verify a question, approve a batch, run a dry-run classification, check LLM status, restart and confirm persistence.
7. A short list of questions that need the human's decision.

Deliver the updated project as a ZIP (original ZIP kept untouched) plus the report. Stop and wait for the human to test; they will send fixes one at a time.
