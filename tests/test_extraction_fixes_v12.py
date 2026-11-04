"""Regression tests for the 5 Nov 2026 extractor fixes (footer spacing, centred labels) and the
audited repair rules in scripts/repair_extraction.py."""
import importlib.util
from pathlib import Path

from src.extraction.extract import HEADER_FOOTER, _lift_centered_labels

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("repair_extraction", ROOT / "scripts" / "repair_extraction.py")
rx = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(rx)


def L(y, x, text, y1=None, page=1):
    return {"page": page, "y": y, "y1": y1 if y1 is not None else y + 13, "x": x, "text": text}


def test_footer_with_double_spaces_and_and_header_are_boilerplate():
    assert HEADER_FOOTER.match("Page  7  of  41")
    assert HEADER_FOOTER.match("Page 7 of 41")
    assert HEADER_FOOTER.match("Computer Science and Information Technology (CS)")
    assert HEADER_FOOTER.match("Computer Science & Information Technology (CS1)")
    assert not HEADER_FOOTER.match("Pages of memory")


def test_stem_line_printed_above_a_centred_label_moves_to_its_question():
    lines = [L(371, 123, "(D)"), L(371, 149, "The number of boys who qualified the test is less"),
             L(82, 149, "A box contains five balls of same size and shape.  Three of them are green", y1=95, page=2),
             L(93, 99, "Q.8", page=2), L(101, 149, "coloured balls and two of them are orange", page=2)]
    out = [l["text"] for l in _lift_centered_labels(lines)]
    assert out.index("Q.8") < out.index("A box contains five balls of same size and shape.  Three of them are green")
    assert out[-1] == "coloured balls and two of them are orange"


def test_multi_line_paragraph_moves_but_stops_at_the_paragraph_gap():
    lines = [L(216.5, 120, "___________ . (rounded off to one decimal place)", y1=229.8),
             L(293.2, 120, "A 5-stage instruction pipeline has stage delays of 180, 250", y1=306.5),
             L(307.0, 120, "respectively, in nanoseconds. The delay of an inter-stage latch", y1=320.3),
             L(319.0, 78, "Q.56", y1=332.3),
             L(320.8, 120, "Assume that there are no pipeline stalls due to branches", y1=334.1)]
    out = [l["text"] for l in _lift_centered_labels(lines)]
    assert out[0].startswith("___")                      # previous question's last line stays
    assert out[1] == "Q.56" and out[2].startswith("A 5-stage") and out[3].startswith("respectively")


def test_fragments_page_markers_and_non_touching_lines_never_move():
    frag = [L(300, 150, "1"), L(310, 150, "x x 2", y1=330), L(320, 99, "Q.3")]
    assert [l["text"] for l in _lift_centered_labels(frag)] == ["1", "x x 2", "Q.3"]
    mark = [L(80, 400, "4/14", y1=100), L(90, 99, "Q.16")]
    assert [l["text"] for l in _lift_centered_labels(mark)] == ["4/14", "Q.16"]
    far = [L(200, 150, "the previous question ends with this long sentence", y1=213), L(260, 99, "Q.9")]
    assert [l["text"] for l in _lift_centered_labels(far)] == [l["text"] for l in far]


def test_repair_rules_accept_real_fixes_and_reject_ocr_noise():
    assert rx._better({"A": "a", "B": "b c d", "C": "", "D": ""}, {"A": "a", "B": "b", "C": "c 1", "D": "d 2"})
    assert rx._better({"A": "x", "D": "y Page  4  of  7"}, {"A": "x", "D": "y"})
    assert rx._better({"A": "a", "B": "b", "C": ""}, {"A": "a", "B": "b", "C": "x"}) is None     # lone OCR glyph
    assert rx._better({"A": "a x", "B": "3"}, {"A": "a", "B": "3 x"}) is None                   # noise moving
    assert rx._text_move_ok("coloured balls", "A box contains five balls of same size coloured balls")
    assert not rx._text_move_ok("Q text", "1 x x 2 Q text")                                     # fragment
    assert rx._text_move_ok("first part and the tail", "first part")
