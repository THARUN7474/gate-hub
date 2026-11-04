"""Re-extraction drift detection. Count reconciliation (65 questions, 100
marks) proves coverage, not content: two different texts give identical
counts. This module compares freshly extracted records against stored rows on
three levels so silent text changes surface instead of passing:

  exact       - byte-identical text and option content
  normalized  - equal after Unicode NFKC + whitespace collapse (catches the
                spacing/diacritic/math-glyph noise a re-extractor produces)
  changed     - normalized forms differ: real drift, must be reviewed

persist_records() uses these helpers and NEVER silently overwrites stored
text that differs: identical or whitespace-only changes keep the stored text
(regions/pages still refresh); real drift keeps the stored text, flags the
question for review and records the drift in the upsert result."""
from __future__ import annotations
import json, re, unicodedata
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db.models import Option, Question

_WS = re.compile(r"\s+")

def normalize_text(s: str | None) -> str:
    """Unicode NFKC (folds math-italic glyphs, ligatures, diacritic spacing)
    plus whitespace collapse. Two extractions that differ only in glyph or
    spacing noise normalize equal; a content change does not."""
    if not s:
        return ""
    return _WS.sub(" ", unicodedata.normalize("NFKC", s)).strip()

def compare_records_vs_db(s: Session, records: list[dict]) -> dict:
    """Classify each extracted record against the stored question row."""
    out = {"exact": [], "normalized_match": [], "changed": [], "new": [], "missing_from_pdf": []}
    seen = set()
    for r in records:
        seen.add(r["id"])
        q = s.get(Question, r["id"])
        if q is None:
            out["new"].append(r["id"])
            continue
        stored_opts = {o.label: o.content for o in s.scalars(
            select(Option).where(Option.question_id == r["id"]))}
        new_opts = {o["label"]: o["content"] for o in r["options"]}
        exact_text = (q.text or "") == (r["text"] or "") and stored_opts == new_opts
        norm_text = (normalize_text(q.text) == normalize_text(r["text"]) and
                     all(normalize_text(stored_opts.get(k)) == normalize_text(v)
                         for k, v in new_opts.items()) and
                     set(stored_opts) == set(new_opts))
        if exact_text:
            out["exact"].append(r["id"])
        elif norm_text:
            out["normalized_match"].append(r["id"])
        else:
            out["changed"].append({"id": r["id"],
                "stored_preview": (q.text or "")[:120], "new_preview": (r["text"] or "")[:120]})
    stored_ids = set(s.scalars(select(Question.id).where(
        Question.paper_id == records[0]["paper_id"] if records else "")).all()) if records else set()
    out["missing_from_pdf"] = sorted(stored_ids - seen)
    out["summary"] = {k: len(v) for k, v in out.items() if k != "summary"}
    return out

def drift_status(stored: str | None, new: str | None) -> str:
    if (stored or "") == (new or ""):
        return "exact"
    if normalize_text(stored) == normalize_text(new):
        return "normalized"
    return "changed"
