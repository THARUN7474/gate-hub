from src.db.session import make_session
from src.db.models import Option, Question
from sqlalchemy import select

def test_counts_and_reconcile(loaded):
    _, pid, rec = loaded
    assert rec["derived_questions"] == 6
    assert rec["derived_marks"] == 8.0
    assert rec["reconciled"] is True
    assert rec["null_marks_or_type"] == 0

def test_types_options_crops(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        qs = {q.id: q for q in s.scalars(select(Question))}
        n_opts = {o.question_id for o in s.scalars(select(Option))}
    assert qs[f"{pid}-Q03"].q_type == "MCQ"
    assert qs[f"{pid}-Q05"].q_type == "NAT"
    assert qs[f"{pid}-Q06"].q_type == "MSQ"      # upgraded by key import
    assert qs[f"{pid}-Q01"].marks == 1.0 and qs[f"{pid}-Q06"].marks == 2.0
    assert "binary search" in qs[f"{pid}-Q03"].text
    assert qs[f"{pid}-Q03"].regions_json         # source-PDF region stored (no image files by default)
    assert qs[f"{pid}-Q03"].image_path is None   # crops only behind write_crops=True
    assert f"{pid}-Q01" in n_opts

def test_idempotent_reimport(loaded, fixture_paper, tmp_path):
    """Importing the same PDF twice creates no duplicates."""
    db_url, pid, _ = loaded
    pdf, _ = fixture_paper
    from src.extraction.extract import extract_questions, persist_records, reconcile
    with make_session(db_url) as s:
        persist_records(s, extract_questions(pdf, pid, tmp_path / "assets2"))
        rec = reconcile(s, pid)
        s.commit()
    assert rec["derived_questions"] == 6
