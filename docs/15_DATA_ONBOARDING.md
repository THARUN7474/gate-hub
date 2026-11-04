# Data onboarding: raw PDFs -> papers -> questions (4 Nov 2026)

How the 2011-2026 corpus in `data/raw/` becomes rows, how to check it, and how to add a new paper
(e.g. GATE 2027). Everything is driven by **`manifests/papers.yaml`**.

## What was supplied and how each file is read

| Years | Files | Text layer | How it is read | Key |
| --- | --- | --- | --- | --- |
| 2007-2010 | `papers/20xx_CS.pdf` | none (photographed pages) | **deferred by the owner** (`status: skip`) | - |
| 2011 | `2011_CS.pdf` | none (scan) | OCR | none supplied |
| 2012 | `2012_CS.pdf` | digital | text; booklet code A | embedded table pp.18-19 (4 codes; Code A read) |
| 2013 | `2013_CS.pdf` (4 sessions in one PDF) | digital | text; split by page range | none supplied |
| 2014 | `2014_CS.pdf` (3 sessions) | digital but **shattered into glyph fragments** | OCR (`ocr: always`) | embedded range table per session |
| 2015 | `2015_CS.pdf` (3 sessions) | scan / platform export | OCR | none supplied (answer ticks are printed in the PDF but are not an official key) |
| 2016 | `2016_CS.pdf` (2 sessions) | digital | text | embedded table per session |
| 2017 | `2017_CS1.pdf`, `2017_CS2.pdf` | image bodies + header text | OCR | CS-2 has an embedded key table (OCR); CS-1 none |
| 2018 | `2018_CS.pdf` | digital | text | embedded table |
| 2019 | `2019_CS.pdf` | scan | OCR | embedded table (OCR) |
| 2020 | `2020_CS.pdf` | scan + overlay | OCR (`ocr: always`) | embedded table (text) |
| 2021 | `2021/CS_2021.pdf` (2 sessions) + `keys/2021/CS_Keys_2021.pdf` | scan | OCR | official key PDF (image, OCR) |
| 2022-2026 | `papers/<y>/CS*.pdf`, `keys/<y>/*.pdf` | digital | text | official tabular key PDFs (2025/2026 CS1 also have CSVs) |

Totals: **29 loadable papers, 1,885 questions, 1,300 keyed questions (20 papers)**. Every loadable paper reconciles
to 65 questions / 100 marks. Papers without a key file are shown as such in the UI; keys are never guessed.

## Layout families the extractor handles

- `cs-first-continuous` (2011-2013): CS Q1-55, GA Q56-65, numbering 1..65.
- `ga-first-restart` (2014-2021): GA Q1-10, then CS restarts at Q1. CS questions are stored as **Q11-65**
  so ids match the official keys; the number printed in the paper is kept in `questions.printed_label`
  (`GA 5`, `CS 12`). A restart is accepted only once, right after ~10 GA questions (a stray `Q.1` inside a stem is not one).
- `continuous-modern` (2022-2026): 1..65 straight through.
- `qnum-export` (2017) and `platform-export` (2015): `Question Number : N ...` headers; 2017 also prints marks.
- Shared stems ("Common Data for Questions 48 and 49", linked answers, <=2013) are cut out of the previous question and
  prepended to both questions (`group_id`).

Quality gates per question (all flagged `needs_review`, never silent): marks inferred from the fixed GATE pattern when no
mark header exists, option count not 0 or 4, empty/figure option text, low OCR confidence, a question label OCR could not
read (the boundary is rebuilt from the option layout and flagged), key type/marks disagreeing with extraction.

## OCR in one paragraph

`src/extraction/ocr.py` (RapidOCR, pip-only, no admin install) turns scanned pages into the same line records the
digital path produces, caches them in `data/extracted/ocr/<pdf-sha16>/pNNNN.json` (so re-extraction is fast and
deterministic), and flags low-confidence questions. Whether a PDF is digital or scanned is decided **per document**
(digital papers have >=50% pages with >=300 non-space characters); within a digital PDF a page is OCR'd only if it has
no text or its text layer is garbled (>4% alien code points). OCR text is good for prose and unreliable for formulas -
the Review Workspace therefore always shows the original PDF region and says so.

