"""v7 regression tests: multi-year ingestion, OCR plumbing, key parsing, registry, doctor/backup.
Everything here is synthetic - no real GATE data and no network."""
import json, sqlite3, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from src.db.models import (AnswerKey, Classification, ClassificationRun, Document, Option, Paper,
                           Question, ReviewEvent)
from src.db.session import make_session
from src.extraction import extract as ex, ocr
from src.ingestion import keypdf as kp, keys as km


# ------------------------------------------------------------------ key text normalisation
def test_norm_letters_variants():
    assert kp._norm_letters("B, C, D") == ("B;C;D", False)
    assert kp._norm_letters("b;c") == ("B;C", False)
    assert kp._norm_letters("MTA") == ("MTA", False)
    # OCR artefact: 'C;D' read as 'CORD' -> accepted but flagged as interpreted
    assert kp._norm_letters("CORD") == ("C;D", True)
    assert kp._norm_letters("E")[0] is None and kp._norm_letters("12")[0] is None


def _ocr_lines(rows):
    """rows: list of token lists -> OCR-like line dicts, one per row, top to bottom on one page."""
    return [{"page": 1, "y": 10.0 * i, "y1": 10.0 * i + 8, "x": 10.0, "text": " ".join(r), "conf": 1.0}
            for i, r in enumerate(rows)]

def _parse(rows):
    return kp.parse_tabular("x.pdf", None, ocr_lines=_ocr_lines(rows))

def _ga_rows():
    return [[str(n), "5", "MCQ", "GA", "A", "1" if n <= 5 else "2", "1/3"] for n in range(1, 11)]

def test_tabular_negative_marks_column_and_restart_numbering():
    rows = _ga_rows() + [[str(n), "5", "MCQ", "CS", "B", "1", "1/3"] for n in range(1, 56)]
    out = _parse(rows)
    assert [r.qno for r in out] == list(range(1, 66))       # CS 1..55 -> 11..65
    assert out[10].section == "CS" and out[10].marks == 1.0


def test_tabular_wrapped_nat_key_with_or_alternative():
    """Key cell wraps over 3 lines with the question number on the middle one (2021 layout)."""
    rows = _ga_rows() + [["1", "5", "NAT", "CS", "3", "to", "3", "1", "0"],
                         ["819", "to", "820"],
                         ["2", "5", "NAT", "CS", "OR", "205", "to", "1", "0"],
                         ["205"],
                         ["3", "5", "NAT", "CS", "2", "0"], ["17160", "to"], ["17160"]]
    # the empty-key row above sits BETWEEN its orphans: reorder so orphans straddle it correctly
    rows = _ga_rows() + [["1", "5", "NAT", "CS", "3", "to", "3", "1", "0"],
                         ["819", "to", "820"], ["2", "5", "NAT", "CS", "OR", "205", "to", "1", "0"], ["205"],
                         ["17160", "to"], ["3", "5", "NAT", "CS", "2", "0"], ["17160"]]
    out = _parse(rows)
    keys = {r.qno: r.key for r in out}
    assert keys[11] == "3 to 3"
    assert keys[12] == "819 to 820 OR 205 to 205"
    assert keys[13] == "17160 to 17160"
    recs = {r["qno"]: r for r in kp.to_records(out)}
    assert recs[12]["min"] == "819" and recs[12]["max"] == "820"          # first accepted range
    assert recs[12]["answer"] == "819 to 820;205 to 205"                  # ...but BOTH kept
    assert "any of these ranges" in recs[12]["notes"]


def test_tabular_order_repair_only_when_neighbours_prove_it():
    rows = _ga_rows() + [[str(n), "5", "MCQ", "CS", "C", "1", "0"] for n in range(1, 6)]
    rows[10 + 2][0] = "83"                                  # OCR read '3' as '83' between 2 and 4
    out = _parse(rows)
    assert [r.qno for r in out] == list(range(1, 16))
    assert "assigned 3 from table order" in out[12].note
    # two bad rows BOUNDED by good neighbours that prove the count (2 ... 5 => they must be 3,4) are repaired
    rows_ok = _ga_rows() + [[str(n), "5", "MCQ", "CS", "C", "1", "0"] for n in (1, 2, 40, 50, 5)]
    assert [r.qno for r in _parse(rows_ok)] == list(range(1, 16))
    # an ambiguous run (no later row proves the count) must NOT be repaired silently
    rows_bad = _ga_rows() + [[str(n), "5", "MCQ", "CS", "C", "1", "0"] for n in (1, 2, 40, 50, 60)]
    with pytest.raises(kp.KeyParseError):
        _parse(rows_bad)


