"""GATE CSE Intelligence - Phase 1 local app.
Run: streamlit run app.py   (DB from GATE_DB_URL / .env; see docs/06_SETUP.md)

Screens: Pipeline Status (stage cards), Question Browser, Analysis Matrix (clickable cells),
Topic Report, Review Workspace (original PDF crop beside the label and second opinions,
one-click Verify / Flag / correct-from-dropdown / Approve & next), Second Opinions, Approve
Queue (batch human approval), LLM Classify (provider setup, dry run, gated
real runs), Glossary & Syllabus.
Every number is computed live from the database. Historical description only."""
from __future__ import annotations
import json
import os
import pandas as pd
import streamlit as st
from sqlalchemy import func, select

from pathlib import Path

from src import settings
from src.analytics import analyze as az, links as nav, opinions as op, search as srch
from src.classification import classify as cl
from src.taxonomy import glossary as glos
from src.db.models import (AnswerKey, Classification, Document, Option, Paper,
                           Question, ReviewEvent, TaxonomyNode)
from src.db.session import make_session
from src.extraction import render as rnd
from src.validation import review as rv

settings.load_env()
APP_ROOT = Path(__file__).resolve().parent

def source_previews(session, qu) -> tuple[list[dict] | None, str | None]:
    """Render the question's stored PDF region(s) on demand.
    Returns (segments, None) on success - one {page, png} per segment - or
    (None, reason) with an honest reason when no preview can be shown."""
    regions = json.loads(qu.regions_json) if qu.regions_json else []
    if not regions:
        return None, "no region is stored for this question"
    paper = session.get(Paper, qu.paper_id)
    doc = session.get(Document, paper.document_id) if paper and paper.document_id else None
    if doc is None:
        return None, "no source document is registered for this paper"
    from src.ingestion.paths import resolve_document_path
    path = resolve_document_path(doc)     # survives renamed/moved raw files via sha256
    if path is None:
        return None, (f"the source PDF ({doc.filename}) is not available locally - the region IS "
                      "stored; place the original PDF anywhere under data/raw/ and the preview "
                      "renders on demand")
    return rnd.render_question_regions(path, regions), None

FIXTURE_BANNER = ("SYNTHETIC FIXTURE DATA - NOT REAL GATE DATA. This database contains "
                  "generated test content (scripts/make_fixture.py). Nothing shown is a real "
                  "GATE question, key or statistic.")

st.set_page_config(page_title="GATE CSE Intelligence", page_icon=":material/school:", layout="wide")

# One line per screen: what it is for (shown under the page title) + its sidebar icon.
PAGE_INFO = {
    "Pipeline Status": (":material/dashboard:", "Where the whole project stands, and the next thing to do at each stage."),
    "About the Data": (":material/folder_open:", "Which GATE CS papers exist 2007-2026, which PDF holds which session, where each key comes from."),
    "Question Browser": (":material/search:", "Find any question by subject, topic, year, type or text, and open it."),
    "Analysis Matrix": (":material/grid_on:", "Marks per subject per year - click any number to see the questions behind it."),
    "Topic Report": (":material/leaderboard:", "Which topics carried the most marks historically (descriptive, not a prediction)."),
    "Subject Overview": (":material/account_tree:", "One subject at a time: its topics, concepts, question counts and prerequisites."),
    "Review Workspace": (":material/rate_review:", "Check one question against its original PDF, then verify, correct or flag its label."),
    "Second Opinions": (":material/forum:", "Everything the AI reviewer and decision models said, beside the current label."),
    "Approve Queue": (":material/playlist_add_check:", "Bulk-approve questions you already checked in the Review Workspace."),
    "LLM Classify": (":material/smart_toy:", "Machines that propose labels: FreeLLMAPI runs, comparisons and decision models."),
    "Glossary & Syllabus": (":material/menu_book:", "What every code means, with the official syllabus text and where it comes from."),
}

# "What this page gives you": functional use first, then how it works underneath.
PAGE_GUIDE = {
    "Pipeline Status": (
        ["See every stage at a glance: extraction, machine labels, AI review, decision models, benchmark, human review.",
         "Each stage card says what to do next and has a button that opens the right page with filters already set.",
         "Per-paper tables show where review is done and where extraction issues remain."],
        ["All numbers are counted live from the database on every load.",
         "'Verified' only ever means a human approved it in the Review Workspace."]),
    "About the Data": (
        ["Which years and sessions exist, which PDF holds them, and which papers have an official key.",
         "How many of those questions this database holds."],
        ["Built from manifests/papers.yaml, the files in data/raw and the database."]),
    "Question Browser": (
        ["Filter by subject, topic, year, type, label status or extraction issue - or search the text.",
         "See how many questions match and how they split by subject and status.",
         "Click any row to open that question in the Review Workspace."],
        ["Dropdowns show full names; the code (e.g. ALGO.SORT) is what is filtered on underneath.",
         "No row cap: every matching question is listed."]),
    "Analysis Matrix": (
        ["Marks per subject per year, with row totals, column totals and a grand total.",
         "Click any number to list the exact questions behind it; click one to review it.",
         "Below: the same view per topic inside one subject."],
        ["Primary topic only, so every question's marks are counted once.",
         "Counts are machine suggestions until verified - tick 'Count verified only' to see human-checked marks."]),
    "Topic Report": (
        ["Topics ranked by historical marks share, recent years weighted higher.",
         "Pick a topic to list every question classified under it."],
        ["Descriptive history, not a prediction for 2027."]),
    "Subject Overview": (
        ["One subject: its topics with question counts, concepts, and curated prerequisites."],
        ["Topics/concepts come from taxonomy.yaml; prerequisites are curated, not official."]),
    "Review Workspace": (
        ["The original PDF crop (the truth) beside what the computer read and every opinion on the label.",
         "Filter to extraction issues, items awaiting you, AI-reviewed items or the 120-question benchmark.",
         "Correct text/options, correct the topic, answer five checks, then Verify - your decision is what counts."],
        ["Every change is an audit event with your name, the old and the new value.",
         "Verifying a benchmark question records it as gold; nothing is ever auto-approved."]),
    "Second Opinions": (
        ["Every question the AI reviewer looked at: its verdict (agree / flag / correct), its topic and its note.",
         "Decision-model answers (when run) with their probability.",
         "Click a row to open the question and decide yourself."],
        ["Opinions are stored apart from the live label and are never verification or gold."]),
    "Approve Queue": (
        ["Approve many questions in one go - but only ones you already checked (saved review checks)."],
        ["The usual flow: review in the Review Workspace with 'Save without verifying', then approve here in bulk."]),
    "LLM Classify": (
        ["Check which label providers are ready, estimate cost, preview payloads, and run or compare classification.",
         "Decision models (paid, off by default) for a calibrated second opinion."],
        ["You do not need this page to review questions. Every run is gated by consent settings in .env."]),
    "Glossary & Syllabus": (
        ["What every label status means (suggested, flagged, verified, unclassified) and related terms.",
         "Every section, topic and concept code with its full name and the verbatim 2027 syllabus text.",
         "Where the syllabus files live on disk and their checksums."],
        ["Sections are official text; topics/concepts are our curated split; LEGACY is historical (pre-2016)."]),
}

def page_header(name: str) -> None:
    icon, purpose = PAGE_INFO.get(name, ("", ""))
    st.header(f"{icon} {name}" if icon else name)
    st.caption(purpose)
    if name in PAGE_GUIDE:
        use, how = PAGE_GUIDE[name]
        with st.expander("What this page gives you", icon=":material/lightbulb:"):
            st.markdown("**What you can do here**\n" + "\n".join(f"- {u}" for u in use)
                        + "\n\n**How it works**\n" + "\n".join(f"- {h}" for h in how))

def how_to_read(label: str = "How to read this page"):
    """Long explanations live here, collapsed, so each page opens on its main content."""
    return st.expander(label, icon=":material/help:")

# ---- label statuses: one definition, used by every dropdown and every "What the statuses mean" toggle ----
STATUS_SHORT = {
    "(all)": "(all)",
    "suggested": "suggested (machine guess, not checked yet)",
    "flagged": "flagged (doubtful - look at these first)",
    "verified": "verified (you checked and approved it)",
    "unclassified": "unclassified (no label at all)",
    "has an issue": "has an issue (text/options may be misread from the PDF)",
    "clean": "clean (no extraction problem found)",
}

def status_label(x) -> str:
    return STATUS_SHORT.get(x, str(x))

def status_guide_md(session) -> str:
    """The full explanation of every status and related term, with live counts."""
    _c = dict(session.execute(select(Classification.status, func.count()).group_by(Classification.status)).all())
    _tot = session.scalar(select(func.count()).select_from(Question)) or 0
    _sug, _fl, _ver = _c.get("suggested", 0), _c.get("flagged", 0), _c.get("verified", 0)
    _lab = _sug + _fl + _ver
    _ext = session.scalar(select(func.count()).select_from(Question).where(Question.needs_review == True)) or 0  # noqa: E712
    return (
        "The **label status** says how far a question's topic label has got: a machine guess, a guess marked "
        "doubtful, or checked by you.\n\n"
        "| Status | What it means | Who sets it | Count now |\n|---|---|---|---|\n"
        f"| **suggested** | A machine model proposed a subject and topic and was reasonably confident. It is a "
        f"**guess** you have not checked yet. | The classifier model | {_sug:,} |\n"
        f"| **flagged** | It has a label too, but something marked it as **doubtful**: low model confidence, an AI "
        f"reviewer raising a concern, or you pressing **Flag**. Look at these first. | Classifier, AI review, or you | {_fl:,} |\n"
        f"| **verified** | **You checked it and approved it** in the Review Workspace (the five checks passed, then "
        f"Verify). The only status that means \"true\". | Only a human | {_ver:,} |\n"
        f"| **unclassified** | The question has **no label at all**. | - | {_tot - _lab:,} |\n\n"
        "**Related words used around the app**\n"
        f"- **Classified / labelled** = has any label (suggested + flagged + verified): {_lab:,} of {_tot:,}.\n"
        f"- **Awaiting your decision** = suggested + flagged ({_sug + _fl:,}): every label you have not approved yet.\n"
        f"- **Extraction issue** ({_ext:,}) is separate: it is about whether the question text and options were read "
        "correctly from the PDF, not about the topic label. That is why it has its own **Extraction** filter.\n"
        "- **AI review** (agree / flag / correct) and **decision models** are opinions stored beside the label. They "
        "never turn a label into verified.\n"
        "- **Benchmark gold** = a verified label on one of the 120 sampled questions; it is what accuracy is measured "
        "against.\n\n"
        "**How a question moves:** unclassified -> suggested or flagged (a machine labels it) -> **verified** (you "
        "approve it). If you correct the topic before verifying, your corrected topic is what gets verified."
    )

def status_guide(session, label: str = "What the statuses mean") -> None:
    with st.expander(label, icon=":material/info:"):
        st.markdown(status_guide_md(session))

def goto(screen: str, **state):
    """Button callback: open another screen with its filters preset (applied before widgets exist)."""
    def _cb():
        for k, v in state.items():
            st.session_state[k] = v
        st.session_state["_pending_screen"] = screen
    return _cb

def named(code, names: dict) -> str:
    """Dropdown label: full name first, code after it. The code stays the value used for filtering."""
    if code in (None, "", "(all)", "-"):
        return code or ""
    n = names.get(code)
    return f"{n}  ({code})" if n else str(code)

# Streamlit re-executes this script on every interaction. Close the PREVIOUS run's session first:
# on PostgreSQL an unclosed session stays 'idle in transaction' and holds locks (it also made the
# test-suite TRUNCATE hang). One cached engine is shared, so reruns don't open new connection pools.
@st.cache_resource
def _engine():
    from src.db.session import make_engine
    return make_engine()

