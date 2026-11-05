"""AI REVIEW pass: an AI (e.g. Claude in chat, or a model behind FreeLLMAPI) reads questions one by
one the way a human reviewer would and records its own verdict - ALWAYS labelled as an AI review,
NEVER as human verification and NEVER as benchmark gold.

    python scripts/ai_review.py export --paper GATE-CS-2026-S2          # -> exports/ai_review/GATE-CS-2026-S2.json
    python scripts/ai_review.py export --benchmark                      # -> exports/ai_review/benchmark.json
    python scripts/ai_review.py export --next 20                        # next 20 not yet reviewed with v2
                                                                        # (skips extraction issues + un-gold benchmark)
    python scripts/ai_review.py progress                                # how far the v2 pass has got
    python scripts/ai_review.py import exports/ai_review/<file>.decisions.json            # DRY RUN
    python scripts/ai_review.py import exports/ai_review/<file>.decisions.json --yes      # backup, then write

v2 (prompts/ai_review_v2.md, the default) adds: question_type + type_check, secondary topics, why_this_topic,
alternatives_considered, solution_sketch, my_answer, key_check, difficulty, flag_reason. v2 NEVER changes a live
label: a 'correct' verdict (or a type that differs) only records the opinion and FLAGS the live label for you.
v1 files (prompt_version "ai-review-v1") keep the old behaviour below.

Decisions file: {"reviewer": "claude-opus-5-5", "prompt_version": "ai-review-v2", "decisions": [ {
    "question_id": "GATE-CS-2026-S2-Q01",
    "verdict": "agree" | "correct" | "flag",
    "section_id": "GA", "primary_topic_id": "GA.VA",          # the AI reviewer's own label (always given)
    "concept_ids": [...], "what_it_tests": "...",             # optional
    "confidence": 0.9,
    "checks": {"source_fidelity": true, "options_ok": true, "key_ok": true, "taxonomy_fit": true},
    "note": "why" } ]}

What import writes (all append-only / audited):
  1. classification_proposals row, provider='ai-review', model='<reviewer>', prompt_version='ai-review-v1'
     - an independent second opinion; `evaluate-benchmark --provider ai-review` scores it against YOUR
     gold later, `proposals-report` shows agreement. Analytics never read proposals.
  2. review_events row field='ai_review', reviewer='<reviewer> (AI review - not human verification)',
     after = the verdict JSON - visible in the Review Workspace audit history.
  3. verdict 'correct' on a question with NO label: a first label is created (status suggested).
     verdict 'correct' on a question that is NOT in the benchmark sample and NOT human-reviewed: the
     live label is changed to the AI reviewer's label (status stays 'suggested', model notes the AI
     review), each changed field logged with before/after. On BENCHMARK questions the live label is
     never changed, so your gold review stays your own independent judgement.
  4. verdict 'flag': live status -> 'flagged' with the note (never on verified/validated rows).
Nothing is ever set to verified. Benchmark gold is never written."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import func, select  # noqa: E402
from src.db.models import (AnswerKey, BenchmarkSample, Classification, ClassificationProposal,  # noqa: E402
                           ClassificationRun, Option, Paper, Question, ReviewEvent, TaxonomyNode, utcnow)
from src.db.session import make_session  # noqa: E402
from src.classification.classify import question_content_hash  # noqa: E402

TAXV = "gate-cs-2027"
PROVIDER = "ai-review"
PROMPT_VERSION = "ai-review-v2"
PROMPT_FILE = ROOT / "prompts" / "ai_review_v2.md"
TYPES = ("MCQ", "MSQ", "NAT")
OUT = ROOT / "exports" / "ai_review"
INSTRUCTIONS_V1 = (
    "Review each question like a human reviewer: read the text, options and official key; decide which "
    "GATE CS 2027 section/topic it actually tests (from the taxonomy below); check the extracted text and "
    "options against the PDF crop where available (source_fidelity), that options look complete (options_ok) "
    "and that the key is plausible (key_ok). verdict: agree (current label is right), correct (give your "
    "label), flag (extraction problem or genuinely ambiguous - say why). Never invent concepts; leave "
    "concept_ids empty if unsure. This is an AI review and is recorded as such - it is never human verification.")

def instructions() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else INSTRUCTIONS_V1

V2_FIELDS = ("question_type", "type_check", "secondary_topic_ids", "why_this_topic", "alternatives_considered",
             "solution_sketch", "my_answer", "key_check", "difficulty", "flag_reason")

def taxonomy(s) -> dict:
    nodes = s.scalars(select(TaxonomyNode).where(TaxonomyNode.version == TAXV, TaxonomyNode.deprecated == False)).all()  # noqa: E712
    secs = {n.node_id: {"name": n.name, "syllabus_text": n.syllabus_text, "topics": {}}
            for n in nodes if n.level == "section"}
    for n in nodes:
        if n.level == "topic" and n.parent_id in secs:
            secs[n.parent_id]["topics"][n.node_id] = {"name": n.name, "concepts": {}}
    for n in nodes:
        if n.level == "concept":
            for sec in secs.values():
                if n.parent_id in sec["topics"]:
                    sec["topics"][n.parent_id]["concepts"][n.node_id] = n.name
    return secs

def _qrow(s, q: Question, sampled: dict) -> dict:
    opts = {o.label: o.content for o in s.scalars(select(Option).where(Option.question_id == q.id).order_by(Option.label))}
    k = s.scalar(select(AnswerKey).where(AnswerKey.question_id == q.id))
    c = s.scalar(select(Classification).where(Classification.question_id == q.id))
    key = None
    if k:
        key = {"kind": k.answer_kind, "answer": k.answer_list, "min": k.answer_min, "max": k.answer_max}
    p = s.get(Paper, q.paper_id)
    return {"question_id": q.id, "year": p.year if p else None, "session": p.session if p else None,
            "q_number": q.q_number, "label": q.printed_label, "marks": q.marks, "type": q.q_type, "text": q.text,
            "options": opts, "key": key, "image": q.image_path,
            "extraction": {"status": q.extraction_status, "needs_review": q.needs_review, "reason": q.review_reason},
            "current_label": None if c is None else {
                "section_id": c.section_id, "primary_topic_id": c.primary_topic_id, "concept_ids": c.concept_ids,
                "what_it_tests": c.what_it_tests, "status": c.status, "confidence": c.confidence, "model": c.model},
            "in_benchmark": q.id in sampled}

def reviewed_v2(s) -> set:
    return set(s.scalars(select(ClassificationProposal.question_id).where(
        ClassificationProposal.provider == PROVIDER, ClassificationProposal.prompt_version == PROMPT_VERSION))) | {
        e.question_id for e in s.scalars(select(ReviewEvent).where(ReviewEvent.field == "ai_review"))
        if f'"prompt_version": "{PROMPT_VERSION}"' in (e.after or "")}

def eligible(s) -> tuple[list, dict]:
    """Questions the v2 pass may review NOW and why the rest are held back. The GOLD SET comes first (all of it,
    extraction issues included, so it is ready for your gold review); then the rest in paper order."""
    sampled = {b.question_id: b.status for b in s.scalars(select(BenchmarkSample))}
    done = reviewed_v2(s)
    verified = set(s.scalars(select(Classification.question_id).where(Classification.status == "verified")))
    gold, rest = [], []
    held = {"already reviewed (v2)": 0, "verified by you - left alone": 0, "extraction issue - fix it first": 0}
    for q in s.scalars(select(Question).order_by(Question.paper_id, Question.q_number)):
        if q.id in done: held["already reviewed (v2)"] += 1
        elif q.id in verified: held["verified by you - left alone"] += 1
        elif q.id in sampled: gold.append(q)
        elif q.needs_review: held["extraction issue - fix it first"] += 1
        else: rest.append(q)
    held["of which gold set still to review"] = len(gold)
    return gold + rest, held

def cmd_progress(a) -> int:
    with make_session(a.db_url) as s:
        ok, held = eligible(s)
        total = s.scalar(select(func.count()).select_from(Question))
    print(json.dumps({"questions": total, "ready to review now": len(ok), **held}, indent=1))
    return 0

def cmd_export(a) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with make_session(a.db_url) as s:
        sampled = {b.question_id: b.status for b in s.scalars(select(BenchmarkSample))}
        if a.next:
            qs = eligible(s)[0][:a.next]
            if not qs:
                print("nothing left to review right now:", json.dumps(eligible(s)[1])); return 0
            name = f"v2-{qs[0].id}"
        elif a.benchmark:
            ids = sorted(sampled); name = "benchmark"
            qs = [s.get(Question, i) for i in ids]
        else:
            if s.get(Paper, a.paper) is None:
                print("unknown paper", a.paper); return 2
            qs = s.scalars(select(Question).where(Question.paper_id == a.paper).order_by(Question.q_number)).all()
            name = a.paper
        doc = {"instructions": instructions(), "prompt_version": PROMPT_VERSION, "taxonomy_version": TAXV,
               "taxonomy": taxonomy(s),
               "questions": [_qrow(s, q, sampled) for q in qs]}
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {path} ({len(doc['questions'])} questions). Decisions go in {path.with_suffix('')}.decisions.json")
    return 0

def _valid_ids(s) -> tuple[set, dict, set]:
    nodes = s.scalars(select(TaxonomyNode).where(TaxonomyNode.version == TAXV, TaxonomyNode.deprecated == False)).all()  # noqa: E712
    secs = {n.node_id for n in nodes if n.level == "section"}
    topic_parent = {n.node_id: n.parent_id for n in nodes if n.level == "topic"}
    concepts = {n.node_id for n in nodes if n.level == "concept"}
    return secs, topic_parent, concepts

def cmd_import(a) -> int:
    data = json.loads(Path(a.decisions).read_text(encoding="utf-8"))
    reviewer = data.get("reviewer") or "ai-reviewer"
    tag = f"{reviewer} (AI review - not human verification)"
    decisions = data["decisions"]
    pv = data.get("prompt_version") or "ai-review-v1"
    if pv not in ("ai-review-v1", PROMPT_VERSION):
        print("unknown prompt_version", pv); return 2
    v2 = pv == PROMPT_VERSION
    errors, plan = [], []
    with make_session(a.db_url) as s:
        secs, topic_parent, concepts = _valid_ids(s)
        sampled = {b.question_id for b in s.scalars(select(BenchmarkSample))}
        seen = set()
        for d in decisions:
            qid = d.get("question_id")
            q = s.get(Question, qid) if qid else None
            e = []
            if q is None: e.append("unknown question")
            if qid in seen: e.append("duplicate decision")
            seen.add(qid)
            if d.get("verdict") not in ("agree", "correct", "flag"): e.append("verdict must be agree|correct|flag")
            gap = d.get("verdict") == "flag" and d.get("section_id") is None and d.get("primary_topic_id") is None
            if not gap and d.get("section_id") not in secs: e.append(f"unknown section {d.get('section_id')}")
            if not gap and topic_parent.get(d.get("primary_topic_id")) != d.get("section_id"):
                e.append(f"topic {d.get('primary_topic_id')} is not in section {d.get('section_id')}")
            bad_c = [c for c in d.get("concept_ids") or [] if c not in concepts]
            if bad_c: e.append(f"unknown concepts {bad_c}")
            if v2:
                if d.get("question_type") not in TYPES: e.append("question_type must be MCQ|MSQ|NAT")
                bad_s = [t for t in d.get("secondary_topic_ids") or [] if t not in topic_parent]
                if bad_s: e.append(f"unknown secondary topics {bad_s}")
            if e:
                errors.append({"question_id": qid, "errors": e}); continue
            c = s.scalar(select(Classification).where(Classification.question_id == qid))
            action = "record only"
            type_differs = v2 and d.get("question_type") != q.q_type
            if v2:
                human = c is not None and (c.status == "verified" or c.provenance == "validated")
                if c is None and d["verdict"] != "flag" and qid not in sampled:
                    action = "create live label (question had no label)"
                elif human or qid in sampled or c is None:
                    action = "record only" + (" (human-reviewed row kept)" if human else
                                              " (benchmark question: kept for your gold review)" if qid in sampled else "")
                elif d["verdict"] in ("correct", "flag") or type_differs:
                    action = "flag live label for you (label NOT changed)"
                plan.append((q, c, d, action)); continue
            if d["verdict"] == "correct":
                if c is None: action = "create live label (question had no label)"
                elif c.status == "verified" or c.provenance == "validated": action = "record only (human-reviewed row kept)"
                elif qid in sampled: action = "record only (benchmark question: live label kept for your independent gold review)"
                elif (c.section_id, c.primary_topic_id) == (d["section_id"], d["primary_topic_id"]): action = "record only (same label)"
                else: action = "correct live label"
            elif d["verdict"] == "flag":
                if qid in sampled: action = "record only (benchmark question: live status kept for your review)"
                elif c is not None and c.status not in ("verified",) and c.provenance != "validated":
                    action = "flag live label"
            plan.append((q, c, d, action))
        from collections import Counter
        print(json.dumps({"reviewer_tag": tag, "decisions": len(decisions), "valid": len(plan), "errors": len(errors),
                          "verdicts": dict(Counter(d["verdict"] for _, _, d, _ in plan)),
                          "actions": dict(Counter(x for *_, x in plan))}, indent=1))
        for e in errors:
            print("   ERROR", e)
        if errors:
            print("Fix the errors first - nothing written."); return 2
        if not a.yes:
            print("\nDRY RUN - nothing changed. Re-run with --yes to write (a backup is taken first)."); return 0
        from src import backup as bk
        b = bk.backup(a.db_url)
        print("backup:", b["file"], "| integrity:", b.get("integrity_check"))
        if b.get("integrity_check") not in (None, "ok"):
            print("backup integrity FAILED - nothing changed"); return 1
        run = ClassificationRun(model=reviewer, prompt_version=pv, provider=PROVIDER,
                                finished_at=utcnow(), stats={"source": Path(a.decisions).name, "n": len(plan),
                                                             "prompt_version": pv,
                                                             "note": "AI review - not human verification"})
        s.add(run); s.flush()
        n_prop = n_corr = n_flag = 0
        for q, c, d, action in plan:
            payload = {k: d.get(k) for k in ("verdict", "section_id", "primary_topic_id", "concept_ids",
                                              "what_it_tests", "confidence", "checks", "note")}
            if v2:
                payload.update({k: d.get(k) for k in V2_FIELDS})
                payload["stored_type"] = q.q_type
                payload["prompt_version"] = pv
            old = s.scalar(select(ClassificationProposal).where(
                ClassificationProposal.question_id == q.id, ClassificationProposal.provider == PROVIDER,
                ClassificationProposal.model == reviewer, ClassificationProposal.prompt_version == pv))
            if d.get("primary_topic_id") is None:          # taxonomy gap: opinion recorded as an event only
                old = prop = None
            prop = None if d.get("primary_topic_id") is None else (old or ClassificationProposal(question_id=q.id, provider=PROVIDER, model=reviewer,
                                                 prompt_version=pv, taxonomy_version=TAXV))
            if prop is not None:
                prop.run_id = run.id; prop.section_id = d["section_id"]; prop.primary_topic_id = d["primary_topic_id"]
                prop.topic_weight = {d["primary_topic_id"]: 1.0}; prop.concept_ids = d.get("concept_ids") or []
                prop.what_it_tests = d.get("what_it_tests"); prop.confidence = float(d.get("confidence") or 0.0)
                prop.evidence_quote = d.get("note"); prop.raw_response = payload
                prop.source_content_hash = question_content_hash(q)
                prop.status = "flagged" if d["verdict"] == "flag" else "suggested"
                if old is None:
                    s.add(prop)
                n_prop += 1
            s.add(ReviewEvent(question_id=q.id, field="ai_review",
                              before=None if c is None else f"{c.section_id}/{c.primary_topic_id} ({c.status})",
                              after=json.dumps(payload, ensure_ascii=False), reviewer=tag,
                              note=f"{d['verdict']}: {action}. {d.get('note') or ''}".strip()))
            if action == "create live label (question had no label)":
                nc = Classification(question_id=q.id, run_id=run.id, taxonomy_version=TAXV,
                                    section_id=d["section_id"], primary_topic_id=d["primary_topic_id"],
                                    topic_weight={d["primary_topic_id"]: 1.0}, concept_ids=d.get("concept_ids") or [],
                                    what_it_tests=d.get("what_it_tests"), confidence=float(d.get("confidence") or 0.0),
                                    provenance="inferred", status="suggested", model=f"ai-review:{reviewer}",
                                    prompt_version=pv, evidence_quote=d.get("note"))
                s.add(nc)
                s.add(ReviewEvent(question_id=q.id, field="primary_topic_id", before=None, after=d["primary_topic_id"],
                                  reviewer=tag, note="AI review created the first label (not human verification)"))
                n_corr += 1
            if action == "correct live label":
                for field, new in (("section_id", d["section_id"]), ("primary_topic_id", d["primary_topic_id"])):
                    if getattr(c, field) != new:
                        s.add(ReviewEvent(question_id=q.id, field=field, before=getattr(c, field), after=new,
                                          reviewer=tag, note="AI review correction (not human verification)"))
                        setattr(c, field, new)
                if d.get("concept_ids") is not None and d.get("concept_ids") != c.concept_ids:
                    s.add(ReviewEvent(question_id=q.id, field="concept_ids", before=json.dumps(c.concept_ids),
                                      after=json.dumps(d["concept_ids"]), reviewer=tag,
                                      note="AI review correction (not human verification)"))
                    c.concept_ids = d["concept_ids"]
                c.topic_weight = {d["primary_topic_id"]: 1.0}
                c.status = "suggested"; c.model = f"{c.model} + ai-review:{reviewer}"
                n_corr += 1
            elif action in ("flag live label", "flag live label for you (label NOT changed)"):
                if c.status != "flagged":
                    why = d.get("note") or "flagged by AI review"
                    if action.startswith("flag live label for"):
                        bits = []
                        if d["verdict"] == "correct": bits.append(f"AI suggests {d['primary_topic_id']}")
                        if d.get("question_type") != q.q_type:
                            bits.append(f"AI says type {d.get('question_type')} (stored {q.q_type})")
                        if d.get("flag_reason"): bits.append(d["flag_reason"])
                        why = "; ".join(bits + [why])
                    s.add(ReviewEvent(question_id=q.id, field="classification_flagged", before=c.status, after="flagged",
                                      reviewer=tag, note=why))
                    c.status = "flagged"
                n_flag += 1
        s.commit()
        print(f"written: {n_prop} AI-review proposals, {n_corr} live labels corrected, {n_flag} flagged. "
              f"Nothing verified; no benchmark gold written.")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export"); g = e.add_mutually_exclusive_group(required=True)
    g.add_argument("--paper"); g.add_argument("--benchmark", action="store_true")
    g.add_argument("--next", type=int, help="the next N questions not yet reviewed with v2")
    e.add_argument("--db-url", default=None)
    i = sub.add_parser("import"); i.add_argument("decisions"); i.add_argument("--yes", action="store_true")
    i.add_argument("--db-url", default=None)
    pr = sub.add_parser("progress"); pr.add_argument("--db-url", default=None)
    a = ap.parse_args()
    return {"export": cmd_export, "import": cmd_import, "progress": cmd_progress}[a.cmd](a)

if __name__ == "__main__":
    raise SystemExit(main())
