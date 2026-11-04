"""Complete question text that an earlier repair left TRUNCATED (the 2025 CS-1 Q59 case).

Why this exists: persist_records never overwrites stored text that differs from a fresh extraction (a human may have
corrected it). Q59 was repaired once (its phantom options were removed), which left its stored text a strict PREFIX of
what the extractor now produces: the 80 characters of state-table values at the end are missing. This script finishes
exactly that situation and nothing else:

    fresh text starts with the stored text, is longer, the options are identical, and no classification of the
    question is human-verified.

Everything else that differs (a real content change, different options, a verified question) is only REPORTED.
Only text is appended; nothing is deleted or rewritten. Each change is logged in review_events (field=text) with the
exact before/after, so it is visible and reversible.

    python scripts/repair_truncated_text.py --paper GATE-CS-2025-S1                 # dry run (default)
    python scripts/repair_truncated_text.py --paper GATE-CS-2025-S1 --yes           # backup, then apply

The target database must already have the current schema (promote_to_live.py upgrades it)."""
from __future__ import annotations
import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import select  # noqa: E402
from src.db.models import Classification, Option, Question, ReviewEvent  # noqa: E402
from src.db.session import make_session  # noqa: E402

REVIEWER = "extraction-repair-v7"

def plan(s, records: list[dict]) -> dict:
    """Compare freshly extracted `records` with the stored rows. Pure read."""
    fixable, refused = [], []
    for r in records:
        q = s.get(Question, r["id"])
        if q is None:
            continue
        stored, fresh = q.text or "", r["text"] or ""
        if stored == fresh:
            continue
        stored_opts = {o.label: o.content for o in s.scalars(select(Option).where(Option.question_id == q.id))}
        fresh_opts = {o["label"]: o["content"] for o in r["options"]}
        verified = s.scalar(select(Classification.id).where(Classification.question_id == q.id,
                                                             Classification.status == "verified")) is not None
        why = None
        if verified:
            why = "a classification of this question is human-verified: never touched"
        elif stored_opts != fresh_opts:
            why = "options differ: not a pure truncation"
        elif not (fresh.startswith(stored) and len(fresh) > len(stored)):
            why = "stored text is not a prefix of the fresh text: a real content difference, needs a human"
        row = {"question_id": q.id, "stored_chars": len(stored), "fresh_chars": len(fresh),
               "missing_tail": fresh[len(stored):] if fresh.startswith(stored) else None}
        (refused if why else fixable).append({**row, "why": why} if why else {**row, "fresh_text": fresh, "stored_text": stored})
    return {"fixable": fixable, "refused": refused}

def apply(s, p: dict) -> int:
    n = 0
    for f in p["fixable"]:
        q = s.get(Question, f["question_id"])
        if (q.text or "") != f["stored_text"]:          # changed since the plan was made: do nothing
            continue
        q.text = f["fresh_text"]
        s.add(ReviewEvent(question_id=q.id, field="text", before=f["stored_text"], after=f["fresh_text"],
                          reviewer=REVIEWER,
                          note=f"appended {len(f['missing_tail'])} missing characters (the stored text was an exact "
                               "prefix of a fresh extraction of the same PDF region); nothing removed or rewritten"))
        n += 1
    return n

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paper", required=True, help="comma list of paper ids (e.g. GATE-CS-2025-S1)")
    ap.add_argument("--db-url", default=None)
    ap.add_argument("--yes", action="store_true", help="apply (default: dry run). Takes a verified backup first.")
    ap.add_argument("--assets-root", default="data/assets")
    a = ap.parse_args()
    from src.extraction.extract import extract_paper
    from src.ingestion import registry as rg
    entries = {e.paper_id: e for e in rg.select(rg.load_manifest())}
    unknown = [p for p in a.paper.split(",") if p.strip() not in entries]
    if unknown:
        print("unknown paper id(s):", unknown); return 2
    with make_session(a.db_url) as s:
        plans = []
        for pid in [p.strip() for p in a.paper.split(",")]:
            e = entries[pid]
            recs, _ = extract_paper(e.file, pid, a.assets_root, pages=e.pages, ocr=e.ocr)
            plans.append((pid, plan(s, recs)))
        total = 0
        for pid, p in plans:
            print(f"{pid}: {len(p['fixable'])} text(s) to complete, {len(p['refused'])} different but left alone")
            for f in p["fixable"]:
                print(f"   + {f['question_id']}: {f['stored_chars']} -> {f['fresh_chars']} chars; appends {f['missing_tail']!r}")
            for f in p["refused"]:
                print(f"   ! {f['question_id']}: {f['why']}")
            total += len(p["fixable"])
        if not a.yes:
            print("\nDRY RUN - nothing changed. Re-run with --yes to apply (a backup is taken first)."); return 0
        if not total:
            print("nothing to do."); return 0
        from src import backup as bk
        b = bk.backup(a.db_url)
        print("backup:", b["file"], "| integrity:", b.get("integrity_check"))
        if b.get("integrity_check") not in (None, "ok"):
            print("backup integrity FAILED - nothing changed"); return 1
        done = sum(apply(s, p) for _, p in plans)
        s.commit()
        print(f"completed {done} text(s); each is logged in review_events (field=text, reviewer={REVIEWER}).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
