"""Taxonomy: load/validate the transcribed official syllabus YAML into
taxonomy_nodes. Sections carry verbatim official text (provenance=official);
topic and concept splits are a curation layer (provenance=inferred) pending
owner review. Optional top-level `prerequisites` list loads curated
concept->concept edges (provenance=inferred, never presented as verified)."""
from __future__ import annotations
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db.models import ConceptPrerequisite, TaxonomyNode

def load_taxonomy(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def validate_taxonomy(tax: dict) -> list[str]:
    errors = []
    if tax.get("exam") != "GATE":
        errors.append("taxonomy.exam must be GATE for this build")
    seen: set[str] = set()
    concept_ids: set[str] = set()
    for sec in tax.get("sections", []):
        sid = sec.get("id")
        if not sid:
            errors.append("section missing id"); continue
        if sid in seen:
            errors.append(f"duplicate section id {sid}")
        seen.add(sid)
        if not sec.get("syllabus_text"):
            errors.append(f"section {sid} missing verbatim syllabus_text")
        for top in sec.get("topics", []) or []:
            tid = top.get("id", "")
            if not tid.startswith(sid + "."):
                errors.append(f"topic {tid} not under section {sid}")
            if tid in seen:
                errors.append(f"duplicate topic id {tid}")
            seen.add(tid)
            if not isinstance(top.get("name"), str) or not top.get("name"):
                errors.append(f"topic {tid} missing/invalid name "
                              "(unquoted multi-part YAML names corrupt into stray keys)")
            extra = set(top) - {"id", "name", "concepts", "syllabus_text", "provenance", "deprecated"}
            if extra:
                errors.append(f"topic {tid} has stray keys {sorted(extra)} - "
                              "quote the name; a comma/colon split corrupts the node")
            for con in top.get("concepts", []) or []:
                cid = con.get("id", "")
                if not cid.startswith(tid + "."):
                    errors.append(f"concept {cid} not under topic {tid}")
                if cid in seen:
                    errors.append(f"duplicate concept id {cid}")
                seen.add(cid)
                concept_ids.add(cid)
                if not isinstance(con.get("name"), str) or not con.get("name"):
                    errors.append(f"concept {cid} missing/invalid name")
    for edge in tax.get("prerequisites", []) or []:
        a, b = edge.get("concept"), edge.get("requires")
        if a not in concept_ids:
            errors.append(f"prerequisite source {a} is not a known concept")
        if b not in concept_ids:
            errors.append(f"prerequisite target {b} is not a known concept")
        if a == b:
            errors.append(f"self-prerequisite on {a}")
    return errors

def upsert_taxonomy(s: Session, tax: dict) -> int:
    version = tax["taxonomy_version"]
    existing = {n.node_id: n for n in s.scalars(select(TaxonomyNode).where(TaxonomyNode.version == version))}
    n = 0
    def upsert(node_id, parent, level, name, text, prov, dep=False):
        nonlocal n
        node = existing.get(node_id)
        if node is None:
            node = TaxonomyNode(node_id=node_id, version=version)
            s.add(node)
        node.parent_id, node.level, node.name = parent, level, name
        node.syllabus_text, node.provenance, node.deprecated = text, prov, dep
        n += 1
    for sec in tax.get("sections", []):
        upsert(sec["id"], None, "section", sec["name"], sec.get("syllabus_text", ""),
               sec.get("provenance", "official"))
        for top in sec.get("topics", []) or []:
            upsert(top["id"], sec["id"], "topic", top["name"], top.get("syllabus_text", ""),
                   top.get("provenance", "inferred"), bool(top.get("deprecated", False)))
            for con in top.get("concepts", []) or []:
                upsert(con["id"], top["id"], "concept", con["name"], "",
                       con.get("provenance", "inferred"), bool(con.get("deprecated", False)))
    edges = tax.get("prerequisites", []) or []
    keep = {(e["concept"], e["requires"]) for e in edges}
    existing_edges = { (e.concept_id, e.required_concept_id): e
                       for e in s.scalars(select(ConceptPrerequisite)) }
    for key, edge in existing_edges.items():
        if key not in keep:
            s.delete(edge)  # curated set is authoritative; removal is explicit in YAML
    for e in edges:
        row = existing_edges.get((e["concept"], e["requires"]))
        if row is None:
            row = ConceptPrerequisite(concept_id=e["concept"], required_concept_id=e["requires"])
            s.add(row)
        row.provenance = "inferred"
        row.source_note = e.get("note", "")
        n += 1
    s.flush()
    return n

def valid_node_ids(s: Session, version: str, include_deprecated: bool = True) -> set[str]:
    rows = s.scalars(select(TaxonomyNode).where(TaxonomyNode.version == version)).all()
    return {n.node_id for n in rows if include_deprecated or not n.deprecated}

def topic_list(s: Session, version: str) -> list[dict]:
    rows = s.scalars(select(TaxonomyNode).where(
        TaxonomyNode.version == version, TaxonomyNode.level == "topic",
        TaxonomyNode.deprecated == False)).all()  # noqa: E712
    concepts = s.scalars(select(TaxonomyNode).where(
        TaxonomyNode.version == version, TaxonomyNode.level == "concept",
        TaxonomyNode.deprecated == False)).all()  # noqa: E712
    by_topic: dict[str, list[dict]] = {}
    for c in concepts:
        by_topic.setdefault(c.parent_id, []).append({"node_id": c.node_id, "name": c.name})
    return [{"node_id": r.node_id, "parent_id": r.parent_id, "name": r.name,
             "concepts": by_topic.get(r.node_id, [])} for r in rows]
