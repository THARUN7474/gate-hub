"""Stratified benchmark sample selection for HUMAN gold review (v11).

The selector only picks WHICH questions a human should review to build the gold
benchmark. It never assigns labels: every row is written with
status='pending_user_review', and validation.metrics.evaluate_benchmark reads
only 'gold_verified' rows - so no fabricated gold can ever enter the metrics.
Selection is deterministic for a given seed, stratified by (paper, marks) so the
sample mirrors the dataset instead of over-drawing one paper or one mark value."""
from __future__ import annotations
import random
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import BenchmarkSample, Classification, Paper, Question

STATUSES = ("pending_user_review", "gold_verified", "gold_rejected")


def _stratum(paper: Paper, q: Question) -> str:
    marks = "marksnull" if q.marks is None else ("marks1" if q.marks <= 1.0 else "marks2")
    return f"{paper.year}-{paper.session}/{marks}"


def select_benchmark_sample(s: Session, n: int, seed: int, batch: str) -> dict:
    """Pick up to n questions, stratified by (year-session, marks bucket), skipping
    questions already in any benchmark batch. Returns an honest summary; writes
    rows with status='pending_user_review' (commit is the caller's job)."""
    if n <= 0:
        raise ValueError("n must be positive")
    already = set(s.scalars(select(BenchmarkSample.question_id)).all())
    strata: dict[str, list[tuple[Paper, Question]]] = defaultdict(list)
    rows = s.execute(select(Paper, Question).join(Question, Question.paper_id == Paper.id)
                     .order_by(Paper.year, Paper.session, Question.q_number)).all()
    for paper, q in rows:
        if q.id not in already:
            strata[_stratum(paper, q)].append((paper, q))
    total_avail = sum(len(v) for v in strata.values())
    if total_avail == 0:
        return {"batch": batch, "requested": n, "selected": 0, "by_stratum": {},
                "note": "every question is already in a benchmark batch"}
    target = min(n, total_avail)
    # proportional allocation with largest remainder; every stratum gets >= 1 when possible
    keys = sorted(strata)
    alloc = {k: min(len(strata[k]), 1) for k in keys}
    remaining = target - sum(alloc.values())
    quotas = sorted(((len(strata[k]) / total_avail * target - alloc[k], k) for k in keys),
                    key=lambda t: (-t[0], t[1]))
    while remaining > 0:
        progressed = False
        for _, k in quotas:
            if remaining <= 0:
                break
            if alloc[k] < len(strata[k]):
                alloc[k] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            break
    from ..classification.classify import question_content_hash
    labels = {c.question_id: c for c in s.scalars(select(Classification)).all()}
    rng = random.Random(seed)
    written = 0
    by_stratum: dict[str, int] = {}
    for k in keys:
        pool = list(strata[k])
        rng.shuffle(pool)
        for paper, q in pool[: alloc[k]]:
            c = labels.get(q.id)     # freeze the CURRENT machine prediction as the baseline
            s.add(BenchmarkSample(question_id=q.id, batch=batch, stratum=k,
                                  status="pending_user_review",
                                  sampled_at=datetime.now(timezone.utc),
                                  baseline_section_id=c.section_id if c else None,
                                  baseline_primary_topic_id=c.primary_topic_id if c else None,
                                  baseline_concept_ids=list(c.concept_ids or []) if c else None,
                                  baseline_confidence=c.confidence if c else None,
                                  baseline_run_id=c.run_id if c else None,
                                  baseline_content_hash=question_content_hash(q)))
            by_stratum[k] = by_stratum.get(k, 0) + 1
            written += 1
    return {"batch": batch, "requested": n, "selected": written, "by_stratum": by_stratum,
            "note": "rows are pending_user_review; gold labels come only from human review"}


def benchmark_status(s: Session) -> dict:
    """Counts per status and per batch."""
    rows = s.scalars(select(BenchmarkSample)).all()
    by_status: dict[str, int] = defaultdict(int)
    by_batch: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        by_status[r.status] += 1
        by_batch[r.batch][r.status] += 1
    return {"total": len(rows), "by_status": dict(by_status),
            "by_batch": {b: dict(v) for b, v in sorted(by_batch.items())}}

def sync_gold_from_review(s: Session, question_id: str, reviewer: str) -> BenchmarkSample | None:
    """If this question belongs to a benchmark sample, record the human's VERIFIED
    label as the row's gold. Called from review.set_status after a successful
    verification (one-by-one and Approve Queue alike): gold always mirrors the
    human's latest verified decision - corrections included - and never a machine
    value. A sample row never becomes gold any other way. Returns the updated row,
    or None when the question is not in any benchmark batch."""
    from ..db.models import Classification
    row = s.scalar(select(BenchmarkSample).where(BenchmarkSample.question_id == question_id))
    if row is None:
        return None
    c = s.scalar(select(Classification).where(Classification.question_id == question_id))
    if c is None or c.status != "verified":
        return row
    row.gold_section_id = c.section_id
    row.gold_primary_topic_id = c.primary_topic_id
    row.gold_concept_ids = list(c.concept_ids or [])
    row.status = "gold_verified"
    row.reviewer = reviewer
    row.reviewed_at = datetime.now(timezone.utc)
    s.flush()
    return row


def sample_membership(s: Session) -> dict[str, tuple[str, str]]:
    """question_id -> (batch, status) for every sampled question (UI surfacing)."""
    return {r.question_id: (r.batch, r.status) for r in s.scalars(select(BenchmarkSample)).all()}

def revoke_gold(s: Session, question_id: str, reason: str) -> BenchmarkSample | None:
    """Take a sample row's gold away: the human re-flagged or un-verified the question,
    so its formerly verified label must not stay scored. Gold fields are cleared and the
    row returns to pending_user_review. Returns the row, or None when not sampled."""
    row = s.scalar(select(BenchmarkSample).where(BenchmarkSample.question_id == question_id))
    if row is None or row.status != "gold_verified":
        return row
    row.status = "pending_user_review"
    row.gold_section_id = None
    row.gold_primary_topic_id = None
    row.gold_concept_ids = None
    row.reviewer = None
    row.reviewed_at = None
    row.note = reason
    s.flush()
    return row