def test_canonical_repairs_single_stray_but_not_more():
    # 1..9 and one stray 99: exactly one missing (10) and one stray -> unambiguous
    rows = [("GA", n, "MCQ", "A", 1.0) for n in range(1, 10)] + [("GA", 99, "MCQ", "A", 1.0)]
    assert [r.qno for r in kp._canonical(rows, "t")] == list(range(1, 11))
    bad = [("GA", n, "MCQ", "A", 1.0) for n in range(1, 8)] + [("GA", 98, "MCQ", "A", 1.0), ("GA", 99, "MCQ", "A", 1.0)]
    with pytest.raises(kp.KeyParseError):                      # two strays, two gaps: refuse to guess
        kp._canonical(bad, "t")


def test_canonical_continuous_vs_restart():
    cont = [("CS", n, "MCQ", "A", 1.0) for n in range(1, 56)] + [("GA", n, "MCQ", "A", 1.0) for n in range(56, 66)]
    assert [r.qno for r in kp._canonical(cont, "t")] == list(range(1, 66))     # 2012/2017 style: printed = canonical
    restart = [("GA", n, "MCQ", "A", 1.0) for n in range(1, 11)] + [("CS", n, "MCQ", "A", 1.0) for n in range(1, 56)]
    assert [r.qno for r in kp._canonical(restart, "t")] == list(range(1, 66))  # CS n -> n+10


def test_embedded_table_ocr_infers_lost_number_only_if_proved(tmp_path, monkeypatch):
    import pymupdf
    pdf = tmp_path / "k.pdf"
    d = pymupdf.open(); d.new_page(); d.save(str(pdf)); d.close()
    rows = [["1", "MCQ", "GA", "A", "1"], ["MCQ", "GA", "B", "1"], ["3", "MCQ", "GA", "C", "1"]]
    monkeypatch.setattr(ocr, "ocr_page", lambda doc, p, sha, dpi=200, cache_root=None: _ocr_lines(rows))
    out = kp.parse_embedded_table(pdf, (1, 1), ocr=True)
    assert [r.qno for r in out] == [1, 2, 3]
    rows[:] = [["1", "MCQ", "GA", "A", "1"], ["MCQ", "GA", "B", "1"], ["9", "MCQ", "GA", "C", "1"]]
    with pytest.raises(kp.KeyParseError):
        kp.parse_embedded_table(pdf, (1, 1), ocr=True)


# ------------------------------------------------------------------ key import cross-checks
def _paper_with(s, specs):
    s.add(Paper(id="P", year=2099, session="S1")); s.flush()
    for n, qt, marks, reason in specs:
        s.add(Question(id=f"P-Q{n:02d}", paper_id="P", q_number=n, marks=marks, q_type=qt,
                       needs_review=bool(reason), review_reason=reason))
    s.flush()

def test_key_import_flags_type_mismatch_and_upgrades_msq(blank_db):
    with make_session(blank_db) as s:
        _paper_with(s, [(1, "MCQ", 1.0, None), (2, "MCQ", 1.0, None), (3, "NAT", 2.0, None)])
        recs = [{"qno": 1, "kind": "msq_set", "answer": "A;C", "min": "", "max": "", "notes": "", "qtype": "MSQ", "marks": "1"},
                {"qno": 2, "kind": "nat_range", "answer": "", "min": "4", "max": "4", "notes": "", "qtype": "NAT", "marks": "1"},
                {"qno": 3, "kind": "nat_range", "answer": "", "min": "1", "max": "2", "notes": "", "qtype": "NAT", "marks": "1"}]
        res = km.import_key_records(s, "P", recs)
        q1, q2, q3 = (s.get(Question, f"P-Q0{n}") for n in (1, 2, 3))
        assert res["upgraded_to_msq"] == [1] and q1.q_type == "MSQ"
        assert res["type_mismatches"] == [{"qno": 2, "key": "NAT", "extracted": "MCQ"}]
        assert q2.needs_review and "key says NAT but extraction found MCQ" in q2.review_reason
        assert res["marks_mismatches"] == [{"qno": 3, "key": 1.0, "extracted": 2.0}]
        assert q2.q_type == "MCQ"                         # the key never silently overwrites extraction


