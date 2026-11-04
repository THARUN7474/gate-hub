# Data inventory: GATE CS papers 2007-2026

Generated on 4 Nov 2026 from `manifests/papers.yaml`, the files in `data/raw` and the 29-paper staging database
(then `data/gate_cse.candidate.sqlite`; since 5 Nov 2026 the same 29 papers are in the live `data/gate_cse.sqlite`). The same tables are live in the app on the **About the Data** screen
(`src/analytics/inventory.py`), so they stay correct when a paper is added. "Paper" = one exam session: 65 questions, 100 marks.

## The answer in numbers

| | Count |
| --- | --- |
| Years covered by files | **20** (2007-2026, every year present) |
| Papers (sessions) registered | **33** = 29 active (2011-2026) + 4 deferred (2007-2010) |
| Question PDFs | **24** (several PDFs hold more than one session) |
| Separate official key PDFs | **9** (2021-2026 only; older keys sit inside the question PDF) |
| Active papers with an official key | **20** of 29 (9 without: 2011, 2013 x4, 2015 x3, 2017 CS-1) |
| Questions in the active papers | **1,885** = 29 x 65, all extracted and reconciled in staging |
| Questions in the live database today | 1,885 (all 29 papers; promoted 5 Nov 2026) |

## Three groups of years

| years | what it is | years count | papers (sessions) | question PDFs | with official key | questions in DB |
| --- | --- | --- | --- | --- | --- | --- |
| 2007-2010 | Deferred (owner decision): photographed booklets, not imported yet | 4 | 4 | 4 | 0 | 0 |
| 2011-2020 | Archive years: one combined PDF per year (or two in 2017); keys inside the PDF, or none | 10 | 19 | 11 | 10 | 1235 |
| 2021-2026 | Recent years: question PDFs plus separate official key PDFs | 6 | 10 | 9 | 10 | 650 |

**2007-2010 (deferred, your decision).** One photographed-booklet PDF per year, no key files. Registered with `status: skip`; nothing
extracted. Whether a PDF contains more than one paper has not been checked yet.

**2011-2020 (archive).** Eleven PDFs for nineteen papers. The pattern differs year to year:
- one PDF holds **several sessions**: 2013 (4 sessions), 2014 (3), 2015 (3), 2016 (2);
- one PDF holds **one paper**: 2011, 2012, 2018, 2019, 2020; 2017 is the only year with **one PDF per session** (CS-1, CS-2);
- keys are **inside the question PDF** (a key table after the questions) for 2012, 2014, 2016, 2017 CS-2, 2018, 2019, 2020, and
  **missing** for 2011, 2013, 2015 and 2017 CS-1 (2015 shows answer ticks from an online test platform - not an official key, not used);
- many are **scans**, read by OCR (2014, 2015, 2020 always; 2011, 2017, 2019 where the text layer is unusable).

**2021-2026 (recent).** Questions and keys come as **separate PDFs**, every paper keyed:
- 2021: one PDF with **both sessions inside** (plus one key PDF covering both; both are scans);
- 2022, 2023: **one paper** each (2022: 7 questions read by OCR where the text layer was unusable);
- 2024, 2025, 2026: **two papers**, one PDF per session, each with its own key PDF.

## Year by year

