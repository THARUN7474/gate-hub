"""Engine & Pipeline screen: live facts about how labels were made and which stage the project is in,
plus Graphviz DOT builders for the diagrams (pure strings - no graphviz package needed;
st.graphviz_chart renders DOT in the browser)."""
from __future__ import annotations
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import (AnswerKey, BenchmarkSample, Classification, ClassificationProposal, Option, Paper,
                         Question, ReviewEvent, TaxonomyNode)

# dark-theme friendly Graphviz styling
_G = ('bgcolor="transparent"; fontname="Inter"; fontcolor="#e6e6e6"; '
      'node [shape=box, style="rounded,filled", fontname="Inter", fontsize=11, fontcolor="#f2f2f2", '
      'color="#5b6170", fillcolor="#262a33", margin="0.18,0.08"]; '
      'edge [color="#8a8f98", fontname="Inter", fontsize=9, fontcolor="#b8bcc4"];')
FILL = {"done": "#1f5f3a", "doing": "#7a5a12", "todo": "#3a3f4a", "optional": "#2d3550", "truth": "#1f5f3a",
        "opinion": "#3b2f5c", "data": "#23415f"}


def _q(s: str) -> str:
    return str(s).replace("\\", "/").replace('"', "'")


def label_sources(s: Session) -> list[dict]:
    """Who made the live labels, in plain words, with counts."""
    rows = s.execute(select(Classification.model, Classification.status, func.count())
                     .group_by(Classification.model, Classification.status)).all()
    agg: dict[str, dict] = {}
    for model, status, n in rows:
        m = model or "unknown"
        if m.startswith("claude-agent-manual"):
            who = "Claude, chat-assisted batches (first pass, no API key)"
        elif m.startswith("ai-review:"):
            who = "Claude as AI reviewer (created labels for the 18 historical SE questions)"
        elif "+ ai-review" in m:
            who = "First pass, topic corrected by the AI reviewer"
        elif m.startswith("mock"):
            who = "Mock (offline placeholder)"
        else:
            who = f"API run: {m}"
        d = agg.setdefault(who, {"made by": who, "labels": 0, "suggested": 0, "flagged": 0, "verified": 0})
        d["labels"] += n
        d[status if status in ("suggested", "flagged", "verified") else "suggested"] += n
    return sorted(agg.values(), key=lambda d: -d["labels"])


def counts(s: Session) -> dict:
    c = lambda q: s.scalar(q) or 0  # noqa: E731
    cls = dict(s.execute(select(Classification.status, func.count()).group_by(Classification.status)).all())
    prov = dict(s.execute(select(ClassificationProposal.provider, func.count(func.distinct(ClassificationProposal.question_id)))
                          .group_by(ClassificationProposal.provider)).all())
    bench = dict(s.execute(select(BenchmarkSample.status, func.count()).group_by(BenchmarkSample.status)).all())
    nodes = dict(s.execute(select(TaxonomyNode.level, func.count()).where(TaxonomyNode.deprecated == False)  # noqa: E712
                           .group_by(TaxonomyNode.level)).all())
    return {
        "papers": c(select(func.count()).select_from(Paper)),
        "questions": c(select(func.count()).select_from(Question)),
        "options": c(select(func.count()).select_from(Option)),
        "keys": c(select(func.count()).select_from(AnswerKey)),
        "ocr": c(select(func.count()).select_from(Question).where(Question.extraction_status == "ocr")),
        "extraction_issues": c(select(func.count()).select_from(Question).where(Question.needs_review == True)),  # noqa: E712
        "labelled": sum(cls.values()), "suggested": cls.get("suggested", 0), "flagged": cls.get("flagged", 0),
        "verified": cls.get("verified", 0),
        "with_concepts": c(select(func.count()).select_from(Classification).where(
            Classification.concept_ids.isnot(None), func.json_array_length(Classification.concept_ids) > 0))
        if s.bind.dialect.name == "sqlite" else None,
        "ai_reviewed": c(select(func.count(func.distinct(ReviewEvent.question_id))).where(ReviewEvent.field == "ai_review")),
        "api_proposals": sum(n for p, n in prov.items() if p not in ("ai-review", "openai-decisions", "jev")),
        "decision": prov.get("openai-decisions", 0) + prov.get("jev", 0),
        "bench_total": sum(bench.values()), "bench_gold": bench.get("gold_verified", 0),
        "sections": nodes.get("section", 0), "topics": nodes.get("topic", 0), "concepts": nodes.get("concept", 0),
    }


