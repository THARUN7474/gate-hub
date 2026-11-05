"""Second opinions and per-question pipeline status for the UI (read-only).

Sources, kept apart on purpose:
  * machine label  - classifications row (a suggestion until a human verifies it)
  * AI review      - review_events field='ai_review' (scripts/ai_review.py; an AI reviewer's opinion)
  * decision models- classification_proposals from openai-decisions / jev (paid, off by default)
  * human review   - classifications.status='verified' + rubric/status review_events
None of the opinions is ever human verification or benchmark gold."""
from __future__ import annotations
import json
import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import BenchmarkSample, Classification, ClassificationProposal, Question, ReviewEvent

DECISION_PROVIDERS = ("openai-decisions", "jev")


def _load(s: str | None) -> dict:
    try:
        return json.loads(s or "{}") or {}
    except ValueError:
        return {}


def ai_review_rows(s: Session) -> list[dict]:
    """One row per question: its LATEST AI-review opinion beside the current live label."""
    latest: dict[str, ReviewEvent] = {}
    for e in s.scalars(select(ReviewEvent).where(ReviewEvent.field == "ai_review").order_by(ReviewEvent.id)):
        latest[e.question_id] = e
    if not latest:
        return []
    cls = {c.question_id: c for c in s.scalars(select(Classification).where(
        Classification.question_id.in_(list(latest))))}
    qinfo = {r[0]: (r[1], r[2]) for r in s.execute(select(Question.id, Question.paper_id, Question.q_type)
                                                    .where(Question.id.in_(list(latest)))).all()}
    out = []
    for qid, e in latest.items():
        d = _load(e.after)
        c = cls.get(qid)
        paper, qtype = qinfo.get(qid, ("", None))
        out.append({"question_id": qid, "paper": paper, "verdict": d.get("verdict") or "",
                    "version": d.get("prompt_version") or "ai-review-v1",
                    "stored_type": qtype, "ai_type": d.get("question_type"),
                    "type_differs": bool(d.get("question_type") and d.get("question_type") != qtype),
                    "key_check": d.get("key_check"), "difficulty": d.get("difficulty"),
                    "why": d.get("why_this_topic") or "",
                    "ai_section": d.get("section_id"), "ai_topic": d.get("primary_topic_id"),
                    "ai_confidence": d.get("confidence"),
                    "label_topic": c.primary_topic_id if c else None,
                    "label_status": c.status if c else "unclassified",
                    "same_topic": bool(c and d.get("primary_topic_id") == c.primary_topic_id),
                    "note": d.get("note") or "", "reviewer": e.reviewer, "when": str(e.created_at)[:16]})
    out.sort(key=lambda r: ({"correct": 0, "flag": 1}.get(r["verdict"], 2), r["question_id"]))
    return out


def decision_rows(s: Session) -> list[dict]:
    rows = s.scalars(select(ClassificationProposal).where(
        ClassificationProposal.provider.in_(DECISION_PROVIDERS)).order_by(ClassificationProposal.id)).all()
    return [{"question_id": p.question_id, "provider": p.provider, "model": p.model, "topic": p.primary_topic_id,
             "probability": p.confidence, "when": str(p.created_at)[:16]} for p in rows]


def decision_status() -> list[dict]:
    """Key/enable state of each decision model - never the key itself."""
    from ..classification import decision_models as dm
    from ..settings import env_flag, load_env
    load_env()
    on = env_flag("DECISIONS_ENABLED", False)
    return [{"provider": n, "key_env": sp.key_env, "key_set": bool(os.environ.get(sp.key_env)),
             "enabled (DECISIONS_ENABLED)": on, "model": os.environ.get(sp.model_env) or sp.default_model,
             "USD per 1M input tokens": float(os.environ.get(sp.price_env) or sp.default_price_in_per_m),
             "reads images": sp.images} for n, sp in dm.SPECS.items()]


def stage_summary(s: Session) -> dict:
    """Headline counts for the Pipeline Status stage cards."""
    total = s.scalar(select(func.count()).select_from(Question)) or 0
    classified = s.scalar(select(func.count(func.distinct(Classification.question_id)))) or 0
    verified = s.scalar(select(func.count()).select_from(Classification)
                        .where(Classification.status == "verified")) or 0
    extraction = s.scalar(select(func.count()).select_from(Question)
                          .where(Question.needs_review == True)) or 0  # noqa: E712
    ai = ai_review_rows(s)
    verdicts: dict[str, int] = {}
    for r in ai:
        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
    dec = s.scalar(select(func.count(func.distinct(ClassificationProposal.question_id))).where(
        ClassificationProposal.provider.in_(DECISION_PROVIDERS))) or 0
    bench = dict(s.execute(select(BenchmarkSample.status, func.count()).group_by(BenchmarkSample.status)).all())
    v2 = sum(1 for r in ai if r["version"] == "ai-review-v2")
    from .dupes import duplicate_map
    D = duplicate_map(s)
    ext_ids = set(s.scalars(select(Question.id).where(Question.needs_review == True)))  # noqa: E712
    ext_copies = len(ext_ids & set(D["copy_of"]))
    return {"questions": total, "unique": D["unique"], "copies": len(D["copy_of"]),
            "extraction_on_originals": extraction - ext_copies, "extraction_on_copies": ext_copies,
            "classified": classified, "ai_reviewed_v2": v2, "verified": verified,
            "extraction_issues": extraction, "ai_reviewed": len(ai), "ai_verdicts": verdicts,
            "decision_questions": dec, "benchmark_total": sum(bench.values()),
            "benchmark_gold": bench.get("gold_verified", 0)}