| year | group | papers (sessions) | question PDFs | files | how bundled | keys | status | questions in DB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2007 | 2007-2010 | 1 | 1 | 2007_CS.pdf | 1 PDF, 1 paper | none | deferred | 0 |
| 2008 | 2007-2010 | 1 | 1 | 2008_CS.pdf | 1 PDF, 1 paper | none | deferred | 0 |
| 2009 | 2007-2010 | 1 | 1 | 2009_CS.pdf | 1 PDF, 1 paper | none | deferred | 0 |
| 2010 | 2007-2010 | 1 | 1 | 2010_CS.pdf | 1 PDF, 1 paper | none | deferred | 0 |
| 2011 | 2011-2020 | 1 | 1 | 2011_CS.pdf | 1 PDF, 1 paper | none | active | 65 |
| 2012 | 2011-2020 | 1 | 1 | 2012_CS.pdf | 1 PDF, 1 paper | inside the question PDF | active | 65 |
| 2013 | 2011-2020 | 4 | 1 | 2013_CS.pdf | 1 PDF, 4 sessions inside | none | active | 260 |
| 2014 | 2011-2020 | 3 | 1 | 2014_CS.pdf | 1 PDF, 3 sessions inside | inside the question PDF | active | 195 |
| 2015 | 2011-2020 | 3 | 1 | 2015_CS.pdf | 1 PDF, 3 sessions inside | none | active | 195 |
| 2016 | 2011-2020 | 2 | 1 | 2016_CS.pdf | 1 PDF, 2 sessions inside | inside the question PDF | active | 130 |
| 2017 | 2011-2020 | 2 | 2 | 2017_CS1.pdf, 2017_CS2.pdf | 1 PDF per session | 1 of 2 sessions keyed | active | 130 |
| 2018 | 2011-2020 | 1 | 1 | 2018_CS.pdf | 1 PDF, 1 paper | inside the question PDF | active | 65 |
| 2019 | 2011-2020 | 1 | 1 | 2019_CS.pdf | 1 PDF, 1 paper | inside the question PDF | active | 65 |
| 2020 | 2011-2020 | 1 | 1 | 2020_CS.pdf | 1 PDF, 1 paper | inside the question PDF | active | 65 |
| 2021 | 2021-2026 | 2 | 1 | CS_2021.pdf | 1 PDF, 2 sessions inside | separate key PDF: CS_Keys_2021.pdf | active | 130 |
| 2022 | 2021-2026 | 1 | 1 | CS_2022.pdf | 1 PDF, 1 paper | separate key PDF: CS_Keys_2022.pdf | active | 65 |
| 2023 | 2021-2026 | 1 | 1 | CS_2023.pdf | 1 PDF, 1 paper | separate key PDF: CS_Keys_2023.pdf | active | 65 |
| 2024 | 2021-2026 | 2 | 2 | CS1_2024.pdf, CS2_2024.pdf | 1 PDF per session | separate key PDFs: CS1_Keys_2024.pdf, CS2_Keys_2024.pdf | active | 130 |
| 2025 | 2021-2026 | 2 | 2 | CS1_2025.pdf, CS2_2025.pdf | 1 PDF per session | separate key PDFs: CS1_Keys_2025.pdf, CS2_Keys_2025.pdf | active | 130 |
| 2026 | 2021-2026 | 2 | 2 | CS1_2026.pdf, CS2_2026.pdf | 1 PDF per session | separate key PDFs: CS1_Keys_2026.pdf, CS2_Keys_2026.pdf | active | 130 |

## Every paper (session)

