"""CSV/JSON exports. Every row comes from the live database - exports match
queries, never hand-built numbers."""
from __future__ import annotations
import csv, json
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db.models import (AnswerKey, Classification, ConceptPrerequisite,
                         Option, Paper, Question, TaxonomyNode)
from . import analyze as az
from ..validation.validate import run_checks

def export_all(s: Session, out_dir: str | Path = "exports",
               year_from: int = 2012, year_to: int = 2026) -> dict:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    written = []

    def w_csv(name: str, header: list[str], rows) -> None:
        with open(out / name, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(header); w.writerows(rows)
        written.append(name)

    qs = s.execute(select(Question, Paper).join(Paper, Paper.id == Question.paper_id)
                   .order_by(Paper.year, Paper.session, Question.q_number))
    w_csv("questions.csv",
          ["question_id", "year", "session", "q_number", "marks", "q_type",
           "page_start", "page_end", "needs_review", "text"],
          [[q.id, p.year, p.session, q.q_number, q.marks, q.q_type,
            q.page_start, q.page_end, q.needs_review, (q.text or "")[:500]] for q, p in qs])

    cs = s.execute(select(Classification, Question, Paper)
                   .join(Question, Question.id == Classification.question_id)
                   .join(Paper, Paper.id == Question.paper_id)
                   # deterministic on every backend (SQLite and PostgreSQL order differently otherwise)
                   .order_by(Paper.year, Paper.session, Question.q_number, Classification.id))
    w_csv("classifications.csv",
          ["question_id", "year", "section_id", "primary_topic_id", "concept_ids",
           "confidence", "status", "provenance", "model", "prompt_version"],
          [[c.question_id, p.year, c.section_id, c.primary_topic_id,
            json.dumps(c.concept_ids or []), c.confidence, c.status, c.provenance,
            c.model, c.prompt_version] for c, q, p in cs])

    m = az.section_year_matrix(s, year_from, year_to)
    years = m["years"]
    w_csv("year_subject_matrix.csv", ["section"] + [str(y) for y in years] + ["total_marks"],
          [[sec] + [d["years"].get(y, {}).get("marks", "") for y in years] + [d["total_marks"]]
           for sec, d in m["sections"].items()])

    tym = az.topic_year_matrix(s, None, year_from, year_to)
    w_csv("year_topic_matrix.csv", ["topic", "year", "questions", "marks"],
          [[r["topic"], r["year"], r["questions"], r["marks"]] for r in tym])

    w_csv("topic_summary.csv", ["topic", "weighted_marks", "share"],
          [[r["topic"], r["weighted_marks"], r["share"]] for r in az.priority_ranking(s, year_from, year_to)])

    concepts = s.scalars(select(TaxonomyNode).where(TaxonomyNode.level == "concept")
                         .order_by(TaxonomyNode.version, TaxonomyNode.node_id)).all()
    w_csv("concepts.csv", ["concept_id", "parent_id", "name", "provenance"],
          [[c.node_id, c.parent_id, c.name, c.provenance] for c in concepts])

    edges = s.scalars(select(ConceptPrerequisite)
                      .order_by(ConceptPrerequisite.concept_id, ConceptPrerequisite.required_concept_id)).all()
    w_csv("prerequisite_edges.csv", ["concept_id", "required_concept_id", "provenance"],
          [[e.concept_id, e.required_concept_id, e.provenance] for e in edges])

    report = {"coverage": az.coverage_report(s), "checks": run_checks(s)}
    (out / "validation_report.json").write_text(json.dumps(report, indent=2, default=str))
    written.append("validation_report.json")
    return {"dir": str(out), "files": written}
