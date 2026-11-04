"""SQL-backed analytics. Every aggregate derives from question records using
primary_topic_id only, so matrix totals always reconcile with paper totals
(no double counting). Every matrix cell can drill down to its contributing
questions. Outputs are historical description, never prediction."""
from __future__ import annotations
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..db.models import AnswerKey, Classification, Paper, Question, TaxonomyNode

def section_year_matrix(s: Session, year_from: int = 2012, year_to: int = 2026,
                        verified_only: bool = False) -> dict:
    q = (select(Classification.section_id, Paper.year,
                func.count().label("questions"), func.coalesce(func.sum(Question.marks), 0).label("marks"))
         .join(Question, Question.id == Classification.question_id)
         .join(Paper, Paper.id == Question.paper_id)
         .where(Paper.year.between(year_from, year_to))
         .group_by(Classification.section_id, Paper.year)
         .order_by(Classification.section_id, Paper.year))
    if verified_only:
        q = q.where(Classification.status == "verified")
    years: set[int] = set()
    sections: dict[str, dict] = {}
    for sec, yr, qc, marks in s.execute(q):
        years.add(yr)
        d = sections.setdefault(sec, {"years": {}, "total_q": 0, "total_marks": 0.0})
        d["years"][yr] = {"questions": qc, "marks": float(marks)}
        d["total_q"] += qc; d["total_marks"] += float(marks)
    return {"window": [year_from, year_to], "years": sorted(years),
            "sections": sections, "verified_only": verified_only}

def drill_down(s: Session, section_id: str, year: int) -> list[str]:
    """The exact questions contributing to one matrix cell."""
    q = (select(Question.id)
         .join(Paper, Paper.id == Question.paper_id)
         .join(Classification, Classification.question_id == Question.id)
         .where(Classification.section_id == section_id, Paper.year == year)
         .order_by(Question.q_number))
    return list(s.scalars(q))

def topic_year_matrix(s: Session, section_id: str | None = None,
                      year_from: int = 2012, year_to: int = 2026) -> list[dict]:
    q = (select(Classification.primary_topic_id, Paper.year,
                func.count().label("questions"), func.coalesce(func.sum(Question.marks), 0).label("marks"))
         .join(Question, Question.id == Classification.question_id)
         .join(Paper, Paper.id == Question.paper_id)
         .where(Paper.year.between(year_from, year_to))
         .group_by(Classification.primary_topic_id, Paper.year)
         .order_by(Classification.primary_topic_id, Paper.year))
    if section_id:
        q = q.where(Classification.section_id == section_id)
    return [{"topic": t, "year": y, "questions": qc, "marks": float(m)}
            for t, y, qc, m in s.execute(q)]

def type_marks_mix(s: Session, year_from: int = 2012, year_to: int = 2026) -> list[dict]:
    q = (select(Question.q_type, Question.marks, func.count().label("n"))
         .join(Paper, Paper.id == Question.paper_id)
         .where(Paper.year.between(year_from, year_to))
         .group_by(Question.q_type, Question.marks)
         .order_by(Question.q_type, Question.marks))
    return [{"q_type": t or "UNKNOWN", "marks": m, "questions": n} for t, m, n in s.execute(q)]

def priority_ranking(s: Session, year_from: int = 2012, year_to: int = 2026,
                     recent_from: int = 2021) -> list[dict]:
    """Score-first order: historical marks share with a recency bump, per
    topic. Assumptions are explicit; this is descriptive, not predictive.
    Foundation-first order needs curated prerequisite edges (Day 3+), so it is
    not fabricated here."""
    recency_w = 1.5
    rows = topic_year_matrix(s, None, year_from, year_to)
    agg: dict[str, float] = {}
    for r in rows:
        w = recency_w if r["year"] >= recent_from else 1.0
        agg[r["topic"]] = agg.get(r["topic"], 0.0) + r["marks"] * w
    total = sum(agg.values()) or 1.0
    return [{"topic": t, "weighted_marks": round(v, 1), "share": round(v / total, 4)}
            for t, v in sorted(agg.items(), key=lambda kv: -kv[1])]