| paper_id | status | question_pdf | pages | papers_in_this_pdf | key_source | layout | read_by_ocr | in_db_questions | in_db_keys | in_db_ocr_questions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GATE-CS-2007-S1 | deferred | data/raw/papers/2007_CS.pdf | all | 1 | not checked (deferred) | - | - | 0 | 0 | 0 |
| GATE-CS-2008-S1 | deferred | data/raw/papers/2008_CS.pdf | all | 1 | not checked (deferred) | - | - | 0 | 0 | 0 |
| GATE-CS-2009-S1 | deferred | data/raw/papers/2009_CS.pdf | all | 1 | not checked (deferred) | - | - | 0 | 0 | 0 |
| GATE-CS-2010-S1 | deferred | data/raw/papers/2010_CS.pdf | all | 1 | not checked (deferred) | - | - | 0 | 0 | 0 |
| GATE-CS-2011-S1 | active | data/raw/papers/2011_CS.pdf | 2-17 | 1 | none (no key file supplied) | cs-first-continuous | if needed | 65 | 0 | 65 |
| GATE-CS-2012-S1 | active | data/raw/papers/2012_CS.pdf | 2-17 | 1 | inside the question PDF pp.18-19 | cs-first-continuous | if needed | 65 | 65 | 0 |
| GATE-CS-2013-S1 | active | data/raw/papers/2013_CS.pdf | 2-15 | 4 | none (no key file supplied) | cs-first-continuous | if needed | 65 | 0 | 0 |
| GATE-CS-2013-S2 | active | data/raw/papers/2013_CS.pdf | 17-30 | 4 | none (no key file supplied) | cs-first-continuous | if needed | 65 | 0 | 0 |
| GATE-CS-2013-S3 | active | data/raw/papers/2013_CS.pdf | 32-45 | 4 | none (no key file supplied) | cs-first-continuous | if needed | 65 | 0 | 0 |
| GATE-CS-2013-S4 | active | data/raw/papers/2013_CS.pdf | 47-60 | 4 | none (no key file supplied) | cs-first-continuous | if needed | 65 | 0 | 0 |
| GATE-CS-2014-S1 | active | data/raw/papers/2014_CS.pdf | 6-21 | 3 | inside the question PDF pp.22-22 | ga-first-restart | always | 65 | 65 | 65 |
| GATE-CS-2014-S2 | active | data/raw/papers/2014_CS.pdf | 28-44 | 3 | inside the question PDF pp.45-45 | ga-first-restart | always | 65 | 65 | 65 |
| GATE-CS-2014-S3 | active | data/raw/papers/2014_CS.pdf | 51-66 | 3 | inside the question PDF pp.67-67 | ga-first-restart | always | 65 | 65 | 65 |
| GATE-CS-2015-S1 | active | data/raw/papers/2015_CS.pdf | 2-25 | 3 | none (no key file supplied) | platform-export | always | 65 | 0 | 65 |
| GATE-CS-2015-S2 | active | data/raw/papers/2015_CS.pdf | 27-51 | 3 | none (no key file supplied) | platform-export | always | 65 | 0 | 65 |
| GATE-CS-2015-S3 | active | data/raw/papers/2015_CS.pdf | 53-79 | 3 | none (no key file supplied) | platform-export | always | 65 | 0 | 65 |
| GATE-CS-2016-S1 | active | data/raw/papers/2016_CS.pdf | 1-20 | 2 | inside the question PDF pp.21-22 | ga-first-restart | if needed | 65 | 65 | 0 |
| GATE-CS-2016-S2 | active | data/raw/papers/2016_CS.pdf | 23-43 | 2 | inside the question PDF pp.44-45 | ga-first-restart | if needed | 65 | 65 | 0 |
| GATE-CS-2017-S1 | active | data/raw/papers/2017_CS1.pdf | 2-27 | 1 | none (no key file supplied) | qnum-export | if needed | 65 | 0 | 65 |
| GATE-CS-2017-S2 | active | data/raw/papers/2017_CS2.pdf | 2-25 | 1 | inside the question PDF pp.26-27 (scanned image, OCR) | qnum-export | if needed | 65 | 65 | 65 |
| GATE-CS-2018-S1 | active | data/raw/papers/2018_CS.pdf | 1-23 | 1 | inside the question PDF pp.24-26 | ga-first-restart | if needed | 65 | 65 | 0 |
| GATE-CS-2019-S1 | active | data/raw/papers/2019_CS.pdf | 1-16 | 1 | inside the question PDF pp.17-19 (scanned image, OCR) | ga-first-restart | if needed | 65 | 65 | 65 |
| GATE-CS-2020-S1 | active | data/raw/papers/2020_CS.pdf | 1-16 | 1 | inside the question PDF pp.17-18 | ga-first-restart | always | 65 | 65 | 65 |
| GATE-CS-2021-S1 | active | data/raw/papers/2021/CS_2021.pdf | 2-41 | 2 | separate key PDF CS_Keys_2021.pdf pp.1-3 (scanned image, OCR) | ga-first-restart | if needed | 65 | 65 | 65 |
| GATE-CS-2021-S2 | active | data/raw/papers/2021/CS_2021.pdf | 46-88 | 2 | separate key PDF CS_Keys_2021.pdf pp.4-6 (scanned image, OCR) | ga-first-restart | if needed | 65 | 65 | 65 |
| GATE-CS-2022-S1 | active | data/raw/papers/2022/CS_2022.pdf | 1-41 | 1 | separate key PDF CS_Keys_2022.pdf | continuous-modern | if needed | 65 | 65 | 7 |
| GATE-CS-2023-S1 | active | data/raw/papers/2023/CS_2023.pdf | all | 1 | separate key PDF CS_Keys_2023.pdf | continuous-modern | if needed | 65 | 65 | 0 |
| GATE-CS-2024-S1 | active | data/raw/papers/2024/CS1_2024.pdf | all | 1 | separate key PDF CS1_Keys_2024.pdf | continuous-modern | if needed | 65 | 65 | 0 |
| GATE-CS-2024-S2 | active | data/raw/papers/2024/CS2_2024.pdf | all | 1 | separate key PDF CS2_Keys_2024.pdf | continuous-modern | if needed | 65 | 65 | 0 |
| GATE-CS-2025-S1 | active | data/raw/papers/2025/CS1_2025.pdf | all | 1 | separate key PDF CS1_Keys_2025.pdf | continuous-modern | if needed | 65 | 65 | 0 |
| GATE-CS-2025-S2 | active | data/raw/papers/2025/CS2_2025.pdf | all | 1 | separate key PDF CS2_Keys_2025.pdf | continuous-modern | if needed | 65 | 65 | 0 |
| GATE-CS-2026-S1 | active | data/raw/papers/2026/CS1_2026.pdf | all | 1 | separate key PDF CS1_Keys_2026.pdf | continuous-modern | if needed | 65 | 65 | 0 |
| GATE-CS-2026-S2 | active | data/raw/papers/2026/CS2_2026.pdf | all | 1 | separate key PDF CS2_Keys_2026.pdf | continuous-modern | if needed | 65 | 65 | 0 |

## What this means for analysis
- Years differ in how many papers they contribute (1 to 4). Comparing raw year totals over-weights 2013-2016 and the two-session years; use
  the **Average over sessions** switch in the Analysis Matrix when comparing years.
- 9 papers (585 questions) can be classified and analysed by topic, but have no official answer to show (docs/16_MISSING_SOURCES.md).
- Scanned papers need a closer human look in review (formulas, figures); the original image is always shown.
- Adding a new paper (e.g. GATE 2027): copy the nearest entry in `manifests/papers.yaml` (docs/15_DATA_ONBOARDING.md); it then appears here automatically.
