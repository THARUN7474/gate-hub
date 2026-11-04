# LLM providers, setup and combined scores (v6)

## One-file setup

`cp .env.example .env` and add what you have. The CLI, the app and every
script load `.env` automatically (src/settings.py). Nothing else to export.

## Providers

All providers implement the same contract (same prompt, same strict-JSON
output), so they are interchangeable. Model resolution order:
`GATE_LLM_MODEL` (global override) > provider-specific `*_MODEL` > default
(where a default exists).

| Provider | Key env var | Billing reality | Model |
| --- | --- | --- | --- |
| mock | - | offline, no network | - |
| openrouter | OPENROUTER_API_KEY | `:free` models are listed at $0 by OpenRouter (rate-limited); any other model is PAID | default meta-llama/llama-3.3-70b-instruct:free (verified live on openrouter.ai, Nov 3 2026) |
| gemini | GEMINI_API_KEY | a FREE TIER exists, but a key on a billing-linked project is CHARGED per token (ai.google.dev/gemini-api/docs/billing). Unverifiable from here | REQUIRED (GEMINI_MODEL): pick from ai.google.dev/gemini-api/docs/models; free-tier model access changes (2.5 models are restricted to past users) |
| groq | GROQ_API_KEY | free tier exists; account/plan-dependent, unverifiable from here | default openai/gpt-oss-120b (production model on console.groq.com/docs/models, Nov 3 2026; llama-3.3-70b-versatile was retired Aug 16 2026) |
| anthropic | ANTHROPIC_API_KEY | paid | default claude-sonnet-4-5 |
| openai | OPENAI_API_KEY | paid | REQUIRED (OPENAI_MODEL): never assumed |

No $0 guarantee is made for gemini/groq: only OpenRouter's `:free` listing is
a provider-stated free route.

## Selection: what "available" means

- `auto` tries providers in `GATE_LLM_PRIORITY` order (default
  `gemini,groq,openrouter,anthropic,openai`) with BOUNDED failover: per
  question, providers are tried in order until one answers; every attempt
  (errors included) is recorded in provider_votes, and the row records which
  provider actually answered. Failover NEVER crosses consent gates - paid
  providers participate only when spend is approved for that run, so there
  is no silent paid fallback.
- Key presence is configuration availability, not a live health check:
  quota/model failures surface as recorded errors and trigger failover.
- `python -m src.cli llm-status` shows keys/consents (never secret values).

## Consent gates

1. `GATE_LLM_ALLOW_EXTERNAL=1` (or `--allow-external`): any external call;
   question text leaves this machine.
2. `GATE_LLM_FREE_PLAN_CONFIRMED=1`: your attestation that your gemini/groq
   accounts are on free plans. Without it those providers need per-run
   `--allow-spend` (which treats them as paid). This makes silent billable
   calls through the free path impossible.
3. `--allow-spend`: paid providers (anthropic, openai, non-free openrouter
   models), per run, unchanged from v5.

## Ensemble and the combined score

`python -m src.cli classify-ensemble` (or the app button) classifies each
question with EVERY runnable provider and combines:

- consensus topic = majority vote on primary_topic_id (ties: summed
  confidence);
- agreement = fraction of providers on the winning topic;
- **combo_score = agreement x mean confidence**, rounded to 3 decimals.

combo_score is a review-priority HEURISTIC, not a correctness probability.
Per-provider votes (including errors) are stored on the classification and
shown in the Review Workspace. combo < 0.5 flags the question. One provider
failing does not stop the others; all failing flags the question. Verified
records are never overwritten.

Provenance is explicit: single-provider runs (including everything
classified before v6) have agreement = NULL, provider_count = 1, and the UI
labels them "single provider - no ensemble agreement". Only a real
multi-provider run shows an ensemble combined score.

## v7: status, safety changes, and the exact first-live-run procedure

