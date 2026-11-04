"""Generic key-PDF parser: real bundled 2025 key + synthetic token streams."""
import os
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import keypdf_to_csv as kp

_ROOT = Path(__file__).resolve().parents[1]
# The owner's raw-data naming is CS1_Keys_2025.pdf; older drops used CS1_Keys.pdf.
KEY2025 = next((p for p in (_ROOT / "data/raw/keys/2025/CS1_Keys_2025.pdf",
                            _ROOT / "data/raw/keys/2025/CS1_Keys.pdf") if p.exists()),
               _ROOT / "data/raw/keys/2025/CS1_Keys_2025.pdf")

@pytest.mark.skipif(not KEY2025.exists(), reason="bundled 2025 key PDF absent")
def test_parse_real_2025_key():
    rows = kp.parse_key_pdf(str(KEY2025))
    assert len(rows) == 65
    assert [r[0] for r in rows] == list(range(1, 66))
    by_q = {r[0]: r for r in rows}
    assert by_q[1][1] == "MCQ" and by_q[1][3] == "A"
    assert by_q[21][1] == "MSQ" and by_q[21][3] == "B;D"
    # Q59 is the NAT the extractor mistyped - the key says NAT
    assert by_q[59][1] == "NAT"
    nats = [q for q, r in by_q.items() if r[1] == "NAT"]
    assert len(nats) > 10

def test_parse_tokens_nat_range_and_mta():
    toks = ("Answer Key for CS1 Q. No. Session Q. Type Section Key/Range Marks "
            "1 1 MCQ GA A 1 "
            "2 1 NAT CS-1 4096 to 4096 2 "
            "3 1 NAT CS-1 0.370 to 0.380 2 "
            "4 1 MSQ CS-1 B;D 1").split()
    rows = kp.parse_key_tokens(toks)
    assert rows == [(1, "MCQ", "GA", "A", 1),
                    (2, "NAT", "CS-1", "4096 to 4096", 2),
                    (3, "NAT", "CS-1", "0.370 to 0.380", 2),
                    (4, "MSQ", "CS-1", "B;D", 1)]
