"""Official GATE answer-key PDF -> canonical key rows.

Row-geometry parser: words are grouped into table rows by their y position and
read left-to-right, so a NAT key such as '2 to 2' followed by marks '2' can no
longer be confused with the marks column (the failure mode of a flat token
stream). Covers the official tabular layout used 2022-2026 (columns Q.No,
Session, Question Type, Section/Subject, Key/Range, Marks). Embedded key pages
of the older papers have their own layouts and live in separate functions.

Anything unreadable raises KeyParseError - keys are never guessed or filled in.
"""
from __future__ import annotations
import csv, re
from dataclasses import dataclass
from pathlib import Path
import pymupdf

class KeyParseError(RuntimeError):
    pass

@dataclass
class KeyRow:
    qno: int
    qtype: str          # MCQ | MSQ | NAT
    section: str        # GA | CS ...
    key: str            # 'B' | 'A;C' | '4096 to 4096' | 'MTA'
    marks: float
    session: str | None = None
    note: str = ""      # set when a printed/OCR'd key had to be interpreted (shown to the reviewer)

_TYPES = ("MCQ", "MSQ", "NAT")
_NUM = r"-?\d+(?:\.\d+)?"
_NAT_OK = re.compile(rf"^{_NUM} to {_NUM}(?: OR {_NUM} to {_NUM})*$", re.I)   # 'a to b' or 'a to b OR c to d'
_LET_OK = re.compile(r"^(?:MTA|[A-D](?:;[A-D])*)$")
_ORPHAN_TOK = re.compile(rf"^(?:{_NUM}|to|OR)$", re.I)

def _norm_letters(key: str) -> tuple[str | None, bool]:
    """Normalise an MCQ/MSQ key to 'A' / 'B;D' / 'MTA'. Separators ', ; / & OR' and spaces are all
    accepted. Returns (normalized|None, interpreted) where interpreted=True means an OCR artefact
    such as 'CORD' (C;D) had to be read as a separator - the caller records a note for review."""
    k = key.upper().strip()
    if k == "MTA":
        return k, False
    interpreted = bool(re.search(r"(?<=[A-D])OR(?=[A-D])", k))
    k2 = re.sub(r"(?<=[A-D])OR(?=[A-D])", ";", k)
    k2 = re.sub(r"\bOR\b", ";", k2)
    k2 = re.sub(r"[\s,;/&]+", ";", k2).strip(";")
    return (k2, interpreted) if re.fullmatch(r"[A-D](?:;[A-D])*", k2) else (None, False)

def _repair_by_table_order(rows: list[KeyRow], max_run: int = 3) -> list[tuple[int, int]]:
    """An official key table is strictly ordered. If OCR misreads a question number (38 -> 83),
    the rows around it still prove what it must be: a run of <= max_run out-of-sequence rows that is
    followed by a row continuing the count exactly. Only then is the run renumbered, and every such
    row gets a note so a human can see it. Anything ambiguous is left alone and fails loudly later."""
    repairs: list[tuple[int, int]] = []
    for want_ga in (True, False):
        idx = [i for i, r in enumerate(rows) if r.section.upper().startswith("GA") == want_ga]
        pos = 1
        while pos < len(idx):
            prev, cur = rows[idx[pos - 1]], rows[idx[pos]]
            if cur.qno == prev.qno + 1:
                pos += 1
                continue
            for run in range(1, max_run + 1):
                if pos + run < len(idx) and rows[idx[pos + run]].qno == prev.qno + 1 + run:
                    for k in range(run):
                        r = rows[idx[pos + k]]
                        new = prev.qno + 1 + k
                        repairs.append((r.qno, new))
                        r.note = (r.note + "; " if r.note else "") + \
                            f"OCR read the question number as {r.qno}; assigned {new} from table order"
                        r.qno = new
                    break
            pos += 1
    return repairs

def _is_record(t: list[str]) -> bool:
    return len(t) >= 5 and t[0].isdigit() and t[1].isdigit() and t[2].upper() in _TYPES

def _is_orphan(t: list[str]) -> bool:
    """A continuation line of a wrapped key cell: only numbers / 'to' / 'OR'."""
    return bool(t) and not _is_record(t) and all(_ORPHAN_TOK.match(x) for x in t)

def _rows_from_words(page, tol: float = 2.8) -> list[list[tuple[float, str]]]:
    words = [(w[0], (w[1] + w[3]) / 2, w[4]) for w in page.get_text("words")]
    words.sort(key=lambda w: (w[1], w[0]))
    rows: list[list[tuple[float, float, str]]] = []
    for x, cy, t in words:
        if rows and abs(rows[-1][0][1] - cy) <= tol:
            rows[-1].append((x, cy, t))
        else:
            rows.append([(x, cy, t)])
    return [[(x, t) for x, cy, t in sorted(r)] for r in rows]

