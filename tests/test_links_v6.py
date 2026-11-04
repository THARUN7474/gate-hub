"""Clickable navigation helpers + dev schema upgrade (v6)."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect, text
from src.analytics import analyze as az, links as nav
from src.db import dev_upgrade
from src.db.session import init_schema, make_engine, make_session

def test_matrix_html_cells_are_links():
    m = {"years": [2024], "sections": {"ALGO": {"years": {2024: {"questions": 3, "marks": 5.0}},
                                                "total_q": 3, "total_marks": 5.0}}}
    html = nav.matrix_html(m)
    assert 'href="?drill_sec=ALGO&amp;drill_year=2024"' in html or \
           'href="?drill_sec=ALGO&drill_year=2024"' in html
    assert ">5</a>" in html
    assert "<script" not in html

def test_matrix_html_escapes_values():
    m = {"years": [2024], "sections": {'<img src=x>': {"years": {2024: {"questions": 1, "marks": 1.0}},
                                                       "total_q": 1, "total_marks": 1.0}}}
    html = nav.matrix_html(m)
    assert "<img src=x>" not in html and "%3Cimg" in html

def test_parse_drill_params():
    assert nav.parse_drill_params({"drill_sec": "ALGO", "drill_year": "2024"}) == ("ALGO", 2024)
    assert nav.parse_drill_params({"drill_sec": "ALGO"}) == (None, None)
    assert nav.parse_drill_params({"drill_sec": "ALGO", "drill_year": "not-a-year"}) == (None, None)
    assert nav.parse_drill_params({}) == (None, None)

def test_drill_list_links_to_review():
    html = nav.drill_list_html(["GATE-CS-2024-S1-Q01"])
    assert "?review_q=GATE-CS-2024-S1-Q01" in html

def test_dev_upgrade_adds_columns_and_backfills(blank_db):
    url = blank_db  # fresh schema already has the columns
    out = dev_upgrade.upgrade_classifications_table(url)
    assert out["added"] == [] and out["backfilled"] == 0
    # idempotent on second run
    assert dev_upgrade.upgrade_classifications_table(url)["added"] == []

@pytest.mark.sqlite_only
def test_dev_upgrade_on_old_schema(tmp_path):
    """Simulate a pre-v6 DB: create schema without the new columns, one old
    classification row, then upgrade."""
    url = f"sqlite:///{tmp_path}/old.db"
    eng = make_engine(url)
    with eng.begin() as con:
        con.execute(text(
            "CREATE TABLE classifications (id INTEGER PRIMARY KEY, question_id TEXT, "
            "run_id INTEGER, taxonomy_version TEXT, section_id TEXT, primary_topic_id TEXT, "
            "topic_weight JSON, concept_ids JSON, what_it_tests TEXT, prerequisite_ids JSON, "
            "confidence FLOAT, evidence_quote TEXT, raw_response JSON, provenance TEXT, "
            "status TEXT, model TEXT, prompt_version TEXT, classified_at DATETIME)"))
        con.execute(text(
            "INSERT INTO classifications (question_id, taxonomy_version, section_id, "
            "primary_topic_id, confidence, status, model, prompt_version) VALUES "
            "('Q1', 'gate-cs-2027', 'ALGO', 'ALGO.SORT', 0.8, 'suggested', 'm', 'v1')"))
    out = dev_upgrade.upgrade_classifications_table(url)
    assert set(out["added"]) == {"agreement", "combo_score", "provider_votes", "provider_count"}
    assert out["backfilled"] == 1
    with make_session(url) as s:
        row = s.execute(text("SELECT agreement, combo_score, provider_count FROM classifications")).fetchone()
    assert row == (None, None, 0)  # legacy: agreement/combo NULL, no provider run recorded