def stage_rows(k: dict) -> list[dict]:
    """The CSE pipeline, stage by stage, with live state."""
    def st(done, total):
        return "done" if total and done >= total else ("doing" if done else "todo")
    return [
        {"stage": "1. Collect source PDFs", "state": "done",
         "detail": f"{k['papers']} papers 2011-2026 in data/raw (2007-2010 deferred) + 2027 CS and GA syllabus PDFs"},
        {"stage": "2. Register papers (manifest)", "state": "done", "detail": "manifests/papers.yaml: file, pages, layout, key source per session"},
        {"stage": "3. Extract questions", "state": "done",
         "detail": f"{k['questions']:,} questions, {k['options']:,} options, PDF regions stored; {k['ocr']} read by OCR"},
        {"stage": "4. Load answer keys", "state": "done", "detail": f"{k['keys']:,} official keys; 9 papers have none (never guessed)"},
        {"stage": "5. Reconcile (65 questions / 100 marks)", "state": "done", "detail": "every paper reconciles; `validate` 10/10"},
        {"stage": "6. Syllabus taxonomy", "state": "done",
         "detail": f"{k['sections']} sections, {k['topics']} topics, {k['concepts']} concepts (taxonomy.yaml)"},
        {"stage": "7. First-pass labels", "state": st(k["labelled"], k["questions"]),
         "detail": f"{k['labelled']:,} of {k['questions']:,} labelled (Claude, chat-assisted)"},
        {"stage": "8. Fix extraction issues", "state": "doing" if k["extraction_issues"] else "done",
         "detail": f"{k['extraction_issues']} questions still flagged by the extractor"},
        {"stage": "9. AI review (second opinion)", "state": "doing" if k["ai_reviewed"] else "todo",
         "detail": f"{k['ai_reviewed']} reviewed (2026 CS-2, benchmark, SE questions)"},
        {"stage": "10. Benchmark gold (your gold set)", "state": st(k["bench_gold"], k["bench_total"]),
         "detail": f"{k['bench_gold']} of {k['bench_total']} verified by you  <- YOU ARE HERE"},
        {"stage": "11. API second opinion (FreeLLMAPI)", "state": "optional" if not k["api_proposals"] else "doing",
         "detail": f"{k['api_proposals']} questions; optional, free via the router"},
        {"stage": "12. Decision models", "state": "optional" if not k["decision"] else "doing",
         "detail": f"{k['decision']} questions; optional, paid, after gold exists"},
        {"stage": "13. Human verification (all)", "state": st(k["verified"], k["questions"]),
         "detail": f"{k['verified']:,} of {k['questions']:,} verified"},
        {"stage": "14. Enrichment (concepts, what-it-tests)", "state": "doing" if k.get("with_concepts") else "todo",
         "detail": (f"{k['with_concepts']} labels carry concepts" if k.get("with_concepts") is not None else "partial")},
        {"stage": "15. Analysis & exports", "state": "doing",
         "detail": "matrices and reports work now on suggested labels; trustworthy as verification grows"},
    ]