def test_key_marks_confirm_clears_inferred_reason_only(blank_db):
    with make_session(blank_db) as s:
        inferred = km._INFERRED_MARKS
        _paper_with(s, [(1, "MCQ", 2.0, inferred), (2, "MCQ", 2.0, inferred + "; 3 options found")])
        km.import_key_records(s, "P", [
            {"qno": 1, "kind": "mcq_single", "answer": "A", "min": "", "max": "", "notes": "", "qtype": "MCQ", "marks": "2"},
            {"qno": 2, "kind": "mcq_single", "answer": "B", "min": "", "max": "", "notes": "", "qtype": "MCQ", "marks": "2"}])
        q1, q2 = s.get(Question, "P-Q01"), s.get(Question, "P-Q02")
        assert q1.needs_review is False and q1.review_reason is None
        assert q2.needs_review is True and q2.review_reason == "3 options found"   # other reason survives


def test_legacy_key_kinds_are_normalised(blank_db):
    assert km.normalize_kind("MCQ") == "mcq_single" and km.normalize_kind("MSQ") == "msq_set"
    assert km.normalize_kind("NAT") == "nat_range" and km.normalize_kind("mcq_single") == "mcq_single"


# ------------------------------------------------------------------ extractor helpers
def test_inline_options_split_only_in_order():
    assert ex._split_inline_options("(A) 5 (B) 7 (C) 9 (D) 11") == [("A", "5"), ("B", "7"), ("C", "9"), ("D", "11")]
    assert ex._split_inline_options("(A) yes (B) no") == [("A", "yes"), ("B", "no")]
    assert ex._split_inline_options("(B) only") is None                  # must start at A
    assert ex._split_inline_options("(A) x (C) y") is None               # out of order
    assert ex._split_inline_options("see (A) in the figure and (B) there")  is None  # label not at line start


def test_resplit_options_swallowed_label_only_when_absent():
    opts = [{"label": "A", "content": "x"}, {"label": "B", "content": "y"},
            {"label": "C", "content": "Q + R (D) PR + P"}]
    out = ex._resplit_options(opts)
    assert [o["label"] for o in out] == ["A", "B", "C", "D"] and out[2]["content"] == "Q + R" and out[3]["content"] == "PR + P"
    present = [{"label": "A", "content": "see (B) below"}, {"label": "B", "content": "real"}]
    assert ex._resplit_options(present)[0]["content"] == "see (B) below"   # B exists -> no split


def test_headers_multi_range_and_type_hint():
    lines = [{"text": "Q.1 to Q.5 carry 1 mark each & Q.6 to Q.10 carry 2 marks each"},
             {"text": "Q.28 – Q.35 Numerical Answer Type (NAT), carry ONE mark each."},
             {"text": "Q.1 – Q.5 Carry ONE mark Each"}]
    h = ex._find_headers(lines)
    assert h[0]["ranges"] == [(1, 5, 1.0), (6, 10, 2.0)]
    assert h[1]["type"] == "NAT" and h[1]["lo"] == 28 and h[1]["hi"] == 35 and h[1]["marks"] == 1.0
    assert h[2]["lo"] == 1 and h[2]["hi"] == 5


def test_pattern_marks_families():
    assert [ex.pattern_marks(n, True) for n in (1, 5, 6, 10, 11, 35, 36, 65)] == [1, 1, 2, 2, 1, 1, 2, 2]
    assert [ex.pattern_marks(n, False) for n in (1, 25, 26, 55, 56, 60, 61, 65)] == [1, 1, 2, 2, 1, 1, 2, 2]
    assert ex.pattern_marks(66, True) is None


