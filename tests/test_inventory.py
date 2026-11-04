"""Data inventory (About the Data screen): numbers come from the real manifest and the database."""
import pytest
from src.analytics import inventory as inv
from src.db.session import make_session

def test_inventory_matches_the_registry():
    r = inv.inventory()                                       # manifest + raw folder only, no database
    T = r["totals"]
    assert T["years"] == 20 and T["papers"] == 33 and T["active_papers"] == 29 and T["deferred_papers"] == 4
    assert T["active_with_key"] + T["active_without_key"] == 29 and T["expected_questions_active"] == 29 * 65
    assert [g["years"] for g in r["groups"]] == ["2007-2010", "2011-2020", "2021-2026"]
    assert sum(g["papers (sessions)"] for g in r["groups"]) == 33
    by_year = {y["year"]: y for y in r["years"]}
    assert by_year[2013]["papers (sessions)"] == 4 and by_year[2013]["how bundled"] == "1 PDF, 4 sessions inside"
    assert by_year[2021]["how bundled"] == "1 PDF, 2 sessions inside" and by_year[2021]["keys"].startswith("separate key PDF")
    assert by_year[2012]["keys"] == "inside the question PDF" and by_year[2011]["keys"] == "none"
    assert by_year[2017]["keys"] == "1 of 2 sessions keyed"
    assert all(by_year[y]["status"] == "deferred" for y in (2007, 2008, 2009, 2010))
    assert all(p["key_source"] for p in r["papers"])

def test_inventory_counts_what_the_database_holds(loaded):
    db_url, pid, _ = loaded                                    # the fixture paper is not in the manifest
    with make_session(db_url) as s:
        r = inv.inventory(s)
    assert r["totals"]["questions_in_db"] == 0                 # manifest papers are not loaded in this test DB
    assert all(p["in_db_questions"] == 0 for p in r["papers"])

def test_about_the_data_screen_renders(loaded, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    db_url, _, _ = loaded
    monkeypatch.setenv("GATE_DB_URL", db_url)
    from pathlib import Path
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
    at.session_state["screen"] = "About the Data"
    at.run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown) + " ".join(str(x.value) for x in at.metric)
    assert "Three groups of years" in text and "Year by year" in text
    assert any(m.label == "Papers (sessions) registered" and str(m.value) == "33" for m in at.metric)
