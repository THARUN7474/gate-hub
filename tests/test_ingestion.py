import zipfile
import pytest
from src.db.session import make_session
from src.ingestion import ingest as ig

def test_sha_dedup(db_url, tmp_path):
    a = tmp_path / "a.pdf"; a.write_bytes(b"%PDF-1.4 same")
    b = tmp_path / "b.pdf"; b.write_bytes(b"%PDF-1.4 same")
    with make_session(db_url) as s:
        d1, new1 = ig.register_document(s, a, role="paper")
        d2, new2 = ig.register_document(s, b, role="paper")
        s.commit()
    assert d1.id == d2.id and new1 and not new2

def test_magic_bytes(tmp_path):
    f = tmp_path / "fake.pdf"; f.write_bytes(b"nope")
    assert ig.magic_kind(f) == "other"

def test_zip_slip_rejected(tmp_path):
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../../escape.txt", "x")
    with pytest.raises(ValueError, match="zip-slip"):
        ig.safe_extract_zip(z, tmp_path / "out")

def test_paper_identity_conflict(db_url, tmp_path):
    f1 = tmp_path / "p1.pdf"; f1.write_bytes(b"%PDF-1.4 v1")
    f2 = tmp_path / "p2.pdf"; f2.write_bytes(b"%PDF-1.4 v2 different")
    with make_session(db_url) as s:
        d1, _ = ig.register_document(s, f1, role="paper")
        d2, _ = ig.register_document(s, f2, role="paper")
        pid, st1 = ig.register_paper(s, 2024, "CS-1", d1.id)
        _, st_dup = ig.register_paper(s, 2024, "CS-1", d1.id)
        _, st_conf = ig.register_paper(s, 2024, "CS-1", d2.id)
        s.commit()
    assert (st1, st_dup, st_conf) == ("new", "existing", "conflict")

def test_role_detection():
    assert ig.detect_role("CS1-2024-key.pdf") == "key"
    assert ig.detect_role("CS_GATE2027_Syllabus.pdf") == "syllabus"
    assert ig.detect_role("CS1-2024.pdf") == "paper"
    assert ig.detect_role("scan0042.pdf") == "unknown"