def pipeline_dot(k: dict) -> str:
    """End-to-end flow; colour = live state."""
    rows = {r["stage"].split(". ", 1)[0]: r["state"] for r in stage_rows(k)}
    f = lambda n: FILL[rows[n]]  # noqa: E731
    return f'''digraph P {{ rankdir=LR; {_G} nodesep=0.25; ranksep=0.35;
  subgraph cluster_in {{ label="INPUT"; color="#5b6170"; fontcolor="#b8bcc4";
    pdf [label="Question PDFs\\n{k['papers']} papers", fillcolor="{f('1')}"];
    keyp [label="Answer-key PDFs\\n{k['keys']:,} keys", fillcolor="{f('4')}"];
    syl [label="2027 syllabus PDFs\\nCS + GA", fillcolor="{f('6')}"]; }}
  subgraph cluster_ex {{ label="EXTRACT"; color="#5b6170"; fontcolor="#b8bcc4";
    man [label="Manifest\\npages, layout", fillcolor="{f('2')}"];
    ext [label="Extract\\ntext / OCR, options,\\nPDF region", fillcolor="{f('3')}"];
    rec [label="Reconcile\\n65 Q / 100 marks", fillcolor="{f('5')}"];
    tax [label="Taxonomy\\n{k['sections']} sections > {k['topics']} topics\\n> {k['concepts']} concepts", fillcolor="{f('6')}"]; }}
  subgraph cluster_lab {{ label="LABEL"; color="#5b6170"; fontcolor="#b8bcc4";
    first [label="First-pass label\\nClaude (chat batches)\\n{k['labelled']:,} questions", fillcolor="{f('7')}"];
    air [label="AI review\\nopinion: {k['ai_reviewed']}", fillcolor="{FILL['opinion']}"];
    api [label="API proposals\\nFreeLLMAPI: {k['api_proposals']}", fillcolor="{FILL['opinion']}", style="rounded,filled,dashed"];
    dec [label="Decision models\\nJev / OpenAI: {k['decision']}", fillcolor="{FILL['opinion']}", style="rounded,filled,dashed"]; }}
  subgraph cluster_rev {{ label="HUMAN REVIEW"; color="#5b6170"; fontcolor="#b8bcc4";
    fix [label="Fix extraction\\n{k['extraction_issues']} open", fillcolor="{f('8')}"];
    gold [label="Benchmark gold\\n{k['bench_gold']} / {k['bench_total']}", fillcolor="{f('10')}", penwidth=2.5, color="#f0b429"];
    ver [label="Verified labels\\n{k['verified']:,} / {k['questions']:,}", fillcolor="{f('13')}"]; }}
  out [label="Analysis\\nmatrices, topic report,\\nexports", fillcolor="{f('15')}"];
  pdf -> man -> ext -> rec; keyp -> rec; syl -> tax;
  rec -> first; tax -> first;
  first -> air [style=dashed, label="2nd opinion"]; first -> api [style=dashed]; first -> dec [style=dashed];
  rec -> fix; first -> gold; air -> gold [style=dotted, label="hint"]; api -> gold [style=dotted]; dec -> gold [style=dotted];
  fix -> ver; gold -> ver [label="then the rest"]; ver -> out; first -> out [style=dotted, label="until verified"];
}}'''


def question_model_dot() -> str:
    """What one question record holds and how it links to the syllabus."""
    return f'''digraph Q {{ rankdir=LR; {_G}
  paper [label="Paper\\nGATE-CS-2011-S1\\nyear, session, PDF", fillcolor="{FILL['data']}"];
  q [label="Question\\nid, Q number, printed label\\nmarks (1/2), type MCQ/MSQ/NAT\\ntext + PDF region (the truth)", fillcolor="{FILL['data']}"];
  opt [label="Options A-D", fillcolor="{FILL['data']}"];
  key [label="Official answer key\\n(or 'missing', never guessed)", fillcolor="{FILL['data']}"];
  lab [label="Label (one per question)\\nstatus: suggested / flagged / verified\\nconfidence, model", fillcolor="#3a3f4a"];
  sec [label="Section (subject)\\ne.g. DL Digital Logic", fillcolor="{FILL['truth']}"];
  top [label="Primary topic (chapter)\\ne.g. DL.CIRC Combinational\\nand sequential circuits", fillcolor="{FILL['truth']}"];
  con [label="Concepts (0..n)\\ne.g. DL.CIRC.SEQ", fillcolor="{FILL['truth']}"];
  sec2 [label="Secondary topics\\n(tags, never counted)", fillcolor="#3a3f4a"];
  ops [label="Opinions\\nAI review, API proposals,\\ndecision models", fillcolor="{FILL['opinion']}"];
  ev [label="Audit log\\nevery change: who, old, new,\\nwhen; 5 review checks", fillcolor="#3a3f4a"];
  bm [label="Gold set (385)\\nverified by you only", fillcolor="#7a5a12"];
  paper -> q [label="65 per paper"]; q -> opt; q -> key; q -> lab; lab -> sec -> top -> con;
  lab -> sec2 [style=dashed]; q -> ops [style=dashed]; q -> ev; q -> bm [style=dashed];
}}'''


def lifecycle_dot() -> str:
    return f'''digraph L {{ rankdir=LR; {_G}
  u [label="unclassified\\n(no label)", fillcolor="#3a3f4a"];
  s [label="suggested\\nmachine guess", fillcolor="#23415f"];
  f [label="flagged\\ndoubtful", fillcolor="#7a5a12"];
  v [label="verified\\nyou approved it", fillcolor="#1f5f3a", penwidth=2.5, color="#3ecf8e"];
  g [label="benchmark gold\\n(if sampled)", fillcolor="#1f5f3a"];
  u -> s [label="machine labels it"]; u -> f [label="low confidence"];
  s -> f [label="Flag (AI or you)"]; f -> s [label="re-label", style=dashed];
  s -> v [label="5 checks pass + Verify"]; f -> v [label="correct + Verify"];
  v -> g [label="sampled question"]; v -> f [label="you re-flag", style=dashed];
}}'''


