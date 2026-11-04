Everything from the handoff is done except the live LLM test, which needs an API key. All 29 papers from 2011 to 2026 now load and reconcile. Your live `data/gate_cse.sqlite` has not been modified.

**Papers and keys**
- Each paper has exactly 65 questions and 100 marks, 1,885 questions in total.
- 20 papers have official answer keys imported, and none of the key marks disagree with the extracted marks.
- 9 papers have no key file, and the app shows them as missing instead of guessing: 2011, 2013 (all four sessions), 2015 (all three) and 2017-CS1.
- The scanned years (2011, 2014, 2015, 2017, 2019, 2020, 2021) are read with OCR. Formulas in OCR text can be wrong, so the Review Workspace always shows the original PDF image next to the text.
- 2007–2010 are skipped, as you said.
- Where papers bundle several sessions in one PDF, the page ranges for each session are written down in `manifests/papers.yaml`.

**Tests**
- 114 tests pass on Python 3.12 and 3.13. 113 pass on PostgreSQL 17 in Docker; the one skipped is an SQLite-only test.
- A real-browser test passed 49 of 49 checks on a throwaway copy of the data: matrix drill-downs, verify/flag/approve, keyboard shortcuts, and everything still saved after a page reload.
- Re-extracting every paper from its PDF gave identical text for 28 of 29. The one exception is 2025 CS-1 Q59, a question a repair script had already touched.

**Bugs found along the way (details in the report)**
- `alembic upgrade head` crashed on a fresh Postgres database.
- A live LLM run would have added a second classification row to each of the 65 existing 2026 suggestions, double-counting 2026 in every matrix. Runs now skip questions that already have a classification.
- The Question dropdown snapped back to Q1 after clicking a link from the matrix. This only showed up in a real browser.

**What I did not do**
- The 65 existing suggestions still have 0 human reviews. I verified nothing on your behalf.
- No LLM call has been made, because `.env` has no API key.
- Only 2026 CS-1 is classified. The other 28 papers are extracted and keyed but unclassified.
- I did not find the cause of the outside auditor's 52 exact / 10 normalized / 3 changed result, because their original file isn't in the project. My re-extraction of 2026 CS-1 matches the stored text for all 65 questions.

Questions for you:
- Do you want to run `.\scripts\dev.ps1 promote --yes`? It puts the full dataset into your live database. It backs up first, and it checks that your existing review events and classifications are unchanged. Without it, the app on the live database only shows the old 2 papers. A plain `.\scripts\dev.ps1 promote` is a dry run that changes nothing.
- Which provider and API key should I use to start classifying, and may I turn on `GATE_LLM_ALLOW_EXTERNAL=1` (question text leaves your machine) for that run? OpenRouter `:free` models are the only route the provider itself lists as $0. Gemini and Groq free tiers depend on your account plan.
- Which years should be classified first? 28 papers are unclassified, and everything is about 0.89M input and 0.47M output tokens.
- Do you have official keys for 2011, 2013, 2015 and 2017-CS1?
- Can you send the auditor's file so I can close that discrepancy?

The report's section 7 has a 15-step click-through checklist, and section 8 has the full list of decisions. After promoting, start the app with `.\scripts\dev.ps1 app`. If anything looks wrong, `python -m src.cli doctor` explains it.

