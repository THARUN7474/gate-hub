"""Rebuild the question-bank workbook from the live database. Every number is
computed from DB rows (never hand-typed), so the workbook always matches
exports/*.csv. Regenerate after any re-extraction, key import, classification
or curation pass:

    python scripts/build_workbook.py --db-url sqlite:///data/gate_cse.sqlite \
        --out exports/GATE-2026-CS1-question-bank.xlsx
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from src.db.models import (AnswerKey, Classification, Document, Option, Paper,
                           Question, TaxonomyNode)
from src.db.session import make_session

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    import openpyxl
    from openpyxl.styles import Font
    with make_session(args.db_url) as s:
        nodes = {n.node_id: n for n in s.scalars(select(TaxonomyNode))}
        papers = {p.id: p for p in s.scalars(select(Paper))}
        questions = s.scalars(select(Question).order_by(Question.paper_id, Question.q_number)).all()
        cls = {c.question_id: c for c in s.scalars(select(Classification))}
        keys = {k.question_id: k for k in s.scalars(select(AnswerKey))}
        opts = {}
        for o in s.scalars(select(Option)):
            opts.setdefault(o.question_id, {})[o.label] = o.content
        docs = s.scalars(select(Document)).all()

        wb = openpyxl.Workbook()
        def sheet(title, header):
            ws = wb.create_sheet(title)
            ws.append(header)
            for cell in ws[1]:
                cell.font = Font(bold=True)
            return ws

        # Question Bank
        ws = sheet("Question Bank",
            ["Q#","Section (Subject)","Topic","Concepts","Prerequisite concepts","Type","Marks",
             "Official Key","What it tests","Conf.","Status","Page in CS1.pdf","Question text",
             "A","B","C","D","DATA CAVEATS (read before trusting text)","Source preview (see note)"])
        for q in questions:
            c = cls.get(q.id); k = keys.get(q.id)
            sec = nodes.get(c.section_id) if c else None
            top = nodes.get(c.primary_topic_id) if c else None
            concept_names = "; ".join(f"{cid} {nodes[cid].name}" for cid in (c.concept_ids or []) if cid in nodes) if c else ""
            prereq_names = "; ".join(f"{pid} {nodes[pid].name}" for pid in (c.prerequisite_ids or []) if pid in nodes) if c else ""
            o = opts.get(q.id, {})
            caveats = []
            if any(not (v or "").strip() for v in o.values()):
                caveats.append("FIGURE option(s): option text empty in extraction; the figure exists only in the PDF region")
            if q.needs_review and q.review_reason:
                caveats.append(q.review_reason)
            key_str = ""
            if k:
                key_str = ",".join(str(a) for a in (k.answer_list or []))
                if k.answer_min is not None:
                    key_str += f" [{k.answer_min}-{k.answer_max}]"
            preview = (f"Rendered on demand from the source PDF page {q.page_start}"
                       f" - open the app's Review Workspace or extract the stored region")
            ws.append([q.q_number,
                       f"{c.section_id} - {sec.name}" if sec else "", 
                       f"{c.primary_topic_id} {top.name}" if top else "",
                       concept_names, prereq_names,
                       q.q_type, q.marks, key_str,
                       (c.what_it_tests if c else "") or "", c.confidence if c else "",
                       c.status if c else "", q.page_start, q.text,
                       o.get("A",""), o.get("B",""), o.get("C",""), o.get("D",""),
                       "; ".join(caveats) or None, preview])

        # Subject Analysis
        ws = sheet("Subject Analysis", ["Section","Subject","Questions","1-mark","2-mark","Total marks","% of paper"])
        agg: dict[str, dict] = {}
        total_marks = sum(q.marks or 0 for q in questions)
        for q in questions:
            c = cls.get(q.id)
            if not c: continue
            d = agg.setdefault(c.section_id, {"q":0,"one":0,"two":0,"marks":0.0})
            d["q"] += 1; d["marks"] += q.marks or 0
            d["one" if (q.marks or 0) == 1 else "two"] += 1
        for sid, d in sorted(agg.items(), key=lambda kv: -kv[1]["marks"]):
            ws.append([sid, nodes[sid].name if sid in nodes else "", d["q"], d["one"], d["two"],
                       d["marks"], f"{round(100*d['marks']/total_marks)}%" if total_marks else ""])

        # Topic Analysis
        ws = sheet("Topic Analysis", ["Topic ID","Topic","Section","Questions","Marks","Question numbers"])
        tagg: dict[str, dict] = {}
        for q in questions:
            c = cls.get(q.id)
            if not c: continue
            d = tagg.setdefault(c.primary_topic_id, {"q":0,"marks":0.0,"qnos":[]})
            d["q"] += 1; d["marks"] += q.marks or 0; d["qnos"].append(f"Q{q.q_number}")
        for tid, d in sorted(tagg.items(), key=lambda kv: -kv[1]["marks"]):
            n = nodes.get(tid)
            ws.append([tid, n.name if n else "", n.parent_id if n else "", d["q"], d["marks"], ", ".join(d["qnos"])])

        # Syllabus (sections + topics + concepts with per-paper usage)
        ws = sheet("Syllabus 2027", ["ID","Name","Kind","Provenance","Questions in this paper","Marks in this paper","Official syllabus text (verbatim)"])
        concept_use: dict[str, dict] = {}
        for q in questions:
            c = cls.get(q.id)
            for cid in (c.concept_ids or []) if c else []:
                d = concept_use.setdefault(cid, {"q":0,"marks":0.0})
                d["q"] += 1; d["marks"] += q.marks or 0
        for nid, n in sorted(nodes.items()):
            if nid.endswith(".deprecated"): continue
            kind = n.level.upper() if n.level == "section" else n.level
            if n.level == "concept":
                d = concept_use.get(nid, {"q":0,"marks":0})
                ws.append([nid, n.name, kind, "inferred (curation - NOT official syllabus)", d["q"] or "", d["marks"] or "", None])
            elif n.level == "topic":
                d = tagg.get(nid)
                ws.append([nid, n.name + (" [DEPRECATED]" if n.deprecated else ""), kind,
                           "inferred (curation split of the official section text)",
                           d["q"] if d else "", d["marks"] if d else "", None])
            else:
                d = agg.get(nid)
                ws.append([nid, n.name, kind, "official (verbatim from the syllabus PDF)",
                           d["q"] if d else "", d["marks"] if d else "",
                           (n.syllabus_text or "")[:500]])

        # Verification
        ws = sheet("Verification", ["Check","Result","How it was verified"])
        from src.validation.validate import run_checks
        for chk in run_checks(s):
            ws.append([chk["check"], "PASS" if chk["ok"] else "FAIL", chk["details"] or "pipeline validation check"])

        # Sources
        ws = sheet("Sources", ["File","Role","sha256","Notes"])
        for d in docs:
            ws.append([d.file_path, d.doc_type, d.sha256, f"registered {d.ingested_at}"])

        # How to use (first sheet)
        ws = wb.active; ws.title = "How to use"
        rows = [
          ("GATE CS question bank - generated from the pipeline database", ""),
          ("", ""),
          ("What this is", "One real GATE paper run end-to-end through the extraction -> keys -> classification -> review pipeline."),
          ("Question Bank", "One row per question: subject, topic, concepts, type, marks, official key, extracted text/options."),
          ("Status column", "suggested = machine/curated proposal awaiting human verification; verified = human-confirmed in the Review Workspace. NOTHING is verified unless a human did it in the app."),
          ("Concepts / Prerequisites", "Concept ids are curated (provenance=inferred); prerequisite concepts derive mechanically from the curated edge set in taxonomy.yaml. Both await human review."),
          ("Source preview", "No images are stored: each question stores its page region and the app renders it from the original PDF on demand."),
          ("DATA CAVEATS", "Figure-only options have empty extracted text; fractions/exponents may be flattened in text. Trust the PDF region, not the text, for those rows."),
          ("Sheets", "Subject Analysis / Topic Analysis: marks by primary topic only (no double counting). Syllabus 2027: official section text verbatim; topic/concept splits are curation."),
          ("Regenerate", "python scripts/build_workbook.py --db-url <url> --out <xlsx> - rebuilds every number from the database."),
        ]
        for r in rows: ws.append(list(r))
        ws["A1"].font = Font(bold=True, size=14)
        from openpyxl.styles import Alignment
        WRAP_MIN_LEN = 40          # columns whose content can be long get wrapped
        for title in wb.sheetnames:
            ws2 = wb[title]
            wrap_cols = set()
            for col in ws2.columns:
                letter = col[0].column_letter
                longest = max((len(str(c.value)) for c in col if c.value is not None), default=8)
                width = min(60, longest + 2)
                ws2.column_dimensions[letter].width = max(10, width)
                if longest >= WRAP_MIN_LEN:
                    wrap_cols.add(letter)
                    ws2.column_dimensions[letter].width = 55
            for row in ws2.iter_rows():
                lines_needed = 1
                for cell in row:
                    if cell.column_letter in wrap_cols:
                        cell.alignment = Alignment(wrap_text=True, vertical="top")
                        if cell.value:
                            est = -(-len(str(cell.value)) // 50)  # ~50 chars per line at width 55
                            lines_needed = max(lines_needed, min(est, 12))
                    else:
                        cell.alignment = Alignment(vertical="top")
                if lines_needed > 1:  # explicit height: non-Excel renderers don't auto-fit
                    ws2.row_dimensions[row[0].row].height = 13.8 * lines_needed
            ws2.freeze_panes = "A2"
        wb.move_sheet("How to use", offset=-len(wb.sheetnames)+1)
        wb.save(args.out)
        print(f"workbook written: {args.out} ({len(questions)} questions)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
