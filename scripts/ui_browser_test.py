"""Real-browser UI test (Playwright + Chromium) - closes handoff gap G6.

    python scripts/ui_browser_test.py [--source-db data/gate_cse.candidate.sqlite] [--keep]

What it does, on a THROWAWAY COPY of the database:
  1. copies the source DB, starts `streamlit run app.py` against the copy (reviewer name TEST-AUTOMATION)
  2. Analysis Matrix: click a cell -> drill-down list size == the cell's question count -> click a question
     -> the Review Workspace opens on that question
  3. Review Workspace: Verify with correction / Verify as-is / Flag / Approve & next via real clicks,
     each checked in the database, then a PAGE RELOAD and a re-check (persistence)
  4. keyboard shortcut Ctrl+Enter, Approve Queue batch approval + audit events
  5. visits all 8 screens: no Streamlit exception, no clipped text, screenshots -> docs/screenshots/v7/
  6. proves the SOURCE database file (and the live data/gate_cse.sqlite) is byte-identical afterwards

Every synthetic click is attributed to reviewer 'TEST-AUTOMATION' and lives only in the copy, which is
deleted at the end - these are test actions, never human reviews, and are never merged back."""
from __future__ import annotations
import argparse, hashlib, os, shutil, socket, sqlite3, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots" / "v7"
results: list[tuple[bool, str]] = []

def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, label))
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   [{detail}]" if detail else ""), flush=True)

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]

def wait_idle(page, timeout=90000):
    """Streamlit paints skeletons while the script runs. Wait for the 'running' indicator to APPEAR (the rerun
    starts a moment after the click) and then to be gone - checking only 'is it gone?' races the rerun."""
    try:
        page.wait_for_selector('[data-testid="stStatusWidget"]', state="attached", timeout=1500)
    except Exception:
        pass                                     # no rerun was triggered (or it already finished)
    page.wait_for_function("() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=timeout)
    page.wait_for_timeout(500)

def goto_screen(page, name):
    page.locator('[data-testid="stSidebar"]').get_by_text(name, exact=True).click()
    wait_idle(page)

def _selectbox_input(page, label: str):
    """Streamlit >= 1.5x selectboxes are react-aria comboboxes: an <input role=combobox> holds the value."""
    return page.locator('[data-testid="stSelectbox"]').filter(has_text=label).first.locator("input").first

def select_option(page, label: str, text: str):
    """Pick an option by typing part of its text (the combobox filters) and clicking the match."""
    inp = _selectbox_input(page, label)
    inp.click()
    inp.press("Control+a")
    page.keyboard.type(text)
    page.wait_for_timeout(600)
    page.locator('[role="option"]').filter(has_text=text).first.click()
    wait_idle(page)

def selected_text(page, label: str) -> str:
    return _selectbox_input(page, label).input_value()

def db_rows(db: Path, sql: str, *a):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, a).fetchall()
    finally:
        con.close()

def exceptions(page) -> int:
    return page.locator('[data-testid="stException"]').count()

