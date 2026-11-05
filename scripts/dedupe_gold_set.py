"""Keep the gold set on ORIGINAL questions only (duplicate copies follow their original - src/analytics/dupes.py).

    python scripts/dedupe_gold_set.py                 # DRY RUN
    python scripts/dedupe_gold_set.py --yes           # backup, then write

For every gold-set row that is a duplicate copy (e.g. GATE 2013 set 2-4):
  * its original is not in the gold set yet -> the row is moved to the original (same batch, baseline re-frozen
    from the original's current label);
  * its original is already in the gold set  -> the row is removed;
then the set is topped up to --size with the usual stratified selector (which never picks copies).
Only rows still 'pending_user_review' are touched; human gold is never moved or removed."""
from __future__ import annotations
import argparse, json, sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import func, select  # noqa: E402
from src.analytics.dupes import duplicate_map  # noqa: E402
from src.classification.classify import question_content_hash  # noqa: E402
from src.db.models import BenchmarkSample, Classification, Paper, Question  # noqa: E402
from src.db.session import make_session  # noqa: E402
from src.validation import benchmark as bm  # noqa: E402


def run(db_url, size: int, yes: bool) -> dict:
    with make_session(db_url) as s:
        copies = duplicate_map(s)["copy_of"]
        rows = list(s.scalars(select(BenchmarkSample)))
        gold_ids = {r.question_id for r in rows}
        move, drop, kept_gold = [], [], []
        for r in rows:
            if r.question_id not in copies:
                continue
            if r.status != "pending_user_review":
                kept_gold.append(r.question_id); continue
            orig = copies[r.question_id]
            if orig in gold_ids:
                drop.append(r)
            else:
                move.append((r, orig)); gold_ids.add(orig)
        plan = {"gold_rows": len(rows), "copies_in_gold": len(move) + len(drop) + len(kept_gold),
                "move_to_original": len(move), "remove": len(drop), "kept (already human gold)": len(kept_gold),
                "after_dedupe": len(rows) - len(drop), "target": size}
        if not yes:
            return {**plan, "dry_run": True}
        from src import backup as bk
        b = bk.backup(db_url)
        if b.get("integrity_check") not in (None, "ok"):
            raise SystemExit("backup integrity failed - nothing changed")
        plan["backup"] = b["file"]
        for r, orig in move:
            q = s.get(Question, orig)
            p = s.get(Paper, q.paper_id)
            c = s.scalar(select(Classification).where(Classification.question_id == orig))
            r.question_id = orig
            r.stratum = bm._stratum(p, q)
            r.baseline_section_id = c.section_id if c else None
            r.baseline_primary_topic_id = c.primary_topic_id if c else None
            r.baseline_concept_ids = list(c.concept_ids or []) if c else None
            r.baseline_confidence = c.confidence if c else None
            r.baseline_run_id = c.run_id if c else None
            r.baseline_content_hash = question_content_hash(q)
            r.sampled_at = datetime.now(timezone.utc)
            r.note = "moved from a duplicate copy to its original"
        for r in drop:
            s.delete(r)
        s.flush()
        have = s.scalar(select(func.count()).select_from(BenchmarkSample))
        if have < size:
            plan["added"] = bm.select_benchmark_sample(s, size - have, 2028, f"gold-{date.today().isoformat()}-dedupe")["selected"]
        s.commit()
        plan["gold_set_after"] = s.scalar(select(func.count()).select_from(BenchmarkSample))
        plan["copies_in_gold_after"] = sum(1 for (q,) in s.execute(select(BenchmarkSample.question_id)) if q in copies)
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--size", type=int, default=385)
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--db-url", default=None)
    a = ap.parse_args()
    print(json.dumps(run(a.db_url, a.size, a.yes), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
