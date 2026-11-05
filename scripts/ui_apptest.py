"""UI interaction + persistence check via Streamlit AppTest (NOT a browser).

Drives app.py against a SCRATCH copy of the database. Covers the v6 approval
surface: Verify as-is / Flag / Save correction / Verify with correction /
Approve & next in the Review Workspace, and the Approve Queue batch approval.
AppTest is the Streamlit in-process test harness; browser-level clicking is
verified separately with Playwright screenshots (scripts/ui_screenshots.py).

Usage: python scripts/ui_apptest.py
"""
from __future__ import annotations
import os, shutil, sqlite3, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

tmp = Path(tempfile.mkdtemp(prefix="gate-apptest-"))
db = tmp / "test.db"
# Source DB to COPY (never modified): $GATE_APPTEST_DB, else the live DB (all 29 papers since 5 Nov 2026).
_src = Path(os.environ.get("GATE_APPTEST_DB") or (ROOT / "data" / "gate_cse.sqlite"))
shutil.copy(_src, db)
os.environ["GATE_DB_URL"] = f"sqlite:///{db}"
os.environ["GATE_REVIEWER"] = "TEST-AUTOMATION"     # synthetic clicks are never attributed to a human


from streamlit.testing.v1 import AppTest  # noqa: E402

Q = "GATE-CS-2026-S1-Q03"
# v11: put Q into a benchmark batch (pending) so the verify flow can be checked end to end
_con = sqlite3.connect(db)
_con.execute("INSERT OR IGNORE INTO benchmark_samples (question_id, batch, stratum, status, sampled_at)"
             " VALUES (?, 'apptest-b1', '2026-CS-1/marks1', 'pending_user_review', '2026-11-04T00:00:00+00:00')", (Q,))
_con.commit(); _con.close()

def set_rubric(at):
    """Tick every rubric check as pass (v8: verify requires a complete passing rubric)."""
    from src.validation import review as _rv
    for _k, _lab, _h in _rv.RUBRIC:
        _r = next((r for r in at.radio if r.label == _lab), None)
        if _r is not None:
            _r.set_value(1)
    at.run()


def dbval(sql):
    con = sqlite3.connect(db)
    r = con.execute(sql).fetchall()
    con.close()
    return r

