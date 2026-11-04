"""Benchmark metrics computed ONLY from user-verified gold (benchmark_samples rows
with status='gold_verified'). Nothing here invents labels: an empty verified set
returns an honest zero-sample report, never made-up numbers. Pure metric helpers
take plain row dicts so they are unit-testable without a database."""
from __future__ import annotations
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import BenchmarkSample, Classification, ClassificationProposal, Paper, Question


def accuracy(rows: list[dict]) -> float | None:
    """Fraction of rows where pred_topic == gold_topic. None when no rows."""
    if not rows:
        return None
    return sum(1 for r in rows if r["pred_topic"] == r["gold_topic"]) / len(rows)


def per_group(rows: list[dict], key: str) -> dict[str, dict]:
    """Accuracy within each value of row[key] (e.g. 'section' or 'year')."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[str(r.get(key))].append(r)
    return {k: {"n": len(v), "accuracy": accuracy(v)} for k, v in sorted(groups.items())}


def concept_prf(rows: list[dict]) -> dict | None:
    """Micro precision/recall/F1 over concept id sets. Rows need gold_concepts and
    pred_concepts lists. None when no row has gold concepts."""
    tp = fp = fn = 0
    seen = False
    for r in rows:
        gold = set(r.get("gold_concepts") or [])
        pred = set(r.get("pred_concepts") or [])
        if not gold:
            continue
        seen = True
        tp += len(gold & pred)
        fp += len(pred - gold)
        fn += len(gold - pred)
    if not seen:
        return None
    p = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * rec / (p + rec) if p + rec else 0.0
    return {"precision": p, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def calibration(rows: list[dict], bins: int = 5) -> list[dict] | None:
    """Confidence buckets vs empirical correctness, over rows that have both a
    prediction and a confidence. None when no such rows."""
    usable = [r for r in rows if r.get("confidence") is not None and r.get("pred_topic")]
    if not usable:
        return None
    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        bucket = [r for r in usable
                  if lo <= r["confidence"] < hi or (i == bins - 1 and r["confidence"] == 1.0)]
        if bucket:
            out.append({"range": f"{lo:.1f}-{hi:.1f}", "n": len(bucket),
                        "mean_confidence": sum(r["confidence"] for r in bucket) / len(bucket),
                        "accuracy": accuracy(bucket)})
    return out


def evaluate_benchmark(s: Session, taxonomy_version: str, batch: str | None = None,
                       provider: str | None = None) -> dict:
    """Score FROZEN predictions against USER-VERIFIED gold only.

    Default prediction source: each sample row's frozen baseline - the machine
    prediction snapshotted when the question was sampled, before any human
    correction. The live `classifications` row is NEVER the prediction source:
    after a human correction it IS the gold, so scoring it would be a tautology.
    With provider=NAME: that provider's independent proposals instead
    (second-opinion comparison; classifications still untouched). Gold rows whose
    question text changed since sampling (re-extraction/OCR fix) are reported as
    stale and excluded from accuracy. Pending rows are counted but never scored."""
    from ..classification.classify import question_content_hash
    q = select(BenchmarkSample).where(BenchmarkSample.status == "gold_verified")
    if batch:
        q = q.where(BenchmarkSample.batch == batch)
    gold_rows = s.scalars(q).all()
    pending = s.scalars(select(BenchmarkSample).where(BenchmarkSample.status == "pending_user_review")).all()
    props = {}
    if provider:
        props = {p.question_id: p for p in s.scalars(
            select(ClassificationProposal).where(ClassificationProposal.provider == provider,
                                                 ClassificationProposal.taxonomy_version == taxonomy_version)).all()}
    rows, missing, stale = [], [], []
    for g in gold_rows:
        qn = s.get(Question, g.question_id)
        paper = s.get(Paper, qn.paper_id) if qn else None
        if provider:
            pred_topic = pred_section = None
            pred_conf = pred_concepts = None
            p = props.get(g.question_id)
            if p is not None:
                pred_topic, pred_section = p.primary_topic_id, p.section_id
                pred_conf, pred_concepts = p.confidence, p.concept_ids or []
        else:
            if (g.baseline_content_hash and qn is not None
                    and question_content_hash(qn) != g.baseline_content_hash):
                stale.append(g.question_id)     # input changed after the prediction was frozen
                continue
            pred_topic, pred_section = g.baseline_primary_topic_id, g.baseline_section_id
            pred_conf, pred_concepts = g.baseline_confidence, g.baseline_concept_ids
        if not pred_topic:
            missing.append(g.question_id)
            continue
        rows.append({"question_id": g.question_id,
                     "gold_topic": g.gold_primary_topic_id, "pred_topic": pred_topic,
                     "gold_section": g.gold_section_id, "section": pred_section,
                     "year": paper.year if paper else None,
                     "confidence": pred_conf,
                     "gold_concepts": g.gold_concept_ids or [],
                     "pred_concepts": pred_concepts or []})
    topic_rows = [r for r in rows if r["gold_topic"]]
    section_rows = [dict(r, gold_topic=r["gold_section"], pred_topic=r["section"])
                    for r in rows if r["gold_section"]]
    return {"taxonomy_version": taxonomy_version,
            "prediction_source": (f"proposals:{provider}" if provider
                                  else "frozen_baseline_at_sampling"),
            "n_gold_verified": len(gold_rows), "n_pending_review": len(pending),
            "n_scored": len(rows), "n_missing_prediction": len(missing),
            "missing_prediction_ids": missing[:20],
            "n_stale_input_excluded": len(stale), "stale_input_ids": stale[:20],
            "topic_accuracy": accuracy(topic_rows),
            "section_accuracy": accuracy(section_rows),
            "per_section": per_group(topic_rows, "section"),
            "per_year": per_group(topic_rows, "year"),
            "concept_prf": concept_prf(rows),
            "calibration": calibration(rows),
            "note": ("scores come only from gold_verified rows (human-reviewed) against the "
                     "FROZEN pre-review prediction (or one provider's proposals); the live "
                     "classification row is never scored against gold that was copied from it; "
                     "pending_user_review rows are listed but never scored")}