def parse_tabular(pdf_path: str | Path, pages: tuple[int, int] | None = None,
                  ocr_lines: list[dict] | None = None) -> list[KeyRow]:
    """Parse rows 'qno session type section key... marks'. `ocr_lines` (OCR line
    dicts) can replace the text layer for image-only key PDFs."""
    out: list[KeyRow] = []
    if ocr_lines is None:
        doc = pymupdf.open(str(pdf_path))
        first, last = pages if pages else (1, len(doc))
        grids = [[t for _, t in r] for p in range(first - 1, min(last, len(doc))) for r in _rows_from_words(doc[p])]
        doc.close()
    else:
        grids = _grids_from_ocr(ocr_lines)
    used: set[int] = set()
    for i, toks in enumerate(grids):
        if not _is_record(toks):
            continue
        # 2021 adds a trailing 'negative marks' column ('1/3', '2/3', '0'): marks is then second-to-last
        neg = len(toks) >= 6 and re.fullmatch(r"\d+/\d+|0(\.0+)?", toks[-1]) and re.fullmatch(r"[12](\.0)?", toks[-2])
        marks_tok = toks[-2] if neg else toks[-1]
        if not re.fullmatch(r"[12](\.0)?", marks_tok):
            continue
        body = toks[4:-2 if neg else -1]
        qtype = toks[2].upper()
        key = " ".join(body).strip()
        note = ""
        if qtype == "NAT":
            valid = lambda k: bool(_NAT_OK.match(k))
        else:
            def valid(k):
                return _norm_letters(k)[0] is not None
        if qtype != "NAT" and valid(key):
            key, interpreted = _norm_letters(key)
            if interpreted:
                note = f"OCR key text {' '.join(body)!r} interpreted as {key!r} - verify against the key page"
        if not valid(key):
            # A key cell can wrap over up to three table lines, with the question number on the
            # middle one ('819 to 820' / 'OR 205 to' / '205'). Absorb the orphan line above and/or
            # below ONLY when the combined key becomes valid; otherwise fail loudly.
            before = grids[i - 1] if i > 0 and (i - 1) not in used and _is_orphan(grids[i - 1]) else []
            after = grids[i + 1] if i + 1 < len(grids) and (i + 1) not in used and _is_orphan(grids[i + 1]) else []
            for cand, take in ((before + body + after, (before, after)), (body + after, ([], after)),
                               (before + body, (before, []))):
                if cand and valid(" ".join(cand)):
                    key = " ".join(cand)
                    if qtype != "NAT":
                        key = _norm_letters(key)[0]
                    if take[0]: used.add(i - 1)
                    if take[1]: used.add(i + 1)
                    break
            else:
                raise KeyParseError(f"unreadable key for Q{toks[0]}: {' '.join(body)!r}")
        out.append(KeyRow(int(toks[0]), qtype, toks[3], key, float(marks_tok), toks[1], note))
    if not out:
        raise KeyParseError(f"no key rows recognised in {pdf_path}")
    _repair_by_table_order(out)
    nums = [r.qno for r in out]
    if nums != list(range(1, len(out) + 1)):
        # papers whose CS numbering restarts after GA (e.g. 2020/2021): GA keeps 1..10, CS n -> n+10
        remap = [KeyRow(r.qno if r.section.upper().startswith("GA") else r.qno + 10, r.qtype, r.section, r.key,
                        r.marks, r.session, r.note)       # keep the repair note: a reviewer must see it
                 for r in out]
        N = len(remap)
        got = sorted(r.qno for r in remap)
        if got != list(range(1, N + 1)):
            missing = sorted(set(range(1, N + 1)) - set(got))
            stray = [r for r in remap if not (1 <= r.qno <= N) or got.count(r.qno) > 1]
            if len(missing) == 1 and len(stray) == 1 and not (1 <= stray[0].qno <= N):
                stray[0].qno = missing[0]       # single OCR misread (e.g. 55 -> 88): only one consistent assignment
            else:
                dup = sorted({n for n in got if got.count(n) > 1})
                raise KeyParseError(f"key rows are not numbered 1..N without gaps ({N} rows): missing {missing}, "
                                    f"duplicated {dup}, out-of-range {sorted(r.qno for r in remap if not 1 <= r.qno <= N)}")
        remap.sort(key=lambda r: r.qno)
        out = remap
    return out

