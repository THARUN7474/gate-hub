"""Human review. Every decision is a ReviewEvent (audit). Verifying promotes
status=verified / provenance=validated; reruns never overwrite it.

The review queue is computed from BOTH pipeline states, not one flag:
  - extraction issues (questions.needs_review)
  - classifier-flagged records (classifications.status = flagged)
  - unverified machine suggestions (status = suggested)
  - unclassified questions
A question leaves the queue only when its extraction fields are resolved AND
its classification is verified. The verified count is tracked separately and
never mixed into the pending count."""
from __future__ import annotations
import json
from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session
from ..db.models import (AnswerKey, Classification, ClassificationProposal, Document,
                         Option, Paper, Question, ReviewEvent)

def unreviewed_condition():
    latest = select(Classification).where(
        Classification.question_id == Question.id)
    return or_(
        Question.needs_review == True,  # noqa: E712
        Classification.status.in_(["flagged", "suggested"]),
        and_(Question.needs_review == False, Classification.id.is_(None)),  # noqa: E712
    )

def review_queue(s: Session, classified_only: bool = False) -> list[dict]:
    """All unverified questions. classified_only=True keeps only those that HAVE a machine
    suggestion awaiting a human decision (suggested/flagged) - what 'Approve & next' should walk
    through; unclassified questions have nothing to approve yet."""
    q = (select(Question, Classification)
         .outerjoin(Classification, Classification.question_id == Question.id)
         .where(unreviewed_condition())
         .order_by(Question.paper_id, Question.q_number))
    if classified_only:
        q = q.where(Classification.status.in_(["suggested", "flagged"]))
    rows = []
    for qu, c in s.execute(q):
        reasons = []
        if qu.needs_review:
            reasons.append("extraction: " + (qu.review_reason or "flagged"))
        if c is None:
            reasons.append("unclassified")
        elif c.status == "flagged":
            reasons.append("classifier flagged (low confidence or invalid id)")
        elif c.status == "suggested":
            reasons.append("unverified machine suggestion")
        rows.append({"question_id": qu.id, "paper_id": qu.paper_id, "q_number": qu.q_number,
                     "marks": qu.marks, "q_type": qu.q_type,
                     "review_reason": "; ".join(reasons),
                     "section_id": c.section_id if c else None,
                     "primary_topic_id": c.primary_topic_id if c else None,
                     "confidence": c.confidence if c else None,
                     "status": c.status if c else None})
    return rows

def review_counts(s: Session) -> dict:
    """Distinct, non-overlapping headline counts."""
    total = s.scalar(select(Question).limit(1)) is not None
    all_q = (select(Question.id, Question.needs_review, Classification.status)
             .outerjoin(Classification, Classification.question_id == Question.id))
    extraction = flagged = unverified = unclassified = verified = 0
    for qid, needs, status in s.execute(all_q):
        if status == "verified":
            verified += 1
            continue
        if status == "flagged":
            flagged += 1
        elif status == "suggested":
            unverified += 1
        else:
            unclassified += 1
        if needs:
            extraction += 1
    pending = flagged + unverified + unclassified
    return {"pending_review": pending, "of_which_extraction_issues": extraction,
            "of_which_classifier_flagged": flagged, "of_which_unverified_suggestions": unverified,
            "of_which_unclassified": unclassified, "verified": verified,
            "has_questions": total}

def verification_progress(s: Session, paper_id: str | None = None) -> dict:
    """'N of M verified' for the Review Workspace header. M = questions that HAVE a classification
    (what a human can verify today); unclassified questions are reported separately, never
    folded into the denominator."""
    from sqlalchemy import func
    cq = (select(func.count(func.distinct(Classification.question_id)),
                 func.count(func.distinct(case((Classification.status == "verified", Classification.question_id)))))
          .join(Question, Question.id == Classification.question_id))
    tq = select(func.count()).select_from(Question)
    if paper_id:
        cq = cq.where(Question.paper_id == paper_id)
        tq = tq.where(Question.paper_id == paper_id)
    classified, verified = s.execute(cq).one()
    total = s.scalar(tq)
    return {"classified": classified, "verified": verified, "total_questions": total,
            "unclassified": total - classified}

def has_fixture_data(s: Session) -> bool:
    """True when any registered document is a synthetic fixture - the UI must
    then banner every screen. Fixture content is never real GATE data."""
    return s.scalar(select(Document.id).where(Document.doc_type == "fixture").limit(1)) is not None

