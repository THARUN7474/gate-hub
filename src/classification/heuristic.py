"""Local heuristic classifier: keyword/phrase scoring against the taxonomy, fully offline.

Purpose: a source-backed FIRST-PASS suggestion when no external LLM is approved. It reads the
question text + options + the paper's GA/CS position and scores every taxonomy topic by
weighted phrase matching (topic names, concept names, and a curated GATE-phrase lexicon).

Honesty contract:
- It is NOT a language model and NOT human review. Rows it writes keep provenance=inferred,
  model="local-heuristic-v1", and are suggested (or flagged when confidence is low); they are
  never marked verified and never overwrite a verified/validated row or an existing suggestion
  unless reclassify=True.
- Its labels are word-matching: strong on named concepts (Dijkstra, B+ tree, TCP), weak on
  bare numerical/word problems. Low-confidence rows are flagged for a human, not hidden.
"""
from __future__ import annotations
import re
from collections import Counter
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Classification, ClassificationRun, Question, ReviewEvent
from ..taxonomy.taxonomy import topic_list
from .classify import _classification_target, _question_block, combo_score

HEURISTIC_MODEL = "local-heuristic-v1"
HEURISTIC_PROMPT_VERSION = "heuristic-v1"

# Curated GATE phrasing per topic id, on top of the taxonomy's own topic/concept names.
# Multi-word phrases are worth more automatically (weight = words). Keep phrases lowercase.
LEXICON: dict[str, list[str]] = {
    "GA.VA.VOCAB": ["opposite in meaning", "closest in meaning", "nearest in meaning", "synonym",
                    "antonym", "meaning of the word", "one word substitute", "idiom"],
    "GA.VA.GRAM": ["grammatically correct", "grammatically incorrect", "correct sentence",
                   "parts of speech", "tense", "preposition"],
    "GA.VA.RC": ["passage", "paragraph", "author", "infer from", "reading comprehension"],
    "GA.QA.COUNT": ["permutation", "combination", "number of ways", "arrange", "arrangement of"],
    "GA.QA.PROB": ["probability", "expected value", "dice", "cards", "coin"],
    "GA.QA.OPTI": ["ratio", "percentage", "average speed", "work done", "simple interest",
                   "compound interest", "profit", "loss percent", "train", "speed of"],
    "GA.QA.FUNC": ["bar graph", "pie chart", "table below", "graph shows", "data interpretation",
                   "plot", "function f(x)", "f(x) ="],
    "GA.AA.DEDUCT": ["logical", "deduce", "conclusion", "implies", "statement", "assumption",
                     "argument", "inference"],
    "GA.AA.ORDER": ["seating", "sitting", "arrangement", "order", "rank", "taller", "older",
                    "next number", "series", "analogy", "odd one", "sequence"],
    "GA.SA.PATTERN": ["folding", "folded", "cutting", "paper fold", "pattern", "tile", "tiling"],
    "GA.SA.VIEWS": ["cube", "cubes", "3d", "three-dimensional", "rotation", "mirror",
                    "orthographic", "view of the", "solid"],
    "EM.DM.LOGIC": ["propositional", "predicate", "first-order logic", "first order logic",
                    "quantifier", "tautology", "satisfiable", "valid formula", "logical equivalence",
                    "modus ponens", "truth table", "boolean formula", "logical inference"],
    "EM.DM.REL": ["equivalence relation", "partial order", "poset", "lattice", "hasse",
                  "reflexive", "symmetric", "transitive", "function", "bijective", "injective",
                  "surjective", "one-to-one", "onto", "group", "monoid", "abelian", "binary operation"],
    "EM.DM.GRAPH": ["graph", "vertex", "vertices", "edge", "planar", "chromatic", "colouring",
                    "coloring", "matching", "connectivity", "euler", "hamiltonian", "degree of"],
    "EM.DM.COUNT": ["recurrence relation", "generating function", "counting", "pigeonhole",
                    "coefficient of", "combinations", "ways to"],
    "EM.LA.RANK": ["matrix", "matrices", "determinant", "rank", "null space", "system of linear",
                   "linear equations", "singular", "inverse of"],
    "EM.LA.EIGEN": ["eigenvalue", "eigenvalues", "eigenvector", "eigenvectors", "characteristic polynomial",
                    "eigen"],
    "EM.LA.LU": ["lu decomposition", "lu factorization", "gaussian elimination", "gauss elimination"],
    "EM.CAL.CONT": ["limit", "continuous", "continuity", "differentiable", "differentiability"],
    "EM.CAL.EXTREMA": ["maximum", "minimum", "maxima", "minima", "mean value theorem", "stationary",
                       "local extremum", "optimization", "optimal value of"],
    "EM.CAL.INTEG": ["integral", "integration", "area under", "evaluate"],
    "EM.PS.COND": ["conditional probability", "bayes", "given that", "independent events"],
    "EM.PS.DIST": ["uniform distribution", "normal distribution", "exponential distribution",
                   "poisson", "binomial distribution", "geometric distribution", "density function"],
    "EM.PS.RV": ["random variable", "expectation", "variance", "standard deviation", "mean of",
                 "expected number", "probability that"],
    "DL.BOOL.ALG": ["boolean", "expression", "simplify", "consensus theorem", "absorption"],
    "DL.BOOL.MINIM": ["karnaugh", "k-map", "minimiz", "minimis", "prime implicant", "essential prime",
                      "sum of products", "product of sums", "minimal form", "minimal sum"],
    "DL.NUM.FIXED": ["2's complement", "1's complement", "sign magnitude", "signed representation",
                     "fixed point", "binary representation of"],
    "DL.NUM.FLOAT": ["ieee 754", "floating point", "mantissa", "exponent field", "normalized"],
    "DL.CIRC.COMB": ["multiplexer", "mux", "demultiplexer", "decoder", "encoder", "half adder",
                     "full adder", "comparator", "combinational"],
    "DL.CIRC.SEQ": ["flip-flop", "flip flop", "register", "counter", "sequential", "state table",
                    "state diagram", "clock", "latch", "shift register", "mod-n", "fsm"],
    "PDS.C.SCOPE": ["c program", "output of the following program", "printf", "pointer", "struct",
                    "storage class", "static", "scope", "#include", "code fragment", "program below",
                    "following program", "c language", "declaration"],
    "PDS.REC.REC": ["recursive", "recursion", "calls itself", "recursively"],
    "PDS.LIN.ARR": ["array", "subscript", "two-dimensional array", "row major", "column major"],
    "PDS.LIN.LL": ["linked list", "link list", "node", "pointer to the next", "singly linked",
                   "doubly linked"],
    "PDS.LIN.STACKQ": ["stack", "queue", "push", "pop", "enqueue", "dequeue", "postfix", "infix",
                       "prefix", "circular queue"],
    "PDS.TREE.BST": ["binary search tree", "bst", "avl", "search tree"],
    "PDS.TREE.BTREE": ["binary tree", "tree with n", "height of", "leaf nodes", "leaves", "arity"],
    "PDS.TREE.HEAP": ["heap", "min-heap", "max-heap", "min heap", "max heap", "priority queue"],
    "PDS.TREE.TRAV": ["traversal", "inorder", "preorder", "postorder", "level order"],
    "PDS.GRAPH.REP": ["adjacency matrix", "adjacency list", "representation of a graph"],
    "ALGO.CMPLX.ASYMPT": ["time complexity", "worst case", "asymptotic", "big o", "theta", "omega", "order of growth", "running time"],
    "ALGO.CMPLX.RECUR": ["recurrence", "t(n)", "master theorem", "solve the recurrence"],
    "ALGO.DESIGN.DP": ["dynamic programming", "optimal substructure", "longest common subsequence",
                       "lcs", "matrix chain", "memoization"],
    "ALGO.DESIGN.GREEDY": ["greedy", "huffman", "activity selection", "knapsack problem"],
    "ALGO.DESIGN.DAC": ["divide and conquer", "merge sort recurrence"],
    "ALGO.GRAPH.TRAV": ["bfs", "dfs", "breadth first", "depth first", "breadth-first", "depth-first",
                        "topological sort", "topological ordering", "graph traversal"],
    "ALGO.GRAPH.MST": ["minimum spanning tree", "spanning tree", "kruskal", "prim's", "prims", "mst"],
    "ALGO.GRAPH.SP": ["shortest path", "dijkstra", "bellman", "floyd", "warshall", "single source"],
    "ALGO.GRAPH.VC": ["vertex cover", "np-complete", "np-hard", "clique", "independent set",
                      "satisfiability problem", "3-sat", "reduction"],
    "ALGO.SORT.SORT": ["sorting", "quicksort", "quick sort", "merge sort", "insertion sort",
                       "selection sort", "heap sort", "heapsort", "radix sort", "counting sort",
                       "bubble sort", "sorted"],
    "ALGO.SORT.SEARCH": ["binary search", "searching", "search for an element"],
    "ALGO.SORT.HASH": ["hash", "hashing", "hash function", "collision", "linear probing",
                       "open addressing", "chaining", "hash table"],
    "CD.LEX.LEX": ["lexical", "lexer", "token", "lexeme", "scanner", "keyword", "lex"],
    "CD.LEX.PARSE": ["parsing", "parser", "ll(1)", "lr(0)", "lr(1)", "slr", "lalr", "clr",
                     "shift-reduce", "shift reduce", "reduce-reduce", "first and follow",
                     "follow set", "first set", "handle", "viable prefix", "syntax error",
                     "left recursion", "ambiguous grammar", "derivation", "parse tree"],
    "CD.SDT.SDD": ["syntax-directed", "syntax directed", "s-attributed", "l-attributed",
                   "attribute grammar", "translation scheme", "semantic action"],
    "CD.RUNTIME.IR": ["intermediate code", "three address", "three-address", "quadruple",
                      "code generation", "basic block", "control flow graph"],
    "CD.RUNTIME.RT": ["activation record", "stack frame", "runtime environment", "garbage collection",
                      "heap allocation", "static allocation", "display", "parameter passing"],
    "CD.OPT.DFLOW": ["data flow", "data-flow", "live variable", "reaching definition",
                     "common subexpression", "constant propagation", "optimization", "optimisation",
                     "dead code", "loop invariant", "available expression"],
    "OS.PROC.PROC": ["process", "fork", "thread", "context switch", "process creation", "zombie",
                     "orphan process"],
    "OS.PROC.IPC": ["shared memory", "message passing", "pipe", "ipc", "inter-process"],
    "OS.SCHED.SCHED": ["scheduling", "fcfs", "sjf", "round robin", "round-robin", "priority scheduling",
                       "turnaround time", "waiting time", "response time", "shortest job first",
                       "cpu scheduling", "preemptive", "gantt"],
    "OS.SYNC.SYNC": ["semaphore", "mutex", "race condition", "critical section", "synchronization",
                     "synchronisation", "atomic", "lock", "monitor", "producer consumer",
                     "reader writer", "dining philosopher", "test-and-set", "peterson"],
    "OS.DL.DLOCK": ["deadlock", "safe state", "unsafe state", "resource allocation graph",
                    "circular wait", "deadlock detection"],
    "OS.DL.BANKER": ["banker's algorithm", "bankers algorithm", "deadlock avoidance", "maximum need",
                     "available resources"],
    "OS.MEM.VMEM": ["page fault", "paging", "virtual memory", "page replacement", "lru", "fifo page",
                    "optimal page", "tlb", "page table", "demand paging", "thrashing", "belady",
                    "logical address", "physical address", "page size", "segmentation"],
    "OS.FS.FS": ["file system", "inode", "i-node", "directory", "file allocation", "indexed allocation",
                 "linked allocation", "contiguous allocation", "file control block"],
    "OS.FS.DISK": ["disk", "seek time", "rotational latency", "disk scheduling", "sstf", "scan",
                   "c-scan", "cylinder", "disk access", "sector"],
    "DB.ER.ER": ["er diagram", "entity relationship", "entity-relationship", "e-r", "entity set",
                 "relationship set", "cardinality ratio"],
    "DB.NF": ["normal form", "normalization", "normalisation", "functional dependency",
              "functional dependencies", "bcnf", "3nf", "2nf", "1nf", "candidate key",
              "prime attribute", "dependency preserving", "lossless"],
    "DB.REL.SQL": ["sql", "select", "query", "group by", "having", "join", "nested query",
                   "aggregate", "count(", "relational algebra", "relational calculus",
                   "natural join", "outer join", "tuple relational"],
    "DB.REL.KEYS": ["super key", "superkey", "primary key"],
    "DB.IDX.IDX": ["index", "indexing", "b+ tree", "b-tree", "b tree", "file organization",
                   "file organisation", "clustered index", "dense index", "sparse index",
                   "search key", "order of the tree"],
    "DB.TXN.TXN": ["transaction", "schedule", "serializable", "serialisability", "serializability",
                   "conflict", "recoverable", "two-phase locking", "2pl", "lock", "concurrency control",
                   "cascadeless", "acid", "commit", "abort", "dirty read", "view serializable"],
    "COA.ISA.INSTR": ["instruction set", "instruction format", "opcode", "risc", "cisc",
                      "load-store", "machine instruction"],
    "COA.ISA.ADDR": ["addressing mode", "immediate addressing", "register addressing",
                     "indirect addressing", "relative addressing"],
    "COA.MEM.CACHE": ["cache", "hit ratio", "hit rate", "miss rate", "cache memory", "direct mapped",
                      "set associative", "block size", "cache line", "tag", "write through",
                      "write back", "cache hit"],
    "COA.MEM.HIER": ["memory hierarchy", "main memory", "memory access time", "average memory access",
                     "byte addressable", "memory module", "interleav"],
    "COA.PIPE.PIPE": ["pipeline", "pipelining", "pipelined", "stage", "hazard", "stall",
                      "data forwarding", "branch prediction", "speedup"],
    "COA.ALU.ALU": ["alu", "adder", "carry look-ahead", "carry lookahead", "booth",
                    "multiplication algorithm", "ripple carry"],
    "COA.ALU.CTRL": ["control unit", "microprogrammed", "microprogram", "hardwired", "microinstruction",
                     "control signal", "micro-operation", "control word"],
    "COA.IO.INTR": ["interrupt", "interrupt driven", "vectored interrupt", "isr", "daisy chain"],
    "COA.IO.DMA": ["dma", "direct memory access", "cycle stealing", "burst mode"],
    "CN.LAYER.LAYER": ["osi", "tcp/ip model", "layer", "encapsulation", "protocol data unit",
                       "packet switching", "circuit switching", "datagram"],
    "CN.DLL.ERR": ["error detection", "error correction", "crc", "cyclic redundancy", "checksum",
                   "hamming", "parity"],
    "CN.DLL.MAC": ["csma", "csma/cd", "csma/ca", "aloha", "ethernet", "mac protocol", "collision",
                   "backoff", "token ring", "minimum frame size"],
    "CN.DLL.SW": ["sliding window", "stop and wait", "go-back-n", "go back n", "selective repeat",
                  "flow control protocol", "sender window", "receiver window", "utilization",
                  "efficiency of"],
    "CN.ROUTE.IPV4": ["ipv4", "ip address", "ip header", "fragmentation", "ttl", "header checksum",
                      "ip packet", "ip datagram"],
    "CN.ROUTE.CIDR": ["subnet", "subnetting", "cidr", "subnet mask", "supernet", "network address",
                      "broadcast address", "host address"],
    "CN.ROUTE.NAT": ["nat", "network address translation", "private address"],
    "CN.ROUTE.ROUTE": ["routing", "distance vector", "link state", "rip", "ospf", "routing table",
                       "next hop", "shortest path routing", "count to infinity"],
    "CN.TCP.FLOW": ["flow control", "window size", "advertised window", "tcp"],
    "CN.TCP.CONG": ["congestion control", "slow start", "congestion window", "cwnd", "timeout",
                    "rtt", "round trip time", "tcp congestion"],
    "CN.TCP.CONN": ["connection establishment", "three way handshake", "three-way handshake",
                    "tcp connection", "sequence number", "syn", "ack"],
    "CN.APP.DNS": ["dns", "domain name", "name resolution", "name server"],
    "CN.APP.HTTP": ["http", "web", "url", "browser", "persistent connection", "proxy", "ftp",
                    "email", "smtp", "pop3"],
    "TOC.REG.RE": ["regular expression", "regular language", "regular set"],
    "TOC.REG.FA": ["finite automata", "finite automaton", "dfa", "nfa", "deterministic finite",
                   "non-deterministic finite", "minimal dfa", "minimization of", "equivalent states",
                   "state machine accepts", "transition diagram"],
    "TOC.PUMP": ["pumping lemma", "context-free language", "context free language", "cfl",
                 "not regular", "not context-free", "language is regular", "language is context"],
    "TOC.CFG.CFG": ["context-free grammar", "context free grammar", "cfg", "ambiguous", "grammar",
                    "production", "derivation", "leftmost", "rightmost", "language generated"],
    "TOC.CFG.PDA": ["pushdown automata", "pushdown automaton", "pda", "stack"],
    "TOC.TM.TM": ["turing machine", "turing machines", "tape", "halting"],
    "TOC.TM.UNDEC": ["undecidable", "decidable", "recursive language", "recursively enumerable",
                     "reduction", "halting problem", "membership problem", "emptiness problem",
                     "turing recognizable"],
}

