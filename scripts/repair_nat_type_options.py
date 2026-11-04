"""Repair NAT questions mistyped by extraction (2025 CS1 Q59 class of defect).

The official final key is the authority on question type. For every paper:
  - if the key says NAT but the stored question is typed otherwise, or a NAT
    question carries extracted 'options' (phantom options - e.g. a table
    misread as choices), then: set q_type=NAT, delete the phantom options,
    flag needs_review with the reason, and log a review_events row.

Idempotent: already-consistent questions are skipped (and counted). Source
content is never lost - the PDF region render remains the source of truth.

Usage: python scripts/repair_nat_type_options.py [--db-url sqlite:///data/gate_cse.sqlite]
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import delete, select
from src.db.models import AnswerKey, Option, Question, ReviewEvent
from src.db.session import make_session

REASON = ("q_type corrected {old}->NAT from the official final key; phantom "
          "extracted options removed (source intact in the PDF region render). "
          "Repair via scripts/repair_nat_type_options.py.")

def repair(session) -> dict:
    repaired, skipped = [], 0
    nat_qids = set()
    for key in session.scalars(select(AnswerKey)):
        # NAT keys carry a numeric range (answer_min/max) and no letter answer
        if key.answer_min is not None or key.answer_max is not None:
            nat_qids.add(key.question_id)
    for qid in sorted(nat_qids):
        q = session.get(Question, qid)
        if q is None:
            continue
        opts = list(session.scalars(select(Option).where(Option.question_id == qid)))
        if q.q_type == "NAT" and not opts:
            skipped += 1
            continue
        old = q.q_type
        if opts:
            session.execute(delete(Option).where(Option.question_id == qid))
        q.q_type = "NAT"
        q.needs_review = True
        q.review_reason = REASON.format(old=old)
        session.add(ReviewEvent(question_id=qid, field="q_type",
                                before=old, after="NAT",
                                reviewer="repair-script-v5",
                                note=f"removed {len(opts)} phantom option(s); flagged needs_review"))
        repaired.append((qid, old, len(opts)))
    session.commit()
    return {"repaired": repaired, "already_consistent": skipped}

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=None)
    args = ap.parse_args()
    with make_session(args.db_url) as s:
        res = repair(s)
    for qid, old, n in res["repaired"]:
        print(f"repaired {qid}: {old}->NAT, removed {n} phantom option(s), flagged")
    print(f"already consistent: {res['already_consistent']} NAT questions untouched")

if __name__ == "__main__":
    main()