def _L(text, page=1, y=100.0, x=60.0):
    return {"text": text, "page": page, "y": y, "y1": y + 10, "x": x, "src": "text", "conf": 1.0}

def test_sequence_aware_starts_ignore_stray_labels_and_restart_only_after_ga():
    lines = [_L(f"Q.{n}", y=20.0 * n) for n in range(1, 11)]                 # GA 1..10
    lines += [_L(f"Q.{n}", y=300 + 20.0 * n) for n in range(1, 4)]            # CS restarts at 1
    lines += [_L("Q.1 appears inside a stem", y=900)]                          # stray late 'Q.1' must NOT restart again
    starts, meta = ex._find_starts(lines, {})
    assert [s["canon"] for s in starts] == list(range(1, 14))                 # CS 1..3 -> 11..13
    assert meta["restarts"] == 1 and meta["ga_count"] == 10 and meta["rejected_candidates"] == 1


def test_no_restart_for_continuous_numbering():
    lines = [_L(f"Q.{n}", y=20.0 * n) for n in range(1, 61)] + [_L("Q.1 in a stem", y=3000)]
    starts, meta = ex._find_starts(lines, {})
    assert meta["restarts"] == 0 and len(starts) == 60 and meta["rejected_candidates"] == 1


def test_preamble_assigned_to_both_linked_questions():
    lines = [_L("Q.1", y=10), _L("(A) a", y=20), _L("(D) d", y=30),
             _L("Common Data Questions", y=40), _L("Common Data for Questions 2 and 3 :", y=50),
             _L("Consider this program", y=60), _L("Q.2", y=80), _L("Q.3", y=120)]
    starts, _ = ex._find_starts(lines, {})
    assert [s["printed"] for s in starts] == [1, 2, 3]
    ends, pre = ex._parse_preambles(lines, starts, {})
    assert ends[0] == 3                                           # Q1's body ends BEFORE the preamble block
    assert 2 in pre and 3 in pre and pre[2]["group"] == 2 and pre[3]["group"] == 2
    assert [l["text"] for l in pre[2]["lines"]][0] == "Common Data Questions"


def test_garble_ratio_and_group_rows():
    assert ocr.garble_ratio("Which one of the following is TRUE for all n >= 1 ? " * 3) == 0.0
    assert ocr.garble_ratio("ܩݐ" * 30 + "abc" * 10) > ocr.GARBLE_RATIO
    boxes = [{"text": "Q.12", "x": 80.0, "w": 20.0, "y": 100.0, "y1": 110.0, "h": 10.0, "cy": 105.0, "conf": 0.99},
             {"text": "The chip select logic", "x": 115.0, "w": 150.0, "y": 99.0, "y1": 110.0, "h": 11.0, "cy": 104.5, "conf": 0.98},
             {"text": "(A) 24 bits", "x": 120.0, "w": 50.0, "y": 140.0, "y1": 150.0, "h": 10.0, "cy": 145.0, "conf": 1.0},
             {"text": "(B) 28 bits", "x": 340.0, "w": 50.0, "y": 141.0, "y1": 151.0, "h": 10.0, "cy": 146.0, "conf": 1.0}]
    rows = ocr._group_rows(boxes)
    assert [r["text"] for r in rows] == ["Q.12 The chip select logic", "(A) 24 bits", "(B) 28 bits"]


# ------------------------------------------------------------------ end-to-end on a synthetic restart-family PDF
def _build_restart_pdf(path: Path) -> Path:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=LETTER)
    y = 740
    def line(t):
        nonlocal y
        c.drawString(60, y, t); y -= 16
        if y < 80:
            c.showPage(); y = 740
    line("Q.1 - Q.5 carry one mark each.")
    for n in range(1, 6):
        line(f"Q.{n} Pick the right word number {n}.")
        for lab in "ABCD":
            line(f"({lab}) choice {lab}")
    line("Q.6 - Q.10 carry two marks each.")
    for n in range(6, 11):
        line(f"Q.{n} A harder aptitude item {n}.")
        for lab in "ABCD":
            line(f"({lab}) choice {lab}")
    line("Q.1 - Q.25 carry one mark each.")
    for n in range(1, 4):
        line(f"Q.{n} CS question {n} about sorting.")
        for lab in "ABCD":
            line(f"({lab}) answer {lab}")
    line("Q.4 What is the value of the sum, numerical answer?")
    c.save()
    return path

