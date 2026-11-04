"""Independent provider proposals (v10): a second opinion that never
overwrites the classifications table."""
from sqlalchemy import select
from src.classification import classify as cl
from src.db.models import Classification, ClassificationProposal
from src.db.session import make_session


class OtherMock(cl.MockProvider):
    name = "othermock"; model = "othermock-v1"


def test_proposals_leave_classifications_untouched(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        s.commit()
        before = [(c.question_id, c.primary_topic_id, c.status, c.provenance, c.what_it_tests)
                  for c in s.scalars(select(Classification)).all()]
        res = cl.run_proposals(s, cl.MockProvider(), "gate-cs-2027", pid)
        s.commit()
        after = [(c.question_id, c.primary_topic_id, c.status, c.provenance, c.what_it_tests)
                 for c in s.scalars(select(Classification)).all()]
        props = s.scalars(select(ClassificationProposal)).all()
    assert before == after, "proposals run must not modify the classifications table"
    assert res["proposals_written"] == 6 and len(props) == 6
    assert all(p.provider == "mock" for p in props)


def test_proposals_resume_skips_existing(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        res1 = cl.run_proposals(s, cl.MockProvider(), "gate-cs-2027", pid, max_calls=2)
        s.commit()
    with make_session(db_url) as s:
        res2 = cl.run_proposals(s, cl.MockProvider(), "gate-cs-2027", pid)
        n = len(s.scalars(select(ClassificationProposal)).all())
        s.commit()
    assert res1["proposals_written"] == 2 and res1["stopped"]["kind"] == "cap"
    assert res2["skipped_existing_proposal"] == 2 and res2["proposals_written"] == 4
    assert n == 6, "no duplicate proposal rows after resume"


def test_proposals_multiple_providers_independent(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        cl.run_proposals(s, cl.MockProvider(), "gate-cs-2027", pid)
        cl.run_proposals(s, OtherMock(), "gate-cs-2027", pid)
        s.commit()
        props = s.scalars(select(ClassificationProposal)).all()
    assert len(props) == 12, "each provider keeps its own proposal per question"
    assert {p.provider for p in props} == {"mock", "othermock"}


def test_proposal_agreement(loaded):
    """Agreement counts agree/disagree against current labels and fills for
    unclassified questions, and never double-counts headline analytics."""
    from src.validation import review as rv
    from src.analytics import analyze as az
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        # label all but one question; make one label human-verified and DIFFERENT
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        uid = f"{pid}-Q03"
        rv.apply_decision(s, uid, "primary_topic_id", "ALGO.SORT", reviewer="owner")
        rv.save_rubric(s, uid, {k: 1 for k in rv.RUBRIC_KEYS}, reviewer="owner")
        rv.set_status(s, uid, "verified", reviewer="owner")
        other = f"{pid}-Q06"
        s.query(Classification).filter(Classification.question_id == other).delete()
        s.commit()
        cov_before = az.coverage_report(s)["classified"]
        cl.run_proposals(s, cl.MockProvider(), "gate-cs-2027", pid)
        s.commit()
        cov_after = az.coverage_report(s)["classified"]
        rows = cl.proposal_agreement(s)
    assert cov_before == cov_after, "proposals must not change headline classified counts"
    assert len(rows) == 1 and rows[0]["provider"] == "mock"
    r = rows[0]
    assert r["proposals"] == 6
    assert r["fills_unclassified"] == 1
    assert r["against_verified"] == 1
    assert r["agree"] + r["disagree"] == 5


def test_proposals_dry_run_makes_no_calls(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        res = cl.run_proposals(s, cl.MockProvider(), "gate-cs-2027", pid, dry_run=True)
        n = len(s.scalars(select(ClassificationProposal)).all())
    assert res["dry_run"] is True and res["proposals_would_write"] == 6 and n == 0

def test_proposal_content_hash_and_staleness(loaded):
    """Every proposal stores the hash of the exact text+options it was made from;
    editing a question afterwards is detected as staleness, never silently compared."""
    from src.db.models import Question
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        cl.run_proposals(s, cl.MockProvider(), "gate-cs-2027", pid)
        s.commit()
        props = s.scalars(select(ClassificationProposal)).all()
        assert all(p.source_content_hash and len(p.source_content_hash) == 64 for p in props)
        assert all(r["stale"] == 0 and r["unknown_hash"] == 0 for r in cl.proposal_staleness(s))
        target = props[0].question_id
        q = s.get(Question, target)
        q.text = (q.text or "") + " [OCR corrected]"
        s.flush()
        st = cl.proposal_staleness(s)
        assert st[0]["stale"] == 1 and target in st[0]["stale_question_ids"]

