"""Reset human review and size the gold set (user request, 6 Nov 2026).

    python scripts/reset_human_review.py                 # DRY RUN: what would change
    python scripts/reset_human_review.py --gold 385 --yes   # backup, then write

1. Every human-verified label goes back to 'suggested' (the label itself is kept; the status change and the
   withdrawn extraction/key approvals are written to the audit log). Any benchmark gold is revoked.
2. The gold set is topped up to --gold questions with the same stratified selector (paper x marks); questions
   already in the sample stay. New rows are 'pending_user_review' - only YOU make gold, by verifying them in
   the Review Workspace (that verification also counts as human verification of the label).
Nothing else changes; machine labels, AI reviews and extraction corrections are kept."""
from __future__ import annotations
import argparse, json, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import func, select  # noqa: E402
from src.db.models import BenchmarkSample, Classification, ReviewEvent  # noqa: E402
from src.db.session import make_session  # noqa: E402
from src.validation import benchmark as bm  # noqa: E402

WHO = "reset (user request: start human review from zero)"


def run(db_url, gold: int, yes: bool) -> dict:
    with make_session(db_url) as s:
        ver = list(s.scalars(select(Classification).where(Classification.status == "verified")))
        have = s.scalar(select(func.count()).select_from(BenchmarkSample)) or 0
        golds = s.scalar(select(func.count()).select_from(BenchmarkSample)
                         .where(BenchmarkSample.status == "gold_verified")) or 0
        plan = {"unverify": [c.question_id for c in ver], "gold_revoked": golds,
                "gold_set_now": have, "gold_set_target": gold, "to_add": max(0, gold - have)}
        if not yes:
            return {**plan, "dry_run": True}
        from src import backup as bk
        b = bk.backup(db_url)
        if b.get("integrity_check") not in (None, "ok"):
            raise SystemExit("backup integrity failed - nothing changed")
        plan["backup"] = b["file"]
        for c in ver:
            s.add(ReviewEvent(question_id=c.question_id, field="status", before="verified", after="suggested",
                              reviewer=WHO, note="human verification withdrawn; label kept as a suggestion"))
            for f in ("extraction_verified", "key_verified"):
                s.add(ReviewEvent(question_id=c.question_id, field=f, before=None, after="false", reviewer=WHO,
                                  note="approval withdrawn by reset"))
            c.status, c.provenance = "suggested", "inferred"
        for r in s.scalars(select(BenchmarkSample).where(BenchmarkSample.status == "gold_verified")):
            bm.revoke_gold(s, r.question_id, "revoked by reset")
        if plan["to_add"]:
            plan["added"] = bm.select_benchmark_sample(s, plan["to_add"], 2027, f"gold-{date.today().isoformat()}")["selected"]
        s.commit()
        plan["gold_set_after"] = s.scalar(select(func.count()).select_from(BenchmarkSample))
        plan["verified_after"] = s.scalar(select(func.count()).select_from(Classification)
                                          .where(Classification.status == "verified"))
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", type=int, default=385)
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--db-url", default=None)
    a = ap.parse_args()
    print(json.dumps(run(a.db_url, a.gold, a.yes), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
