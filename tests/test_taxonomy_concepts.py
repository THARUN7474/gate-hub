"""Taxonomy concepts + prerequisite edges: validation catches malformed YAML
(regression for the corrupted topic names the audit found), upsert loads all
levels, and curated edges stay inside the concept vocabulary."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from src.db.models import ConceptPrerequisite, TaxonomyNode
from src.db.session import make_session
from src.taxonomy import taxonomy as tx

ROOT = Path(__file__).resolve().parents[1]

def test_shipped_taxonomy_is_valid():
    tax = tx.load_taxonomy(str(ROOT / "taxonomy.yaml"))
    assert tx.validate_taxonomy(tax) == []

def test_topic_names_not_split_into_stray_keys():
    """Regression: unquoted multi-part names ('Searching, sorting, hashing')
    corrupted into name='Searching' + stray keys. Names must carry the full
    syllabus phrase so topic ids like ALGO.SORT are not misleading."""
    tax = tx.load_taxonomy(str(ROOT / "taxonomy.yaml"))
    names = {t["id"]: t["name"] for s in tax["sections"] for t in s["topics"]}
    assert "hashing" in names["ALGO.SORT"]
    assert "linked lists" in names["PDS.LIN"]
    assert "CIDR" in names["CN.ROUTE"]
    assert "normal forms" in names["DB.NF"]
    assert "pumping lemma" in names["TOC.RCFL"]
    assert names["COA.IO"] == "I/O interface (interrupt and DMA)"
    deprecated = {t2["id"] for s in tax["sections"] for t2 in s["topics"] if t2.get("deprecated")}
    assert "TOC.PUMP" in deprecated and "TOC.PUMP" not in {
        t2["id"] for s in tax["sections"] for t2 in s["topics"] if not t2.get("deprecated")}

def test_validate_catches_stray_keys_and_bad_concepts():
    bad = {"exam": "GATE", "sections": [
        {"id": "ALGO", "name": "Algorithms", "syllabus_text": "x",
         "topics": [{"id": "ALGO.SORT", "name": "Searching", "hashing": None},
                    {"id": "WRONG.X", "name": "nope"}]}],
        "prerequisites": [{"concept": "ALGO.SORT.HASH", "requires": "NOPE"}]}
    errors = tx.validate_taxonomy(bad)
    assert any("stray keys" in e for e in errors)
    assert any("not under section" in e for e in errors)
    assert any("not a known concept" in e for e in errors)

def test_upsert_loads_concepts_and_edges(db_url):
    tax = tx.load_taxonomy(str(ROOT / "taxonomy.yaml"))
    with make_session(db_url) as s:
        tx.upsert_taxonomy(s, tax)
        levels = dict(s.execute(
            select(TaxonomyNode.node_id, TaxonomyNode.level)).all())
        assert levels["ALGO.SORT.HASH"] == "concept"
        assert levels["CN.ROUTE.CIDR"] == "concept"
        assert levels["DB.REL.KEYS"] == "concept"
        pump = s.scalar(select(TaxonomyNode).where(TaxonomyNode.node_id == "TOC.PUMP"))
        assert pump.deprecated  # old id resolvable but retired
        edges = {(e.concept_id, e.required_concept_id)
                 for e in s.scalars(select(ConceptPrerequisite))}
        assert ("CN.ROUTE.CIDR", "CN.ROUTE.IPV4") in edges
        assert ("DB.NF.FD", "DB.REL.KEYS") in edges
        s.commit()
        # idempotent re-upsert
        tx.upsert_taxonomy(s, tax)
        n_edges = len(s.scalars(select(ConceptPrerequisite)).all())
        assert n_edges == len(tax["prerequisites"])
