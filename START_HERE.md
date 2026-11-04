# START HERE

## This package (review ZIP) - how to install

This ZIP deliberately EXCLUDES some files that were in your original archive. Do not
delete your original folder - merge instead:

1. Keep your existing `gate_hub` folder (it has your raw PDFs in `data/raw/`, your `.env`,
   `backups/`, and `data/extracted/`). If you don't have it, the original ZIP you sent has them.
2. Unzip this package and copy its contents OVER the existing folder (it updates code in
   `src/`, `app.py`, `scripts/`, `tests/`, `docs/`, `exports/`, and the staging database
   `data/gate_cse.candidate.sqlite`). The package does NOT CONTAIN `.env`, your raw PDFs,
   `backups/`, or the live `data/gate_cse.sqlite` at all - so merging cannot overwrite them
   (the live database file is simply not in the ZIP; merge-tested: a live database with
   newer reviews stays byte-for-byte identical).
3. **Done on 5 Nov 2026 (owner-approved):** promotion, label import, Q59 repair and the extractor
   repairs have been applied to the live database (29 papers / 1,885 questions). Do not re-run them.
   Next step for you: review the 120-question benchmark sample - see `docs\22_BENCHMARK_REVIEW_GUIDE.md`.
   Current state: `docs\CURRENT_STATUS.md`. LLM setup (FreeLLMAPI only): `docs\23_LLM_ROUTER_AND_DECISION_MODELS.md`.
4. `.env` stays on your machine only - never send it in a ZIP (it can hold API keys).



GATE CSE Intelligence runs **on your own computer**. No account, no cloud, no cost.

## The 30-second version

