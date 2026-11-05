"""AI review v2: type check, full reasoning stored, never changes a live label, batches skip held questions."""
import importlib.util
import json
from argparse import Namespace
from pathlib import Path

from sqlalchemy import select

from src.analytics import opinions as op
from src.db.models import (BenchmarkSample, Classification, ClassificationProposal, Paper, Question, ReviewEvent,
                           TaxonomyNode)
from src.db.session import make_session

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ai_review", ROOT / "scripts" / "ai_review.py")
air = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(air)


def _seed(s):
    for nid, lvl, par in (("DL", "section", None), ("DL.CIRC", "topic", "DL"), ("DL.NUM", "topic", "DL"),
                          ("DL.CIRC.SEQ", "concept", "DL.CIRC")):
        s.add(TaxonomyNode(node_id=nid, version=air.TAXV, parent_id=par, level=lvl, name=nid, provenance="official"))
    s.add(Paper(id="P", year=2011, session="CS", reconciled=True))
    for i in range(1, 5):
        s.add(Question(id=f"P-Q{i}", paper_id="P", q_number=i, text="t", marks=1.0, q_type="NAT",
                       needs_review=(i == 4)))
    s.flush()
    for i in (1, 2, 3):
        s.add(Classification(question_id=f"P-Q{i}", taxonomy_version=air.TAXV, section_id="DL",
                             primary_topic_id="DL.CIRC", confidence=0.8, provenance="inferred", status="suggested",
                             model="m", prompt_version="v"))
    s.add(BenchmarkSample(question_id="P-Q3", batch="b1", stratum="DL", status="pending_user_review"))
    s.commit()


def _dec(qid, verdict, topic="DL.CIRC", qtype="NAT"):
    return {"question_id": qid, "verdict": verdict, "question_type": qtype, "section_id": "DL",
            "primary_topic_id": topic, "concept_ids": ["DL.CIRC.SEQ"], "secondary_topic_ids": ["DL.NUM"],
            "why_this_topic": "mod-N counter needs ceil(log2 N) flip-flops", "solution_sketch": "2^9=512>=258",
            "alternatives_considered": [{"topic_id": "DL.NUM", "why_not": "not about number systems"}],
            "my_answer": "A", "key_check": "no_key", "difficulty": "easy", "confidence": 0.9, "note": "n"}


def test_v2_import_flags_never_changes_and_stores_reasoning(db_url, tmp_path, monkeypatch):
    monkeypatch.setattr(air, "OUT", tmp_path)
    with make_session(db_url) as s:
        _seed(s)
        ok, held = air.eligible(s)
        assert [q.id for q in ok] == ["P-Q1", "P-Q2"]                     # Q3 benchmark, Q4 extraction issue
        assert held["benchmark - after your gold review"] == 1 and held["extraction issue - fix it first"] == 1
    f = tmp_path / "d.json"
    f.write_text(json.dumps({"reviewer": "claude-test", "prompt_version": "ai-review-v2", "decisions": [
        _dec("P-Q1", "correct", topic="DL.NUM"), _dec("P-Q2", "flag", qtype="MCQ")]}), encoding="utf-8")
    monkeypatch.setattr("src.backup.backup", lambda url: {"file": "x", "integrity_check": "ok"})
    assert air.cmd_import(Namespace(decisions=str(f), yes=True, db_url=db_url)) == 0
    with make_session(db_url) as s:
        c1 = s.scalar(select(Classification).where(Classification.question_id == "P-Q1"))
        assert c1.primary_topic_id == "DL.CIRC" and c1.status == "flagged"          # not changed, only flagged
        p = s.scalar(select(ClassificationProposal).where(ClassificationProposal.question_id == "P-Q1"))
        assert p.prompt_version == "ai-review-v2" and p.primary_topic_id == "DL.NUM"
        rows = op.ai_review_rows_for(s, "P-Q2")
        assert rows[-1]["why_this_topic"].startswith("mod-N") and rows[-1]["question_type"] == "MCQ"
        st2 = op.question_stages(s, "P-Q2")
        assert st2["qtype"] == {"stored": "NAT", "ai": "MCQ", "ai_differs": True, "human": None}
        flag = s.scalar(select(ReviewEvent).where(ReviewEvent.question_id == "P-Q2",
                                                  ReviewEvent.field == "classification_flagged"))
        assert "AI says type MCQ" in flag.note
        assert [q.id for q in air.eligible(s)[0]] == []                  # both done with v2
        r = {x["question_id"]: x for x in op.ai_review_rows(s)}
        assert r["P-Q2"]["type_differs"] and r["P-Q1"]["version"] == "ai-review-v2"


def test_v2_rejects_bad_type(db_url, tmp_path):
    with make_session(db_url) as s:
        _seed(s)
    f = tmp_path / "d.json"
    f.write_text(json.dumps({"prompt_version": "ai-review-v2", "decisions": [_dec("P-Q1", "agree", qtype="XYZ")]}),
                 encoding="utf-8")
    assert air.cmd_import(Namespace(decisions=str(f), yes=True, db_url=db_url)) == 2
