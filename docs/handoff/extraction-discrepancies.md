# Extraction discrepancies: 2026 CS-1 Q21 / Q37 / Q48 and 2025 CS-1 Q59

## Status at a glance (re-run 4 Nov 2026, 13:57 local, against the LIVE database, read-only)

| Item | What was executed | Result | Resolved? |
| --- | --- | --- | --- |
| 2026 Q21, Q37, Q48 vs fresh extraction | `qcheck` re-extraction of `CS1_2026.pdf`, byte compare with live rows | text and all options **identical** (151 / 528 / 213 chars) | no data defect found; the notation caveats remain open for a human (flags kept) |
| same, printed options vs official key | options as printed (read from the region renders) evaluated by computer | Q21 A,C = key `A;C`; Q37 B = key `B`; Q48 B,D = key `B;D` | consistent with the key |
| auditor's 52 exact / 10 normalized / 3 changed | cannot be re-run: the auditor's file is not in the project | **not reproduced** | **NO - unexplained** |
| 2025 Q59 | same re-extraction; `papers-drift` over all 29 papers of the staging DB | stored text is an exact 277-char prefix of the 357-char fresh text (80 chars of state-table values missing); drift = **28/29 papers exact, Q59 changed** | **NO** - a repair script exists and passed a rehearsal on a COPY, but it has **not** been applied to the live or staging database |

Evidence files (in `docs/handoff/evidence/`): `2026-CS1-Q21_page16.png`, `2026-CS1-Q37_page26.png`, `2026-CS1-Q48_page36.png`,
`2025-CS1-Q59_page59.png`, `2025-CS1-Q59_page60.png` (the original PDF regions), `qcheck-live-20261104.txt` (the full output of the run above).
Re-run it yourself: the comparison is `python scripts/repair_truncated_text.py --paper GATE-CS-2025-S1` (dry run; needs the promoted schema) and
`python -m src.cli papers-drift --db-url sqlite:///data/gate_cse.candidate.sqlite`.

Note on "fresh type MCQ" in the evidence file for Q21/Q48: the extractor alone cannot tell MCQ from MSQ; the stored type MSQ comes from the
official key at load time (both keys list two answers). Not a discrepancy.

---

Checked 4 Nov 2026. Method: (1) rendered each question's stored region from the original PDF and read what is printed;
(2) re-extracted the paper fresh and compared with the stored rows character by character; (3) evaluated every printed option by
computer against the official key. Compared against the live database (130 questions) and a copy carrying the full 29 papers.
**Nothing in your live database was changed by this check.**

## Verdict in one table

| Question | Stored text vs PDF text layer | Stored vs what is printed | Printed options vs official key | Decision |
| --- | --- | --- | --- | --- |
| 2026 Q21 | identical (151 = 151 chars, options identical) | one option's overbar span is lost | A, C correct = key `A;C` | leave text; flag stays |
| 2026 Q37 | identical (528 = 528 chars) | table layout flattened; some overbars detached | B correct = key `B` | leave text; flag stays |
| 2026 Q48 | identical (213 = 213 chars) | content identical; overbars are combining marks | B, D correct = key `B;D` | leave text; flag stays |
| 2025 Q59 | **stored text is 80 characters short** | state-table values missing | min states 5 = key `5` | **proposed:** append the missing 80 characters (audited) - NOT applied yet |

So the auditor-style worry ("3 changed") does not show up as a content defect in any of the three 2026 questions; only Q59 had a real
text gap, and it is the single question out of 1,885 where re-extraction differed from storage.

## 2026 CS-1 Q21 (`GATE-CS-2026-S1-Q21`, MSQ, key A;C)
Printed: `F(P,Q) = (P' + Q) XOR (P'Q)`, options (A) overbar over the whole `P XOR Q`, (B) `P XOR Q`, (C) `P' XOR Q`, (D) `P' XOR Q'`.
- Stem, B, C, D: stored text equals the printed one.
- **Exact difference, option A:** printed as ONE overbar spanning `P ⊕ Q`. Stored as the three characters `𝑃⊕𝑄` followed by eight
  U+0305 (combining overline) code points. The eight bars are the PDF's own drawing of a long overbar; they sit on `Q` only when
  rendered as text, so the "whole expression" meaning is not visible in the text.
