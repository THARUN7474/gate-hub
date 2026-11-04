"""Re-extraction drift: normalized comparison sees through glyph/spacing
noise, real content changes are caught, and persist_records never silently
overwrites stored text."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from src.db.models import Question
from src.db.session import make_session
from src.validation.drift import compare_records_vs_db, drift_status, normalize_text

def test_normalize_folds_spacing_and_math_glyphs():
    assert normalize_text("a  b\n c") == "a b c"
    assert normalize_text("𝑥 + 1") == normalize_text("x + 1")  # math italic folds via NFKC
    assert normalize_text("  ") == ""
    assert drift_status("x ", "x") == "normalized"
    assert drift_status("x", "y") == "changed"
    assert drift_status("same", "same") == "exact"

def test_compare_classifies_records(loaded):
    db_url, pid, _ = loaded
    from src.extraction.extract import extract_questions
    pdf = None
    with make_session(db_url) as s:
        # rebuild records identical to stored rows
        from src.db.models import Paper, Document
        p = s.get(Paper, pid); doc = s.get(Document, p.document_id)
        pdf = doc.file_path
        records = extract_questions(pdf, pid, "/tmp/drift-assets")
        rep = compare_records_vs_db(s, records)
        assert rep["summary"]["exact"] == len(records)
        assert rep["summary"]["changed"] == 0
        # mutate one record's text -> changed; whitespace-only -> normalized
        records[0]["text"] = "completely different stem"
        records[1]["text"] = records[1]["text"] + "   "
        rep = compare_records_vs_db(s, records)
        assert rep["summary"]["changed"] == 1
        assert records[1]["id"] in rep["normalized_match"]

def test_persist_never_overwrites_drifted_text(loaded):
    db_url, pid, _ = loaded
    from src.db.models import Paper, Document
    from src.extraction.extract import extract_questions, persist_records
    with make_session(db_url) as s:
        p = s.get(Paper, pid); doc = s.get(Document, p.document_id)
        records = extract_questions(doc.file_path, pid, "/tmp/drift-assets")
        victim = records[2]
        original = s.get(Question, victim["id"]).text
        victim["text"] = "TAMPERED " + victim["text"]
        res = persist_records(s, victim and records)
        assert res["drift_flagged"] == 1
        q = s.get(Question, victim["id"])
        assert q.text == original            # stored text kept
        assert q.needs_review                # and flagged
        assert "drift" in (q.review_reason or "")
        s.commit()
        # whitespace-only change: no flag, no churn
        records = extract_questions(doc.file_path, pid, "/tmp/drift-assets")
        records[2]["text"] = records[2]["text"] + "  "
        res = persist_records(s, records)
        assert res["drift_flagged"] == 0

def test_human_decisions_and_keys_survive_reextraction(loaded):
    """Text, marks, q_type, review events and imported keys are all preserved
    when a human has touched the question; only regions/pages refresh."""
    db_url, pid, _ = loaded
    from sqlalchemy import select
    from src.db.models import AnswerKey, Document, Option, Paper, Question
    from src.validation import review as rv
    from src.extraction.extract import extract_questions, persist_records
    uid = f"{pid}-Q03"
    with make_session(db_url) as s:
        rv.apply_decision(s, uid, "marks", "99", reviewer="owner")
        rv.apply_decision(s, uid, "q_type", "MSQ", reviewer="owner")
        q = s.get(Question, uid)
        q.text = "HUMAN-EDITED STEM"
        key_before = s.get(AnswerKey, None) or s.scalars(
            select(AnswerKey).where(AnswerKey.question_id == uid)).first()
        key_snapshot = (key_before.answer_kind, list(key_before.answer_list or [])) if key_before else None
        p = s.get(Paper, pid); doc = s.get(Document, p.document_id)
        records = extract_questions(doc.file_path, pid, "/tmp/drift-assets2")
        res = persist_records(s, records)
        q = s.get(Question, uid)
        assert q.text == "HUMAN-EDITED STEM" and q.marks == 99.0 and q.q_type == "MSQ"
        assert res["human_preserved"] >= 1
        key_after = s.scalars(select(AnswerKey).where(AnswerKey.question_id == uid)).first()
        if key_snapshot:
            assert (key_after.answer_kind, list(key_after.answer_list or [])) == key_snapshot
        s.rollback()
