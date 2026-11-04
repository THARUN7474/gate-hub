"""OCR for scanned/image-only PDF pages (pip-only engine, no admin install).

Why this exists: GATE papers before 2022 are frequently distributed as
rasterised pages (2011, 2015, 2017, 2019, 2020, 2021 here). They carry no text
layer, so the digital extractor sees nothing. This module turns such a page
into the SAME line dicts the digital path produces ({page, y, y1, x, text}),
in PDF point coordinates, so segmentation, regions and the on-demand source
preview all keep working unchanged.

Honesty rules:
  * Every OCR line keeps its recognition confidence; the extractor flags
    questions whose lines are low-confidence.
  * Math/figures OCR badly. The stored region always points at the ORIGINAL
    page, so a reviewer sees the real question; OCR text is only a search /
    classification aid and is marked extraction_status='ocr'.
  * Results are cached on disk keyed by the PDF's sha256, so re-extraction is
    deterministic and fast, and drift-check can compare like with like.

Engine: RapidOCR (ONNX runtime, PP-OCR models). Optional dependency - the
digital pipeline never imports this module unless a page needs OCR.
"""
from __future__ import annotations
import hashlib, json, re, sys
from pathlib import Path

DEFAULT_DPI = 200
CACHE_ROOT = Path("data/extracted/ocr")
ENGINE_TAG = "rapidocr-ppocr"
MIN_TEXT_CHARS = 300          # NON-WHITESPACE text-layer chars; fewer AND an image => scanned page
                              # (whitespace is excluded: GATE 2017 header lines are padded with hundreds of spaces)

def _nonws_len(text: str) -> int:
    return len("".join(text.split()))
_engine = None

def pdf_sha(pdf_path: str | Path) -> str:
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def doc_scan_mode(doc, first: int = 1, last: int | None = None) -> str:
    """'digital' or 'scanned' for a page range, decided on the WHOLE range.

    A per-page rule cannot work: sparse digital pages (one short question per
    page, ~300 chars + a figure) look just like hybrid scans whose text layer
    is only a 'Question Number : N' header. Measured on the real 2011-2026
    files, digital papers have >=80% of pages with >= MIN_TEXT_CHARS of text,
    scanned/hybrid ones <= 17%. Threshold: half the pages."""
    last = min(last or len(doc), len(doc))
    pages = range(first - 1, last)
    if not len(pages):
        return "digital"
    rich = sum(1 for p in pages if _nonws_len(doc[p].get_text()) >= MIN_TEXT_CHARS)
    return "digital" if rich >= 0.5 * len(pages) else "scanned"

GARBLE_RATIO = 0.04

def _alien(ch: str) -> bool:
    """Code points that never occur in English GATE text but do appear when a PDF's
    math/symbol font is mis-mapped: Hebrew/Arabic/Syriac/Thaana, Indic scripts,
    private-use area (U+E000-F8FF) and the specials block."""
    o = ord(ch)
    return (0x0590 <= o <= 0x08FF) or (0x0900 <= o <= 0x0DFF) or (0xE000 <= o <= 0xF8FF) or (0xFFF0 <= o <= 0xFFFF)

def garble_ratio(text: str) -> float:
    t = [c for c in text if not c.isspace()]
    if len(t) < 40:
        return 0.0
    return sum(1 for c in t if _alien(c)) / len(t)

def page_needs_ocr(page, mode: str = "scanned") -> bool:
    """Per-page OCR decision inside a document whose mode is already known.
    any doc     : a page whose text layer is garbled (glyph-encoded math) is OCR'd,
                  because the rendered page is readable even when the text is not.
    digital doc : OCR a page that has an image and (almost) no text at all.
    scanned doc : OCR any page with an image and a thin text layer.
    Blank separator pages ('SESSION - 1') carry no image and are left alone."""
    txt = page.get_text()
    if garble_ratio(txt) > GARBLE_RATIO:
        return True
    chars = _nonws_len(txt)
    if not page.get_images():
        return False
    return chars < 20 if mode == "digital" else chars < MIN_TEXT_CHARS

def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr import RapidOCR
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("OCR needed but 'rapidocr' is not installed: pip install rapidocr onnxruntime") from e
        import logging
        logging.getLogger("RapidOCR").setLevel(logging.WARNING)
        _engine = RapidOCR()
    return _engine

_QLABEL = re.compile(r"^Q\.?\s*\d{1,3}\.?$", re.I)