_prev_session = st.session_state.pop("_db_session", None)
if _prev_session is not None:
    try:
        _prev_session.close()
    except Exception:  # noqa: BLE001 - a dead connection must never block the page
        pass
from sqlalchemy.orm import sessionmaker as _sessionmaker

def render_data_inventory(session):
    """About the Data: papers 2007-2026, PDFs, sessions, keys, what this database holds (read-only)."""
    from src.analytics import inventory as _inv
    page_header("About the Data")
    with how_to_read():
        st.caption("Computed live from manifests/papers.yaml, the files in data/raw and this database. A 'paper' = one exam "
                   "session (65 questions, 100 marks). One PDF can hold several sessions.")
    inv = _inv.inventory(session)
    T = inv["totals"]
    with st.container(horizontal=True):
        st.metric("Years 2007-2026", T["years"], border=True)
        st.metric("Papers registered", T["papers"], help="including the 4 deferred 2007-2010 papers", border=True)
        st.metric("Active papers 2011-2026", T["active_papers"], help=f"{T['deferred_papers']} deferred (2007-2010)", border=True)
        st.metric("Question / key PDFs", f"{T['question_pdfs']} / {T['key_pdfs']}", border=True)
        st.metric("Papers with an official key", f"{T['active_with_key']} of {T['active_papers']}",
                  help=f"{T['active_without_key']} have no key file (listed as missing, never guessed)", border=True)
    _in_db = T["questions_in_db"]
    (st.success if _in_db >= T["expected_questions_active"] else st.warning)(
        f"This database holds {_in_db:,} of the {T['expected_questions_active']:,} questions of the {T['active_papers']} active papers"
        + ("." if _in_db >= T["expected_questions_active"] else
           " - the rest are prepared and come in with the promotion (promote.cmd)."))
    st.subheader("Three groups of years")
    st.dataframe(pd.DataFrame(inv["groups"]), hide_index=True, width="stretch")
    st.subheader("Year by year")
    st.caption("How many papers each year has, in which PDF(s), and where the key comes from.")
    st.dataframe(pd.DataFrame(inv["years"]), hide_index=True, width="stretch")
    with st.expander("Every paper (session): PDF pages, key source, layout, what this database holds"):
        _cols = ["paper_id", "status", "question_pdf", "pages", "papers_in_this_pdf", "key_source", "layout",
                 "read_by_ocr", "in_db_questions", "in_db_keys", "in_db_ocr_questions", "classified", "verified"]
        st.dataframe(pd.DataFrame(inv["papers"])[_cols], hide_index=True, width="stretch")
    with st.expander("What the layout names mean"):
        st.markdown(
            "- **cs-first-continuous** (2011-2013): CS questions Q1-55 first, General Aptitude Q56-65 last.\n"
            "- **ga-first-restart** (2014, 2016, 2018-2021): General Aptitude block first, then a CS block whose printed numbering "
            "restarts at 1 (stored as Q11-65; the printed label is kept).\n"
            "- **platform-export** (2015): an online test-platform printout ('Question Number : N', ticks on options - ticks are "
            "**not** used as a key).\n"
            "- **qnum-export** (2017): a similar export with marks printed per question.\n"
            "- **continuous-modern** (2022-2026): GA Q1-10 then CS Q11-65, continuous numbering.\n\n"
            "Scanned years are read with OCR (2014, 2015, 2020 always; others where the text layer is unusable) - the review "
            "screen always shows the original image. Details: docs/15_DATA_ONBOARDING.md and docs/21_DATA_INVENTORY.md.")

# A database created by an older version lacks newer columns (e.g. questions.printed_label). Never crash and
# never alter it silently: say exactly what is missing and offer a backed-up, additive upgrade.
try:
    from src.db import dev_upgrade as _du
    _missing = _du.missing_schema()
except Exception as _e:  # noqa: BLE001 - unreachable DB: show the real reason instead of a stack trace
    st.error(f"Cannot open the database: {_e}")
    st.info("Check GATE_DB_URL in .env. For PostgreSQL start Docker Desktop and run `docker compose up -d`; "
            "for SQLite delete the GATE_DB_URL line to use data/gate_cse.sqlite. `python -m src.cli doctor` explains more.")
    st.stop()
if _missing:
    st.warning("This database was created by an older version and needs a one-time, **additive** schema upgrade "
               "(new empty columns/tables only - no data is changed or removed): " + ", ".join(_missing[:8]))
    if _engine().dialect.name == "sqlite":
        if st.button("Back up the database, then upgrade it"):
            from src import backup as _bk
            _res = _bk.backup()
            _du.upgrade_schema()
            st.success(f"Backed up to {_res['file']} and upgraded. Reload the page.")
    else:
        st.code("alembic upgrade head")
    st.markdown("---")
    st.caption("Read-only preview while you decide (nothing below changes the database):")
    render_data_inventory(_sessionmaker(bind=_engine())())
    st.stop()
session = _sessionmaker(bind=_engine(), expire_on_commit=False)()
st.session_state["_db_session"] = session

GLOSSARY = glos.build_glossary(str(APP_ROOT / "taxonomy.yaml"))

def code_explainer(codes, label="What these codes mean"):
    """Hover tooltips (desktop) plus a tappable expander (mobile) expanding
    every short code on screen. Content comes from taxonomy.yaml via the
    Glossary & Syllabus screen, so both stay in sync."""
    codes = list(dict.fromkeys(c for c in codes if c))
    if not codes:
        return
    st.markdown(glos.hover_legend_html(GLOSSARY, codes), unsafe_allow_html=True)
    with st.expander(label + " - tap for the full table"):
        for row in glos.describe_codes(GLOSSARY, codes):
            st.markdown(f"**{row['Code']}** = {row['Meaning']}  \n"
                        f"<span style='color:#777; font-size:0.85em'>{row['Provenance']}</span>",
                        unsafe_allow_html=True)

def taxonomy_maps(session):
    """sections, {section: [topics]}, {topic: [concepts]}, name lookup."""
    nodes = session.scalars(select(TaxonomyNode).where(
        TaxonomyNode.deprecated == False)).all()  # noqa: E712
    sections = [n.node_id for n in nodes if n.level == "section"]
    topics_by_sec: dict[str, list[str]] = {s: [] for s in sections}
    concepts_by_topic: dict[str, list[str]] = {}
    names = {n.node_id: n.name for n in nodes}
    for n in nodes:
        if n.level == "topic" and n.parent_id in topics_by_sec:
            topics_by_sec[n.parent_id].append(n.node_id)
        if n.level == "concept":
            concepts_by_topic.setdefault(n.parent_id, []).append(n.node_id)
    return sections, topics_by_sec, concepts_by_topic, names

# ---- deep links (v6): ?review_q=<id> and ?drill_sec=<sec>&drill_year=<yr> ---
_qp_review = st.query_params.get("review_q")
if _qp_review:
    st.session_state["review_pick"] = _qp_review
    st.session_state["_pending_screen"] = "Review Workspace"
    st.query_params.clear()
_drill_sec, _drill_year = nav.parse_drill_params(st.query_params)
_drill_is_topic = bool(st.query_params.get("drill_topic"))
if _drill_sec:
    st.session_state["_pending_screen"] = "Analysis Matrix"
    st.query_params.clear()
    st.session_state["drill"] = (_drill_sec, _drill_year)
    st.session_state["drill_kind"] = "topic" if _drill_is_topic else "section"

# Screen-jump requests are queued by callbacks (widget state may only change
# before the radio is instantiated) and applied here, at the top of the run.
_pending = st.session_state.pop("_pending_screen", None)
if _pending:
    st.session_state["screen"] = _pending

if rv.has_fixture_data(session):
    st.error(FIXTURE_BANNER)
SCREENS = ["Pipeline Status", "About the Data", "Question Browser", "Analysis Matrix", "Topic Report",
           "Subject Overview", "Review Workspace", "Second Opinions", "Approve Queue", "LLM Classify",
           "Glossary & Syllabus"]
st.sidebar.markdown("### :material/school: GATE CSE Intelligence")
st.sidebar.caption("Local, phase 1. Every figure is computed live from the question records - historical "
                   "description only, not a prediction for GATE 2027.")
page = st.sidebar.radio("Screen", SCREENS, key="screen",
                        format_func=lambda x: f"{PAGE_INFO[x][0]} {x}" if x in PAGE_INFO else x)
# Every human decision is written to the audit log under this name (default: GATE_REVIEWER or "owner").
REVIEWER = st.sidebar.text_input("Reviewer name (audit log)", value=os.environ.get("GATE_REVIEWER", "owner"),
                                 key="reviewer_name").strip() or "owner"
st.sidebar.caption("Keyboard in the Review Workspace: **Ctrl+Enter** approve & next, **Alt+N** skip, "
                   "**Alt+V** verify as-is, **Alt+X** flag.")

