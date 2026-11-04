"""taxonomy.yaml must match the official GATE 2027 syllabus PDFs: checksums and verbatim GA text.
Skipped on a fresh clone (the PDFs live in data/raw/, which is not in git)."""
import hashlib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TAX = yaml.safe_load((ROOT / "taxonomy.yaml").read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    return " ".join(s.split())


@pytest.mark.parametrize("pdf_key,sha_key", [("source_pdf", "source_sha256"), ("ga_source_pdf", "ga_source_sha256")])
def test_syllabus_pdf_checksums_match(pdf_key, sha_key):
    p = ROOT / TAX[pdf_key]
    if not p.exists():
        pytest.skip(f"{p} not present (fresh clone)")
    assert hashlib.sha256(p.read_bytes()).hexdigest() == TAX[sha_key]


def test_ga_section_text_is_verbatim_from_the_ga_pdf():
    p = ROOT / TAX["ga_source_pdf"]
    if not p.exists():
        pytest.skip("GA syllabus PDF not present (fresh clone)")
    import pymupdf
    with pymupdf.open(p) as d:
        pdf = _norm(" ".join(page.get_text() for page in d))
    ga = next(s for s in TAX["sections"] if s["id"] == "GA")
    assert _norm(ga["syllabus_text"]) in pdf


def test_every_ga_syllabus_item_has_a_concept():
    ga = next(s for s in TAX["sections"] if s["id"] == "GA")
    names = " | ".join(c["name"].lower() for t in ga["topics"] for c in t["concepts"])
    for item in ("grammar", "vocabulary", "reading comprehension", "narrative sequencing", "data interpretation",
                 "permutations", "mensuration and geometry", "probability", "deduction and induction", "analogy",
                 "transformation of shapes", "folding"):
        assert item in names, item
