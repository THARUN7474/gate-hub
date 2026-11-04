"""Repair question/option text that an older extractor got wrong - audited, never on human-reviewed questions.

Three extractor bugs fixed on 5 Nov 2026 (src/extraction/extract.py):
  1. the footer filter matched "Page N of M" with single spaces only; 2022-S1 / 2023-S1 print
     "Page  N  of  41" (double spaces), so the footer (and in 2023-S1 the running header
     "Computer Science and Information Technology (CS)") was stored as option D text;
  2. two-column option detection bucketed label x positions in 8pt steps, so labels at x=123 and
     x=124 (sub-pixel jitter) looked like two columns and continuation lines were attached to the
     wrong option (2022-S1: real D glued onto C; 2021-S1/S2: C and D glued onto B, C/D empty);
  3. some papers centre the 'Q.N' label on the first paragraph, so the stem's first line(s) print
     ABOVE the label and were glued onto the previous question (2022-S1 Q08, 2024-S2 x6,
     2025-S1 x3, 2025-S2 Q56 lost their opening sentence).

This script re-extracts the given papers IN MEMORY and replaces stored text/options only where:
  * options-only difference and the fresh options are clearly better: they fill options that were
    empty with real text, or they remove leaked page boilerplate (page footer / running header); OR
  * a chain of neighbouring questions where text moved between them: every word is conserved
    (stored minus page boilerplate == fresh, in order) and every text change is a question
    GAINING a prose prefix (>= 20 chars, >= 3 words) or LOSING a tail; AND
  * no classification of the question is human-verified and no human extraction decision exists
    (review events on text / option:* / marks / q_type / extraction_verified by a person).
Anything else that differs (e.g. OCR noise moving between options) is REPORTED and left alone.

Every replaced value is logged in review_events (field=text or option:X, exact before/after,
reviewer=extraction-repair-v12) - visible in the app's audit history and reversible.

Benchmark rows: a sampled question whose content changes gets a new content hash, so its frozen
baseline would be reported STALE and excluded. With --rebaseline-pending, rows that are still
pending_user_review (no gold yet) get baseline_content_hash updated to the repaired content; the
frozen PREDICTION is not changed, and an event (field=benchmark_rebaseline) records why. Rows that
already hold gold are never touched.

    python scripts/repair_extraction.py --paper all                               # dry run
    python scripts/repair_extraction.py --paper all --yes --rebaseline-pending    # backup, then apply"""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import select  # noqa: E402
from src.db.models import BenchmarkSample, Classification, Option, Question, ReviewEvent  # noqa: E402
from src.db.session import make_session  # noqa: E402

REVIEWER = "extraction-repair-v12"
MACHINE_REVIEWERS = {REVIEWER, "extraction-repair-v7"}          # earlier audited machine repairs
HUMAN_EXTRACTION_FIELDS = ("text", "marks", "q_type", "extraction_verified")
BOILERPLATE = re.compile(r"Page\s+\d+\s+of\s+\d+|Computer Science (?:&|and) Information Technology \(CS\d?\)"
                         r"|Organizing Institute:")

def _human_extraction_decision(s, qid: str) -> bool:
    for e in s.scalars(select(ReviewEvent).where(ReviewEvent.question_id == qid)):
        if e.reviewer in MACHINE_REVIEWERS:
            continue
        if e.field in HUMAN_EXTRACTION_FIELDS or (e.field or "").startswith("option:"):
            return True
    return False

def _better(stored: dict, fresh: dict) -> str | None:
    empty = lambda d: sum(1 for v in d.values() if not (v or "").strip())
    filled = [fresh[k] for k in fresh if not (stored.get(k) or "").strip() and (fresh[k] or "").strip()]
    real = all(len(v.strip()) >= 2 or v.strip().isdigit() for v in filled)   # a lone OCR glyph ('x') is noise
    if set(stored) == set(fresh) and empty(fresh) < empty(stored) and real:
        return "fills options that were empty (text had been glued onto a neighbouring option)"
    if any(BOILERPLATE.search(v or "") for v in stored.values()) and \
            not any(BOILERPLATE.search(v or "") for v in fresh.values()):
        return "removes leaked page footer/header from the options"
    return None

