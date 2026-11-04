"""Regression: review queue and status counts come from BOTH extraction and
classification states; fixture data is labelled synthetic, never official."""
from sqlalchemy import select
from src.classification import classify as cl
from src.db.models import Classification, Question
from src.db.session import make_session
from src.validation import review as rv

def test_queue_covers_flagged_and_unverified(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        queue = rv.review_queue(s)
        counts = rv.review_counts(s)
        s.commit()
    # every mock-classified question is unverified (suggested or flagged) => all 6 pending
    assert len(queue) == 6
    assert counts["pending_review"] == 6 and counts["verified"] == 0
    assert counts["of_which_unverified_suggestions"] + counts["of_which_classifier_flagged"] == 6

def test_verified_leaves_queue_and_counts_distinct(loaded):
    db_url, pid, _ = loaded
    uid = f"{pid}-Q03"
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        rv.apply_decision(s, uid, "primary_topic_id", "ALGO.SORT", reviewer="owner")
        rv.save_rubric(s, uid, {k: 1 for k in rv.RUBRIC_KEYS}, reviewer="owner")
        rv.set_status(s, uid, "verified", reviewer="owner")
        counts = rv.review_counts(s)
        queue_ids = [r["question_id"] for r in rv.review_queue(s)]
        s.commit()
    assert counts["verified"] == 1 and counts["pending_review"] == 5
    assert uid not in queue_ids

def test_flagged_survives_reextraction_in_queue(loaded, fixture_paper, tmp_path):
    """The old bug: re-extraction cleared needs_review and flagged records
    vanished from the queue. The union contract keeps them visible."""
    from src.extraction.extract import extract_questions, persist_records
    db_url, pid, _ = loaded
    pdf, _ = fixture_paper
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)  # flags low-confidence
        persist_records(s, extract_questions(pdf, pid, tmp_path / "a3"))  # resets needs_review
        queue = rv.review_queue(s)
        s.commit()
    assert len(queue) == 6   # still all pending: suggestions unverified

def test_fixture_provenance_labels(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        assert rv.has_fixture_data(s) is True
        label = rv.key_provenance_label(s, f"{pid}-Q01")
    assert label.startswith("Fixture") and "SYNTHETIC" in label