def _group_rows(boxes: list[dict]) -> list[dict]:
    """Cluster OCR boxes into visual rows and return line dicts ordered by
    (row, x). A bare question label ('Q.12') is merged with the box to its
    right on the same row so it reads 'Q.12 <stem text>' like a digital line."""
    if not boxes:
        return []
    boxes = sorted(boxes, key=lambda b: (b["cy"], b["x"]))
    rows: list[list[dict]] = []
    for b in boxes:
        if rows:
            last = rows[-1]
            ref = last[0]
            tol = 0.55 * min(b["h"], ref["h"])
            if abs(b["cy"] - ref["cy"]) <= tol:
                last.append(b)
                continue
        rows.append([b])
    out: list[dict] = []
    for row in rows:
        row.sort(key=lambda b: b["x"])
        i = 0
        while i < len(row):
            b = row[i]
            if _QLABEL.match(b["text"].strip()) and i + 1 < len(row) and row[i + 1]["x"] - (b["x"] + b["w"]) < 90:
                nxt = row[i + 1]
                merged = {"text": b["text"].strip() + " " + nxt["text"].strip(),
                          "x": b["x"], "y": min(b["y"], nxt["y"]), "y1": max(b["y1"], nxt["y1"]),
                          "conf": min(b["conf"], nxt["conf"])}
                out.append(merged); i += 2
            else:
                out.append({"text": b["text"].strip(), "x": b["x"], "y": b["y"], "y1": b["y1"], "conf": b["conf"]})
                i += 1
    return [l for l in out if l["text"]]

def ocr_page(doc, pno: int, sha: str, dpi: int = DEFAULT_DPI, cache_root: Path | None = None) -> list[dict]:
    """OCR page index `pno` (0-based). Returns line dicts in PDF points. Cached."""
    cache_root = Path(cache_root) if cache_root else CACHE_ROOT
    cdir = cache_root / sha[:16]
    cfile = cdir / f"p{pno + 1:04d}.json"
    if cfile.exists():
        data = json.loads(cfile.read_text(encoding="utf-8"))
        return [dict(l, page=pno + 1) for l in data["lines"]]
    import numpy as np
    page = doc[pno]
    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
    res = _get_engine()(img)
    scale = 72.0 / dpi
    boxes = []
    if res is not None and getattr(res, "boxes", None) is not None:
        for box, txt, sc in zip(res.boxes, res.txts, res.scores):
            xs = [float(p[0]) for p in box]; ys = [float(p[1]) for p in box]   # numpy -> plain float (JSON-safe)
            y0, y1, x0, x1 = min(ys) * scale, max(ys) * scale, min(xs) * scale, max(xs) * scale
            boxes.append({"text": str(txt), "x": x0, "w": x1 - x0, "y": y0, "y1": y1,
                          "h": max(y1 - y0, 1.0), "cy": (y0 + y1) / 2, "conf": float(sc)})
    lines = _group_rows(boxes)
    cdir.mkdir(parents=True, exist_ok=True)
    cfile.write_text(json.dumps({"engine": ENGINE_TAG, "dpi": dpi, "page": pno + 1, "lines": lines},
                                ensure_ascii=False), encoding="utf-8")
    return [dict(l, page=pno + 1) for l in lines]

def warm_cache(pdf_path: str | Path, dpi: int = DEFAULT_DPI, pages: list[int] | None = None,
               force_all: bool = False, log=print) -> dict:
    """OCR every page of `pdf_path` that needs it (or all, with force_all)."""
    import pymupdf
    sha = pdf_sha(pdf_path)
    doc = pymupdf.open(str(pdf_path))
    todo = []
    mode = doc_scan_mode(doc)
    for pno in range(len(doc)):
        if pages and (pno + 1) not in pages:
            continue
        if force_all or page_needs_ocr(doc[pno], mode):
            todo.append(pno)
    done = 0
    total = len(doc)
    for n, pno in enumerate(todo, 1):
        ocr_page(doc, pno, sha, dpi)
        done += 1
        if n % 10 == 0 or n == len(todo):
            log(f"  {Path(pdf_path).name}: OCR {n}/{len(todo)} pages")
    doc.close()
    return {"pdf": str(pdf_path), "sha16": sha[:16], "pages_total": total, "ocr_pages": done}

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Warm the OCR cache for scanned PDFs")
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    ap.add_argument("--all-pages", action="store_true")
    a = ap.parse_args()
    for p in a.pdfs:
        print(json.dumps(warm_cache(p, a.dpi, force_all=a.all_pages)), flush=True)
