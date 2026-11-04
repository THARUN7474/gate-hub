"""Human review contract (docs/18): five-check rubric, approval blocked without a passing rubric, separate approval
scopes, audited extraction corrections that survive re-ingestion, secondary topics as tags, and AI never verified."""
import json
import pytest
from sqlalchemy import select
from src.classification import classify as cl
from src.db.models import Classification, Option, Question, ReviewEvent
from src.db.session import make_session
from src.validation import review as rv

PASS = {k: 1 for k in rv.RUBRIC_KEYS}

@pytest.fixture()
def classified(loaded):
    db_url, pid, rec = loaded
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        s.commit()
    return db_url, pid

def test_rubric_is_validated_and_scored(classified):
    db_url, pid = classified
    uid = f"{pid}-Q01"
    with make_session(db_url) as s:
        with pytest.raises(ValueError):
            rv.save_rubric(s, uid, {"source_fidelity": 1}, "owner")                  # all five required
        with pytest.raises(ValueError):
            rv.save_rubric(s, uid, {**PASS, "concept_depth": 2}, "owner")            # only 0/1
        rec = rv.save_rubric(s, uid, {**PASS, "explanation": 0}, "owner", "weak evidence")
        assert rec["review_quality_score"] == 4 and rec["taxonomy_version"] == "gate-cs-2027"
        assert rv.latest_rubric(s, uid)["explanation"] == 0
        ev = s.scalar(select(ReviewEvent).where(ReviewEvent.field == "rubric"))
        assert ev.reviewer == "owner" and ev.created_at is not None and json.loads(ev.after)["review_quality_score"] == 4

def test_verify_requires_a_passing_rubric(classified):
    db_url, pid = classified
    uid = f"{pid}-Q02"
    with make_session(db_url) as s:
        with pytest.raises(ValueError, match="no review rubric"):
            rv.set_status(s, uid, "verified", "owner")
        rv.save_rubric(s, uid, {**PASS, "source_fidelity": 0}, "owner")
        with pytest.raises(ValueError, match="source_fidelity"):
            rv.set_status(s, uid, "verified", "owner")
        rv.save_rubric(s, uid, {**PASS, "primary_topic": 0}, "owner")
        with pytest.raises(ValueError, match="primary_topic"):
            rv.set_status(s, uid, "verified", "owner")
        assert s.scalar(select(Classification.status).where(Classification.question_id == uid)) != "verified"
        rv.save_rubric(s, uid, {**PASS, "concept_depth": 0}, "owner")                # only the two are required
        rv.set_status(s, uid, "verified", "owner")
        assert s.scalar(select(Classification.status).where(Classification.question_id == uid)) == "verified"
        sc = rv.approval_scope(s, uid)
        assert sc["classification_verified"] and sc["extraction_verified"] and sc["key_status"] == "loaded"
        s.commit()

def test_classification_only_approval_never_claims_a_missing_key(classified):
    from src.db.models import AnswerKey
    db_url, pid = classified
    uid = f"{pid}-Q03"
    with make_session(db_url) as s:
        s.delete(s.scalar(select(AnswerKey).where(AnswerKey.question_id == uid)))
        rv.save_rubric(s, uid, PASS, "owner")
        rv.set_status(s, uid, "verified", "owner")
        sc = rv.approval_scope(s, uid)
        assert sc["classification_verified"] and sc["key_status"] == "missing" and not sc["key_verified"]

def test_batch_approval_obeys_the_same_rule(classified):
    db_url, pid = classified
    with make_session(db_url) as s:
        rv.save_rubric(s, f"{pid}-Q04", PASS, "owner")
        res = rv.approve_batch(s, [f"{pid}-Q04", f"{pid}-Q05"], reviewer="owner")
        assert res["approved"] == 1 and res["blocked_no_passing_rubric"] == 1
        st = dict(s.execute(select(Classification.question_id, Classification.status)).all())
        assert st[f"{pid}-Q04"] == "verified" and st[f"{pid}-Q05"] != "verified"