def paper_status_table(s: Session) -> list[dict]:
    """One row per paper for the Pipeline Status screen: what is loaded, how well it reconciles,
    whether a key exists, how much is OCR text, and where classification/review stands."""
    from sqlalchemy import case
    papers = s.scalars(select(Paper).order_by(Paper.year, Paper.session)).all()
    qagg = {r[0]: r[1:] for r in s.execute(
        select(Question.paper_id, func.count(), func.coalesce(func.sum(Question.marks), 0),
               func.sum(case((Question.needs_review == True, 1), else_=0)),   # noqa: E712
               func.sum(case((Question.extraction_status == "ocr", 1), else_=0)))
        .group_by(Question.paper_id))}
    keys = dict(s.execute(select(Question.paper_id, func.count()).join(AnswerKey, AnswerKey.question_id == Question.id)
                          .group_by(Question.paper_id)).all())
    cls = {r[0]: r[1:] for r in s.execute(
        select(Question.paper_id, func.count(func.distinct(Classification.question_id)),
               func.count(func.distinct(case((Classification.status == "verified", Classification.question_id)))))
        .join(Classification, Classification.question_id == Question.id).group_by(Question.paper_id))}
    out = []
    for p in papers:
        nq, marks, flagged, ocr = qagg.get(p.id, (0, 0, 0, 0))
        classified, verified = cls.get(p.id, (0, 0))
        out.append({"paper": p.id, "year": p.year, "session": p.session, "set": p.paper_code or "",
                    "questions": nq, "marks": float(marks or 0), "reconciled": "yes" if p.reconciled else "NO",
                    "official_keys": keys.get(p.id, 0), "text_source": ("OCR" if ocr and ocr == nq else
                                                                         f"OCR {ocr}/{nq}" if ocr else "digital"),
                    "needs_review": int(flagged or 0), "classified": classified, "verified": verified})
    return out

def papers_per_year(s: Session, classified_only: bool = True) -> dict[int, int]:
    """Number of distinct (classified) papers contributing to each year - the divisor for the
    'average over sessions' view, because a year with 4 sessions otherwise shows 4x the marks."""
    q = select(Paper.year, func.count(func.distinct(Paper.id))).join(Question, Question.paper_id == Paper.id)
    if classified_only:
        q = q.join(Classification, Classification.question_id == Question.id)
    return dict(s.execute(q.group_by(Paper.year)).all())

def averaged_matrix(m: dict, per_year: dict[int, int]) -> dict:
    """Display copy of a section_year_matrix with every cell divided by that year's paper count."""
    out = {"window": m["window"], "years": m["years"], "verified_only": m.get("verified_only", False), "sections": {}}
    for sec, d in m["sections"].items():
        yrs = {y: {"questions": round(c["questions"] / max(per_year.get(y, 1), 1), 2),
                   "marks": round(c["marks"] / max(per_year.get(y, 1), 1), 2)} for y, c in d["years"].items()}
        out["sections"][sec] = {"years": yrs, "total_q": round(sum(v["questions"] for v in yrs.values()), 2),
                                "total_marks": round(sum(v["marks"] for v in yrs.values()), 2)}
    return out

def coverage_report(s: Session) -> dict:
    papers = s.scalars(select(Paper).order_by(Paper.year, Paper.session)).all()
    q_total = s.scalar(select(func.count()).select_from(Question))
    keyed = s.scalar(select(func.count()).select_from(AnswerKey))
    classified = s.scalar(select(func.count(func.distinct(Classification.question_id))))
    verified = s.scalar(select(func.count(func.distinct(Classification.question_id))).where(Classification.status == "verified"))
    flagged = s.scalar(select(func.count(func.distinct(Classification.question_id))).where(Classification.status == "flagged"))
    extraction_issues = s.scalar(select(func.count()).select_from(Question).where(Question.needs_review == True))  # noqa: E712
    unclassified = s.scalar(select(func.count()).select_from(Question)
                            .where(~Question.id.in_(select(Classification.question_id))))
    pending_review = (q_total - verified) if q_total else 0
    return {
        "papers": len(papers),
        "papers_list": [{"paper_id": p.id, "year": p.year, "session": p.session,
                         "derived_questions": p.derived_questions,
                         "reconciled": bool(p.reconciled)} for p in papers],
        "questions": q_total, "with_keys": keyed, "classified": classified,
        "verified_by_human": verified, "flagged": flagged,
        "pending_review": pending_review, "of_which_extraction_issues": extraction_issues,
        "of_which_unclassified": unclassified,
        "unreconciled_papers": [p.id for p in papers if not p.reconciled],
        "note": "Coverage is measured, not asserted. Unreconciled papers and "
                "review items must be resolved before any number is published."}

def matrix_markdown(s: Session, year_from: int = 2012, year_to: int = 2026) -> str:
    m = section_year_matrix(s, year_from, year_to)
    lines = [f"## Section x Year (marks, primary topic only) [window {year_from}-{year_to}]", ""]
    header = "| Section | " + " | ".join(str(y) for y in m["years"]) + " | Total marks |"
    lines += [header, "|" + "---|" * (len(m["years"]) + 2)]
    for sec, d in m["sections"].items():
        cells = [str(d["years"].get(y, {}).get("marks", "")) for y in m["years"]]
        lines.append(f"| {sec} | " + " | ".join(cells) + f" | {d['total_marks']:g} |")
    lines.append("")
    lines.append("Historical description only. Not a prediction for any future paper.")
    return "\n".join(lines)