**Status when this section was written (early 4 Nov 2026): BLOCKED-NEEDS-KEY. SUPERSEDED later that day: a Gemini key was saved and two 7-question pilots ran - see "v7.3" below.** At the time `.env` contained no provider key, so no live call had been made and the
adapters are still verified only with fake transports (real response shapes, model names, rate limits and JSON compliance are
unverified - handoff gap G2). Provider terms/model lists below were last checked against official docs on 3 Nov 2026 and were
NOT re-checked in v7 (G9): re-check the official model list before you set a `*_MODEL`.

Where to get a key (put it ONLY in `.env`, never in chat or code):

| Provider | Create key at | `.env` variable(s) |
| --- | --- | --- |
| Gemini | https://aistudio.google.com/apikey | `GEMINI_API_KEY`, `GEMINI_MODEL` (current model, required) |
| Groq | https://console.groq.com/keys | `GROQ_API_KEY` (`GROQ_MODEL` optional) |
| OpenRouter | https://openrouter.ai/keys | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` ending `:free` |
| Anthropic / OpenAI | provider console | paid: needs `--allow-spend` and an explicit cap you set |

What changed in v7 (all tested):
- **No duplicate classification rows.** A run used to classify every question and skip only *verified* ones, so a run over
  "all papers" would have added a second row to each of the 65 existing 2026 suggestions and doubled that year in every matrix.
  Now a run skips any question that already has a classification (`skipped_existing` in the result) and never touches a verified
  one under any version. `--reclassify` (CLI) / the checkbox (app) replaces UNVERIFIED suggestions in place and writes an audit
  event (`classification_replaced`).
- **`classify-compare`** (and the "4. Compare" panel): runs ONE provider on a sample of already-classified questions and prints
  section/topic AGREEMENT with the existing suggestions. Writes nothing. Agreement is not accuracy: the 65 suggestions are
  themselves unverified. Real accuracy needs a human-verified gold set.
- The LLM Classify screen shows per-provider `calls_ok / calls_failed / last_success / last_error` from RECORDED attempts, and
  explains errors in plain language with the fix (401 key, 404 model, 429 rate limit, 5xx, timeout, bad JSON).

First live run, in this order (stop at any step that fails; each is cheap):
```powershell
# 1. .env: add the key + model, GATE_LLM_ALLOW_EXTERNAL=1 (question text leaves this machine), and for gemini/groq on a FREE plan
#    GATE_LLM_FREE_PLAN_CONFIRMED=1 (your statement; the tool cannot see billing)
.venv\Scripts\python -m src.cli llm-status
.venv\Scripts\python -m src.cli classify --provider gemini --paper-id GATE-CS-2025-S1 --dry-run     # inspect payloads, no network
.venv\Scripts\python -m src.cli classify --estimate-cost --price-in <$/Mtok> --price-out <$/Mtok>  # prices from the provider's page
.venv\Scripts\python -m src.cli classify-compare gemini --sample 0.08                              # ~5 questions, writes nothing
# 2. only then, on a copy first, a small real run of an UNCLASSIFIED paper:
.venv\Scripts\python -m src.cli classify --provider gemini --paper-id GATE-CS-2025-S1 --sample 0.08
# 3. full runs once those look sane: --provider auto (failover) or classify-ensemble (agreement score)
```
Back up first (`.\scripts\dev.ps1 backup`). Scale: 1,885 questions loaded, 1,867 classified by the agent first pass -
so run API classification as PROPOSALS (`classify --provider <name> --proposals`), which writes a separate table
and never overwrites existing labels or reviews (`proposals-report` compares agreement). **Correction (v7.3):** the old estimate assumed
about 400 prompt tokens per question; the measured prompt is about **3,900 tokens per call**, because every call re-sends the system prompt
and the whole taxonomy. See the v7.3 section for the real numbers.

## v7.2: using Gemini with your own key (facts checked 4 Nov 2026)

Checked against Google's own pages on 4 Nov 2026 (the old `ai.google.dev/gemini-api/docs/...` URLs now redirect to `aistudio.google.com/docs/...`):

