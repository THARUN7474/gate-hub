# LLM access: FreeLLMAPI for all chat calls; decision models kept separate

## 1. FreeLLMAPI (the single key for every chat-LLM call)

The owner decided on 5 Nov 2026 that every chat-LLM call goes through the local FreeLLMAPI router.
The router is installed at `C:\Users\Tharun\freellmapi` and runs in Docker on http://127.0.0.1:3001.
You add your provider keys in the router's dashboard; this project only ever holds the router's ONE
unified key.

Settings in `.env`:

| variable | value | meaning |
| --- | --- | --- |
| `GATE_LLM_PROVIDER` | `freellmapi` | default provider |
| `GATE_LLM_PRIORITY` | `freellmapi` | auto picks the router |
| `GATE_LLM_ROUTER_ONLY` | `1` | direct providers (gemini, groq...) are ignored even if a key is present |
| `FREELLMAPI_BASE_URL` | `http://127.0.0.1:3001/v1` | the router's OpenAI-compatible endpoint |
| `FREELLMAPI_MODEL` | `auto` | the router picks and fails over; also `auto:smart`, `auto:fast`, `auto:<profile>` or an exact id |
| `FREELLMAPI_API_KEY` | (empty) | paste it with the command below; it is never printed |

Set it up:

1. Open http://127.0.0.1:3001. Go to **Keys**, add your provider keys, then copy the unified
   `freellmapi-...` key from the page header.
2. Save the key (hidden prompt): `.\.venv\Scripts\python.exe -m src.cli set-key freellmapi`
3. Check it: `.\.venv\Scripts\python.exe -m src.cli llm-status`. It shows the key as set, never its value.
4. See what models the router can use with your keys (sends only the key):
   `.\.venv\Scripts\python.exe -m src.cli llm-models freellmapi`
5. Smallest real test, 5 questions. It writes nothing; it compares against the stored labels:
   `.\.venv\Scripts\python.exe -X utf8 -m src.cli classify-compare freellmapi --paper-id GATE-CS-2026-S1 --sample 0.08`

Every existing path uses the router automatically: classify, classify-compare, the `--proposals`
second-opinion run and the app's LLM Classify screen. The upstream that served each call is read from
the router's `X-Routed-Via` header.

Gates still apply. Question text goes on to whichever upstream provider serves the call, so calls need
`GATE_LLM_ALLOW_EXTERNAL=1` plus your free-plan statement `GATE_LLM_FREE_PLAN_CONFIRMED=1`. Both are
already set from the Gemini decision. If you add a PAID key to the router, set
`GATE_LLM_FREE_PLAN_CONFIRMED=0` so runs require `--allow-spend`. Pacing (`GATE_LLM_RPM`, default 8)
and the stop-on-quota guard are unchanged. No bulk run starts without your go-ahead.

Not verified yet: no call has gone through the router from this project. The key is not set, and the
router answers 401 without it. The provider is tested offline with fake transports.

## 2. Decision models (OpenAI Decisions, Jev): separate, paid, off by default

**My take.** They are worth having for ONE job: an independent, calibrated second opinion on the topic.
One typed `choice` question over the 49 topics returns a probability for every topic. That maps 1:1
onto a `classification_proposals` row: choice becomes the topic, probability becomes the confidence,
and the distribution becomes `topic_weight`. It's cheap. The whole 120-question sample is estimated
at **$0.007 on Jev** and **$0.017 on OpenAI Decisions** (input tokens only; output is free on both).
The probabilities make a good review-priority signal: low confidence or a split between two topics
points to genuinely ambiguous questions.

They do NOT replace review, and they don't create truth. Their accuracy is unknown until it is scored
against YOUR verified gold. So the right order is:

1. You review the benchmark into gold (docs/22).
2. Run one model on the 120 questions.
3. Run `evaluate-benchmark --provider <name>`.
4. Only then decide whether it earns a bigger role.

Running them before gold exists only measures agreement with unverified labels.

Jev is text-only: diagram questions go in as extracted text. OpenAI Decisions can also receive the PDF
crop (`--with-images`). Not worth adding: LangChain4j DecisionModel (Java-only, experimental). SetFit
is a free local option later, once about 50 gold labels exist per major section.

Settings in `.env` (separate from FreeLLMAPI):

    DECISIONS_ENABLED=0               # master switch; 1 is needed for any real call
    OPENAI_DECISIONS_API_KEY=         # python -m src.cli set-key openai-decisions
    OPENAI_DECISIONS_MODEL=gpt-6-luna
    TYPESAFE_API_KEY=                 # python -m src.cli set-key jev
    JEV_MODEL=jev-1.14.0
    # optional: OPENAI_DECISIONS_URL, TYPESAFE_URL, OPENAI_DECISIONS_PRICE_IN_PER_M (0.10), JEV_PRICE_IN_PER_M (0.042)

Commands:

    # dry run (default): cost estimate + the exact first payload, nothing sent
    .\.venv\Scripts\python.exe -X utf8 -m src.cli decisions jev --benchmark
    .\.venv\Scripts\python.exe -X utf8 -m src.cli decisions openai-decisions --benchmark

    # real run - only after you approve the estimate; every flag is required
    .\.venv\Scripts\python.exe -X utf8 -m src.cli decisions jev --benchmark --yes --allow-spend --max-calls 120

    # score against your gold
    .\.venv\Scripts\python.exe -X utf8 -m src.cli evaluate-benchmark --provider jev

Results go only to `classification_proposals` (provider `jev` / `openai-decisions`, prompt
`decisions-v1`). They never touch the live labels, never verify anything and never write gold. A run
stops at the first 401/402/403/404 error or after 3 errors.

## 3. Claude AI review (chat, no API)

`scripts/ai_review.py` exports questions as JSON, imports an AI reviewer's decisions file, and records
each verdict as an AI review. It is never human verification and never gold. Done on 5 Nov 2026 for
2026 CS-2 and for the 120-question sample. See docs/CURRENT_STATUS.md.