def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9+#]+(?:[-'][a-z0-9+#]+)*", (text or "").lower()))

def _phrases_for(topic: dict) -> list[tuple[str, int]]:
    """(phrase, weight) pairs: topic name x2, concept names x3, curated lexicon x2."""
    out = [(t, 2) for t in {_norm(topic["name"])} if t]
    for c in topic.get("concepts", []):
        n = _norm(c["name"])
        if n:
            out.append((n, 3))
        for part in re.split(r"[:,;(]", c["name"]):
            p = _norm(part)
            if len(p.split()) >= 2 and p != n:
                out.append((p, 2))
    keys = [topic["node_id"]] + [c["node_id"] for c in topic.get("concepts", [])]
    for k in keys:
        for p in LEXICON.get(k, []):
            out.append((_norm(p), 2))
    return out

def build_lexicon(s: Session, taxonomy_version: str) -> list[dict]:
    """[{node_id, parent_id, name, phrases:[(phrase, weight)]}] from the live taxonomy."""
    return [{**t, "phrases": _phrases_for(t)} for t in topic_list(s, taxonomy_version)]

def score_topics(text: str, options: list[str], lex: list[dict],
                 block: str | None) -> list[tuple[str, float, list[str]]]:
    """Score every topic; returns [(topic_id, score, matched phrases)] best first.
    The GA/CS position hint restricts the candidate set when the layout is known."""
    hay = _norm((text or "") + " " + " ".join(options or []))
    results = []
    for t in lex:
        sec = t["parent_id"]
        if block == "GA" and sec != "GA":
            continue
        if block == "CS" and sec == "GA":
            continue
        total, matched = 0.0, []
        for phrase, w in t["phrases"]:
            if not phrase:
                continue
            n = hay.count(phrase)
            if n:
                words = len(phrase.split())
                hits = min(n, 3) if words > 1 else min(n, 2)
                # single generic words (stack, process, query, graph) are weak evidence
                total += w * (1 + 0.5 * (words - 1)) * hits * (0.5 if words == 1 else 1.0)
                matched.append(phrase)
        if total > 0:
            results.append((t["node_id"], total, matched))
    results.sort(key=lambda r: -r[1])
    return results

