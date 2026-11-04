"""Carry the candidate database's first-pass LABELS into the live database - safely.

Why this exists: `promote_to_live.py` re-extracts papers + keys from the PDFs into the
live database. It deliberately does NOT copy classifications, review events or
benchmark samples. The v9-v11 first pass (1,802 claude-agent-manual-v2 suggestions, 377
flag events, 18 taxonomy-gap + 18 syllabus-audit events, 13 audited what_it_tests
cleanups, the 120-row benchmark sample) lives only in data/gate_cse.candidate.sqlite.
This script reconciles it into live AFTER promotion. It is not a file copy.

    python scripts/import_candidate_labels.py            # DRY RUN: counts + reasons, touches nothing
    python scripts/import_candidate_labels.py --yes      # backup -> import -> prove pre-existing rows unchanged

Rules (per question id, matched by the stable id e.g. GATE-CS-2026-S2-Q01):
  * a question is eligible only if its content hash (text + options) is IDENTICAL in
    both databases - otherwise the label was made from different input and is skipped
  * a question that already has ANY classification in live is never touched (this is
    where human reviews/corrections live); its candidate label is skipped
  * imported rows keep provenance=inferred and status suggested|flagged - never verified
  * events are appended (never edited/deleted); duplicates are not re-added
  * the 13 what_it_tests cleanups are applied only where the live text still equals the
    event's `before` value and the row is not verified/validated
  * benchmark rows keep status pending_user_review and their FROZEN baseline; a row is
    imported only if its baseline_content_hash matches the live question
Nothing is ever deleted. Run ids are re-created in live (stats note the source run id)."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import select  # noqa: E402
from src import backup as bk  # noqa: E402
from src.db import dev_upgrade  # noqa: E402
from src.db.models import (BenchmarkSample, Classification, ClassificationRun, Question,  # noqa: E402
                           ReviewEvent)
from src.db.session import get_url, make_session  # noqa: E402
from src.classification.classify import question_content_hash  # noqa: E402

CANDIDATE_URL = f"sqlite:///{(ROOT / 'data' / 'gate_cse.candidate.sqlite').as_posix()}"
CARRIED_EVENT_FIELDS = {"classification_flagged", "taxonomy_gap", "syllabus_audit"}

def _cols(model):
    return [c.key for c in model.__table__.columns if c.key != "id"]

def _copy(obj, model, **override):
    d = {k: getattr(obj, k) for k in _cols(model)}
    d.update(override)
    return model(**d)

def _ev_key(e):
    return (e.question_id, e.field, e.before, e.after, e.reviewer, e.note)

def fingerprint(s) -> dict:
    ev = [(e.id,) + _ev_key(e) for e in s.scalars(select(ReviewEvent).order_by(ReviewEvent.id))]
    cl = {c.id: json.dumps({k: getattr(c, k) for k in _cols(Classification)}, default=str, sort_keys=True)
          for c in s.scalars(select(Classification))}
    return {"events": ev, "cls": cl}

def plan(live, cand) -> dict:
    live_q = {q.id: q for q in live.scalars(select(Question))}
    cand_q = {q.id: q for q in cand.scalars(select(Question))}
    live_hash = {qid: question_content_hash(q) for qid, q in live_q.items()}
    cand_hash = {qid: question_content_hash(q) for qid, q in cand_q.items() if qid in live_q}
    same = {qid for qid, h in cand_hash.items() if live_hash.get(qid) == h}
    live_cls = {c.question_id: c for c in live.scalars(select(Classification))}
    live_ev = {_ev_key(e) for e in live.scalars(select(ReviewEvent))}
    live_bench = set(live.scalars(select(BenchmarkSample.question_id)))

    p = {"cls": [], "events": [], "wit": [], "bench": [], "skip": {}}
    def skip(reason, qid):
        p["skip"].setdefault(reason, []).append(qid)

    for c in cand.scalars(select(Classification).order_by(Classification.id)):
        if c.question_id not in live_q: skip("cls: question not in live (promote first)", c.question_id)
        elif c.question_id not in same: skip("cls: question content differs", c.question_id)
        elif c.question_id in live_cls: skip("cls: live already has a classification (kept)", c.question_id)
        else: p["cls"].append(c)
    imported_q = {c.question_id for c in p["cls"]}

    for e in cand.scalars(select(ReviewEvent).order_by(ReviewEvent.id)):
        if _ev_key(e) in live_ev:
            continue
        if e.field == "what_it_tests":
            lc = live_cls.get(e.question_id)
            if lc is None: skip("wit: no live row", e.question_id)
            elif lc.status == "verified" or lc.provenance == "validated": skip("wit: live row human-reviewed (kept)", e.question_id)
            elif lc.what_it_tests != e.before: skip("wit: live text differs from event 'before' (kept)", e.question_id)
            else: p["wit"].append((lc, e))
        elif e.field == "classification_flagged":
            if e.question_id in imported_q: p["events"].append(e)
            else: skip("event: flag for a label not imported", e.question_id)
        elif e.field in CARRIED_EVENT_FIELDS:
            if e.question_id not in same: skip(f"event {e.field}: question content differs / missing", e.question_id)
            elif e.question_id in live_cls: skip(f"event {e.field}: live already classified it", e.question_id)
            else: p["events"].append(e)
        else:
            skip(f"event {e.field}: not a carried field", e.question_id)

    for b in cand.scalars(select(BenchmarkSample).order_by(BenchmarkSample.id)):
        if b.question_id in live_bench: skip("bench: already sampled in live", b.question_id)
        elif b.question_id not in live_q: skip("bench: question not in live", b.question_id)
        elif b.status != "pending_user_review": skip("bench: not pending (kept out)", b.question_id)
        elif b.baseline_content_hash != live_hash[b.question_id]: skip("bench: content differs from frozen baseline", b.question_id)
        else: p["bench"].append(b)
    return p

def summarize(p) -> dict:
    from collections import Counter
    return {"classifications_to_add": len(p["cls"]),
            "  by status": dict(Counter(c.status for c in p["cls"])),
            "  by model": dict(Counter(c.model for c in p["cls"])),
            "events_to_append": dict(Counter(e.field for e in p["events"])),
            "what_it_tests_cleanups": len(p["wit"]),
            "benchmark_rows_to_add": len(p["bench"]),
            "skipped": {k: len(v) for k, v in p["skip"].items()}}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="actually apply (default: dry run)")
    ap.add_argument("--db-url", default=None, help="target (default: $GATE_DB_URL or data/gate_cse.sqlite)")
    ap.add_argument("--candidate-url", default=CANDIDATE_URL)
    a = ap.parse_args()
    url = get_url(a.db_url)
    if "candidate" in url:
        print("Target is the candidate DB - refusing."); return 2
    missing = dev_upgrade.missing_schema(a.db_url)
    if missing:
        print("Target schema is missing:", missing, "\nRun `python -m src.cli upgrade-dev` (after a backup) first."); return 2
    print(f"target:    {url}\ncandidate: {a.candidate_url}")
    with make_session(a.db_url) as live, make_session(a.candidate_url) as cand:
        p = plan(live, cand)
        print(json.dumps(summarize(p), indent=1))
        not_promoted = p["skip"].get("cls: question not in live (promote first)", [])
        if not_promoted:
            print(f"\n{len(not_promoted)} candidate questions are not in the target yet. Run promotion FIRST "
                  "(scripts/promote_to_live.py --yes), then this script - a partial import is refused.")
            return 0 if not a.yes else 2
        if not a.yes:
            print("\nDRY RUN - nothing changed. Re-run with --yes to apply (a backup is taken first).")
            return 0

    print("1/4 backup ...")
    b = bk.backup(a.db_url)
    print("    ", b["file"], "| integrity:", b.get("integrity_check"))
    if b.get("integrity_check") != "ok":
        print("backup integrity FAILED - aborting, nothing changed"); return 1
    with make_session(a.db_url) as live, make_session(a.candidate_url) as cand:
        before = fingerprint(live)
        p = plan(live, cand)
        print("2/4 importing ...")
        run_map: dict[int, int] = {}
        def live_run(cid):
            if cid is None: return None
            if cid not in run_map:
                cr = cand.get(ClassificationRun, cid)
                stats = dict(cr.stats or {}); stats["copied_from_candidate_run_id"] = cid
                nr = _copy(cr, ClassificationRun, stats=stats); live.add(nr); live.flush()
                run_map[cid] = nr.id
            return run_map[cid]
        for c in p["cls"]:
            live.add(_copy(c, Classification, run_id=live_run(c.run_id)))
        for e in p["events"]:
            live.add(_copy(e, ReviewEvent))
        wit_ids = set()
        for lc, e in p["wit"]:
            lc.what_it_tests = e.after; wit_ids.add(lc.id)
            live.add(_copy(e, ReviewEvent))
        for bs in p["bench"]:
            live.add(_copy(bs, BenchmarkSample, baseline_run_id=live_run(bs.baseline_run_id)))
        live.commit()
        after = fingerprint(live)
        print("3/4 verifying pre-existing rows ...")
        ev_ok = set(before["events"]) <= set(after["events"])
        changed = {cid for cid, v in before["cls"].items() if after["cls"].get(cid) != v}
        cl_ok = changed <= wit_ids
        print(f"     every pre-existing review event unchanged: {ev_ok}")
        print(f"     pre-existing classifications changed: {len(changed)} (all are the audited what_it_tests cleanups: {cl_ok})")
        print(f"     any verified rows created by this script: {'NO' if not any(c.status == 'verified' for c in p['cls']) else 'YES - BUG'}")
        if not (ev_ok and cl_ok):
            print(f"\nFAIL - restore the backup: {b['file']}"); return 1
    print(f"4/4 DONE. Backup of the previous state: {b['file']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
