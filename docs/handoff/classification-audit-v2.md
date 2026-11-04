# Classification audit - agent first pass v2 (4 Nov 2026)

## Method (honest)
- 28 papers (1,820 questions) classified by an AI agent (Claude) reading each question's text from the
  staging DB and assigning one primary topic + confidence. Same method as the 65 of 2026 CS-1 (v1).
  NOT an LLM API run, NOT human verification. Every row: model=claude-agent-manual-v2,
  prompt_version=agent-v2, provenance=inferred, status=suggested (1,425) or flagged (377).
- The 28 per-paper label files are the per-question evidence: docs/handoff/labels-v2/*.tsv
  (question_id, topic, confidence, flag-reason). The DB row's raw_response keeps the flag reason,
  the matched_from source (for 2013 shuffles) and the keyword heuristic's independent guess.
- 2013 S2/S3/S4 are official shuffles of the same 65 questions as 2013 S1. Labels were carried over
  by exact normalized-text match where the text was identical (S2: 37, S3: 39, S4: 37 of 65) and
  assigned individually otherwise - including all four shared common-data stems (PDS.C find-replace
  pair, COA.ISA register-code pair, DB.NF pair, OS.MEM paging pair) and OCR-variant mismatches.
- 113 rows initially carried the match provenance in the flag field by mistake ("- (matched S1-Qxx)");
  these were NOT real flags and have been corrected: status=suggested, provenance kept in
  raw_response.matched_from.

## Taxonomy gap: software engineering (explicit, not hidden)
- The taxonomy (gate-cs-2027) has NO software-engineering topic. 18 questions (testing, COCOMO, SRS,
  cohesion/coupling, function points, fault seeding, cyclomatic complexity, process models, code
  inspection, LOC/requirements estimation) were left UNCLASSIFIED with a review_events row
  field=taxonomy_gap, instead of being forced into PDS.C. They appear as unclassified in every
  matrix/export and in Pipeline Status. Owner decision needed: extend the taxonomy with an SE
  topic or accept GATE no longer tests SE (post-2015 syllabus).
- 4 "web technologies match" questions (2013 S1/S2/S3/S4) sit in CN.APP at 0.4 flagged - a weak
  but defensible bucket (application-layer protocols), left flagged for review.

## Confidence and flag distribution
- 1,867 classified: 1,490 suggested, 377 flagged. 18 unclassified (taxonomy gap). 0 verified.
- Top flag reasons: register-operand code segments (6), string find-replace procedures (6),
  three-level paging (6) - ambiguous stems and numerical questions where keyword signal is weak.

## Quality signals (not validation)
- Offline keyword heuristic (local-heuristic-v1, `classify-local`) independently agrees with the
  agent's topic on 1,083 / 1,867 (58%); on the 65 v1 labels 45/65 (69%). This is a weak-second-opinion
  signal only - keyword matching is not an LLM and agreement is not correctness.
- Independent API agreement (real provider votes) is still pending the owner's key + consent; nothing
  was sent to any external provider.

## Verification
- pytest: 193 passed, 1 skipped (2 more tests unblocked once streamlit installed).
- scripts/ui_apptest.py (updated for the v8 rubric gate): all 9 screens render; Flag / Verify as-is /
  Save without verifying / Verify with correction / Approve & next / Approve Queue all persist with
  audit events; matrix cell links clickable.
- Rendered screenshots of the new UI: docs/screenshots/v9-*.png.

- **Topic-level pass, documented as such:** the v2 first pass assigned section + primary topic +
  confidence ONLY. It did not record what-it-tests prose, prerequisites, or concept-level detail
  (except 113 rows with keyword-heuristic concept ids where the heuristic agreed with the agent
  topic). These are open gaps, not completed work: the API proposals pass or human review supplies
  them. Earlier wording that implied fuller classification detail was corrected in docs/00_STATUS.md.

## Corrections added 4 Nov 2026 (v10 review)

- **what_it_tests:** the v2 TSVs carried only topic + confidence + evidence keywords; the apply
  script synthesized `what_it_tests = "agent: <keywords>"` for 1,589 rows. That was placeholder
  text, not a real explanation, and it has been REMOVED: all 1,802 v2 rows now have
  what_it_tests = NULL. The UI says "not recorded for this suggestion - add during review".
  The 65 v1 rows keep their real human-readable notes. The TSV evidence columns are unchanged.
- **model column meaning:** `claude-agent-manual-v1` / `-v2` are descriptive labels of the
  LABELING METHOD (which agent pass produced the row), not a verified identity of any underlying
  provider model. Anywhere a real API provider runs, its own reported model string is stored.
- **Independent provider proposals:** API classification should run as `classify --provider X
  --proposals`, which writes separate rows to classification_proposals and never overwrites these
  labels or human review; `proposals-report` computes agreement. See docs/00_STATUS.md v10.