- **Models** - https://aistudio.google.com/docs/models. Current IDs: `gemini-3.8-flash` (flagship Flash), `gemini-3.6-flash` and `gemini-3.5-flash-lite`
  and `gemini-3.1-flash-lite` (stable; the two `-lite` ones are the cheapest), `gemini-3-flash-preview` and `gemini-3.1-pro-preview` (preview),
  `gemini-4-argon` (flagship reasoning). **Deprecated:** `gemini-2.5-flash` and `gemini-2.5-pro` are re-routed to `gemini-3.5-flash-lite` and
  `gemini-3.8-flash` from **1 Dec 2026**; `gemini-2.0-flash(-lite)` are shut down. The page does NOT say which models are free-tier eligible.
- **Do not use a `-latest` alias for a long run.** AI Studio's snippet uses `gemini-flash-latest`, but an alias moves when a new version ships
  (Google emails two weeks ahead). Every classification row records its model, so pin an explicit ID or one run silently mixes model versions.
- **Rate limits** - https://aistudio.google.com/docs/rate-limits. No free-tier numbers are published on that page; yours are shown (after login) in
  AI Studio at https://aistudio.google.com/rate-limit. Limits are **per project, not per key**, and linking billing to the project moves it to Tier 1
  "typically instantly" - so a key from a billing-linked project is a PAID key.
- **Data terms** - https://aistudio.google.com/docs/terms. *Unpaid* services: your content is used "to provide, improve, and develop" Google products
  and human reviewers may read input and output (disconnected from your account/key/project); **"Do not submit sensitive, confidential, or personal
  information to the Unpaid Services."** *Paid* services: not used to improve products. GATE papers are public exam text with no personal data, so the
  free tier is acceptable here - but it is your decision, and it is why `GATE_LLM_ALLOW_EXTERNAL` exists.