def key_provenance_label(s: Session, question_id: str) -> str:
    """How the key for this question may be described. 'Official' is asserted
    only when the paper's source document is official; fixture keys are
    labelled synthetic."""
    q = s.get(Question, question_id)
    p = s.get(Paper, q.paper_id)
    doc = s.get(Document, p.document_id) if p and p.document_id else None
    if doc is None or doc.doc_type == "fixture" or doc.rights_status == "fixture":
        return "Fixture key (SYNTHETIC - not a real GATE key)"
    return "Official key"

EXTRACTION_FIELDS = ("marks", "q_type", "text")          # plus "option:<label>"
CLASSIFICATION_FIELDS = ("section_id", "primary_topic_id", "concept_ids", "secondary_topic_ids", "what_it_tests")

def _check_taxonomy_ids(s: Session, c: Classification, field: str, value) -> None:
    """A human correction may only use ids that exist (and are not deprecated) in the row's taxonomy version."""
    if field == "what_it_tests":
        return
    from ..taxonomy.taxonomy import valid_node_ids
    valid = valid_node_ids(s, c.taxonomy_version, include_deprecated=False)
    ids = value if isinstance(value, list) else [value]
    bad = [i for i in ids if i not in valid]
    if bad:
        raise ValueError(f"unknown or deprecated taxonomy id(s) for {c.taxonomy_version}: {bad}")

def apply_decision(s: Session, question_id: str, field: str, new_value,
                   reviewer: str, note: str = "") -> None:
    """One human correction = one audited ReviewEvent (before, after, reviewer, UTC time, note; classification
    corrections also name the taxonomy version). Extraction corrections (text / an option / marks / type) are
    protected from later re-ingestion because the question then has a review event (see persist_records).
    A correction is NOT a verification: the status stays as it was until a human verifies."""
    if not (field in EXTRACTION_FIELDS or field in CLASSIFICATION_FIELDS or field.startswith("option:")):
        raise ValueError(f"field {field} not reviewable; allowed: {sorted(EXTRACTION_FIELDS + CLASSIFICATION_FIELDS)} "
                         "or option:<label>")
    q = s.get(Question, question_id)
    if q is None:
        raise ValueError(f"no such question {question_id}")
    if field in EXTRACTION_FIELDS or field.startswith("option:"):
        if field.startswith("option:"):
            label = field.split(":", 1)[1]
            o = s.scalar(select(Option).where(Option.question_id == question_id, Option.label == label))
            if o is None:
                raise ValueError(f"{question_id} has no option {label}")
            before, o.content = o.content, str(new_value)
        else:
            before = getattr(q, field)
            setattr(q, field, float(new_value) if field == "marks" else new_value)
        s.add(ReviewEvent(question_id=question_id, field=field,
                          before=None if before is None else str(before), after=str(new_value),
                          reviewer=reviewer, note=note))
        # an extraction correction resolves the extraction flag (the reviewer has looked at the source)
        q.needs_review = False
        q.review_reason = None
        s.flush()
        return
    c = s.scalar(select(Classification).where(Classification.question_id == question_id))
    if c is None:
        raise ValueError("no classification to correct for this question")
    _check_taxonomy_ids(s, c, field, new_value)
    tax_note = f"{note} [taxonomy {c.taxonomy_version}]".strip()
    if field == "secondary_topic_ids":
        # secondary topics are TAGS: kept as extra keys of topic_weight. Headline counts and marks use
        # primary_topic_id only, so a secondary tag can never double-count a question.
        tw = dict(c.topic_weight or {})
        before = sorted(k for k in tw if k != c.primary_topic_id)
        keep = {c.primary_topic_id: tw.get(c.primary_topic_id, 1.0)}
        for t in new_value:
            if t != c.primary_topic_id:
                keep[t] = tw.get(t, 0.0)
        c.topic_weight = keep
        c.provenance = "validated"
        s.add(ReviewEvent(question_id=question_id, field=field, before=json.dumps(before),
                          after=json.dumps(sorted(new_value)), reviewer=reviewer, note=tax_note))
        s.flush()
        return
    before = getattr(c, field)
    setattr(c, field, new_value)
    # 'validated' = a human chose this value (still NOT verified until status=verified). Such a row is never
    # replaced by a classifier rerun or a chat import (see classify._classification_target).
    c.provenance = "validated"
    note = tax_note
    # topic implies its parent section: keep the two consistent on correction
    if field == "primary_topic_id" and "." in str(new_value):
        new_section = str(new_value).split(".")[0]
        if new_section != c.section_id:
            s.add(ReviewEvent(question_id=question_id, field="section_id",
                              before=c.section_id, after=new_section,
                              reviewer=reviewer, note=note or "implied by topic correction"))
            c.section_id = new_section
    s.add(ReviewEvent(question_id=question_id, field=field,
                      before=None if before is None else str(before),
                      after=json.dumps(new_value) if isinstance(new_value, (list, dict)) else str(new_value),
                      reviewer=reviewer, note=note))
    if c.status == "verified":
        # a correction on an already-verified row IS the human's latest decision on it;
        # keep benchmark gold in step (a correction is not a verification - status untouched).
        from . import benchmark as _bm
        _bm.sync_gold_from_review(s, question_id, reviewer)
    # a classification correction does NOT clear an extraction flag (e.g. notation still to check)
    s.flush()