def main() -> None:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    assert not at.exception, at.exception

    # every screen renders cleanly
    for screen in ["Pipeline Status", "About the Data", "Question Browser", "Analysis Matrix",
                   "Topic Report", "Subject Overview", "Review Workspace", "Second Opinions", "Approve Queue",
                   "LLM Classify", "Engine & Pipeline", "Glossary & Syllabus"]:
        at.sidebar.radio[0].set_value(screen)
        at.run()
        assert not at.exception, (screen, at.exception)
    print("PASS all 12 screens render")

    at.sidebar.radio[0].set_value("Review Workspace")
    at.run()
    qsel = next(s for s in at.selectbox if s.label == "Question")
    qsel.set_value(Q)
    at.run()
    assert not at.exception, at.exception

    next(b for b in at.button if b.label == "Flag").click().run()
    assert dbval(f"select status from classifications where question_id='{Q}'") == [("flagged",)]
    print(f"PASS Flag persisted: {Q} -> flagged")

    set_rubric(at)
    next(b for b in at.button if b.label == "Verify as-is").click().run()
    assert dbval(f"select status from classifications where question_id='{Q}'") == [("verified",)]
    print(f"PASS Verify as-is persisted: {Q} -> verified")

    # v11: the verified question's benchmark row (seeded below) became gold via the normal flow
    import sqlite3 as _sq
    con = _sq.connect(db)
    grew = con.execute("select status, gold_primary_topic_id, reviewer from benchmark_samples where question_id=?", (Q,)).fetchone()
    con.close()
    assert grew and grew[0] == "gold_verified" and grew[1] and grew[2] == "TEST-AUTOMATION", grew
    print(f"PASS benchmark gold recorded by normal verify: {Q} -> {grew[0]}, gold topic {grew[1]}")


    ssel = next(s for s in at.selectbox if s.label == "Section")
    ssel.set_value("DL")
    at.run()
    tsel = next(s for s in at.selectbox if s.label == "Topic")
    tsel.set_value("DL.NUM")
    at.run()
    next(b for b in at.button if b.label == "Save without verifying").click().run()
    row = dbval(f"select primary_topic_id, section_id from classifications where question_id='{Q}'")
    assert row == [("DL.NUM", "DL")], row
    print("PASS Save without verifying persisted: topic -> DL.NUM, section auto-synced -> DL")

    # Verify with correction on another question
    Q2 = "GATE-CS-2026-S1-Q04"
    qsel = next(s for s in at.selectbox if s.label == "Question")
    qsel.set_value(Q2)
    at.run()
    ssel = next(s for s in at.selectbox if s.label == "Section")
    ssel.set_value("DL")
    at.run()
    tsel = next(s for s in at.selectbox if s.label == "Topic")
    tsel.set_value("DL.NUM")
    at.run()
    set_rubric(at)
    next(b for b in at.button if b.label == "Verify with correction").click().run()
    row = dbval(f"select primary_topic_id, status from classifications where question_id='{Q2}'")
    assert row == [("DL.NUM", "verified")], row
    print(f"PASS Verify with correction: {Q2} -> DL.NUM verified")

    # Approve & next jumps to another pending question
    Q3 = "GATE-CS-2026-S1-Q05"
    qsel = next(s for s in at.selectbox if s.label == "Question")
    qsel.set_value(Q3)
    at.run()
    set_rubric(at)
    next(b for b in at.button if b.label == "Approve & next").click().run()
    assert dbval(f"select status from classifications where question_id='{Q3}'") == [("verified",)]
    cur = next(s for s in at.selectbox if s.label == "Question").value
    assert cur != Q3, cur
    print(f"PASS Approve & next: {Q3} verified, jumped to {cur}")

    ev = dbval(f"select field, after, reviewer from review_events where question_id='{Q}' order by rowid")
    assert any(e[0] == "status" for e in ev) and any(e[0] == "primary_topic_id" for e in ev)
    print("PASS review events recorded:", len(ev), "for", Q)

    # Paper/question state sync (v10): a deep link drives BOTH filters; switching paper
    # resets the question to that paper; saves always target the DISPLAYED question.
    at.sidebar.radio[0].set_value("Review Workspace")
    at.run()
    at.query_params["review_q"] = "GATE-CS-2011-S1-Q64"
    at.run()
    at.run()  # deep link consumed, screen switched
    assert not at.exception, at.exception
    psel = next(s for s in at.selectbox if s.label == "Paper")
    qsel = next(s for s in at.selectbox if s.label == "Question")
    assert psel.value == "GATE-CS-2011-S1", psel.value
    assert qsel.value == "GATE-CS-2011-S1-Q64", qsel.value
    print("PASS deep link syncs paper + question:", qsel.value)
    psel.set_value("GATE-CS-2012-S1")
    at.run()
    qsel = next(s for s in at.selectbox if s.label == "Question")
    assert str(qsel.value).startswith("GATE-CS-2012-S1-"), f"stale question after paper switch: {qsel.value}"
    # save targets the displayed (new paper's) question, never the stale one
    next(b for b in at.button if b.label == "Flag").click().run()
    assert dbval(f"select status from classifications where question_id='{qsel.value}'") == [("flagged",)]
    assert dbval("select status from classifications where question_id='GATE-CS-2011-S1-Q64'") != [("flagged",)]
    print("PASS paper switch resets question; save targets displayed question:", qsel.value)

    # Approve Queue: batch approve with a topic correction via per-row widgets.
    # v8: the queue only approves rows that already have a passing rubric, so give the
    # first queue row its rubric in the Review Workspace first (Save without verifying).
    at.sidebar.radio[0].set_value("Approve Queue")
    at.run()
    assert not at.exception, at.exception
    next(tg for tg in at.toggle if tg.key == "aq_only_ready").set_value(False)
    at.run()
    appr = [c for c in at.checkbox if c.label == "Approve"]
    assert appr, "no approve checkboxes on Approve Queue"
    qid = appr[0].key.removeprefix("aq_appr_")
    at.sidebar.radio[0].set_value("Review Workspace")
    at.run()
    next(s for s in at.selectbox if s.label == "Question").set_value(qid)
    at.run()
    set_rubric(at)
    next(b for b in at.button if b.label == "Save without verifying").click().run()
    at.sidebar.radio[0].set_value("Approve Queue")
    at.run()
    next(c for c in at.checkbox if c.key == f"aq_appr_{qid}").set_value(True)
    corr = next(s for s in at.selectbox if s.key == f"aq_corr_{qid}")
    corr.set_value("DL.NUM")
    at.run()
    cb = next(c for c in at.checkbox if "reviewed the" in c.label)
    cb.set_value(True)
    at.run()
    btn = next(b for b in at.button if b.label.startswith("Approve 1 selected"))
    assert not btn.disabled
    btn.click().run()
    assert not at.exception, at.exception
    row = dbval(f"select primary_topic_id, status from classifications where question_id='{qid}'")
    assert row == [("DL.NUM", "verified")], row
    ev = dbval(f"select count(*) from review_events where question_id='{qid}' and note='approve queue'")
    assert ev[0][0] >= 2, ev
    print(f"PASS Approve Queue: {qid} corrected to DL.NUM + verified with audit events")

    # Analysis Matrix: clickable HTML matrix present with drill links
    at.sidebar.radio[0].set_value("Analysis Matrix")
    at.run()
    html_blocks = [m.value for m in at.markdown]
    assert any("drill_sec=" in h and "drill_year=" in h for h in html_blocks), "no clickable matrix found"
    print("PASS Analysis Matrix renders clickable cell links")

    # v11: review-priority ordering in the Review Workspace
    at.sidebar.radio[0].set_value("Review Workspace")
    at.run()
    oradio = next(r for r in at.radio if r.label == "Order")
    oradio.set_value("review priority first")
    at.run()
    assert not at.exception, at.exception
    qsel = next(s for s in at.selectbox if s.label == "Question")
    first = qsel.options[0]
    assert str(first).startswith("GATE-CS-2011-S1-Q05"), f"priority order should lead with the taxonomy-gap question, got {first}"
    qsel.set_value("GATE-CS-2011-S1-Q05")
    at.run()
    assert not at.exception, at.exception
    assert any("taxonomy gap" in (c.value or "") for c in at.caption), "priority bucket caption missing"
    print("PASS review priority order: taxonomy-gap question first, bucket caption shown")
    # v11: benchmark filter renders and lists only pending sample questions
    sradio = next(r for r in at.radio if r.label == "Show")
    sradio.set_value("benchmark sample (gold review)")
    at.run()
    assert not at.exception, at.exception
    qsel = next(s for s in at.selectbox if s.label == "Question")
    assert all(not str(o).startswith(Q + " ") and str(o).split()[0] != Q for o in qsel.options), "verified gold must leave the pending list"
    print(f"PASS benchmark filter: {len(qsel.options)} pending sample questions listed (gold one excluded)")

    # v13: extraction-issue filter lists only extractor-flagged questions
    sradio = next(r for r in at.radio if r.label == "Show")
    sradio.set_value("extraction issues")
    at.run()
    assert not at.exception, at.exception
    qsel = next(s for s in at.selectbox if s.label == "Question")
    flagged = {r[0] for r in dbval("select id from questions where needs_review=1")}
    assert qsel.options and all(str(o).split()[0] in flagged for o in qsel.options)
    print(f"PASS extraction-issues filter: {len(qsel.options)} questions, all extractor-flagged")

    # v13: Pipeline Status stage buttons jump to the right screen with filters preset
    at.sidebar.radio[0].set_value("Pipeline Status")
    at.run()
    next(b for b in at.button if b.label == "Review the benchmark").click().run()
    assert not at.exception, at.exception
    assert at.sidebar.radio[0].value == "Review Workspace", at.sidebar.radio[0].value
    assert next(r for r in at.radio if r.label == "Show").value == "benchmark sample (gold review)"
    at.sidebar.radio[0].set_value("Pipeline Status")
    at.run()
    next(b for b in at.button if b.label == "See AI opinions").click().run()
    assert at.sidebar.radio[0].value == "Second Opinions" and not at.exception
    print("PASS stage buttons open the right screen with filters preset")

    # v13: Question Browser lists every question (no 500 cap)
    at.sidebar.radio[0].set_value("Question Browser")
    at.run()
    nq = dbval("select count(*) from questions")[0][0]
    assert any(f"**{nq:,}** of {nq:,}" in (m.value or "") for m in at.markdown), "browser should list all questions"
    print(f"PASS Question Browser lists all {nq} questions")

    # v13: status guide shown on the Glossary and as a dropdown explanation in the browser
    at.sidebar.radio[0].set_value("Glossary & Syllabus")
    at.run()
    assert any("Awaiting your decision" in (m.value or "") for m in at.markdown), "status guide missing on Glossary"
    at.sidebar.radio[0].set_value("Question Browser")
    at.run()
    ls = next(s for s in at.selectbox if s.label == "Label status")
    assert ls.format_func("verified").startswith("verified (you checked")
    print("PASS status guide on Glossary + explained Label status dropdown")

    print("ALL APPTEST CHECKS PASSED (scratch DB:", db, ")")

if __name__ == "__main__":
    main()
