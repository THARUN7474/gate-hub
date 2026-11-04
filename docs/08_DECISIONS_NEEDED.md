# Decisions Only the Owner Can Make (answer before/at Day 1)

1. How will you supply the papers?
   (a) Download CS.zip from the official Drive folder yourself, or
   (b) point an agent at the year-wise downloads 2021-2026 first and open
       CS.zip later, or
   (c) you already have PDFs locally.
   Recommended: (b) gets the Day-2 vertical slice unblocked fastest; (a) can
   run in parallel.

2. Which ONE LLM provider for classification?
   Claude API or OpenAI API. You have Claude Code etc., but a Claude Code
   subscription is NOT API credit - classification needs an API key and
   approved spend (estimate first; expect a small number for ~1-2k questions,
   measured by --estimate-cost, not guessed). Until you decide, the mock
   provider keeps everything testable.

3. Development machine OS? (Windows / macOS / Linux)
   Setup commands in docs/06_SETUP.md assume bash; on Windows use WSL2 or the
   noted activation path. Also confirm Docker Desktop can run (needed for the
   locked Postgres stack; SQLite fallback exists if not).

Also needed from you during the week (the human bottlenecks):
- ~30-45 min Day 1: approve the taxonomy topic splits in taxonomy.yaml.
- ~2 hrs Day 3: blind-label the gold set (60-100 questions).
- 15-30 min per paper Days 3-5: review queue.

## v4 additions

- **Multi-year import (audit priority fix 7)**: do not import historical
  papers until the extractor is validated against at least two historical
  layouts (font/header/segmentation drift). No additional papers were
  supplied with the audit; coverage remains GATE 2026 CS-1 only. When papers
  arrive, run `drift-check` per paper and expect pattern tuning.
- **LLM provider spend**: providers are implemented (v4). Owner must pick ONE
  (anthropic or openai), set its key + GATE_LLM_MODEL, run
  `python -m src.cli classify --estimate-cost --price-in X --price-out Y`
  with prices from the provider's CURRENT pricing page, then approve
  `--allow-spend`. A Claude Code subscription is not API credit.
