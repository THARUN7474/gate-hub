"""Generic GATE answer-key PDF -> pipeline key CSV.

Handles the tabular official key layout (columns Q.No / Session / Q.Type /
Section / Key-or-Range / Marks, one cell per line in extraction order), as
published by GATE 2024 (IISc), 2025 (IIT Roorkee) and 2026 (IIT Guwahati).
Replaces the paper-specific keypdf_to_csv_2026_cs1.py helper for this layout
family; a genuinely different layout still needs its own handler (fail loudly,
never guess).

Row grammar: qno(sequential int) session(int) type(MCQ|MSQ|NAT) section
key+(one or more tokens; MTA allowed) marks(1|2).

Usage: python scripts/keypdf_to_csv.py KEY_PDF OUT_CSV [--expect-questions 65]
Cross-checks against the DB when the paper is already extracted (q_type and
marks per question), warning instead of asserting so it also runs pre-ingest.
"""
from __future__ import annotations
import argparse, csv, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf  # noqa: E402

def parse_key_pdf(pdf_path: str) -> list[tuple[int, str, str, str, int]]:
    tokens: list[str] = []
    for page in pymupdf.open(pdf_path):
        tokens.extend(page.get_text().split())
    return parse_key_tokens(tokens)

def parse_key_tokens(tokens: list[str]) -> list[tuple[int, str, str, str, int]]:
    rows = []
    i, qno = 0, 1
    while i < len(tokens):
        if tokens[i] != str(qno):
            i += 1
            continue
        try:
            session = tokens[i + 1]
            qtype = tokens[i + 2]
            section = tokens[i + 3]
        except IndexError:
            break
        if not session.isdigit() or qtype not in ("MCQ", "MSQ", "NAT"):
            i += 1
            continue
        j = i + 4
        key_parts = []
        while j < len(tokens):
            t = tokens[j]
            nxt = tokens[j + 1] if j + 1 < len(tokens) else None
            if t in ("1", "2") and (nxt == str(qno + 1) or nxt is None
                                    or not re.fullmatch(r"\d+", nxt)):
                marks = int(t)
                break
            key_parts.append(t)
            j += 1
        else:
            raise SystemExit(f"unterminated key row at Q{qno}: layout not recognised - "
                             "this parser covers the tabular official layout only")
        if not key_parts:
            raise SystemExit(f"empty key at Q{qno}: layout not recognised")
        rows.append((qno, qtype, section, " ".join(key_parts), marks))
        qno += 1
        i = j + 1
    return rows

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("key_pdf")
    ap.add_argument("out_csv")
    ap.add_argument("--expect-questions", type=int, default=65)
    args = ap.parse_args()
    rows = parse_key_pdf(args.key_pdf)
    if len(rows) != args.expect_questions:
        raise SystemExit(f"parsed {len(rows)} rows, expected {args.expect_questions} - "
                         "layout not recognised or paper structure differs; inspect manually")
    if [r[0] for r in rows] != list(range(1, args.expect_questions + 1)):
        raise SystemExit("question numbers not sequential - layout not recognised")
    # optional DB cross-check
    try:
        from sqlalchemy import select
        from src.db.session import make_session
        from src.db.models import Question
        with make_session() as s:
            qs = {q.q_number: q for q in s.scalars(select(Question)).all()}
        mismatch = [(qno, qt, qs[qno].q_type, marks, qs[qno].marks)
                    for qno, qt, sec, key, marks in rows
                    if qno in qs and not (qs[qno].q_type == qt or (qt == "MSQ" and qs[qno].q_type == "MCQ"))
                    or (qno in qs and float(marks) != qs[qno].marks)]
        if mismatch:
            print(f"WARNING: {len(mismatch)} q_type/marks mismatches vs DB: {mismatch[:5]}")
        else:
            print("DB cross-check: q_type and marks consistent for all parsed rows")
    except Exception as e:  # DB not populated yet - fine, CSV is still written
        print(f"DB cross-check skipped ({type(e).__name__})")
    with open(args.out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["qno", "kind", "answer", "min", "max", "notes"])
        for qno, qtype, sec, key, marks in rows:
            if qtype == "NAT":
                nums = [t for t in key.replace("to", " to ").split() if t != "to"]
                if key.upper() == "MTA":
                    w.writerow([qno, qtype, "MTA", "", "", "marks to all"])
                else:
                    lo, hi = (nums + nums)[:2]
                    w.writerow([qno, qtype, "", lo, hi, ""])
            else:
                w.writerow([qno, qtype, key, "", "", ""])
    print(f"wrote {args.out_csv}: {len(rows)} keys")

if __name__ == "__main__":
    main()