def test_extraction_corrections_are_audited_and_survive_reingestion(classified, fixture_paper, tmp_path):
    from src.extraction.extract import extract_questions, persist_records
    db_url, pid = classified
    uid = f"{pid}-Q02"
    with make_session(db_url) as s:
        old = s.get(Question, uid).text
        rv.apply_decision(s, uid, "text", old + " (fixed)", "owner", "OCR fix")
        opt = s.scalar(select(Option).where(Option.question_id == uid).order_by(Option.label))
        if opt:
            rv.apply_decision(s, uid, f"option:{opt.label}", "corrected option", "owner")
        rv.apply_decision(s, uid, "marks", 2, "owner")
        with pytest.raises(ValueError):
            rv.apply_decision(s, uid, "option:Z", "x", "owner")
        with pytest.raises(ValueError):
            rv.apply_decision(s, uid, "paper_id", "x", "owner")
        s.commit()
        fields = [e.field for e in s.scalars(select(ReviewEvent).where(ReviewEvent.question_id == uid))]
        assert "text" in fields and "marks" in fields
    pdf, _ = fixture_paper
    with make_session(db_url) as s:                        # re-load the same PDF, even in refresh mode
        persist_records(s, extract_questions(pdf, pid, tmp_path / "a"), refresh=True)
        s.commit()
        assert s.get(Question, uid).text.endswith(" (fixed)") and s.get(Question, uid).marks == 2.0
        if opt:
            assert s.scalar(select(Option.content).where(Option.question_id == uid, Option.label == opt.label)) == "corrected option"

def test_classification_correction_keeps_extraction_flag_and_validates_ids(classified):
    db_url, pid = classified
    uid = f"{pid}-Q01"
    with make_session(db_url) as s:
        q = s.get(Question, uid); q.needs_review = True; q.review_reason = "notation to check"
        with pytest.raises(ValueError, match="unknown or deprecated"):
            rv.apply_decision(s, uid, "primary_topic_id", "ALGO.NOPE", "owner")
        rv.apply_decision(s, uid, "primary_topic_id", "ALGO.GRAPH", "owner")
        assert q.needs_review and q.review_reason == "notation to check"           # still flagged for the human
        ev = s.scalars(select(ReviewEvent).where(ReviewEvent.question_id == uid, ReviewEvent.field == "primary_topic_id")).first()
        assert "[taxonomy gate-cs-2027]" in ev.note

def test_secondary_topics_are_tags_only(classified):
    from src.analytics import analyze as az
    db_url, pid = classified
    uid = f"{pid}-Q01"
    with make_session(db_url) as s:
        rv.apply_decision(s, uid, "primary_topic_id", "ALGO.SORT", "owner")
        before = az.section_year_matrix(s) if hasattr(az, "section_year_matrix") else None
        rv.apply_decision(s, uid, "secondary_topic_ids", ["ALGO.GRAPH", "PDS.TREE"], "owner")
        c = s.scalar(select(Classification).where(Classification.question_id == uid))
        assert c.primary_topic_id == "ALGO.SORT" and set(c.topic_weight) == {"ALGO.SORT", "ALGO.GRAPH", "PDS.TREE"}
        assert c.status != "verified"                                                # a correction is not a verification
        if before is not None:
            assert az.section_year_matrix(s) == before                               # tags never add marks
        with pytest.raises(ValueError):
            rv.apply_decision(s, uid, "secondary_topic_ids", ["NOT.A.TOPIC"], "owner")

def test_human_corrected_row_is_never_replaced_by_a_rerun(classified):
    db_url, pid = classified
    uid = f"{pid}-Q03"
    with make_session(db_url) as s:
        rv.apply_decision(s, uid, "primary_topic_id", "ALGO.GRAPH", "owner")       # corrected, NOT verified
        s.commit()
        res = cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid, reclassify=True)
        assert res["skipped_verified"] >= 1
        assert s.scalar(select(Classification.primary_topic_id).where(Classification.question_id == uid)) == "ALGO.GRAPH"

def test_audit_history_and_coverage(classified):
    db_url, pid = classified
    uid = f"{pid}-Q04"
    with make_session(db_url) as s:
        rv.save_rubric(s, uid, PASS, "alice"); rv.set_status(s, uid, "verified", "alice")
        hist = rv.audit_history(s, uid)
        assert [h["field"] for h in hist] == ["rubric", "status", "extraction_verified", "key_verified"]
        assert all(h["reviewer"] == "alice" for h in hist)
        cov = rv.review_coverage(s)
        assert cov["questions"] == 6 and cov["classified"] == 6 and cov["verified"] == 1 and cov["with_rubric"] == 1
        assert cov["review_coverage"] == "1/6 classified questions verified by a human"
