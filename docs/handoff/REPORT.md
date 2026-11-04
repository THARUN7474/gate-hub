# Handoff report: GATE CSE Intelligence v6 -> v7 (4 Nov 2026)

Everything marked VERIFIED was run on this machine during this session and its output was read. Anything not run is
labelled BLOCKED/OPEN. Evidence files: `docs/handoff/baseline.txt` (start), `final-state.txt` (end),
`notation-proposals.md`, `docs/14_POSTGRES_E2E.md`, `docs/15_DATA_ONBOARDING.md`, `docs/screenshots/v7/`.

## 0. Headline

**Deliverable:** `C:\Users\Tharun\Desktop\2027\gate-cse-intelligence-phase1-v7-20261104.zip` (3.8 MB: code, docs, manifests, 329 cached OCR pages,
the candidate DB, this report; **excludes** `.env`, `.venv` and your raw PDFs). The original v6 ZIP was not in the workspace (the project was already
unpacked at `gate-hub/`), so there was nothing to keep or overwrite; your pre-change DB snapshot is `backups/gate_cse.20261104-013036.sqlite`.
The working tree at `C:\Users\Tharun\Desktop\2027\gate-hub` is the same content, ready to run.

- **29 papers, 2011-2026, 1,885 questions, all reconcile to 65 questions / 100 marks.** 20 papers have an official key
  imported (1,300 keyed questions) with **0 key-vs-extraction marks mismatches**. 9 papers have no key file (named in the UI, never guessed).
- **PostgreSQL 17.11 + pgvector 0.8.7 in Docker works end to end** after fixing 5 real defects (see 2).
- **114 tests pass on SQLite, 113 on PostgreSQL 17 (+1 SQLite-only skip), Python 3.12.9 and 3.13.2.** Real-browser UI test: **49/49**.
- **Your live `data/gate_cse.sqlite` was not modified** (SHA-256 `80c7859f...` before and after everything). The full dataset is in
  `data/gate_cse.candidate.sqlite`; one command moves it into the live DB (section 7, item 2). Your 3 review events and 65
  classifications are identical in the candidate (checked row-by-row).
- **No live LLM call was made** (no API key in `.env`). The tooling for the first call is ready and tested offline (BLOCKED-NEEDS-KEY).
- **Nothing is human-verified.** I verified 0 questions on your behalf. All synthetic UI clicks used reviewer `TEST-AUTOMATION`, on a
  throwaway copy that was deleted.

## 1. Gaps G1-G9

| Gap | Status | Evidence (command -> result) |
| --- | --- | --- |
| G1 Postgres 17 + pgvector via Docker | **VERIFIED / FIXED** 4 Nov | `docker compose up -d` -> `PostgreSQL 17.11`, `vector 0.8.7`; `alembic upgrade head` -> `0005 (head)` (it **crashed before my fix**); `sqlite_to_postgres.py` -> all 13 tables match by content checksum, 2nd run +0 rows; `verify_postgres.py` 10/10; restart keeps data; `pg_dump` -> restore into scratch DB -> 29/1885/3 rows. docs/14 |
| G2 live LLM calls | **BLOCKED-NEEDS-KEY** | `llm-status`: no key set. Ready and tested offline: `classify --dry-run`, `--estimate-cost` (all 1,885 questions = ~0.89M input + 0.47M output tokens, measured), `classify-compare`, error explanations. First-run procedure: docs/13 |
| G3 human review | **OPEN (only you can close it)** | live DB: 65 suggestions, 0 verified, 3 audit events (read from the DB, not assumed). I verified nothing |
| G4 2025 CS-1 unclassified | **OPEN by policy** (extraction now sound) | 2025-CS1: 65 q / 100 marks, key 65/65 with MSQ types fixed, 61 questions' fused page-headers cleaned (in the candidate). Still unclassified and excluded from analytics, as are the other 27 new papers |
| G5 auditor discrepancy 52/10/3 | **PARTIAL** | `papers-drift`: 2026-CS1 = 65 exact on Py3.12.9 / PyMuPDF 1.28.2 (as docs/12 said). Auditor's artifact still not supplied -> cause still unexplained. Q21/37/48 proposals in `notation-proposals.md`: my reading of the overbars reproduces the official keys A;C / B / B;D by computer evaluation. DB unchanged |
| G6 real-browser edit persistence | **VERIFIED** 4 Nov | `scripts/ui_browser_test.py` -> 49/49: click edit -> DB row -> **page reload** -> still saved, for Verify with correction / as-is / Flag / Approve & next / batch approve; `review_events` reviewer = `TEST-AUTOMATION`. It found a real bug (dropdown snapped to Q1 after any deep link) - fixed |
| G7 Python 3.12 / 3.13 | **VERIFIED** | `pytest` -> 114 passed on 3.12.9 **and** 3.13.2 |
| G8 other years / layouts | **VERIFIED / DONE** | `papers-probe` 29/29 reconcile; `papers-drift` 28/29 byte-identical (1,884/1,885 questions), the one difference explained (2025-CS1 Q59, a row a repair script touched earlier). 7 layout families. 2007-2010 deliberately skipped |
| G9 model names | **OPEN (not re-checked)** | No model default is assumed (GEMINI/OPENAI required, GROQ default `openai/gpt-oss-120b`). I did **not** re-check provider model lists today (no key => Phase D skipped); last checked 3 Nov. Re-check before setting a model |

