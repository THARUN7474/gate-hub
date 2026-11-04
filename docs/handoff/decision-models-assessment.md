# Decision Model Architecture handoff: what checks out, what we adopted (v11)

Date: 2026-11-04. Scope: the pasted "Decision Model Architecture" handoff received
over WhatsApp. Every technology claim below was verified against the owner's own
documentation on 2026-11-04; the source URLs are listed per item. Nothing here was
taken on trust from the handoff text (its links carried `utm_source=chatgpt.com`,
so the text is treated as a draft until checked).

## Verified: the named technologies are real

**OpenAI Decisions API with gpt-6-luna** - verified, generally available.
- `POST /v1/decisions`; `gpt-6-luna` is currently the only supported model.
- Three question types: `predicate` (probability 0-1), `choice` (one of a fixed
  set, with probabilities over the options), `score` (ordered rubric levels).
- Text, image, and JSON inputs; up to 400 questions per request; prompt caching
  with discounted cache reads; ZDR and HIPAA eligible.
- Pricing (verified on the owner's pricing page): uncached input $0.10 per 1M
  tokens, cached input discounted, **output tokens are not charged** on
  `/v1/decisions`.
- Sources: https://developers.openai.com/api/docs/guides/decisions ,
  https://developers.openai.com/api/docs/models/gpt-6-luna

**TypeSafe Jev (System One)** - verified, real.
- `POST /v1/systemone`; current model `jev-1.14.0` (Oct 2026).
- Primitives: `choice`, `score`, `noul` (boolean with probability), all with
  calibrated probabilities; answers are typed, no generated text.
- Pricing (verified): **$0.042 per 1M input tokens, output free**, one plan.
- Sources: https://docs.typesafe.ai/models ,
  https://docs.typesafe.ai/concepts/system-one ,
  https://help.typesafe.ai/articles/5187202169-how-much-does-jev-cost

**SetFit** - verified, real: few-shot fine-tuning of Sentence Transformers,
runs locally and free. Source: https://huggingface.co/docs/setfit/index

**LangChain4j DecisionModel** - real but Java-only and marked experimental.
Not usable in this Python codebase. Source:
https://docs.langchain4j.dev/tutorials/decision-models

## Corrections to the handoff's claims

- "Jev supports up to 10,000 questions per request": not what the docs say.
  There is no fixed question cap; requests are bounded by context (64k tokens
  per request / 32k per question, 262k with the long-context header).
- Jev is **text-only** (no image input). For our diagram-heavy questions (the
  kind that needed OCR), OpenAI Decisions accepts images and Jev does not; the
  question's image would have to be OCR'd or described first.
- Both are paid, account-based external APIs. No run happens without your
  approval, a key, and explicit spend consent (the existing gates stay exactly
  as they are). Nothing was called for this assessment: documentation only.

## What this means for GATE Hub: adopt the shape, not a rewrite

The handoff's core idea - store every model's answer as an append-only
candidate prediction with probabilities, and measure providers against a
human-verified gold benchmark before trusting any of them - is **already the
architecture built in v10**:

| Handoff requirement | Where it lives now |
| --- | --- |
| Append-only candidate predictions, never overwrite | `classification_proposals` table + `--proposals` run (v10); the `classifications` table and its human decisions are never touched |
| Fixed choice sets with probability distributions | A Decisions/Jev `choice` question maps 1:1 onto a proposal row: topic choice -> `primary_topic_id`, probability -> `confidence`, full distribution -> `topic_weight` |
| Independent second opinion + agreement report | `proposals-report` (per-provider agree/disagree/fills-unclassified vs current labels) |
| Decision gate: no full-dataset run without approval | Existing consent gates (`--allow-spend`/`--allow-external`), dry-run mode, call guard |

So instead of a new system, v11 closes the gaps the handoff correctly
identifies, all local and free:

1. **Staleness detection** (`source_content_hash` on every proposal, Alembic
   0007): each proposal stores the SHA-256 of the exact question text+options it
   was made from. If a question is re-extracted or OCR-corrected later,
   `proposals-report` now reports the proposal as *stale* instead of silently
   comparing an old opinion against changed input.
2. **Stratified gold benchmark** (`benchmark_samples` table + `benchmark-sample`
   CLI): 120 questions drawn proportionally across every paper/session and both
   mark values (deterministic seed). Actual composition: 96 suggested / 23
   flagged / 1 unclassified (one of the 18 SE gap questions); 66 clean-extracted
   / 54 OCR; 83 MCQ / 5 MSQ / 31 NAT; all 11 sections + GA covered. Every row is
   `pending_user_review` - the tool never invents gold labels. The loop is
   closed in the app: the Review Workspace has a "benchmark sample (gold
   review)" filter, and verifying a sampled question there (or in the Approve
   Queue) records YOUR verified label as that row's gold automatically - the
   normal rubric gate still applies, nothing is auto-approved.
3. **Metrics on verified gold only, against FROZEN predictions**
   (`validation.metrics` + `evaluate-benchmark` CLI): each sample row freezes the
   machine prediction (section/topic/concepts/confidence + a content hash of the
   question) at sampling time. Scoring compares THAT frozen baseline against your
   gold - never the live classification row, which after your correction IS the
   gold (scoring it would be a tautology). Re-flagging a verified question
   revokes its gold; a question whose text changes after sampling is reported
   stale and excluded. Metrics: topic and section accuracy, per-section and
   per-year breakdowns, concept micro P/R/F1, confidence calibration. Today it
   honestly reports `n_gold_verified: 0`, because no gold exists yet. It can
   also score one provider's independent proposals against the gold
   (`--provider`), which is exactly the bake-off the handoff wants once you
   approve any API run.
4. **Review prioritization** (`prioritized_review_queue` + `review-queue` CLI +
   "review priority first" ordering in the Review Workspace): taxonomy gaps
   first, then classifier-flagged, low-confidence (<0.6), extraction/OCR issues,
   provider disagreements, remaining suggestions, and a deterministic 5%
   spot-check sample of verified rows at the end.
5. **18-question syllabus audit** - see `docs/handoff/se18-syllabus-audit.md`.

## If you later approve an API comparison

The cheapest, cleanest first experiment is a small proposals run (existing
`--proposals` path) against the 120-question benchmark sample *after* you have
reviewed it into gold: cost is input tokens only on both candidate APIs
(Jev $0.042/1M, Decisions $0.10/1M uncached), output is free on both, and the
existing call guard caps spend. Jev would need diagram questions pre-OCR'd;
Decisions can take the rendered crops directly. SetFit becomes a free local
third voter once ~50+ gold labels exist per major section. None of this has
been run or scheduled; it needs your explicit approval first.