Files are in `C:\Users\Tharun\Desktop\2027\`:
- `gate-cse-intelligence-phase1-v7-20261104.zip` (excludes `.env` and your raw PDFs)
- `gate-hub\handoff-report\REPORT.md`
- `gate-hub\handoff-report\notation-proposals.md` (proposed notation for Q21/Q37/Q48; it reproduces the official keys; database unchanged)
- `gate-hub\docs\14_POSTGRES_E2E.md`
- `gate-hub\docs\15_DATA_ONBOARDING.md`

The Postgres container is still running; stop it with `.\scripts\dev.ps1 pg-down`, which keeps the data.



I added [START_HERE.md](START_HERE.md) and five double-click launchers in `C:\Users\Tharun\Desktop\2027\gate-hub\`, and tested each one except the real `YES` step in `promote.cmd`.

**To start the app, double-click `start.cmd`.** It opens your browser at http://localhost:8501, and closing its black window stops the app. It also sets itself up if this is a new machine.

| File | What it does |
| --- | --- |
| `start.cmd` | Opens the app. |
| `setup.cmd` | One-time setup. It never overwrites your `.env` or your database. |
| `promote.cmd` | Loads the full 2011–2026 dataset into your real database. It shows a preview, then waits for you to type `YES`; anything else cancels. |
| `backup.cmd` | Makes a checked backup copy of your database in `backups\`. |
| `doctor.cmd` | Health check with the fix for each problem. It changes nothing. |

`START_HERE.md` is plain language and covers:
- the 30-second version;
- the first-time order (`setup.cmd`, then `doctor.cmd`, then `promote.cmd`, then `start.cmd`);
- what each of the 8 screens is for;
- how to review questions, including the keyboard shortcuts;
- where your data lives;
- optional AI keys and Postgres;
- a table of symptoms and fixes.

**What I tested**
- `start.cmd` started the app, the health check answered, and the port was freed afterwards. I ran it against the candidate copy, so your real database wasn't even opened.
- `doctor.cmd` ran and reported 15 pass, 2 warn, 0 fail.
- `promote.cmd` showed the preview and cancelled cleanly when I answered "no". Your real database was byte-identical afterwards.
- `backup.cmd` produced a verified backup of the candidate copy, and I removed that test file.
- I confirmed `winget install astral-sh.uv` is a real package, since the guide tells new machines to use it if Python is missing.

**Still open**
- Your real database still has only 2 papers. Run `promote.cmd` once and type `YES` to load the full dataset; it backs up first.
- The ZIP on your Desktop now includes the guide and the launchers, and still excludes your `.env` and raw PDFs.
- In PowerShell, run them as `.\start.cmd`.



The project root is now clean. The analysis and handoff documents have their own folders under `docs/`, and nothing was lost.

**Root now holds only what you run:** the five `.cmd` launchers, `README.md`, `START_HERE.md`, `app.py`, the config files, and the folders `src/`, `scripts/`, `tests/`, `alembic/`, `manifests/`, `data/`, `exports/`, `backups/`, `docs/`.

**Moved**
- `ANALYSIS.md` → `docs/analysis/ANALYSIS.md`. The `analyze` command now writes there by default, and I regenerated it. The matrix numbers are unchanged; the coverage section now says 29 papers instead of 1, because the old file predated the full data load.
- `GATE-v6-agent-handoff.md`, `REPORT.md`, `notation-proposals.md`, `baseline.txt`, `final-state.txt` → `docs/handoff/`. The `handoff-report/` folder is gone.
- `docs/AGENT_OUTPUTS/session1.md` → `docs/handoff/session-logs/session1.md`. This is a saved copy of my last summary. It has garbled characters and old paths; I left it unchanged as a historical record.

**Updated**
- Path references in `README.md`, `START_HERE.md`, `docs/00_STATUS.md`, `docs/09_REAL_PAPER_VALIDATION.md`, the report, and the handoff spec now point at the new locations. I also edited the spec's two path instructions, which the agent would otherwise follow to the old folders.
- `docs/README.md` is now a proper index. It separates start-here guides, numbered reference docs, the generated analysis, and handoff material.
- `README.md` has a "Where things are" table.
- `.gitignore` now excludes `backups/` and `*.pgdump`.

**Checks**
- All 114 tests pass after the change.
- Every relative link in the main guides resolves.
- The only remaining old-path mention is the historical session log.
- The ZIP on your Desktop was rebuilt with the new layout and contains no `.env`, `.venv`, or raw PDFs.
- The live database is still byte-identical to the original.

**Left alone, your call**
- `end goal referenes/` keeps its misspelled name, since it's your own material. Renaming it is a one-line change if you want.
- The first listing showed an empty `gate-cse-intelligence-phase1-v6/` folder, but it isn't in the project now. I didn't delete it.
- I haven't made this a git repository. Say the word if you want one and I'll set it up.


I couldn't use your Gemini key yet, because the screenshot only shows its last four characters and it shouldn't go into chat anyway. So I built a safe way for you to give it to the app, and made no live Gemini call. Your live database, `.env` consent flags, and ZIP leak check are all unchanged.

Your message cut off at "so that we an…". I assumed you want to classify the unclassified questions with free LLMs; tell me if you meant something else.

**What I found**
- **freellmapi.co** is an open-source (MIT), self-hosted router. You run it in Docker (installed with `curl … | bash`), add your own provider keys, and it fails over between free tiers on `localhost:3001`. It pulls its model catalog from freellmapi.co twice a day, and its page has no privacy text. I did not integrate it. Our `auto` mode already fails over between Gemini, Groq and OpenRouter, and a router would hide which provider and plan each question went to. I wrote this up in `docs/13_LLM_SETUP.md` if you want to revisit it.
- **`gemini-skills-main.zip`** is Google's own Apache-2.0 pack. I extracted it into its own folder and read every file: no hooks. I installed one skill, `gemini-api-dev`, which is documentation only. I left out `gemini-api-cli` because its setup is `curl | bash`, and the live-voice and video skills because we don't need them. Its model list matches Google's official page.
- **Google's free-tier terms:** your content is used to improve Google's products and human reviewers may read it, and they say "Do not submit sensitive, confidential, or personal information." GATE questions are public exam text, so it's acceptable. A Google project with billing linked counts as paid.
- **Models:** the current IDs are `gemini-3.8-flash`, `gemini-3.5-flash-lite` and `gemini-3.1-flash-lite`. `gemini-2.5-*` is re-routed on 1 Dec 2026. Google's pages don't say which models the free tier covers, so only a real call will show.
- **Don't use `gemini-flash-latest`** (the model in your screenshot) for the long run. It changes when Google ships a new version, which would mix model versions across questions.
- **I removed a stale `gemini-2.5-flash` default** from our Gemini adapter. It's an unused constant, but that model is deprecated.
- **API call style:** our adapter still calls `generateContent`. Google's pages don't say it is being retired, and your AI Studio snippet still uses it, so I did not migrate to the newer Interactions API.

**What I added**
- `setkey.cmd gemini` asks for the key at a hidden prompt and writes it only to `.env`. It never prints the key and never turns on any consent flag.
- `.\scripts\dev.ps1 models` lists the model IDs your key can see, sending only the key to Google and no questions.
- 9 new tests; the full suite is at 123 passing. I tested both commands only with no key and no network. The model listing has been tried only against fake responses.

**Your next steps**
1. Run `setkey.cmd gemini` and paste the key at the hidden prompt.
2. Run `.\scripts\dev.ps1 models`, then pick a `-lite` model and save it with `python -m src.cli set-key gemini --model <id>`.
3. Decide on the two consents below, set them in `.env` yourself, and I'll run a dry run, a cost estimate and a comparison on about 5 questions (about 8% of 65) before any real run.

**Questions for you**
- Is the Google project behind this key free, with no billing linked? Only then set `GATE_LLM_FREE_PLAN_CONFIRMED=1`.
- Are you fine with sending question text to Gemini under those free-tier terms? Only then set `GATE_LLM_ALLOW_EXTERNAL=1`.
- Which papers should we classify first: 2022–2026, or all 28?
- Do you still want freellmapi added as an extra provider anyway?

The ZIP on your Desktop was rebuilt with all of this; the new files are `setkey.cmd` and `tests/test_llm_helpers.py`.

The pilot has not run, because `.env` still has no `GEMINI_API_KEY`. So there is no pilot accuracy, API cost or error count to report yet, and I won't invent any. I did everything that doesn't need the key.

**Your next step:** run `setkey.cmd gemini` and paste the key at the hidden prompt, then run `.\scripts\dev.ps1 models` and tell me which `-lite` model to pin. After that I run the pilot and stop to report before any batch.

I set `GATE_LLM_ALLOW_EXTERNAL=1` and `GATE_LLM_FREE_PLAN_CONFIRMED=1` in `.env`, on your statements in this chat. I can't verify that the Google project has no billing. Only a real call will show whether your model is served on the free tier.

**My earlier token estimate was wrong.** The full run is about **7.2M input tokens**, not 0.89M. Every call re-sends the whole taxonomy, about 3,900 tokens each. The batches are 455 questions for 2022–2026, 455 for 2017–2021 and 910 for 2011–2016. Whether the free tier covers that depends on limits that Google shows only inside AI Studio. A run that hits a daily limit stops cleanly and resumes later.

**Classifier (your points 4, 9 and 10).** Before, it had no rate limit, retry, quota handling or token counting, and a malformed reply could crash the run.
- **Pacing and retries:** it waits to stay under `GATE_LLM_RPM` (default 8 requests a minute), retries once for bad JSON and twice for server errors, and waits out a per-minute 429 once.
- **Stops:** it stops with exit code 3 on 401/402/403/404, billing wording, a daily quota, a repeated 429, 5 failed questions in a row or `--max-calls`. The question in progress is left untouched.
- **Resume and usage:** it commits every 10 questions, skips already-classified questions so a re-run resumes, and records the provider's actual token counts.
- **Selection:** `--years` picks the year bands, and the pilot sample is spread across the paper, not the first questions (those are all General Aptitude).
- **Never verified:** nothing a classification run writes can be marked human-verified, and a test enforces it. There is no separate "AI-reviewed" status; the app has suggested, flagged and verified.
- **One existing test changed:** it expected 6 failing calls in a row, and a run now stops after 5.
- **Tested:** 158 tests pass on SQLite and 157 on PostgreSQL 17, all with fake network replies. The pacing and error handling have never run against Google's real service.

**Promotion (point 6): rehearsed, not run.** I ran the full promotion on a copy of your live database. The copy ended up identical to the staging database: 29 papers, 1,885 questions, 1,300 keys and 5,542 options. Your 3 review events and 65 classifications were unchanged. The live file is byte-identical to before. Say the word and I'll run `promote --yes`.

**Extraction discrepancies (point 8).** Details are in [extraction-discrepancies.md](docs/handoff/extraction-discrepancies.md).
- **Q21, Q37, Q48:** I compared the stored text with the original PDF and with a fresh extraction. The stored text is identical to the PDF text layer. Evaluating the printed options reproduces the official keys: A and C for Q21, B for Q37, B and D for Q48.
- **Why I left them alone:** the gaps are how overbars and tables display, not content. Rewriting the text would break the check that stored text matches the PDF. The flags stay until you review them.
- **2025 Q59:** this is the one real difference out of 1,885 questions. The stored text is cut off 80 characters early, before the state-table values. The table gives 5 minimal states, matching the key.
- **The fix:** I wrote an audited repair that only appends the missing tail and never touches a verified question. On the copy, all 29 papers then re-extract identically. It needs the schema upgrade, so run it after promotion: `.\scripts\dev.ps1 repair-text --paper GATE-CS-2025-S1 --yes`.
- **Auditor's 52/10/3:** still unexplained, because their original file isn't here.

**Missing sources (point 7).** [16_MISSING_SOURCES.md](docs/16_MISSING_SOURCES.md) lists the 9 papers without keys: 2011, 2013 (4 sessions), 2015 (3) and 2017 CS-1. Nothing was invented; the answer ticks printed in the 2015 PDF are not used. 11 of those questions have no question type and go to review.

Questions for you:
- Do you approve `promote --yes`? Classification batches should run on the live database after promotion, and promotion doesn't copy classifications.
- Should the pilot use `GATE_LLM_RPM` at the default 8, or do you want to set it from the rate-limit page in AI Studio first?

The ZIP on your Desktop is rebuilt with all of this and contains no `.env`.

The pilot ran and worked: all 7 answers were valid, but it found two gaps I'd like your decision on before any batch. I made 7 Gemini calls and 1 model-list call, and nothing was written to either database.

**Setup.** Your key works. I pinned `gemini-3.5-flash-lite` in `.env`, a stable Flash-Lite ID and not a `-latest` alias, so tell me if you prefer `gemini-3.1-flash-lite`. The Google calls went to the free-tier endpoint. I can't see your billing, so "free" rests on your own statement. Please check AI Studio's usage view: it should show 7 requests from this session and no charges.

**Pilot result.** The test used 7 questions of 2026 CS-1, spread evenly across the paper.

| Check | Result |
| --- | --- |
| Valid JSON and shape | 7 of 7 |
| Valid taxonomy ids (section, topic, concepts, prerequisites) | 7 of 7 |
| Errors / retries / quota or billing stops | 0 / 0 / none |
| Topic agreement with the existing suggestions | 6 of 7 (86%) |
| Actual tokens | 41,968 in, 1,271 out (about 5,995 and 182 per call) |
| Estimated tokens for the same run | about 28,000 in, 1,750 out |
| Actual cost | none visible to me; check the AI Studio usage view above |

- **Accuracy:** the 86% is agreement with 65 suggestions that no human has verified, not accuracy. Seven questions can't estimate accuracy anyway.
- **Only disagreement, Q05:** it needs your manual review. The paper prints it as "Q 5" in the General Aptitude block, and the existing label is GA.AA. Gemini filed it under discrete maths, because the classifier sees only the question text, not where the question sits in the paper.
- **Tokens:** the full run is about **10.9M input tokens** over roughly 3 h 50 min at 8 requests a minute, not the 7.2M I gave you earlier. I've recalibrated the estimator from the pilot, and 158 tests still pass. The three planned batches work out to about 2.7M, 2.7M and 5.5M input tokens.

**Two gaps I found, which I'd like your decision on.**
1. **Options are never sent to Gemini.** The code passes an empty option list, so the model classifies from the question stem alone. Q05 is a case where the options would likely help.
2. **No hint for General Aptitude questions.** Each paper has 10 of them, and they could be filed under CS topics, which would inflate CS marks in the analytics.

Fixing both changes the prompt (a new version, and a re-pilot with a small cost). I recommend doing it before the batches. I haven't done it unasked, because it changes what the 65 existing labels are compared against.

**Questions for you:**
- Do you want me to add the options and a General Aptitude hint, then re-pilot, or run the batches as they are?
- Do you approve `promote --yes`? Batches should run on the live database after promotion, since promotion doesn't copy classifications.

The ZIP on your Desktop is rebuilt and checked: no `.env`, and your key appears nowhere in it. The live and staging databases are byte-identical to before the pilot.


I've made the changes and the re-pilot passed (7 of 7), but I haven't started the batches. The promotion to your live database was **blocked by the tool's permission check**, because it writes to your live database. I haven't worked around it.

To your question: yes, only the options and a section hint are sent. Neither the key, the marks, nor the year or session goes into the prompt.

**Re-pilot.** It used the same 7 questions as before, with `gemini-3.5-flash-lite` and no writes anywhere.

| | Before (text only) | Now (options and hint) |
| --- | --- | --- |
| Topic agreement with the existing suggestions | 6 of 7 | **7 of 7** |
| Q05 (General Aptitude) | filed as discrete maths | **GA.AA, correct** |
| Errors, retries, quota stops | 0 | 0 |
| Tokens | 41,968 in, 1,271 out | 42,858 in, 1,215 out |

- **Caveat:** 7 questions isn't an accuracy figure, and the comparison is against labels no human has verified. The other four checks were also clean: all 7 answers were valid JSON, all taxonomy ids were valid, none were flagged and none need manual review.
- **Section hint:** I checked the layout of all 29 papers from their marks pattern. 21 put the GA block first (Q1–10) and 8 put it last (Q56–65), with none unclear. If a paper's pattern isn't recognised, no hint is sent.
- **Contradictions:** if Gemini's section contradicts the hint, the row is saved as flagged for you to review.
- **Cost:** about 127 extra tokens per call. The full run is now about 11.1M input tokens, roughly 3 h 50 min at 8 requests a minute.
- **Tests:** 170 pass on SQLite and 169 pass plus 1 skipped on PostgreSQL. All 12 new prompt tests use fake network replies.

**What's blocked and why.**
- **Promotion:** the batches need the 27 extra papers in your live database, so they wait on it. They also can't go into the staging database instead, because promotion doesn't copy classifications.
- **Safety:** the same promotion passed a full rehearsal on a copy, and it takes its own verified backup first. Your live database is byte-identical to before and `backups/` is untouched.
- **Q59:** its repair also needs the promoted database.

**Please run this in your own terminal** (it's your decision, and it takes about a minute):
```powershell
cd C:\Users\Tharun\Desktop\2027\gate-hub
.\scripts\dev.ps1 promote --yes
```
Alternatively, add a permission rule for it in Claude Code's settings and tell me, and I'll run it. Once it prints "DONE" with both "unchanged: True" lines, tell me and I'll do the rest in this order:
1. Complete Q59's text with the audited repair.
2. Back up again.
3. Classify 2022–2026 (about an hour), then check the flags and token usage.
4. Classify 2017–2021, then 2011–2016.

If the free daily quota runs out, a run stops cleanly and resumes later without redoing finished questions.

The ZIP on your Desktop is rebuilt and checked: no `.env`, and your key isn't in it.

All ten tasks are done except the real promotion, which still needs your approval. The app is running at http://localhost:8501 (HTTP 200), and your live database is byte-identical to before (`80c7859f05b608e5`). Because that database still has the old schema, the app opens on a one-time "Back up the database, then upgrade it" prompt. I didn't click it.

**Where the 65 GATE 2026 CS-1 classifications came from** (checked in the database and the scripts):
- An earlier coding agent read each question and wrote a hand-made table into `scripts/agent_classify_2026_cs1.py`. The database records this as `provider=agent-analysis`, `model=claude-agent-manual-v1`, `prompt_version=agent-v1`, with a note "NOT an LLM API integration run".
- A second agent pass (`scripts/curate_concepts_2026_cs1.py`) added concept tags and applied 2 outside-audit topic corrections, still as suggestions.
- They remain unverified because no human has checked them, and the confidence values (0.80–0.98) were chosen by the agent itself.
- Your draft's claims about this were all correct. Details are in `docs/17_CLASSIFICATION_PROVENANCE.md`.

**Test results (all run today)**

| Check | Result |
| --- | --- |
| Automated tests, SQLite | 188 passed |
| Automated tests, PostgreSQL 17 | 187 passed, 1 skipped (SQLite-only) |
| Real-browser test (on a throwaway copy) | 60/60 passed |
| `validate` | 10/10 on both databases (live checked on an upgraded copy) |
| `doctor` | 16 pass, 1 warn (old live schema), 0 fail |
| Drift check (re-extract every paper) | 28 of 29 papers identical; 2025 CS-1 Q59 differs |

**Database counts and coverage**

| | Live | Staging |
| --- | --- | --- |
| Papers / questions | 2 / 130 | 29 / 1,885 |
| Official key rows | 130 | 1,300 (9 papers have no key) |
| Classified | 65 | 65 (1,820 not classified) |
| Human-verified | **0** | **0** |
| Review checks saved | **0** | **0** |

**Changes**
- **Review screen** (`app.py`, `src/validation/review.py`): each question shows the original PDF region, the extracted text and the official key status. You can now correct the text, options, marks and type, and set secondary topics and "what it tests". The five review checks and the audit history are on screen.
- **Rule enforced everywhere:** a question can't be verified unless its five checks are saved with Source fidelity and Primary topic passing. This applies to the buttons, keyboard shortcuts, the batch queue and the command line.
- **Protection for your edits:** questions you've corrected or verified are never overwritten by a reload or a new classification run.
- **Chat workflow, no API key** (`src/classification/chat_batch.py`): `chat-export` writes a batch folder, and `chat-import` checks the reply and loads it as suggestions only, never verified.
- **Clearer errors:** command-line checks now explain an old-schema database in plain words instead of crashing.
- **Docs:**
  - New: `docs/17`–`20` (provenance, review guide, restart steps, chat workflow), a reconciliation note in your pack folder, and evidence images for the discrepancy work.
  - Updated: `README.md`, `START_HERE.md`, `docs/README.md`, `docs/00_STATUS.md` and `docs/04_CHECKLISTS.md`. An outdated "no live API call has been made" claim was removed.
  - Fixed: a few links to renamed key files.
- **New tests:** `tests/test_review_rubric.py`, `tests/test_chat_batch.py`, and an extended browser test.

**Q21/Q37/Q48 and Q59.** I re-ran the comparison against the live database.
- Q21, Q37 and Q48 match the PDF text exactly, and the printed options give the official answers. The only issues are how overbars and a table display.
- The outside auditor's 52/10/3 result is still unexplained, because their file isn't here.
- Q59 is **not fixed**: its stored text is still missing 80 characters of table values. The repair script only worked on a copy.

**Unresolved**
- Promotion of the live database.
- The Q59 repair, which needs the promoted database.
- All human review (0 of 65).
- Classification of the remaining 1,820 questions.
- The auditor's file, and official keys for 9 papers.

**How to run it yourself**
1. **Stop only this app.** Close the window that started it. If unsure, check port 8501 with the command in `docs/19_LOCAL_RESTART_5_STEPS.md`, and stop that process only if its command line is `streamlit run app.py` from this folder. Today nothing else was running there.
2. **Back up and check.** Double-click `backup.cmd`, then `doctor.cmd`; you want 0 fail. I made a backup today: `backups\gate_cse.20261104-140559.sqlite`.
3. **Preview.** Double-click `promote.cmd` and read the preview: 27 papers to add, plus one new column. Type anything other than YES to cancel.
4. **Promote, if you approve.** Run `promote.cmd` again and type YES. It backs up first and checks your existing reviews are unchanged. Then optionally run `.\scripts\dev.ps1 repair-text --paper GATE-CS-2025-S1` (preview), and again with `--yes` to fix Q59.
5. **Start and review.** Double-click `start.cmd` and open http://localhost:8501. Set your reviewer name in the sidebar, then open the Review Workspace. For each question: look at the image, fix anything wrong, answer the five checks, then Verify or Flag.

**Classifying more questions with ChatGPT, no API key**
1. Run `.\scripts\dev.ps1 chat-export --years 2022-2026`. It writes a folder under `exports\chat_batches\` containing `prompt.md` and an `images` folder. One 20-question batch from 2026 CS-2 is already there.
2. Paste `prompt.md` into a new chat and attach the images.
3. Save the chat's JSON reply as `answers.json` in that same folder.
4. Run `.\scripts\dev.ps1 chat-import "<folder>" "<folder>\answers.json" --model "ChatGPT …"`. This only checks the reply; add `--yes` to import.
5. Review the new suggestions in the Review Workspace. The full guide is `docs/20_CHAT_ASSISTED_CLASSIFICATION.md`.


The data inventory is now on the site and in the docs. There are **33 papers (exam sessions) across all 20 years, 2007–2026, in 24 question PDFs**. 29 of those papers are active (2011–2026) and 4 are deferred (2007–2010, as you asked).

| Group | Years | Papers (sessions) | Question PDFs | Papers with official key |
| --- | --- | --- | --- | --- |
| Deferred | 2007–2010 | 4 | 4 | 0 (not checked yet) |
| Archive | 2011–2020 | 19 | 11 | 10 of 19 |
| Recent | 2021–2026 | 10 | 9 (+9 separate key PDFs) | 10 of 10 |

**Year by year (2011–2026)**

| Year | Papers | How the PDFs are bundled | Where the key comes from |
| --- | --- | --- | --- |
| 2011 | 1 | 1 PDF, 1 paper (scan) | none |
| 2012 | 1 | 1 PDF, 1 paper | inside the question PDF |
| 2013 | **4** | **1 PDF, 4 sessions inside** | none |
| 2014 | **3** | **1 PDF, 3 sessions inside** (scan) | inside the PDF |
| 2015 | **3** | **1 PDF, 3 sessions inside** (scan) | none (the printed ticks are not used as a key) |
| 2016 | **2** | **1 PDF, 2 sessions inside** | inside the PDF |
| 2017 | 2 | 2 PDFs, one per session (scans) | CS-2 inside its PDF; CS-1 none |
| 2018–2020 | 1 each | 1 PDF, 1 paper (2019 and 2020 are scans) | inside the PDF |
| 2021 | **2** | **1 PDF, 2 sessions inside** (scan) | 1 separate key PDF covering both |
| 2022, 2023 | 1 each | 1 PDF, 1 paper | separate key PDF |
| 2024–2026 | 2 each | 1 PDF per session | separate key PDF per session |

- **Pattern:** the archive years mostly put several sessions in one combined PDF, with keys inside it or missing. From 2021 on, questions and keys are separate PDFs and every paper has a key.
- **Totals:** 29 active papers × 65 = 1,885 questions, all extracted. 20 have an official key and 9 do not (2011, 2013 ×4, 2015 ×3, 2017 CS-1).
- **For analysis:** years contribute 1 to 4 papers, so use the "Average over sessions" switch when comparing years.

**On the site.** There's a new **About the Data** screen, right after Pipeline Status, and the Glossary page links to it. It shows the three groups, the year-by-year table, a per-paper table (pages, key source, layout, what's loaded) and what each layout name means. It's computed live from the paper registry and the database, so it updates when you add GATE 2027. It also shows under the upgrade prompt on a database that hasn't been upgraded yet. The written version is in `docs/21_DATA_INVENTORY.md`, linked from START_HERE, README and the docs index.

**Tests:** 191 automated tests pass, including 3 new ones that pin these numbers to the registry. The real-browser test passes 62/62, including the new screen.

**Your live database was changed at 14:15:23**, by the app's "Back up the database, then upgrade it" button, not by any of my commands. My scripts only read the app on port 8501, and my tests use copies. The server log shows browser activity then, so I assume you clicked it.
- **What changed:** it backed up first (`backups/gate_cse.20261104-141523.sqlite`), then added the one empty column.
- **What didn't:** every existing table is identical to the backup I took at 14:05, and the database still holds just the 2 papers, so nothing was promoted.
- **What it means for you:** the full app now works on your live database, including the Review Workspace. Loading the other 27 papers is still your decision: `promote.cmd`, then type YES.20



Yes, that's a sound plan, and the order is right: classify everything, review it, analyse it, then generalise to other branches, then build the proper app and the bot. Below is what you do next, what each stage takes, and the questions that need your answer. The counts and times come from this session; the review and later-phase effort figures are my rough estimates.

## Your actions, in order

**Now (minutes)**
1. Double-click `promote.cmd`, read the preview and type YES. This loads all 29 papers into your live database. It backs up first and checks your existing reviews are unchanged.
2. Run `.\scripts\dev.ps1 repair-text --paper GATE-CS-2025-S1`, then the same with `--yes`. This completes Q59's missing table text.
3. Run `.\scripts\dev.ps1 validate` and `.\scripts\dev.ps1 review-status` to confirm 29 papers and 1,885 questions.

**Then classify the remaining 1,820 questions** (the three ways are below).

**Then review** in the Review Workspace and Approve Queue.

**Then analyse** using the Analysis Matrix and Topic Report.

## The three ways of classifying

So far 65 of 1,885 questions have a suggestion, and none is verified.

| Way | What it is | What it takes for 1,820 questions | Status today |
| --- | --- | --- | --- |
| **1. Agent** | A Claude/ChatGPT chat (or a coding agent like me) reads each question and its image and proposes labels | Chat batches: 91 batches of 20, each a copy-paste round trip of about 5–10 min, so roughly 8–15 hours of your time spread over days. A coding agent can also do it in sessions, within your plan's limits | Built and tested (`chat-export` / `chat-import`); one batch is already exported |
| **2. API** | Gemini runs unattended | About 11.1M input tokens and 1,820 calls, roughly 3 h 50 min at 8 requests a minute. It may need several days if the free daily limit is lower; the run stops cleanly and resumes | Built, safety-tested and piloted (7 of 7 matched); not run yet |
| **3. Human** | You check each question against the image, correct it, score the 5 checks, then approve | At about 2–3 min per question, all 1,885 is roughly 60–90 hours | Built and enforced; 0 of 65 done |

**How the three fit together.** Ways 1 and 2 only produce suggestions; only way 3 makes anything "verified".

Where the agent and the API **agree** (likely most questions), you can approve faster. Where they **disagree**, those questions go to the front of your queue.

That needs one change: today each question can hold **only one** suggestion, a deliberate guard against double-counting. Storing both the agent's and the API's answers and showing their agreement needs a small design change. This is the first thing to decide.

**Making human review realistic.** Reviewing all 1,885 questions carefully is a big job. A practical path:
1. Review a stratified sample of about 200 questions, all subjects and years.
2. That sample becomes your gold set, which tells you the real accuracy of the agent and API.
3. If accuracy is high, fully review only the disagreements, flagged items and scanned or figure-heavy questions. The rest stay "suggested", clearly labelled.

## After classification

- **Data and matrix:** already built. As soon as questions are classified, the Analysis Matrix and Topic Report fill in. It's wise to show "suggested" and "verified" counts separately.
- **Other branches from a dumped zip:** this is a big jump, not a switch.
  - Each branch needs its own syllabus taxonomy.
  - The 2011–2020 PDFs needed 7 different hand-tuned layout rules.
  - Session splits and page ranges were set by hand in `manifests/papers.yaml`.
  - Answer keys come in at least 6 formats.
  - Automatic "drop a zip" needs layout detection, a review step for anything not recognised, and a taxonomy per branch.
  - Expect weeks per new layout family. A semi-automatic flow (auto-detect, then human confirms) is the realistic first version.
- **The real app and the bot:** replacing Streamlit with a web app (separate backend and frontend), then a tutor bot over the verified bank. This means accounts, hosting and costs. Phase 1 was deliberately local-only, so it's a new phase.

## Questions still unanswered

**Classification**
1. Should the agent and the API **both** classify every question, so you get agreement (needs the design change above)? Or should each question get one suggestion (agent *or* API)?
2. Which agent path: you with ChatGPT/Claude chat batches, or a coding agent classifying in sessions?
3. May I run the Gemini batches? And what are your free-tier limits in AI Studio (requests per minute and per day)?
4. Review depth: full review of all 1,885, or the gold-set plus risky-items approach?
5. Who reviews: only you, or others too (the app already records reviewer names)?

**Data**
6. When do you want to tackle 2007–2010 (needs OCR work on photographed pages)?
7. Can you find official keys for the 9 key-less papers?
8. Can you send the auditor's file behind the unexplained 52/10/3 result?

**Later phases**
9. Which branches next, and do you have their syllabi?
10. The public app: who uses it, where is it hosted, and is it free or paid? Republishing official GATE papers online also needs a rights check before going public.
11. What should the bot do: explain questions, recommend practice, or predict topics? Predicting topics would need care, since this data describes history, not the future.

Want me to save this as `docs/22_ROADMAP.md` so it lives with the project?