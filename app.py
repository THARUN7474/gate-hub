"""GATE CSE Intelligence - Phase 1 local app.
Run: streamlit run app.py   (DB from GATE_DB_URL / .env; see docs/06_SETUP.md)

Screens: Pipeline Status, Question Browser, Analysis Matrix (clickable cells),
Topic Report, Review Workspace (original PDF crop beside the AI suggestion,
one-click Verify / Flag / correct-from-dropdown / Approve & next), Approve
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
from src.analytics import analyze as az, links as nav, search as srch
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

st.set_page_config(page_title="GATE CSE Intelligence (local)", layout="wide")
st.title("GATE CSE Intelligence - Phase 1 (local)")
st.caption("All figures computed live from question records. Historical description only - "
           "not a prediction for GATE 2027.")

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
    st.subheader("About the Data - which GATE CS papers exist and how they are stored")
    st.caption("Computed live from manifests/papers.yaml, the files in data/raw and this database. A 'paper' = one exam "
               "session (65 questions, 100 marks). One PDF can hold several sessions.")
    inv = _inv.inventory(session)
    T = inv["totals"]
    m = st.columns(5)
    m[0].metric("Years 2007-2026", T["years"])
    m[1].metric("Papers (sessions) registered", T["papers"], help="including the 4 deferred 2007-2010 papers")
    m[2].metric("Active papers 2011-2026", T["active_papers"], help=f"{T['deferred_papers']} deferred (2007-2010)")
    m[3].metric("Question PDFs / key PDFs", f"{T['question_pdfs']} / {T['key_pdfs']}")
    m[4].metric("Papers with an official key", f"{T['active_with_key']} of {T['active_papers']}",
                help=f"{T['active_without_key']} have no key file (listed as missing, never guessed)")
    _in_db = T["questions_in_db"]
    (st.success if _in_db >= T["expected_questions_active"] else st.warning)(
        f"This database holds {_in_db:,} of the {T['expected_questions_active']:,} questions of the {T['active_papers']} active papers"
        + ("." if _in_db >= T["expected_questions_active"] else
           " - the rest are prepared and come in with the promotion (promote.cmd)."))
    st.markdown("**Three groups of years**")
    st.dataframe(pd.DataFrame(inv["groups"]), hide_index=True, width="stretch")
    st.markdown("**Year by year** - how many papers each year has, in which PDF(s), and where the key comes from")
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

def _ai_reviews(session, qid):
    """AI-review verdicts for one question (review_events field='ai_review', written by
    scripts/ai_review.py). Opinions only - never human verification, never gold."""
    out = []
    for e in session.scalars(select(ReviewEvent).where(ReviewEvent.question_id == qid,
                                                        ReviewEvent.field == "ai_review").order_by(ReviewEvent.id)):
        try:
            d = json.loads(e.after or "{}")
        except ValueError:
            d = {}
        out.append({"reviewer": e.reviewer, "when": str(e.created_at)[:16], "verdict": d.get("verdict"),
                    "section_id": d.get("section_id"), "primary_topic_id": d.get("primary_topic_id"),
                    "confidence": d.get("confidence"), "note": d.get("note")})
    return out

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
           "Subject Overview", "Review Workspace", "Approve Queue", "LLM Classify", "Glossary & Syllabus"]
page = st.sidebar.radio("Screen", SCREENS, key="screen")
# Every human decision is written to the audit log under this name (default: GATE_REVIEWER or "owner").
REVIEWER = st.sidebar.text_input("Reviewer name (audit log)", value=os.environ.get("GATE_REVIEWER", "owner"),
                                 key="reviewer_name").strip() or "owner"
st.sidebar.caption("Keyboard in the Review Workspace: **Ctrl+Enter** approve & next, **Alt+N** skip, "
                   "**Alt+V** verify as-is, **Alt+X** flag.")

if page == "Pipeline Status":
    cov = az.coverage_report(session)
    c = st.columns(6)
    for col, (label, key) in zip(c, [("Papers", "papers"), ("Questions", "questions"),
                                     ("With keys", "with_keys"), ("Classified", "classified"),
                                     ("Verified", "verified_by_human"), ("Pending review", "pending_review")]):
        col.metric(label, cov[key])
    st.caption(f"Pending review = every question without a human-verified classification "
               f"(extraction issues: {cov['of_which_extraction_issues']}, unclassified: "
               f"{cov['of_which_unclassified']}, flagged/unverified suggestions: "
               f"{cov['flagged'] + max(cov['classified'] - cov['verified_by_human'] - cov['flagged'], 0)}).")
    from sqlalchemy import select as _sel
    from src.db.models import Classification as _Cls
    _pairs = session.execute(_sel(_Cls.model, _Cls.status).where(_Cls.status != "verified")).all()
    _agg = {}
    for _m, _st in _pairs:
        _d = _agg.setdefault(_m or "unknown", {"suggested": 0, "flagged": 0})
        _d[_st if _st in ("suggested", "flagged") else "suggested"] += 1
    if _agg:
        st.caption("Unverified suggestions by model: " + "; ".join(
            f"{m} ({d['suggested']} suggested, {d['flagged']} flagged)" for m, d in sorted(_agg.items()))
            + " - all machine suggestions, none verified until a human approves them.")
    from src.classification.classify import proposal_agreement as _pagree
    _prow = _pagree(session)
    if _prow:
        st.caption("Independent provider proposals (classification_proposals table - a separate second "
                   "opinion that NEVER overwrites the labels above; 'fills_unclassified' covers questions "
                   "with no label at all):")
        st.dataframe(pd.DataFrame(_prow), width="stretch", hide_index=True)
    st.subheader("Papers")
    ptab = az.paper_status_table(session)
    _pcols = ["paper", "year", "session", "questions", "marks", "reconciled", "official_keys", "text_source",
              "needs_review", "classified", "verified", "set"]
    st.dataframe(pd.DataFrame(ptab)[_pcols], width="stretch", hide_index=True)
    n_ocr = sum(1 for r in ptab if r["text_source"] != "digital")
    nokey = [r["paper"].replace("GATE-CS-", "") for r in ptab if r["official_keys"] == 0]
    st.caption(f"{len(ptab)} papers. **text_source**: 'digital' = exact PDF text; 'OCR' = read from scanned pages "
               f"({n_ocr} papers) - OCR text can contain errors in formulas, the source region shown in the Review "
               f"Workspace is always the truth. **official_keys**: {len(nokey)} papers have no key "
               f"({', '.join(nokey) or 'none'}): listed as missing, never guessed. Papers 2007-2010 are photographed "
               f"scans, deferred.")
    _gap = list(session.scalars(select(ReviewEvent.question_id).where(
        ReviewEvent.field == "taxonomy_gap").distinct()))
    if _gap:
        with st.expander(f"Taxonomy gap: {len(_gap)} questions left UNCLASSIFIED (no software-engineering topic "
                         "in the taxonomy) - not counted as classified anywhere"):
            st.caption("These are software-engineering questions (testing, COCOMO, SRS, cohesion/coupling, "
                       "estimation). They were deliberately NOT forced into the programming topic. Decide: "
                       "extend the taxonomy or leave unclassified.")
            for _g in _gap:
                _gq = session.get(Question, _g)
                st.markdown(f"- **{_g}** ({_gq.paper_id if _gq else ''}, "
                            f"{(_gq.text or '')[:110]}...)" if _gq else f"- {_g}")
    if cov["unreconciled_papers"]:
        st.warning("Unreconciled papers: " + ", ".join(cov["unreconciled_papers"]))
    st.caption(cov["note"])
    with st.expander("Back up the database"):
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
    years = [r for r in session.scalars(select(Paper.year).distinct().order_by(Paper.year))]
    sections = [r for r in session.scalars(
        select(TaxonomyNode.node_id).where(TaxonomyNode.level == "section"))]
    _, _tbs, _, _names = taxonomy_maps(session)
    c1, c2, c3, c4 = st.columns(4)
    f_sec = c1.selectbox("Section", ["(all)"] + sections,
                     help="Short codes. Full names and what each covers: hover the codes below the results, or open the Glossary & Syllabus screen.")
    _topic_opts = sorted(_tbs.get(f_sec, [])) if f_sec != "(all)" else sorted({t for v in _tbs.values() for t in v})
    f_topic = c2.selectbox("Topic", ["(all)"] + _topic_opts)
    f_years = c3.multiselect("Years", years, default=years)
    f_type = c4.selectbox("Type", ["(all)", "MCQ", "MSQ", "NAT"])
    c5, c6 = st.columns(2)
    f_rev = c5.selectbox("Review", ["(all)", "needs review", "ok"])
    f_status = c6.selectbox("Classification status", ["(all)", "suggested", "flagged", "verified", "unclassified"],
                            help="suggested/flagged are machine proposals awaiting human review; "
                                 "verified = a human approved it; unclassified = no row yet (includes taxonomy gaps).")
    q_text = st.text_input("Search question text")
    if f_status == "unclassified":
        rows = srch.search_questions(
            session, text_query=q_text or None, years=f_years or None,
            q_type=None if f_type == "(all)" else f_type,
            needs_review={"(all)": None, "needs review": True, "ok": False}[f_rev])
        rows = [r for r in rows if not r.get("primary_topic_id")]
    else:
        rows = srch.search_questions(
            session, text_query=q_text or None, years=f_years or None,
            section_id=None if f_sec == "(all)" else f_sec,
            topic_id=None if f_topic == "(all)" else f_topic,
            q_type=None if f_type == "(all)" else f_type,
            needs_review={"(all)": None, "needs review": True, "ok": False}[f_rev],
            status=None if f_status == "(all)" else f_status)
    _, _tbn, _, _bnames = taxonomy_maps(session)
    for r in rows:
        r["section"] = _bnames.get(r.get("section_id") or "", r.get("section_id") or "")
        r["topic"] = _bnames.get(r.get("primary_topic_id") or "", r.get("primary_topic_id") or "")
        if not r.get("primary_topic_id"):
            r["status"] = "unclassified (taxonomy gap)" if r.get("status") is None else r["status"]
    st.session_state["browser_grid_ids"] = [r["id"] for r in rows]

    def _jump_from_grid():
        sel_rows = st.session_state["browser_grid"].selection.rows
        ids = st.session_state.get("browser_grid_ids", [])
        if sel_rows and sel_rows[0] < len(ids):
            st.session_state["_pending_screen"] = "Review Workspace"
            st.session_state["review_pick"] = ids[sel_rows[0]]
            st.session_state.pop("browser_grid", None)

    _bcols = ["id", "year", "session", "q_number", "marks", "q_type", "section", "topic",
              "status", "confidence", "needs_review"]
    st.dataframe(pd.DataFrame(rows)[[c for c in _bcols if rows and c in rows[0]]], width="stretch",
                 on_select=_jump_from_grid, selection_mode="single-row",
                 key="browser_grid")
    code_explainer(sorted({r["section_id"] for r in rows if r.get("section_id")}
                          | {r["primary_topic_id"] for r in rows if r.get("primary_topic_id")}))
    st.caption("Click a table row to open that question in the Review Workspace.")
    def _jump_from_fallback():
        pick = st.session_state.get("browser_fallback_pick", "-")
        if pick != "-":
            st.session_state["_pending_screen"] = "Review Workspace"
            st.session_state["review_pick"] = pick

    j1, j2 = st.columns([3, 1])
    j1.selectbox("Fallback: choose a question if row-click is unavailable",
                 ["-"] + [r["id"] for r in rows], key="browser_fallback_pick")
    j2.button("Open in Review Workspace", on_click=_jump_from_fallback)

elif page == "Analysis Matrix":
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
    if m["years"]:
        st.caption("Classified papers per year: " + ", ".join(f"{y}: {_ppy.get(y, 0)}" for y in m["years"]))
    drill = st.session_state.pop("drill", None)
    if drill:
        d_sec, d_year = drill
        _kind = st.session_state.pop("drill_kind", "section")
        st.subheader(f"Drill down: {d_sec} in {d_year}")
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
        st.markdown("**Section x Year (marks, primary topic only)** - every number is "
                    "**clickable** and opens that cell's contributing questions. Totals "
                    "always reconcile to paper totals. Only classified questions are included: "
                    f"**{_n_cls} of {_tot_q} questions** "
                    f"({_stat_counts.get('verified', 0)} verified, {_stat_counts.get('suggested', 0)} suggested, "
                    f"{_stat_counts.get('flagged', 0)} flagged - all machine suggestions until a human verifies them; "
                    f"{_tot_q - _n_cls} unclassified, the software-engineering taxonomy gap listed on Pipeline Status).")
        st.markdown(nav.matrix_html(m), unsafe_allow_html=True)
        code_explainer(list(m["sections"].keys()))
        st.subheader("Drill down (fallback dropdowns)")
        d1, d2 = st.columns(2)
        d_sec = d1.selectbox("Cell section", list(m["sections"].keys()) or ["-"])
        d_year = d2.selectbox("Cell year", m["years"] or ["-"])
        if d_sec != "-" and d_year != "-":
            st.write(az.drill_down(session, d_sec, d_year))
    st.subheader("Type / marks mix")
    st.dataframe(pd.DataFrame(az.type_marks_mix(session, yf, yt)), width="stretch")
    st.subheader("Topic x Year (marks)")
    _secs, _tbs2, _, _names2 = taxonomy_maps(session)
    t_sec = st.selectbox("Section for topic matrix", _secs, key="topic_matrix_sec")
    t_rows = az.topic_year_matrix(session, t_sec, yf, yt)
    if t_rows:
        st.caption("Every number is clickable and opens that cell's contributing questions (counts are "
                   "machine suggestions until verified).")
        st.markdown(nav.topic_matrix_html(t_rows, _names2), unsafe_allow_html=True)
        code_explainer(sorted({r["topic"] for r in t_rows}))
    else:
        st.caption("No classified questions for this section in the selected years.")

elif page == "Topic Report":
    st.caption("Only classified questions are included; papers not yet classified are excluded (see Pipeline Status).")
    st.markdown("**Score-first priority** (historical marks share, recency-weighted x1.5 for recent years; "
                "descriptive, not predictive. Prerequisite edges exist but are curated/inferred, "
                "not official syllabus relationships - see exports/prerequisite_edges.csv provenance.)")
    pr = az.priority_ranking(session)
    st.dataframe(pd.DataFrame(pr), width="stretch")
    code_explainer([r["topic"] for r in pr])
    st.subheader("Drill into a topic")
    _t = st.selectbox("Topic", [r["topic"] for r in pr], key="tr_topic")
    _q = (select(Question.id, Paper.year, Question.q_number, Classification.status)
          .join(Paper, Paper.id == Question.paper_id)
          .join(Classification, Classification.question_id == Question.id)
          .where(Classification.primary_topic_id == _t)
          .order_by(Paper.year, Question.q_number))
    _rows = [{"question": qid, "year": y, "q#": n, "status": st_} for qid, y, n, st_ in session.execute(_q)]
    st.caption(f"{len(_rows)} questions classified as {_t} "
               f"({sum(1 for r in _rows if r['status'] == 'verified')} verified, "
               f"{sum(1 for r in _rows if r['status'] == 'suggested')} suggested, "
               f"{sum(1 for r in _rows if r['status'] == 'flagged')} flagged). Click one to open it.")
    st.dataframe(pd.DataFrame(_rows), width="stretch", hide_index=True)
    st.markdown(nav.drill_list_html([r["question"] for r in _rows]), unsafe_allow_html=True)

elif page == "Subject Overview":
    st.subheader("Subject Overview - main topics, what they test, prerequisites")
    st.caption("Topics, concepts and prerequisite edges come from taxonomy.yaml (curated, not official "
               "syllabus relationships). Question counts are machine suggestions until a human verifies them.")
    _secs3, _tbs3, _cbt3, _names3 = taxonomy_maps(session)
    ov_sec = st.selectbox("Subject", _secs3, key="ov_sec",
                          format_func=lambda x: f"{x} - {_names3.get(x, '')}")
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
    code_explainer(list(_tbs3.get(ov_sec, [])))
    st.markdown("**Per-topic detail** (concepts with readable names, and what classified questions test):")
    for t in _tbs3.get(ov_sec, []):
        with st.expander(f"{t} - {_names3.get(t, '')}"):
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
    st.markdown("**Prerequisite edges in this subject** (curated/inferred - not official syllabus relationships):")
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
    st.subheader("Review Workspace")
    _flash_msg = st.session_state.pop("_flash", None)
    if _flash_msg:
        st.success(_flash_msg)
    counts = rv.review_counts(session)
    prog_all = rv.verification_progress(session)
    st.progress(prog_all["verified"] / prog_all["classified"] if prog_all["classified"] else 0.0,
                text=f"{prog_all['verified']} of {prog_all['classified']} classified questions verified by a human "
                     f"({prog_all['unclassified']} of {prog_all['total_questions']} loaded questions have no classification yet)")
    st.caption(f"Awaiting a decision: extraction issues {counts['of_which_extraction_issues']}, "
               f"classifier-flagged {counts['of_which_classifier_flagged']}, "
               f"unverified suggestions {counts['of_which_unverified_suggestions']}, "
               f"unclassified {counts['of_which_unclassified']} - reviewing as **{REVIEWER}**.")
    pre = st.session_state.pop("review_pick", None)
    if pre:
        _pq = session.get(Question, pre)
        if _pq is not None:
            # a deep link drives BOTH filters: the paper dropdown follows the linked question,
            # so the displayed paper can never disagree with the displayed question
            st.session_state["rw_paper"] = _pq.paper_id
    _paper_ids = [r for r in session.scalars(select(Paper.id).order_by(Paper.year, Paper.session))]
    f1, f2, f3 = st.columns([2, 3, 2])
    f_paper = f1.selectbox("Paper", ["(all papers)"] + _paper_ids, key="rw_paper")
    f_show = f2.radio("Show", ["all questions", "suggestion awaiting my decision", "verified",
                               "no classification yet", "benchmark sample (gold review)"],
                      horizontal=True, key="rw_show")
    f_order = f3.radio("Order", ["paper order", "review priority first"], horizontal=True, key="rw_order")
    _q = select(Question.id, Question.printed_label).order_by(Question.paper_id, Question.q_number)
    if f_paper != "(all papers)":
        _q = _q.where(Question.paper_id == f_paper)
    _rows = session.execute(_q).all()
    _label = {i: (pl or "") for i, pl in _rows}
    all_ids = [i for i, _ in _rows]
    from src.validation import benchmark as _bm
    _sample = _bm.sample_membership(session)
    if f_show == "benchmark sample (gold review)":
        all_ids = [i for i in all_ids if _sample.get(i, (None, ""))[1] == "pending_user_review"]
        st.caption(f"Benchmark sample: {sum(1 for v in _sample.values() if v[1] == 'gold_verified')} of "
                   f"{len(_sample)} sampled questions have your verified gold. Verifying a sampled question "
                   f"here records your decision as its benchmark gold - nothing is auto-approved.")
    elif f_show != "all questions":
        _await = {r["question_id"] for r in rv.review_queue(session, classified_only=True)}
        _cls_ids = set(session.scalars(select(Classification.question_id)))
        _ver = set(session.scalars(select(Classification.question_id).where(Classification.status == "verified")))
        all_ids = [i for i in all_ids if (i in _await if f_show.startswith("suggestion")
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
        _pp = rv.verification_progress(session, qu.paper_id)
        st.caption(f"This paper: {_pp['verified']} of {_pp['classified']} classified questions verified"
                   f" ({_pp['unclassified']} unclassified) - printed in the paper as **{qu.printed_label or 'Q ' + str(qu.q_number)}**")
        if uid in _sample:
            _b, _st = _sample[uid]
            st.caption(f"In benchmark sample **{_b}** ({_st.replace('_', ' ')})"
                       + (" - verifying records your label as its gold" if _st == "pending_user_review" else ""))
        if _prio.get(uid):
            st.caption(f"Review priority #{_prio[uid][0]} of {len(_prio)} - bucket: "
                       f"**{_prio[uid][1].replace('_', ' ')}** (why this order: validation.review.PRIORITY_BUCKETS)")
        left, right = st.columns(2)
        with left:
            st.markdown("**Original source** (rendered on demand from the PDF - no stored images)")
            if qu.extraction_status == "ocr":
                st.info("This paper is a scan. The text below was read by OCR and can contain errors, "
                        "especially in formulas - **the image is the original; trust it over the text.**")
            previews, preview_reason = source_previews(session, qu)
            if previews:
                for seg in previews:
                    st.image(seg["png"], caption=f"original PDF, page {seg['page']}")
            elif qu.image_path:
                st.image(qu.image_path, caption=f"legacy stored crop, pages {qu.page_start}-{qu.page_end}")
            else:
                st.info(f"No source preview available - {preview_reason}.")
            st.write(qu.text)
            for o in session.scalars(select(Option).where(Option.question_id == uid)):
                st.write(f"({o.label}) {o.content}")
            if key:
                label = rv.key_provenance_label(session, uid)
                rng = f" [{key.answer_min}-{key.answer_max}]" if key.answer_min is not None else ""
                if label.startswith("Fixture"):
                    st.warning(f"{label} ({key.key_version}): {key.answer_list}{rng}")
                else:
                    st.success(f"{label} ({key.key_version}): {key.answer_list}{rng}")
                if key.notes:
                    st.caption("Key note: " + key.notes)
            else:
                st.caption("No official key is loaded for this paper (listed as missing, never guessed).")
            if qu.review_reason:
                st.warning(qu.review_reason)
            with st.expander("Correct the extraction (text, options, marks, type) - compare with the image above"):
                st.caption("Every change is saved with your name, the old and new value and the time. A corrected "
                           "question is protected: re-loading the PDF never overwrites it.")
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
            st.markdown("**Classification (machine suggestion until verified)**")
            if cls:
                n_prov = cls.provider_count if cls.provider_count is not None else 1
                legacy = any("pre-v6" in str(v.get("provider", ""))
                             for v in (cls.provider_votes or []))
                if legacy:
                    combo_txt = ""
                    combo_note = ("Legacy inferred suggestion - original confidence "
                                  "retained; no ensemble run recorded for this row. "
                                  "Run an ensemble (LLM Classify screen) for a real "
                                  "agreement score.")
                elif n_prov > 1 and cls.agreement is not None:
                    combo_txt = (f"  Combined score: {cls.combo_score:.2f}"
                                 f" (ENSEMBLE: agreement {cls.agreement:.2f} x "
                                 f"mean confidence, {n_prov} providers)")
                    combo_note = ("Ensemble combined score = provider agreement x mean "
                                  "confidence. A review-priority heuristic, not a "
                                  "correctness probability.")
                else:
                    combo_txt = (f"  Score: {(cls.combo_score if cls.combo_score is not None else cls.confidence):.2f}"
                                 f" (single provider - no ensemble agreement)")
                    combo_note = ("Single-provider run: the score equals the model's "
                                  "self-reported confidence. Run an ensemble (LLM "
                                  "Classify screen) for a real agreement score.")
                st.write(f"Section: `{cls.section_id}`  Topic: `{cls.primary_topic_id}`  "
                         f"Confidence: {cls.confidence:.2f}  Status: {cls.status}{combo_txt}")
                st.caption(combo_note)
                st.write("What it tests: " + (cls.what_it_tests or
                         "_not recorded - the v2 first pass is topic-level only; the API proposals pass "
                         "can supply this, or add during review_"))
                st.write("Concepts: " + (", ".join(f"`{c}`" for c in (cls.concept_ids or [])) or "none")
                         + ("  |  Prerequisites: " + ", ".join(f"`{p}`" for p in (cls.prerequisite_ids or []))
                            if cls.prerequisite_ids else ""))
                if cls.provider_votes and len(cls.provider_votes) > 1:
                    with st.expander("Provider votes"):
                        st.json(cls.provider_votes)
                _ai = _ai_reviews(session, uid)
                if _ai:
                    st.markdown("**AI review** - an AI reviewer's opinion, recorded as such. "
                                "It is NOT human verification and never becomes benchmark gold.")
                    for _r in _ai:
                        _txt = (f"`{_r['reviewer']}` ({_r['when']}): **{_r['verdict']}** -> "
                                f"`{_r['section_id']}` / `{_r['primary_topic_id']}`  conf {_r['confidence']}")
                        (st.warning if _r["verdict"] in ("flag", "correct") else st.info)(
                            _txt + (f"  \n{_r['note']}" if _r.get("note") else ""))
                code_explainer([cls.section_id, cls.primary_topic_id]
                               + list(cls.concept_ids or []) + list(cls.prerequisite_ids or []))

                secs, topics_by_sec, concepts_by_topic, names = taxonomy_maps(session)
                st.markdown("**Correct from the dropdowns** (full names in the Glossary screen)")
                cur_sec = cls.section_id if cls.section_id in secs else secs[0]
                new_sec = st.selectbox("Section", secs,
                                       index=secs.index(cur_sec),
                                       format_func=lambda x: f"{x} - {names.get(x, '')}",
                                       key=f"rw_sec_{uid}")
                sec_topics = topics_by_sec.get(new_sec, []) or ["-"]
                cur_topic = cls.primary_topic_id if cls.primary_topic_id in sec_topics else sec_topics[0]
                new_topic = st.selectbox("Topic", sec_topics,
                                         index=sec_topics.index(cur_topic),
                                         format_func=lambda x: f"{x} - {names.get(x, '')}",
                                         key=f"rw_topic_{uid}")
                all_concepts = sorted({c for lst in concepts_by_topic.values() for c in lst})
                cur_concepts = [c for c in (cls.concept_ids or []) if c in all_concepts]
                new_concepts = st.multiselect("Concepts", all_concepts, default=cur_concepts,
                                              format_func=lambda x: f"{x} - {names.get(x, '')}",
                                              key=f"rw_concepts_{uid}")
                all_topics = sorted({t for lst in topics_by_sec.values() for t in lst})
                cur_secondary = [t for t in (cls.topic_weight or {}) if t != cls.primary_topic_id and t in all_topics]
                new_secondary = st.multiselect("Secondary topics (tags only - never counted in marks)",
                                               [t for t in all_topics if t != new_topic], default=[t for t in cur_secondary if t != new_topic],
                                               format_func=lambda x: f"{x} - {names.get(x, '')}", key=f"rw_secondary_{uid}")
                new_wit = st.text_input("What it tests (one sentence)", value=cls.what_it_tests or "", key=f"rw_wit_{uid}")
                note = st.text_input("Note (optional, goes to audit log)", key=f"rw_note_{uid}")

                # ---- five-point rubric: a reviewer's record, not a GATE score and not model confidence ----
                st.markdown("**Review checks** - required before Verify: *Source fidelity* and *Primary topic* must pass")
                _prev = rv.latest_rubric(session, uid) or {}
                scores = {}
                for _k, _lab, _help in rv.RUBRIC:
                    _d = _prev.get(_k)
                    scores[_k] = st.radio(_lab, [1, 0], index=None if _d not in (0, 1) else [1, 0].index(_d),
                                          format_func=lambda v: "pass" if v == 1 else "fail", horizontal=True,
                                          help=_help, key=f"rw_rub_{_k}_{uid}")
                _answered = all(v is not None for v in scores.values())
                st.caption(f"review_quality_score: {sum(v for v in scores.values() if v is not None)}/5"
                           + ("" if _answered else " - not all five checks answered yet")
                           + (f" (last saved by the audit log: {_prev.get('review_quality_score')}/5)" if _prev else ""))
                _scope = rv.approval_scope(session, uid)
                st.caption("Approved so far - classification: " + ("yes" if _scope["classification_verified"] else "no")
                           + " | extraction: " + ("yes" if _scope["extraction_verified"] else "no")
                           + " | official key: " + ("missing (never claimed)" if _scope["key_status"] == "missing"
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

                b1, b2 = st.columns(2)     # two per row: the shortcut hints make three-per-row labels truncate
                if b1.button("Verify as-is", key=f"rw_verify_{uid}", shortcut="Alt+V"):
                    if _verify(f"{uid} verified by {REVIEWER}"):
                        st.rerun()
                if b2.button("Flag", key=f"rw_flag_{uid}", shortcut="Alt+X"):
                    if _answered:
                        _apply_corrections()
                    rv.set_status(session, uid, "flagged", reviewer=REVIEWER, note=note)
                    session.commit(); _flash(f"{uid} flagged"); st.rerun()
                b3, b4 = st.columns(2)
                if b3.button("Save without verifying", key=f"rw_save_{uid}"):
                    if _apply_corrections():
                        session.commit(); _flash(f"{uid}: saved (NOT verified)")
                    else:
                        _flash("no changes to save")
                    st.rerun()
                b5, b6 = st.columns(2)
                if b4.button("Verify with correction", key=f"rw_vwc_{uid}"):
                    if _verify(f"{uid} corrected and verified by {REVIEWER}"):
                        st.rerun()
                if b5.button("Approve & next", key=f"rw_next_{uid}", shortcut="Ctrl+Enter"):
                    nxt = rv.next_pending(session, uid)
                    if nxt == uid:
                        nxt = None                       # it was the last one: nothing left to advance to
                    if _verify(f"{uid} verified by {REVIEWER}; next: {nxt}" if nxt else f"{uid} verified - nothing left awaiting a decision"):
                        if nxt:
                            st.session_state["review_pick"] = nxt
                        st.rerun()
                if b6.button("Skip to next pending", key=f"rw_skip_{uid}", shortcut="Alt+N"):
                    nxt = rv.next_pending(session, uid)
                    if nxt and nxt != uid:
                        st.session_state["review_pick"] = nxt
                    st.rerun()
                # legacy-compatible invisible anchors for the AppTest script:
                st.caption("Actions persist with a full audit trail (ReviewEvent rows).")
            else:
                st.info("This question has no classification yet, so there is nothing to verify. Add suggestions with the "
                        "chat-assisted batch workflow (docs/20_CHAT_ASSISTED_CLASSIFICATION.md - no API key) or the LLM Classify "
                        "screen. You can still read the source, correct the extraction and see the official key on the left.")
                for _r in _ai_reviews(session, uid):
                    st.warning(f"AI review (not human verification) `{_r['reviewer']}`: **{_r['verdict']}**"
                               + (f"  \n{_r['note']}" if _r.get("note") else ""))
        with st.expander("Audit history for this question (every change, oldest first)"):
            _hist = rv.audit_history(session, uid)
            if _hist:
                st.table(pd.DataFrame(_hist))
            else:
                st.caption("No review events yet.")

elif page == "Approve Queue":
    st.subheader("Approve Queue - batch human approval")
    st.caption("Review suggestions row by row, optionally correct the topic from the "
               "dropdown, tick Approve, then apply. Every approval logs a ReviewEvent "
               "(under the reviewer name in the sidebar) exactly like one-by-one verification. Verified records "
               "are never overwritten by later runs. **Only questions that already have a saved review rubric with "
               "Source fidelity and Primary topic passing can be approved here** - an AI suggestion alone is never enough.")
    rows = [r for r in rv.review_queue(session) if r["status"] in ("suggested", "flagged")]
    f1, f2, f3 = st.columns(3)
    min_combo = f1.slider("Minimum combined score", 0.0, 1.0, 0.0, 0.05,
                          help="Heuristic filter: provider agreement x mean confidence.")
    only_flagged = f2.checkbox("Only classifier-flagged", value=False)
    page_size = f3.selectbox("Rows per page", [10, 20, 50], index=0)
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
    st.caption(f"{len(rows)} rows match; sorted by combined score (highest first).")
    pages = max(1, (len(rows) + page_size - 1) // page_size)
    page_no = st.number_input("Page", 1, pages, 1) - 1
    view = rows[page_no * page_size:(page_no + 1) * page_size]
    secs, topics_by_sec, _, names = taxonomy_maps(session)
    all_topics = sorted({t for lst in topics_by_sec.values() for t in lst})
    for r in view:
        qid = r["question_id"]
        with st.container(border=True):
            rc1, rc2, rc3 = st.columns([3, 2, 1])
            combo_v = combo_map.get(qid)
            rc1.markdown(f"**{qid}**  ({r['status']}, {r['q_type']}, {r['marks']:g} marks)  \n"
                         f"suggested `{r['primary_topic_id']}` "
                         f"(conf {r['confidence']:.2f}"
                         + (f", combo {combo_v:.2f}" if combo_v is not None else "") + ")  \n"
                         f"<span style='color:#777; font-size:0.85em'>{r['review_reason']}</span>",
                         unsafe_allow_html=True)
            rc2.selectbox("Correct to (optional)", [""] + all_topics,
                          format_func=lambda x: (f"{x} - {names.get(x, '')}" if x
                                                 else "keep suggestion"),
                          key=f"aq_corr_{qid}", label_visibility="collapsed")
            rc3.checkbox("Approve", key=f"aq_appr_{qid}")
    if st.button("Select all on this page"):
        for r in view:
            st.session_state[f"aq_appr_{r['question_id']}"] = True
        st.rerun()
    selected = [r for r in view if st.session_state.get(f"aq_appr_{r['question_id']}")]
    confirm = st.checkbox(f"I reviewed the {len(selected)} selected row(s)", key="aq_confirm")
    if st.button(f"Approve {len(selected)} selected",
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
                   f"{result['blocked_no_passing_rubric']} NOT approved because they have no passing review rubric - "
                   "score them in the Review Workspace first)")
        st.rerun()
    if st.session_state.get("_aq_flash"):
        st.info(st.session_state.pop("_aq_flash"))
    st.caption("To inspect a question's original PDF crop before approving, open it in "
               "the Review Workspace (clickable from the Analysis Matrix drill-down).")

elif page == "LLM Classify":
    st.subheader("LLM Classify - providers, setup, gated runs")
    st.markdown(
        "Add API keys to `.env` (copy `.env.example`) and everything else is automatic: "
        "`auto` tries providers in your `GATE_LLM_PRIORITY` order with bounded failover "
        "(per-question, recorded, never crossing consent gates). "
        "**Gates:** any external call needs `GATE_LLM_ALLOW_EXTERNAL=1` (question text "
        "leaves this machine). Providers with account-dependent billing (gemini, groq) "
        "additionally need your free-plan attestation (`GATE_LLM_FREE_PLAN_CONFIRMED=1`) "
        "or per-run spend approval; paid providers always need explicit spend approval "
        "per run. Only OpenRouter `:free` models are listed at $0 by the provider itself. "
        "Mock works fully offline.")
    st.markdown("**Provider status** (secrets never shown - only whether a key is set. "
                "A set key does NOT prove a free plan: gemini/groq bill per token when the "
                "account/project has billing linked - confirm your plan, this tool cannot.)")
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
    _cols = ["provider", "key_set", "gate_state", "calls_ok", "calls_failed", "last_success", "last_error", "tier", "key_env"]
    st.dataframe(pd.DataFrame(_st_rows)[_cols], width="stretch", hide_index=True)
    st.caption("`calls_ok` / `calls_failed` / `last_success` come from RECORDED attempts in the database - a key "
               "being set only means a key exists, not that calls work. No live call has been recorded yet if these "
               "are all 0 / never.")
    def _show_err(err, prefix: str = ""):
        """Plain-language error: what happened + the fix. Consent-gate / setup messages (which already
        say what to do) are shown as written instead of being mislabelled 'provider failed'."""
        msg = str(err)
        if any(t in msg for t in ("GATE_LLM_", "allow_spend", "no provider", ".env", "taxonomy")):
            st.error(prefix + msg)
            return
        ex = cl.explain_provider_error(msg)
        st.error(f"{prefix}{ex['what']}  \n**Fix:** {ex['fix']}  \nRaw message: `{ex['raw']}`")

    for _name, _h in _hist.items():
        if _h.get("last_error"):
            _show_err(_h["last_error"], prefix=f"**{_name}** last failed at {str(_h['last_error_at'])[:19]}: ")
    st.write(f"**Priority order** (`GATE_LLM_PRIORITY`): {', '.join(cl.priority_list())}")
    st.write(f"**GATE_LLM_ALLOW_EXTERNAL**: {'set' if settings.external_calls_allowed() else 'unset'}  |  "
             f"**GATE_LLM_FREE_PLAN_CONFIRMED**: {'set' if settings.free_plan_confirmed() else 'unset'}")
    _runnable, _skipped = cl.runnable_providers(False, settings.external_calls_allowed())
    st.write(f"**Runnable now (keys + consents, no spend)**: {', '.join(_runnable) or 'none'}")
    if _skipped:
        with st.expander("Why the others are skipped"):
            for _n, _why in _skipped.items():
                st.write(f"- `{_n}`: {_why}")

    st.markdown("**1. Measure first (offline)**")
    e1, e2, e3 = st.columns(3)
    price_in = e1.number_input("Input $/M tokens", 0.0, 1000.0, 0.0)
    price_out = e2.number_input("Output $/M tokens", 0.0, 1000.0, 0.0)
    est_paper = e3.selectbox("Paper", ["(all)"] + [p for p in session.scalars(select(Paper.id))])
    if st.button("Estimate cost"):
        st.json(cl.estimate_cost(session, None if est_paper == "(all)" else est_paper,
                                 price_in, price_out))

    st.markdown("**2. Dry run - inspect exact payloads, no network**")
    d1, d2 = st.columns(2)
    dry_provider = d1.selectbox("Provider", ["mock", "auto", "free", "freellmapi", "gemini", "groq",
                                             "openrouter", "anthropic", "openai"])
    if d2.button("Dry run"):
        try:
            prov = cl.get_provider(dry_provider)
            st.json(cl.run_classification(session, prov, "gate-cs-2027",
                                          None if est_paper == "(all)" else est_paper,
                                          dry_run=True))
        except (RuntimeError, KeyError) as e:
            session.rollback()
            _show_err(e)

    st.markdown("**3. Classify**")
    _scope = None if est_paper == "(all)" else est_paper
    _in_scope = session.scalar(select(func.count()).select_from(Question)
                               .where(Question.paper_id == _scope) if _scope else select(func.count()).select_from(Question))
    _have = session.scalar(select(func.count(func.distinct(Classification.question_id))).join(
        Question, Question.id == Classification.question_id).where(*( [Question.paper_id == _scope] if _scope else [] )))
    reclass = st.checkbox(
        "Replace existing UNVERIFIED suggestions (audited). Off = questions that already have a suggestion are left "
        "alone, so no question can end up with two classifications.", value=False)
    st.caption(f"Scope: {_in_scope} questions, of which {_have} already have a classification "
               f"-> {'they will be REPLACED unless a human verified them' if reclass else 'they will be skipped'}; "
               f"human-verified rows are never touched either way.")
    r1, r2 = st.columns(2)
    if r1.button("Run mock classification (offline, placeholder output)"):
        stats = cl.run_classification(session, cl.get_provider("mock"), "gate-cs-2027",
                                      None if est_paper == "(all)" else est_paper, reclassify=reclass)
        session.commit()
        st.warning("Mock output is placeholder plumbing - every row still needs human review.")
        st.json(stats)
    consent_external = st.checkbox(
        "I approve sending question text to external providers for this run "
        "(requires GATE_LLM_ALLOW_EXTERNAL=1 in .env; gemini/groq additionally need "
        "GATE_LLM_FREE_PLAN_CONFIRMED=1 unless paid spend is approved)")
    consent_paid = st.checkbox("I approve PAID provider spend for this run")
    if r2.button("Run auto (tries providers in priority order, bounded failover)"):
        try:
            stats = cl.run_auto_classification(
                session, "gate-cs-2027",
                None if est_paper == "(all)" else est_paper,
                allow_spend=consent_paid,
                allow_external=consent_external and settings.external_calls_allowed(),
                reclassify=reclass)
            session.commit()
            st.json(stats)
        except (RuntimeError, KeyError) as e:
            session.rollback()
            _show_err(e)
    ens_names, ens_skipped = cl.runnable_providers(
        consent_paid, consent_external and settings.external_calls_allowed(),
        free_only=not consent_paid)
    if st.button(f"Run ensemble ({'+'.join(ens_names) if ens_names else 'none runnable'})",
                 disabled=not ens_names):
        try:
            provs = [cl.get_provider(n) for n in ens_names]
            stats = cl.run_ensemble(
                session, provs, "gate-cs-2027",
                None if est_paper == "(all)" else est_paper,
                allow_spend=consent_paid,
                allow_external=consent_external and settings.external_calls_allowed(),
                reclassify=reclass)
            session.commit()
            st.json(stats)
        except (RuntimeError, KeyError) as e:
            session.rollback()
            _show_err(e)
    if ens_skipped:
        st.caption("Ensemble skips: " + "; ".join(f"{n} ({w[:80]})" for n, w in ens_skipped.items()))

    st.markdown("**4. Compare a provider with the existing suggestions (writes nothing)**")
    st.caption("Runs ONE provider on a small sample of already-classified questions and shows how often it picks the "
               "same section/topic. This is AGREEMENT, not accuracy - the existing suggestions are unverified until a "
               "human verifies them. Same consent gates as above.")
    cc1, cc2, cc3 = st.columns(3)
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
    st.markdown("**Combined score distribution** (existing classifications)")
    dist = pd.DataFrame(session.execute(
        select(Classification.combo_score, Classification.status)).fetchall(),
        columns=["combo_score", "status"])
    if len(dist):
        st.bar_chart(dist.dropna().groupby("status")["combo_score"].mean())

elif page == "About the Data":
    render_data_inventory(session)

else:  # Glossary & Syllabus
    st.subheader("Glossary & Syllabus")
    st.info("Which papers and years are in this project (2007-2026, PDFs, sessions, keys): see the **About the Data** screen.")
    st.caption(f"GATE CS syllabus {GLOSSARY['syllabus_year']} (sources: {GLOSSARY['source_pdf']} + {GLOSSARY.get('ga_source_pdf') or 'GA section'}). "
               "Every short code used anywhere in this app is expanded here.")
    st.markdown(
        "**How to read the provenance column.** Sections and their syllabus text are "
        "**official** - copied verbatim from the GATE syllabus PDF. Topics and concepts under "
        "them are **inferred** - our curation split of the official text, pending human review. "
        "Prerequisite edges used elsewhere in the app are curated/inferred too, never official.")
    st.markdown("**Sections** - the top-level subjects (GA, EM, DL, ...)")
    st.dataframe(pd.DataFrame(GLOSSARY["sections"]), width="stretch")
    st.markdown("**Topics** - the second level, shown in the app as e.g. `ALGO.SORT`. "
                "Note SORT's full scope is *Searching, sorting, hashing*, not only sorting.")
    st.dataframe(pd.DataFrame(GLOSSARY["topics"]), width="stretch")
    st.markdown("**Concepts** - the finest level, shown as e.g. `ALGO.SORT.HASH`")
    st.dataframe(pd.DataFrame(GLOSSARY["concepts"]), width="stretch")
    if GLOSSARY["structure_notes"]:
        st.markdown("**Structure notes**")
        for n in GLOSSARY["structure_notes"]:
            st.write("- " + n)
