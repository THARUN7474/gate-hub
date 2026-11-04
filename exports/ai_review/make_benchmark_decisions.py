"""Builds benchmark.decisions.json from Claude's question-by-question AI review (5 Nov 2026).
The judgements below were made by reading each question's text, options and key in chat.
AI review only - never human verification, never benchmark gold."""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
src = json.loads((HERE / "benchmark.json").read_text(encoding="utf8"))
P = "GATE-CS-"
corr = {
 "2011-S1-Q49": ("PDS", "PDS.REC", 0.7, "Tracing a recursive function (sum of base-r digits of n) is Recursion; C syntax is incidental. OCR noise in the stem."),
 "2013-S4-Q01": ("CN", "CN.TCP", 0.65, "Asks which TRANSPORT protocol (TCP/UDP) each application uses - transport layer, not application-layer detail; concept CN.APP.DNS would be removed."),
 "2013-S4-Q50": ("CD", "CD.OPT", 0.6, "Minimum registers for a code segment with dead variables = liveness / register allocation (compiler), not ISA design."),
 "2014-S1-Q47": ("DL", "DL.NUM", 0.5, "Picking 1,2,4,8,16 coins encodes the heavy bags in binary (323-310=13=01101b): binary number representation. Puzzle-like, low confidence."),
 "2014-S3-Q20": ("PDS", "PDS.LIN", 0.6, "In-place swap over a 2-D array (net effect: matrix unchanged) - arrays, not C-language semantics."),
}
flags = {
 "2011-S1-Q15": ("DL", "DL.CIRC", 0.85, "EXTRACTION: stored as NAT but the four MCQ options (9, 8, 512, 258) are inside the stem. Topic correct."),
 "2011-S1-Q51": ("DL", "DL.CIRC", 0.8, "EXTRACTION: option D carries the page marker 14/20. Figure-based; topic correct."),
 "2013-S1-Q47": ("EM", "EM.DM", 0.85, "EXTRACTION: two-column options - A and B each hold two formulas, C and D are empty. Topic correct."),
 "2013-S2-Q23": ("EM", "EM.LA", 0.8, "EXTRACTION: determinant matrices flattened into an unreadable number stream; check the PDF crop. Topic correct."),
 "2013-S2-Q65": ("GA", "GA.VA", 0.8, "EXTRACTION: option D ends with END OF THE QUESTION PAPER. Topic correct."),
 "2013-S3-Q09": ("DL", "DL.NUM", 0.9, "EXTRACTION: options B/C carry stray fraction fragments of a neighbouring question. Topic correct."),
 "2013-S3-Q65": ("GA", "GA.QA", 0.8, "EXTRACTION: series formula garbled and option C ends with END OF THE QUESTION PAPER. Topic correct."),
 "2013-S4-Q27": (None, None, 0.0, "TAXONOMY GAP: software-engineering cohesion/coupling - no 2027 node. Candidate for the proposed deprecated LEGACY.SE category; not forced into a topic."),
 "2014-S1-Q31": ("DB", "DB.NF", 0.9, "EXTRACTION: only 2 options stored - option D glued onto B, option C missing; q_type empty. Topic correct (candidate key from FDs)."),
 "2014-S2-Q23": ("ALGO", "ALGO.CMPLX", 0.85, "EXTRACTION: recurrence lost its argument (T(n) = 2T + log n; should be 2T(n/2)). Topic correct."),
 "2014-S2-Q46": ("TOC", "TOC.REG", 0.7, "EXTRACTION: stem is OCR noise (L1/L2 unreadable); option D ends with stray TE. Topic plausible from options."),
 "2015-S1-Q17": ("PDS", "PDS.TREE", 0.9, "EXTRACTION: 2015 response-sheet residue in options (A x B x C x D / Options : 1. 3. 4) - must never be read as a key. Topic correct."),
 "2015-S1-Q32": ("DB", "DB.IDX", 0.9, "EXTRACTION: 2015 response-sheet residue in options. Topic correct."),
 "2015-S1-Q37": ("PDS", "PDS.TREE", 0.9, "EXTRACTION: 2015 response-sheet residue in options C/D. Topic correct (binary heap insert)."),
 "2015-S1-Q42": ("EM", "EM.DM", 0.8, "EXTRACTION: options garbled (B holds C/D fragments, C=4, D empty). Topic correct (lattice)."),
 "2015-S2-Q22": ("PDS", "PDS.TREE", 0.75, "EXTRACTION: all four options glued into A with response-sheet residue; B/C/D are noise. Topic plausible (heaps)."),
 "2015-S2-Q28": ("CD", "CD.RUNTIME", 0.55, "EXTRACTION: options B/C/D are noise. TOPIC: AST and CFG are intermediate representations (CD.RUNTIME covers intermediate code), not data-flow optimisation."),
 "2015-S2-Q47": ("ALGO", "ALGO.DESIGN", 0.9, "EXTRACTION: response-sheet residue on option D. Topic correct."),
 "2015-S3-Q10": ("GA", "GA.AA", 0.8, "EXTRACTION: response-sheet residue + running header on option D. Topic correct."),
 "2015-S3-Q14": ("OS", "OS.PROC", 0.85, "EXTRACTION: response-sheet residue in option A. Topic correct."),
 "2015-S3-Q35": ("CN", "CN.DLL", 0.9, "EXTRACTION: response-sheet residue in option A. Topic correct (CSMA/CD)."),
 "2015-S3-Q55": ("ALGO", "ALGO.GRAPH", 0.9, "EXTRACTION: stem ends with the printed Correct Answer : 995 from the 2015 response sheet - strip it (never use 2015 printed answers). 500+5*99=995. Topic correct."),
 "2016-S1-Q10": ("GA", "GA.QA", 0.75, "EXTRACTION: option A ends with END OF THE QUESTION PAPER. Topic correct."),
 "2017-S1-Q44": ("EM", "EM.DM", 0.6, "TAXONOMY: RSA key generation is not in the 2027 syllabus; the computation (inverse of 35 mod 192) is number theory - nearest EM.DM."),
 "2017-S2-Q30": ("ALGO", "ALGO.CMPLX", 0.85, "EXTRACTION: recurrence garbled by OCR. Topic correct."),
 "2018-S1-Q11": ("EM", "EM.DM", 0.85, "EXTRACTION: generating-function options lost their fraction structure. Topic correct."),
 "2019-S1-Q62": ("PDS", "PDS.C", 0.85, "EXTRACTION: loop body garbled by OCR, closing brace missing. Topic correct."),
 "2020-S1-Q56": ("PDS", "PDS.C", 0.7, "EXTRACTION: fun1 and fun2 printed side by side are interleaved line by line. Topic: static locals + recursion (PDS.C acceptable, PDS.REC defensible)."),
 "2022-S1-Q15": ("PDS", "PDS.LIN", 0.9, "EXTRACTION: Theta expressions lost in the options. Topic correct."),
 "2022-S1-Q36": ("EM", "EM.DM", 0.8, "EXTRACTION: generating-function formulas garbled (OCR). Topic correct."),
}
KEY_OK = {"2014-S1-Q08", "2016-S1-Q49", "2019-S1-Q35", "2020-S1-Q30", "2021-S2-Q34", "2024-S1-Q13", "2024-S2-Q38",
          "2024-S2-Q63", "2025-S1-Q14", "2025-S2-Q62", "2023-S1-Q12", "2024-S1-Q41", "2026-S1-Q05", "2012-S1-Q14",
          "2013-S1-Q07"}