def _grids_from_ocr(lines: list[dict]) -> list[list[str]]:
    """OCR lines -> rows of tokens (same y band, left to right)."""
    rows: list[list[dict]] = []
    for l in sorted(lines, key=lambda l: (l["page"], (l["y"] + l["y1"]) / 2, l["x"])):
        cy = (l["y"] + l["y1"]) / 2
        if rows and rows[-1][0]["page"] == l["page"] and abs((rows[-1][0]["y"] + rows[-1][0]["y1"]) / 2 - cy) <= 4:
            rows[-1].append(l)
        else:
            rows.append([l])
    return [" ".join(x["text"] for x in sorted(r, key=lambda z: z["x"])).split() for r in rows]

def _canonical(rows: list[tuple[str, int, str, str, float | None]], source: str) -> list[KeyRow]:
    """(section, printed_no, qtype, key, marks) -> KeyRow numbered 1..N in the SAME
    scheme as extraction: GA keeps 1..10, CS printed n becomes n+10 (papers whose CS
    numbering restarts). Fails loudly unless the result is exactly 1..N."""
    out = []
    printed = [n for _, n, *_ in rows]
    continuous = sorted(printed) == list(range(1, len(rows) + 1))   # 1..N, each once: no GA->CS restart (2012/2017 style)
    for sec, n, qt, key, marks in rows:
        canon = n if (continuous or sec.upper().startswith("GA")) else n + 10
        out.append(KeyRow(canon, qt, sec, key, marks if marks is not None else 0.0, None))
    N = len(out)
    nums = [r.qno for r in out]
    if sorted(nums) != list(range(1, N + 1)):
        # Exactly one number missing AND exactly one row outside 1..N (an OCR misread such as 55 -> 88):
        # only one assignment is consistent, so reassign it. Anything less clear fails loudly.
        missing = sorted(set(range(1, N + 1)) - set(nums))
        stray = [r for r in out if not (1 <= r.qno <= N)]
        if len(missing) == 1 and len(stray) == 1:
            stray[0].qno = missing[0]
        else:
            raise KeyParseError(f"{source}: key rows do not form 1..N (got {sorted(nums)[:8]}...{sorted(nums)[-4:]}, {N} rows)")
    out.sort(key=lambda r: r.qno)
    return out

def _qtype_from_key(key: str) -> str:
    return "NAT" if re.search(r"\d", key) and not re.fullmatch(r"[A-D](;[A-D])*", key.strip()) else "MCQ"

def parse_embedded_table(pdf_path: str | Path, pages: tuple[int, int], ocr: bool = False) -> list[KeyRow]:
    """2016/2018/2019 embedded key: rows 'qno type section key... marks'; CS numbering
    restarts. ocr=True reads image-only key pages through the cached OCR; there a row whose
    number was lost is accepted ONLY when its neighbours prove it (n-1 before, n+1 after)."""
    doc = pymupdf.open(str(pdf_path))
    if ocr:
        from ..extraction import ocr as _ocr
        sha = _ocr.pdf_sha(pdf_path)
        lines = [l for p in range(pages[0] - 1, pages[1]) for l in _ocr.ocr_page(doc, p, sha)]
        grids = _grids_from_ocr(lines)
    else:
        grids = [[t for _, t in r] for p in range(pages[0] - 1, pages[1]) for r in _rows_from_words(doc[p])]
    doc.close()
    parsed: list[list] = []          # [printed_no|None, type, section, key, marks]
    for t in grids:
        if len(t) >= 4 and re.fullmatch(r"[12](\.0)?", t[-1]):
            if t[0].isdigit() and t[1].upper() in _TYPES and len(t) >= 5:
                parsed.append([int(t[0]), t[1].upper(), t[2], " ".join(x for x in t[3:-1] if x != ":"), float(t[-1])])
            elif ocr and t[0].upper() in _TYPES:
                parsed.append([None, t[0].upper(), t[1], " ".join(x for x in t[2:-1] if x != ":"), float(t[-1])])
    for i, row in enumerate(parsed):                     # prove-or-reject inference for OCR-lost numbers
        if row[0] is None:
            prev = parsed[i - 1][0] if i > 0 else None
            nxt = parsed[i + 1][0] if i + 1 < len(parsed) else None
            if prev is not None and nxt is not None and nxt == prev + 2:
                row[0] = prev + 1
            else:
                raise KeyParseError(f"{Path(pdf_path).name}: a key row lost its question number and cannot be inferred "
                                    f"(neighbours {prev}, {nxt}) - read the page by eye")
    rows = [(r[2], r[0], r[1], r[3], r[4]) for r in parsed]
    return _canonical(rows, f"{Path(pdf_path).name} pp.{pages}")

