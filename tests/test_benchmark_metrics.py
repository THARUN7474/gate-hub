"""v11: stratified benchmark sampling (no fabricated gold), gold-only metrics,
and the review-priority ordering."""
import datetime
from sqlalchemy import select
from src.classification import classify as cl
from src.db.models import BenchmarkSample, Classification, Question, ReviewEvent
from src.db.session import make_session
from src.validation import benchmark as bm, metrics as mt, review as rv


# ---------------- pure metric math ----------------

def test_accuracy_and_per_group():
    rows = [{"pred_topic": "A", "gold_topic": "A", "section": "S1", "year": 2020},
            {"pred_topic": "B", "gold_topic": "A", "section": "S1", "year": 2020},
            {"pred_topic": "C", "gold_topic": "C", "section": "S2", "year": 2021}]
    assert mt.accuracy(rows) == 2 / 3
    g = mt.per_group(rows, "section")
    assert g["S1"] == {"n": 2, "accuracy": 0.5}
    assert g["S2"] == {"n": 1, "accuracy": 1.0}
    assert mt.accuracy([]) is None


def test_concept_prf_micro():
    rows = [{"gold_concepts": ["a", "b"], "pred_concepts": ["a", "c"]},
            {"gold_concepts": ["a"], "pred_concepts": ["a"]},
            {"gold_concepts": [], "pred_concepts": ["x"]}]  # no gold: excluded
    r = mt.concept_prf(rows)
    assert r["tp"] == 2 and r["fp"] == 1 and r["fn"] == 1
    assert abs(r["precision"] - 2 / 3) < 1e-9 and abs(r["recall"] - 2 / 3) < 1e-9
    assert mt.concept_prf([{"gold_concepts": [], "pred_concepts": ["x"]}]) is None


def test_calibration_buckets():
    rows = [{"pred_topic": "A", "gold_topic": "A", "confidence": 0.9},
            {"pred_topic": "B", "gold_topic": "A", "confidence": 0.85},
            {"pred_topic": "A", "gold_topic": "A", "confidence": 0.2},
            {"pred_topic": None, "gold_topic": "A", "confidence": 0.7}]  # no prediction: excluded
    cal = mt.calibration(rows, bins=5)
    assert cal is not None
    hi = [b for b in cal if b["range"] == "0.8-1.0"][0]
    assert hi["n"] == 2 and hi["accuracy"] == 0.5
    assert mt.calibration([{"pred_topic": None, "confidence": None}]) is None


# ---------------- benchmark sampling ----------------

