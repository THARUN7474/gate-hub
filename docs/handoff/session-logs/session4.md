# Session 4 (4 Nov 2026, ~15:00-16:00) - review fixes, marks audit, Gemini smoke test

Context: review of the v9 delivery asked for clickable Topic x Year cells, a readable
Subject Overview, a marks audit, and the bounded API smoke test with the owner's key.

Done:
- Analysis Matrix: every Topic x Year cell is a link; it opens a drill view listing the
  cell's contributing questions; each question link opens it directly in the Review
  Workspace (verified end-to-end with Playwright screenshots).
- Subject Overview: compact per-subject table (topic, name, questions, verified,
  suggested, flagged) + per-topic expanders with readable concept names, what-it-tests
  samples from classifications, and prerequisite edges from taxonomy.yaml.
- Marks audit on staging DB: all 1,885 questions have marks in {1.0, 2.0}; every paper
  sums to exactly 100.0. Distribution: 1-mark 870, 2-mark 1,015. No anomalies.
- Gemini smoke test (owner-supplied key, free tier, no spend; the key was never written to the repo):
  PROVEN: `llm-models gemini` OK (key valid; gemini-3.8-flash listed).
  NOT PROVEN: any successful inference. `classify --provider gemini --paper-id
  GATE-CS-2011-S1 --max-calls 2`: 2 attempts, both HTTP 503 UNAVAILABLE ("high
  demand"); guard waited 5s + 15s and stopped cleanly at the cap. 0 rows written,
  classifications table untouched. Probe after 75s: still 503. Internal usage
  counters recorded no completed call - that is our own accounting and says nothing
  about provider-side quota; the 503 alone does not establish the cause or duration.
  No further API retries without an explicit owner instruction.
- Independent provider proposals workflow built + tested: `classify --provider X
  --proposals` writes to a separate classification_proposals table and never touches
  classifications (labels and human review preserved; no analytics double-counting);
  `proposals-report` gives per-provider agreement. tests/test_proposals.py: 5 tests.
- Region preview honesty: verified 2011-S1 Q64's stored region against the real
  source PDF (sha256-matched): correctly aligned, full question + options. The
  missing-PDF fallback message now says the region IS stored and names the file.
- What-it-tests cleanup: v2 placeholder values ("agent: <keywords>", 1,589 rows)
  removed - NULL now; UI shows honest "not recorded" text. v1's 65 real notes kept.
- Status doc advanced to v10.