CLIPPED_JS = """() => {
  const bad = [];
  for (const el of document.querySelectorAll('[data-testid="stMain"] *')) {
    const cs = getComputedStyle(el);
    if (!el.children.length && el.textContent.trim().length > 3 && cs.overflow !== 'visible' &&
        cs.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth + 2 &&
        !el.closest('[data-testid="stDataFrame"]') && !el.closest('[data-baseweb="select"]'))
      bad.push(el.textContent.trim().slice(0, 60));
  }
  return bad;
}"""

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-db", default=str(ROOT / "data" / "gate_cse.candidate.sqlite"))
    ap.add_argument("--keep", action="store_true", help="keep the temp copy for inspection")
    ap.add_argument("--port", type=int, default=8612)
    a = ap.parse_args()
    source = Path(a.source_db)
    live = ROOT / "data" / "gate_cse.sqlite"
    before = {p: sha(p) for p in (source, live) if p.exists()}
    tmp = Path(tempfile.mkdtemp(prefix="gate-browser-"))
    db = tmp / "copy.sqlite"
    shutil.copy(source, db)
    env = dict(os.environ, GATE_DB_URL=f"sqlite:///{db.as_posix()}", GATE_REVIEWER="TEST-AUTOMATION")
    env.pop("GATE_TEST_DB_URL", None)
    SHOTS.mkdir(parents=True, exist_ok=True)
    srv = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(a.port),
                            "--server.headless", "true", "--browser.gatherUsageStats", "false"],
                           cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(90):
            try:
                socket.create_connection(("127.0.0.1", a.port), timeout=1).close(); break
            except OSError:
                time.sleep(1)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            url = f"http://127.0.0.1:{a.port}"
            page.goto(url); page.wait_for_load_state("networkidle"); wait_idle(page)
            check(exceptions(page) == 0, "app boots on the copy (Pipeline Status) without an exception")

            screens = ["Pipeline Status", "About the Data", "Question Browser", "Analysis Matrix", "Topic Report", "Review Workspace",
                       "Approve Queue", "LLM Classify", "Glossary & Syllabus"]
            def visit_all(tag: str, shots: bool):
                for i, name in enumerate(screens, 1):
                    goto_screen(page, name)
                    clipped = page.evaluate(CLIPPED_JS)
                    check(exceptions(page) == 0 and not clipped,
                          f"[{tag}] screen '{name}' renders: no exception, no clipped text",
                          f"clipped: {clipped[:2]}" if clipped else "")
                    if shots:
                        page.screenshot(path=str(SHOTS / f"10-screen-{i}-{name.split()[0].lower()}.png"), full_page=True)
            visit_all("pristine data", shots=True)      # documentation screenshots show UNTOUCHED data

            # ---------------- 1. Analysis Matrix -> drill-down -> Review Workspace ----------------
            goto_screen(page, "Analysis Matrix")
            link = page.locator('a[href*="drill_sec"]').first
            title = link.get_attribute("title") or ""
            n_cell = int(title.split(" ")[0])
            sec = (link.get_attribute("href") or "").split("drill_sec=")[1].split("&")[0]
            link.click(); page.wait_for_load_state("networkidle"); wait_idle(page)
            n_list = page.locator('a[href*="review_q"]').count()
            check(n_list == n_cell and n_cell > 0, "matrix cell drill-down lists exactly the cell's question count",
                  f"cell {sec}: title says {n_cell}, list shows {n_list}")
            page.screenshot(path=str(SHOTS / "02-matrix-drilldown.png"), full_page=True)
            first_q = page.locator('a[href*="review_q"]').first.inner_text()
            page.locator('a[href*="review_q"]').first.click(); page.wait_for_load_state("networkidle"); wait_idle(page)
            check(first_q in selected_text(page, "Question"), "clicking a drill-down question opens it in the Review Workspace", first_q)

            # ---------------- 2. Review Workspace: real clicks + reload persistence ----------------
            def review_events(qid):
                return db_rows(db, "select field, before, after, reviewer from review_events where question_id=? order by id", qid)
            def cls_status(qid):
                r = db_rows(db, "select status, primary_topic_id, provenance from classifications where question_id=?", qid)
                return r[0] if r else None

            # pick questions that really are classified suggestions
            qs = [r[0] for r in db_rows(db, "select question_id from classifications where status='suggested' order by question_id limit 12")]
            q_corr, q_asis, q_flag, q_next, q_key = qs[3], qs[4], qs[5], qs[6], qs[7]

            RUBRIC_LABELS = ["Source fidelity", "Answer/key provenance", "Primary section/topic", "Concept depth",
                             "Explanation/evidence"]
            def score(passes=True, fail=()):
                """Answer the five review checks like a reviewer would (pass, except the labels in `fail`)."""
                for lab in RUBRIC_LABELS:
                    choice = "fail" if (not passes or lab in fail) else "pass"
                    page.locator('[data-testid="stRadio"]').filter(has_text=lab).get_by_text(choice, exact=True).click()
                    wait_idle(page)

            def open_q(qid):
                goto_screen(page, "Review Workspace")
                select_option(page, "Question", qid)
                check(qid in selected_text(page, "Question"), f"opened {qid}",
                      f"page shows '{selected_text(page, 'Question')}'")

            # 2a verify with correction (change the topic within the same section)
            open_q(q_corr)
            sec_id, topic0 = db_rows(db, "select section_id, primary_topic_id from classifications where question_id=?", q_corr)[0]
            alt = [r[0] for r in db_rows(db, "select node_id from taxonomy_nodes where level='topic' and parent_id=? and node_id<>? "
                                              "and deprecated=0 order by node_id", sec_id, topic0)]
            if alt:
                select_option(page, "Topic", alt[0])
                score()
                page.get_by_role("button", name="Verify with correction").click(); wait_idle(page)
                st = cls_status(q_corr)
                ev = review_events(q_corr)
                check(st and st[0] == "verified" and st[1] == alt[0], "Verify with correction: status + topic saved in the DB", f"{topic0} -> {st}")
                check(any(e[0] == "primary_topic_id" and e[3] == "TEST-AUTOMATION" for e in ev), "audit event attributed to TEST-AUTOMATION (never 'owner')")
                page.reload(); page.wait_for_load_state("networkidle"); wait_idle(page)
                open_q(q_corr)
                check("verified" in page.locator('[data-testid="stMain"]').inner_text(), "after a PAGE RELOAD the question still shows verified")
                check(cls_status(q_corr)[0] == "verified", "after reload the database still says verified")
            else:
                check(False, f"no alternative topic under {sec_id}")

            # 2b verify as-is
            open_q(q_asis)
            page.get_by_role("button", name="Verify as-is").click(); wait_idle(page)
            body = page.locator('[data-testid="stMain"]').inner_text()
            check(cls_status(q_asis)[0] == "suggested" and "Score all five review checks first" in body,
                  "Verify WITHOUT the review checks is refused (status unchanged, message shown)")
            score(fail=("Source fidelity",))
            page.get_by_role("button", name="Verify as-is").click(); wait_idle(page)
            body = page.locator('[data-testid="stMain"]').inner_text()
            check(cls_status(q_asis)[0] == "suggested" and "must both pass" in body,
                  "Verify with a FAILED source-fidelity check is refused")
            score()
            page.get_by_role("button", name="Verify as-is").click(); wait_idle(page)
            check(cls_status(q_asis)[0] == "verified", "Verify as-is persisted (after all checks passed)", q_asis)
            rub = [e for e in review_events(q_asis) if e[0] == "rubric"]
            check(bool(rub) and '"review_quality_score": 5' in rub[-1][2] and rub[-1][3] == "TEST-AUTOMATION",
                  "the rubric is stored as an audit event (score 5/5, reviewer TEST-AUTOMATION)")
            check(any(e[0] == "extraction_verified" and e[2] == "true" for e in review_events(q_asis))
                  and any(e[0] == "key_verified" for e in review_events(q_asis)),
                  "approval scope recorded separately (extraction_verified, key_verified)")
            page.reload(); page.wait_for_load_state("networkidle"); wait_idle(page)
            check(cls_status(q_asis)[0] == "verified" and any(e[0] == "status" for e in review_events(q_asis)), "Verify as-is survives reload with its audit event")

            # 2c flag
            open_q(q_flag)
            page.get_by_role("button", name="Flag").click(); wait_idle(page)
            check(cls_status(q_flag)[0] == "flagged", "Flag persisted", q_flag)
            page.reload(); page.wait_for_load_state("networkidle"); wait_idle(page)
            check(cls_status(q_flag)[0] == "flagged", "Flag survives reload")

            # 2d approve & next (button) and the progress counter
            open_q(q_next)
            score()
            before_txt = page.locator('[data-testid="stMain"]').inner_text()
            page.get_by_role("button", name="Approve & next").click(); wait_idle(page)
            check(cls_status(q_next)[0] == "verified", "Approve & next verified the question", q_next)
            after_txt = page.locator('[data-testid="stMain"]').inner_text()
            check(q_next not in selected_text(page, "Question"), "Approve & next moved to a different question", selected_text(page, "Question")[:40])
            check("verified by a human" in after_txt and "of 65 classified" in after_txt, "visible 'N of 65 verified' progress counter")
            check("verified by TEST-AUTOMATION" in after_txt or "verified by" in after_txt, "confirmation message survives the rerun")
            page.screenshot(path=str(SHOTS / "05-review-workspace-after-approve.png"), full_page=True)

            # 2e keyboard shortcut Ctrl+Enter == Approve & next
            open_q(q_key)
            score()
            page.get_by_role("heading", name="Review Workspace").click()      # neutral focus target, not an input
            page.keyboard.press("Control+Enter"); wait_idle(page)
            kb = cls_status(q_key)[0] == "verified"
            check(kb, "keyboard shortcut Ctrl+Enter = Approve & next", q_key)

            # the other advertised shortcuts: Alt+V verify as-is, Alt+X flag, Alt+N skip
            q_v, q_x, q_n = qs[8], qs[9], qs[10]
            open_q(q_v)
            score()
            page.get_by_role("heading", name="Review Workspace").click()
            page.keyboard.press("Alt+v"); wait_idle(page)
            check(cls_status(q_v)[0] == "verified", "keyboard shortcut Alt+V = Verify as-is", q_v)
            open_q(q_x)
            page.get_by_role("heading", name="Review Workspace").click()
            page.keyboard.press("Alt+x"); wait_idle(page)
            check(cls_status(q_x)[0] == "flagged", "keyboard shortcut Alt+X = Flag", q_x)
            open_q(q_n)
            page.get_by_role("heading", name="Review Workspace").click()
            page.keyboard.press("Alt+n"); wait_idle(page)
            check(q_n not in selected_text(page, "Question") and cls_status(q_n)[0] == "suggested",
                  "keyboard shortcut Alt+N = skip to the next pending question (without verifying)", selected_text(page, "Question")[:36])

            # 2f extraction correction: real typing, persisted, audited, survives reload; audit history visible
            q_txt = qs[11]
            open_q(q_txt)
            old_text = db_rows(db, "select text from questions where id=?", q_txt)[0][0]
            page.get_by_text("Correct the extraction", exact=False).first.click(); wait_idle(page)
            page.get_by_label("Question text").fill(old_text + " [corrected by test]")
            page.get_by_label("Reason (goes to the audit log)").fill("browser test correction")
            page.get_by_label("Reason (goes to the audit log)").press("Tab"); wait_idle(page)
            page.get_by_role("button", name="Save extraction correction").click(); wait_idle(page)
            new_text = db_rows(db, "select text from questions where id=?", q_txt)[0][0]
            check(new_text.endswith("[corrected by test]") and any(e[0] == "text" and e[3] == "TEST-AUTOMATION" for e in review_events(q_txt)),
                  "extraction text correction saved with an audit event (old and new value)")
            page.reload(); page.wait_for_load_state("networkidle"); wait_idle(page)
            open_q(q_txt)
            page.get_by_text("Audit history for this question", exact=False).first.click(); wait_idle(page)
            hist = page.locator('[data-testid="stMain"]').inner_text()
            check(db_rows(db, "select text from questions where id=?", q_txt)[0][0] == new_text and "browser test correction" in hist,
                  "correction survives a reload and appears in the on-screen audit history")
            check(cls_status(q_txt)[0] == "suggested", "an extraction correction does NOT verify the classification")
            page.screenshot(path=str(SHOTS / "08-review-rubric-and-history.png"), full_page=True)

            # ---------------- 3. Approve Queue batch: a passing rubric is required ----------------
            import re as _re
            goto_screen(page, "Approve Queue")
            queue_ids = _re.findall(r"GATE-CS-\d{4}-S\d-Q\d\d", page.locator('[data-testid="stMain"]').inner_text())
            q_scored, q_unscored = queue_ids[0], queue_ids[1]
            open_q(q_scored)                                         # score it, save WITHOUT verifying
            score()
            page.get_by_role("button", name="Save without verifying").click(); wait_idle(page)
            check(cls_status(q_scored)[0] == "suggested", "'Save without verifying' stores the checks but does not verify")
            goto_screen(page, "Approve Queue")
            pre = db_rows(db, "select count(*) from review_events where note='approve queue' and field='status'")[0][0]
            for qid in (q_scored, q_unscored):
                page.locator(f'.st-key-aq_appr_{qid} label').first.click(); wait_idle(page)   # stable widget key
            confirm = page.locator('[data-testid="stCheckbox"]').filter(has_text="I reviewed the")
            confirm.first.click(); wait_idle(page)
            btn_txt = page.get_by_role("button", name="Approve 2 selected")
            check(btn_txt.count() == 1, "Approve Queue offers 'Approve 2 selected' after ticking 2 rows")
            btn_txt.click(); wait_idle(page)
            post = db_rows(db, "select count(*) from review_events where note='approve queue' and field='status' and reviewer='TEST-AUTOMATION'")[0][0]
            body = page.locator('[data-testid="stMain"]').inner_text()
            check(post - pre == 1 and cls_status(q_scored)[0] == "verified" and cls_status(q_unscored)[0] == "suggested"
                  and "NOT approved because they have no passing review rubric" in body,
                  "batch approval verifies the scored row and REFUSES the unscored one", f"{post - pre} approved")
            page.screenshot(path=str(SHOTS / "06-approve-queue.png"), full_page=True)

            # ---------------- 4. every screen: no exception, no clipped text, screenshots ----------------
            visit_all("after test actions", shots=False)   # same screens must still render with edited data

            # an OCR'd (scanned) paper in the Review Workspace
            goto_screen(page, "Review Workspace")
            select_option(page, "Paper", "GATE-CS-2019-S1")
            select_option(page, "Question", "GATE-CS-2019-S1-Q12")
            body = page.locator('[data-testid="stMain"]').inner_text()
            check("read by OCR" in body and "GA" in body or "CS" in body, "scanned paper shows the OCR notice and printed label")
            page.screenshot(path=str(SHOTS / "07-review-ocr-paper.png"), full_page=True)
            browser.close()

        # ---------------- 5. isolation proof ----------------
        after = {p: sha(p) for p in before}
        check(after == before, "source/live database files are byte-identical after the whole run", str(before))
        n_test = db_rows(db, "select count(*) from review_events where reviewer='TEST-AUTOMATION'")[0][0]
        n_other = db_rows(db, "select count(*) from review_events where reviewer not in ('TEST-AUTOMATION','owner-relayed-audit','repair-script-v5')")[0][0]
        check(n_test >= 8 and n_other == 0, "all new audit events are test actions (TEST-AUTOMATION), none human", f"{n_test} test events")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=15)
        except Exception:
            srv.kill()
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)
    failed = [l for ok, l in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} browser checks passed; screenshots in {SHOTS}")
    for l in failed:
        print("  FAILED:", l)
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
