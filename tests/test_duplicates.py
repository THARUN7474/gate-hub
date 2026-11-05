"""Duplicate question papers (GATE 2013 sets): detected from data, kept in totals, reviewed once."""
from sqlalchemy import select

from src.analytics import analyze as az, dupes
from src.classification.classify import _select_questions
from src.db.models import BenchmarkSample, Classification, Option, Paper, Question, ReviewEvent, TaxonomyNode
from src.db.session import make_session
from src.validation import benchmark as bm, review as rv

TEXTS = ["The minimum number of D flip-flops needed to design a mod-258 counter is",
         "Which one of the following is TRUE about threads of a process and the heap?",
         "Which one of the following is TRUE about threads of a process and the heap?"]   # same stem, other options


def _seed(s):
    for nid, lvl, par in (("DL", "section", None), ("DL.CIRC", "topic", "DL"), ("DL.SEQ", "topic", "DL")):
        s.add(TaxonomyNode(node_id=nid, version="t", parent_id=par, level=lvl, name=nid, provenance="official"))
    for pid, yr, sess in (("Y-S1", 2013, "CS-1"), ("Y-S2", 2013, "CS-2"), ("Z-S1", 2014, "CS-1")):
        s.add(Paper(id=pid, year=yr, session=sess, reconciled=True))
    s.flush()
    # 2013 set 2 = set 1 in another order; 2014 shares a stem but has different options (not a duplicate)
    rows = [("Y-S1-Q1", "Y-S1", 1, TEXTS[0], ["9", "8", "512", "258"]),
            ("Y-S1-Q2", "Y-S1", 2, TEXTS[1], ["globals only", "heap only", "neither", "both"]),
            ("Y-S2-Q1", "Y-S2", 1, TEXTS[1], ["globals only", "heap only", "neither", "both"]),
            ("Y-S2-Q2", "Y-S2", 2, TEXTS[0], ["9", "8", "512", "258"]),
            ("Z-S1-Q1", "Z-S1", 1, TEXTS[2], ["stack", "registers", "program counter", "address space"])]
    for qid, pid, n, text, opts in rows:
        s.add(Question(id=qid, paper_id=pid, q_number=n, text=text, marks=1.0, q_type="MCQ"))
        for lab, o in zip("ABCD", opts):
            s.add(Option(question_id=qid, label=lab, content=o))
    s.flush()
    for qid in ("Y-S1-Q1", "Y-S1-Q2", "Y-S2-Q1", "Y-S2-Q2", "Z-S1-Q1"):
        s.add(Classification(question_id=qid, taxonomy_version="t", section_id="DL", primary_topic_id="DL.CIRC",
                             confidence=0.8, provenance="inferred", status="suggested", model="m", prompt_version="v"))
    s.commit()


def test_detects_shuffled_set_and_ignores_same_stem_other_year(db_url):
    with make_session(db_url) as s:
        _seed(s)
        d = dupes.duplicate_map(s)
        assert d["copy_of"] == {"Y-S2-Q1": "Y-S1-Q2", "Y-S2-Q2": "Y-S1-Q1"}
        assert d["total"] == 5 and d["unique"] == 3 and d["years"] == {2013: ["Y-S1", "Y-S2"]}
        assert "3 unique" in dupes.summary_line(s) and "2 duplicate copies" in dupes.summary_line(s)


def test_copies_skipped_by_queue_classifier_and_sampler_and_matrix(db_url):
    with make_session(db_url) as s:
        _seed(s)
        assert {r["question_id"] for r in rv.review_queue(s)} == {"Y-S1-Q1", "Y-S1-Q2", "Z-S1-Q1"}
        assert {q.id for q in _select_questions(s)} == {"Y-S1-Q1", "Y-S1-Q2", "Z-S1-Q1"}
        res = bm.select_benchmark_sample(s, 10, 1, "b")
        assert res["selected"] == 3
        assert not {b.question_id for b in s.scalars(select(BenchmarkSample))} & {"Y-S2-Q1", "Y-S2-Q2"}
        full = az.section_year_matrix(s, 2013, 2014)
        uniq = az.section_year_matrix(s, 2013, 2014, exclude_ids=set(dupes.duplicate_map(s)["copy_of"]))
        assert full["sections"]["DL"]["years"][2013]["questions"] == 4
        assert uniq["sections"]["DL"]["years"][2013]["questions"] == 2


def test_small_top_up_does_not_overshoot(db_url):
    with make_session(db_url) as s:
        _seed(s)
        assert bm.select_benchmark_sample(s, 1, 1, "b")["selected"] == 1


def test_verifying_the_original_updates_its_copy(db_url):
    with make_session(db_url) as s:
        _seed(s)
        rv.apply_decision(s, "Y-S1-Q1", "primary_topic_id", "DL.SEQ", "owner", "")
        rv.save_rubric(s, "Y-S1-Q1", {k: 1 for k in rv.RUBRIC_KEYS}, "owner", "")
        rv.set_status(s, "Y-S1-Q1", "verified", reviewer="owner")
        s.commit()
        c = s.scalar(select(Classification).where(Classification.question_id == "Y-S2-Q2"))
        assert c.status == "verified" and c.primary_topic_id == "DL.SEQ"
        ev = s.scalars(select(ReviewEvent).where(ReviewEvent.question_id == "Y-S2-Q2")).all()
        assert ev and all("follows original Y-S1-Q1" in (e.note or "") for e in ev)