# ---- five-point review rubric (docs/18_HUMAN_REVIEW_AND_SCORING.md) ------------------------------------------
# NOT a GATE score and NOT model confidence: a reviewer's record of which checks passed.
RUBRIC = [
    ("source_fidelity", "Source fidelity", "text, options, diagram and notation checked against the original PDF"),
    ("key_provenance", "Answer/key provenance", "official key correctly aligned - or explicitly not available"),
    ("primary_topic", "Primary section/topic", "the primary mapping is correct"),
    ("concept_depth", "Concept depth", "concepts and secondary tags are accurate enough"),
    ("explanation", "Explanation/evidence", "what-it-tests and evidence support the mapping"),
]
RUBRIC_KEYS = [k for k, _, _ in RUBRIC]
REQUIRED_FOR_APPROVAL = ("source_fidelity", "primary_topic")

def save_rubric(s: Session, question_id: str, scores: dict, reviewer: str, note: str = "") -> dict:
    """Record a reviewer's 0/1 for each of the five checks (one ReviewEvent, field=rubric)."""
    if s.get(Question, question_id) is None:
        raise ValueError(f"no such question {question_id}")
    missing = [k for k in RUBRIC_KEYS if k not in scores]
    bad = [k for k in RUBRIC_KEYS if k in scores and scores[k] not in (0, 1)]
    if missing or bad:
        raise ValueError(f"rubric needs 0 or 1 for every check; missing {missing}, invalid {bad}")
    c = s.scalar(select(Classification).where(Classification.question_id == question_id))
    rec = {k: int(scores[k]) for k in RUBRIC_KEYS}
    rec["review_quality_score"] = sum(rec[k] for k in RUBRIC_KEYS)
    rec["taxonomy_version"] = c.taxonomy_version if c else None
    prev = latest_rubric(s, question_id)
    s.add(ReviewEvent(question_id=question_id, field="rubric", before=json.dumps(prev) if prev else None,
                      after=json.dumps(rec), reviewer=reviewer, note=note))
    s.flush()
    return rec

def latest_rubric(s: Session, question_id: str) -> dict | None:
    ev = s.scalar(select(ReviewEvent).where(ReviewEvent.question_id == question_id, ReviewEvent.field == "rubric")
                  .order_by(ReviewEvent.id.desc()).limit(1))
    return json.loads(ev.after) if ev and ev.after else None

def approval_blockers(s: Session, question_id: str) -> list[str]:
    """Why this question may NOT be verified yet ([] = it may). A saved rubric is required, and a failed
    source-fidelity or primary-topic check blocks approval."""
    r = latest_rubric(s, question_id)
    if r is None:
        return ["no review rubric saved yet: score the five checks first"]
    return [f"rubric check '{k}' failed (0)" for k in REQUIRED_FOR_APPROVAL if r.get(k) != 1]

def approval_scope(s: Session, question_id: str) -> dict:
    """What a human has actually approved, kept separate instead of one ambiguous boolean."""
    c = s.scalar(select(Classification).where(Classification.question_id == question_id))
    key = s.scalar(select(AnswerKey).where(AnswerKey.question_id == question_id))
    def last(field):
        ev = s.scalar(select(ReviewEvent).where(ReviewEvent.question_id == question_id, ReviewEvent.field == field)
                      .order_by(ReviewEvent.id.desc()).limit(1))
        return ev.after if ev else None
    return {"classification_verified": bool(c and c.status == "verified"),
            "extraction_verified": last("extraction_verified") == "true",
            "key_verified": last("key_verified") == "true",
            "key_status": "loaded" if key else "missing"}