def question_dot(s: Session, qid: str) -> str:
    """Live diagram for one real question."""
    q = s.get(Question, qid)
    p = s.get(Paper, q.paper_id)
    c = s.scalar(select(Classification).where(Classification.question_id == qid))
    k = s.scalar(select(AnswerKey).where(AnswerKey.question_id == qid))
    names = dict(s.execute(select(TaxonomyNode.node_id, TaxonomyNode.name)).all())
    nopt = s.scalar(select(func.count()).select_from(Option).where(Option.question_id == qid)) or 0
    lines = [f"digraph X {{ rankdir=LR; {_G}",
             f'p [label="{_q(p.id)}\\nyear {p.year}, {_q(p.session)}", fillcolor="{FILL["data"]}"];',
             f'q [label="{_q(q.printed_label or "Q " + str(q.q_number))}  ({_q(qid)})\\n{q.marks or 0:g} mark(s), '
             f'{_q(q.q_type or "?")}, {nopt} options\\n{"OCR" if q.extraction_status == "ocr" else "digital text"}'
             f'{" - EXTRACTION ISSUE" if q.needs_review else ""}", fillcolor="{"#7a5a12" if q.needs_review else FILL["data"]}"];',
             f'k [label="Key: {_q(k.answer_list) if k else "missing (never guessed)"}", fillcolor="{FILL["data"] if k else "#3a3f4a"}"];',
             "p -> q; q -> k;"]
    if c:
        col = {"verified": "#1f5f3a", "flagged": "#7a5a12"}.get(c.status, "#23415f")
        lines += [f'l [label="Label: {c.status}\\nconf {c.confidence or 0:.2f}\\n{_q((c.model or "")[:34])}", fillcolor="{col}"];',
                  f'sec [label="Subject\\n{_q(names.get(c.section_id, c.section_id))}", fillcolor="{FILL["truth"]}"];',
                  f'top [label="Topic\\n{_q(names.get(c.primary_topic_id, c.primary_topic_id))}", fillcolor="{FILL["truth"]}"];',
                  "q -> l; l -> sec -> top;"]
        for i, cid in enumerate(c.concept_ids or []):
            lines += [f'c{i} [label="Concept\\n{_q(names.get(cid, cid))}", fillcolor="{FILL["truth"]}"];', f"top -> c{i};"]
    else:
        lines += ['l [label="no label yet", fillcolor="#3a3f4a"]; q -> l;']
    for i, e in enumerate(s.scalars(select(ReviewEvent).where(ReviewEvent.question_id == qid,
                                                              ReviewEvent.field == "ai_review").order_by(ReviewEvent.id))):
        try:
            d = json.loads(e.after or "{}")
        except ValueError:
            d = {}
        lines += [f'a{i} [label="AI review: {_q(d.get("verdict"))}\\n-> {_q(names.get(d.get("primary_topic_id"), d.get("primary_topic_id")))}", '
                  f'fillcolor="{FILL["opinion"]}"];', f"q -> a{i} [style=dashed];"]
    lines.append("}")
    return "\n".join(lines)


def taxonomy_dot(s: Session, section_id: str) -> str:
    nodes = s.scalars(select(TaxonomyNode).where(TaxonomyNode.deprecated == False)).all()  # noqa: E712
    by = {n.node_id: n for n in nodes}
    sec = by[section_id]
    used = dict(s.execute(select(Classification.primary_topic_id, func.count())
                          .where(Classification.section_id == section_id)
                          .group_by(Classification.primary_topic_id)).all())
    out = [f"digraph T {{ rankdir=LR; {_G} ranksep=0.5;",
           f'S [label="{_q(sec.name)}\\n({section_id})", fillcolor="{FILL["truth"]}"];']
    for t in [n for n in nodes if n.level == "topic" and n.parent_id == section_id]:
        tid = t.node_id.replace(".", "_")
        out += [f'{tid} [label="{_q(t.name)}\\n{used.get(t.node_id, 0)} questions", fillcolor="{FILL["data"]}"];',
                f"S -> {tid};"]
        for cn in [n for n in nodes if n.level == "concept" and n.parent_id == t.node_id]:
            cid = cn.node_id.replace(".", "_")
            out += [f'{cid} [label="{_q(cn.name)}", fillcolor="#262a33", fontsize=9];', f"{tid} -> {cid};"]
    out.append("}")
    return "\n".join(out)
