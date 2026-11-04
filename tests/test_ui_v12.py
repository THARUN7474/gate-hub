"""v12 UI + legacy-section regressions."""
import re
from pathlib import Path

import yaml

from src.analytics import analyze as az
from src.db.models import Classification, Paper, Question

ROOT = Path(__file__).resolve().parents[1]


def test_no_bare_dollar_in_app_text():
    """A '$' in a widget label or markdown is parsed as LaTeX; '$/M tokens' froze the browser on the LLM
    Classify screen (5 Nov 2026). Write 'USD' instead."""
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    bad = [ln for ln in src.splitlines() if re.search(r"\$[0-9A-Za-z/]", ln) and not ln.lstrip().startswith("#")]
    assert not bad, bad


def test_legacy_section_is_historical_and_valid():
    tax = yaml.safe_load((ROOT / "taxonomy.yaml").read_text(encoding="utf-8"))
    leg = next(s for s in tax["sections"] if s["id"] == "LEGACY")
    assert leg["provenance"] == "historical" and "2027" in leg["name"]
    assert [t["id"] for t in leg["topics"]] == ["LEGACY.SE"]
    assert all(c["id"].startswith("LEGACY.SE.") for c in leg["topics"][0]["concepts"])


def test_paper_review_table_counts(db_url):
    from src.db.session import make_session
    with make_session(db_url) as session:
        _check(session)


def _check(session):
    session.add(Paper(id="P-1", year=2020, session="CS-1", reconciled=True))
    for n in range(1, 4):
        session.add(Question(id=f"P-1-Q{n}", paper_id="P-1", q_number=n, text="t", marks=1.0, q_type="MCQ"))
    session.flush()
    for n, st in ((1, "verified"), (2, "flagged")):
        session.add(Classification(question_id=f"P-1-Q{n}", taxonomy_version="t", section_id="OS",
                                   primary_topic_id="OS.MEM", confidence=0.9, provenance="inferred", status=st,
                                   model="m", prompt_version="v"))
    session.flush()
    row = next(r for r in az.paper_review_table(session) if r["paper"] == "P-1")
    assert row["questions"] == 3 and row["verified"] == 1 and row["flagged"] == 1 and row["suggested"] == 0
    assert abs(row["verified_share"] - 1 / 3) < 1e-3