def _record_scopes(s: Session, question_id: str, reviewer: str, note: str) -> None:
    r = latest_rubric(s, question_id) or {}
    key = s.scalar(select(AnswerKey).where(AnswerKey.question_id == question_id))
    s.add(ReviewEvent(question_id=question_id, field="extraction_verified", before=None,
                      after="true" if r.get("source_fidelity") == 1 else "false", reviewer=reviewer, note=note))
    if key is None:
        # classification-only approval: the key stays 'missing', never claimed as verified
        s.add(ReviewEvent(question_id=question_id, field="key_verified", before=None, after="false",
                          reviewer=reviewer, note="no official key loaded - key status stays missing"))
    else:
        s.add(ReviewEvent(question_id=question_id, field="key_verified", before=None,
                          after="true" if r.get("key_provenance") == 1 else "false", reviewer=reviewer, note=note))

def audit_history(s: Session, question_id: str) -> list[dict]:
    return [{"when (UTC)": e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else "", "field": e.field,
             "before": e.before, "after": e.after, "reviewer": e.reviewer, "note": e.note}
            for e in s.scalars(select(ReviewEvent).where(ReviewEvent.question_id == question_id)
                               .order_by(ReviewEvent.id))]

def review_coverage(s: Session) -> dict:
    """Numerators AND denominators (coverage of human review - not model accuracy)."""
    from sqlalchemy import func
    total_q = s.scalar(select(func.count()).select_from(Question)) or 0
    classified = s.scalar(select(func.count(func.distinct(Classification.question_id)))) or 0
    verified = s.scalar(select(func.count(func.distinct(Classification.question_id)))
                        .where(Classification.status == "verified")) or 0
    rubric_q = s.scalar(select(func.count(func.distinct(ReviewEvent.question_id))).where(ReviewEvent.field == "rubric")) or 0
    by_status = dict(s.execute(select(Classification.status, func.count()).group_by(Classification.status)).all())
    return {"questions": total_q, "classified": classified, "unclassified": total_q - classified,
            "verified": verified, "with_rubric": rubric_q, "by_status": by_status,
            "review_coverage": f"{verified}/{classified} classified questions verified by a human"}

def set_status(s: Session, question_id: str, status: str, reviewer: str, note: str = "") -> None:
    if status not in ("verified", "flagged"):
        raise ValueError("status must be verified or flagged")
    c = s.scalar(select(Classification).where(Classification.question_id == question_id))
    if c is None:
        raise ValueError("no classification for this question")
    if status == "verified":
        blockers = approval_blockers(s, question_id)
        if blockers:
            raise ValueError(f"{question_id} cannot be verified: " + "; ".join(blockers))
    s.add(ReviewEvent(question_id=question_id, field="status",
                      before=c.status, after=status, reviewer=reviewer, note=note))
    c.status = status
    c.provenance = "validated" if status == "verified" else "inferred"
    q = s.get(Question, question_id)
    if status == "verified":
        _record_scopes(s, question_id, reviewer, note)
        q.needs_review = False
        q.review_reason = None
        # v11: if this question is in the benchmark sample, the human's verified
        # label becomes that row's gold (benchmark.sync_gold_from_review; no
        # auto-approval - this runs only after the rubric gate above passed).
        from . import benchmark as _bm
        _bm.sync_gold_from_review(s, question_id, reviewer)
    else:
        q.needs_review = True
        q.review_reason = note or "flagged by reviewer"
        # v11: re-flagging un-verifies, so any benchmark gold from the earlier
        # verification is revoked - a formerly verified label must not stay scored.
        from . import benchmark as _bm
        _bm.revoke_gold(s, question_id, f"revoked: re-flagged by {reviewer}")
    s.flush()

def approve_batch(s: Session, question_ids: list[str], reviewer: str,
                  corrections: dict[str, dict] | None = None,
                  note: str = "approve queue") -> dict:
    """Batch human approval (v6). For each id: apply any correction
    ({section_id, primary_topic_id, concept_ids}), then set status=verified.
    Every decision logs a ReviewEvent, same as one-by-one approval. Questions
    without a classification are skipped (nothing to approve yet)."""
    corrections = corrections or {}
    approved = corrected = skipped = blocked = 0
    for qid in question_ids:
        c = s.scalar(select(Classification).where(Classification.question_id == qid))
        if c is None:
            skipped += 1
            continue
        if approval_blockers(s, qid):        # same rule as one-by-one: a passing rubric must exist
            blocked += 1
            continue
        for field, value in (corrections.get(qid) or {}).items():
            if value is not None and value != getattr(c, field):
                apply_decision(s, qid, field, value, reviewer, note=note)
                corrected += 1
        set_status(s, qid, "verified", reviewer, note=note)
        approved += 1
    s.flush()
    return {"approved": approved, "corrected": corrected, "skipped_unclassified": skipped,
            "blocked_no_passing_rubric": blocked}