def advise_one(s: Session, question: Question, lex: list[dict], block_cache: dict,
               options: list[str] | None = None) -> dict:
    """Best-effort suggestion dict for ONE question (no DB writes)."""
    block = _question_block(s, question, block_cache)
    if options is None:
        options = [o.content or "" for o in sorted(question.options, key=lambda o: o.label)]
    scored = score_topics(question.text, options, lex, block)
    if scored:
        best, s1, matched = scored[0]
        s2 = scored[1][1] if len(scored) > 1 else 0.0
        margin = (s1 - s2) / s1 if s1 else 0.0
        conf = 0.30 + min(s1, 10.0) * 0.045 + margin * 0.15
        conf = round(min(conf, 0.85), 2)
        section = next(t["parent_id"] for t in lex if t["node_id"] == best)
        concepts = []
        for t in lex:
            if t["node_id"] == best:
                cmap = {(_norm(c["name"])): c["node_id"] for c in t.get("concepts", [])}
                for m in matched:
                    if m in cmap and cmap[m] not in concepts:
                        concepts.append(cmap[m])
                break
        out = {"section_id": section, "primary_topic_id": best, "confidence": conf,
               "score": round(s1, 2), "margin": round(margin, 2), "evidence": matched[:5],
               "concept_ids": concepts[:3], "paper_block": block}
    else:
        out = {"section_id": "GA" if block == "GA" else "", "primary_topic_id": "",
               "confidence": 0.0, "score": 0.0, "margin": 0.0, "evidence": [],
               "concept_ids": [], "paper_block": block}
    # weak signal or OCR text => human should look
    if out["score"] < 2.5 or out["margin"] < 0.25 or question.extraction_status == "ocr" and out["score"] < 5:
        out["flag"] = True
    else:
        out["flag"] = False
    return out

