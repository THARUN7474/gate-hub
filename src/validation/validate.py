"""Data-quality checks. A failing check is a finding with details, not a
silent pass. These mirror the definition-of-done tests in docs/04_CHECKLISTS."""
from __future__ import annotations
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..db.models import (AnswerKey, Classification, ConceptPrerequisite, Option,
                         Paper, Question, TaxonomyNode)

def run_checks(s: Session) -> list[dict]:
    checks = []
    def add(name, ok, details=""):
        checks.append({"check": name, "ok": bool(ok), "details": details})

    dup = s.scalar(select(Question.paper_id, Question.q_number, func.count())
                   .group_by(Question.paper_id, Question.q_number)
                   .having(func.count() > 1).limit(1))
    add("no duplicate (paper, q_number)", dup is None)

    orphans = s.scalar(select(func.count()).select_from(Question)
                       .where(~Question.paper_id.in_(select(Paper.id))))
    add("no orphan questions", orphans == 0, f"{orphans} orphans")

    # A NULL marks/type is acceptable ONLY when the question is routed to review (needs_review): the
    # extractor never guesses, e.g. an OCR page where one option label was not read. Unflagged NULLs fail.
    null_cond = (Question.marks.is_(None)) | (Question.q_type.is_(None))
    unflagged = s.scalar(select(func.count()).select_from(Question)
                         .where(null_cond & (Question.needs_review == False)))  # noqa: E712
    flagged = s.scalar(select(func.count()).select_from(Question)
                       .where(null_cond & (Question.needs_review == True)))  # noqa: E712
    add("no unexplained NULL marks/type", unflagged == 0,
        f"{unflagged} unflagged NULL (must be 0); {flagged} NULL questions are flagged for review")

    valid_ids = {n.node_id for n in s.scalars(select(TaxonomyNode))}
    bad = [c.question_id for c in s.scalars(select(Classification))
           if c.primary_topic_id not in valid_ids or c.section_id not in valid_ids]
    add("all classification IDs exist in taxonomy", not bad, f"{len(bad)} invalid: {bad[:5]}")

    unreconciled = [p.id for p in s.scalars(select(Paper)) if not p.reconciled]
    add("all papers reconciled to manifests", not unreconciled, ", ".join(unreconciled))

    # Matrix totals must equal paper totals (no double counting). A question with
    # NO classification (e.g. a deliberate taxonomy gap) is absent from the matrix by
    # design: it is reported as unclassified marks, not hidden and not a failure.
    # Failure = a question counted twice, or classified + unclassified != paper total.
    papers = s.scalars(select(Paper)).all()
    mismatch, unclassified_note = [], []
    for p in papers:
        derived = p.derived_marks or 0
        classified_marks = s.scalar(
            select(func.coalesce(func.sum(Question.marks), 0))
            .join(Classification, Classification.question_id == Question.id)
            .where(Question.paper_id == p.id)) or 0
        n_cls = s.scalar(select(func.count()).select_from(Classification)
                         .join(Question, Question.id == Classification.question_id)
                         .where(Question.paper_id == p.id))
        n_cls_q = s.scalar(select(func.count(func.distinct(Classification.question_id)))
                           .join(Question, Question.id == Classification.question_id)
                           .where(Question.paper_id == p.id))
        unclassified_marks = s.scalar(
            select(func.coalesce(func.sum(Question.marks), 0))
            .where(Question.paper_id == p.id,
                   ~Question.id.in_(select(Classification.question_id)))) or 0
        if not n_cls:
            continue
        if n_cls != n_cls_q or abs(classified_marks + unclassified_marks - derived) > 1e-9:
            mismatch.append(p.id)
        elif unclassified_marks:
            unclassified_note.append(f"{p.id} {unclassified_marks:g}")
    detail = ", ".join(mismatch) if mismatch else (
        "unclassified marks (outside the matrix, by design): " + "; ".join(unclassified_note)
        if unclassified_note else "")
    add("matrix totals equal paper totals", not mismatch, detail)

    active_ids = {n.node_id for n in s.scalars(
        select(TaxonomyNode).where(TaxonomyNode.deprecated == False))}  # noqa: E712
    bad_concepts = []
    deprecated_refs = []
    for c in s.scalars(select(Classification)):
        for cid in (c.concept_ids or []):
            if cid not in valid_ids:
                bad_concepts.append((c.question_id, cid))
        if c.primary_topic_id not in active_ids or c.section_id not in active_ids:
            deprecated_refs.append(c.question_id)
    add("all concept_ids exist in taxonomy", not bad_concepts,
        f"{len(bad_concepts)} invalid: {bad_concepts[:5]}")
    add("no classification points at a deprecated node", not deprecated_refs,
        f"{len(deprecated_refs)}: {deprecated_refs[:5]}")

    empty_opts = s.scalars(select(Option).where(Option.content == "")).all()
    unflagged_empty = [o.question_id for o in empty_opts
                       if not s.get(Question, o.question_id).needs_review]
    add("empty (figure-only) options are flagged for review", not unflagged_empty,
        f"{len(unflagged_empty)} unflagged: {unflagged_empty[:5]}")

    edges = s.scalars(select(ConceptPrerequisite)).all()
    dangling = [(e.concept_id, e.required_concept_id) for e in edges
                if e.concept_id not in valid_ids or e.required_concept_id not in valid_ids]
    add("prerequisite edges reference known concepts", not dangling,
        f"{len(dangling)} dangling: {dangling[:5]}")
    return checks