def next_pending(s: Session, after_question_id: str | None = None) -> str | None:
    """The next question id with a suggestion awaiting a decision, after the given one
    (for 'Approve & next'); wraps to the first when at the end. Unclassified questions are
    skipped - there is nothing to approve on them."""
    queue = [r["question_id"] for r in review_queue(s, classified_only=True)]
    if not queue:
        return None
    if after_question_id in queue:
        i = queue.index(after_question_id)
        return queue[(i + 1) % len(queue)]
    return queue[0]

# Review-priority buckets, highest first. The order follows the v11 handoff: look
# hardest where the pipeline is most likely wrong, and still spot-check agreement.
PRIORITY_BUCKETS = [
    "taxonomy_gap",            # no topic exists (e.g. historical software engineering)
    "classifier_flagged",      # flagged suggestions (invalid id / low confidence / conflict)
    "low_confidence",          # suggested with confidence < 0.6
    "extraction_issue",        # OCR / extraction problems (questions.needs_review)
    "provider_disagreement",   # an independent proposal disagrees with the current label
    "suggestion",              # remaining unverified suggestions
    "unclassified",            # no classification and no taxonomy-gap note
    "verified_spotcheck",      # random 5% sample of verified rows for audit
]


def prioritized_review_queue(s: Session, limit: int | None = None,
                             include_spotcheck: bool = True,
                             seed: int = 42) -> list[dict]:
    """review_queue rows in decision order: the same population, but ordered so a
    human's first hour goes to the questions most likely to be wrong. Each row
    gains priority_bucket and priority_rank. Verified rows are excluded except a
    deterministic random 5% audit sample at the very end (include_spotcheck)."""
    rows = review_queue(s)
    gap_ids = set(s.scalars(select(ReviewEvent.question_id)
                            .where(ReviewEvent.field == "taxonomy_gap")).all())
    disagree: set[str] = set()
    props = s.scalars(select(ClassificationProposal)).all()
    labels = {c.question_id: c for c in s.scalars(select(Classification)).all()}
    for pr in props:
        lab = labels.get(pr.question_id)
        if lab is not None and pr.primary_topic_id != lab.primary_topic_id:
            disagree.add(pr.question_id)

    def bucket(r: dict) -> str:
        if r["question_id"] in gap_ids:
            return "taxonomy_gap"
        if r["status"] == "flagged":
            return "classifier_flagged"
        if r["status"] == "suggested" and (r["confidence"] or 0) < 0.6:
            return "low_confidence"
        if r["review_reason"].startswith("extraction"):
            return "extraction_issue"
        if r["question_id"] in disagree:
            return "provider_disagreement"
        if r["status"] == "suggested":
            return "suggestion"
        return "unclassified"

    for r in rows:
        r["priority_bucket"] = bucket(r)
    order = {b: i for i, b in enumerate(PRIORITY_BUCKETS)}
    rows.sort(key=lambda r: (order[r["priority_bucket"]], r["paper_id"], r["q_number"]))
    if include_spotcheck:
        import random
        ver_ids = list(s.scalars(select(Classification.question_id)
                                 .where(Classification.status == "verified")).all())
        rng = random.Random(seed)
        rng.shuffle(ver_ids)
        for vid in ver_ids[: max(1, len(ver_ids) // 20)]:
            q = s.get(Question, vid)
            c = labels.get(vid)
            rows.append({"question_id": vid, "paper_id": q.paper_id, "q_number": q.q_number,
                         "marks": q.marks, "q_type": q.q_type,
                         "review_reason": "audit spot-check of a verified row",
                         "section_id": c.section_id if c else None,
                         "primary_topic_id": c.primary_topic_id if c else None,
                         "confidence": c.confidence if c else None,
                         "status": "verified", "priority_bucket": "verified_spotcheck"})
    for i, r in enumerate(rows, 1):
        r["priority_rank"] = i
    return rows[:limit] if limit else rows