if page == "Pipeline Status":
    page_header("Pipeline Status")
    cov = az.coverage_report(session)
    S = op.stage_summary(session)
    with st.container(horizontal=True):
        for label, val, hlp in [("Papers", cov["papers"], "exam sessions loaded (65 questions / 100 marks each)"),
                                ("Questions", cov["questions"], "all loaded questions"),
                                ("With official keys", cov["with_keys"], "questions with an official answer key"),
                                ("Labelled", cov["classified"], "questions with a topic label (machine suggestion or verified)"),
                                ("Human-verified", cov["verified_by_human"], "approved by a human after the five review checks"),
                                ("Waiting for a human", cov["pending_review"], "every question without a human-verified label")]:
            st.metric(label, f"{val:,}", help=hlp, border=True)

    st.subheader("Stages", help="Left to right is the order work flows in. Each card: how far it got, what to do, "
                                "and a button that opens the right page with the filters already set.")
    _nq = S["questions"] or 1
    _v = S["ai_verdicts"]
    _bt = S["benchmark_total"] or 120
    STAGES = [
        ("1 · Read from the PDFs", ":material/description:",
         (S["questions"] - S["extraction_issues"]) / _nq,
         f"{S['questions'] - S['extraction_issues']:,} clean · **{S['extraction_issues']} need a check**",
         "The extractor could not read some questions cleanly (options that are only a figure, OCR noise, a "
         "type mismatch with the key). Open each, compare with the PDF image, fix the text or confirm it.",
         "Fix extraction issues", "Review Workspace",
         {"rw_paper": "(all papers)", "rw_show": "extraction issues", "rw_order": "paper order"}),
        ("2 · Machine label", ":material/label:", S["classified"] / _nq,
         f"{S['classified']:,} of {S['questions']:,} have a suggested topic",
         "Done. These are machine guesses - they become true only when you verify them. Browse them by "
         "subject or topic if you want to look around.",
         "Browse questions", "Question Browser", {}),
        ("3 · AI review (second opinion)", ":material/forum:", S["ai_reviewed"] / _nq,
         f"{S['ai_reviewed']} reviewed · {_v.get('agree', 0)} agree · **{_v.get('flag', 0)} flag · "
         f"{_v.get('correct', 0)} correct**",
         "Claude's opinion on 2026 CS-2, the benchmark and the 18 SE questions. Not verification. "
         "Read the 'flag' and 'correct' ones first - that is where it disagreed.",
         "See AI opinions", "Second Opinions", {}),
        ("4 · Decision models", ":material/psychology:", S["decision_questions"] / _bt,
         f"{S['decision_questions']} questions answered" if S["decision_questions"] else "Not run yet (paid, off)",
         "Optional. A paid, calibrated second opinion (Jev / OpenAI Decisions). Run it on the benchmark "
         "only after you have verified the benchmark, so it can be scored.",
         "Open decision models", "LLM Classify", {}),
        ("5 · Your benchmark (gold)", ":material/workspace_premium:", S["benchmark_gold"] / _bt,
         f"**{S['benchmark_gold']} of {S['benchmark_total']}** verified by you",
         "Start here. 120 sampled questions; verifying them measures how accurate the machine labels are. "
         "About 2-4 hours in total, 50 already give a first figure.",
         "Review the benchmark", "Review Workspace",
         {"rw_paper": "(all papers)", "rw_show": "benchmark sample (gold review)", "rw_order": "paper order"}),
        ("6 · Human-verified", ":material/verified:", S["verified"] / _nq,
         f"**{S['verified']:,} of {S['questions']:,}** verified",
         "Your approval is the only thing that makes a label true. After the benchmark, work through the rest "
         "in priority order (most likely wrong first).",
         "Review next in priority", "Review Workspace",
         {"rw_paper": "(all papers)", "rw_show": "awaiting my decision", "rw_order": "review priority first"}),
    ]
    for _row in (STAGES[:3], STAGES[3:]):
        for _col, (_t, _ic, _frac, _num, _todo, _btn, _scr, _state) in zip(st.columns(3), _row):
            with _col.container(border=True, height="stretch"):
                st.markdown(f"#### {_ic} {_t}")
                st.progress(min(max(_frac, 0.0), 1.0))
                st.markdown(_num)
                st.caption("**What to do:** " + _todo)
                st.button(_btn, key=f"stage_{_t}", icon=":material/arrow_forward:", width="stretch",
                          on_click=goto(_scr, **_state))

    _rev = az.paper_review_table(session)
    ptab = az.paper_status_table(session)
    n_ocr = sum(1 for r in ptab if r["text_source"] != "digital")
    nokey = [r["paper"].replace("GATE-CS-", "") for r in ptab if r["official_keys"] == 0]
    st.subheader("Per paper")
    _tab_rev, _tab_pap = st.tabs(["Review progress", "Paper details"])
    with _tab_rev:
        st.dataframe(
            pd.DataFrame(_rev), width="stretch", hide_index=True,
            column_config={
                "paper": st.column_config.TextColumn("paper", pinned=True),
                "verified_share": st.column_config.ProgressColumn("verified", format="percent", min_value=0, max_value=1,
                                                                  help="share of the paper's questions a human verified"),
                "verified": st.column_config.NumberColumn("verified (n)"),
                "ai_reviewed": st.column_config.NumberColumn("AI-reviewed", help="has an AI-review opinion (not verification)"),
                "extraction_issues": st.column_config.NumberColumn("extraction issues", help="questions the extractor flagged for a check"),
                "benchmark_pending": st.column_config.NumberColumn("benchmark to do"),
                "benchmark_gold": st.column_config.NumberColumn("benchmark gold"),
            })
    with _tab_pap:
        _pcols = ["paper", "year", "session", "questions", "marks", "reconciled", "official_keys", "text_source",
                  "needs_review", "classified", "verified", "set"]
        st.dataframe(pd.DataFrame(ptab)[_pcols], width="stretch", hide_index=True,
                     column_config={"needs_review": st.column_config.NumberColumn("extraction issues")})
        st.caption(f"**text_source**: 'digital' = exact PDF text; 'OCR' = read from scanned pages ({n_ocr} papers; "
                   f"the PDF image in the Review Workspace is always the truth). **official_keys**: {len(nokey)} papers "
                   f"have no key ({', '.join(nokey) or 'none'}) - listed as missing, never guessed. 2007-2010 are deferred.")

    status_guide(session)
    with how_to_read("How these numbers are counted"):
        st.markdown(f"- **Waiting for a human** = every question without a human-verified label "
                    f"({cov['pending_review']:,}). Of those, {cov['of_which_extraction_issues']} also have an "
                    f"extraction issue and {cov['of_which_unclassified']} have no label at all.\n"
                    f"- **Extraction issue** = the extractor itself flagged the question (e.g. options that are only a "
                    f"figure, an option count that does not fit the type, OCR text, a question the key marks as dropped). "
                    f"It clears when you correct or confirm the extraction in the Review Workspace.\n"
                    f"- **AI review** and **decision models** are opinions stored apart from the label. They never "
                    f"count as verified.\n- {cov['note']}")
    from src.db.models import Classification as _Cls
    _pairs = session.execute(select(_Cls.model, _Cls.status).where(_Cls.status != "verified")).all()
    _agg = {}
    for _m, _st in _pairs:
        _d = _agg.setdefault(_m or "unknown", {"suggested": 0, "flagged": 0})
        _d[_st if _st in ("suggested", "flagged") else "suggested"] += 1
    if _agg:
        with st.expander("Where the unverified labels came from", icon=":material/source:"):
            st.dataframe(pd.DataFrame([{"model / source": m, **d} for m, d in sorted(_agg.items())]),
                         hide_index=True, width="stretch")
            st.caption("All machine suggestions - none is verified until a human approves it.")
    from src.classification.classify import proposal_agreement as _pagree
    _prow = _pagree(session)
    if _prow:
        with st.expander("Second-opinion agreement (AI review and API proposals)", icon=":material/compare_arrows:"):
            st.caption("How often each stored second opinion picks the same topic as the live label. These never "
                       "overwrite the label.")
            st.dataframe(pd.DataFrame(_prow), width="stretch", hide_index=True)
    _legacy = list(session.scalars(select(Classification.question_id).where(Classification.section_id == "LEGACY")))
    if _legacy:
        with st.expander(f"Out of the 2027 syllabus: {len(_legacy)} historical software-engineering questions",
                         icon=":material/history_edu:"):
            st.caption("Software engineering was in the GATE CS syllabus until about 2015 and is not in the 2027 "
                       "syllabus. These 2011-2015 questions are counted under 'Out of 2027 syllabus' (LEGACY.SE) so "
                       "every question is accounted for - they are not 2027 preparation topics.")
            for _g in _legacy:
                _gq = session.get(Question, _g)
                st.markdown(f"- **{_g}** - {(_gq.text or '')[:110]}..." if _gq else f"- {_g}")
    if cov["unreconciled_papers"]:
        st.warning("Unreconciled papers: " + ", ".join(cov["unreconciled_papers"]))
    with st.expander("Back up the database", icon=":material/backup:"):
        st.write("Writes a verified, timestamped copy to `backups/` (safe while the app is open; the live "
                 "database is only read).")
        if st.button("Back up now", key="backup_now"):
            try:
                from src import backup as _bk
                res = _bk.backup()
                st.success(f"Backup written: {res['file']}")
                st.json({k: v for k, v in res.items() if k != "file"})
            except Exception as e:  # noqa: BLE001
                st.error(f"Backup failed: {e}")

elif page == "Question Browser":
    page_header("Question Browser")
    years = [r for r in session.scalars(select(Paper.year).distinct().order_by(Paper.year))]
    sections, _tbs, _, _names = taxonomy_maps(session)
    c1, c2, c3, c4 = st.columns([3, 4, 3, 2])
    f_sec = c1.selectbox("Subject", ["(all)"] + sections, format_func=lambda x: named(x, _names) or "(all)",
                         key="qb_sec")
    _topic_opts = (_tbs.get(f_sec, []) if f_sec != "(all)"
                   else sorted({t for v in _tbs.values() for t in v}, key=lambda t: _names.get(t, t)))
    f_topic = c2.selectbox("Topic", ["(all)"] + _topic_opts, format_func=lambda x: named(x, _names) or "(all)")
    f_years = c3.multiselect("Years", years, default=years, placeholder="all years")
    f_type = c4.selectbox("Type", ["(all)", "MCQ", "MSQ", "NAT"])
    with st.container(horizontal=True, vertical_alignment="bottom"):
        f_status = st.selectbox("Label status", ["(all)", "suggested", "flagged", "verified", "unclassified"],
                                key="qb_status", format_func=status_label,
                                help="Full explanation: 'What the statuses mean' below the filters.")
        f_ext = st.selectbox("Extraction", ["(all)", "has an issue", "clean"], key="qb_ext", format_func=status_label,
                             help="'has an issue' = the extractor flagged the text/options for a check.")
        q_text = st.text_input("Search question text", placeholder="e.g. deadlock, eigenvalue, B+ tree")
    status_guide(session)
    _ext = {"(all)": None, "has an issue": True, "clean": False}[f_ext]
    rows = srch.search_questions(
        session, text_query=q_text or None, years=f_years or None,
        section_id=None if f_sec == "(all)" or f_status == "unclassified" else f_sec,
        topic_id=None if f_topic == "(all)" or f_status == "unclassified" else f_topic,
        q_type=None if f_type == "(all)" else f_type, extraction_issue=_ext,
        status=None if f_status in ("(all)", "unclassified") else f_status)
    if f_status == "unclassified":
        rows = [r for r in rows if not r.get("primary_topic_id")]
    for r in rows:
        r["subject"] = _names.get(r.get("section_id") or "", r.get("section_id") or "")
        r["topic"] = _names.get(r.get("primary_topic_id") or "", r.get("primary_topic_id") or "")
        r["status"] = r.get("status") or "unclassified"
        r["extraction"] = "check" if r.get("needs_review") else "ok"
    st.session_state["browser_grid_ids"] = [r["id"] for r in rows]

    _total = session.scalar(select(func.count()).select_from(Question))
    st.markdown(f"**{len(rows):,}** of {_total:,} questions match"
                + ("" if len(rows) == _total else " these filters") + ". Click a row to open it for review.")

    def _jump_from_grid():
        sel_rows = st.session_state["browser_grid"].selection.rows
        ids = st.session_state.get("browser_grid_ids", [])
        if sel_rows and sel_rows[0] < len(ids):
            st.session_state["_pending_screen"] = "Review Workspace"
            st.session_state["review_pick"] = ids[sel_rows[0]]
            st.session_state.pop("browser_grid", None)

    _bcols = ["id", "year", "session", "q_number", "marks", "q_type", "subject", "topic",
              "status", "confidence", "extraction"]
    st.dataframe(pd.DataFrame(rows, columns=_bcols + ["section_id", "primary_topic_id"])[_bcols], width="stretch",
                 hide_index=True, on_select=_jump_from_grid, selection_mode="single-row", key="browser_grid",
                 column_config={"id": st.column_config.TextColumn("question", pinned=True),
                                "q_number": st.column_config.NumberColumn("Q#"),
                                "q_type": "type",
                                "confidence": st.column_config.NumberColumn(format="%.2f"),
                                "extraction": st.column_config.TextColumn(
                                    help="'check' = the extractor flagged this question's text/options")})
    if rows:
        _df = pd.DataFrame(rows)
        with st.expander("Breakdown of these results (by subject and status)", icon=":material/bar_chart:"):
            _b1, _b2 = st.columns([3, 2])
            _by_sec = (_df.assign(subject=_df["subject"].replace("", "(no label)"))
                       .groupby("subject").agg(questions=("id", "count"), marks=("marks", "sum"))
                       .sort_values("questions", ascending=False).reset_index())
            _b1.dataframe(_by_sec, hide_index=True, width="stretch",
                          column_config={"questions": st.column_config.ProgressColumn(
                              format="%d", min_value=0, max_value=int(_by_sec["questions"].max()))})
            _b2.dataframe(_df.groupby("status").size().rename("questions").reset_index(), hide_index=True,
                          width="stretch")
            if f_sec != "(all)":
                _by_t = _df.groupby("topic").size().rename("questions").sort_values(ascending=False).reset_index()
                st.dataframe(_by_t, hide_index=True, width="stretch")

    def _jump_from_fallback():
        pick = st.session_state.get("browser_fallback_pick", "-")
        if pick != "-":
            st.session_state["_pending_screen"] = "Review Workspace"
            st.session_state["review_pick"] = pick

    with st.expander("Row click not working? Pick a question here", icon=":material/open_in_new:"):
        j1, j2 = st.columns([3, 1], vertical_alignment="bottom")
        j1.selectbox("Fallback: choose a question if row-click is unavailable",
                     ["-"] + [r["id"] for r in rows], key="browser_fallback_pick")
        j2.button("Open in Review Workspace", on_click=_jump_from_fallback)

