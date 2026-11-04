"""Paper registry: manifests/papers.yaml -> probe / load.

`probe` extracts every registered paper WITHOUT touching any database and
reports the reconciliation gate (65 questions / 100 marks, GA/CS marks pattern,
gaps, OCR usage). `load` registers documents + papers, extracts, reconciles and
(optionally) imports keys. Nothing is imported silently: a paper that fails the
gate is still stored (so it can be reviewed) but is reported as NOT reconciled,
and analytics only ever count classified questions."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from ..settings import APP_ROOT
from .ingest import paper_id_for

@dataclass
class PaperEntry:
    year: int
    session: str
    file: Path
    pages: tuple[int, int] | None
    expected_questions: int | None
    expected_marks: float | None
    branch: str = "CS"
    paper_code: str | None = None
    layout: str = ""
    ocr: str = "auto"
    status: str = "active"
    note: str = ""
    key: dict | None = None

    @property
    def paper_id(self) -> str:
        return paper_id_for(self.year, self.session, self.branch)

def load_manifest(path: str | Path = "manifests/papers.yaml") -> list[PaperEntry]:
    p = Path(path)
    if not p.is_absolute():
        p = APP_ROOT / p
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    d = data.get("defaults", {})
    out: list[PaperEntry] = []
    seen: set[str] = set()
    for e in data["papers"]:
        pg = e.get("pages")
        ent = PaperEntry(
            year=int(e["year"]), session=str(e["session"]),
            file=APP_ROOT / e["file"], pages=(int(pg[0]), int(pg[1])) if pg else None,
            expected_questions=e.get("expected_questions", d.get("expected_questions")),
            expected_marks=e.get("expected_marks", d.get("expected_marks")),
            branch=e.get("branch", d.get("branch", "CS")), paper_code=e.get("paper_code"),
            layout=e.get("layout", ""), ocr=e.get("ocr", d.get("ocr", "auto")),
            status=e.get("status", "active"), note=e.get("note", ""), key=e.get("key"))
        if ent.paper_id in seen:
            raise ValueError(f"duplicate paper identity in manifest: {ent.paper_id}")
        seen.add(ent.paper_id)
        out.append(ent)
    return out

def select(entries: list[PaperEntry], only: str | None = None, include_pending: bool = False) -> list[PaperEntry]:
    """`only`: comma list of years ('2014,2016') or paper ids."""
    keys = {k.strip() for k in only.split(",")} if only else None
    out = []
    for e in entries:
        if e.status == "skip" or (e.status == "pending" and not include_pending):
            continue
        if keys and str(e.year) not in keys and e.paper_id not in keys:
            continue
        out.append(e)
    return out

def probe_entry(e: PaperEntry, assets_root: str | Path = "data/assets") -> dict:
    """Extract one entry in memory and summarise how well it reconciles."""
    from ..extraction.extract import extract_paper
    recs, meta = extract_paper(e.file, e.paper_id, assets_root, pages=e.pages, ocr=e.ocr)
    n, marks = len(recs), sum(r["marks"] or 0 for r in recs)
    types: dict[str, int] = {}
    for r in recs:
        types[r["q_type"] or "NULL"] = types.get(r["q_type"] or "NULL", 0) + 1
    flagged = [r for r in recs if r["needs_review"]]
    nums = [r["q_number"] for r in recs]
    expected_nums = list(range(1, (e.expected_questions or n) + 1))
    ok = ((e.expected_questions is None or n == e.expected_questions) and
          (e.expected_marks is None or abs(marks - e.expected_marks) < 1e-9) and nums == expected_nums[:len(nums)])
    return {"paper_id": e.paper_id, "questions": n, "marks": marks, "types": types,
            "needs_review": len(flagged), "ocr_pages": meta["ocr_pages"], "scan_mode": meta["scan_mode"],
            "gaps": meta["gaps"], "restarts": meta["restarts"], "rejected_candidates": meta["rejected_candidates"],
            "missing_numbers": sorted(set(expected_nums) - set(nums)),
            "reconciles": ok, "flag_reasons": _reason_counts(flagged)}

def drift_entry(s, e: PaperEntry, assets_root: str | Path = "data/assets") -> dict:
    """Re-extract one registered paper and compare it with what the database stores:
    exact / normalized (glyph+spacing only) / changed (real content drift) / new / missing."""
    from ..extraction.extract import extract_paper
    from ..validation import drift as dr
    recs, _ = extract_paper(e.file, e.paper_id, assets_root, pages=e.pages, ocr=e.ocr)
    rep = dr.compare_records_vs_db(s, recs)
    return {"paper_id": e.paper_id, "layout": e.layout, **rep["summary"],
            "changed_ids": [c["id"] for c in rep["changed"]][:10]}

def parse_entry_key(e: PaperEntry):
    """Parse the entry's official key into KeyRow list (None if no key is registered)."""
    from . import keypdf as kp
    k = e.key
    if not k:
        return None
    pdf = APP_ROOT / k["pdf"]
    pages = tuple(k["pages"]) if k.get("pages") else None
    kind = k["kind"]
    if kind == "tabular":
        return kp.parse_tabular(pdf, pages)
    if kind == "embedded-table":
        return kp.parse_embedded_table(pdf, pages)
    if kind == "ocr-embedded-table":
        return kp.parse_embedded_table(pdf, pages, ocr=True)
    if kind == "embedded-range":
        return kp.parse_embedded_range(pdf, pages)
    if kind == "embedded-codes":
        return kp.parse_embedded_codes(pdf, pages, k.get("code", "A"))
    if kind == "ocr-tabular":
        from ..extraction import ocr as _ocr
        import pymupdf
        doc = pymupdf.open(str(pdf)); sha = _ocr.pdf_sha(pdf)
        first, last = pages if pages else (1, len(doc))
        lines = [l for p in range(first - 1, min(last, len(doc))) for l in _ocr.ocr_page(doc, p, sha)]
        doc.close()
        return kp.parse_tabular(pdf, pages, ocr_lines=lines)
    raise ValueError(f"unknown key kind {kind!r} for {e.paper_id}")

