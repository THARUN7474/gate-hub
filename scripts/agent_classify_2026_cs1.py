"""Agent-performed classification of GATE 2026 CS-1 against taxonomy gate-cs-2027.

NOT an LLM API integration run. The agent read each extracted question and
assigned section/topic/confidence/what-it-tests by hand. Rows are written with
provenance=inferred, status=suggested, prompt_version=agent-v1, so they stay
separate from both mock plumbing and any future real-provider run, and they
surface in the Review Workspace for human verification.

Run:  PYTHONPATH=. GATE_DB_URL=sqlite:///data/gate_cse.sqlite python scripts/agent_classify_2026_cs1.py
"""
from datetime import datetime, timezone
from sqlalchemy import select
from src.db.session import make_session
from src.db.models import Classification, ClassificationRun, Question

# qno: (section, topic, confidence, what_it_tests)
C = {
 1:("GA","GA.VA",0.98,"Vocabulary: antonym of 'protagonist'"),
 2:("GA","GA.SA",0.95,"Spatial reasoning: tiling patterns (figure-based; options are images)"),
 3:("GA","GA.QA",0.90,"Counting: games in a 64-player knockout tournament"),
 4:("GA","GA.QA",0.90,"Numerical optimization: max elective credits under constraints"),
 5:("GA","GA.AA",0.90,"Logic: necessary vs sufficient inference from a conditional"),
 6:("GA","GA.AA",0.85,"Reading comprehension + logical inference about statements P and Q"),
 7:("GA","GA.SA",0.97,"Spatial aptitude: front/top views to 3D structure (figure-based)"),
 8:("GA","GA.QA",0.90,"Function graphs: expressing N(S) via hinge functions H_K(S)"),
 9:("GA","GA.AA",0.90,"Deductive ordering: infer round of best throw from observations"),
 10:("GA","GA.QA",0.90,"Probability: two dice rolls, integer-multiple event"),
 11:("EM","EM.PS",0.95,"Conditional probability in a Polya-urn process"),
 12:("EM","EM.DM",0.85,"Combinatorics: counting 0-1 matrices with even row/column sums"),
 13:("EM","EM.LA",0.97,"Eigenvalue multiplicity bounds for real n x n matrices"),
 14:("COA","COA.ISA",0.97,"Addressing modes matched to HLL data elements"),
 15:("COA","COA.ISA",0.95,"Load-store ISA instruction sequence for Z = X + Y"),
 16:("COA","COA.PIPE",0.97,"Pipeline data hazards: read-after-write dependency"),
 17:("ALGO","ALGO.CMPLX",0.95,"Solving coupled recurrences (Master-theorem style)"),
 18:("CN","CN.TCP",0.95,"TCP connection termination semantics"),
 19:("CN","CN.APP",0.95,"HTTP 1.1 persistent connections and pipelining"),
 20:("EM","EM.LA",0.97,"Null space, determinant and rank relationships"),
 21:("DL","DL.BOOL",0.95,"Boolean algebra: equivalent forms of XOR expression"),
 22:("DL","DL.NUM",0.95,"Sign-magnitude representation and arithmetic overflow"),
 23:("PDS","PDS.TREE",0.85,"Binary minheap array layout: leaf vs internal indices"),
 24:("ALGO","ALGO.SORT",0.85,"Hashing: linear probing occupancy (topic id covers searching/sorting/hashing)"),
 25:("TOC","TOC.CFG",0.95,"CFG ambiguity and derivations"),
 26:("TOC","TOC.REG",0.95,"NFA-to-DFA subset construction state bounds"),
 27:("CD","CD.LEX",0.90,"Lexical vs syntactic vs semantic errors in C declarations"),
 28:("CD","CD.LEX",0.95,"LL(1) parser properties"),
 29:("OS","OS.DL",0.97,"Deadlock prevention, Banker's algorithm, resource allocation graph"),
 30:("DB","DB.NF",0.90,"Functional dependency implication rules"),
 31:("DB","DB.NF",0.97,"Normal forms: dependency-preserving decompositions (3NF/BCNF)"),
 32:("EM","EM.CAL",0.97,"Continuity condition at a point, solve for constants"),
 33:("PDS","PDS.TREE",0.90,"Maximum height of a full binary tree with 23 nodes"),
 34:("PDS","PDS.C",0.95,"C scoping: shadowed variable in nested block, printf output"),
 35:("OS","OS.DL",0.97,"Minimum resource instances to be deadlock-free"),
 36:("DL","DL.NUM",0.95,"IEEE 754 single-precision floating-point addition"),
 37:("DL","DL.CIRC",0.97,"Synchronous sequential design: D flip-flop input expressions for a counter"),
 38:("COA","COA.MEM",0.97,"Cache TAG bits: direct-mapped vs K-way set-associative"),
 39:("PDS","PDS.LIN",0.75,"Recursive linked-list length in C (recursion + linear DS; topic choice reviewable)"),
 40:("PDS","PDS.TREE",0.90,"BST insertion order producing a complete binary tree"),
 41:("ALGO","ALGO.GRAPH",0.90,"Shortest-path properties with bounded edge count"),
 42:("CD","CD.OPT",0.97,"Common subexpression elimination in a control flow graph"),
 43:("DB","DB.REL",0.95,"Tuple relational calculus to relational algebra equivalence"),
 44:("CN","CN.TCP",0.97,"TCP slow-start congestion-window timing"),
 45:("CN","CN.DLL",0.95,"Sliding window size for 100% link utilization"),
 46:("EM","EM.CAL",0.97,"Local extrema and differentiability of a piecewise function"),
 47:("ALGO","ALGO.GRAPH",0.80,"Vertex cover: membership constraints (graph theory overlap with EM.DM)"),
 48:("DL","DL.BOOL",0.97,"Minimal sum-of-products from minterms (K-map minimization)"),
 49:("ALGO","ALGO.GRAPH",0.97,"MST cycle/cut properties with unique edge weights"),
 50:("ALGO","ALGO.GRAPH",0.97,"DFS discovery/finishing time orderings in a DAG"),
 51:("TOC","TOC.PUMP",0.85,"Regular/context-free language class relationships and closure"),
 52:("TOC","TOC.CFG",0.90,"Counting terminal symbols in strings of a CFG language"),
 53:("CD","CD.SDT",0.97,"S-attributed vs L-attributed syntax-directed definitions"),
 54:("OS","OS.MEM",0.85,"TLB/page-table/cache hit-miss sequences (virtual memory)"),
 55:("ALGO","ALGO.GRAPH",0.85,"2-colorability (bipartiteness) properties and test complexity"),
 56:("CN","CN.ROUTE",0.90,"CIDR supernetting: valid address block allocation"),
 57:("EM","EM.DM",0.90,"Counting matchings in a path graph"),
 58:("EM","EM.PS",0.97,"Expected value of a discrete random variable"),
 59:("OS","OS.FS",0.85,"Disk access time: seek + rotational latency + transfer"),
 60:("COA","COA.PIPE",0.97,"Structural-hazard stall cycles in a pipelined EX stage"),
 61:("PDS","PDS.REC",0.95,"Mutual recursion: smallest n with foo(n) = 5"),
 62:("PDS","PDS.TREE",0.95,"BST preorder reconstruction; position in postorder"),
 63:("OS","OS.PROC",0.97,"fork() semantics: process counting"),
 64:("OS","OS.SCHED",0.97,"FCFS scheduling average waiting time"),
 65:("DB","DB.NF",0.85,"Counting superkeys from candidate keys"),
}

