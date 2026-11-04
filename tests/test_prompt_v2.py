"""Prompt v2 = question text + OPTIONS + POSITION HINT (GA block vs CS block). Nothing else is sent: not the key, not the
marks, not the year or session. Offline: fake transports only."""
import json
import sqlite3
from pathlib import Path
import pytest
from sqlalchemy import select
from src.classification import classify as cl
from src.db.models import Classification, Option, Question
from src.db.session import make_session

ROOT = Path(__file__).resolve().parents[1]

def resp(section="ALGO", topic="ALGO.SORT", conf=0.9):
    body = {"section_id": section, "primary_topic_id": topic, "topic_weight": {topic: 1.0}, "concept_ids": [],
            "what_it_tests": "x", "prerequisite_ids": [], "confidence": conf, "evidence_quote": "q"}
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}

class Spy:
    """Transport that records every prompt text it is sent and answers with `answer`."""
    def __init__(self, answer):
        self.answer, self.prompts = answer, []
    def __call__(self, url, headers, payload):
        self.prompts.append(payload["contents"][0]["parts"][0]["text"])
        return self.answer

@pytest.fixture()
def gem(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GATE_LLM_MODEL", "test-model-1")
    monkeypatch.setenv("GATE_LLM_FREE_PLAN_CONFIRMED", "1")

def run(db_url, pid, spy, **kw):
    p = cl.get_provider("gemini", transport=spy)
    with make_session(db_url) as s:
        res = cl.run_classification(s, p, "gate-cs-2027", pid, allow_external=True, guard=cl.RunGuard(rpm=0), **kw)
        s.commit()
    return res

# ------------------------------------------------------------------------------------------------ layout detection
def marks_first():   # GA Q1-10 (5x1, 5x2), then CS 25x1, 30x2
    return {i: (1 if i <= 5 else 2 if i <= 10 else 1 if i <= 35 else 2) for i in range(1, 66)}
def marks_last():    # CS Q1-25 x1, Q26-55 x2, GA Q56-60 x1, Q61-65 x2
    return {i: (1 if i <= 25 else 2 if i <= 55 else 1 if i <= 60 else 2) for i in range(1, 66)}

def test_layout_detection():
    assert cl._ga_layout(marks_first()) == "first" and cl._ga_layout(marks_last()) == "last"
    assert cl._ga_layout({**marks_first(), 11: 2}) is None                 # not the exam's pattern -> no hint
    assert cl._ga_layout({**marks_first(), 7: None}) is None               # unknown mark -> no hint
    assert cl._ga_layout({i: 1 for i in range(1, 11)}) is None             # incomplete paper -> no hint
    assert cl._ga_layout({}) is None

class FakeQ:
    def __init__(self, paper_id, n): self.paper_id, self.q_number = paper_id, n

def test_block_follows_layout():
    c = {"P1": "first", "P2": "last", "P3": None}
    assert [cl._question_block(None, FakeQ("P1", n), c) for n in (1, 10, 11, 65)] == ["GA", "GA", "CS", "CS"]
    assert [cl._question_block(None, FakeQ("P2", n), c) for n in (1, 55, 56, 65)] == ["CS", "CS", "GA", "GA"]
    assert cl._question_block(None, FakeQ("P3", 5), c) is None

def test_conflict_rule():
    o = lambda sec: cl.ClassificationOut(section_id=sec, primary_topic_id="x")
    assert cl._position_conflict("GA", o("EM")) and not cl._position_conflict("GA", o("GA"))
    assert cl._position_conflict("CS", o("GA")) and not cl._position_conflict("CS", o("EM"))
    assert not cl._position_conflict(None, o("GA")) and not cl._position_conflict(None, o("EM"))

@pytest.mark.skipif(not (ROOT / "data" / "gate_cse.sqlite").exists(), reason="live DB not present (fresh clone)")
def test_every_loaded_paper_has_a_known_layout():
    """Evidence run on 4 Nov 2026: 21 papers GA-first, 8 GA-last, none unknown (spot-checked against question text)."""
    db = sqlite3.connect(f"file:{ROOT / 'data' / 'gate_cse.sqlite'}?mode=ro", uri=True)
    seen = {}
    for (pid,) in db.execute("select id from papers").fetchall():
        marks = dict(db.execute("select q_number, marks from questions where paper_id=?", (pid,)).fetchall())
        seen[pid] = cl._ga_layout(marks)
    assert None not in seen.values(), [k for k, v in seen.items() if v is None]
    assert sorted(k for k, v in seen.items() if v == "last") == [
        "GATE-CS-2011-S1", "GATE-CS-2012-S1", "GATE-CS-2013-S1", "GATE-CS-2013-S2", "GATE-CS-2013-S3",
        "GATE-CS-2013-S4", "GATE-CS-2017-S1", "GATE-CS-2017-S2"]

# ------------------------------------------------------------------------------------------------ what is sent
def test_prompt_has_hint_outside_the_question_block_and_nothing_else():
    topics = [{"parent_id": "ALGO", "node_id": "ALGO.SORT", "name": "Sorting", "concepts": []}]
    txt = cl._user_prompt("Q text", ["opt one", "opt two"], topics, cl._hint("GA"))
    head, _, q = txt.partition("<question>")
    assert "Position hint" in head and "Position hint" not in q                # hint cannot be spoofed from inside the question
    assert "(A) opt one" in q and "(B) opt two" in q and q.rstrip().endswith("</question>")
    assert "Position hint" not in cl._user_prompt("Q text", [], topics, None)  # no hint -> no line at all

def test_options_reach_the_model_and_rows_are_v2(loaded, gem):
    db_url, pid, _ = loaded
    spy = Spy(resp())
    res = run(db_url, pid, spy)
    assert res["classified"] == 6 and cl.PROMPT_VERSION == "v2"
    with make_session(db_url) as s:
        opts = {q.id: [o.content for o in sorted(q.options, key=lambda o: o.label)]
                for q in s.scalars(select(Question).where(Question.paper_id == pid).order_by(Question.q_number))}
        assert {r.prompt_version for r in s.scalars(select(Classification))} == {"v2"}
    assert any(opts.values()), "fixture should have at least one question with options"
    for prompt, (qid, o) in zip(spy.prompts, opts.items()):
        for i, text in enumerate(o):
            assert f"({chr(65 + i)}) {text}" in prompt, (qid, text)

def test_no_hint_when_layout_unknown(loaded, gem):
    db_url, pid, _ = loaded                    # 6-question fixture paper: not a 65-question layout
    spy = Spy(resp())
    run(db_url, pid, spy)
    assert spy.prompts and not any("Position hint" in p for p in spy.prompts)

def test_nothing_else_is_sent(loaded, gem, monkeypatch):
    """No answer key, no marks, no year/session/paper id in the prompt."""
    db_url, pid, _ = loaded
    spy = Spy(resp())
    run(db_url, pid, spy)
    for p in spy.prompts:
        for forbidden in (pid, "2099", "GATE-CS", "answer_key", "marks", "official key"):
            assert forbidden not in p, forbidden

def test_hint_is_sent_and_contradiction_is_flagged_for_a_human(loaded, gem, monkeypatch):
    db_url, pid, _ = loaded
    monkeypatch.setattr(cl, "_ga_layout", lambda marks: "first")               # pretend: Q1-10 are GA (all 6 questions)
    spy = Spy(resp(section="ALGO", topic="ALGO.SORT"))                           # model says a CS section for GA questions
    res = run(db_url, pid, spy)
    assert all("Position hint" in p and "General Aptitude (GA) block" in p for p in spy.prompts)
    assert res["flagged"] == 6 and res["classified"] == 6
    with make_session(db_url) as s:
        rows = s.scalars(select(Classification)).all()
        reasons = s.scalars(select(Question.review_reason).where(Question.paper_id == pid)).all()
    assert {r.status for r in rows} == {"flagged"} and {r.provenance for r in rows} == {"inferred"}
    assert all("contradicts the question's position" in x for x in reasons)

def test_agreeing_with_the_hint_is_not_flagged(loaded, gem, monkeypatch):
    db_url, pid, _ = loaded
    monkeypatch.setattr(cl, "_ga_layout", lambda marks: "last")                # Q1-6 are then the CS block
    spy = Spy(resp(section="ALGO", topic="ALGO.SORT"))
    res = run(db_url, pid, spy)
    assert all("Computer Science block" in p for p in spy.prompts)
    assert res["flagged"] == 0 and res["classified"] == 6

def test_compare_reports_block_and_conflict(loaded, gem, monkeypatch):
    db_url, pid, _ = loaded
    monkeypatch.setattr(cl, "_ga_layout", lambda marks: "first")
    with make_session(db_url) as s:
        s.add(Classification(question_id=f"{pid}-Q01", taxonomy_version="gate-cs-2027", prompt_version="agent-v1",
                             section_id="ALGO", primary_topic_id="ALGO.SORT", confidence=0.9, status="suggested",
                             model="agent", provenance="inferred"))
        s.commit()
    p = cl.get_provider("gemini", transport=Spy(resp(section="ALGO", topic="ALGO.SORT")))
    with make_session(db_url) as s:
        res = cl.compare_with_existing(s, p, "gate-cs-2027", pid, sample=1.0, allow_external=True, guard=cl.RunGuard(rpm=0))
    row = res["rows"][0]
    assert row["paper_block"] == "GA" and row["position_conflict"] is True and row["needs_manual_review"] is True

def test_dry_run_preview_includes_options(loaded, gem):
    from src.taxonomy.taxonomy import topic_list
    db_url, pid, _ = loaded
    p = cl.get_provider("gemini", transport=Spy(resp()))
    with make_session(db_url) as s:
        out = cl.run_classification(s, p, "gate-cs-2027", pid, dry_run=True)
        first = s.scalars(select(Question).where(Question.paper_id == pid).order_by(Question.q_number)).first()
        assert first.options, "fixture question 1 should have options"
        without = len(json.dumps(p.build_request(first.text, [], topic_list(s, "gate-cs-2027"))[2]))
    assert out["dry_run"] and out["questions_would_classify"] == 6
    assert out["request_previews"][0]["payload_chars"] > without               # the preview is the v2 request (with options)