def _words(*parts) -> list[str]:
    return " ".join(BOILERPLATE.sub(" ", p or "") for p in parts).split()

def _all(text: str, opts: dict) -> list[str]:
    return _words(text, *[opts[k] for k in sorted(opts)])

def _prose(x: str) -> bool:
    return len(x.strip()) >= 20 and len(re.findall(r"[A-Za-z]{2,}", x)) >= 3

def _text_move_ok(stored: str, fresh: str) -> bool:
    if fresh.endswith(stored) and fresh != stored:
        return _prose(fresh[: len(fresh) - len(stored)])          # gained its opening sentence
    return stored.startswith(fresh) and fresh != stored            # lost a tail to the next question

def plan(s, records: list[dict]) -> dict:
    """Pure read: compare fresh `records` (one paper, in order) with the stored rows."""
    rows = []
    for r in records:
        q = s.get(Question, r["id"])
        if q is None:
            continue
        stored = {o.label: o.content for o in s.scalars(select(Option).where(Option.question_id == q.id))}
        fresh = {o["label"]: o["content"] for o in r["options"]}
        rows.append({"question_id": q.id, "stored": stored, "fresh": fresh, "stored_text": q.text or "",
                     "fresh_text": r["text"] or "",
                     "changed": stored != fresh or (q.text or "") != (r["text"] or "")})
    chains, cur = [], []                     # text can only move between neighbours
    for row in rows:
        if row["changed"]:
            cur.append(row)
        elif cur:
            chains.append(cur); cur = []
    if cur:
        chains.append(cur)
    fix, left = [], []
    for ch in chains:
        moving = [r for r in ch if r["stored_text"] != r["fresh_text"]]
        chain_why = None
        if moving:
            conserved = (sum((_all(r["stored_text"], r["stored"]) for r in ch), [])
                         == sum((_all(r["fresh_text"], r["fresh"]) for r in ch), []))
            if conserved and all(_text_move_ok(r["stored_text"], r["fresh_text"]) for r in moving):
                chain_why = ("opening text moved back to the question it belongs to (label centred on the "
                             "paragraph); every word conserved")
        members = []
        for r in ch:
            why = chain_why if moving else _better(r["stored"], r["fresh"])
            if not why:
                r["why"] = ("text differs and the chain is not a clean move: needs a human" if moving else
                            "not clearly better (e.g. OCR noise moving between options): left alone")
            elif s.scalar(select(Classification.id).where(Classification.question_id == r["question_id"],
                                                          Classification.status == "verified")) is not None:
                why, r["why"] = None, "human-verified: never touched"
            elif _human_extraction_decision(s, r["question_id"]):
                why, r["why"] = None, "a human extraction decision exists: never touched"
            else:
                r["why"] = why
            members.append((r, why))
        if moving and any(w is None for _, w in members):      # a text move is all-or-nothing
            for r, w in members:
                if w:
                    r["why"] = "part of a text move whose partner is refused"
            left += [r for r, _ in members]
        else:
            fix += [r for r, w in members if w]
            left += [r for r, w in members if not w]
    return {"fix": fix, "left": left}

