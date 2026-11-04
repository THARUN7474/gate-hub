"""Real-browser screenshots of the v6 app (Playwright + headless Chromium).
Starts `streamlit run app.py` on a scratch copy of the DB, visits each screen,
clicks a matrix cell link (clickable navigation), and saves PNGs to
docs/screenshots/v6/. Usage: python scripts/ui_screenshots.py
"""
from __future__ import annotations
import os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "screenshots" / "v6"
OUT.mkdir(parents=True, exist_ok=True)

tmp = Path(tempfile.mkdtemp(prefix="gate-shots-"))
db = tmp / "shots.db"
shutil.copy(ROOT / "data" / "gate_cse.sqlite", db)

port = 8799
env = dict(os.environ, GATE_DB_URL=f"sqlite:///{db}")
proc = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
     "--server.port", str(port), "--server.headless", "true"],
    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wait_ready(timeout=60):
    import urllib.request
    for _ in range(timeout * 2):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False

def main():
    from playwright.sync_api import sync_playwright
    assert wait_ready(), "streamlit did not start"
    base = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.goto(base, wait_until="networkidle")
        page.wait_for_timeout(3000)

        def go_screen(name):
            page.get_by_test_id("stSidebar").get_by_text(name, exact=True).click()
            page.wait_for_timeout(2500)

        # LLM Classify screen
        go_screen("LLM Classify")
        page.screenshot(path=str(OUT / "v6-llm-classify.png"), full_page=True)

        # Approve Queue
        go_screen("Approve Queue")
        page.screenshot(path=str(OUT / "v6-approve-queue.png"), full_page=True)

        # Analysis Matrix: clickable cells
        go_screen("Analysis Matrix")
        page.screenshot(path=str(OUT / "v6-matrix-clickable.png"), full_page=True)
        # click a real cell link -> drill view
        link = page.locator('a[href*="drill_sec="]').first
        assert link.count() > 0, "no clickable matrix cell found"
        link.click()
        page.wait_for_timeout(2500)
        page.screenshot(path=str(OUT / "v6-matrix-drilldown.png"), full_page=True)
        # click a question link -> Review Workspace
        qlink = page.locator('a[href*="review_q="]').first
        assert qlink.count() > 0, "no review link in drill view"
        qlink.click()
        page.wait_for_timeout(3500)
        page.screenshot(path=str(OUT / "v6-review-from-link.png"), full_page=True)
        assert page.get_by_text("Verify as-is").count() > 0
        browser.close()
    print("screenshots saved to", OUT)
    for f in sorted(OUT.iterdir()):
        print(" ", f.name, f.stat().st_size)

try:
    main()
finally:
    proc.terminate()
