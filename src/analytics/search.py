"""Question search. PostgreSQL: tsvector + plainto_tsquery over the generated
search_tsv column (GIN-indexed by migration 0001). SQLite fallback: LIKE.
Structured filters (year/session/marks/type/status) stay B-tree indexed."""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db.models import Classification, Paper, Question

def search_questions(s: Session, text_query: str | None = None, years: list[int] | None = None,
                     section_id: str | None = None, topic_id: str | None = None,
                     q_type: str | None = None, needs_review: bool | None = None,
                     status: str | None = None, limit: int | None = None,
                     extraction_issue: bool | None = None) -> list[dict]:
    """limit=None returns every match (the bank is ~2k rows). extraction_issue filters on
    questions.needs_review directly; needs_review keeps its older, broader 'anything unreviewed' meaning."""
    q = (select(Question, Paper, Classification)
         .join(Paper, Paper.id == Question.paper_id)
         .outerjoin(Classification, Classification.question_id == Question.id))
    if years:
        q = q.where(Paper.year.in_(years))
    if q_type:
        q = q.where(Question.q_type == q_type)
    if needs_review is not None:
        if needs_review:
            from ..validation.review import unreviewed_condition
            q = q.where(unreviewed_condition())
        else:
            q = q.where(Question.needs_review == False)  # noqa: E712
    if extraction_issue is not None:
        q = q.where(Question.needs_review == extraction_issue)
    if section_id:
        q = q.where(Classification.section_id == section_id)
    if topic_id:
        q = q.where(Classification.primary_topic_id == topic_id)
    if status:
        q = q.where(Classification.status == status)
    if text_query:
        if s.bind.dialect.name == "postgresql":
            from sqlalchemy import func, literal_column
            q = q.where(literal_column("questions.search_tsv").op("@@")(
                func.plainto_tsquery("english", text_query)))
        else:
            q = q.where(Question.like(f"%{text_query}%")) if False else q.where(Question.text.like(f"%{text_query}%"))
    q = q.order_by(Paper.year, Question.q_number)
    if limit:
        q = q.limit(limit)
    out = []
    for question, paper, cls in s.execute(q):
        out.append({
            "id": question.id, "year": paper.year, "session": paper.session,
            "q_number": question.q_number, "marks": question.marks, "q_type": question.q_type,
            "section_id": cls.section_id if cls else None,
            "primary_topic_id": cls.primary_topic_id if cls else None,
            "confidence": cls.confidence if cls else None,
            "status": cls.status if cls else None,
            "needs_review": question.needs_review})
    return out