def apply(s, fixes: list[dict], rebaseline: bool) -> dict:
    from src.classification.classify import question_content_hash
    n_opt = n_text = n_q = n_bench = 0
    for f in fixes:
        q = s.get(Question, f["question_id"])
        rows = {o.label: o for o in s.scalars(select(Option).where(Option.question_id == q.id))}
        if {k: o.content for k, o in rows.items()} != f["stored"] or (q.text or "") != f["stored_text"]:
            continue                                   # changed since the plan: do nothing
        if f["fresh_text"] != f["stored_text"]:
            s.add(ReviewEvent(question_id=q.id, field="text", before=f["stored_text"], after=f["fresh_text"],
                              reviewer=REVIEWER, note=f"extractor fix 2026-11-05: {f['why']}"))
            q.text = f["fresh_text"]; n_text += 1
        for lab, new in f["fresh"].items():
            old = rows[lab].content
            if old == new:
                continue
            rows[lab].content = new
            s.add(ReviewEvent(question_id=q.id, field=f"option:{lab}", before=old, after=new, reviewer=REVIEWER,
                              note=f"extractor fix 2026-11-05: {f['why']}; same PDF region re-extracted"))
            n_opt += 1
        n_q += 1
        s.flush()
        if rebaseline:
            for b in s.scalars(select(BenchmarkSample).where(BenchmarkSample.question_id == q.id)):
                if b.status != "pending_user_review":
                    continue
                new_hash = question_content_hash(q)
                if b.baseline_content_hash != new_hash:
                    s.add(ReviewEvent(question_id=q.id, field="benchmark_rebaseline", before=b.baseline_content_hash,
                                      after=new_hash, reviewer=REVIEWER,
                                      note="content repaired by an audited extraction fix while the row was still "
                                           "pending (no gold); frozen prediction unchanged, only its content hash"))
                    b.baseline_content_hash = new_hash
                    n_bench += 1
    return {"questions": n_q, "texts": n_text, "options": n_opt, "benchmark_rebaselined": n_bench}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paper", required=True, help="comma list of paper ids, or 'all'")
    ap.add_argument("--db-url", default=None)
    ap.add_argument("--yes", action="store_true", help="apply (default: dry run). Takes a verified backup first.")
    ap.add_argument("--rebaseline-pending", action="store_true",
                    help="update the content hash of PENDING benchmark rows whose content was repaired")
    ap.add_argument("--assets-root", default="data/assets")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    from src.extraction.extract import extract_paper
    from src.ingestion import registry as rg
    entries = {e.paper_id: e for e in rg.select(rg.load_manifest())}
    pids = list(entries) if a.paper == "all" else [p.strip() for p in a.paper.split(",")]
    unknown = [p for p in pids if p not in entries]
    if unknown:
        print("unknown paper id(s):", unknown); return 2
    with make_session(a.db_url) as s:
        fixes, left = [], []
        for pid in pids:
            e = entries[pid]
            if s.scalar(select(Question.id).where(Question.paper_id == pid).limit(1)) is None:
                continue
            recs, _ = extract_paper(e.file, pid, a.assets_root, pages=e.pages, ocr=e.ocr)
            p = plan(s, recs); fixes += p["fix"]; left += p["left"]
        n_text = sum(f["stored_text"] != f["fresh_text"] for f in fixes)
        print(f"questions to repair: {len(fixes)} ({n_text} with a text change); different but left alone: {len(left)}")
        for f in fixes:
            print(f"   + {f['question_id']}: {f['why']}")
            if a.verbose:
                if f["stored_text"] != f["fresh_text"]:
                    print(f"        text: {f['stored_text'][:70]!r} -> {f['fresh_text'][:70]!r}")
                for k in f["fresh"]:
                    if f["stored"].get(k) != f["fresh"][k]:
                        print(f"        {k}: {f['stored'].get(k)!r} -> {f['fresh'][k]!r}")
        for f in left:
            print(f"   ! {f['question_id']}: {f['why']}")
        sampled = {b.question_id: b.status for b in s.scalars(select(BenchmarkSample).where(
            BenchmarkSample.question_id.in_([f["question_id"] for f in fixes])))}
        if sampled:
            print(f"benchmark rows affected: {sampled}"
                  + ("" if a.rebaseline_pending else "  (they will report STALE unless --rebaseline-pending)"))
        if not a.yes:
            print("\nDRY RUN - nothing changed. Re-run with --yes to apply (a backup is taken first)."); return 0
        if not fixes:
            print("nothing to do."); return 0
        from src import backup as bk
        b = bk.backup(a.db_url)
        print("backup:", b["file"], "| integrity:", b.get("integrity_check"))
        if b.get("integrity_check") not in (None, "ok"):
            print("backup integrity FAILED - nothing changed"); return 1
        res = apply(s, fixes, a.rebaseline_pending)
        s.commit()
        print(f"repaired {res['questions']} question(s): {res['texts']} text(s), {res['options']} option(s); "
              f"benchmark rows re-baselined: {res['benchmark_rebaselined']}. Logged in review_events "
              f"(reviewer={REVIEWER}).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