elif page == "Analysis Matrix":
    page_header("Analysis Matrix")
    _, _, _, _mnames = taxonomy_maps(session)
    c1, c2 = st.columns(2)
    _yrs = [y for (y,) in session.execute(select(Paper.year).distinct().order_by(Paper.year))] or [2011, 2026]
    yf = c1.number_input("From year", 2007, 2100, max(min(_yrs), 2007))
    yt = c2.number_input("To year", 2007, 2100, max(_yrs))
    m = az.section_year_matrix(session, yf, yt)
    _ppy = az.papers_per_year(session)
    avg_mode = st.checkbox(
        "Average over sessions (divide each year by its number of classified papers)",
        help="Years with several sessions (e.g. 2013 had 4 papers) otherwise show several times the marks of a "
             "single-paper year. Averaging makes years comparable; clicking a cell still lists the real questions.")
    ver_only = st.checkbox("Count verified only (hide machine suggestions)",
                           help="Until human review happens this shows zeros - that is honest, not a bug.")
    if ver_only:
        m = az.section_year_matrix(session, yf, yt, verified_only=True)
    if avg_mode:
        m = az.averaged_matrix(m, _ppy)
    _ppy_txt = ("Classified papers per year: " + ", ".join(f"{y}: {_ppy.get(y, 0)}" for y in m["years"])) if m["years"] else ""
    drill = st.session_state.pop("drill", None)
    if drill:
        d_sec, d_year = drill
        _kind = st.session_state.pop("drill_kind", "section")
        st.subheader(f"Drill down: {named(d_sec, _mnames)} in {d_year}")
        if _kind == "topic":
            ids = list(session.scalars(
                select(Question.id)
                .join(Paper, Paper.id == Question.paper_id)
                .join(Classification, Classification.question_id == Question.id)
                .where(Classification.primary_topic_id == d_sec, Paper.year == d_year)
                .order_by(Question.q_number)))
        else:
            ids = az.drill_down(session, d_sec, d_year)
        n = len(ids)
        st.caption(f"{n} question{'s' if n != 1 else ''} contribute{'s' if n == 1 else ''} to this cell. "
                   "Click one to open it in the Review Workspace.")
        st.markdown(nav.drill_list_html(ids), unsafe_allow_html=True)
        if st.button("Back to full matrix"):
            st.rerun()
    else:
        _tot_q = session.scalar(select(func.count()).select_from(Question))
        _stat_counts = dict(session.execute(
            select(Classification.status, func.count()).group_by(Classification.status)).all())
        _n_cls = sum(_stat_counts.values())
        st.subheader("Subject x year")
        st.caption(f"Two views of the same questions: marks (a 2-mark question counts 2) and question counts. "
                   f"One paper = 65 questions = 100 marks, so {_tot_q // 65} papers = {_tot_q:,} questions = {_tot_q // 65 * 100:,} marks. "
                   f"Click any number to see its questions. Bottom row = column totals; bottom-right = grand total. {_n_cls:,} of {_tot_q:,} questions counted.")
        with how_to_read():
            st.markdown("Primary topic only; totals always reconcile to paper totals. Only classified questions are "
                        f"included: **{_n_cls} of {_tot_q} questions** "
                        f"({_stat_counts.get('verified', 0)} verified, {_stat_counts.get('suggested', 0)} suggested, "
                        f"{_stat_counts.get('flagged', 0)} flagged - all machine suggestions until a human verifies "
                        f"them). The LEGACY column is historical software engineering, out of the 2027 syllabus.")
            if _ppy_txt:
                st.caption(_ppy_txt)
        _tm, _tq = st.tabs(["Marks", "Questions"])
        with _tm:
            st.markdown(nav.matrix_html(m, _mnames), unsafe_allow_html=True)
        with _tq:
            st.markdown(nav.matrix_html(m, _mnames, metric="questions"), unsafe_allow_html=True)
        with st.expander("Drill down (fallback dropdowns)", icon=":material/filter_list:"):
            d1, d2 = st.columns(2)
            d_sec = d1.selectbox("Cell subject", list(m["sections"].keys()) or ["-"], format_func=lambda x: named(x, _mnames))
            d_year = d2.selectbox("Cell year", m["years"] or ["-"])
            if d_sec != "-" and d_year != "-":
                st.write(az.drill_down(session, d_sec, d_year))
    with st.expander("Type / marks mix (MCQ / MSQ / NAT, 1 and 2 marks)", icon=":material/pie_chart:"):
        st.dataframe(pd.DataFrame(az.type_marks_mix(session, yf, yt)), width="stretch")
    st.subheader("Topic x year (questions)")
    _secs, _tbs2, _, _names2 = taxonomy_maps(session)
    t_sec = st.selectbox("Subject for the topic matrix", _secs, key="topic_matrix_sec", format_func=lambda x: named(x, _names2))
    t_rows = az.topic_year_matrix(session, t_sec, yf, yt)
    if t_rows:
        st.caption("Every number is clickable and opens that cell's contributing questions (counts are "
                   "machine suggestions until verified).")
        st.markdown(nav.topic_matrix_html(t_rows, _names2), unsafe_allow_html=True)
    else:
        st.caption("No classified questions for this section in the selected years.")

elif page == "Topic Report":
    page_header("Topic Report")
    with how_to_read():
        st.caption("Only classified questions are included; papers not yet classified are excluded (see Pipeline Status).")
        st.markdown("**Score-first priority** (historical marks share, recency-weighted x1.5 for recent years; "
                    "descriptive, not predictive. Prerequisite edges exist but are curated/inferred, "
                    "not official syllabus relationships - see exports/prerequisite_edges.csv provenance.) "
                    "LEGACY.SE is historical software engineering - out of the 2027 syllabus.")
    pr = az.priority_ranking(session)
    _, _, _, _trn = taxonomy_maps(session)
    _prdf = pd.DataFrame(pr)
    if len(_prdf):
        _prdf.insert(1, "name", _prdf["topic"].map(lambda c: _trn.get(c, "")))
    st.dataframe(_prdf, width="stretch", hide_index=True)
    st.subheader("Drill into a topic")
    _t = st.selectbox("Topic", [r["topic"] for r in pr], key="tr_topic", format_func=lambda x: named(x, _trn))
    _q = (select(Question.id, Paper.year, Question.q_number, Classification.status)
          .join(Paper, Paper.id == Question.paper_id)
          .join(Classification, Classification.question_id == Question.id)
          .where(Classification.primary_topic_id == _t)
          .order_by(Paper.year, Question.q_number))
    _rows = [{"question": qid, "year": y, "q#": n, "status": st_} for qid, y, n, st_ in session.execute(_q)]
    st.caption(f"{len(_rows)} questions classified as {named(_t, _trn)} "
               f"({sum(1 for r in _rows if r['status'] == 'verified')} verified, "
               f"{sum(1 for r in _rows if r['status'] == 'suggested')} suggested, "
               f"{sum(1 for r in _rows if r['status'] == 'flagged')} flagged). Click one to open it.")
    st.dataframe(pd.DataFrame(_rows), width="stretch", hide_index=True)
    st.markdown(nav.drill_list_html([r["question"] for r in _rows]), unsafe_allow_html=True)

elif page == "Subject Overview":
    page_header("Subject Overview")
    with how_to_read():
        st.caption("Topics, concepts and prerequisite edges come from taxonomy.yaml (curated, not official "
                   "syllabus relationships). Question counts are machine suggestions until a human verifies them.")
    _secs3, _tbs3, _cbt3, _names3 = taxonomy_maps(session)
    ov_sec = st.selectbox("Subject", _secs3, key="ov_sec",
                          format_func=lambda x: named(x, _names3))
    _stat_rows = session.execute(
        select(Classification.primary_topic_id, Classification.status, func.count())
        .where(Classification.section_id == ov_sec)
        .group_by(Classification.primary_topic_id, Classification.status)).all()
    _agg = {}
    for t, st_, n in _stat_rows:
        d = _agg.setdefault(t, {"suggested": 0, "flagged": 0, "verified": 0})
        d[st_ if st_ in d else "suggested"] += n
    _rows = []
    for t in _tbs3.get(ov_sec, []):
        d = _agg.get(t, {"suggested": 0, "flagged": 0, "verified": 0})
        _rows.append({"topic": t, "name": _names3.get(t, ""), "questions": sum(d.values()),
                      "verified": d["verified"], "suggested": d["suggested"], "flagged": d["flagged"]})
    st.dataframe(pd.DataFrame(_rows), width="stretch", hide_index=True)
    st.subheader("Per-topic detail")
    st.caption("Open a topic for its concepts and what its questions test.")
    for t in _tbs3.get(ov_sec, []):
        with st.expander(named(t, _names3)):
            _concept_names = [f"- **{c}** - {_names3.get(c, '')}" if _names3.get(c) else f"- {c}"
                              for c in _cbt3.get(t, [])]
            st.markdown("Concepts:\n" + ("\n".join(_concept_names) or "-"))
            _wit = [w for (w,) in session.execute(
                select(Classification.what_it_tests)
                .where(Classification.primary_topic_id == t,
                       Classification.what_it_tests.isnot(None),
                       Classification.what_it_tests != "")
                .limit(3)) if w]
            if _wit:
                st.markdown("What it tests (sample from classifications):")
                for _w in _wit:
                    st.markdown(f"- {_w}")
            else:
                st.caption("What it tests: not recorded - the v2 first pass is topic-level only; "
                           "the API proposals pass can supply these, or add during review.")
    st.subheader("Prerequisites in this subject")
    st.caption("Curated/inferred - not official syllabus relationships.")
    import yaml as _yaml
    _raw = _yaml.safe_load(open(APP_ROOT / "taxonomy.yaml"))
    _topic_set = set(_tbs3.get(ov_sec, []))
    _concept_set = {c for t in _topic_set for c in _cbt3.get(t, [])}
    _edge_rows = []
    for _e in (_raw.get("prerequisites") or []):
        _c, _r = _e.get("concept"), _e.get("requires")
        if _c in _concept_set:
            _edge_rows.append({"concept": f"{_c} ({_names3.get(_c, '')})",
                               "requires": f"{_r} ({_names3.get(_r, '')})",
                               "provenance": _e.get("note", "curated")})
    if _edge_rows:
        st.dataframe(pd.DataFrame(_edge_rows), width="stretch", hide_index=True)
    else:
        st.caption("No curated prerequisite edges for this subject's concepts yet.")

