# START HERE

GATE CSE Intelligence runs **on your own computer**. No account, no cloud. LLM calls are optional and
go only through your local FreeLLMAPI router.

Current state (5 Nov 2026): 29 papers / 1,885 questions (2011-2026) are in your database, with
first-pass labels on 1,867 of them. **0 are human-verified.** Your next job is reviewing the
120-question benchmark sample: `docs\22_BENCHMARK_REVIEW_GUIDE.md`. Full measured status:
`docs\CURRENT_STATUS.md`.

## The 30-second version

1. Double-click **`start.cmd`**.
2. Wait a few seconds. Your browser opens the app (if not, go to http://localhost:8501).
3. When you are done, **close the black window**. That stops the app. Your work is saved.

## Every time you reopen VS Code / the computer

Full version: `docs\19_LOCAL_RESTART_5_STEPS.md`.

1. Open Docker Desktop. FreeLLMAPI restarts by itself; check that http://127.0.0.1:3001 opens.
2. Open the folder `C:\Users\Tharun\Desktop\2027\gate-hub` in VS Code and open a terminal (Ctrl+`).
3. Run the health check: `.\.venv\Scripts\python.exe -X utf8 -m src.cli doctor`. You want 0 fail.
4. Start the app: `start.cmd` or `.\scripts\dev.ps1 app`.
5. After a review session, run `backup.cmd`. After changing code or docs, run `git add .`, then
   `git commit -m "..."`, then `git push`.

## The double-click files

| File | What it does | When |
| --- | --- | --- |
| **`start.cmd`** | Opens the app. Sets itself up first if this is a new machine. | every day |
| **`setup.cmd`** | One-time setup: Python 3.12, packages, settings file, tests, health check. Safe to re-run; never touches your `.env` or your database. | new machine only |
| **`backup.cmd`** | Saves a checked copy of your database into the `backups` folder. | after review sessions, before big changes |
| **`setkey.cmd`** | Saves a key into `.env` at a hidden prompt (never shown or printed). Usage: `setkey.cmd freellmapi`. | once per key |
| **`doctor.cmd`** | Health check: PASS / WARN / FAIL for everything, with the exact fix. Changes nothing. | when something looks wrong |
| `promote.cmd` | Loads every paper in `manifests\papers.yaml` into the database (preview, then type YES). **Done on 5 Nov 2026**; only needed after adding a new paper (e.g. GATE 2027). | rarely |

## First time on a new computer (fresh `git clone`)

The repository holds code and docs only. Your PDFs, database, `.env` and backups are NOT on GitHub.

1. Run `git clone https://github.com/THARUN7474/gate-hub.git` and open the folder.
2. Copy your PDFs into `data\raw\`, keeping the same layout (`papers\`, `keys\`, `syllabus\`).
3. Run `setup.cmd`. Then either:
   - copy your `data\gate_cse.sqlite` from the old computer (keeps your reviews), **or**
   - run `promote.cmd` to rebuild the papers from the PDFs. Labels and reviews are then not included.
4. Copy `.env.example` to `.env` and save your key with `setkey.cmd freellmapi`.
5. Run `doctor.cmd`, then `start.cmd`.

`setup.cmd` needs **uv** or **Python 3.12**. If it can't find either, run `winget install astral-sh.uv` and then run it again.

## What you will see in the app (left menu)

| Screen | Use it to |
| --- | --- |
| **Pipeline Status** | See every paper: questions, marks, official key yes/no, OCR or not, classified and verified counts. Has a "Back up now" button. |
| **About the Data** | See every paper 2007-2026: which PDF holds which session, where each answer key comes from. |
| **Question Browser** | Search and filter all questions. Click a row to open it. |
| **Analysis Matrix** | See section-by-year marks. **Click a number** to see exactly which questions make it up. |
| **Topic Report** | See which topics carry the most marks (history only, not a prediction). |
| **Review Workspace** | Check one question at a time: original image, text, official key, suggestion, the **AI review** box, five review checks, corrections, audit history. |
| **Approve Queue** | Approve several at once. Only questions whose five review checks you already saved and passed appear. |
| **LLM Classify** | Estimate, dry run, and gated runs through FreeLLMAPI. |
| **Glossary & Syllabus** | Look up what every short code (like `ALGO.SORT`) means. |

## How to review questions (the main job)

1. Type **your name** in the sidebar box "Reviewer name". Every decision is saved under that name.
2. Open **Review Workspace**. Set Show to **benchmark sample (gold review)** to start there, or pick a paper and
   "suggestion awaiting my decision".
3. The left side is the **original question image** (the truth). If the text, an option, the marks or the type is
   wrong, open **Correct the extraction**, fix it, give a reason, and save.
4. Decide the topic yourself. Then fix **Section / Topic / Concepts / What it tests** if needed. The yellow or blue
   **AI review** box is Claude's opinion from 5 Nov 2026. Read it after you decide; it is never a verification.
5. Answer the five **Review checks** (pass/fail). **Verify** is refused unless *Source fidelity* and *Primary topic*
   pass. Not sure? Use **Save without verifying** or **Flag**.
6. Keyboard: **Ctrl+Enter** = approve and next, **Alt+V** = verify as-is, **Alt+X** = flag, **Alt+N** = skip.

Scanned papers (2011, 2014, 2015, 2017, 2019, 2020, 2021) show a blue notice: their text came from OCR and can be
wrong in formulas. **Always trust the image over the text.** Only your click, after the review checks, makes
something "verified".

Full procedure: `docs\18_HUMAN_REVIEW_AND_SCORING.md`. Benchmark walk-through: `docs\22_BENCHMARK_REVIEW_GUIDE.md`.

## Where your data lives (none of it is in git)

| Thing | Location |
| --- | --- |
| Your database (all reviews) | `data\gate_cse.sqlite` (one file) |
| Backups (DB snapshots; old ZIPs in `backups\zips\`) | `backups\` |
| Your original PDFs | `data\raw\` (never modified) |
| Settings and keys | `.env` (private, never shared or printed) |
| Paper list / page ranges | `manifests\papers.yaml` (this one IS in git) |

**Never** copy another database file over `data\gate_cse.sqlite` unless you mean to replace your reviews. Use `backup.cmd`.

## AI: one key through FreeLLMAPI (optional)

1. Open http://127.0.0.1:3001 and go to **Keys**. Add your provider keys there, then copy the unified `freellmapi-...` key.
2. Run `setkey.cmd freellmapi` (or `.\.venv\Scripts\python.exe -m src.cli set-key freellmapi`), then `... -m src.cli llm-status`.
3. Smallest test (writes nothing):
   `.\.venv\Scripts\python.exe -X utf8 -m src.cli classify-compare freellmapi --paper-id GATE-CS-2026-S1 --sample 0.08`
4. Bigger runs go in as **proposals** (`classify --provider freellmapi --proposals`). Proposals live in a separate
   table and never overwrite labels or your reviews. In **LLM Classify**, always run Estimate and Dry run first.

Decision models (OpenAI Decisions, Jev) are separate, paid and off. Details for both:
`docs\23_LLM_ROUTER_AND_DECISION_MODELS.md`. Without any API, use `docs\20_CHAT_ASSISTED_CLASSIFICATION.md`
(chat batches) or `scripts\ai_review.py` (AI-review files).

## Optional: PostgreSQL 17

Not needed. To try it: start Docker Desktop, then run `.\scripts\dev.ps1 pg-up` and `.\scripts\dev.ps1 pg-sync`.
Details: `docs\14_POSTGRES_E2E.md`.

## If something goes wrong

| What you see | Do this |
| --- | --- |
| Window flashes and closes | Run `.\start.cmd` in PowerShell to see the message, or run `doctor.cmd`. |
| Cannot find Python | Run `winget install astral-sh.uv`, then `setup.cmd` again. |
| App says the database "needs a one-time upgrade" | Click **Back up the database, then upgrade it** (adds empty columns only). |
| Page is blank / "Cannot open the database" | Run `doctor.cmd`. On a fresh clone, the database must be copied or rebuilt (see above). |
| "Port 8501 is already in use" | The app is already open in another window. Use it or close it. |
| `llm-status` says no key | Run `setkey.cmd freellmapi`, and check that FreeLLMAPI is running (Docker Desktop open). |
| A question's text looks garbled | It came from a scan. Trust the image on the left. |
| A paper has no answer key | Expected for 9 papers (`docs\16_MISSING_SOURCES.md`). The app never guesses. |

## Command cheat sheet (PowerShell, in this folder)

```powershell
.\scripts\dev.ps1 help          # all commands
.\scripts\dev.ps1 doctor        # health check
.\scripts\dev.ps1 validate      # database consistency checks
.\scripts\dev.ps1 review-status # how many questions are classified / verified
.\scripts\dev.ps1 test          # run the automated tests
.\scripts\dev.ps1 backup        # same as backup.cmd
.\scripts\dev.ps1 llm           # which LLM providers have keys (never shows the keys)
.\.venv\Scripts\python.exe -X utf8 -m src.cli evaluate-benchmark   # accuracy vs your verified gold
```

More: `README.md` (overview), `docs\README.md` (index of all docs), `docs\04_CHECKLISTS.md` (what is done and what is open).
