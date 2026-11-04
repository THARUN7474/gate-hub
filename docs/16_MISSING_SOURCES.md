# Missing sources (what is not here, and what that costs)

Written 4 Nov 2026 from the loaded data (`manifests/papers.yaml`, `data/raw`, the 29-paper database).
Rule applied everywhere: **a missing official answer key is listed, never guessed or back-filled.**

## 1. Nine papers have no official answer key

| Paper | Source file (pages) | Questions | Marks sum | Type NULL | Flagged for review | Why there is no key |
| --- | --- | --- | --- | --- | --- | --- |
| 2011 CS | `data/raw/papers/2011_CS.pdf` (2-17) | 65 | 100 | 1 | 6 | no key file supplied (scanned booklet, read by OCR) |
| 2013 CS-1 | `2013_CS.pdf` (2-15) | 65 | 100 | 2 | 5 | no key file supplied |
| 2013 CS-2 | `2013_CS.pdf` (17-30) | 65 | 100 | 2 | 5 | no key file supplied |
| 2013 CS-3 | `2013_CS.pdf` (32-45) | 65 | 100 | 2 | 5 | no key file supplied |
| 2013 CS-4 | `2013_CS.pdf` (47-60) | 65 | 100 | 2 | 5 | no key file supplied |
| 2015 CS-1 | `2015_CS.pdf` (2-25) | 65 | 100 | 0 | 12 | PDF is a quiz-platform export with answer ticks printed in it; **no official key file** |
| 2015 CS-2 | `2015_CS.pdf` (27-51) | 65 | 100 | 0 | 13 | same |
| 2015 CS-3 | `2015_CS.pdf` (53-79) | 65 | 100 | 0 | 16 | same |
| 2017 CS-1 | `2017_CS1.pdf` (2-27) | 65 | 100 | 2 | 4 | export without a key table (2017 CS-2 has one, so it is keyed) |

The other 20 papers (2012, 2014 x3, 2016 x2, 2017 CS-2, 2018-2026) have an official key: 1,300 key rows loaded, 0 marks mismatches
against the extraction.

**The printed ticks in the 2015 export are not used.** They are not an official key, and using them would be guessing. They are
visible in the PDF region for a human reviewer.

### What still works for these nine papers
- All 585 questions are extracted and reconcile (65 questions, 100 marks each). Marks come from the paper itself.
- They can be classified like any other paper: classification reads the question text, not the key.
- Topic/marks analysis counts them (it counts classified questions only).

### What does not work for them
- No official answer is shown or checked. The "answer" panel for these questions says there is no key.
- The key-vs-extraction cross-check (question type MCQ/MSQ/NAT, marks) cannot run. Types come from the extractor alone, so
  **11 questions have type NULL** (2011: 1; 2013: 2 in each of 4 sessions = 8; 2017 CS-1: 2). NULL types are never
  guessed: those questions route to human review.
- OCR'd papers (2011, 2015, 2017) have 4-16 flagged questions each, mostly figure-only options and OCR text to check against the
  PDF region.

### What you can supply (any one is enough per paper)
Official GATE answer keys for those years, as a PDF or CSV. Put them under `data/raw/keys/<year>/`, then:
1. add a `key:` entry to that paper in `manifests/papers.yaml` (copy a similar entry, e.g. the 2022 `tabular` one; scanned key
   images use `ocr-tabular`),
2. `.\scripts\dev.ps1 load --only <year>` (idempotent: adds keys, never touches review decisions),
3. `.\scripts\dev.ps1 doctor` (should no longer list the paper as missing a key).

## 2. Deferred by you: 2007-2010
Four photographed-booklet PDFs (`2007_CS.pdf` ... `2010_CS.pdf`) are registered with `status: skip`. Nothing was extracted or
guessed. They need either better scans or a dedicated OCR pass; say when you want them.

## 3. Not missing, but worth knowing
- 2013 is one PDF with four sessions and 2015 is one PDF with three: each session is its own paper in the database.
- 2012 uses a key table inside the question PDF (Code A), parsed and cross-checked.
- 2021-CS1 Q9: the OCR read a key cell as `CORD` and it was stored as `C;D`. **Verify against the key image** (flagged on the row).
- 8 questions have marks-to-all / dropped keys (2012 Q3/29/38/39/45/60, 2020 Q17, 2023 Q2): stored as `dropped`, not as a letter.
