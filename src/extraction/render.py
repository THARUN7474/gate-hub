"""On-demand rendering of question regions from the original source PDF.
Regions (page + y-range per page) are stored on each question at extraction
time; nothing is written to disk. This replaces permanently stored per-
question crop PNGs: the PDF stays the single source of truth, previews are
regenerated whenever viewed, and figures/tables/fractions always render in
their original layout."""
from __future__ import annotations
from pathlib import Path
import pymupdf as fitz  # PyMuPDF (pymupdf is the supported import name; `fitz` is deprecated)

def render_question_regions(pdf_path: str | Path, regions: list[dict],
                            dpi: int = 110, pad_top: float = 10,
                            pad_bottom: float = 12) -> list[dict]:
    """Render each stored region segment to PNG bytes.
    Returns one item per segment: {"page": int, "png": bytes}. A question
    spanning pages yields one image per page, in reading order."""
    doc = fitz.open(str(pdf_path))
    out = []
    try:
        for seg in regions:
            page = doc[int(seg["page"]) - 1]
            top = max(float(seg["y_top"]) - pad_top, 0)
            bottom = min(float(seg["y_bottom"]) + pad_bottom, page.rect.height)
            clip = fitz.Rect(0, top, page.rect.width, bottom)
            pix = page.get_pixmap(clip=clip, dpi=dpi)
            out.append({"page": int(seg["page"]), "png": pix.tobytes("png")})
    finally:
        doc.close()
    return out
