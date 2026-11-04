"""Transcribe the official GATE 2026 CS-1 answer-key PDF table into the
pipeline's key CSV format, and cross-check extraction vs the key.

Reads the pdftotext -layout rendering of the key PDF. Emits
data/raw/keys/2026/CS1_key.csv. Also verifies (needs the DB populated):
  - extracted q_type matches the key's Question Type for all 65 questions
    (MSQ appears as MCQ before key import, by design)
  - extracted marks match the key's Marks column
  - extracted NAT question set equals the key's NAT set
Run AFTER: init, taxonomy, ingest, extract.
"""
import re, csv
from sqlalchemy import select
from src.db.session import make_session
from src.db.models import Question

KEY_TXT = "/tmp/key.txt"   # pdftotext -layout data/raw/keys/2026/CS1_answer_key.pdf /tmp/key.txt
OUT = "data/raw/keys/2026/CS1_key.csv"

def main():
    rows = []
    for line in open(KEY_TXT):
        m = re.match(r"\s*(\d{1,2})\s+3\s+(MCQ|MSQ|NAT)\s+(GA|CS-1)\s+(.+?)\s+(\d)\s*$", line)
        if m:
            rows.append((int(m.group(1)), m.group(2), m.group(3), m.group(4).strip(), int(m.group(5))))
    assert len(rows) == 65, len(rows)
    assert [r[0] for r in rows] == list(range(1, 66))
    with make_session() as s:
        qs = {q.q_number: q for q in s.scalars(select(Question)).all()}
    mismatch = []
    for qno, qtype, sec, key, marks in rows:
        q = qs[qno]
        ok = (q.q_type == qtype) or (qtype == "MSQ" and q.q_type == "MCQ")
        if not ok or float(marks) != q.marks:
            mismatch.append((qno, qtype, q.q_type, marks, q.marks))
    assert not mismatch, mismatch
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["qno", "kind", "answer", "min", "max", "notes"])
        for qno, qtype, sec, key, marks in rows:
            if qtype == "MCQ":
                w.writerow([qno, "mcq_single", key, "", "", ""])
            elif qtype == "MSQ":
                w.writerow([qno, "msq_set", key, "", "", ""])
            else:
                lo, hi = [x.strip() for x in key.split("to")]
                w.writerow([qno, "nat_range", "", lo, hi, ""])
    print("csv written:", OUT)

if __name__ == "__main__":
    main()