def parse_embedded_range(pdf_path: str | Path, pages: tuple[int, int]) -> list[KeyRow]:
    """2014 embedded key: two records per table row ('GA 1 B 1  CS 24 C 1'); no type
    column, so type follows the key (letter -> MCQ, numbers -> NAT)."""
    doc = pymupdf.open(str(pdf_path))
    rows = []
    for p in range(pages[0] - 1, pages[1]):
        for r in _rows_from_words(doc[p]):
            t = [x for _, x in r]
            starts = [i for i, x in enumerate(t) if x in ("GA", "CS") and i + 1 < len(t) and t[i + 1].isdigit()]
            for a, b in zip(starts, starts[1:] + [len(t)]):
                rec = t[a:b]
                if len(rec) >= 4 and re.fullmatch(r"[12](\.0)?", rec[-1]):
                    key = " ".join(rec[2:-1])
                    rows.append((rec[0], int(rec[1]), _qtype_from_key(key), key, float(rec[-1])))
    doc.close()
    return _canonical(rows, f"{Path(pdf_path).name} pp.{pages}")

def parse_embedded_codes(pdf_path: str | Path, pages: tuple[int, int], code: str = "A") -> list[KeyRow]:
    """2012 embedded key: 'CS <qno> <A-key> <B-key> <C-key> <D-key>' where a key is a
    letter or 'Marks to All'. Returns the requested booklet code's column."""
    col = "ABCD".index(code.upper())
    doc = pymupdf.open(str(pdf_path))
    rows = []
    for p in range(pages[0] - 1, pages[1]):
        for r in _rows_from_words(doc[p]):
            t = [x for _, x in r]
            if len(t) >= 6 and t[0] in ("CS", "GA") and t[1].isdigit():
                entries, i = [], 2
                while i < len(t):
                    if t[i:i + 3] == ["Marks", "to", "All"]:
                        entries.append("MTA"); i += 3
                    else:
                        entries.append(t[i]); i += 1
                if len(entries) == 4 and all(e == "MTA" or re.fullmatch(r"[A-D]", e) for e in entries):
                    rows.append((int(t[1]), "MCQ", entries[col]))
    doc.close()
    rows.sort()
    out = [KeyRow(n, qt, "CS", key, 0.0, None) for n, qt, key in rows]   # 2012 numbers 1..65 continuously
    if [r.qno for r in out] != list(range(1, len(out) + 1)):
        raise KeyParseError(f"{Path(pdf_path).name}: code table rows do not form 1..N ({len(out)} rows)")
    return out

def to_records(rows: list[KeyRow]) -> list[dict]:
    """Canonical import records: kind in mcq_single | msq_set | nat_range | dropped."""
    recs = []
    for r in rows:
        key = r.key.strip()
        rec = {"qno": r.qno, "kind": "", "answer": "", "min": "", "max": "", "notes": "",
               "qtype": r.qtype, "marks": f"{r.marks:g}" if r.marks else ""}
        if key.upper() in ("MTA", "BONUS"):
            rec.update(kind="dropped", notes="MTA: marks to all (per official key)")
        elif r.qtype == "NAT":
            ranges = re.findall(rf"({_NUM})\s*(?:to|:)\s*({_NUM})", key)
            if not ranges:
                nums = re.findall(_NUM, key)
                if not nums:
                    raise KeyParseError(f"unreadable NAT key for Q{r.qno}: {key!r}")
                ranges = [((nums + nums)[0], (nums + nums)[1])]
            # the first range fills min/max; EVERY accepted range (official 'a to b OR c to d') is kept in answer_list
            rec.update(kind="nat_range", min=ranges[0][0], max=ranges[0][1],
                       answer=";".join(f"{a} to {b}" for a, b in ranges) if len(ranges) > 1 else "",
                       notes=("official key accepts any of these ranges" if len(ranges) > 1 else ""))
        elif r.qtype == "MSQ":
            rec.update(kind="msq_set", answer=";".join(sorted(set(re.findall(r"[A-D]", key)))))
        else:
            letters = re.findall(r"[A-D]", key)
            if len(letters) > 1:                       # official 'A;B' on an MCQ: either option is accepted
                rec.update(kind="mcq_single", answer=";".join(letters), notes="official key accepts any of these options")
            else:
                rec.update(kind="mcq_single", answer=letters[0] if letters else key)
        if r.note:
            rec["notes"] = (rec["notes"] + "; " if rec["notes"] else "") + r.note
        recs.append(rec)
    return recs

def write_csv(path: str | Path, rows: list[KeyRow]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["qno", "kind", "answer", "min", "max", "notes", "qtype", "marks"])
        w.writeheader()
        for rec in to_records(rows):
            w.writerow(rec)
