"""Extraction: PDF -> Question/Option rows + source-PDF region references.

Digital extraction first (PyMuPDF layout spans); scanned pages fall back to a
cached OCR pass (src/extraction/ocr.py) that yields the same line dicts.
Segmentation is SEQUENCE-AWARE: a line only starts a question if its number is
the next expected one (or the single GA->CS restart), so stray 'Q.1' text in a
header or stem cannot create phantom questions. Marks come from printed
mark-section headers (cross-checked against the fixed GATE pattern); type
combines headers with option structure. Unknown marks/type stay NULL and route
to review - never guessed silently. Each question stores its REGION in the
original PDF (page + y-range per page, JSON on Question.regions_json); the
review workspace renders that region on demand (src/extraction/render.py), so
no per-question image files are stored.

Layout families handled (all discovered on the real 2011-2026 papers):
  * CS first, GA last, continuous numbering 1-65        (2011-2013)
  * GA first (Q1-10) then CS restarting at Q1 (-55)     (2014-2021): the CS
    questions are renumbered 11-65 so ids are unique and match official keys;
    the printed label (e.g. 'CS 12') is kept in Question.printed_label
  * GA first, continuous numbering 1-65                 (2022-2026)
  * 'Question Number : N  Correct : 1  Wrong : -0.33'    (GATE 2017 export)
  * Common-data / linked-answer preambles shared by two questions (<=2013)
"""
from __future__ import annotations
import json, re
from pathlib import Path
import pymupdf as fitz  # PyMuPDF (pymupdf is the supported import name; `fitz` is deprecated)
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db.models import Classification, Option, Paper, Question, ReviewEvent
from ..validation.drift import drift_status

Q_START = re.compile(r"^Q\.?\s*(?:No\.?\s*)?(\d{1,3})(?!\d)[.)]?\s*(.*)")   # 'Q.5', 'Q. 5', 'Q.No. 5', OCR 'Q.No. 32Consider'
QNUM_HDR = re.compile(r"^Question\s+Number\s*[:：.]?\s*(\d{1,3})\b", re.I)    # OCR sometimes returns a full-width colon
CORRECT_MARKS = re.compile(r"Correct\s*[:.]?\s*(\d)\b", re.I)
OPTION = re.compile(r"^\(?([A-D])\)?[.)]\s+(.*)")
OPT_LABEL_ONLY = re.compile(r"^\(?([A-D])\)?[.)]?\s*$")
HEADER_FOOTER = re.compile(
    r"^(Organizing Institute:|Page\s+\d+\s+of\s+\d+|"   # \s+: 2022-S1/2023-S1 print "Page  N  of  41"
    r"Computer Science (?:&|and) Information Technology \(CS\d?\)|"
    r"General Aptitude \(GA\))")
MARKS_HEADER = re.compile(r"carry\s+(ONE|TWO|1|2)\s+marks?", re.IGNORECASE)
RANGE_HDR = re.compile(r"^Q\.?\s*(\d{1,3})\s*(?:[–—-]+|to)\s*Q?\.?\s*(\d{1,3})\b", re.I)
RANGE_MARKS = re.compile(
    r"Q\.?\s*(\d{1,3})\s*(?:to|[–—-]+)\s*Q?\.?\s*(\d{1,3})\s*(?:[A-Za-z]+\s+){0,3}?carry\s+(ONE|TWO|1|2)\s+marks?", re.I)
PREAMBLE = re.compile(r"^(Common\s+Data|Linked\s+Answer|Statement\s+for\s+Linked)", re.I)
PRE_NUMS = re.compile(r"(?:Questions?|Q\.?)\s*(\d{1,3})\s*(?:and|&|to|,|-|–)\s*(?:Q\.?\s*)?(\d{1,3})", re.I)
PRE_PURE_HEADER = re.compile(r"^(Common\s+Data\s+Questions|Linked\s+Answer\s+Questions)\s*:?\s*$", re.I)

def pattern_marks(canon_no: int, ga_first: bool) -> float | None:
    """Fixed GATE structure. Used only as a CROSS-CHECK and a FLAGGED fallback."""
    if ga_first:
        if 1 <= canon_no <= 5: return 1.0
        if 6 <= canon_no <= 10: return 2.0
        if 11 <= canon_no <= 35: return 1.0
        if 36 <= canon_no <= 65: return 2.0
    else:
        if 1 <= canon_no <= 25: return 1.0
        if 26 <= canon_no <= 55: return 2.0
        if 56 <= canon_no <= 60: return 1.0
        if 61 <= canon_no <= 65: return 2.0
    return None