FIG = {"2012-S1-Q26", "2014-S3-Q55", "2021-S1-Q38", "2021-S2-Q27", "2022-S1-Q22", "2011-S1-Q51", "2013-S1-Q33"}
done = {P + x for x in ("2026-S2-Q07", "2026-S2-Q14", "2026-S2-Q27", "2026-S2-Q53")}   # reviewed with the 2026-S2 paper

decisions = []
for q in src["questions"]:
    qid = q["question_id"]
    if qid in done:
        continue
    k = qid[len(P):]; c = q["current_label"] or {}
    checks = {"text_readable": k not in ("2014-S2-Q46", "2013-S2-Q23"), "options_complete": k not in flags,
              "key_recomputed_matches": True if k in KEY_OK else None, "figure_seen": False if k in FIG else None,
              "taxonomy_fit": k not in ("2013-S4-Q27", "2017-S1-Q44")}
    if k in corr:
        sec, top, conf, note = corr[k]
        decisions.append({"question_id": qid, "verdict": "correct", "section_id": sec, "primary_topic_id": top,
                          "concept_ids": [], "confidence": conf, "checks": checks, "note": note})
    elif k in flags:
        sec, top, conf, note = flags[k]
        decisions.append({"question_id": qid, "verdict": "flag", "section_id": sec, "primary_topic_id": top,
                          "confidence": conf, "checks": checks, "note": note})
    else:
        note = "Topic matches what the question tests."
        if k in FIG: note += " Figure not visible to a text-only reviewer; judged from the stem."
        if k in KEY_OK: note += " Official key recomputed and matches."
        decisions.append({"question_id": qid, "verdict": "agree", "section_id": c["section_id"],
                          "primary_topic_id": c["primary_topic_id"], "concept_ids": c["concept_ids"],
                          "confidence": 0.85, "checks": checks, "note": note})
assert len(decisions) == 116, len(decisions)
out = {"reviewer": "claude-opus-5-5", "reviewed_on": "2026-11-05",
       "method": "read text+options+key one by one in chat; no API call. The 4 sampled 2026-S2 questions are in "
                 "GATE-CS-2026-S2.decisions.json", "decisions": decisions}
(HERE / "benchmark.decisions.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")
print(Counter(d["verdict"] for d in decisions))