def question_stages(s: Session, qid: str) -> dict:
    """Where one question stands in every stage, with the source of each fact."""
    q = s.get(Question, qid)
    c = s.scalar(select(Classification).where(Classification.question_id == qid))

    def last(field):
        return s.scalar(select(ReviewEvent).where(ReviewEvent.question_id == qid, ReviewEvent.field == field)
                        .order_by(ReviewEvent.id.desc()).limit(1))
    ext_ok = last("extraction_verified")
    corrected = s.scalar(select(func.count()).select_from(ReviewEvent).where(
        ReviewEvent.question_id == qid,
        (ReviewEvent.field == "text") | ReviewEvent.field.like("option:%")
        | (ReviewEvent.field == "q_type") | (ReviewEvent.field == "marks"))) or 0
    if q.needs_review:
        extraction = ("needs a check", "orange", q.review_reason or "flagged by the extractor")
    elif ext_ok is not None and ext_ok.after == "true":
        extraction = ("confirmed by a human", "green", f"by {ext_ok.reviewer}")
    else:
        extraction = ("no issue found", "gray", "automatic checks passed - not yet confirmed by a human")
    if corrected:
        extraction = (extraction[0], extraction[1], extraction[2] + f" · {corrected} field correction(s) saved")
    src = "OCR (scanned PDF)" if q.extraction_status == "ocr" else "digital PDF text"

    if c is None:
        machine = ("no label", "gray", "not classified yet")
    else:
        origin = (c.model or "unknown model")
        if origin.startswith("ai-review:"):
            origin = "created by the AI reviewer (" + origin.split(":", 1)[1] + ")"
        machine = ({"verified": "verified", "flagged": "flagged", "suggested": "suggestion"}.get(c.status, c.status),
                   {"verified": "green", "flagged": "orange"}.get(c.status, "blue"),
                   f"{origin} · confidence {c.confidence:.2f}" if c.confidence is not None else origin)

    ai = ai_review_rows_for(s, qid)
    if ai:
        r = ai[-1]
        aiv = (r["verdict"], {"agree": "green", "flag": "orange", "correct": "red"}.get(r["verdict"], "gray"),
               f"{r['reviewer'].split(' ')[0]} · {r['when']}")
    else:
        aiv = ("not reviewed", "gray", "no AI-review opinion recorded")

    dec = [p for p in s.scalars(select(ClassificationProposal).where(
        ClassificationProposal.question_id == qid, ClassificationProposal.provider.in_(DECISION_PROVIDERS)))]
    decv = ((f"{len(dec)} opinion(s)", "violet", ", ".join(f"{p.provider}: {p.primary_topic_id} "
                                                            f"({(p.confidence or 0):.2f})" for p in dec))
            if dec else ("not run", "gray", "paid, off by default - run on the benchmark after gold exists"))

    st_ev = s.scalar(select(ReviewEvent).where(ReviewEvent.question_id == qid, ReviewEvent.field == "status")
                     .order_by(ReviewEvent.id.desc()).limit(1))
    bm = s.scalar(select(BenchmarkSample).where(BenchmarkSample.question_id == qid))
    if c is not None and c.status == "verified":
        human = ("verified", "green", f"by {st_ev.reviewer}" if st_ev else "verified")
    else:
        human = ("not yet", "gray", "waiting for your decision")
    if bm is not None:
        human = (human[0], human[1], human[2] + (" · benchmark gold" if bm.status == "gold_verified"
                                                 else " · in the benchmark sample"))
    t_ev = s.scalar(select(ReviewEvent).where(ReviewEvent.question_id == qid, ReviewEvent.field == "q_type")
                    .order_by(ReviewEvent.id.desc()).limit(1))
    ai_t = next((r.get("question_type") for r in reversed(ai) if r.get("question_type")), None)
    qtype = {"stored": q.q_type, "ai": ai_t, "ai_differs": bool(ai_t and ai_t != q.q_type),
             "human": (t_ev.after, t_ev.reviewer) if t_ev is not None else None}
    return {"qtype": qtype, "extraction": extraction, "text_source": src, "machine": machine, "ai_review": aiv,
            "decision_models": decv, "human": human, "ai_rows": ai, "decision_rows": dec}


def ai_review_rows_for(s: Session, qid: str) -> list[dict]:
    out = []
    for e in s.scalars(select(ReviewEvent).where(ReviewEvent.question_id == qid, ReviewEvent.field == "ai_review")
                       .order_by(ReviewEvent.id)):
        d = _load(e.after)
        out.append({**d, "reviewer": e.reviewer, "when": str(e.created_at)[:16], "verdict": d.get("verdict") or "",
                    "version": d.get("prompt_version") or "ai-review-v1",
                    "section_id": d.get("section_id"), "primary_topic_id": d.get("primary_topic_id"),
                    "confidence": d.get("confidence"), "note": d.get("note") or ""})
    return out


def ready_to_approve(s: Session) -> set[str]:
    """Question ids whose LATEST saved review checks pass the two required checks."""
    from ..validation.review import REQUIRED_FOR_APPROVAL
    latest: dict[str, dict] = {}
    for qid, after in s.execute(select(ReviewEvent.question_id, ReviewEvent.after)
                                .where(ReviewEvent.field == "rubric").order_by(ReviewEvent.id)):
        latest[qid] = _load(after)
    return {q for q, r in latest.items() if all(r.get(k) == 1 for k in REQUIRED_FOR_APPROVAL)}

