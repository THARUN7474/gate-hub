"""Evidence script for the PostgreSQL 17 + pgvector end-to-end check (docs/14).

    GATE_DB_URL=postgresql+psycopg://... python scripts/verify_postgres.py

Read-only. Prints PASS/FAIL per check and exits non-zero on any failure.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import func, select, text  # noqa: E402
from src.analytics import analyze as az  # noqa: E402
from src.analytics.search import search_questions  # noqa: E402
from src.db.models import Classification, Paper, Question, ReviewEvent  # noqa: E402
from src.db.session import make_session, get_url  # noqa: E402
from src.validation import validate as vd  # noqa: E402

results: list[tuple[bool, str]] = []
def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, label))
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  [{detail}]" if detail else ""))

def main() -> int:
    url = get_url()
    if not url.startswith("postgresql"):
        print("GATE_DB_URL is not PostgreSQL - nothing to verify", file=sys.stderr); return 2
    with make_session() as s:
        ver = s.execute(text("select version()")).scalar()
        check(ver.startswith("PostgreSQL 17"), "server is PostgreSQL 17", ver.split(" on ")[0])
        ext = dict(s.execute(text("select extname, extversion from pg_extension")).all())
        check("vector" in ext, "pgvector extension installed", f"vector {ext.get('vector')}")
        gen = s.execute(text("select is_generated from information_schema.columns "
                             "where table_name='questions' and column_name='search_tsv'")).scalar()
        check(gen == "ALWAYS", "questions.search_tsv is a generated tsvector column")
        idx = s.execute(text("select indexdef from pg_indexes where indexname='ix_questions_fts'")).scalar()
        check(bool(idx) and "gin" in idx.lower(), "GIN index ix_questions_fts exists")
        head = s.execute(text("select version_num from alembic_version")).scalar()
        check(head is not None, "alembic_version stamped", str(head))

        # validation suite
        checks = vd.run_checks(s)
        bad = [c["check"] for c in checks if not c["ok"]]
        check(not bad, f"validate: {len(checks)} checks", "all pass" if not bad else f"FAILING: {bad}")

        # analytics invariants (marks per cell vs question count are DIFFERENT numbers)
        m = az.section_year_matrix(s, 1990, 2100)
        paper_marks: dict[int, float] = {}
        for pid, yr, marks in s.execute(
                select(Paper.id, Paper.year, func.coalesce(func.sum(Question.marks), 0))
                .join(Question, Question.paper_id == Paper.id)
                .where(Question.id.in_(select(Classification.question_id)))
                .group_by(Paper.id, Paper.year)):
            paper_marks[yr] = paper_marks.get(yr, 0.0) + float(marks)
        for yr in m["years"]:
            cell_sum = sum(d["years"].get(yr, {}).get("marks", 0.0) for d in m["sections"].values())
            check(abs(cell_sum - paper_marks.get(yr, 0.0)) < 1e-9,
                  f"matrix marks for {yr} equal classified paper marks", f"{cell_sum} == {paper_marks.get(yr)}")
        bad_cells = []
        for sec, d in m["sections"].items():
            for yr, cell in d["years"].items():
                n = len(az.drill_down(s, sec, yr))
                if n != cell["questions"]:
                    bad_cells.append((sec, yr, n, cell["questions"]))
        check(not bad_cells, "every drill-down lists exactly the cell's question count", str(bad_cells[:3]))

        # real full-text search (tsvector + plainto_tsquery), compared to a LIKE baseline
        hits = search_questions(s, text_query="graph")
        like = s.scalar(select(func.count()).select_from(Question).where(Question.text.ilike("%graph%")))
        check(len(hits) > 0, "FTS query 'graph' returns rows via search_questions()", f"{len(hits)} hits (ILIKE substring: {like})")
        plan = s.execute(text("set local enable_seqscan = off")) and s.execute(text(
            "explain select id from questions where search_tsv @@ plainto_tsquery('english','graph')")).all()
        uses_gin = any("ix_questions_fts" in r[0] for r in plan)
        check(uses_gin, "planner can use the GIN index for FTS (seqscan disabled for the probe)")
        s.rollback()

        counts = {
            "papers": s.scalar(select(func.count()).select_from(Paper)),
            "questions": s.scalar(select(func.count()).select_from(Question)),
            "classifications": s.scalar(select(func.count()).select_from(Classification)),
            "verified": s.scalar(select(func.count()).select_from(Classification).where(Classification.status == "verified")),
            "review_events": s.scalar(select(func.count()).select_from(ReviewEvent)),
        }
        print("COUNTS", counts)
    fails = [l for ok, l in results if not ok]
    print(f"\n{len(results) - len(fails)}/{len(results)} checks passed")
    return 1 if fails else 0

if __name__ == "__main__":
    raise SystemExit(main())
