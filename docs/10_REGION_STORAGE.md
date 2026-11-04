# 10. Region storage: PDF regions + on-demand previews (replaces stored crops)

## Why
Phase-1 v2 stored one rendered PNG crop per question (65 files, ~5.2 MB for
one paper; projected ~160 MB for 30 papers). The owner asked to keep full
original fidelity (diagrams, tables, fractions, layout) without storing and
managing thousands of image files.

## What changed (v3)
- Extraction now stores each question's REGION in the original PDF instead of
  writing a crop: `Question.regions_json` = a JSON list of
  `{"page": int, "y_top": float, "y_bottom": float}` segments, one per page
  the question touches. Alembic migration `0002_question_regions` adds the
  column (`alembic upgrade head`; the shipped SQLite already has it).
- `src/extraction/render.py::render_question_regions()` renders those regions
  from the source PDF to PNG bytes on demand (PyMuPDF, 110 dpi, same clip
  padding the old crops used). Nothing is written to disk.
- The Review Workspace renders the region live beside the classification.
  Multi-page questions render one image per page, in reading order.
- `extract_questions(..., write_crops=True)` keeps the old PNG-crop behavior
  available for callers that need files; the default is image-free.
- `data/assets/` is gone from the package. The original PDFs in `data/raw/`
  are the single source of truth.
- `Question.image_path` remains in the schema for legacy databases; new
  extractions leave it NULL. The app falls back to it only if a question has
  no stored region.

## Region-boundary rule
Region bounds come from a question's CONTENT lines (running headers/footers
and mark-section headers like "Q.11 - Q.35 Carry ONE mark Each" are excluded).
This matters: a trailing mark-section header of the NEXT section previously
pulled questions onto an extra page (2026 CS-1 Q5, Q10, Q35 looked
"multi-page"); with content-driven bounds all 65 questions of 2026 CS-1 map
to their true single page.

## Verified on the real paper (2026 CS-1)
- All 65 questions have regions; re-extraction changed no question text,
  marks, types, options, keys or classifications (byte-compared against the
  v2 database; MSQ types re-asserted by re-importing the official key).
- Figure/table/fraction questions visually inspected from on-demand renders:
  Q2 (all four figure options), Q7, Q8 (stem figures), Q10 (fraction options
  1/6, 5/18, 7/18, 5/6 render as real fractions), Q37 (state table + boolean
  overlines), Q53 (two SDD tables). All render completely, nothing clipped.
- Automated scan: every large vector graphic in the PDF falls inside some
  question's stored region (only the IIT Guwahati watermark/logo, which
  appear on every page, are outside - by design).
- 23/23 tests pass, including new region/render tests
  (tests/test_regions.py): regions stored for every question, on-demand
  renders are valid non-empty PNGs, multi-page regions render one image per
  page in order, crop writing stays opt-in.

## Scaling
- Per paper: source PDFs (~2.8 MB) + SQLite (~0.3 MB). Regions are ~200 bytes
  per question of JSON. 30 papers ~= 95 MB total, dominated by the source
  PDFs themselves. No image directory, no cloud storage, nothing to sync.

## Known limit
Bounds come from text lines. A figure positioned below a question's last text
line, with no text after it, would be clipped. This did not occur in 2026
CS-1 (all figure questions verified visually); if it appears in a future
paper, widen the affected question's `y_bottom` to the next question's
`y_top` (one-line fix in extraction) and re-extract.