## Commands

```powershell
.\scripts\dev.ps1 probe                         # extract everything IN MEMORY, print the 65/100 gate per paper (no DB writes)
.\scripts\dev.ps1 load                          # register + extract + reconcile + import keys into the CURRENT database (idempotent)
.venv\Scripts\python -m src.cli papers-drift    # re-extract every paper and compare with the database (exact/normalized/changed)
.\scripts\dev.ps1 promote [--yes]               # same loader, applied to the LIVE database with backup + before/after proof
```

## Adding a paper (GATE 2027, a new session, a re-scan)

1. Put the PDF under `data/raw/papers/` and its key under `data/raw/keys/`.
2. Copy the nearest entry in `manifests/papers.yaml`, set `year`, `session` (`CS-1`, `CS-2`...), `file`, `pages`
   (the question pages only, 1-based) and the `key:` block. Layout kinds for keys: `tabular`, `ocr-tabular`,
   `embedded-table`, `ocr-embedded-table`, `embedded-range`, `embedded-codes`.
3. `.\scripts\dev.ps1 probe --only 2027` - it must say `OK ... q=65 marks=100.0`. If not, the report names the missing
   numbers/flags; do not load it until it reconciles or you understand why.
4. `.\scripts\dev.ps1 load --only 2027`, then `papers-drift --only 2027` (should be all exact on a second run).
`python -m src.cli doctor` warns about PDFs in `data/raw/papers` that are not in the manifest.

## Evidence (run on this machine, 4 Nov 2026)

- `papers-probe`: 29/29 reconcile (65 questions, 100.0 marks).
- `papers-load`: 20 keys imported, **0 key-vs-extraction marks mismatches**; type mismatches only in OCR'd papers
  (2014: 7/4/4, 2017-CS2: 4, 2019: 2, 2021: 2+2) and each is flagged on its question.
- `papers-drift` on the loaded database: **28/29 papers re-extract byte-identical** (1,884 of 1,885 questions exact). The one
  difference is 2025-CS1 Q59, a row a repair script touched earlier: the stored text lacks the state-table values that a
  fresh extraction includes; persistence refuses to overwrite it because it has a review event.
- 2025-CS1: 61 questions had page headers fused into option text (the old regex only knew the American spelling
  "Organizing"); repaired by `papers-load --refresh` (touches only rows no human has touched). Its 13 MSQ questions now
  carry the right type (the old key CSV used a different vocabulary).
- 2026-CS1: 65/65 exact vs the stored rows (unchanged by any of this).

## Known limits

- OCR errors in formulas/subscripts; some question stems/options of scanned papers will need a human look
  (they are flagged: about 5-30 per scanned paper).
- Papers with no key file: 2011, 2013 (4 sessions), 2015 (3), 2017-CS1.
- Key anomalies, each carrying a note on its row: 2 OCR'd key rows repaired from table order (2021-CS1 Q48, Q49: OCR read
  `38`/`39` as `83`/`63`); 1 OCR artefact `CORD` read as `C;D` (2021-CS1 Q9 - **verify against the key image**); 4 NAT keys that accept
  more than one range (2019 Q52, 2020 Q31, 2021-CS1 Q33, 2023 Q30 - all ranges stored); 1 MCQ accepting two options (2019 Q22);
  8 marks-to-all (2012 Q3/29/38/39/45/60, 2020 Q17, 2023 Q2 - stored as `dropped`).
- 2007-2010 not imported.
- Only 2026 CS-1 is classified (65 suggestions, 0 verified). The rest can be classified without a key through chat batches
  (docs/20_CHAT_ASSISTED_CLASSIFICATION.md) or with a provider key (docs/13_LLM_SETUP.md).
