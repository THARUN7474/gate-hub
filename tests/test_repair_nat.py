"""NAT repair helper: mistyped question + phantom options -> corrected, flagged,
event logged, idempotent on re-run."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sqlalchemy import select
from src.db.models import AnswerKey, Option, Paper, Question, ReviewEvent
from src.db.session import init_schema, make_session
import repair_nat_type_options as rep

@pytest.fixture()
def sess(blank_db):
    s = make_session(blank_db)
    # Real FK targets: SQLite never enforced them, PostgreSQL does.
    s.add(Paper(id="P", year=2099, session="S1"))
    s.flush()
    s.add(Question(id="P-Q01", paper_id="P", q_number=1, marks=2.0, q_type="MCQ",
                   text="nat question", needs_review=False))
    s.flush()  # AnswerKey has no relationship() to Question, so order the FK target explicitly
    s.add(Option(question_id="P-Q01", label="A", content="phantom"))
    s.add(Option(question_id="P-Q01", label="B", content="phantom2"))
    s.add(AnswerKey(question_id="P-Q01", key_version="final", answer_kind="NAT", answer_list="",
                    answer_min=4.0, answer_max=4.0))
    s.commit()
    yield s
    s.close()

def test_repair_corrects_flags_and_logs(sess):
    res = rep.repair(sess)
    assert res["repaired"] == [("P-Q01", "MCQ", 2)]
    q = sess.get(Question, "P-Q01")
    assert q.q_type == "NAT" and q.needs_review
    assert "official final key" in q.review_reason
    assert not list(sess.scalars(select(Option).where(Option.question_id=="P-Q01")))
    ev = sess.scalars(select(ReviewEvent).where(ReviewEvent.question_id=="P-Q01")).all()
    assert len(ev) == 1 and ev[0].field == "q_type" and ev[0].before == "MCQ"

def test_repair_idempotent(sess):
    rep.repair(sess)
    res2 = rep.repair(sess)
    assert res2["repaired"] == [] and res2["already_consistent"] == 1
