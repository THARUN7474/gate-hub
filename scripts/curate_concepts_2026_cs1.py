"""Populate concept-level classification for GATE 2026 CS-1 and apply the
independent-audit corrections, with honest provenance:

  - concept_ids for all 65 questions, curated question-by-question against the
    extracted stems/options (this script IS the curation record).
  - prerequisite_ids derived mechanically from the curated concept->concept
    edges in taxonomy.yaml (direct prerequisites of the question's concepts).
  - audit corrections applied as SUGGESTIONS: Q65 primary DB.NF -> DB.REL
    (superkeys are relational-keys content, not integrity constraints /
    normalization) and Q51 primary TOC.PUMP -> TOC.RCFL (id rename; node
    deprecated, not deleted). Each change is logged in review_events with
    reviewer 'owner-relayed-audit'. Nothing here is human-verified:
    provenance stays 'inferred', status stays 'suggested'.

Usage: python scripts/curate_concepts_2026_cs1.py [--db-url sqlite:///data/gate_cse.sqlite]
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from src.db.models import (Classification, ClassificationRun, ConceptPrerequisite,
                           Question, ReviewEvent)
from src.db.session import make_session

# q_number -> (primary_topic_id, [concept_ids], audit note or "")
# Concept ids must exist in taxonomy.yaml. Primary topic unchanged unless the
# audit found it wrong; the concept layer carries the granularity.
MAP: dict[int, tuple[str, list[str], str]] = {
 1:("GA.VA",["GA.VA.VOCAB"],""),
 2:("GA.SA",["GA.SA.PATTERN"],""),
 3:("GA.QA",["GA.QA.COUNT"],""),
 4:("GA.QA",["GA.QA.OPTI"],""),
 5:("GA.AA",["GA.AA.DEDUCT"],""),
 6:("GA.AA",["GA.AA.DEDUCT","GA.VA.RC"],""),
 7:("GA.SA",["GA.SA.VIEWS"],""),
 8:("GA.QA",["GA.QA.FUNC"],""),
 9:("GA.AA",["GA.AA.ORDER"],""),
 10:("GA.QA",["GA.QA.PROB"],""),
 11:("EM.PS",["EM.PS.COND"],""),
 12:("EM.DM",["EM.DM.COUNT"],"audit: appropriate (combinatorics counting)"),
 13:("EM.LA",["EM.LA.EIGEN"],""),
 14:("COA.ISA",["COA.ISA.ADDR"],""),
 15:("COA.ISA",["COA.ISA.INSTR"],""),
 16:("COA.PIPE",["COA.PIPE.HAZARD"],""),
 17:("ALGO.CMPLX",["ALGO.CMPLX.RECUR"],""),
 18:("CN.TCP",["CN.TCP.CONN"],""),
 19:("CN.APP",["CN.APP.HTTP"],""),
 20:("EM.LA",["EM.LA.RANK"],""),
 21:("DL.BOOL",["DL.BOOL.ALG"],""),
 22:("DL.NUM",["DL.NUM.FIXED"],""),
 23:("PDS.TREE",["PDS.TREE.HEAP"],"audit: appropriate (min-heap)"),
 24:("ALGO.SORT",["ALGO.SORT.HASH"],"audit: added explicit hashing/linear-probing microtopic (was only implied by topic id)"),
 25:("TOC.CFG",["TOC.CFG.CFG"],""),
 26:("TOC.REG",["TOC.REG.FA"],""),
 27:("CD.LEX",["CD.LEX.LEX","CD.LEX.PARSE"],""),
 28:("CD.LEX",["CD.LEX.PARSE"],""),
 29:("OS.DL",["OS.DL.BANKER","OS.DL.DLOCK"],""),
 30:("DB.NF",["DB.NF.FD"],""),
 31:("DB.NF",["DB.NF.NF","DB.NF.FD"],""),
 32:("EM.CAL",["EM.CAL.CONT"],""),
 33:("PDS.TREE",["PDS.TREE.BTREE"],""),
 34:("PDS.C",["PDS.C.SCOPE"],""),
 35:("OS.DL",["OS.DL.DLOCK"],""),
 36:("DL.NUM",["DL.NUM.FLOAT"],""),
 37:("DL.CIRC",["DL.CIRC.SEQ"],""),
 38:("COA.MEM",["COA.MEM.CACHE"],""),
 39:("PDS.LIN",["PDS.LIN.LL","PDS.REC.REC"],"audit: added linked-list and recursion concepts as requested"),
 40:("PDS.TREE",["PDS.TREE.BST","PDS.TREE.BTREE"],""),
 41:("ALGO.GRAPH",["ALGO.GRAPH.SP"],""),
 42:("CD.OPT",["CD.OPT.DFLOW"],""),
 43:("DB.REL",["DB.REL.CALC","DB.REL.ALG"],""),
 44:("CN.TCP",["CN.TCP.CONG"],""),
 45:("CN.DLL",["CN.DLL.SW"],""),
 46:("EM.CAL",["EM.CAL.EXTREMA","EM.CAL.CONT"],""),
 47:("ALGO.GRAPH",["ALGO.GRAPH.VC","EM.DM.GRAPH"],"audit: added graph-theory and vertex-cover concepts (vertex cover not verbatim in syllabus; concept marked as curation extension)"),
 48:("DL.BOOL",["DL.BOOL.MINIM"],""),
 49:("ALGO.GRAPH",["ALGO.GRAPH.MST"],""),
 50:("ALGO.GRAPH",["ALGO.GRAPH.TRAV"],""),
 51:("TOC.RCFL",["TOC.RCFL.CLOSURE"],"audit: primary id renamed TOC.PUMP -> TOC.RCFL (same node, non-misleading id); closure-properties concept added"),
 52:("TOC.CFG",["TOC.CFG.CFG"],""),
 53:("CD.SDT",["CD.SDT.SDD"],""),
 54:("OS.MEM",["OS.MEM.VMEM","COA.MEM.CACHE"],"audit: OS.MEM primary kept; cache aspect added as secondary concept COA.MEM.CACHE"),
 55:("ALGO.GRAPH",["EM.DM.GRAPH","ALGO.GRAPH.TRAV"],"audit: added bipartite/graph-colouring (EM.DM.GRAPH) and traversal-based test concepts"),
 56:("CN.ROUTE",["CN.ROUTE.CIDR"],"audit: CIDR/subnetting microtopic now explicit"),
 57:("EM.DM",["EM.DM.GRAPH","EM.DM.COUNT"],"audit: appropriate (matching verbatim in DM syllabus)"),
 58:("EM.PS",["EM.PS.RV"],""),
 59:("OS.FS",["OS.FS.DISK"],"audit: reasonable (storage performance)"),
 60:("COA.PIPE",["COA.PIPE.HAZARD"],""),
 61:("PDS.REC",["PDS.REC.REC"],""),
 62:("PDS.TREE",["PDS.TREE.BST","PDS.TREE.TRAV"],""),
 63:("OS.PROC",["OS.PROC.PROC"],""),
 64:("OS.SCHED",["OS.SCHED.SCHED"],""),
 65:("DB.REL",["DB.REL.KEYS"],"audit: PRIMARY CORRECTED DB.NF -> DB.REL - superkeys/candidate keys are relational-model keys content, distinct from integrity constraints and normal forms"),
}
REVIEWER = "owner-relayed-audit"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=None)
    args = ap.parse_args()
    with make_session(args.db_url) as s:
        edges: dict[str, set[str]] = {}
        for e in s.scalars(select(ConceptPrerequisite)):
            edges.setdefault(e.concept_id, set()).add(e.required_concept_id)
        run = ClassificationRun(model="curated-concepts-v1", prompt_version="v1",
                                provider="curation+audit-review")
        s.add(run); s.flush()
        updated = corrected = 0
        questions = {q.q_number: q for q in s.scalars(select(Question))}
        missing = sorted(set(MAP) - set(questions))
        if missing:
            print(f"questions not in DB: {missing}"); return 1
        for qno, (topic, concepts, note) in MAP.items():
            q = questions[qno]
            c = s.scalar(select(Classification).where(Classification.question_id == q.id))
            if c is None:
                print(f"no classification for {q.id}"); return 1
            if c.primary_topic_id != topic:
                s.add(ReviewEvent(question_id=q.id, field="primary_topic_id",
                                  before=c.primary_topic_id, after=topic,
                                  reviewer=REVIEWER,
                                  note="audit correction applied as SUGGESTION; human verification pending"))
                corrected += 1
                c.primary_topic_id = topic
                c.section_id = topic.split(".")[0]
            prereq = sorted({p for cid in concepts for p in edges.get(cid, set())
                             if p not in concepts})
            c.concept_ids = concepts
            c.prerequisite_ids = prereq
            c.run_id = run.id
            c.provenance = "inferred"   # curation is not verification
            c.status = "suggested"
            if note and note not in (c.what_it_tests or ""):
                c.what_it_tests = (c.what_it_tests or "") + " | 3rd pass (" + REVIEWER + "): " + note
            updated += 1
        from datetime import datetime, timezone
        run.finished_at = datetime.now(timezone.utc)
        run.stats = {"curated": updated, "primary_corrections": corrected,
                     "provenance": "inferred", "status": "suggested",
                     "note": "concept-level curation + owner-relayed audit corrections; not human verification"}
        s.commit()
        print(f"curated {updated} questions, {corrected} primary-topic corrections; "
              f"all remain provenance=inferred status=suggested")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
