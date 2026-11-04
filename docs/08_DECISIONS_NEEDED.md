# Owner decisions - made and still open (updated 5 Nov 2026)

The original Day-0 questions (paper supply, OS, which LLM provider) are all answered; see "Made".
The older v4-v7 wording is in git history.

## Made

- [x] **Papers:** supplied locally in `data/raw/` (2007-2026). 2011-2026 are loaded; 2007-2010
  (photographed pages) are deferred.
- [x] **Machine:** Windows 11, Python 3.12 venv, Docker Desktop. SQLite is the default database;
  PostgreSQL 17 is an option.
- [x] **Missing answer keys:** the 9 key-less papers are used for questions only. Keys are never guessed,
  and the 2015 printed ticks are never used.
- [x] **Promotion to the live database:** approved and done on 5 Nov 2026.
- [x] **LLM access:** every chat-LLM call goes through the local FreeLLMAPI router with ONE unified key
  (`GATE_LLM_ROUTER_ONLY=1`). Direct Gemini is no longer used.
- [x] **Decision models** (OpenAI Decisions, Jev): kept separate from FreeLLMAPI, paid, and off by default.
- [x] **AI review:** Claude may review questions as an AI reviewer. It is always labelled as such and is
  never human verification or gold.
- [x] **Free-plan statement** (`GATE_LLM_FREE_PLAN_CONFIRMED=1`): given by you. Set it to 0 if you add a
  paid key to the router.
- [x] **Repository:** github.com/THARUN7474/gate-hub. No keys, databases, PDFs or backups are in git.
- [x] **Auditor 52/10/3 file:** deferred ("check later").

## Still open (only you can decide)

- [ ] **Review scope:** start with the 120-question benchmark sample (recommended,
  `docs/22_BENCHMARK_REVIEW_GUIDE.md`). Decide later whether to review whole papers or the full bank.
- [ ] **The 18 software-engineering questions:** adopt the proposed deprecated `LEGACY.SE` category, or
  keep them unclassified (`docs/handoff/se18-syllabus-audit.md`).
- [ ] **Topics outside the 2027 syllabus** (e.g. RSA in 2017-S1 Q44, three-schema architecture in
  2026-S2 Q15): keep them on the nearest topic, or give them a legacy tag.
- [ ] **First FreeLLMAPI run:** save the key, run the 5-question `classify-compare` test, then decide on a
  proposals run (`docs/23_LLM_ROUTER_AND_DECISION_MODELS.md`).
- [ ] **Decision-model bake-off:** run Jev (~$0.007) or OpenAI Decisions (~$0.017) on the 120 questions
  *after* gold exists, or skip it.
- [ ] **Enrichment:** decide whether concepts / what-it-tests / prerequisites come from review, chat batches
  or an API proposals run.

## Your time, roughly

- Benchmark sample: 120 questions at 1-2 min each, so 2-4 hours. About 50 already give a first accuracy
  figure.
- One full paper: 65 questions, about 1.5-2 hours.
