"""Official answer keys. Keys arrive in inconsistent formats across years, so
the reliable path is: parse the official key PDF (src/ingestion/keypdf.py) or
read a CSV, normalise to canonical records, then import. Anomalies are
modelled: NAT ranges, MSQ sets, MTA/dropped (marks to all), multi-answer MCQ,
corrected final-key versions. Missing keys are listed, never guessed. Import is
idempotent per question.

CROSS-CHECK (new): every record that carries the key's question type and marks
is compared with what extraction found. A disagreement is a strong signal of an
extraction defect (e.g. key says NAT but extraction saw four phantom options),
so it is reported in the result AND the question is flagged needs_review - the
key never silently overwrites extraction, and extraction never silently
overrides the key. The only automatic change is MCQ -> MSQ when the key says MSQ
(extraction cannot tell a multi-select from a single-select question)."""
from __future__ import annotations
import csv
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db.models import AnswerKey, Question

KIND_ALIASES = {"MCQ": "mcq_single", "MSQ": "msq_set", "NAT": "nat_range",
                "MCQ_SINGLE": "mcq_single", "MSQ_SET": "msq_set", "NAT_RANGE": "nat_range",
                "NAT_VALUE": "nat_value", "DROPPED": "dropped", "MTA": "dropped"}
KIND_TO_QTYPE = {"mcq_single": "MCQ", "msq_set": "MSQ", "nat_range": "NAT", "nat_value": "NAT"}

def normalize_kind(kind: str) -> str:
    k = (kind or "").strip()
    return KIND_ALIASES.get(k.upper(), k)

def _flag(q: Question, reason: str) -> None:
    q.needs_review = True
    if reason not in (q.review_reason or ""):
        q.review_reason = ((q.review_reason + "; ") if q.review_reason else "") + reason

_INFERRED_MARKS = "marks inferred from the fixed GATE exam pattern (no mark-section header matched)"

def _confirm_marks(q: Question) -> None:
    """The official key states the marks and they equal what extraction inferred from the exam
    pattern: that review reason is now answered by evidence, so it is removed (and the question
    un-flagged only if nothing else is wrong)."""
    if q.review_reason and _INFERRED_MARKS in q.review_reason:
        parts = [p for p in q.review_reason.split("; ") if p and p != _INFERRED_MARKS]
        q.review_reason = "; ".join(parts) or None
        if not parts:
            q.needs_review = False

def import_key_records(s: Session, paper_id: str, records: list[dict], key_version: str = "final",
                       source_document_id: str | None = None) -> dict:
    """records: dicts with qno, kind, answer, min, max, notes and optional qtype, marks."""
    imported, unmatched = 0, []
    type_mismatches, marks_mismatches, upgraded = [], [], []
    for row in records:
        qno = int(row["qno"])
        uid = f"{paper_id}-Q{qno:02d}"
        q = s.get(Question, uid)
        if q is None:
            unmatched.append(qno); continue
        kind = normalize_kind(str(row["kind"]))
        answers = [a.strip() for a in str(row.get("answer") or "").split(";") if a.strip()]
        amin = float(row["min"]) if row.get("min") not in (None, "") else None
        amax = float(row["max"]) if row.get("max") not in (None, "") else None
        if kind == "nat_value" and answers and amin is None:
            amin = amax = float(answers[0])
        key = s.scalar(select(AnswerKey).where(AnswerKey.question_id == uid))
        if key is None:
            key = AnswerKey(question_id=uid)
            s.add(key)
        key.answer_kind = kind; key.answer_list = answers
        key.answer_min = amin; key.answer_max = amax
        key.key_version = key_version; key.source_document_id = source_document_id
        key.notes = row.get("notes") or None
        # --- cross-check against extraction -------------------------------------------------
        key_type = KIND_TO_QTYPE.get(kind) or (row.get("qtype") or None)
        if kind == "msq_set" and q.q_type == "MCQ":
            q.q_type = "MSQ"; upgraded.append(qno)
        elif key_type and q.q_type and key_type != q.q_type:
            type_mismatches.append({"qno": qno, "key": key_type, "extracted": q.q_type})
            _flag(q, f"key says {key_type} but extraction found {q.q_type}")
        elif key_type and q.q_type is None:
            type_mismatches.append({"qno": qno, "key": key_type, "extracted": None})
        if row.get("marks") not in (None, "") and q.marks is not None and float(row["marks"]) != q.marks:
            marks_mismatches.append({"qno": qno, "key": float(row["marks"]), "extracted": q.marks})
            _flag(q, f"key marks {float(row['marks']):g} differ from extracted {q.marks:g}")
        elif row.get("marks") not in (None, "") and q.marks is not None:
            _confirm_marks(q)
        if kind == "dropped":
            _flag(q, "dropped/bonus (marks to all) per key")
        imported += 1
    s.flush()
    return {"paper_id": paper_id, "imported": imported, "unmatched_qnos": unmatched,
            "type_mismatches": type_mismatches, "marks_mismatches": marks_mismatches,
            "upgraded_to_msq": upgraded}

def import_keys_csv(s: Session, paper_id: str, csv_path: str | Path,
                    key_version: str = "final", source_document_id: str | None = None) -> dict:
    """CSV columns: qno,kind,answer[,min,max,notes,qtype,marks]
    kind: mcq_single|msq_set|nat_range|nat_value|dropped (legacy MCQ|MSQ|NAT accepted)
    answer: 'B' (MCQ) | 'A;C' (MSQ set) | numeric (nat_value)."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        records = list(csv.DictReader(f))
    return import_key_records(s, paper_id, records, key_version, source_document_id)