## 2. Real defects found (and fixed, each with a regression test)

1. `alembic upgrade head` crashed on a fresh DB (`DuplicateColumn regions_json`): the migration chain was never run on current code.
2. `classification_runs.provider` was `VARCHAR(20)`; `auto` writes `auto:gemini+openrouter` -> would crash on the first real multi-provider run on Postgres.
3. CSV exports had no ORDER BY -> differed between SQLite and Postgres.
4. The Streamlit app leaked an `idle in transaction` DB session per rerun (hung the Postgres test suite; would pile up locks in real use).
5. **A live LLM run would have added a second classification row to each of the 65 existing 2026 suggestions**, double-counting 2026 in every matrix. Runs now skip any question that already has a classification; `--reclassify` replaces unverified ones with an audit event.
6. "Approve & next" would have walked through ~1,800 unclassified questions; navigation is now scoped to questions with a suggestion awaiting a decision.
7. Browser-only bug: the Question dropdown reset to Q1 after any link (widget identity depended on a computed `index`).
8. Existing 2025-CS1 rows had page headers fused into option text (regex knew "Organizing" not "Organising"); 13 MSQ questions were typed MCQ.
9. A marks-regex of mine matched the word "correct" in ordinary stems (caught by drift-check on 2025 Q25) - restricted.
10. My boilerplate stripper removed top-of-page question labels (`Question Number : 51`) in 2017 - fixed (caught by the reconciliation gate).

## 3. What I installed

| Item | Version | Why |
| --- | --- | --- |
| Python (via `uv python install`) | 3.12.9 (project), 3.13.2 (compat test only) | target is 3.12+; machine only had 3.11.3 |
| `.venv` packages | streamlit 1.66.1, sqlalchemy 2.1.6, alembic 1.20.1, psycopg 3.3.7, **pymupdf 1.28.2 (pinned)**, pdfplumber 0.11.10, pydantic 2.14.2, pandas 3.1.0, plotly 7.1.0, typer 0.27.3, pytest 9.2.0, reportlab 5.1.0, openpyxl 3.1.5 | requirements.txt |
| OCR | rapidocr 3.10.0, onnxruntime 1.31.1, numpy 2.5.4 | scanned years; pip-only, no admin install |
| Browser test | playwright 1.64.1 + Chromium headless shell 156.0.8078.4 | G6 |
| Docker image | `pgvector/pgvector:pg17` (627 MB); Docker Desktop 29.9.2 (you started it) | G1 |
| Agent skills (global, from skills.sh) | `obra/superpowers`: systematic-debugging, verification-before-completion; `anthropics/skills`: webapp-testing; `streamlit/agent-skills`: developing-with-streamlit; `supabase/agent-skills`: supabase-postgres-best-practices | I used webapp-testing's approach for G6; skipped the many mirror repos of "superpowers" from unknown authors |

`.env` was created from the template (it did not exist) with a random local Postgres password (not printed anywhere). No API keys.

## 4. Test results

| Run | Result |
| --- | --- |
| SQLite, Python 3.12.9 | **114 passed** (81 original + 33 new) |
| PostgreSQL 17.11 (`GATE_TEST_DB_URL`, DB `gate_test`) | **113 passed, 1 skipped** (SQLite-only test) |
| SQLite, Python 3.13.2 | **114 passed** |
| `ui_apptest.py` (Streamlit AppTest, copy of candidate DB) | all checks passed |
| `ui_browser_test.py` (real Chromium, copy of candidate DB) | **49/49** |
| `papers-probe` | 29/29 reconcile (65 q, 100.0 marks) |
| `papers-drift` | 28/29 identical; Q59 explained |
| `verify_postgres.py` | 10/10 |
| `doctor` (candidate) | 15 pass, 2 warn (no API key, no external-call consent: intentional), 0 fail |

## 5. Live LLM results

**BLOCKED-NEEDS-KEY** for every provider (gemini, groq, openrouter, anthropic, openai). No request left this machine; tokens used = 0; cost = $0.
`GATE_LLM_ALLOW_EXTERNAL` and `GATE_LLM_FREE_PLAN_CONFIRMED` are 0. What is ready: docs/13 "first live run" (dry-run -> estimate -> compare on ~5 questions ->
small real run), the per-provider status panel, and plain-language error help. Honest limit: the adapters have still only met fake transports.

