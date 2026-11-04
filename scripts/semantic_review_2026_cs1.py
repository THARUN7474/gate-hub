"""Stratified AUTOMATED semantic pass over the 2026 CS1 classifications.

This is a NON-HUMAN second look: it samples questions across sections,
confidence bands and question types, then runs mechanical consistency
checks. It does NOT verify anything - no classification status changes, no
'human-verified' labels. Output: exports/semantic_review_2026_cs1.{csv,md}
with provenance stated on every row. Human review in the Review Workspace
remains the only path to 'verified'."""
from __future__ import annotations
import csv, sys
from pathlib import Path
from collections import defaultdict
from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db.models import Classification, ConceptPrerequisite, Option, Paper, Question, TaxonomyNode
from src.db.session import make_session

PROVENANCE = "automated non-human review (mechanical checks only) - NOT verification"

def main() -> None:
    s = make_session()
    paper = s.scalar(select(Paper).where(Paper.year == 2026))
    nodes = {n.node_id: n for n in s.scalars(select(TaxonomyNode))}
    edges = {e.concept_id: e.required_concept_id for e in s.scalars(select(ConceptPrerequisite))}

    rows = []
    for q in s.scalars(select(Question).where(Question.paper_id == paper.id).order_by(Question.q_number)):
        cls = s.scalar(select(Classification).where(Classification.question_id == q.id))
        rows.append((q, cls))

    # Stratify: section x confidence band x type, take up to 2 per stratum.
    strata = defaultdict(list)
    for q, cls in rows:
        band = ("none" if cls is None else
                "low" if cls.confidence < 0.6 else
                "mid" if cls.confidence < 0.85 else "high")
        strata[((cls.section_id if cls else None), band, q.q_type)].append((q, cls))
    sample = []
    for key in sorted(strata, key=lambda k: (str(k[0]), str(k[1]), str(k[2]))):
        sample.extend(strata[key][:2])

    out = []
    for q, cls in sample:
        issues = []
        if cls is None:
            issues.append("unclassified")
        else:
            sec = nodes.get(cls.section_id)
            top = nodes.get(cls.primary_topic_id)
            if sec is None:
                issues.append(f"unknown section {cls.section_id}")
            if top is None:
                issues.append(f"unknown topic {cls.primary_topic_id}")
            elif not cls.primary_topic_id.startswith(cls.section_id + "."):
                issues.append(f"topic {cls.primary_topic_id} not under section {cls.section_id}")
            for cid in cls.concept_ids or []:
                node = nodes.get(cid)
                if node is None:
                    issues.append(f"unknown concept {cid}")
                # cross-topic concepts are allowed by design (a question can test
                # material outside its primary topic) - not flagged here.
                if (cid in edges and edges[cid] not in (cls.prerequisite_ids or [])
                        and edges[cid] not in (cls.concept_ids or [])):
                    issues.append(f"curated prerequisite {edges[cid]} of {cid} neither listed as prerequisite nor tested as concept")
            # weak text signal: do any topic/concept name words appear in the text?
            hay = (q.text or "").lower()
            names = [nodes[c].name for c in (cls.concept_ids or []) if c in nodes]
            hits = sum(1 for n in names if any(w in hay for w in n.lower().split() if len(w) > 4))
            if names and hits == 0:
                issues.append("no topic/concept name words visible in question text (weak signal - may still be correct)")
        out.append({
            "question_id": q.id, "type": q.q_type,
            "section": cls.section_id if cls else "",
            "topic": cls.primary_topic_id if cls else "",
            "confidence": cls.confidence if cls else "",
            "status": cls.status if cls else "",
            "needs_review": q.needs_review,
            "issues": "; ".join(issues) or "none found by mechanical checks",
            "provenance": PROVENANCE,
        })

    exp = ROOT / "exports"
    exp.mkdir(exist_ok=True)
    with open(exp / "semantic_review_2026_cs1.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    with open(exp / "semantic_review_2026_cs1.md", "w") as f:
        f.write("# Stratified automated semantic pass - 2026 CS1\n\n"
                f"Provenance: {PROVENANCE}. Sampling: up to 2 questions per "
                "(section x confidence band x question type) stratum; checks are "
                "structural consistency only. Statuses are unchanged; human review "
                "in the Review Workspace is the only path to 'verified'.\n\n")
        for r in out:
            f.write(f"- {r['question_id']} [{r['section']}/{r['topic']}, conf {r['confidence']}] "
                    f"{r['issues']}\n")
    n_flag = sum(1 for r in out if r["issues"] != "none found by mechanical checks")
    print(f"sampled {len(out)} of {len(rows)} questions across {len(strata)} strata; "
          f"{n_flag} with mechanical-check findings")

if __name__ == "__main__":
    main()
