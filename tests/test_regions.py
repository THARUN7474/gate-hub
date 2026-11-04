"""Region storage + on-demand rendering: the replacement for stored crops."""
import json
import pymupdf as fitz
from sqlalchemy import select

from src.db.session import make_session
from src.db.models import Question
from src.extraction.extract import extract_questions, persist_records
from src.extraction.render import render_question_regions


def test_regions_stored_for_every_question(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        qs = {q.id: q for q in s.scalars(select(Question))}
    for qid, q in qs.items():
        regions = json.loads(q.regions_json)
        assert regions, qid
        for seg in regions:
            assert seg["page"] >= 1
            assert seg["y_bottom"] > seg["y_top"]
        assert regions[0]["page"] == q.page_start
        assert regions[-1]["page"] == q.page_end


def test_on_demand_render_matches_region(loaded, fixture_paper):
    """Every stored region renders to a real PNG from the source PDF."""
    db_url, pid, _ = loaded
    pdf, _ = fixture_paper
    with make_session(db_url) as s:
        qs = {q.id: q for q in s.scalars(select(Question))}
    for qid, q in qs.items():
        out = render_question_regions(pdf, json.loads(q.regions_json))
        assert len(out) == q.page_end - q.page_start + 1
        for seg in out:
            assert seg["png"].startswith(b"\x89PNG")
            assert len(seg["png"]) > 2000  # actual content, not a blank sliver


def test_multi_page_region_render(tmp_path):
    """A question spanning pages renders one image per page, in order."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas
    pdf = tmp_path / "two_page.pdf"
    c = canvas.Canvas(str(pdf), pagesize=LETTER)
    c.drawString(72, 700, "Q.1 stem on page one")
    c.showPage()
    c.drawString(72, 700, "(A) option continued on page two")
    c.save()
    doc = fitz.open(str(pdf))
    regions = [{"page": 1, "y_top": 100, "y_bottom": 110},
               {"page": 2, "y_top": 100, "y_bottom": 110}]
    out = render_question_regions(pdf, regions)
    doc.close()
    assert [seg["page"] for seg in out] == [1, 2]
    assert all(seg["png"].startswith(b"\x89PNG") for seg in out)


def test_write_crops_opt_in(loaded, fixture_paper, tmp_path):
    """Stored PNG crops remain available behind write_crops=True."""
    pdf, _ = fixture_paper
    db_url, pid, _ = loaded
    recs = extract_questions(pdf, pid, tmp_path / "assets3", write_crops=True)
    assert all(r["image_path"] for r in recs)
    assert all(r["regions"] for r in recs)
    # default stays image-free
    recs2 = extract_questions(pdf, pid, tmp_path / "assets4")
    assert all(r["image_path"] is None for r in recs2)
    assert not (tmp_path / "assets4").exists() or not list((tmp_path / "assets4").iterdir())