## 6. Files changed and why

New: `src/extraction/ocr.py`, `src/ingestion/{registry,keypdf,paths}.py`, `src/{doctor,backup}.py`, `manifests/papers.yaml`,
`alembic/versions/0004,0005`, `scripts/{setup.ps1,setup.sh,dev.ps1,sqlite_to_postgres.py,verify_postgres.py,promote_to_live.py,ui_browser_test.py}`,
`Makefile`, `tests/test_v7_ingestion.py`, `docs/14,15`, `docs/handoff/*`, `docs/screenshots/v7/*`, `data/gate_cse.candidate.sqlite`, `data/extracted/ocr/` (329 cached OCR pages, 2 MB).
Changed: `src/extraction/{extract,render}.py` (rewrite, API-compatible), `src/ingestion/keys.py`, `src/db/{models,dev_upgrade}.py`,
`src/classification/classify.py` (skip-existing, reclassify, history, compare, error help), `src/analytics/{analyze,exports}.py`, `src/validation/{review,validate}.py`,
`src/cli.py` (+doctor, backup, papers-probe/load/drift, classify-compare), `app.py`, alembic 0002/0003 (idempotent), `tests/conftest.py` (+Postgres mode), `requirements.txt`, `.env.example`, README + docs 00/06/13.
**Data safety:** backup `backups/gate_cse.20261104-013036.sqlite` (integrity ok; taken before any command) is your pre-change snapshot; the live DB was only read.
Candidate vs backup: `review_events` 3 = 3 and `classifications` 65 = 65, identical row by row; 0 verified.
`validate` check "no unexplained NULL marks/type" was blunter than its own description (counted flagged NULLs as failures); it now fails only on *unflagged* NULLs.

## 7. Human testing checklist (click by click)

Open PowerShell in `C:\Users\Tharun\Desktop\2027\gate-hub`.

1. `.\scripts\dev.ps1 doctor` -> expect `0 fail`; 2 warnings about API keys are normal.
2. **Make the data live** (or skip and use the candidate): `.\scripts\dev.ps1 promote` shows "27 to be ADDED" and changes nothing. Then
   `.\scripts\dev.ps1 promote --yes`. It backs up first and must end with "every pre-existing review event unchanged: True | classification unchanged: True".
3. `.\scripts\dev.ps1 app` -> browser opens. **Pipeline Status**: 29 papers, 1885 questions, 1300 with keys, 65 classified, 0 verified.
4. Same screen: find 2019 (text_source `OCR`) and 2024 (`digital`); open "Back up the database" -> **Back up now** -> a file appears in `backups/`.
5. **Analysis Matrix**: click a number (e.g. ALGO 2026). The list length must equal the cell's question count (hover shows it); click a question -> **Review Workspace** opens on it.
6. **Review Workspace**: type your name in the sidebar *Reviewer name*. Set Paper = `GATE-CS-2026-S1`, Show = "suggestion awaiting my decision". Open a question, compare the source image with the suggestion; change **Topic** from the dropdown; click **Verify with correction**. Green banner appears; progress bar reads "1 of 65".
7. Press **F5** (reload). The question still shows verified. (This is the persistence check.)
8. On the next question press **Ctrl+Enter** (= Approve & next). Try **Alt+V** (verify as-is), **Alt+X** (flag), **Alt+N** (skip).
9. **Approve Queue**: tick Approve on 3 rows, tick "I reviewed...", click **Approve 3 selected**; they leave the queue.
10. Open a scanned question: Paper = `GATE-CS-2019-S1`, Question Q12: blue OCR notice, original image, "printed in the paper as CS 2". The image is right; if the text is wrong that is OCR (expected for formulas).
11. Open `GATE-CS-2013-S1` Q05: left panel says no official key is loaded (not guessed).
12. **LLM Classify**: every provider shows `no key`, `never`; click **Estimate cost** (all papers) and **Dry run** (mock): no network. The "Priority order" line must be fully readable.
13. Restart check: close the app, `.\scripts\dev.ps1 app` again: your reviews are still there. `.\scripts\dev.ps1 backup` once more.
14. Optional Postgres (after step 2): start Docker Desktop, `.\scripts\dev.ps1 pg-up`, `.\scripts\dev.ps1 pg-sync` (copies the live SQLite into Postgres and prints a per-table parity report), then `.\scripts\dev.ps1 test-pg` (113 passed expected).
15. Optional: `.\scripts\dev.ps1 browser-test` re-runs the automated browser test on a throwaway copy.
Send me anything odd as: screen name + question id + what you expected (a screenshot helps). I will fix one item at a time.