def test_benchmark_sample_deterministic_and_pending(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        r1 = bm.select_benchmark_sample(s, 4, 7, "b1")
        s.commit()
        rows = s.scalars(select(BenchmarkSample)).all()
        ids1 = sorted(b.question_id for b in rows)
        assert r1["selected"] == 4 and len(ids1) == 4
        assert all(b.status == "pending_user_review" for b in rows), "selector never assigns gold"
        assert all(b.gold_primary_topic_id is None for b in rows)
        # a second batch never resamples the same questions
        r2 = bm.select_benchmark_sample(s, 4, 7, "b2")
        s.commit()
        ids2 = [b.question_id for b in s.scalars(select(BenchmarkSample).where(BenchmarkSample.batch == "b2"))]
        assert not set(ids1) & set(ids2)
        assert r2["selected"] == 2, "only 2 questions were left unsampled"
        st = bm.benchmark_status(s)
        assert st["by_status"]["pending_user_review"] == 6


def test_benchmark_sample_reproducible_selection(loaded):
    """Same seed on identical data picks the same questions (checked on two dbs)."""
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        bm.select_benchmark_sample(s, 3, 99, "bx")
        s.commit()
        first = sorted(b.question_id for b in s.scalars(select(BenchmarkSample)).all())
        for b in s.scalars(select(BenchmarkSample)).all():
            s.delete(b)
        s.commit()
        bm.select_benchmark_sample(s, 3, 99, "by")
        s.commit()
        second = sorted(b.question_id for b in s.scalars(select(BenchmarkSample)).all())
    assert first == second


# ---------------- gold-only evaluation ----------------

def test_evaluate_benchmark_uses_only_verified_gold(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        bm.select_benchmark_sample(s, 3, 5, "g1")
        s.commit()
        # nothing verified yet: honest zero-sample report
        rep0 = mt.evaluate_benchmark(s, "gate-cs-2027")
        assert rep0["n_gold_verified"] == 0 and rep0["n_scored"] == 0
        assert rep0["topic_accuracy"] is None and rep0["n_pending_review"] == 3
        # a human verifies two rows: one gold matches the prediction, one does not
        samples = s.scalars(select(BenchmarkSample)).all()
        labels = {c.question_id: c for c in s.scalars(select(Classification)).all()}
        s1, s2 = samples[0], samples[1]
        s1.status = "gold_verified"
        s1.gold_primary_topic_id = labels[s1.question_id].primary_topic_id
        s1.gold_section_id = labels[s1.question_id].section_id
        s1.reviewer = "human-tester"
        s1.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
        s2.status = "gold_verified"
        s2.gold_primary_topic_id = "__not_the_prediction__"
        s2.gold_section_id = labels[s2.question_id].section_id
        s2.reviewer = "human-tester"
        s2.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
        s.flush()
        rep = mt.evaluate_benchmark(s, "gate-cs-2027")
        assert rep["n_gold_verified"] == 2 and rep["n_scored"] == 2
        assert rep["topic_accuracy"] == 0.5
        assert rep["section_accuracy"] == 1.0
        # the third row is still pending and was never scored
        assert rep["n_pending_review"] == 1
        assert s1.question_id not in rep["missing_prediction_ids"]


# ---------------- review priority ----------------

def test_prioritized_review_queue_order(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        cls = s.scalars(select(Classification)).all()
        suggested = [x for x in cls if x.status == "suggested"]
        assert len(suggested) >= 3, "fixture should leave at least 3 plain suggestions"
        # row A: flagged; row B: low-confidence suggestion; row C: taxonomy gap (unclassified)
        a, b, c = suggested[0], suggested[1], suggested[2]
        a.status = "flagged"
        b.confidence = 0.5
        gap_qid = c.question_id
        qid_b = b.question_id
        qid_a = a.question_id
        s.delete(c)
        s.add(ReviewEvent(question_id=gap_qid, field="taxonomy_gap",
                          reviewer="agent-test", note="no syllabus topic exists"))
        s.flush()
        rows = rv.prioritized_review_queue(s, include_spotcheck=False)
    buckets = {r["question_id"]: r["priority_bucket"] for r in rows}
    assert buckets[gap_qid] == "taxonomy_gap"
    assert buckets[qid_a] == "classifier_flagged"
    assert buckets[qid_b] == "low_confidence"
    # bucket order is non-decreasing in priority (gaps first, unclassified last)
    order = {b: i for i, b in enumerate(rv.PRIORITY_BUCKETS)}
    seq = [order[r["priority_bucket"]] for r in rows]
    assert seq == sorted(seq)
    assert rows[0]["question_id"] == gap_qid, "taxonomy gap reviews first"
    assert [r["priority_rank"] for r in rows] == list(range(1, len(rows) + 1))
    # same population as the plain queue (plus buckets), nothing dropped
    assert len(rows) == 6

def test_verify_records_gold_and_evaluate_consumes_it(loaded):
    """The full chain: sample -> human verifies in the normal review flow (rubric +
    set_status) -> sample row becomes gold_verified with the human's final label ->
    evaluate_benchmark scores it. No auto-approval: without a passing rubric the
    verification is refused and no gold is recorded."""
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        bm.select_benchmark_sample(s, 6, 3, "chain")
        s.commit()
        row = s.scalars(select(BenchmarkSample)).first()
        uid = row.question_id
        # no rubric yet: verification refused, no gold
        import pytest as _pt
        with _pt.raises(ValueError):
            rv.set_status(s, uid, "verified", reviewer="owner")
        assert row.status == "pending_user_review"
        # passing rubric, then verify: gold recorded from the human's decision
        rv.save_rubric(s, uid, {k: 1 for k in rv.RUBRIC_KEYS}, "owner")
        rv.set_status(s, uid, "verified", reviewer="owner")
        s.flush()
        assert row.status == "gold_verified" and row.reviewer == "owner"
        c = s.scalar(select(Classification).where(Classification.question_id == uid))
        assert row.gold_primary_topic_id == c.primary_topic_id
        rep = mt.evaluate_benchmark(s, "gate-cs-2027")
        assert rep["n_gold_verified"] == 1 and rep["topic_accuracy"] == 1.0
        assert rep["prediction_source"] == "frozen_baseline_at_sampling"
        # a later correction re-syncs the gold to the human's latest decision
        rv.save_rubric(s, uid, {k: 1 for k in rv.RUBRIC_KEYS}, "owner")
        rv.apply_decision(s, uid, "primary_topic_id", "DL.NUM", "owner")
        rv.set_status(s, uid, "verified", reviewer="owner")
        s.flush()
        assert row.gold_primary_topic_id == "DL.NUM"
        assert row.status == "gold_verified"
        rep2 = mt.evaluate_benchmark(s, "gate-cs-2027")
        assert rep2["n_gold_verified"] == 1 and rep2["n_pending_review"] == 5

def test_evaluation_scores_frozen_baseline_not_live_label(loaded):
    """Regression (tautology guard): the machine's initial prediction is WRONG, the
    human corrects and verifies -> baseline accuracy must be 0.0 for that row, not
    1.0. Scoring the live (corrected) label against gold copied from it would be
    scoring the gold against itself."""
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        bm.select_benchmark_sample(s, 6, 3, "freeze")
        s.commit()
        row = s.scalars(select(BenchmarkSample).where(
            BenchmarkSample.baseline_primary_topic_id.isnot(None))).first()
        uid = row.question_id
        frozen_wrong = row.baseline_primary_topic_id
        other = s.scalar(select(Classification.primary_topic_id).where(
            Classification.primary_topic_id != frozen_wrong).limit(1))
        assert other, "fixture needs a second topic to correct to"
        # human corrects to a DIFFERENT topic and verifies
        rv.save_rubric(s, uid, {k: 1 for k in rv.RUBRIC_KEYS}, "owner")
        rv.apply_decision(s, uid, "primary_topic_id", other, "owner")
        rv.set_status(s, uid, "verified", reviewer="owner")
        s.flush()
        assert row.gold_primary_topic_id == other != frozen_wrong
        # the frozen baseline still holds the original (wrong) machine prediction
        assert row.baseline_primary_topic_id == frozen_wrong
        rep = mt.evaluate_benchmark(s, "gate-cs-2027")
        assert rep["n_gold_verified"] == 1 and rep["n_scored"] == 1
        assert rep["topic_accuracy"] == 0.0, "frozen wrong baseline must score 0, not 1"


def test_reflag_revokes_gold(loaded):
    """Re-flagging un-verifies: formerly verified gold must leave the scored set."""
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        bm.select_benchmark_sample(s, 6, 3, "revoke")
        s.commit()
        row = s.scalars(select(BenchmarkSample)).first()
        uid = row.question_id
        rv.save_rubric(s, uid, {k: 1 for k in rv.RUBRIC_KEYS}, "owner")
        rv.set_status(s, uid, "verified", reviewer="owner")
        s.flush()
        assert row.status == "gold_verified"
        assert mt.evaluate_benchmark(s, "gate-cs-2027")["n_gold_verified"] == 1
        rv.set_status(s, uid, "flagged", reviewer="owner", note="second thoughts")
        s.flush()
        assert row.status == "pending_user_review"
        assert row.gold_primary_topic_id is None and row.reviewer is None
        rep = mt.evaluate_benchmark(s, "gate-cs-2027")
        assert rep["n_gold_verified"] == 0 and rep["n_scored"] == 0


def test_stale_input_excluded_from_scoring(loaded):
    """If the question text changes after sampling (re-extraction/OCR fix), the
    frozen prediction no longer describes the input: report stale, do not score."""
    from src.db.models import Question
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        bm.select_benchmark_sample(s, 6, 3, "stale")
        s.commit()
        row = s.scalars(select(BenchmarkSample)).first()
        uid = row.question_id
        rv.save_rubric(s, uid, {k: 1 for k in rv.RUBRIC_KEYS}, "owner")
        rv.set_status(s, uid, "verified", reviewer="owner")
        s.flush()
        rep = mt.evaluate_benchmark(s, "gate-cs-2027")
        assert rep["n_scored"] == 1 and rep["n_stale_input_excluded"] == 0
        q = s.get(Question, uid)
        q.text = (q.text or "") + " [OCR corrected after sampling]"
        s.flush()
        rep2 = mt.evaluate_benchmark(s, "gate-cs-2027")
        assert rep2["n_stale_input_excluded"] == 1 and rep2["n_scored"] == 0
        assert rep2["topic_accuracy"] is None

