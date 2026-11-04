# Reviewing the 120-question benchmark sample (your gold labels)

Why this matters: the 120 sampled questions are the only way to get an honest accuracy number for
the first-pass labels, and every later model (FreeLLMAPI, Jev, OpenAI Decisions, Claude's AI review)
is scored against what you decide here. Only YOUR "Verify" creates gold. Nothing else does.

Time: about 1-2 minutes per question, so 2-4 hours in total. You can stop at any point: progress is
saved per question.

## 1. Start the app

Double-click `start.cmd`, or in PowerShell in the project folder:

    .\scripts\dev.ps1 app

The app opens at http://localhost:8501.

## 2. Open the sample

1. In the left sidebar, choose **Review Workspace**.
2. Set **Show** to **benchmark sample (gold review)**.
3. Set **Order** to **paper order**, or to **review priority first** if you want the hard ones first.
4. Leave **Paper** as it is. The filter lists all pending sample questions across papers.

## 3. For each question

The left side shows the original PDF crop and the official key. The right side shows the stored label.

1. **Read the PDF crop**, not just the extracted text. The crop is the source of truth.
2. **Decide the topic yourself first.** Ask: what knowledge do I need to solve this? Then look at the
   stored Section and Topic. If it's wrong, pick the right ones in the two dropdowns.
3. **The yellow or blue "AI review" box** is Claude's opinion from 5 Nov 2026. Read it after you have
   decided. It is a second opinion, not an answer. On sampled questions Claude deliberately did NOT
   change the label, so your judgement stays independent. Claude's opinion is scored against yours later.
4. **Score the five review checks** (pass or fail):
   - Source fidelity: do the text, options and figure match the PDF? If not, it fails. Many 2015 OCR
     questions contain response-sheet residue such as "Options : 1. 2 3 4" or "Correct Answer : 995";
     the AI review box names them. These fail.
   - Answer/key provenance: the official key is aligned, or it is honestly shown as missing (9 papers
     have no keys; that still counts as a pass).
   - Primary section/topic: the label (after your correction) is right.
   - Concept depth: the concepts are accurate, or empty rather than wrong.
   - Explanation/evidence: "what it tests" supports the mapping, or is honestly not recorded.
5. **Press one button:**
   - **Verify as-is** (Alt+V): the stored label is right. Gold is created.
   - **Verify with correction**: you changed the dropdowns. Gold is your corrected label.
   - **Flag** (Alt+X): the extraction is broken or the question is genuinely ambiguous. No gold is created.
   - **Skip to next pending** (Alt+N): decide later.

   Verify is refused unless Source fidelity and Primary topic both pass. That is deliberate.
6. **Approve & next** (Ctrl+Enter) verifies and moves on in one step.

Questions with a broken extraction (Source fidelity fails): fix the text or options in the extraction
correction box on the left first, then verify. Or flag the question and come back to it.

The single taxonomy-gap question (2013-S4 Q27, software-engineering cohesion/coupling) has no valid
topic. Leave it flagged until you decide on the proposed LEGACY.SE category.

## 4. See your numbers

Any time, in PowerShell:

    .\.venv\Scripts\python.exe -X utf8 -m src.cli benchmark-status
    .\.venv\Scripts\python.exe -X utf8 -m src.cli evaluate-benchmark
    .\.venv\Scripts\python.exe -X utf8 -m src.cli evaluate-benchmark --provider ai-review

- The first shows how many questions are done.
- The second shows first-pass accuracy against your gold: topic and section accuracy, per section and
  per year, plus calibration. It always scores the FROZEN first-pass prediction, never the row you
  just corrected.
- The third shows how often Claude's AI review agreed with you.

Tip: about 50 verified questions already give a rough accuracy figure (roughly +/- 13 points). All 120
narrow that to about +/- 8.

## 5. Undo

Every action is an audit event (open "Audit history" at the bottom of a question). Re-flagging a
verified question revokes its gold. A full database restore is in `docs/CURRENT_STATUS.md`.