def test_restart_family_end_to_end(tmp_path):
    pdf = _build_restart_pdf(tmp_path / "restart.pdf")
    recs, meta = ex.extract_paper(pdf, "GATE-CS-2099-S1", tmp_path / "a")
    nums = [r["q_number"] for r in recs]
    assert nums == list(range(1, 15)), nums                       # 10 GA + 4 CS renumbered 11..14
    assert meta["restarts"] == 1 and meta["ga_count"] == 10
    by = {r["q_number"]: r for r in recs}
    assert by[1]["printed_label"] == "GA 1" and by[11]["printed_label"] == "CS 1" and by[14]["printed_label"] == "CS 4"
    assert by[1]["marks"] == 1.0 and by[7]["marks"] == 2.0 and by[11]["marks"] == 1.0
    assert by[14]["q_type"] == "NAT" and by[11]["q_type"] == "MCQ"
    assert all(r["extraction_status"] == "extracted" for r in recs)


# ------------------------------------------------------------------ persistence semantics
def test_refresh_rewrites_untouched_rows_but_never_human_touched(blank_db):
    with make_session(blank_db) as s:
        s.add(Paper(id="P", year=2099, session="S1")); s.flush()
        rec = lambda n, txt, opt: {"id": f"P-Q{n:02d}", "paper_id": "P", "q_number": n, "text": txt, "marks": 1.0,
                                   "q_type": "MCQ", "page_start": 1, "page_end": 1, "image_path": None,
                                   "regions": [{"page": 1, "y_top": 1, "y_bottom": 2}],
                                   "options": [{"label": "A", "content": opt}], "needs_review": False,
                                   "review_reason": None, "extraction_confidence": 0.9,
                                   "extraction_status": "extracted", "printed_label": f"Q {n}", "group_id": None}
        ex.persist_records(s, [rec(1, "old one", "old A"), rec(2, "old two", "old A")])
        s.add(ReviewEvent(question_id="P-Q02", field="q_type", before="MCQ", after="MCQ", reviewer="human"))
        s.flush()
        res = ex.persist_records(s, [rec(1, "NEW one", "NEW A"), rec(2, "NEW two", "NEW A")], refresh=True)
        assert res["refreshed"] == 1
        assert s.get(Question, "P-Q01").text == "NEW one"
        assert s.scalar(select(Option.content).where(Option.question_id == "P-Q01")) == "NEW A"
        assert s.get(Question, "P-Q02").text == "old two"                        # human-touched: untouched
        assert s.scalar(select(Option.content).where(Option.question_id == "P-Q02")) == "old A"


def test_validation_unexplained_null_check(blank_db):
    from src.validation import validate as vd
    with make_session(blank_db) as s:
        s.add(Paper(id="P", year=2099, session="S1", reconciled=True)); s.flush()
        s.add(Question(id="P-Q01", paper_id="P", q_number=1, marks=1.0, q_type=None, needs_review=True,
                       review_reason="3 options found"))
        s.flush()
        chk = {c["check"]: c for c in vd.run_checks(s)}["no unexplained NULL marks/type"]
        assert chk["ok"] and "1 NULL questions are flagged" in chk["details"]
        s.add(Question(id="P-Q02", paper_id="P", q_number=2, marks=None, q_type="MCQ", needs_review=False))
        s.flush()
        assert not {c["check"]: c for c in vd.run_checks(s)}["no unexplained NULL marks/type"]["ok"]


def test_classification_run_accepts_composite_provider_and_model_values(blank_db):
    """Regression for the PostgreSQL-only VARCHAR(20) crash on 'auto:gemini+openrouter'."""
    with make_session(blank_db) as s:
        s.add(ClassificationRun(provider="auto:gemini+groq+openrouter+anthropic+openai", prompt_version="v1-ensemble-test",
                                model="+".join(["gemini-3.8-flash", "openai/gpt-oss-120b",
                                                "meta-llama/llama-3.3-70b-instruct:free", "claude-sonnet-4-5"])))
        s.commit()
        assert s.scalar(select(ClassificationRun.provider)).startswith("auto:gemini+groq")


