"""scripts/repair_truncated_text.py: completes ONLY a pure truncation, never rewrites or touches verified content."""
import sys
from pathlib import Path
import pytest
from sqlalchemy import select
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import repair_truncated_text as rt  # noqa: E402
from src.db.models import Classification, Question, ReviewEvent  # noqa: E402
from src.db.session import make_session  # noqa: E402

def _records(s, pid):
    """What a fresh extraction would produce = what is stored right now (fixture paper)."""
    from src.db.models import Option
    out = []
    for q in s.scalars(select(Question).where(Question.paper_id == pid).order_by(Question.q_number)):
        opts = [{"label": o.label, "content": o.content}
                for o in s.scalars(select(Option).where(Option.question_id == q.id).order_by(Option.label))]
        out.append({"id": q.id, "text": q.text, "options": opts})
    return out

def test_truncated_text_is_completed_and_audited(loaded):
    db_url, pid, _ = loaded
    qid = f"{pid}-Q02"
    with make_session(db_url) as s:
        recs = _records(s, pid)
        full = s.get(Question, qid).text
        s.get(Question, qid).text = full[:-12]                 # simulate the old truncating repair
        s.commit()
    with make_session(db_url) as s:
        p = rt.plan(s, recs)
        assert [f["question_id"] for f in p["fixable"]] == [qid] and p["refused"] == []
        assert p["fixable"][0]["missing_tail"] == full[-12:]
        assert rt.apply(s, p) == 1
        s.commit()
    with make_session(db_url) as s:
        assert s.get(Question, qid).text == full
        ev = s.scalar(select(ReviewEvent).where(ReviewEvent.question_id == qid, ReviewEvent.field == "text"))
        assert ev.before == full[:-12] and ev.after == full and ev.reviewer == rt.REVIEWER
        assert rt.plan(s, recs) == {"fixable": [], "refused": []}      # idempotent: nothing left to do

def test_real_content_difference_is_reported_not_touched(loaded):
    db_url, pid, _ = loaded
    qid = f"{pid}-Q03"
    with make_session(db_url) as s:
        recs = _records(s, pid)
        s.get(Question, qid).text = "a human corrected this sentence"      # NOT a prefix of the fresh text
        s.commit()
        p = rt.plan(s, recs)
        assert p["fixable"] == [] and "not a prefix" in p["refused"][0]["why"]
        assert rt.apply(s, p) == 0
        assert s.get(Question, qid).text == "a human corrected this sentence"

def test_verified_question_is_never_touched_even_if_it_is_a_pure_prefix(loaded):
    db_url, pid, _ = loaded
    qid = f"{pid}-Q04"
    with make_session(db_url) as s:
        recs = _records(s, pid)
        full = s.get(Question, qid).text
        s.get(Question, qid).text = full[:-5]
        s.add(Classification(question_id=qid, taxonomy_version="gate-cs-2027", prompt_version="v1", section_id="ALGO",
                             primary_topic_id="ALGO.SORT", confidence=1.0, status="verified", model="human",
                             provenance="validated"))
        s.commit()
        p = rt.plan(s, recs)
        assert p["fixable"] == [] and "human-verified" in p["refused"][0]["why"]
        assert rt.apply(s, p) == 0 and s.get(Question, qid).text == full[:-5]

def test_differing_options_are_not_a_truncation(loaded):
    db_url, pid, _ = loaded
    qid = f"{pid}-Q01"
    with make_session(db_url) as s:
        recs = _records(s, pid)
        full = s.get(Question, qid).text
        s.get(Question, qid).text = full[:-3]
        if recs[0]["options"]:
            recs[0]["options"][0] = {"label": recs[0]["options"][0]["label"], "content": "changed"}
        else:
            recs[0]["options"] = [{"label": "A", "content": "new"}]
        p = rt.plan(s, recs)
        assert p["fixable"] == [] and "options differ" in p["refused"][0]["why"]