# --------------------------------------------------------------------------
# Line sources
# --------------------------------------------------------------------------
def _row_sort(lines: list[dict]) -> list[dict]:
    """Reading order: cluster lines into visual rows (centre-y within half a line
    height), rows top->bottom, left->right inside a row."""
    ordered = sorted(lines, key=lambda l: ((l["y"] + l["y1"]) / 2, l["x"]))
    rows: list[list[dict]] = []
    for l in ordered:
        cy = (l["y"] + l["y1"]) / 2
        if rows:
            ref = rows[-1][0]
            rcy = (ref["y"] + ref["y1"]) / 2
            if abs(cy - rcy) <= 0.5 * min(max(l["y1"] - l["y"], 1.0), max(ref["y1"] - ref["y"], 1.0)):
                rows[-1].append(l); continue
        rows.append([l])
    out: list[dict] = []
    for r in rows:
        out.extend(sorted(r, key=lambda l: l["x"]))
    return out

def _needs_reading_order(lines: list[dict], page_h: float) -> bool:
    """True when a question label sits physically ABOVE content lines that precede it
    in the PDF content stream (LaTeX exports emit 'Q.39' after its text; figure pages
    emit diagram labels late). Margin lines (running header/footer) are ignored."""
    body = [(i, l) for i, l in enumerate(lines) if 45 < l["y"] < page_h - 60]
    for i, l in body:
        t = l["text"].strip()
        if Q_START.match(t) and not MARKS_HEADER.search(t):
            if any(p["y"] > l["y"] + 6 for j, p in body if j < i and not Q_START.match(p["text"].strip())):
                return True
    return False

def _text_lines(doc, pno: int) -> list[dict]:
    out = []
    for block in doc[pno].get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = " ".join(span["text"] for span in line["spans"]).strip()
            if text:
                out.append({"page": pno + 1, "y": line["bbox"][1], "y1": line["bbox"][3],
                            "x": line["bbox"][0], "text": text, "src": "text", "conf": 1.0})
    if out and _needs_reading_order(out, doc[pno].rect.height):
        out = _row_sort(out)
    return _lift_centered_labels(out)

_DOTTED_LABEL = re.compile(r"^Q\.\s*\d{1,3}(?!\d)")
_PAGE_MARK = re.compile(r"^\d+\s*/\s*\d+$")
_WORD = re.compile(r"[A-Za-z]{2,}")

def _lift_centered_labels(lines: list[dict]) -> list[dict]:
    """Some papers (2022-S1, 2024-S2, 2025-S1/S2) centre the 'Q.N' label vertically on the
    first paragraph of the stem, so the stem's first line(s) are printed slightly ABOVE the
    label and arrive before it - they were glued onto the previous question. Move such lines
    to just after the label. Deliberately narrow: only a dotted 'Q.<n>' label; only lines in
    the stem column (right of the label) that touch the label vertically (the line just before
    must end within 3pt of the label's top) and are spaced like one paragraph (<= 15pt gaps,
    at most 4 lines, top line within 45pt of the label); page markers, boilerplate, option
    labels, other question labels and short fragments (< 20 chars or < 3 words: fraction parts,
    code lines of the previous options) are never moved."""
    out = list(lines)
    i = 0
    while i < len(out):
        lab = out[i]
        t = lab["text"].strip()
        if not _DOTTED_LABEL.match(t) or i == 0:
            i += 1; continue
        run, j = [], i - 1
        while j >= 0 and len(run) < 4:
            p = out[j]; pt = p["text"].strip()
            nxt = out[j + 1] if run else None
            if (p["page"] != lab["page"] or p.get("x", 0) < lab.get("x", 0) + 20 or Q_START.match(pt)
                    or OPTION.match(pt) or OPT_LABEL_ONLY.match(pt) or _PAGE_MARK.match(pt)
                    or HEADER_FOOTER.match(pt) or MARKS_HEADER.search(pt)):
                break
            if len(pt) < 20 or len(_WORD.findall(pt)) < 3:
                break                                   # fraction/code fragments of the previous options stay
            if not run and p["y1"] < lab["y"] - 3:
                break                                   # does not touch the label: a normal previous line
            if run and nxt["y"] - p["y1"] > 15:
                break                                   # paragraph gap: belongs to the previous question
            run.insert(0, j); j -= 1
        if run and lab["y"] - out[run[0]]["y"] <= 45:
            moved = [out[k] for k in run]
            del out[run[0]:i]
            k = run[0]                                  # label now sits at index k
            out[k + 1:k + 1] = moved
            i = k + 1 + len(moved)
        else:
            i += 1
    return out