- **API shape** - our adapter calls `generateContent`, which is still documented and is what AI Studio's own "first API call" snippet uses. Google's
  newer *Interactions API* (`POST /v1beta/interactions`) is where new features land; nothing says `generateContent` is being removed, so it is NOT
  migrated (Google's migration guide itself says to confirm scope first). Revisit only if a live test shows `generateContent` failing.

**What to do (you run these; the key never goes in chat):**
1. `setkey.cmd gemini` - paste the key at the hidden prompt. It is written to `.env` only and never printed. (`.\scripts\dev.ps1 setkey gemini` is the same.)
2. `.\scripts\dev.ps1 models` - lists the model IDs your key can see. This sends **only the key** to Google, no question text.
3. `python -m src.cli set-key gemini --model <id>` (or edit `GEMINI_MODEL` in `.env`). Start with a `-lite` model.
4. In `.env`, set `GATE_LLM_FREE_PLAN_CONFIRMED=1` **only if the Google project has no billing linked** (that is your statement; the tool cannot see
   billing), and `GATE_LLM_ALLOW_EXTERNAL=1` only when you accept the free-tier terms above for the run.
5. Then the "first live run" steps above: `--dry-run`, `--estimate-cost`, `classify-compare gemini --sample 0.08`, a small real run.

**freellmapi.co - looked at, not integrated.** It is an open-source (MIT, github.com/tashfeenahmed/freellmapi) *self-hosted router*: you run it
(Docker, installed with `curl -fsSL https://freellmapi.co/install.sh | bash`), add your own provider keys, and it exposes one OpenAI-compatible
endpoint on `localhost:3001` that fails over between free tiers. A paid "premium" ($19/yr or $49 once) only buys a faster catalog feed; the router
phones freellmapi.co twice a day for a signed model catalog. Why we do not need it now: (a) our `auto` mode already fails over between Gemini,
Groq and OpenRouter; (b) it would hide *which* upstream provider (and which plan) a question went to, which defeats the per-provider consent gates;
(c) it adds a piped-to-bash installer and a Docker service; (d) its page states no privacy text and says "personal use only, each provider's ToS applies".
It could be added later as one more OpenAI-compatible provider if free quotas become the bottleneck.

**Google's `gemini-skills` pack** (github.com/google-gemini/gemini-skills, Apache-2.0, v2.3.0) was reviewed file by file: no hooks, no network code in
the docs skills. Only **`gemini-api-dev`** (documentation only) was installed as an agent skill. Not installed: `gemini-api-cli` (its setup is
`curl | bash`), `gemini-live-api-dev` and `gemini-omni-flash-api` (voice/video; the latter ships scripts that shell out). The skill's model list
matches the official models page above.

## v7.3: pilot, then batches (Gemini, free tier) - what the run does to protect you

Status words, kept apart on purpose (no new status was invented):
| Word in the app | What it is in the database | Who set it |
| --- | --- | --- |
| **suggested** | `classifications.status=suggested`, `provenance=inferred` | one AI run, passed the checks (valid taxonomy ids, confidence >= 0.5) |
| **flagged** | `status=flagged` (+ the question is `needs_review`) | the run: invalid id, low confidence; or a provider error on that question |
| **AI-cross-checked** | `provider_count > 1` and `agreement` (only from `classify-ensemble`) | a second provider agreed; it is NOT a status and NOT a verification |
| **verified** | `status=verified`, `provenance=validated` | **a human, only via the Review screen / CLI review path**. A classification run can never set it (test: `test_ai_runs_never_produce_human_verified_rows`) |

Real numbers. **Measured by the live pilots (gemini-3.5-flash-lite, 4 Nov 2026): v1 5,995 input / 182 output tokens per call; v2 6,123 / 174**
(no hidden-reasoning tokens reported). My earlier estimates were too low (0.89M total, then 7.2M): the naive chars/4 under-counts this prompt by ~50%
(it is 2.65 chars/token, now used by `--estimate-cost`). Projection from the measured per-call figures:
| Batch | Questions to classify | Input tokens | Output tokens | Time at 8 requests/min |
| --- | --- | --- | --- | --- |
| 2022-2026 (8 papers; 2026 CS-1 already done) | 455 | ~2.8M | ~79k | ~57 min |
| 2017-2021 (7 papers) | 455 | ~2.8M | ~79k | ~57 min |
| 2011-2016 (14 papers) | 910 | ~5.6M | ~159k | ~1 h 55 min |
| all | 1,820 | ~11.1M | ~317k | ~3 h 50 min |
Most of each call is the fixed prompt (system prompt + the whole taxonomy). If your free-tier limits bind on tokens or requests per day, a run stops with
`stopped.kind = daily_quota` and you re-run it later; finished questions are skipped.

**Prompt v2 (4 Nov 2026).** The first pilot showed the classifier saw only the question text. v2 sends exactly two more things: the answer **options**, and a
**position hint** saying whether the question sits in the General Aptitude block or the Computer Science block of its paper (read from the marks pattern, checked on all 29
papers: 21 have GA first at Q1-10, 8 have GA last at Q56-65, 0 unknown; if a paper's pattern is not recognised, no hint is sent). NOT sent: the answer key, marks, year,
session, paper id. If the model's section contradicts the hint, the row is saved as `flagged` with the reason, never silently accepted. Rows record `prompt_version=v2`.
Cost: ~127 more input tokens per call.

**Pilot results, 2026 CS-1, the same 7 questions spread across the paper, nothing written, model gemini-3.5-flash-lite:**
| | v1 (text only) | v2 (+ options + position hint) |
| --- | --- | --- |
| valid JSON / valid taxonomy ids | 7/7, 7/7 | 7/7, 7/7 |
| errors / retries / quota stops | 0 / 0 / none | 0 / 0 / none |
| topic agreement with the unverified suggestions | 6/7 | **7/7** |
| the one miss | Q05 (General Aptitude) filed as EM.DM | fixed: GA.AA |
| actual tokens | 41,968 in, 1,271 out | 42,858 in, 1,215 out |
Seven questions cannot estimate accuracy, and agreement is with suggestions no human has verified. It shows the pipeline works and the GA problem is fixed on the one GA
question sampled; the 'GA last' layout (2011-13, 2017) has no existing labels to compare against, so it is covered by unit tests and the layout check only.

What every real run now does (all tested offline, `tests/test_run_guard.py`):
- **Skips** any question that already has a classification (any version) or a human-verified one. Re-running the same command resumes.
- **Paces** itself to `GATE_LLM_RPM` requests/minute (default 8; every attempt counts). Set it from YOUR limits page in AI Studio.
- **Retries conservatively:** bad JSON/shape 1x; 5xx/network 2x (5 s, 15 s); a per-minute 429 waits the provider's `retryDelay`+2 s once.
  A cut-off answer (`MAX_TOKENS`) is not retried.
- **Stops, never pushes through:** HTTP 401/402/403/404 or billing/permission wording, a daily quota, a 429 that repeats after waiting,
  5 questions in a row failing, or `--max-calls`. The question being processed is left untouched, everything done is saved, the result has
  `stopped: {kind, reason, what_to_do}` and the command exits with code 3.
- **Checkpoints** every 10 questions (`--checkpoint-every`), so a crash loses at most 10.
- **Reports ACTUAL usage** (`actual_usage`: calls, input_tokens, output_tokens - the provider's own `usageMetadata`, thinking tokens counted as
  output; `calls_without_usage` shows if a response carried none) and is stored on the run row. It cannot see your bill: whether the project is
  billed is your statement (`GATE_LLM_FREE_PLAN_CONFIRMED`). Check AI Studio's usage view after the pilot.

Order (you approve each step; nothing here runs by itself):
```powershell
# 0. key + model (key never in chat):  setkey.cmd gemini      then   .\scripts\dev.ps1 models   then   python -m src.cli set-key gemini --model <a -lite id>
# 1. read-only checks
.\scripts\dev.ps1 llm                                                                   # key set? gates? (no secrets printed)
.\scripts\dev.ps1 classify --provider gemini --years 2022-2026 --dry-run                # exact payloads + measured estimate, no network
# 2. PILOT: ~8 of the 65 existing suggestions, spread across the paper, writes NOTHING
.\scripts\dev.ps1 compare gemini --paper-id GATE-CS-2026-S1 --sample 0.12
# 3. batches, on the full database (after promote), newest first; resumable; stop and read the result after each
.\scripts\dev.ps1 backup
.\scripts\dev.ps1 classify --provider gemini --years 2022-2026
.\scripts\dev.ps1 classify --provider gemini --years 2017-2021
.\scripts\dev.ps1 classify --provider gemini --years 2011-2016
```
The pilot's number is **agreement with 65 unverified suggestions, not accuracy** (nothing is human-verified yet). Real accuracy needs a human-checked
gold set: verify a spread sample in the Review screen, then run `compare` again and it reports `topic_agreement_vs_verified`.

Gemini knobs: `GEMINI_MAX_OUTPUT_TOKENS` (default 8192; thinking models share it with hidden reasoning), `GEMINI_THINKING_LEVEL` (sent only if set).
`GATE_LLM_RPM` as above. Unverified until a live call: that your model accepts `thinkingConfig`, and which model the free tier serves.

## Human approval surface

- Review Workspace: Verify as-is / Flag / Save correction / Verify with
  correction / Approve & next / Skip. Section, topic (filtered to the
  section) and concepts are corrected from dropdowns showing full names.
  Correcting a topic auto-syncs its parent section.
- Approve Queue: batch approval. Filter by combined score or flagged-only,
  correct any row from its dropdown, tick Approve, confirm, apply. Every
  decision logs a ReviewEvent (reviewer = the name in the sidebar, note="approve queue"),
  identical audit to one-by-one verification.
- Analysis Matrix cells are clickable: a cell opens its contributing
  questions, each question opens its Review Workspace page.