1. Double-click **`start.cmd`**.
2. Wait a few seconds. Your browser opens the app (if not, go to http://localhost:8501).
3. When you are done, **close the black window**. That stops the app. Your work is saved.

That is all you need day to day.

## The double-click files

| File | What it does | When |
| --- | --- | --- |
| **`start.cmd`** | Opens the app. Sets itself up first if this is a new machine. | every day |
| **`setup.cmd`** | One-time setup: Python 3.12, packages, settings file, tests, health check. Safe to re-run; never touches your `.env` or your database. | new machine only |
| **`promote.cmd`** | Loads the full 2011-2026 dataset into your real database. Shows a preview first, then asks you to type `YES`. Backs up first and proves your reviews are unchanged. | once |
| **`backup.cmd`** | Saves a checked copy of your database into the `backups` folder. | before big changes, or weekly |
| **`setkey.cmd`** | Saves an AI provider key into `.env` at a hidden prompt (it never shows or prints the key). Usage: `setkey.cmd gemini`. | once per key |
| **`doctor.cmd`** | Health check. Says PASS / WARN / FAIL for everything, with the exact fix. Changes nothing. | when something looks wrong |

## First time on this computer

1. Double-click **`setup.cmd`**. It needs internet and takes a few minutes.
   - It needs either **uv** or **Python 3.12**. If it says it cannot find them: open PowerShell and run
     `winget install astral-sh.uv`, then double-click `setup.cmd` again.
2. Double-click **`doctor.cmd`**. You want `0 fail`. Two warnings about "API keys" and "external calls" are normal until you add an AI key.
3. Double-click **`promote.cmd`**, read the preview, type `YES`. (If you only see 2 papers in the app, this is the step you skipped.)
4. Double-click **`start.cmd`**.

## What you will see in the app (left menu)

| Screen | Use it to |
| --- | --- |
| **Pipeline Status** | See every paper: questions, marks, whether it has an official key, whether its text came from a scan (OCR), what is classified and verified. Has a "Back up now" button. |
| **About the Data** | Every paper 2007-2026: how many per year, which PDF holds which session, where each answer key comes from, what is loaded. |
| **Question Browser** | Search and filter all questions. Click a row to open it. |
| **Analysis Matrix** | Section-by-year marks. **Click a number** to see exactly which questions make it up, then click a question to open it. Tick "Average over sessions" so years with several papers (2013 had 4) are comparable. |
| **Topic Report** | Which topics carry the most marks (history only, not a prediction). |
| **Review Workspace** | Check one question at a time: original image, text, official key, suggestion, five review checks, corrections, audit history. |
| **Approve Queue** | Approve several at once - only questions whose five review checks you already saved (and passed). |
| **LLM Classify** | Set up and run the AI classifier (needs an API key, see below). |
| **Glossary & Syllabus** | What every short code (like `ALGO.SORT`) means. |

## How to review questions (the main job)

1. Type **your name** in the sidebar box "Reviewer name". Every decision is saved under that name.
2. Open **Review Workspace**. Choose a Paper (for example `GATE-CS-2026-S1`) and "suggestion awaiting my decision".
3. Left side = the **original question image** (the truth), the extracted text and the official key. Look at the image first.
   If the text, an option, marks or type is wrong, open **Correct the extraction**, fix it, give a reason, save.
4. Right side = the machine's suggestion. Fix **Section / Topic / Concepts / Secondary topics / What it tests** if needed.
5. Answer the five **Review checks** (pass/fail): source fidelity, answer key, primary topic, concept depth, explanation.
6. Click **Verify with correction** (or **Verify as-is**). Verify is refused unless *Source fidelity* and *Primary topic* pass.
   Not sure? **Save without verifying** or **Flag**. The progress bar shows "N of 1,867 verified".
7. Open **Audit history** at the bottom to see every change to the question.
8. Keyboard: **Ctrl+Enter** = approve and go to next, **Alt+V** = verify as-is, **Alt+X** = flag, **Alt+N** = skip.

Scanned papers (2011, 2014, 2015, 2017, 2019, 2020, 2021) show a blue notice: the text was read by OCR and can be wrong in
formulas. **Always trust the image over the text.**

Only a human click, after the review checks, makes something "verified". Nothing else ever does.
Full procedure and the meaning of each check: `docs\18_HUMAN_REVIEW_AND_SCORING.md`.
Where the suggestions came from: `docs\17_CLASSIFICATION_PROVENANCE.md` (the first 65) and
`docs\handoff\classification-audit-v2.md` (the other 1,802 - topic-level first pass).

## Where your data lives

| Thing | Location |
| --- | --- |
| Your database | `data\gate_cse.sqlite` (one file) |
| Backups | `backups\` |
| Your original PDFs | `data\raw\` (never modified) |
| Settings and keys | `.env` (private, never shared or printed) |
| Paper list / page ranges | `manifests\papers.yaml` |

**Never** copy another database file over `data\gate_cse.sqlite`; you would lose your reviews. Use `promote.cmd` / `backup.cmd` instead.

## Classifying more questions WITHOUT an API key (ChatGPT / Claude chat)

All 29 papers now carry a first-pass suggestion: **1,867 of 1,885 questions classified** (1,490 suggested,
377 flagged - none human-verified) and **18 software-engineering questions deliberately left UNCLASSIFIED**
(the taxonomy has no software-engineering topic; extending it is your call). The first pass is
**topic-level only**: no per-question "what it tests" prose, no concept detail (except 113 keyword-backed
rows), no prerequisite lists - those come from the API proposals pass below or from your review.
You can still use your own chat to add detail, 20 questions at a time:

1. `.\scripts\dev.ps1 chat-export --years 2022-2026` - makes a folder in `exports\chat_batches\`.
2. Paste its `prompt.md` into a new chat and attach the pictures from its `images` folder.
3. Save the chat's JSON reply as `answers.json` in that folder.
4. `.\scripts\dev.ps1 chat-import "<folder>" "<folder>\answers.json" --model "ChatGPT ..."` checks it (changes nothing); add `--yes` to import.
5. Review the new suggestions in the Review Workspace. Details: `docs\20_CHAT_ASSISTED_CLASSIFICATION.md`.

Imports are always suggestions, never verified, and never overwrite anything you corrected or verified.

## Optional: AI classification through an API (needs a key)

To classify unattended you need an API key:

1. Get a key (links and the exact steps are in `docs\13_LLM_SETUP.md`), then double-click **`setkey.cmd`** and type `gemini`. Paste the key when asked: nothing shows on screen and it is saved only in `.env`. **Never paste a key into a chat or screenshot.** Next, `.\scripts\dev.ps1 models` lists the models your key can use.
2. In `.env` set `GATE_LLM_ALLOW_EXTERNAL=1` only when you are ready: question text then leaves your computer.
3. In the app: **LLM Classify**. Always do **Estimate cost** and **Dry run** first, then a tiny test, then the full run.
4. Run API classification as **proposals**: `classify --provider <name> --proposals` writes each provider's
   answers to a SEPARATE table - it never overwrites the existing agent labels or your review decisions.
   `proposals-report` then shows, per provider, how often it agrees with the current labels and which
   still-unclassified questions it covers.
   Status (4 Nov 2026): your Gemini key is valid and lists models (gemini-3.8-flash is on the free tier),
   but every inference attempt so far returned HTTP 503 ("high demand") - **no question has been
   classified by API yet**. Cause and duration unknown; no automatic retries happen.

## Optional: gold benchmark + priority review (v11, fully local)

1. `python -m src.cli benchmark-sample` writes 120 stratified sample rows (every paper, both mark values)
   marked `pending_user_review`. It never assigns labels. In the Review Workspace choose
   **Show: benchmark sample (gold review)** to walk just the sample; verifying a sampled question
   (same rubric as always, here or in the Approve Queue) records your label as its benchmark gold
   automatically - nothing is auto-approved.
2. In the Review Workspace, set **Order: review priority first** to walk questions in decision order:
   taxonomy gaps, classifier-flagged, low-confidence, OCR problems, provider disagreements, then the rest,
   with a 5% spot-check of verified rows at the end.
3. `python -m src.cli evaluate-benchmark` then reports accuracy and calibration against your verified gold
   only. Before any gold exists it says so plainly instead of printing made-up numbers.

Nothing is ever sent anywhere, and nothing is ever charged, unless you do these steps.

## Optional: PostgreSQL 17 (the "big database" option)

Not needed to use the app. If you want it: start **Docker Desktop**, then in PowerShell:
`.\scripts\dev.ps1 pg-up` then `.\scripts\dev.ps1 pg-sync`. Details and proof: `docs\14_POSTGRES_E2E.md`.
`.\scripts\dev.ps1 pg-down` stops it and keeps the data.

## If something goes wrong

| What you see | Do this |
| --- | --- |
| Window flashes and closes | Open PowerShell in this folder and run `.\start.cmd` to see the message, or double-click `doctor.cmd`. |
| "Setup did not finish" / cannot find Python | Run `winget install astral-sh.uv`, then `setup.cmd` again. |
| App says the database "needs a one-time upgrade" | Click **Back up the database, then upgrade it** (adds empty columns only), or run `promote.cmd`. |
| You only see 2 papers | Run `promote.cmd` once. |
| Page is blank or says "Cannot open the database" | Run `doctor.cmd`. If you use PostgreSQL, start Docker Desktop first. |
| "Port 8501 is already in use" | The app is already open in another window. Use that one, or close it. |
| A question's text looks garbled | It came from a scan. Look at the image on the left; that is correct. |
| A paper has no answer key | Expected for 2011, 2013, 2015, 2017-CS1 (no key file was supplied). The app says so; it never guesses. |
| Anything else | Run `doctor.cmd` and send me the output, plus the screen name and question id. |

## Command cheat sheet (PowerShell, in this folder)

Restarting safely (stop only this app, back up, preview promotion, start): `docs\19_LOCAL_RESTART_5_STEPS.md`.

```powershell
.\scripts\dev.ps1 help          # all commands
.\scripts\dev.ps1 doctor        # health check
.\scripts\dev.ps1 validate      # database consistency checks
.\scripts\dev.ps1 review-status # how many questions are classified / verified
.\scripts\dev.ps1 chat-export   # a question batch for ChatGPT/Claude chat (no API key)
.\scripts\dev.ps1 test          # run the 198 tests
.\scripts\dev.ps1 browser-test  # automated real-browser test on a throwaway copy
.\scripts\dev.ps1 probe         # re-read every PDF in memory and show the 65-question / 100-mark check
.\scripts\dev.ps1 backup        # same as backup.cmd
.\scripts\dev.ps1 llm           # which AI providers have keys (never shows the keys)
```

More detail: `README.md` (overview), `docs\00_STATUS.md` (what is verified and what is not),
`docs\15_DATA_ONBOARDING.md` (how the PDFs become questions, and how to add GATE 2027),
`docs\16_MISSING_SOURCES.md` (papers without official keys), `docs\README.md` (index of all docs).