def _lines(doc, pdf_path: str | Path | None = None, pages: tuple[int, int] | None = None,
           ocr: str = "auto", ocr_dpi: int | None = None) -> tuple[list[dict], dict]:
    """All content lines for the requested 1-based inclusive page range.
    ocr: 'auto' (scanned pages only) | 'never' | 'always'."""
    first, last = pages if pages else (1, len(doc))
    last = min(last, len(doc))
    lines: list[dict] = []
    ocr_pages = 0
    sha = None
    mode = "digital"
    if ocr == "auto":
        from .ocr import doc_scan_mode
        mode = doc_scan_mode(doc, first, last)
    for pno in range(first - 1, last):
        use_ocr = False
        if ocr == "always":
            use_ocr = True
        elif ocr == "auto":
            from .ocr import page_needs_ocr
            use_ocr = page_needs_ocr(doc[pno], mode)
        if use_ocr:
            from . import ocr as _ocr
            if sha is None:
                sha = _ocr.pdf_sha(pdf_path)
            for l in _ocr.ocr_page(doc, pno, sha, ocr_dpi or _ocr.DEFAULT_DPI):
                l["src"] = "ocr"
                lines.append(l)
            ocr_pages += 1
        else:
            lines.extend(_text_lines(doc, pno))
    return lines, {"ocr_pages": ocr_pages, "pages": last - first + 1, "scan_mode": mode}

_DIG = re.compile(r"\d+")