- Truth table of F: 1 when P = Q (XNOR). (A) NOT(P XOR Q) = XNOR yes; (B) no; (C) P' XOR Q = XNOR yes; (D) = P XOR Q no. So A and C, equal to the official key.

## 2026 CS-1 Q37 (`GATE-CS-2026-S1-Q37`, MCQ, key B)
- The Next-State table: all 8 rows of values are present in the stored text in row order and equal the printed table
  (000→01, 001→10, 010→11, 011→11, 100→00, 101→00, 110→01, 111→10). Only the row/column *structure* is lost (flat text).
- **Exact difference, options:** overbars are U+0305 runs positioned after the glyph(s) they cover. In 10 places a space sits
  directly before an overbar (option A idx 85; B idx 65, 73, 90; C idx 15, 23, 90; D idx 14, 66, 91). Some are the PDF's trailing
  bars of a subscripted literal (`𝑄 0 ̅̅̅` = Q̄₀, intended); others detach the bar from its letter, e.g. stored `𝑃 ̅𝑄 1` where the paper
  prints P̄Q₁. Reading the PDF gives the intended terms; the text alone is ambiguous in those places.
- Evaluating the four printed options against the table: only (B) reproduces all 8 rows. Equal to the official key.

## 2026 CS-1 Q48 (`GATE-CS-2026-S1-Q48`, MSQ, key B;D)
- Minterm list, stem and all four options match the print exactly. Per-literal overbars are U+0305 (A: 6, B: 5, C: 4, D: 5), each
  directly after its letter. **No difference of content**; the flag is a display caution only.
- Evaluating the printed options: (B) and (D) equal F as functions; (A), (C) do not. Equal to the official key.

## 2025 CS-1 Q59 (`GATE-CS-2025-S1-Q59`, NAT, key 5)
- History: the extractor once read the state table as four phantom options; `repair_nat_type_options.py` (event 3, `repair-script-v5`) set the
  type to NAT and removed them. That left the stored text ending at `... Output f X= 0 X= 1 X= 0 X= 1`.
- **Exact difference:** a fresh extraction of the same PDF region gives the same 277 characters **plus 80 more**:
  `' A F B 0 0 B D C 0 0 C F E 0 0 D G A 1 0 E D C 0 0 F F B 1 1 G G H 0 1 H G A 1 0'`. The stored text is an exact prefix of the fresh
  text; the options are identical (none). The persistence layer correctly refuses to overwrite a row that has a review event, so it never self-healed.
- Check of the table (states A-H; next state/output for X=0 and X=1): partition refinement leaves 5 equivalence classes
  {A,C}, {B,E}, {D,H}, {F}, {G}. The official key is 5.
- **Proposed fix, not yet applied (`scripts/repair_truncated_text.py`, audited):** it appends only the missing tail, only when the stored text is an
  exact prefix of the fresh text, the options are identical and no classification of the question is human-verified; otherwise it only
  reports. Each change is logged in `review_events` (`field=text`, reviewer `extraction-repair-v7`, full before and after). Dry run by
  default; `--yes` takes a verified backup first. Rehearsed on a copy of the live database: 1 text completed, original 3 review
  events unchanged, second run a no-op, **drift check then 65/65 exact on all 29 papers**.
  Not yet applied to the real database: it needs the schema upgrade that `promote` performs, so run it after promotion
  (`.\scripts\dev.ps1 repair-text --paper GATE-CS-2025-S1`, then add `--yes`).

## Why Q21/Q37/Q48 text is not rewritten
Rewriting extracted text with an AI-authored "clean" notation would (a) put words in the exam's mouth, (b) make the stored text stop
matching the PDF, so the drift check could no longer prove stored = source, and (c) change content no human approved. The stored text
is the PDF's own text layer; the review screen always shows the original region next to it. The three questions keep their
`needs_review` flags (reasons already say what to look at) until a human clears them. `docs/handoff/notation-proposals.md` stays as a
reading aid, not a patch. Nothing here is human-verified.

## The outside auditor's 52 / 10 / 3
Still not reproduced: on this machine (Python 3.12.9, PyMuPDF 1.28.2) 2026 CS-1 re-extracts 65/65 exact. The auditor's original file is
not in the project, so the cause cannot be pinned down. The three "changed" records they named are the three above; their stored content
equals the PDF text layer, so a different extraction engine/version is the likely source of their differences (not confirmed).