# ------------------------------------------------------------------ classification safety at multi-paper scale
def _seed_other_version(s, qid, status="suggested"):
    s.add(Classification(question_id=qid, taxonomy_version="gate-cs-2027", prompt_version="agent-v1",
                         section_id="ALGO", primary_topic_id="ALGO.SORT", confidence=0.9,
                         status=status, model="agent", provenance="validated" if status == "verified" else "inferred"))
    s.flush()

def test_run_never_creates_a_second_row_for_an_existing_suggestion(loaded):
    """A live run over 'all questions' must not add a 2nd classification (it would double-count in every matrix)."""
    from src.classification import classify as cl
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        _seed_other_version(s, f"{pid}-Q01")
        res = cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        assert res["skipped_existing"] == 1 and res["classified"] == 5
        rows = s.scalars(select(Classification).where(Classification.question_id == f"{pid}-Q01")).all()
        assert len(rows) == 1 and rows[0].prompt_version == "agent-v1"          # untouched
        s.commit()


def test_verified_row_is_protected_across_prompt_versions(loaded):
    from src.classification import classify as cl
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        _seed_other_version(s, f"{pid}-Q02", status="verified")
        res = cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid, reclassify=True)   # even when forced
        assert res["skipped_verified"] == 1
        row = s.scalar(select(Classification).where(Classification.question_id == f"{pid}-Q02"))
        assert row.status == "verified" and row.prompt_version == "agent-v1"
        s.commit()


def test_reclassify_replaces_in_place_and_audits(loaded):
    from src.classification import classify as cl
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        _seed_other_version(s, f"{pid}-Q01")
        res = cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid, reclassify=True)
        assert res["classified"] == 6 and res["skipped_existing"] == 0
        rows = s.scalars(select(Classification).where(Classification.question_id == f"{pid}-Q01")).all()
        assert len(rows) == 1 and rows[0].prompt_version == cl.PROMPT_VERSION     # replaced, not duplicated
        ev = s.scalar(select(ReviewEvent).where(ReviewEvent.field == "classification_replaced"))
        assert ev is not None and "ALGO.SORT" in ev.before and ev.reviewer == "classifier-rerun"
        s.commit()


def test_compare_with_existing_writes_nothing(loaded):
    from src.classification import classify as cl
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        for n in (1, 2, 3):
            _seed_other_version(s, f"{pid}-Q0{n}")
        before = (s.scalar(select(Classification.id).limit(1)), len(s.scalars(select(Classification)).all()),
                  len(s.scalars(select(ReviewEvent)).all()))
        res = cl.compare_with_existing(s, cl.MockProvider(), "gate-cs-2027", pid, sample=1.0)
        assert res["sampled"] == 3 and res["answered"] == 3 and "Nothing was written" in res["caveat"]
        assert 0.0 <= res["topic_agreement"] <= 1.0 and res["verified_rows_compared"] == 0
        s.flush()
        after = (s.scalar(select(Classification.id).limit(1)), len(s.scalars(select(Classification)).all()),
                 len(s.scalars(select(ReviewEvent)).all()))
        assert before == after


def test_provider_history_comes_from_recorded_attempts_not_key_presence(loaded, monkeypatch):
    from src.classification import classify as cl
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        assert cl.provider_history(s) == {}                                        # key set, nothing ever ran
        _seed_other_version(s, f"{pid}-Q01")
        c = s.scalar(select(Classification))
        c.provider_votes = [{"provider": "gemini", "model": "m", "topic": "ALGO.SORT", "confidence": 0.9},
                            {"provider": "groq", "model": "g", "error": "HTTP 429 from provider: rate limit"}]
        s.flush()
        h = cl.provider_history(s)
        assert h["gemini"]["successes"] == 1 and h["gemini"]["last_success_at"] is not None
        assert h["groq"]["errors"] == 1 and "429" in h["groq"]["last_error"]


