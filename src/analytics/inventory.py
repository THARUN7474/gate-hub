"""Data inventory: which GATE CS papers exist in data/raw, how they are bundled in PDFs, where each key comes from,
and how much of it is in the database. Computed from manifests/papers.yaml + the raw folder + the database - nothing
is typed in by hand, so it stays true when a paper is added."""
from __future__ import annotations
from collections import OrderedDict
from pathlib import Path
from sqlalchemy import func, select
from ..ingestion import registry as rg
from ..settings import APP_ROOT

GROUPS = OrderedDict([
    ("2007-2010", "Deferred (owner decision): photographed booklets, not imported yet"),
    ("2011-2020", "Archive years: one combined PDF per year (or two in 2017); keys inside the PDF, or none"),
    ("2021-2026", "Recent years: question PDFs plus separate official key PDFs"),
])

def group_of(year: int) -> str:
    return "2007-2010" if year <= 2010 else "2011-2020" if year <= 2020 else "2021-2026"

def _rel(p) -> str:
    p = Path(p)
    try:
        return p.resolve().relative_to(APP_ROOT).as_posix()
    except ValueError:
        return p.as_posix()

def _key_source(e: rg.PaperEntry) -> str:
    k = e.key
    if not k:
        return "none (no key file supplied)" if e.status != "skip" else "not checked (deferred)"
    pages = f" pp.{k['pages'][0]}-{k['pages'][1]}" if k.get("pages") else ""
    kind = k.get("kind", "")
    scan = " (scanned image, OCR)" if "ocr" in kind else ""
    if Path(k["pdf"]).name == Path(e.file).name:
        return f"inside the question PDF{pages}{scan}"
    return f"separate key PDF {Path(k['pdf']).name}{pages}{scan}"

def inventory(s=None, manifest: str = "manifests/papers.yaml") -> dict:
    """{'papers': [...one row per paper/session...], 'years': [...one row per year...], 'groups': [...], 'totals': {...}}.
    With a session, adds what this database holds (questions, keys, OCR'd questions, classified, verified)."""
    from ..db.models import AnswerKey, Classification, Question
    entries = rg.select(rg.load_manifest(manifest), include_pending=True) + \
        [e for e in rg.load_manifest(manifest) if e.status == "skip"]
    db = {}
    if s is not None:
        q = (select(Question.paper_id, func.count(Question.id),
                    func.sum(func.cast(Question.extraction_status == "ocr", type_=func.count().type)))
             .group_by(Question.paper_id))
        for pid, n, ocr in s.execute(q):
            db[pid] = {"questions": n, "ocr": int(ocr or 0)}
        for pid, n in s.execute(select(Question.paper_id, func.count(AnswerKey.id))
                                .join(AnswerKey, AnswerKey.question_id == Question.id).group_by(Question.paper_id)):
            db.setdefault(pid, {})["keys"] = n
        for pid, st, n in s.execute(select(Question.paper_id, Classification.status, func.count())
                                    .join(Classification, Classification.question_id == Question.id)
                                    .group_by(Question.paper_id, Classification.status)):
            d = db.setdefault(pid, {})
            d["classified"] = d.get("classified", 0) + n
            if st == "verified":
                d["verified"] = n
    pdf_sessions: dict[str, int] = {}
    for e in entries:
        pdf_sessions[_rel(e.file)] = pdf_sessions.get(_rel(e.file), 0) + 1
    papers = []
    for e in sorted(entries, key=lambda e: (e.year, e.session)):
        f = _rel(e.file)
        d = db.get(e.paper_id, {})
        papers.append({
            "year": e.year, "group": group_of(e.year), "paper_id": e.paper_id, "session": e.session,
            "status": "deferred" if e.status == "skip" else e.status,
            "question_pdf": f, "pages": f"{e.pages[0]}-{e.pages[1]}" if e.pages else "all",
            "papers_in_this_pdf": pdf_sessions[f],
            "key_source": _key_source(e), "has_key": bool(e.key),
            "layout": e.layout or "-", "read_by_ocr": "always" if e.ocr == "always" else ("-" if e.status == "skip" else "if needed"),
            "in_db_questions": d.get("questions", 0), "in_db_keys": d.get("keys", 0), "in_db_ocr_questions": d.get("ocr", 0),
            "classified": d.get("classified", 0), "verified": d.get("verified", 0),
        })
    years = []
    for y in sorted({p["year"] for p in papers}):
        rows = [p for p in papers if p["year"] == y]
        pdfs = sorted({p["question_pdf"] for p in rows})
        key_pdfs = sorted({p["key_source"].split(" ")[3] for p in rows if p["key_source"].startswith("separate")})
        years.append({
            "year": y, "group": group_of(y), "papers (sessions)": len(rows),
            "question PDFs": len(pdfs), "files": ", ".join(Path(x).name for x in pdfs),
            "how bundled": ("1 PDF, " + str(len(rows)) + " sessions inside") if len(pdfs) == 1 and len(rows) > 1
                           else ("1 PDF, 1 paper" if len(rows) == 1 else "1 PDF per session" if len(pdfs) == len(rows)
                                 else f"{len(pdfs)} PDFs for {len(rows)} sessions"),
            "keys": ("separate key PDF" + ("s" if len(key_pdfs) > 1 else "") + ": " + ", ".join(key_pdfs)) if key_pdfs
                    else ("inside the question PDF" if all(p["has_key"] for p in rows)
                          else ("none" if not any(p["has_key"] for p in rows)
                                else f"{sum(p['has_key'] for p in rows)} of {len(rows)} sessions keyed")),
            "status": rows[0]["status"],
            "questions in DB": sum(p["in_db_questions"] for p in rows),
        })
    groups = []
    for g, desc in GROUPS.items():
        rows = [p for p in papers if p["group"] == g]
        groups.append({"years": g, "what it is": desc, "years count": len({p['year'] for p in rows}),
                       "papers (sessions)": len(rows), "question PDFs": len({p["question_pdf"] for p in rows}),
                       "with official key": sum(p["has_key"] for p in rows),
                       "questions in DB": sum(p["in_db_questions"] for p in rows)})
    active = [p for p in papers if p["status"] != "deferred"]
    raw = APP_ROOT / "data" / "raw"
    totals = {"years": len(years), "papers": len(papers), "active_papers": len(active),
              "deferred_papers": len(papers) - len(active),
              "question_pdfs": len({p["question_pdf"] for p in papers}),
              "key_pdfs": len({p for p in (raw / "keys").rglob("*.pdf")}) if (raw / "keys").exists() else 0,
              "active_with_key": sum(p["has_key"] for p in active),
              "active_without_key": sum(not p["has_key"] for p in active),
              "expected_questions_active": 65 * len(active),
              "questions_in_db": sum(p["in_db_questions"] for p in papers)}
    return {"papers": papers, "years": years, "groups": groups, "totals": totals}