def run_local_classify(s: Session, taxonomy_version: str, paper_ids: list[str] | None = None,
                       reclassify: bool = False, flag_below: float = 0.45) -> dict:
    """Write heuristic suggestion rows. Same safety contract as run_classification:
    skip verified/validated, skip any existing suggestion unless reclassify=True, never
    invent a topic outside the taxonomy, flag weak matches. Returns counts."""
    lex = build_lexicon(s, taxonomy_version)
    run = ClassificationRun(model=HEURISTIC_MODEL, prompt_version=HEURISTIC_PROMPT_VERSION,
                            provider="local-heuristic")
    s.add(run); s.flush()
    counts = Counter(); blocks: dict = {}
    q = select(Question)
    if paper_ids:
        q = q.where(Question.paper_id.in_(paper_ids))
    for question in s.scalars(q):
        row, action = _classification_target(s, question, taxonomy_version, reclassify)
        counts[action] += 1
        if action.startswith("skip"):
            continue
        a = advise_one(s, question, lex, blocks)
        if not a["primary_topic_id"]:
            s.add(ReviewEvent(question_id=question.id, field="classification_unclassified",
                              before=None, after="no keyword signal", reviewer="local-heuristic",
                              note="heuristic found no topic signal; needs human review"))
            counts["no_signal"] += 1
            continue
        status = "flagged" if (a["flag"] or a["confidence"] < flag_below) else "suggested"
        if row is None:
            row = Classification(question_id=question.id, taxonomy_version=taxonomy_version,
                                 prompt_version=HEURISTIC_PROMPT_VERSION)
            s.add(row)
        row.run_id = run.id
        row.section_id = a["section_id"]; row.primary_topic_id = a["primary_topic_id"]
        row.topic_weight = {a["primary_topic_id"]: 1.0}
        row.concept_ids = a["concept_ids"]; row.prerequisite_ids = []
        row.what_it_tests = "keyword match: " + ", ".join(a["evidence"][:3])
        row.confidence = a["confidence"]
        row.agreement = None; row.combo_score = combo_score(1.0, a["confidence"])
        row.provider_votes = None; row.provider_count = 1
        row.evidence_quote = "; ".join(a["evidence"][:5])
        row.raw_response = {"score": a["score"], "margin": a["margin"], "paper_block": a["paper_block"]}
        row.provenance = "inferred"; row.status = status; row.model = HEURISTIC_MODEL
        counts["written_" + status] += 1
    s.commit()
    return dict(counts)
