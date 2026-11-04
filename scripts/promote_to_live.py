"""Make the full multi-year dataset LIVE - safely.

    python scripts/promote_to_live.py            # DRY RUN: shows exactly what would change, touches nothing
    python scripts/promote_to_live.py --yes      # backup -> additive schema upgrade -> load papers+keys -> prove human data unchanged

Why this is NOT a file copy: the live database may hold human review decisions made after the candidate was
built; copying a file over it would silently erase them. This applies the same idempotent loader (papers-load)
directly to the live database. That loader only ADDS papers/questions/options/keys and refreshes extraction
text of rows NO human has touched.

Safety net, in order:
  1. verified backup of the live database (SQLite online-backup API, integrity_check)
  2. fingerprint of every human/agent decision (review_events, classifications)
  3. additive schema upgrade, papers-load --refresh
  4. re-fingerprint: every pre-existing decision must be byte-identical; otherwise the script says FAIL and
     tells you which backup to restore. Nothing is ever deleted."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import select, func  # noqa: E402
from src import backup as bk  # noqa: E402
from src.db import dev_upgrade  # noqa: E402
from src.db.models import Classification, Paper, Question, ReviewEvent  # noqa: E402
from src.db.session import get_url, make_session  # noqa: E402
from src.ingestion import registry as rg  # noqa: E402

def fingerprint(s) -> dict:
    ev = [(e.id, e.question_id, e.field, e.before, e.after, e.reviewer, e.note)
          for e in s.scalars(select(ReviewEvent).order_by(ReviewEvent.id))]
    cl = [(c.id, c.question_id, c.section_id, c.primary_topic_id, c.status, c.provenance, c.model, c.prompt_version,
           json.dumps(c.concept_ids))
          for c in s.scalars(select(Classification).order_by(Classification.id))]
    h = lambda rows: hashlib.sha256(json.dumps(rows, default=str, sort_keys=True).encode()).hexdigest()[:16]
    return {"review_events": (len(ev), h(ev)), "classifications": (len(cl), h(cl)),
            "verified": sum(1 for c in cl if c[4] == "verified"), "rows": {"events": ev, "cls": cl}}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="actually apply (default is a dry run)")
    ap.add_argument("--db-url", default=None, help="target database (default: $GATE_DB_URL or data/gate_cse.sqlite)")
    a = ap.parse_args()
    url = get_url(a.db_url)
    if "candidate" in url:
        print("This is the candidate DB, not the live one - nothing to promote."); return 2
    entries = rg.select(rg.load_manifest())
    with make_session(a.db_url) as s:
        have = {p for (p,) in s.execute(select(Paper.id))} if "papers" in dev_upgrade.inspect(
            dev_upgrade.make_engine(a.db_url)).get_table_names() else set()
    todo = [e for e in entries if e.paper_id not in have]
    print(f"target: {url}")
    print(f"manifest papers: {len(entries)} | already in the database: {len(entries) - len(todo)} | to be ADDED: {len(todo)}")
    print("missing schema:", dev_upgrade.missing_schema(a.db_url) or "none")
    if not a.yes:
        for e in todo:
            print(f"   + {e.paper_id}  ({e.layout}, key: {'yes' if e.key else 'none'})")
        print("\nDRY RUN - nothing changed. Re-run with --yes to apply (a backup is taken first).")
        return 0

    print("1/5 backup ...")
    b = bk.backup(a.db_url)
    print("    ", b["file"], "| integrity:", b.get("integrity_check"))
    if b.get("integrity_check") != "ok":
        print("backup integrity FAILED - aborting, nothing changed"); return 1
    with make_session(a.db_url) as s:
        before = fingerprint(s)
    print(f"2/5 human data before: {before['review_events'][0]} review events, {before['classifications'][0]} classifications, "
          f"{before['verified']} verified")
    print("3/5 additive schema upgrade ...", json.dumps(dev_upgrade.upgrade_schema(a.db_url)["columns"]["added"]))
    print("4/5 loading papers + keys ...")
    n_ok = 0
    for e in entries:
        with make_session(a.db_url) as s:
            try:
                r = rg.load_entry(s, e, refresh=True, with_keys=True)
                s.commit()
                ok = r.get("reconcile", {}).get("reconciled", False)
            except Exception as ex:  # noqa: BLE001
                s.rollback(); ok = False; r = {"error": str(ex)}
        n_ok += ok
        print(f"     {'OK  ' if ok else 'FAIL'} {e.paper_id}" + (f"  {r['error']}" if "error" in r else ""))
    with make_session(a.db_url) as s:
        after = fingerprint(s)
        n_papers = s.scalar(select(func.count()).select_from(Paper)); n_q = s.scalar(select(func.count()).select_from(Question))
    old_ev = set(before["rows"]["events"]); old_cl = {r[0]: r for r in before["rows"]["cls"]}
    ev_ok = old_ev <= set(after["rows"]["events"])
    cl_ok = all(any(r == old for r in after["rows"]["cls"]) for old in old_cl.values())
    print(f"5/5 verification: {n_papers} papers / {n_q} questions; {n_ok}/{len(entries)} papers reconciled")
    print(f"     every pre-existing review event unchanged: {ev_ok}  |  every pre-existing classification unchanged: {cl_ok}")
    if not (ev_ok and cl_ok and n_ok == len(entries)):
        print(f"\nFAIL - restore the backup if anything looks wrong: {b['file']}"); return 1
    print(f"\nDONE. Live database now holds the full dataset. Backup of the previous state: {b['file']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