def _strip_boilerplate(lines: list[dict], doc, n_pages: int) -> list[dict]:
    """Drop running headers/footers: the same (normalised) text recurring at the
    same height on many pages, within the top/bottom page margins. Never drops
    anything that looks like a question start or an option."""
    if n_pages < 3:
        return lines
    count: dict[tuple, set] = {}
    def key(l): return (int(l["y"] // 6), _DIG.sub("#", l["text"].strip().lower())[:70])
    for l in lines:
        count.setdefault(key(l), set()).add(l["page"])
    need = max(3, int(0.30 * n_pages))
    out = []
    for l in lines:
        h = doc[l["page"] - 1].rect.height
        in_margin = l["y"] < 110 or l["y1"] > h - 100
        t = l["text"].strip()
        if (in_margin and len(count[key(l)]) >= need and not Q_START.match(t) and not QNUM_HDR.match(t)
                and not OPTION.match(t) and not OPT_LABEL_ONLY.match(t)):
            continue
        out.append(l)
    return out

def _crop_region(doc, pages: list[int], y_first: float, y_last: float | None,
                 uid: str, assets_dir: Path) -> str | None:
    """Render the question's own region of its first page to PNG (source crop).
    Clips from the question's first line to its last line on that page, so the
    review workspace shows THIS question, not the whole page."""
    if not pages:
        return None
    assets_dir.mkdir(parents=True, exist_ok=True)
    page = doc[pages[0] - 1]
    bottom = (y_last + 12) if y_last is not None else page.rect.height
    clip = fitz.Rect(0, max(y_first - 10, 0), page.rect.width, min(bottom, page.rect.height))
    pix = page.get_pixmap(clip=clip, dpi=110)
    fname = assets_dir / f"{uid}-crop.png"
    pix.save(str(fname))
    return str(fname)

def _crop_embedded_images(doc, pages: list[int], uid: str, assets_dir: Path) -> list[str]:
    files = []
    for pno in pages:
        page = doc[pno - 1]
        for idx, img in enumerate(page.get_images(full=True)):
            try:
                pix = fitz.Pixmap(doc, img[0])
                if pix.n - pix.alpha > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                fname = assets_dir / f"{uid}-p{pno}-img{idx+1}.png"
                pix.save(str(fname))
                files.append(str(fname))
            except Exception:
                continue
    return files

# --------------------------------------------------------------------------
# Section headers (marks / type)
# --------------------------------------------------------------------------
_INLINE_LABEL = re.compile(r"\(([A-D])\)")

def _split_inline_options(text: str) -> list[tuple[str, str]] | None:
    """Split '(A) 5 (B) 7 (C) 9 (D) 11' (several options on one line) into
    [(A,'5'),(B,'7'),...]. Only when the labels appear strictly in order A,B,(C,(D)),
    starting with A, so a stem that merely mentions '(B)' is never split."""
    marks = list(_INLINE_LABEL.finditer(text))
    labs = [m.group(1) for m in marks]
    if len(labs) < 2 or labs != list("ABCD")[:len(labs)] or marks[0].start() > 1:
        return None
    out = []
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        out.append((m.group(1), text[m.end():end].strip()))
    return out

def _type_hint(text: str) -> str | None:
    t = text.upper()
    if "MSQ" in t or "MULTIPLE SELECT" in t: return "MSQ"
    if "(NAT)" in t or "NUMERICAL" in t: return "NAT"
    if "MCQ" in t or "MULTIPLE CHOICE" in t: return "MCQ"
    return None

def _find_headers(lines: list[dict]) -> dict[int, dict]:
    """index -> {marks, lo, hi, type}. Any line saying 'carry ONE/TWO mark(s)' is a
    header (never a question). A line starting with a Q-range whose 'carry ...'
    wraps onto the next line is joined with that next line."""
    hdr: dict[int, dict] = {}
    for i, ln in enumerate(lines):
        t = ln["text"]
        m = MARKS_HEADER.search(t)
        joined = t
        consumed = [i]
        if not m and RANGE_HDR.match(t) and i + 1 < len(lines):
            joined = t + " " + lines[i + 1]["text"]
            m = MARKS_HEADER.search(joined)
            if m:
                consumed.append(i + 1)
        if not m:
            continue
        w = m.group(1).upper()
        marks = 1.0 if w in ("ONE", "1") else 2.0
        r = RANGE_HDR.match(t)
        # several ranges on one line: 'Q.1 to Q.5 carry 1 mark each & Q.6 to Q.10 carry 2 marks each'
        ranges = [(int(a), int(b), 1.0 if mk.upper() in ("ONE", "1") else 2.0)
                  for a, b, mk in RANGE_MARKS.findall(joined)]
        info = {"marks": marks, "lo": int(r.group(1)) if r else None,
                "hi": int(r.group(2)) if r else None, "type": _type_hint(joined), "ranges": ranges}
        for c in consumed:
            hdr[c] = info
    return hdr

# --------------------------------------------------------------------------
# Question starts (sequence-aware)
# --------------------------------------------------------------------------
def _find_starts(lines: list[dict], hdr: dict[int, dict]) -> tuple[list[dict], dict]:
    cands = []
    for i, ln in enumerate(lines):
        if i in hdr:
            continue
        t = ln["text"]
        if QNUM_HDR.match(t):
            cands.append((i, int(QNUM_HDR.match(t).group(1)), "qnum")); continue
        m = Q_START.match(t)
        if m:
            cands.append((i, int(m.group(1)), "q"))
    starts: list[dict] = []
    last, offset, restarts, gaps, rejected = 0, 0, 0, [], 0
    for i, n, kind in cands:
        if starts and n == last and i - starts[-1]["idx"] <= 4 and starts[-1]["kind"] == kind:
            starts[-1]["idx"] = i      # label repeated right after a start (split header): keep the later one
            continue
        if n == last + 1:
            pass
        elif n == 1 and 8 <= last <= 12 and restarts == 0:
            # The GA block is always exactly 10 questions; CS then restarts at Q.1.
            # Renumber CS as 11..65. (A stray 'Q.1' deep inside a stem - last is 60+ - is NOT a restart.)
            restarts += 1; offset = 10
        elif last < n <= last + 3 and starts:
            gaps.append((last + 1, n - 1))        # missing question(s): reported, never invented
        else:
            rejected += 1
            continue
        last = n
        starts.append({"idx": i, "printed": n, "canon": n + offset, "kind": kind})
    ga_count = 0
    for s in starts:
        if s["canon"] != s["printed"]:
            break
        ga_count += 1
    return starts, {"restarts": restarts, "gaps": gaps, "rejected_candidates": rejected,
                    "ga_count": ga_count if restarts else 0}

def _is_label(t: str, letter: str) -> bool:
    m = OPTION.match(t) or OPT_LABEL_ONLY.match(t)
    return bool(m) and m.group(1) == letter

def _find_hidden_boundary(lines: list[dict], hdr: dict[int, dict], a: int, b: int) -> int | None:
    """Between two accepted starts exactly one question label is missing (e.g. OCR lost
    'Q.36' together with its math-heavy first lines). Look for: options A-D of the earlier
    question, then a clear vertical gap (or page break), then a SECOND option block. The first
    line after the gap is where the hidden question starts. None when the pattern is absent."""
    seq = 0                      # next expected option letter index of the earlier question
    d_end = None
    for j in range(a + 1, b):
        if j in hdr:
            continue
        t = lines[j]["text"].strip()
        if seq < 4 and _is_label(t, "ABCD"[seq]):
            seq += 1
            if seq == 4:
                d_end = j
    if d_end is None:
        return None
    prev = d_end
    for j in range(d_end + 1, b):
        if j in hdr:
            continue
        cur, pr = lines[j], lines[prev]
        gap = cur["page"] != pr["page"] or (cur["y"] - pr["y1"]) > 28
        if gap and any(_is_label(lines[k]["text"].strip(), "A") for k in range(j, b) if k not in hdr):
            return j
        prev = j
    return None

def _find_fuzzy_label(lines: list[dict], hdr: dict[int, dict], a: int, b: int, missing: int) -> int | None:
    """OCR sometimes damages a label ('Q.No. 3' -> '0..3'). Accept a line as the missing
    question's label ONLY if it is the exact missing number, begins like a label (Q/O/0 +
    optional 'No.'), and follows a clear vertical gap or page break (a question boundary)."""
    pat = re.compile(rf"^\W{{0,2}}[QO0Ø]\W{{0,3}}(?:[NM][o0O]\W{{0,3}})?{missing}(?!\d)")
    for j in range(a + 1, b):
        if j in hdr:
            continue
        if pat.match(lines[j]["text"].strip()):
            pr = lines[j - 1]
            # boundary evidence: a vertical gap / page break, or the OCR itself was unsure of this line
            if (lines[j]["page"] != pr["page"] or (lines[j]["y"] - pr["y1"]) > 20
                    or lines[j].get("conf", 1.0) < 0.8):
                return j
    return None

def _recover_starts(lines: list[dict], hdr: dict[int, dict], starts: list[dict]) -> tuple[list[dict], list[int]]:
    out: list[dict] = []
    recovered: list[int] = []
    for k, st in enumerate(starts):
        out.append(st)
        if k + 1 < len(starts) and starts[k + 1]["canon"] - st["canon"] == 2:
            j = _find_fuzzy_label(lines, hdr, st["idx"], starts[k + 1]["idx"], st["printed"] + 1)
            if j is None:
                j = _find_hidden_boundary(lines, hdr, st["idx"], starts[k + 1]["idx"])
            if j is not None:
                out.append({"idx": j, "printed": st["printed"] + 1, "canon": st["canon"] + 1, "kind": "recovered"})
                recovered.append(st["canon"] + 1)
    return out, recovered

def _resplit_options(options: list[dict]) -> list[dict]:
    """An option's text sometimes swallows the NEXT label inline ('Q + R + S (D) PR + PRS').
    Split it out when that label is not otherwise present. Conservative: only the very next
    expected letter, only if no real option with that letter exists."""
    present = {o["label"] for o in options}
    out: list[dict] = []
    for o in options:
        out.append({"label": o["label"], "content": o["content"]})
        while len(out) < 4:
            exp = "ABCD"[len(out)]
            if exp in present:
                break
            m = re.search(rf"\({exp}\)", out[-1]["content"])
            if not m:
                break
            pre, post = out[-1]["content"][:m.start()].strip(), out[-1]["content"][m.end():].strip()
            out[-1]["content"] = pre
            out.append({"label": exp, "content": post})
            present.add(exp)
    return out

def _parse_preambles(lines: list[dict], starts: list[dict], hdr: dict[int, dict]) -> tuple[dict, dict]:
    """Cut common-data/linked-answer blocks out of the previous question's body.
    Returns (body_end_by_start_k, {printed_no: {"group": int, "lines": [...]}})."""
    ends: dict[int, int] = {}
    for k, st in enumerate(starts):
        seg_end = starts[k + 1]["idx"] if k + 1 < len(starts) else len(lines)
        cut = seg_end
        for j in range(st["idx"] + 1, seg_end):
            if j in hdr:
                continue
            if PREAMBLE.match(lines[j]["text"].strip()):
                cut = j; break
        ends[k] = cut
    pre: dict[int, dict] = {}
    for k, st in enumerate(starts):
        seg_end = starts[k + 1]["idx"] if k + 1 < len(starts) else len(lines)
        if ends[k] < seg_end:
            block = [l for j, l in enumerate(lines[ends[k]:seg_end], ends[k]) if j not in hdr]
            head = " ".join(l["text"] for l in block[:4])
            nums = PRE_NUMS.search(head)
            if nums:
                a, b = int(nums.group(1)), int(nums.group(2))
                targets = [a, b] if b > a else [a]
            elif k + 1 < len(starts):
                targets = [starts[k + 1]["printed"]]
            else:
                targets = []
            for tno in targets:
                pre[tno] = {"group": targets[0], "lines": block}
    return ends, pre

# --------------------------------------------------------------------------
# Main extraction
# --------------------------------------------------------------------------
def extract_paper(pdf_path: str | Path, paper_id: str, assets_root: str | Path,
                  write_crops: bool = False, pages: tuple[int, int] | None = None,
                  ocr: str = "auto", ocr_dpi: int | None = None) -> tuple[list[dict], dict]:
    doc = fitz.open(str(pdf_path))
    raw, srcmeta = _lines(doc, pdf_path, pages, ocr, ocr_dpi)
    lines = _strip_boilerplate(raw, doc, srcmeta["pages"])
    hdr = _find_headers(lines)
    starts, smeta = _find_starts(lines, hdr)
    starts, recovered = _recover_starts(lines, hdr, starts)
    smeta["recovered_starts"] = recovered
    ends, preambles = _parse_preambles(lines, starts, hdr)
    # GA-first papers either restart the numbering for CS (2014-2021) or number 1..65
    # straight through (2022+); a 'Q.1 - Q.5' header shows the latter. Only used to pick
    # the cross-check pattern and the printed label.
    hdr_sorted = sorted(hdr)
    ga_first = smeta["restarts"] > 0
    if not ga_first:     # a 'Q.1 - Q.5' range, alone or inside a multi-range line, marks the GA block first
        ga_first = any((h.get("lo") == 1 and (h.get("hi") or 99) <= 5) or
                       any(a == 1 and b <= 5 for a, b, _ in h.get("ranges", [])) for h in hdr.values())
    if not ga_first and starts:
        # CS-first papers meet their next marks header at Q.26; GA-first ones at Q.6. Only headers
        # AFTER the first question count (instruction pages list every range before Q.1).
        later = [h for h in hdr_sorted if h > starts[0]["idx"]]
        if later:
            after = [s for s in starts if s["idx"] > later[0]]
            ga_first = bool(after) and after[0]["canon"] <= 7

    ga_n = smeta["ga_count"]
    ga_last_idx = starts[ga_n - 1]["idx"] if (smeta["restarts"] and ga_n and len(starts) >= ga_n) else None

    def header_for(idx: int, qno: int) -> dict | None:
        """Nearest preceding section header. When numbering restarts after the GA block, GA and CS
        reuse the printed numbers 1..10, so a header only applies inside its OWN section."""
        best, best_idx = None, None
        for hi_idx in hdr_sorted:
            if hi_idx <= idx:
                best, best_idx = hdr[hi_idx], hi_idx
            else:
                break
        if best is not None and ga_last_idx is not None:
            if (best_idx < ga_last_idx) != (qno <= ga_n):
                return None
        return best

    assets_dir = Path(assets_root)
    records: list[dict] = []
    for k, st in enumerate(starts):
        i, qno, printed = st["idx"], st["canon"], st["printed"]
        body = lines[i:ends[k]]
        stem_parts: list[str] = []
        options: list[dict] = []
        in_options = False
        current_opt = None
        first = body[0]["text"]
        mq = Q_START.match(first)
        if st["kind"] == "recovered":
            stem_parts.append(first)       # no label line was read: the first line IS stem text
        elif mq and mq.group(2):
            stem_parts.append(mq.group(2))
        marks_correct = None
        if st["kind"] == "qnum":     # 'Question Number : N  Correct : 1  Wrong : -0.33' layout only
            head = " ".join(l["text"] for l in body[:3])
            mc = CORRECT_MARKS.search(head)
            if mc and "wrong" in head.lower():
                marks_correct = float(mc.group(1))
        label_xs: dict[str, float] = {}
        for bi, ln in enumerate(body[1:], 1):
            t = ln["text"]
            if (i + bi) in hdr or HEADER_FOOTER.match(t):
                continue
            if QNUM_HDR.match(t) or (bi <= 3 and CORRECT_MARKS.search(t) and "wrong" in t.lower()):
                continue
            mdup = Q_START.match(t)
            if mdup and int(mdup.group(1)) == printed and not in_options:
                if mdup.group(2):
                    stem_parts.append(mdup.group(2))
                continue                           # repeated label of THIS question, not content
            nxt = "ABCD"[len(options)] if len(options) < 4 else None
            om, lm = OPTION.match(t), OPT_LABEL_ONLY.match(t)
            if lm and not options and not re.search(r"[().]", t):
                lm = None      # a bare 'A' line before any option is a variable name in the stem, not label (A)
            inline = _split_inline_options(t) if om and om.group(1) == nxt else None
            if inline:                                   # '(A) 5 (B) 7 (C) 9 (D) 11' on one line
                in_options = True
                for lab, content in inline:
                    current_opt = {"label": lab, "content": content}
                    options.append(current_opt); label_xs[lab] = ln.get("x", 0.0)
            elif om and om.group(1) == nxt:
                in_options = True
                current_opt = {"label": om.group(1), "content": om.group(2).strip()}
                options.append(current_opt); label_xs[om.group(1)] = ln.get("x", 0.0)
            elif lm and lm.group(1) == nxt:
                in_options = True
                current_opt = {"label": lm.group(1), "content": ""}
                options.append(current_opt); label_xs[lm.group(1)] = ln.get("x", 0.0)
            elif in_options and current_opt is not None:
                tgt = current_opt
                if max(label_xs.values()) - min(label_xs.values()) > 24:   # two-column options: attach by x
                    # (a spread, not 8pt buckets: labels at x=123/124 fell into different buckets and
                    #  2022-S1 option D's text was glued onto C)
                    cands = [o for o in options if label_xs[o["label"]] <= ln.get("x", 0.0) + 4]
                    if cands:
                        mx = max(label_xs[o["label"]] for o in cands)
                        tgt = [o for o in cands if label_xs[o["label"]] == mx][-1]
                tgt["content"] = (tgt["content"] + " " + t).strip()
            elif not in_options:
                stem_parts.append(t)
        options = _resplit_options(options)
        # Content lines drive region bounds: a trailing mark-section header of
        # the NEXT section must not extend this question onto another page.
        content = [ln for j, ln in enumerate(body)
                   if (i + j) not in hdr and not HEADER_FOOTER.match(ln["text"])]
        pre = preambles.get(printed)
        pre_lines = [l for l in (pre["lines"] if pre else []) if not PRE_PURE_HEADER.match(l["text"].strip())]
        region_lines = pre_lines + content if pre_lines else content
        by_page: dict[int, list[dict]] = {}
        for ln in region_lines:
            by_page.setdefault(ln["page"], []).append(ln)
        pages_used = sorted(by_page)
        regions = [{"page": pg, "y_top": min(l["y"] for l in by_page[pg]),
                    "y_bottom": max(l["y1"] for l in by_page[pg])} for pg in pages_used]
        text = " ".join(stem_parts).strip()
        if pre_lines:
            text = (" ".join(l["text"] for l in pre_lines).strip() + " | " + text).strip(" |")

        h = header_for(i, qno)
        marks = h["marks"] if h else None
        hint = h["type"] if h else None
        if h:
            covered = False
            for lo, hi, mk in h.get("ranges", []):
                if lo <= printed <= hi:
                    marks, covered = mk, True
                    break
            if not covered and h.get("lo") is not None and h.get("hi") is not None:
                # the nearest header states a printed range and this question is OUTSIDE it: that
                # header does not apply (e.g. a CS page with no header inheriting 'Q.6-Q.10 carry TWO')
                if h["lo"] <= printed <= h["hi"]:
                    covered = True
                else:
                    marks, hint = None, None
            elif not covered and h.get("ranges"):
                marks, hint = None, None
        if marks_correct is not None:
            marks = marks_correct
        needs_review, reasons = False, []
        if st["kind"] == "recovered":
            needs_review = True
            reasons.append("question label was not read (OCR); boundary reconstructed from the option layout - verify against the source region")
        pm = pattern_marks(qno, ga_first)
        if marks is None:
            if pm is not None:
                marks = pm; needs_review = True
                reasons.append("marks inferred from the fixed GATE exam pattern (no mark-section header matched)")
            else:
                needs_review = True; reasons.append("marks unknown (no mark-section header matched)")
        elif pm is not None and marks != pm:
            needs_review = True
            reasons.append(f"printed marks ({marks:g}) differ from the standard GATE pattern ({pm:g}) for Q{qno}")
        if any(not o["content"].strip() for o in options):
            needs_review = True
            reasons.append("empty option content (likely figure-only option; verify against the PDF region)")
        n_opt = len(options)
        if n_opt == 0:
            qtype = "NAT"
        elif n_opt == 4:
            qtype = "MSQ" if hint == "MSQ" else "MCQ"      # else MSQ upgrade happens at key-import time
        else:
            qtype = None; needs_review = True
            reasons.append(f"{n_opt} options found; expected 0 (NAT) or 4")
        if hint == "NAT" and n_opt != 0:
            needs_review = True; reasons.append("section header says NAT but options were found")
        confs = [l.get("conf", 1.0) for l in content]
        is_ocr = any(l.get("src") == "ocr" for l in content)
        mean_conf = (sum(confs) / len(confs)) if confs else 1.0
        if is_ocr and (mean_conf < 0.90 or min(confs or [1.0]) < 0.55):
            needs_review = True
            reasons.append(f"OCR text (mean confidence {mean_conf:.2f}); verify against the source region")
        uid = f"{paper_id}-Q{qno:02d}"
        crop = None
        if write_crops:
            first_page_lines = [ln for ln in body if ln["page"] == pages_used[0]]
            y_last = max(ln["y1"] for ln in first_page_lines) if len(pages_used) == 1 else None
            crop = _crop_region(doc, pages_used, body[0]["y"], y_last, uid, assets_dir)
            _crop_embedded_images(doc, pages_used, uid, assets_dir)
        if smeta["restarts"]:
            label = f"{'GA' if qno <= smeta['ga_count'] else 'CS'} {printed}"
        else:
            label = f"Q {printed}"
        records.append({
            "id": uid, "paper_id": paper_id, "q_number": qno,
            "text": text, "marks": marks, "q_type": qtype,
            "page_start": pages_used[0], "page_end": pages_used[-1], "image_path": crop,
            "regions": regions, "options": options, "needs_review": needs_review,
            "review_reason": "; ".join(reasons) or None,
            "extraction_confidence": (0.95 if not needs_review else 0.5) if not is_ocr
                                     else round(min(0.9, mean_conf) if not needs_review else min(0.5, mean_conf), 3),
            "extraction_status": "ocr" if is_ocr else "extracted",
            "printed_label": label,
            "group_id": f"{paper_id}-G{pre['group']:02d}" if pre_lines and pre else None})
    doc.close()
    meta = {**srcmeta, **smeta, "questions": len(records),
            "marks_sum": sum(r["marks"] or 0 for r in records), "ga_first": ga_first}
    return records, meta

def extract_questions(pdf_path: str | Path, paper_id: str, assets_root: str | Path,
                      write_crops: bool = False, pages: tuple[int, int] | None = None,
                      ocr: str = "auto", ocr_dpi: int | None = None) -> list[dict]:
    """Backward-compatible entry point: records only (see extract_paper for meta)."""
    return extract_paper(pdf_path, paper_id, assets_root, write_crops, pages, ocr, ocr_dpi)[0]

def persist_records(s: Session, records: list[dict], refresh: bool = False) -> dict:
    """Idempotent upsert keyed by (paper_id, q_number). Re-extraction updates
    extraction-owned fields only; it NEVER touches classifications marked
    verified or questions with human review events on marks/q_type.

    Drift protection (compare-before-upsert): stored text is overwritten only
    when it is empty or byte-identical to the new record. Whitespace/glyph
    differences keep the stored text (regions/pages still refresh). A real
    content difference keeps the stored text, flags the question for review
    and is counted in the result - re-extraction can never silently rewrite
    what a reviewer may already have read.

    refresh=True is the explicit, opt-in repair mode: for questions that no
    human has touched (no review event AND no verified classification) the
    stored text AND options are replaced by the fresh extraction, because
    nobody has read them yet. Used to fix extractor defects (e.g. page headers
    fused into option text). Counted separately in the result."""
    created = updated = preserved = drift_flagged = refreshed = 0
    for r in records:
        q = s.get(Question, r["id"])
        is_new = q is None
        if q is None:
            q = Question(id=r["id"], paper_id=r["paper_id"], q_number=r["q_number"])
            s.add(q)
            created += 1
        else:
            updated += 1
            has_human = s.scalar(select(ReviewEvent.id).where(
                ReviewEvent.question_id == q.id).limit(1))
            if has_human and (q.marks is not None and q.q_type is not None):
                preserved += 1
                # keep human-reviewed marks/type; refresh regions only
                for f in ("page_start", "page_end", "image_path"):
                    setattr(q, f, r[f])
                q.regions_json = json.dumps(r["regions"])
                continue
        status = drift_status(q.text, r["text"]) if q.text else "exact"
        for f in ("marks", "q_type", "page_start", "page_end", "image_path",
                  "needs_review", "review_reason", "extraction_confidence"):
            setattr(q, f, r[f])
        for f in ("extraction_status", "printed_label", "group_id"):
            if f in r:
                setattr(q, f, r[f])
        if refresh and not is_new and not _human_touched(s, q.id):
            if status != "exact" or _options_differ(s, q.id, r["options"]):
                refreshed += 1
            q.text = r["text"]
            for o in s.scalars(select(Option).where(Option.question_id == q.id)).all():
                s.delete(o)
            s.flush()
            q.regions_json = json.dumps(r["regions"])
            for o in r["options"]:
                s.add(Option(question_id=q.id, label=o["label"], content=o["content"]))
            continue
        if status == "exact":
            q.text = r["text"]
        elif status == "normalized":
            # glyph/spacing-only difference: stored text stands, no churn
            pass
        else:
            drift_flagged += 1
            q.needs_review = True
            note = " re-extraction text drift - stored text kept, review against PDF"
            q.review_reason = ((q.review_reason or "") + note) if note not in (q.review_reason or "") else q.review_reason
        q.regions_json = json.dumps(r["regions"])
        s.flush()
        existing = {(o.label) for o in s.scalars(select(Option).where(Option.question_id == q.id))}
        for o in r["options"]:
            if o["label"] not in existing:
                s.add(Option(question_id=q.id, label=o["label"], content=o["content"]))
    s.flush()
    return {"created": created, "updated": updated, "human_preserved": preserved,
            "drift_flagged": drift_flagged, "refreshed": refreshed}

def _human_touched(s: Session, qid: str) -> bool:
    """True if any human decision exists for the question (review event or verified classification)."""
    if s.scalar(select(ReviewEvent.id).where(ReviewEvent.question_id == qid).limit(1)) is not None:
        return True
    return s.scalar(select(Classification.id).where(
        Classification.question_id == qid, Classification.status == "verified").limit(1)) is not None

def _options_differ(s: Session, qid: str, new_opts: list[dict]) -> bool:
    stored = {o.label: o.content for o in s.scalars(select(Option).where(Option.question_id == qid))}
    return stored != {o["label"]: o["content"] for o in new_opts}

def reconcile(s: Session, paper_id: str) -> dict:
    p = s.get(Paper, paper_id)
    qs = s.scalars(select(Question).where(Question.paper_id == paper_id)).all()
    derived_q = len(qs)
    derived_m = sum(q.marks or 0 for q in qs)
    ok = True
    if p.expected_questions is not None and p.expected_questions != derived_q:
        ok = False
    if p.expected_marks is not None and abs(p.expected_marks - derived_m) > 1e-9:
        ok = False
    null_fields = sum(1 for q in qs if q.marks is None or q.q_type is None)
    p.derived_questions, p.derived_marks, p.reconciled = derived_q, derived_m, ok
    s.flush()
    return {"paper_id": paper_id, "derived_questions": derived_q, "derived_marks": derived_m,
            "reconciled": ok, "null_marks_or_type": null_fields}