def csv_agreement(rows, csv_path: Path) -> dict:
    """Compare a hand-made key CSV with the PDF-parsed rows (type + answer/range)."""
    import csv as _csv
    from . import keypdf as kp
    from .keys import normalize_kind
    recs = {r["qno"]: r for r in kp.to_records(rows)}
    diffs = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            q = int(row["qno"]); a = recs.get(q)
            if a is None:
                diffs.append((q, "missing in PDF parse")); continue
            same_kind = normalize_kind(row["kind"]) == a["kind"]
            same_ans = (row.get("answer") or "") == (a["answer"] or "")
            same_rng = all((float(row[c]) if row.get(c) else None) == (float(a[c]) if a[c] != "" else None) for c in ("min", "max"))
            if not (same_kind and same_ans and same_rng):
                diffs.append((q, f"csv={row['kind']}/{row.get('answer')}/{row.get('min')}-{row.get('max')} pdf={a['kind']}/{a['answer']}/{a['min']}-{a['max']}"))
    return {"csv": str(csv_path), "rows": len(recs), "differences": diffs}

def load_entry(s, e: PaperEntry, assets_root: str | Path = "data/assets",
               refresh: bool = False, with_keys: bool = True) -> dict:
    """Register document + paper, extract, reconcile, import key. Idempotent."""
    from ..extraction.extract import extract_paper, persist_records, reconcile
    from ..db.models import Paper
    from . import ingest as ig, keypdf as kp
    from .keys import import_key_records
    out: dict = {"paper_id": e.paper_id}
    doc, _ = ig.register_document(s, e.file, role="paper")
    # heal a stale recorded path after the owner renamed/moved the file (same sha256)
    if not Path(doc.file_path).exists() and Path(e.file).exists():
        doc.file_path = str(Path(e.file).relative_to(APP_ROOT)) if str(e.file).startswith(str(APP_ROOT)) else str(e.file)
        doc.filename = Path(e.file).name
    pid, state = ig.register_paper(s, e.year, e.session, doc.id, e.expected_questions,
                                   e.expected_marks, e.branch, e.paper_code)
    out["register"] = state
    if state == "conflict":
        out["error"] = "a different file already claims this paper identity - human reconciliation required"
        return out
    p = s.get(Paper, pid)
    if p.expected_questions is None: p.expected_questions = e.expected_questions
    if p.expected_marks is None: p.expected_marks = e.expected_marks
    if not p.paper_code and e.paper_code: p.paper_code = e.paper_code
    recs, meta = extract_paper(e.file, pid, assets_root, pages=e.pages, ocr=e.ocr)
    out["extract"] = {**persist_records(s, recs, refresh=refresh), "ocr_pages": meta["ocr_pages"]}
    out["reconcile"] = reconcile(s, pid)
    if with_keys and e.key:
        try:
            rows = parse_entry_key(e)
            kdoc, _ = ig.register_document(s, APP_ROOT / e.key["pdf"], role="key") if e.key.get("pdf") else (None, False)
            res = import_key_records(s, pid, kp.to_records(rows), "final", kdoc.id if kdoc else None)
            if e.key.get("csv") and (APP_ROOT / e.key["csv"]).exists():
                res["csv_vs_pdf"] = csv_agreement(rows, APP_ROOT / e.key["csv"])
            out["key"] = res
        except Exception as ex:   # a key that cannot be read is reported, never guessed
            out["key"] = {"error": f"{type(ex).__name__}: {ex}"}
    elif with_keys:
        out["key"] = {"missing": "no official key registered for this paper"}
    return out

def _reason_counts(flagged: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in flagged:
        for part in (r["review_reason"] or "").split("; "):
            key = part.split("(")[0].strip()[:70]
            if key:
                out[key] = out.get(key, 0) + 1
    return out