def main():
    assert len(C) == 65
    with make_session() as s:
        run = ClassificationRun(
            model="claude-agent-manual-v1", prompt_version="agent-v1",
            provider="agent-analysis",
            stats={"note": "Agent read each extracted question and classified against "
                           "taxonomy gate-cs-2027. NOT an LLM API integration run; "
                           "suggestions pending human verification."})
        s.add(run); s.flush()
        n = 0
        for qno, (sec, topic, conf, wit) in C.items():
            uid = f"GATE-CS-2026-S1-Q{qno:02d}"
            q = s.get(Question, uid)
            assert q, uid
            existing = s.scalar(select(Classification).where(
                Classification.question_id == uid,
                Classification.taxonomy_version == "gate-cs-2027",
                Classification.prompt_version == "agent-v1"))
            if existing and existing.status == "verified":
                continue
            c = existing or Classification(question_id=uid, taxonomy_version="gate-cs-2027",
                                           prompt_version="agent-v1")
            c.run_id = run.id; c.section_id = sec; c.primary_topic_id = topic
            c.topic_weight = {topic: 1.0}; c.concept_ids = []
            c.what_it_tests = wit; c.prerequisite_ids = []; c.confidence = conf
            c.evidence_quote = (q.text or "")[:120]
            c.provenance = "inferred"
            c.status = "suggested" if conf >= 0.5 else "flagged"
            c.model = "claude-agent-manual-v1"
            c.classified_at = datetime.now(timezone.utc)
            s.add(c); n += 1
        run.finished_at = datetime.now(timezone.utc)
        run.stats = {**run.stats, "classified": n, "flagged": 0, "skipped_verified": 0}
        s.commit()
        print("classified", n)

if __name__ == "__main__":
    main()
