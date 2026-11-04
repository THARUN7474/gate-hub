from sqlalchemy import select
from src.classification import classify as cl
from src.db.models import Classification
from src.db.session import make_session

def test_mock_contract_and_flagging(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        res = cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        rows = s.scalars(select(Classification)).all()
        s.commit()
    assert res["classified"] == 6
    for r in rows:
        assert r.primary_topic_id and r.provenance == "inferred"
        assert r.status in ("suggested", "flagged")

def test_verified_survives_rerun(loaded):
    """Editing + verifying a classification survives an ingestion/classify rerun."""
    from src.validation import review as rv
    db_url, pid, _ = loaded
    uid = f"{pid}-Q03"
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        rv.apply_decision(s, uid, "primary_topic_id", "ALGO.SORT", reviewer="owner")
        rv.save_rubric(s, uid, {k: 1 for k in rv.RUBRIC_KEYS}, reviewer="owner")
        rv.set_status(s, uid, "verified", reviewer="owner")
        s.commit()
    with make_session(db_url) as s:
        res = cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        c = s.scalar(select(Classification).where(Classification.question_id == uid))
        s.commit()
    assert res["skipped_verified"] == 1
    assert c.primary_topic_id == "ALGO.SORT" and c.status == "verified" and c.provenance == "validated"