def test_explain_provider_error_is_plain_language():
    from src.classification import classify as cl
    assert cl.explain_provider_error(None) is None
    assert "API key" in cl.explain_provider_error("HTTP 401 from provider: invalid api key")["what"]
    assert "model" in cl.explain_provider_error("HTTP 404 ... model not found")["what"].lower()
    assert "Rate limit" in cl.explain_provider_error("HTTP 429 from provider")["what"]
    assert "JSON" in cl.explain_provider_error("response failed contract validation")["what"]
    assert cl.explain_provider_error("weird")["fix"]


# ------------------------------------------------------------------ registry, paths, schema upgrade, doctor, backup
def test_manifest_loads_unique_ids_and_status_filtering():
    from src.ingestion import registry as rg
    entries = rg.load_manifest()
    ids = [e.paper_id for e in entries]
    assert len(ids) == len(set(ids))
    active = rg.select(entries)
    assert all(e.status == "active" for e in active) and not any(e.year <= 2010 for e in active)
    assert any(e.paper_id == "GATE-CS-2026-S1" for e in active)
    assert [e.paper_id for e in rg.select(entries, only="2013")] == [f"GATE-CS-2013-S{i}" for i in (1, 2, 3, 4)]
    assert all(e.expected_questions == 65 and e.expected_marks == 100.0 for e in active)


def test_resolve_document_path_survives_rename(tmp_path):
    import hashlib
    from src.ingestion import paths
    raw = tmp_path / "raw"; raw.mkdir()
    f = raw / "CS1_2026.pdf"; f.write_bytes(b"%PDF-1.4 renamed file content")
    doc = Document(id="d", filename="CS1.pdf", sha256=hashlib.sha256(f.read_bytes()).hexdigest(),
                   file_path="data/raw/papers/2026/CS1.pdf", doc_type="paper")
    got = paths.resolve_document_path(doc, root=raw)
    assert got == f
    doc2 = Document(id="e", filename="x.pdf", sha256="0" * 64, file_path="nope/x.pdf", doc_type="paper")
    assert paths.resolve_document_path(doc2, root=raw) is None


def test_sync_missing_columns_adds_printed_label_to_old_database(tmp_path):
    from src.db import dev_upgrade
    p = tmp_path / "old.sqlite"
    con = sqlite3.connect(p)
    con.execute("create table papers (id text primary key, year integer, branch text, session text, paper_code text, "
                "document_id text, expected_questions integer, expected_marks float, derived_questions integer, "
                "derived_marks float, reconciled boolean)")
    con.execute("create table questions (id text primary key, paper_id text, q_number integer, text text, marks float, "
                "q_type text, page_start integer, page_end integer, image_path text, regions_json text, group_id text, "
                "extraction_confidence float, extraction_status text, needs_review boolean, review_reason text)")
    con.execute("insert into questions (id, paper_id, q_number, text) values ('P-Q01','P',1,'keep me')")
    con.commit(); con.close()
    url = f"sqlite:///{p}"
    out = dev_upgrade.sync_missing_columns(url)
    assert out["added"]["questions"] == ["printed_label"]
    again = dev_upgrade.sync_missing_columns(url)
    assert again["added"] == {}                                                   # idempotent
    assert sqlite3.connect(p).execute("select text from questions").fetchone()[0] == "keep me"


def test_backup_sqlite_is_consistent_and_leaves_source_untouched(tmp_path):
    from src import backup as bk
    src = tmp_path / "live.sqlite"
    con = sqlite3.connect(src); con.execute("create table papers (id text)"); con.execute("insert into papers values ('a')")
    con.execute("create table questions (id text)"); con.commit(); con.close()
    before = src.read_bytes()
    out = bk.backup_sqlite(src, tmp_path / "bk")
    assert out["integrity_check"] == "ok" and Path(out["file"]).exists() and out["rows"]["papers"] == 1
    assert src.read_bytes() == before


def test_doctor_never_prints_secrets(blank_db, monkeypatch):
    from src import doctor as dc
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-VALUE-1234567890")
    res = dc.run_checks(blank_db)
    text = dc.render(res)
    assert "SECRET-VALUE-1234567890" not in text
    names = {r["name"] for r in res}
    assert {"Python version", "Database connection", "Database schema", "LLM provider keys"} <= names
    assert next(r for r in res if r["name"] == "LLM provider keys")["level"] == dc.PASS