elif page == "Review Workspace":
    page_header("Review Workspace")
    _flash_msg = st.session_state.pop("_flash", None)
    if _flash_msg:
        st.success(_flash_msg)
    counts = rv.review_counts(session)
    prog_all = rv.verification_progress(session)
    from src.validation import benchmark as _bm
    _sample = _bm.sample_membership(session)
    _gold = sum(1 for v in _sample.values() if v[1] == "gold_verified")
    with st.container(horizontal=True):
        st.metric("Verified by a human", f"{prog_all['verified']:,} of {prog_all['total_questions']:,}", border=True)
        st.metric("Awaiting your decision", f"{counts['of_which_classifier_flagged'] + counts['of_which_unverified_suggestions']:,}",
                  help=f"{counts['of_which_classifier_flagged']} flagged by the classifier + "
                       f"{counts['of_which_unverified_suggestions']} unverified suggestions", border=True)
        st.metric("Extraction issues", f"{counts['of_which_extraction_issues']:,}",
                  help="questions whose text/options the extractor flagged for a check", border=True)
        st.metric("Benchmark gold", f"{_gold} of {len(_sample)}", help="the 120-question sample you verify first",
                  border=True)
    status_guide(session)
    with st.expander("What you do here - step by step", icon=":material/school:"):
        st.markdown(
            "**What you have for each question:** the **original PDF crop** (the truth), the **text the computer "
            "read** from it, the official **answer key** (when one exists), the **machine label** (subject + topic), "
            "and any **second opinions** (AI review, decision models).\n\n"
            "1. **Look at the PDF image.** Does the extracted text and every option match it? If not, open "
            "*Correct the extraction* and fix it (an extraction issue clears once corrected).\n"
            "2. **Read the label.** Is this the subject and topic the question really tests? Use the AI opinion as a "
            "hint, not an answer.\n"
            "3. **Correct the label** in *Your decision* if needed (dropdowns show full names).\n"
            "4. **Answer the five checks** (pass/fail). *Source fidelity* and *Primary topic* must pass to verify.\n"
            "5. **Verify** (or *Approve & next*). If unsure, **Flag** it.\n\n"
            "**What changes when you act:** the label's status becomes *verified* under your name, an audit event "
            "stores the old and new values, and a benchmark question becomes gold. Nothing else is ever "
            "auto-approved.")
    pre = st.session_state.pop("review_pick", None)
    if pre:
        _pq = session.get(Question, pre)
        if _pq is not None:
            # a deep link drives BOTH filters: the paper dropdown follows the linked question,
            # so the displayed paper can never disagree with the displayed question
            st.session_state["rw_paper"] = _pq.paper_id
    _paper_ids = [r for r in session.scalars(select(Paper.id).order_by(Paper.year, Paper.session))]
    SHOW_OPTS = ["all questions", "awaiting my decision", "extraction issues", "AI-reviewed",
                 "benchmark sample (gold review)", "verified", "no classification yet"]
    if st.session_state.get("rw_show") not in SHOW_OPTS:
        st.session_state.pop("rw_show", None)
    with st.container(border=True):
        f1, f3 = st.columns([3, 2])
        f_paper = f1.selectbox("Paper", ["(all papers)"] + _paper_ids, key="rw_paper")
        f_order = f3.radio("Order", ["paper order", "review priority first"], horizontal=True, key="rw_order",
                           help="Priority = most-likely-wrong first (taxonomy gaps, flagged, low confidence).")
        f_show = st.radio("Show", SHOW_OPTS, horizontal=True, key="rw_show")
    _q = select(Question.id, Question.printed_label).order_by(Question.paper_id, Question.q_number)
    if f_paper != "(all papers)":
        _q = _q.where(Question.paper_id == f_paper)
    _rows = session.execute(_q).all()
    _label = {i: (pl or "") for i, pl in _rows}
    all_ids = [i for i, _ in _rows]
    if f_show == "benchmark sample (gold review)":
        all_ids = [i for i in all_ids if _sample.get(i, (None, ""))[1] == "pending_user_review"]
        st.caption("Verifying a sampled question records your decision as its benchmark gold - nothing is "
                   "auto-approved. Verified ones leave this list.")
    elif f_show == "extraction issues":
        _ext = set(session.scalars(select(Question.id).where(Question.needs_review == True)))  # noqa: E712
        all_ids = [i for i in all_ids if i in _ext]
        st.caption("Compare the text and options with the PDF image, then fix them under *Correct the extraction*.")
    elif f_show == "AI-reviewed":
        _air = set(session.scalars(select(ReviewEvent.question_id).where(ReviewEvent.field == "ai_review")))
        all_ids = [i for i in all_ids if i in _air]
    elif f_show != "all questions":
        _await = {r["question_id"] for r in rv.review_queue(session, classified_only=True)}
        _cls_ids = set(session.scalars(select(Classification.question_id)))
        _ver = set(session.scalars(select(Classification.question_id).where(Classification.status == "verified")))
        all_ids = [i for i in all_ids if (i in _await if f_show == "awaiting my decision"
                                          else i in _ver if f_show == "verified" else i not in _cls_ids)]
    if pre and pre not in all_ids and session.get(Question, pre):
        all_ids = [pre] + all_ids            # a deep link must always open its question
        _label.setdefault(pre, session.get(Question, pre).printed_label or "")
    _prio: dict = {}
    if f_order == "review priority first":
        _prio = {r["question_id"]: (r["priority_rank"], r["priority_bucket"])
                 for r in rv.prioritized_review_queue(session, include_spotcheck=False)}
        _maxr = len(_prio) + 1
        # same membership, decision order: most-likely-wrong first (buckets in validation.review)
        all_ids.sort(key=lambda i: (_prio.get(i, (_maxr, ""))[0], i))
    if not all_ids:
        st.info("No questions match this filter.")
    # A STABLE key (not an index computed from the deep link): Streamlit derives a widget's identity from its
    # parameters, so a changing `index` made the dropdown snap back to question 1 after any deep link.
    # Paper+filter-scoped widget key: switching paper or filter creates a NEW widget, so a question
    # from another paper/filter can never linger in the dropdown while the body renders a different
    # question (observed wrong-question review/approval risk; browser-verified).
    _qkey = f"rw_question::{f_paper}::{f_show}::{f_order}"
    if pre and pre in all_ids:
        st.session_state[_qkey] = pre
    elif st.session_state.get(_qkey) not in all_ids:
        st.session_state.pop(_qkey, None)
    uid = st.selectbox("Question", all_ids, key=_qkey,
                       format_func=lambda x: f"{x}   ({_label.get(x) or '-'})") if all_ids else None
    if uid:
        qu = session.get(Question, uid)
        cls = session.scalar(select(Classification).where(Classification.question_id == uid))
        key = session.scalar(select(AnswerKey).where(AnswerKey.question_id == uid))
        secs, topics_by_sec, concepts_by_topic, names = taxonomy_maps(session)
        _pos = all_ids.index(uid) + 1
        _pp = rv.verification_progress(session, qu.paper_id)
        st.caption(f"{_pos} of {len(all_ids)} in this list · printed in the paper as "
                   f"**{qu.printed_label or 'Q ' + str(qu.q_number)}** · {qu.marks:g} mark(s), {qu.q_type or 'type ?'} · "
                   f"this paper: {_pp['verified']} of {_pp['total_questions']} verified")
        if _prio.get(uid):
            st.caption(f"Review priority #{_prio[uid][0]} of {len(_prio)} - bucket: "
                       f"**{_prio[uid][1].replace('_', ' ')}**")

        # ---- status strip: where this question stands in every stage, and where each fact comes from ----
        _stg = op.question_stages(session, uid)
        _strip = [("Extraction", ":material/description:", _stg["extraction"], _stg["text_source"]),
                  ("Machine label", ":material/label:", _stg["machine"],
                   named(cls.primary_topic_id, names) if cls else "-"),
                  ("AI review", ":material/forum:", _stg["ai_review"], "opinion only"),
                  ("Decision models", ":material/psychology:", _stg["decision_models"], "opinion only"),
                  ("Human review", ":material/verified:", _stg["human"], "the only approval")]
        for _c, (_t, _ic, (_state, _color, _detail), _src) in zip(st.columns(5), _strip):
            with _c.container(border=True, height="stretch"):
                st.markdown(f"**{_ic} {_t}**  \n:{_color}-badge[{_state}]")
                st.caption(f"{_detail}  \n*{_src}*")

        left, right = st.columns(2, gap="large")
        with left:
            st.subheader(":material/picture_as_pdf: 1 · Original source", divider="gray",
                         help="Rendered on demand from the original PDF. This is the truth.")
            previews, preview_reason = source_previews(session, qu)
            if previews:
                for seg in previews:
                    st.image(seg["png"], caption=f"original PDF, page {seg['page']}")
            elif qu.image_path:
                st.image(qu.image_path, caption=f"legacy stored crop, pages {qu.page_start}-{qu.page_end}")
            else:
                st.info(f"No source preview available - {preview_reason}.")
            st.markdown("**What the computer read**" + (" (OCR from a scan - trust the image over the text)"
                                                         if qu.extraction_status == "ocr" else " (digital PDF text)"))
            with st.container(border=True):
                st.write(qu.text)
                for o in session.scalars(select(Option).where(Option.question_id == uid)):
                    st.write(f"({o.label}) {o.content}")
            if qu.review_reason:
                st.warning("**Extraction issue:** " + qu.review_reason, icon=":material/warning:")
            if key:
                label = rv.key_provenance_label(session, uid)
                rng = f" [{key.answer_min}-{key.answer_max}]" if key.answer_min is not None else ""
                (st.warning if label.startswith("Fixture") else st.success)(
                    f"**Answer key** - {label} ({key.key_version}): {key.answer_list}{rng}")
                if key.notes:
                    st.caption("Key note: " + key.notes)
            else:
                st.caption("Answer key: none loaded for this paper (listed as missing, never guessed).")
            with st.expander("Correct the extraction (text, options, marks, type)", icon=":material/edit_note:"):
                st.caption("Compare with the image above. Every change is saved with your name, the old and new "
                           "value and the time. A corrected question is protected: re-loading the PDF never "
                           "overwrites it.")
                new_text = st.text_area("Question text", value=qu.text or "", height=160, key=f"rw_text_{uid}")
                _opt_rows = list(session.scalars(select(Option).where(Option.question_id == uid).order_by(Option.label)))
                new_opts = {o.label: st.text_input(f"Option ({o.label})", value=o.content or "", key=f"rw_opt_{uid}_{o.label}")
                            for o in _opt_rows}
                _mc, _tc = st.columns(2)
                _marks_opts = ["(unknown)", 1.0, 2.0]
                new_marks = _mc.selectbox("Marks", _marks_opts, key=f"rw_marks_{uid}",
                                          index=_marks_opts.index(qu.marks) if qu.marks in _marks_opts else 0)
                _type_opts = ["(unknown)", "MCQ", "MSQ", "NAT"]
                new_type = _tc.selectbox("Type", _type_opts, key=f"rw_type_{uid}",
                                         index=_type_opts.index(qu.q_type) if qu.q_type in _type_opts else 0)
                x_note = st.text_input("Reason (goes to the audit log)", key=f"rw_xnote_{uid}")
                if st.button("Save extraction correction", key=f"rw_xsave_{uid}"):
                    _n = 0
                    if new_text != (qu.text or ""):
                        rv.apply_decision(session, uid, "text", new_text, REVIEWER, x_note); _n += 1
                    for o in _opt_rows:
                        if new_opts[o.label] != (o.content or ""):
                            rv.apply_decision(session, uid, f"option:{o.label}", new_opts[o.label], REVIEWER, x_note); _n += 1
                    if new_marks != "(unknown)" and new_marks != qu.marks:
                        rv.apply_decision(session, uid, "marks", new_marks, REVIEWER, x_note); _n += 1
                    if new_type != "(unknown)" and new_type != qu.q_type:
                        rv.apply_decision(session, uid, "q_type", new_type, REVIEWER, x_note); _n += 1
                    session.commit()
                    st.session_state["_flash"] = f"{uid}: {_n} extraction correction(s) saved" if _n else "no extraction changes to save"
                    st.rerun()
        with right:
            st.subheader(":material/label: 2 · Machine label", divider="gray",
                         help="Proposed by a classifier model. A suggestion until a human verifies it.")
            if cls:
                with st.container(border=True):
                    st.markdown(f"**Subject:** {named(cls.section_id, names)}  \n"
                                f"**Topic:** {named(cls.primary_topic_id, names)}")
                    _sc = {"verified": "green", "flagged": "orange"}.get(cls.status, "blue")
                    st.markdown(f":{_sc}-badge[{cls.status}] :gray-badge[confidence {cls.confidence:.2f}] "
                                f":gray-badge[{(cls.model or 'unknown model')[:40]}]")
                n_prov = cls.provider_count if cls.provider_count is not None else 1
                legacy = any("pre-v6" in str(v.get("provider", "")) for v in (cls.provider_votes or []))
                with st.expander("Label details (score, concepts, what it tests)", icon=":material/info:"):
                    if legacy:
                        st.caption("Legacy inferred suggestion - original confidence retained; no ensemble run "
                                   "recorded for this row.")
                    elif n_prov > 1 and cls.agreement is not None:
                        st.caption(f"Combined score {cls.combo_score:.2f} = agreement {cls.agreement:.2f} x mean "
                                   f"confidence across {n_prov} providers. A review-priority heuristic, not a "
                                   "correctness probability.")
                    else:
                        st.caption("One provider: the score is the model's own confidence (no ensemble agreement).")
                    st.markdown("**What it tests:** " + (cls.what_it_tests or "_not recorded yet - add it below if useful_"))
                    st.markdown("**Concepts:** " + (", ".join(named(c, names) for c in (cls.concept_ids or [])) or "none"))
                    if cls.prerequisite_ids:
                        st.markdown("**Prerequisites:** " + ", ".join(named(p, names) for p in cls.prerequisite_ids))
                    if cls.provider_votes and len(cls.provider_votes) > 1:
                        st.json(cls.provider_votes)

            st.subheader(":material/forum: 3 · Second opinions", divider="gray",
                         help="AI review and decision models. Opinions only - never verification, never gold.")
            if _stg["ai_rows"]:
                for _r in _stg["ai_rows"]:
                    _box = {"agree": st.success, "flag": st.warning, "correct": st.error}.get(_r["verdict"], st.info)
                    _same = cls is not None and _r["primary_topic_id"] == cls.primary_topic_id
                    _box(f"**AI review: {_r['verdict']}** → {named(_r['primary_topic_id'], names)}"
                         f"{' (same as the label)' if _same else ' (DIFFERENT from the label)'}  \n"
                         f"{_r['note']}  \n*{_r['reviewer']} · {_r['when']}*", icon=":material/smart_toy:")
            else:
                st.caption("AI review: none for this question.")
            if _stg["decision_rows"]:
                for _p in _stg["decision_rows"]:
                    st.info(f"**{_p.provider}** ({_p.model}) → {named(_p.primary_topic_id, names)} · "
                            f"probability {(_p.confidence or 0):.2f}", icon=":material/psychology:")
            else:
                st.caption("Decision models: not run (paid, off by default).")

            if cls:
                st.subheader(":material/how_to_reg: 4 · Your decision", divider="gray",
                             help="The only step that makes a label true. Every action is written to the audit log.")
                cur_sec = cls.section_id if cls.section_id in secs else secs[0]
                new_sec = st.selectbox("Section", secs, index=secs.index(cur_sec),
                                       format_func=lambda x: named(x, names), key=f"rw_sec_{uid}")
                sec_topics = topics_by_sec.get(new_sec, []) or ["-"]
                cur_topic = cls.primary_topic_id if cls.primary_topic_id in sec_topics else sec_topics[0]
                new_topic = st.selectbox("Topic", sec_topics, index=sec_topics.index(cur_topic),
                                         format_func=lambda x: named(x, names), key=f"rw_topic_{uid}")
                all_concepts = sorted({c for lst in concepts_by_topic.values() for c in lst})
                cur_concepts = [c for c in (cls.concept_ids or []) if c in all_concepts]
                all_topics = sorted({t for lst in topics_by_sec.values() for t in lst})
                cur_secondary = [t for t in (cls.topic_weight or {}) if t != cls.primary_topic_id and t in all_topics]
                with st.expander("More detail (optional): concepts, secondary topics, what it tests, note",
                                 icon=":material/tune:"):
                    _sug = concepts_by_topic.get(new_topic, [])
                    new_concepts = st.multiselect("Concepts", _sug + [c for c in all_concepts if c not in _sug],
                                                  default=cur_concepts, format_func=lambda x: named(x, names),
                                                  key=f"rw_concepts_{uid}",
                                                  help="The chosen topic's own concepts are listed first.")
                    new_secondary = st.multiselect("Secondary topics (tags only - never counted in marks)",
                                                   [t for t in all_topics if t != new_topic],
                                                   default=[t for t in cur_secondary if t != new_topic],
                                                   format_func=lambda x: named(x, names), key=f"rw_secondary_{uid}")
                    new_wit = st.text_input("What it tests (one sentence)", value=cls.what_it_tests or "",
                                            key=f"rw_wit_{uid}")
                    note = st.text_input("Note (optional, goes to audit log)", key=f"rw_note_{uid}")

                # ---- five-point rubric: a reviewer's record, not a GATE score and not model confidence ----
                st.markdown("**Review checks** - *Source fidelity* and *Primary topic* must pass to verify.")
                _prev = rv.latest_rubric(session, uid) or {}
                scores = {}
                with st.container(border=True):
                    _rc = st.columns(2)
                    for _i, (_k, _lab, _help) in enumerate(rv.RUBRIC):
                        _d = _prev.get(_k)
                        scores[_k] = _rc[_i % 2].radio(_lab, [1, 0], index=None if _d not in (0, 1) else [1, 0].index(_d),
                                                       format_func=lambda v: "pass" if v == 1 else "fail",
                                                       horizontal=True, help=_help, key=f"rw_rub_{_k}_{uid}")
                _answered = all(v is not None for v in scores.values())
                _scope = rv.approval_scope(session, uid)
                st.caption(f"Checks: {sum(v for v in scores.values() if v is not None)}/5"
                           + ("" if _answered else " (answer all five)")
                           + " · approved so far - label: " + ("yes" if _scope["classification_verified"] else "no")
                           + ", extraction: " + ("yes" if _scope["extraction_verified"] else "no")
                           + ", key: " + ("missing" if _scope["key_status"] == "missing"
                                          else "verified" if _scope["key_verified"] else "not yet verified"))

                def _apply_corrections(reviewer=None):
                    reviewer = reviewer or REVIEWER
                    changed = False
                    if new_sec != cls.section_id:
                        rv.apply_decision(session, uid, "section_id", new_sec, reviewer, note)
                        changed = True
                    if new_topic != "-" and new_topic != cls.primary_topic_id:
                        rv.apply_decision(session, uid, "primary_topic_id", new_topic, reviewer, note)
                        changed = True
                    if list(new_concepts) != list(cls.concept_ids or []):
                        rv.apply_decision(session, uid, "concept_ids", list(new_concepts), reviewer, note)
                        changed = True
                    if sorted(new_secondary) != sorted(cur_secondary):
                        rv.apply_decision(session, uid, "secondary_topic_ids", list(new_secondary), reviewer, note)
                        changed = True
                    if new_wit != (cls.what_it_tests or ""):
                        rv.apply_decision(session, uid, "what_it_tests", new_wit, reviewer, note)
                        changed = True
                    if _answered and {k: scores[k] for k in rv.RUBRIC_KEYS} != {k: _prev.get(k) for k in rv.RUBRIC_KEYS}:
                        rv.save_rubric(session, uid, scores, reviewer, note)
                        changed = True
                    return changed

                def _flash(msg: str):          # shown on the NEXT run (st.rerun() would swallow a success() here)
                    st.session_state["_flash"] = msg

                def _verify(msg: str) -> bool:
                    """Verify = a human approval. Refused unless all five checks are answered and the two required
                    ones pass; nothing is written in that case."""
                    if not _answered:
                        st.error("Score all five review checks first (pass/fail) - nothing was saved.")
                        return False
                    if scores["source_fidelity"] != 1 or scores["primary_topic"] != 1:
                        st.error("Cannot verify: 'Source fidelity' and 'Primary topic' must both pass. Correct the "
                                 "extraction/topic, or Flag it - nothing was verified.")
                        return False
                    _apply_corrections()
                    rv.set_status(session, uid, "verified", reviewer=REVIEWER, note=note)
                    session.commit(); _flash(msg)
                    return True

                b5, b6 = st.columns(2)     # two per row: the shortcut hints make three-per-row labels truncate
                if b5.button("Approve & next", key=f"rw_next_{uid}", shortcut="Ctrl+Enter", type="primary",
                             width="stretch", help="Verify (with any corrections above) and open the next one"):
                    nxt = rv.next_pending(session, uid)
                    if nxt == uid:
                        nxt = None                       # it was the last one: nothing left to advance to
                    if _verify(f"{uid} verified by {REVIEWER}; next: {nxt}" if nxt else f"{uid} verified - nothing left awaiting a decision"):
                        if nxt:
                            st.session_state["review_pick"] = nxt
                        st.rerun()
                if b6.button("Skip to next pending", key=f"rw_skip_{uid}", shortcut="Alt+N", width="stretch"):
                    nxt = rv.next_pending(session, uid)
                    if nxt and nxt != uid:
                        st.session_state["review_pick"] = nxt
                    st.rerun()
                b1, b4 = st.columns(2)
                if b1.button("Verify as-is", key=f"rw_verify_{uid}", shortcut="Alt+V", width="stretch"):
                    if _verify(f"{uid} verified by {REVIEWER}"):
                        st.rerun()
                if b4.button("Verify with correction", key=f"rw_vwc_{uid}", width="stretch"):
                    if _verify(f"{uid} corrected and verified by {REVIEWER}"):
                        st.rerun()
                b3, b2 = st.columns(2)
                if b3.button("Save without verifying", key=f"rw_save_{uid}", width="stretch",
                             help="Keep corrections and checks; approve later (here or in the Approve Queue)"):
                    if _apply_corrections():
                        session.commit(); _flash(f"{uid}: saved (NOT verified)")
                    else:
                        _flash("no changes to save")
                    st.rerun()
                if b2.button("Flag", key=f"rw_flag_{uid}", shortcut="Alt+X", width="stretch",
                             help="Not sure / something is wrong - come back to it later"):
                    if _answered:
                        _apply_corrections()
                    rv.set_status(session, uid, "flagged", reviewer=REVIEWER, note=note)
                    session.commit(); _flash(f"{uid} flagged"); st.rerun()
                st.caption("Every action is saved with your name (sidebar) in the audit log.")
            else:
                st.info("This question has no label yet, so there is nothing to verify. Add one with the LLM Classify "
                        "screen or the chat-assisted batch workflow. You can still read the source, correct the "
                        "extraction and see the key on the left.")
        with st.expander("Audit history for this question (every change, oldest first)", icon=":material/history:"):
            _hist = rv.audit_history(session, uid)
            if _hist:
                st.dataframe(pd.DataFrame(_hist), hide_index=True, width="stretch")
            else:
                st.caption("No review events yet.")

