"""v13: second opinions, per-question stages, uncapped search, matrix totals."""
import json

from src.analytics import links as nav, opinions as op, search as srch
from src.db.models import Classification, Paper, Question, ReviewEvent
from src.db.session import make_session


def _seed(session, n=3):
    session.add(Paper(id="P-1", year=2020, session="CS-1", reconciled=True))
    for i in range(1, n + 1):
        session.add(Question(id=f"P-1-Q{i}", paper_id="P-1", q_number=i, text=f"question {i}", marks=1.0,
                             q_type="MCQ", needs_review=(i == 2), review_reason="empty option" if i == 2 else None))
    session.flush()
    session.add(Classification(question_id="P-1-Q1", taxonomy_version="t", section_id="OS", primary_topic_id="OS.MEM",
                               confidence=0.9, provenance="inferred", status="suggested", model="m", prompt_version="v"))
    session.add(ReviewEvent(question_id="P-1-Q1", field="ai_review", reviewer="claude (AI review)",
                            after=json.dumps({"verdict": "correct", "section_id": "OS", "primary_topic_id": "OS.PROC",
                                              "confidence": 0.8, "note": "process, not memory"})))
    session.flush()


def test_ai_review_rows_and_stage_summary(db_url):
    with make_session(db_url) as s:
        _seed(s)
        rows = op.ai_review_rows(s)
        assert len(rows) == 1 and rows[0]["verdict"] == "correct" and rows[0]["same_topic"] is False
        assert rows[0]["label_topic"] == "OS.MEM" and rows[0]["ai_topic"] == "OS.PROC"
        S = op.stage_summary(s)
        assert S["questions"] == 3 and S["classified"] == 1 and S["extraction_issues"] == 1
        assert S["ai_reviewed"] == 1 and S["ai_verdicts"] == {"correct": 1} and S["decision_questions"] == 0


def test_question_stages_reports_every_stage(db_url):
    with make_session(db_url) as s:
        _seed(s)
        st1 = op.question_stages(s, "P-1-Q1")
        assert st1["machine"][0] == "suggestion" and st1["ai_review"][0] == "correct"
        assert st1["decision_models"][0] == "not run" and st1["human"][0] == "not yet"
        st2 = op.question_stages(s, "P-1-Q2")
        assert st2["extraction"][0] == "needs a check" and st2["machine"][0] == "no label"


def test_search_has_no_cap_and_filters_extraction(db_url):
    with make_session(db_url) as s:
        _seed(s, n=520)
        assert len(srch.search_questions(s)) == 520                      # the old default capped at 500
        assert [r["id"] for r in srch.search_questions(s, extraction_issue=True)] == ["P-1-Q2"]
        assert len(srch.search_questions(s, extraction_issue=False)) == 519


def test_matrix_html_has_column_totals_and_grand_total():
    m = {"years": [2020, 2021], "sections": {
        "OS": {"years": {2020: {"marks": 5, "questions": 3}, 2021: {"marks": 2, "questions": 1}}, "total_marks": 7, "total_q": 4},
        "DB": {"years": {2020: {"marks": 4, "questions": 2}}, "total_marks": 4, "total_q": 2}}}
    html = nav.matrix_html(m, {"OS": "Operating System"})
    foot = html[html.index("<tfoot>"):]
    assert ">9<" in foot and ">2<" in foot and ">11<" in foot           # 5+4, 2, grand 11
    assert "Operating System" in html
    t = nav.topic_matrix_html([{"topic": "OS.MEM", "year": 2020, "questions": 2},
                               {"topic": "OS.PROC", "year": 2020, "questions": 3}])
    assert ">5<" in t[t.index("<tfoot>"):]


def test_matrix_html_question_counts():
    m = {"years": [2020], "sections": {
        "OS": {"years": {2020: {"marks": 5, "questions": 3}}, "total_marks": 5, "total_q": 3},
        "DB": {"years": {2020: {"marks": 4, "questions": 2}}, "total_marks": 4, "total_q": 2}}}
    foot = nav.matrix_html(m, metric="questions").split("<tfoot>")[1]
    assert ">5<" in foot and ">9<" not in foot                         # 3+2 questions, not 9 marks


def test_engine_counts_stages_and_diagrams(db_url):
    from src.analytics import engine as eng
    with make_session(db_url) as s:
        _seed(s)
        k = eng.counts(s)
        assert k["questions"] == 3 and k["labelled"] == 1 and k["extraction_issues"] == 1 and k["ai_reviewed"] == 1
        rows = {r["stage"]: r["state"] for r in eng.stage_rows(k)}
        assert rows["7. First-pass labels"] == "doing" and rows["12. Decision models"] == "optional"
        assert eng.label_sources(s)[0]["labels"] == 1
        for dot in (eng.pipeline_dot(k), eng.question_model_dot(), eng.lifecycle_dot(), eng.question_dot(s, "P-1-Q1")):
            assert dot.startswith("digraph") and dot.rstrip().endswith("}") and dot.count("{") == dot.count("}")
        assert "AI review: correct" in eng.question_dot(s, "P-1-Q1")