## 8. Decisions I need from you

1. **Promote now?** (`promote --yes`, backed up and self-checking). Until then the app on the live DB shows a one-time "upgrade needed" prompt.
2. **API key + provider**, to unblock classification: the only provider-stated $0 route is OpenRouter `:free`; Gemini/Groq free tiers depend on your account plan (you must attest it). Which one, and may I turn on `GATE_LLM_ALLOW_EXTERNAL=1` for the run?
3. **Which years to classify first?** 28 papers are unclassified (~0.89M input / 0.47M output tokens for everything, estimated). 2022-2026 first, or all?
4. **Keys for 2011, 2013 (4 sessions), 2015 (3), 2017-CS1?** The 2015 PDF prints a tick next to the correct option (unofficial, icon-based): do you want me to extract those as a *labelled, unofficial* key, or leave them missing?
5. **Multi-session years**: the matrix sums sessions (2013 shows 4x). I added an "average over sessions" switch (default off). Which default do you want?
6. **2007-2010** (photographed): try OCR on them too, or keep skipping?
7. **Auditor artifact** (the 52/10/3 comparison) - can you send it so G5 can be closed properly?
8. Apply the Q21/Q37/Q48 notation proposals to the database, or leave as is?
9. Make PostgreSQL the default DB (`GATE_DB_URL` in `.env`) or stay on SQLite for now? (I left `.env` on the SQLite default; the Postgres container is still running.)

---

## Addendum, 4 Nov 2026: owner decisions recorded (Phase 1 round 2)

Decisions given in-session by the owner, and what was done about each. Nothing below was run against the live database.

| # | Decision (owner) | Status |
| --- | --- | --- |
| 1 | Use the direct Gemini integration; pick a specific Flash-Lite model via `models`; no `-latest` alias | **Waiting for the key** (`setkey.cmd gemini`, then `.\scripts\dev.ps1 models`). Adapter has no default model and refuses to run without one |
| 2 | Owner attests the Google project has no billing linked and the model supports the free tier | `GATE_LLM_FREE_PLAN_CONFIRMED=1` set in `.env` on the owner's statement. The tool cannot verify it; only a live call shows whether the model is served on the free tier |
| 3 | Approve sending public question text + syllabus labels to Gemini | `GATE_LLM_ALLOW_EXTERNAL=1` set in `.env` on the owner's instruction |
| 4 | Pilot (5-10 questions) first, then 2022-2026, 2017-2021, 2011-2016; skip existing; checkpoint | Built + tested offline (`compare`, `classify --years`, skip-existing, `--checkpoint-every`). **Pilot not run: no key** |
| 5 | Do not add freellmapi | Not added |
| 6 | Promotion: dry run, verify counts / reviews / backup; promote only after explicit approval | Dry run + full rehearsal on a copy: PASS (docs/00_STATUS.md v7.3). **Real promotion not run; awaiting approval** |
| 7 | Keep the 9 key-less papers marked missing; produce a report | docs/16_MISSING_SOURCES.md |
| 8 | Compare Q21/Q37/Q48 with the PDF; inspect 2025 Q59; resolve without overwriting approved content | docs/handoff/extraction-discrepancies.md; Q59 completion script rehearsed on a copy, to be applied after promotion |
| 9 | Never mark AI labels human-verified; keep statuses distinct | Enforced and tested (`test_ai_runs_never_produce_human_verified_rows`); status words in docs/13 v7.3 |
| 10 | Show estimated vs actual tokens; enforce rate limits; retry conservatively; stop on billing/quota errors | Built + tested offline (`RunGuard`); not yet exercised against the real service |

**Correction to §8 item 3 above:** "~0.89M input / 0.47M output tokens for everything" came from a flat 400-token-per-call guess. The measured
fixed prompt is ~3,900 tokens per call (system prompt + the whole taxonomy are re-sent every call), so all 1,820 remaining questions are about
**7.2M input / 0.46M output tokens** (output excludes hidden reasoning). Per batch figures are in docs/13 "v7.3".

Resolved from the list above: item 4 (leave key-less papers missing; the 2015 ticks are NOT used as a key), item 8 (leave the stored text; documented),
item 2/3 (Gemini, owner-attested free plan, consent given). Still open: 1 (promote), 5, 6, 7, 9, and the pilot itself.

**Update, later on 4 Nov 2026:** owner said "do those changes and go ahead". Prompt v2 (options + position hint) was built and tested (170 tests) and re-piloted: 7/7
agreement, 0 errors (docs/13 "Prompt v2"). The real `promote --yes` was attempted and **blocked by the tool's permission check** (it writes to the live database), so it
has NOT run; the live file is byte-identical (sha16 80c7859f05b608e5). The three classification batches wait on it.