elif page == "Second Opinions":
    page_header("Second Opinions")
    status_guide(session)
    _, _, _, _onames = taxonomy_maps(session)
    _ai_rows = op.ai_review_rows(session)
    _dec_rows = op.decision_rows(session)
    _vc = {}
    for r in _ai_rows:
        _vc[r["verdict"]] = _vc.get(r["verdict"], 0) + 1
    with st.container(horizontal=True):
        st.metric("AI-reviewed questions", len(_ai_rows), border=True)
        st.metric("Agree", _vc.get("agree", 0), help="the AI found the label right", border=True)
        st.metric("Flag", _vc.get("flag", 0), help="label probably fine, but something else needs a look "
                                                   "(often the extraction)", border=True)
        st.metric("Correct", _vc.get("correct", 0), help="the AI thinks the topic is wrong and proposes another",
                  border=True)
        st.metric("Decision-model answers", len(_dec_rows), border=True)
    st.info("**What to do:** open the **correct** rows first (the AI disagrees with the topic), then **flag** "
            "(usually an extraction problem). Click a row to open it in the Review Workspace and decide yourself. "
            "These opinions never change a label on their own.", icon=":material/lightbulb:")
    _tab_ai, _tab_dec = st.tabs([f"AI review ({len(_ai_rows)})", f"Decision models ({len(_dec_rows)})"])
    with _tab_ai:
        if not _ai_rows:
            st.caption("No AI-review opinions recorded yet.")
        else:
            o1, o2, o3 = st.columns(3)
            _verd = o1.multiselect("Verdict", ["correct", "flag", "agree"], default=["correct", "flag", "agree"])
            _papers = sorted({r["paper"] for r in _ai_rows})
            _pp = o2.selectbox("Paper", ["(all)"] + _papers, key="so_paper")
            _diff = o3.toggle("Only where the AI picked a different topic", key="so_diff")
            _view = [r for r in _ai_rows if r["verdict"] in _verd and (_pp == "(all)" or r["paper"] == _pp)
                     and (not _diff or not r["same_topic"])]
            _df = pd.DataFrame([{
                "question": r["question_id"], "verdict": r["verdict"],
                "AI's topic": named(r["ai_topic"], _onames), "current label": named(r["label_topic"], _onames),
                "same?": r["same_topic"], "label status": r["label_status"], "AI's note": r["note"],
                "reviewer": r["reviewer"].split(" ")[0], "when": r["when"]} for r in _view])
            st.session_state["so_grid_ids"] = [r["question_id"] for r in _view]

            def _jump_so():
                sel = st.session_state["so_grid"].selection.rows
                ids = st.session_state.get("so_grid_ids", [])
                if sel and sel[0] < len(ids):
                    st.session_state["_pending_screen"] = "Review Workspace"
                    st.session_state["review_pick"] = ids[sel[0]]
                    st.session_state.pop("so_grid", None)
            st.caption(f"{len(_view)} shown. Click a row to open it.")
            st.dataframe(_df, hide_index=True, width="stretch", on_select=_jump_so, selection_mode="single-row",
                         key="so_grid",
                         column_config={"question": st.column_config.TextColumn(pinned=True),
                                        "AI's note": st.column_config.TextColumn(width="large")})
    with _tab_dec:
        if _dec_rows:
            st.dataframe(pd.DataFrame([{**r, "topic": named(r["topic"], _onames)} for r in _dec_rows]),
                         hide_index=True, width="stretch")
        else:
            st.caption("No decision-model answers yet. They are paid and off by default - see LLM Classify → "
                       "Decision models for setup and the exact command.")
            st.button("Open decision models", icon=":material/arrow_forward:", on_click=goto("LLM Classify"))

