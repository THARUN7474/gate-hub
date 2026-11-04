from src.analytics import analyze as az, exports as ex, search as srch
from src.classification import classify as cl
from src.db.session import make_session
from src.validation import validate as vd

def _classified(loaded):
    db_url, pid, rec = loaded
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        s.commit()
    return db_url, pid, rec

def test_matrix_totals_equal_paper_totals(loaded):
    db_url, pid, rec = _classified(loaded)
    with make_session(db_url) as s:
        m = az.section_year_matrix(s, 2099, 2099)
    total = sum(d["total_marks"] for d in m["sections"].values())
    assert total == rec["derived_marks"]

def test_drill_down_contributors(loaded):
    db_url, pid, _ = _classified(loaded)
    with make_session(db_url) as s:
        m = az.section_year_matrix(s, 2099, 2099)
        sec = next(iter(m["sections"]))
        ids = az.drill_down(s, sec, 2099)
        expected = m["sections"][sec]["years"][2099]["questions"]
    assert len(ids) == expected

def test_search_finds_text(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        rows = srch.search_questions(s, text_query="binary search")
    assert any(r["id"] == f"{pid}-Q03" for r in rows)

def test_validation_checks_clean(loaded):
    db_url, pid, _ = _classified(loaded)
    with make_session(db_url) as s:
        checks = vd.run_checks(s)
    assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]

def test_exports_match_db(loaded, tmp_path):
    db_url, pid, _ = _classified(loaded)
    with make_session(db_url) as s:
        result = ex.export_all(s, tmp_path / "exports", 2099, 2099)
        cov = az.coverage_report(s)
    import csv
    with open(tmp_path / "exports" / "questions.csv") as f:
        n = sum(1 for _ in csv.reader(f)) - 1
    assert n == cov["questions"] == 6
    assert "validation_report.json" in result["files"]

def test_matrix_check_allows_unclassified_gap_but_catches_double_count(loaded):
    """v11 merge fix: a deliberately unclassified question (taxonomy gap) is outside the
    matrix by design and must not FAIL the check; a question counted twice must."""
    from sqlalchemy import select
    from src.db.models import Classification
    db_url, pid, _ = _classified(loaded)
    chk = lambda s: {c["check"]: c for c in vd.run_checks(s)}["matrix totals equal paper totals"]
    with make_session(db_url) as s:
        rows = s.scalars(select(Classification)).all()
        gap_q = rows[0].question_id
        s.delete(rows[0]); s.commit()
        c = chk(s)
        assert c["ok"], c
        assert "unclassified marks" in c["details"]
        dup = rows[1]
        s.add(Classification(question_id=dup.question_id, run_id=dup.run_id,
                             taxonomy_version=dup.taxonomy_version, section_id=dup.section_id,
                             primary_topic_id=dup.primary_topic_id, confidence=0.5,
                             provenance="inferred", status="suggested", model="dup", prompt_version="x"))
        s.commit()
        assert not chk(s)["ok"]
        assert gap_q