elif page == "Approve Queue":
    page_header("Approve Queue")
    status_guide(session)
    st.info("**When to use this:** after you checked questions in the Review Workspace and pressed *Save without "
            "verifying* (corrections + passing checks saved). Here you approve them in one go. A question without "
            "saved, passing checks can never be approved here - an AI suggestion alone is never enough.",
            icon=":material/lightbulb:")
    _ready = op.ready_to_approve(session)
    rows = [r for r in rv.review_queue(session) if r["status"] in ("suggested", "flagged")]
    f0, f1, f2, f3 = st.columns([3, 2, 2, 1], vertical_alignment="bottom")
    only_ready = f0.toggle(f"Only questions ready to approve ({sum(1 for r in rows if r['question_id'] in _ready)})",
                           value=True, key="aq_only_ready",
                           help="ready = saved review checks with Source fidelity and Primary topic passing")
    min_combo = f1.slider("Minimum combined score", 0.0, 1.0, 0.0, 0.05,
                          help="Heuristic filter: provider agreement x mean confidence.")
    only_flagged = f2.checkbox("Only classifier-flagged", value=False)
    page_size = f3.selectbox("Rows per page", [10, 20, 50], index=0)
    if only_ready:
        rows = [r for r in rows if r["question_id"] in _ready]
    if only_flagged:
        rows = [r for r in rows if r["status"] == "flagged"]
    ids = [r["question_id"] for r in rows]
    combo_map = {}
    for qid, combo in session.execute(
            select(Classification.question_id, Classification.combo_score)
            .where(Classification.question_id.in_(ids))):
        combo_map[qid] = combo
    rows = [r for r in rows if (combo_map.get(r["question_id"]) or 0.0) >= min_combo]
    rows.sort(key=lambda r: -(combo_map.get(r["question_id"]) or 0.0))
    if not rows:
        st.caption("Nothing to approve with these filters." + (" Check questions in the Review Workspace and use "
                                                                "'Save without verifying' to make them ready." if only_ready else ""))
    else:
        st.caption(f"{len(rows)} rows match; sorted by combined score (highest first).")
    pages = max(1, (len(rows) + page_size - 1) // page_size)
    page_no = st.number_input("Page", 1, pages, 1) - 1
    view = rows[page_no * page_size:(page_no + 1) * page_size]
    secs, topics_by_sec, _, names = taxonomy_maps(session)
    all_topics = sorted({t for lst in topics_by_sec.values() for t in lst}, key=lambda t: names.get(t, t))
    for r in view:
        qid = r["question_id"]
        with st.container(border=True):
            rc1, rc2, rc3 = st.columns([3, 2, 1], vertical_alignment="center")
            combo_v = combo_map.get(qid)
            rc1.markdown(f"**{qid}** :gray-badge[{r['status']}] :gray-badge[{r['q_type']}, {r['marks']:g} marks]"
                         + (" :green-badge[ready]" if qid in _ready else "") + "  \n"
                         f"{named(r['primary_topic_id'], names)} · conf {r['confidence']:.2f}"
                         + (f", combo {combo_v:.2f}" if combo_v is not None else ""))
            rc2.selectbox("Correct to (optional)", [""] + all_topics,
                          format_func=lambda x: named(x, names) if x else "keep suggestion",
                          key=f"aq_corr_{qid}", label_visibility="collapsed")
            rc3.checkbox("Approve", key=f"aq_appr_{qid}")
    if view and st.button("Select all on this page"):
        for r in view:
            st.session_state[f"aq_appr_{r['question_id']}"] = True
        st.rerun()
    selected = [r for r in view if st.session_state.get(f"aq_appr_{r['question_id']}")]
    confirm = st.checkbox(f"I reviewed the {len(selected)} selected row(s)", key="aq_confirm")
    if st.button(f"Approve {len(selected)} selected", type="primary",
                 disabled=(not selected or not confirm)):
        corrections = {}
        for r in selected:
            corr_to = st.session_state.get(f"aq_corr_{r['question_id']}") or ""
            if corr_to and corr_to != r["primary_topic_id"]:
                corrections[r["question_id"]] = {"primary_topic_id": corr_to}
        result = rv.approve_batch(session, [r["question_id"] for r in selected],
                                  reviewer=REVIEWER, corrections=corrections,
                                  note="approve queue")
        session.commit()
        for r in selected:
            st.session_state.pop(f"aq_appr_{r['question_id']}", None)
            st.session_state.pop(f"aq_corr_{r['question_id']}", None)
        st.session_state["_aq_flash"] = (f"approved {result['approved']} "
                   f"(with {result['corrected']} corrections, "
                   f"{result['skipped_unclassified']} skipped unclassified, "
                   f"{result['blocked_no_passing_rubric']} NOT approved because they have no passing review checks - "
                   "score them in the Review Workspace first)")
        st.rerun()
    if st.session_state.get("_aq_flash"):
        st.info(st.session_state.pop("_aq_flash"))

elif page == "LLM Classify":
    page_header("LLM Classify")
    st.info("**You do not need this page to review.** Every question already has a label. Come here to (a) check "
            "that FreeLLMAPI is ready, (b) compare a fresh model run with the existing labels (writes nothing), "
            "(c) re-label questions, or (d) set up the paid decision models. Nothing leaves this machine unless the "
            "consent settings in `.env` allow it.", icon=":material/lightbulb:")

    def _show_err(err, prefix: str = ""):
        """Plain-language error: what happened + the fix. Consent-gate / setup messages (which already
        say what to do) are shown as written instead of being mislabelled 'provider failed'."""
        msg = str(err)
        if any(t in msg for t in ("GATE_LLM_", "allow_spend", "no provider", ".env", "taxonomy")):
            st.error(prefix + msg)
            return
        ex = cl.explain_provider_error(msg)
        st.error(f"{prefix}{ex['what']}  \n**Fix:** {ex['fix']}  \nRaw message: `{ex['raw']}`")

    _tab_st, _tab_run, _tab_cmp, _tab_dec = st.tabs(["1 · Status & setup", "2 · Classify (writes labels)",
                                                     "3 · Compare (no writes)", "4 · Decision models (paid)"])
    with _tab_st:
        _st_rows = cl.provider_status()
        _hist = cl.provider_history(session)
        _ext = settings.external_calls_allowed()
        for _r in _st_rows:
            _name = _r["provider"]
            _r["tier"] = cl.TIER_LABELS.get(_r["tier"], _r["tier"])
            if not _r["key_set"]:
                _r["gate_state"] = "no key"
            else:
                try:
                    _why = cl.gate_status(cl.get_provider(_name), False, _ext)
                    _r["gate_state"] = "ready (free consent given)" if _why is None else "blocked: " + _why[:70]
                except Exception as _e:  # noqa: BLE001 - e.g. a required *_MODEL is not set
                    _r["gate_state"] = "blocked: " + str(_e)[:70]
            _h = _hist.get(_name, {})
            _r["calls_ok"] = _h.get("successes", 0)
            _r["calls_failed"] = _h.get("errors", 0)
            _r["last_success"] = str(_h["last_success_at"])[:19] if _h.get("last_success_at") else "never"
            _r["last_error"] = (_h.get("last_error") or "")[:60]
        _runnable, _skipped = cl.runnable_providers(False, settings.external_calls_allowed())
        with st.container(horizontal=True):
            st.metric("Runnable now", ", ".join(_runnable) or "none", border=True,
                      help="keys + consents present, no spend needed")
            st.metric("Priority order", ", ".join(cl.priority_list()), border=True, help="GATE_LLM_PRIORITY")
            st.metric("External calls", "allowed" if _ext else "off", border=True, help="GATE_LLM_ALLOW_EXTERNAL")
            st.metric("Free-plan statement", "given" if settings.free_plan_confirmed() else "not given", border=True,
                      help="GATE_LLM_FREE_PLAN_CONFIRMED")
        st.caption("Secrets are never shown - only whether a key is set. calls_ok / calls_failed are RECORDED attempts; "
                   "a set key alone does not prove calls work.")
        _cols = ["provider", "key_set", "gate_state", "calls_ok", "calls_failed", "last_success", "last_error", "tier", "key_env"]
        st.dataframe(pd.DataFrame(_st_rows)[_cols], width="stretch", hide_index=True)
        for _name, _h in _hist.items():
            if _h.get("last_error"):
                _show_err(_h["last_error"], prefix=f"**{_name}** last failed at {str(_h['last_error_at'])[:19]}: ")
        if _skipped:
            with st.expander("Why the other providers are skipped"):
                for _n, _why in _skipped.items():
                    st.write(f"- `{_n}`: {_why}")
        with how_to_read("How keys and consent gates work"):
            st.markdown(
                "Keys live in `.env` (save them with `python -m src.cli set-key <provider>`). With "
                "`GATE_LLM_ROUTER_ONLY=1` every chat call goes through the local FreeLLMAPI router with its one "
                "unified key. **Gates:** any external call needs `GATE_LLM_ALLOW_EXTERNAL=1` (question text leaves "
                "this machine); billing-dependent providers also need `GATE_LLM_FREE_PLAN_CONFIRMED=1` or per-run "
                "spend approval; paid providers always need explicit spend approval per run. Mock works offline.")

    with _tab_run:
        _p1, _p2, _p3 = st.columns(3)
        est_paper = _p1.selectbox("Paper scope", ["(all)"] + [p for p in session.scalars(select(Paper.id))])
        price_in = _p2.number_input("Input USD per 1M tokens", 0.0, 1000.0, 0.0)
        price_out = _p3.number_input("Output USD per 1M tokens", 0.0, 1000.0, 0.0)
        _scope = None if est_paper == "(all)" else est_paper
        st.markdown("**Step 1 - measure first (offline)**")
        if st.button("Estimate cost"):
            st.json(cl.estimate_cost(session, _scope, price_in, price_out))
        st.markdown("**Step 2 - dry run: the exact payloads, no network**")
        d1, d2 = st.columns([3, 1], vertical_alignment="bottom")
        dry_provider = d1.selectbox("Provider", ["mock", "auto", "free", "freellmapi", "gemini", "groq",
                                                 "openrouter", "anthropic", "openai"])
        if d2.button("Dry run"):
            try:
                prov = cl.get_provider(dry_provider)
                st.json(cl.run_classification(session, prov, "gate-cs-2027", _scope, dry_run=True))
            except (RuntimeError, KeyError) as e:
                session.rollback()
                _show_err(e)
        st.markdown("**Step 3 - classify**")
        _in_scope = session.scalar(select(func.count()).select_from(Question)
                                   .where(Question.paper_id == _scope) if _scope else select(func.count()).select_from(Question))
        _have = session.scalar(select(func.count(func.distinct(Classification.question_id))).join(
            Question, Question.id == Classification.question_id).where(*([Question.paper_id == _scope] if _scope else [])))
        reclass = st.checkbox(
            "Replace existing UNVERIFIED suggestions (audited). Off = questions that already have a suggestion are left "
            "alone, so no question can end up with two classifications.", value=False)
        st.caption(f"Scope: {_in_scope} questions, of which {_have} already have a label "
                   f"-> {'they will be REPLACED unless a human verified them' if reclass else 'they will be skipped'}; "
                   f"human-verified rows are never touched either way.")
        consent_external = st.checkbox(
            "I approve sending question text to external providers for this run "
            "(requires GATE_LLM_ALLOW_EXTERNAL=1 in .env; gemini/groq additionally need "
            "GATE_LLM_FREE_PLAN_CONFIRMED=1 unless paid spend is approved)")
        consent_paid = st.checkbox("I approve PAID provider spend for this run")
        r1, r2 = st.columns(2)
        if r1.button("Run mock classification (offline, placeholder output)"):
            stats = cl.run_classification(session, cl.get_provider("mock"), "gate-cs-2027", _scope, reclassify=reclass)
            session.commit()
            st.warning("Mock output is placeholder plumbing - every row still needs human review.")
            st.json(stats)
        if r2.button("Run auto (tries providers in priority order, bounded failover)"):
            try:
                stats = cl.run_auto_classification(
                    session, "gate-cs-2027", _scope, allow_spend=consent_paid,
                    allow_external=consent_external and settings.external_calls_allowed(), reclassify=reclass)
                session.commit()
                st.json(stats)
            except (RuntimeError, KeyError) as e:
                session.rollback()
                _show_err(e)
        ens_names, ens_skipped = cl.runnable_providers(
            consent_paid, consent_external and settings.external_calls_allowed(), free_only=not consent_paid)
        if st.button(f"Run ensemble ({'+'.join(ens_names) if ens_names else 'none runnable'})",
                     disabled=not ens_names):
            try:
                provs = [cl.get_provider(n) for n in ens_names]
                stats = cl.run_ensemble(
                    session, provs, "gate-cs-2027", _scope, allow_spend=consent_paid,
                    allow_external=consent_external and settings.external_calls_allowed(), reclassify=reclass)
                session.commit()
                st.json(stats)
            except (RuntimeError, KeyError) as e:
                session.rollback()
                _show_err(e)
        if ens_skipped:
            st.caption("Ensemble skips: " + "; ".join(f"{n} ({w[:80]})" for n, w in ens_skipped.items()))
        dist = pd.DataFrame(session.execute(
            select(Classification.combo_score, Classification.status)).fetchall(), columns=["combo_score", "status"])
        if len(dist):
            with st.expander("Combined score by label status", icon=":material/bar_chart:"):
                _d = dist.dropna().groupby("status")["combo_score"].agg(["count", "mean"]).reset_index()
                _d.columns = ["status", "labels", "mean combined score"]
                st.dataframe(_d, hide_index=True, width="stretch",
                             column_config={"mean combined score": st.column_config.ProgressColumn(
                                 format="%.2f", min_value=0.0, max_value=1.0)})

    with _tab_cmp:
        st.caption("Runs ONE provider on a small sample of already-labelled questions and shows how often it picks the "
                   "same section/topic. This is AGREEMENT, not accuracy - the existing labels are unverified until a "
                   "human verifies them. Uses the consent boxes on the Classify tab. Writes nothing.")
        cc1, cc2, cc3 = st.columns([2, 2, 1], vertical_alignment="bottom")
        cmp_provider = cc1.selectbox("Provider to test", ["freellmapi", "gemini", "groq", "openrouter", "anthropic", "openai"], key="cmp_prov")
        cmp_sample = cc2.slider("Sample (fraction)", 0.05, 1.0, 0.08, 0.01, key="cmp_sample")
        if cc3.button("Compare (no writes)", key="cmp_go"):
            try:
                _res = cl.compare_with_existing(session, cl.get_provider(cmp_provider), "gate-cs-2027", _scope,
                                                cmp_sample, allow_spend=consent_paid,
                                                allow_external=consent_external and settings.external_calls_allowed())
                session.rollback()
                st.json({k: v for k, v in _res.items() if k != "rows"})
                st.dataframe(pd.DataFrame(_res["rows"]), width="stretch", hide_index=True)
            except Exception as e:  # noqa: BLE001
                session.rollback()
                _show_err(e)

    with _tab_dec:
        st.markdown("**Decision models** answer one typed question - *which syllabus topic is this?* - with a "
                    "calibrated probability instead of free text. They are a cheap, independent second opinion. "
                    "They are **paid**, kept **separate from FreeLLMAPI**, and **off by default**. Their answers go "
                    "only to the second-opinion table (Second Opinions screen), never to the labels and never gold.")
        _ds = op.decision_status()
        st.dataframe(pd.DataFrame(_ds), hide_index=True, width="stretch")
        from src.classification import decision_models as _dm
        from src.db.models import BenchmarkSample as _BS
        _bq = [session.get(Question, i) for i in sorted(session.scalars(select(_BS.question_id)))]
        if _bq:
            _est = [{"provider": n, **{k: v for k, v in _dm.estimate(session, sp, _bq).items() if k != "note"}}
                    for n, sp in _dm.SPECS.items()]
            st.caption(f"Estimated cost for the {len(_bq)}-question benchmark (from character counts):")
            st.dataframe(pd.DataFrame(_est), hide_index=True, width="stretch")
        _ready = [d["provider"] for d in _ds if d["key_set"] and d["enabled (DECISIONS_ENABLED)"]]
        (st.success if _ready else st.warning)(
            f"Ready for a real run: {', '.join(_ready)}" if _ready else
            "Not ready: add a key and set DECISIONS_ENABLED=1 in .env (steps below).")
        st.markdown("**Setup (once)**")
        st.code("python -m src.cli set-key jev                 # TypeSafe key, hidden prompt\n"
                "python -m src.cli set-key openai-decisions    # OpenAI key, hidden prompt\n"
                "# then in .env:  DECISIONS_ENABLED=1", language="bash")
        st.markdown("**Run (after you verified the benchmark)** - dry run first, it prints the payload and cost:")
        st.code("python -m src.cli decisions jev --benchmark                                  # dry run, free\n"
                "python -m src.cli decisions jev --benchmark --yes --allow-spend --max-calls 120\n"
                "python -m src.cli evaluate-benchmark --provider jev                          # score vs your gold",
                language="bash")
        st.caption("Details: docs/23_LLM_ROUTER_AND_DECISION_MODELS.md")

elif page == "About the Data":
    render_data_inventory(session)

else:  # Glossary & Syllabus
    page_header("Glossary & Syllabus")
    import hashlib as _hl
    import yaml as _yaml
    _tax = _yaml.safe_load((APP_ROOT / "taxonomy.yaml").read_text(encoding="utf-8"))
    st.subheader("Statuses and terms", divider="gray")
    st.markdown(status_guide_md(session))
    st.subheader("Where the syllabus comes from", divider="gray")
    _src_rows = []
    for _lab, _pk, _hk in [("CS syllabus 2027 (official PDF)", "source_pdf", "source_sha256"),
                           ("General Aptitude syllabus 2027 (official PDF)", "ga_source_pdf", "ga_source_sha256")]:
        _rel = _tax.get(_pk)
        if not _rel:
            continue
        _f = APP_ROOT / _rel
        _ok = None
        if _f.exists() and _tax.get(_hk):
            _ok = _hl.sha256(_f.read_bytes()).hexdigest() == _tax[_hk]
        _src_rows.append({"source": _lab, "path (in this project)": _rel, "on disk": _f.exists(),
                          "checksum matches": _ok, "sha256": (_tax.get(_hk) or "")[:16] + "..."})
    _src_rows.append({"source": "Codes, names, topics, concepts (curated)", "path (in this project)": "taxonomy.yaml",
                      "on disk": (APP_ROOT / "taxonomy.yaml").exists(), "checksum matches": None, "sha256": "-"})
    st.dataframe(pd.DataFrame(_src_rows), hide_index=True, width="stretch")
    st.caption(f"Full folder: `{APP_ROOT / 'data' / 'raw' / 'syllabus'}`. Which papers and years are loaded: see "
               "the About the Data screen.")
    with how_to_read("How to read the provenance column"):
        st.markdown(
            "- **official** - section text copied verbatim from the GATE 2027 syllabus PDFs above.\n"
            "- **inferred** - topics and concepts are our curated split of that official text, pending review.\n"
            "- **historical** - the LEGACY section (pre-2016 software engineering), not part of GATE 2027.\n"
            "- Prerequisite edges used elsewhere in the app are curated, never official.")

    st.subheader("Sections", divider="gray")
    st.caption("The top-level subjects. Open one for its verbatim syllabus text.")
    _secs_df = pd.DataFrame(GLOSSARY["sections"])
    st.dataframe(_secs_df[["Code", "Full name", "Provenance"]], hide_index=True, width="stretch")
    for _s in GLOSSARY["sections"]:
        with st.expander(f"{_s['Full name']}  ({_s['Code']})"):
            st.markdown(_s["What it covers (official syllabus text, verbatim)"] or "-")
            st.caption(_s["Provenance"])

    st.subheader("Topics", divider="gray")
    st.caption("The second level, e.g. ALGO.SORT = Searching, sorting, hashing.")
    _tsec = st.selectbox("Show topics of", ["(all)"] + [s["Code"] for s in GLOSSARY["sections"]],
                         format_func=lambda x: x if x == "(all)" else
                         next(f"{s['Full name']}  ({s['Code']})" for s in GLOSSARY["sections"] if s["Code"] == x),
                         key="gl_sec")
    _tdf = pd.DataFrame(GLOSSARY["topics"])
    if _tsec != "(all)":
        _tdf = _tdf[_tdf["Full code"].str.startswith(_tsec + ".")]
    st.dataframe(_tdf, hide_index=True, width="stretch")
    st.subheader("Concepts", divider="gray")
    st.caption("The finest level, e.g. ALGO.SORT.HASH.")
    _cdf = pd.DataFrame(GLOSSARY["concepts"])
    if _tsec != "(all)":
        _cdf = _cdf[_cdf["Full code"].str.startswith(_tsec + ".")]
    st.dataframe(_cdf, hide_index=True, width="stretch")
    if GLOSSARY["structure_notes"]:
        with st.expander("Structure notes", icon=":material/notes:"):
            for n in GLOSSARY["structure_notes"]:
                st.write("- " + n)
