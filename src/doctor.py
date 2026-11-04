"""`python -m src.cli doctor` - one command that says what is wrong with this
machine/project and how to fix it. PASS / WARN / FAIL per check, each with a
fix hint. Never prints a secret: keys are reported only as set / not set.
Read-only: it opens the database for SELECTs and touches nothing."""
from __future__ import annotations
import importlib, os, platform, shutil, subprocess, sys
from pathlib import Path
from .settings import APP_ROOT, load_env, external_calls_allowed, free_plan_confirmed

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
PINNED_PYMUPDF = "1.28.2"

def _ver(mod: str) -> str | None:
    try:
        m = importlib.import_module(mod)
    except Exception:
        return None
    return getattr(m, "__version__", None) or getattr(m, "VersionBind", None) or "installed"

def run_checks(db_url: str | None = None) -> list[dict]:
    load_env()
    out: list[dict] = []
    def add(level, name, detail="", fix=""):
        out.append({"level": level, "name": name, "detail": detail, "fix": fix})

    # ---- python + dependencies ------------------------------------------------------------
    v = sys.version_info
    if v >= (3, 12):
        add(PASS, "Python version", platform.python_version())
    elif v >= (3, 10):
        add(WARN, "Python version", f"{platform.python_version()} (target is 3.12+)",
            "install 3.12: `uv python install 3.12` then `uv venv --python 3.12 .venv`")
    else:
        add(FAIL, "Python version", platform.python_version(), "install Python 3.12+")
    required = {"sqlalchemy": "sqlalchemy", "alembic": "alembic", "psycopg": "psycopg", "pymupdf": "pymupdf",
                "pdfplumber": "pdfplumber", "pydantic": "pydantic", "yaml": "pyyaml", "pandas": "pandas",
                "streamlit": "streamlit", "plotly": "plotly", "dotenv": "python-dotenv", "typer": "typer"}
    missing = [pkg for mod, pkg in required.items() if _ver(mod) is None]
    if missing:
        add(FAIL, "Python packages", "missing: " + ", ".join(missing), "pip install -r requirements.txt")
    else:
        add(PASS, "Python packages", f"{len(required)} required packages importable")
    pm = _ver("pymupdf")
    if pm and pm != PINNED_PYMUPDF:
        add(WARN, "PyMuPDF version", f"{pm} (pinned {PINNED_PYMUPDF}; extraction text is version-sensitive)",
            f"pip install pymupdf=={PINNED_PYMUPDF}")
    elif pm:
        add(PASS, "PyMuPDF version", f"{pm} (matches the pin)")
    if _ver("rapidocr") and _ver("onnxruntime"):
        add(PASS, "OCR engine", "rapidocr + onnxruntime available (scanned papers 2011/2015/2017/2019-2021)")
    else:
        add(WARN, "OCR engine", "rapidocr/onnxruntime missing: scanned papers cannot be (re-)extracted",
            "pip install rapidocr onnxruntime   (cached OCR results still work without it)")

    # ---- environment file -----------------------------------------------------------------
    if (APP_ROOT / ".env").exists():
        add(PASS, ".env file", "present (never printed)")
    else:
        add(WARN, ".env file", "missing - defaults to offline SQLite, no LLM keys", "cp .env.example .env")

    # ---- database -------------------------------------------------------------------------
    try:
        from sqlalchemy import inspect, select, func
        from .db.session import get_url, make_engine, make_session
        from .db import models as m
        url = get_url(db_url)
        kind = url.split(":", 1)[0].split("+")[0]
        safe = url if kind == "sqlite" else url.split("@")[-1]
        eng = make_engine(db_url)
        with eng.connect() as con:
            con.exec_driver_sql("select 1")
        add(PASS, "Database connection", f"{kind}: {safe}")
        insp = inspect(eng)
        tables = set(insp.get_table_names())
        need = {t.name for t in m.Base.metadata.sorted_tables}
        if need - tables:
            add(FAIL, "Database schema", "missing tables: " + ", ".join(sorted(need - tables)),
                "alembic upgrade head   (PostgreSQL)  |  python -m src.cli init   (SQLite)")
        else:
            miss_cols = [f"{t.name}.{c.name}" for t in m.Base.metadata.sorted_tables
                         for c in t.columns if c.name not in {x['name'] for x in insp.get_columns(t.name)}]
            if miss_cols:
                add(WARN, "Database schema", "columns missing: " + ", ".join(miss_cols[:6]),
                    "alembic upgrade head   (PostgreSQL)  |  python -m src.cli upgrade-dev   (SQLite)")
            else:
                add(PASS, "Database schema", f"{len(need)} tables, all model columns present")
        if kind == "postgresql":
            with eng.connect() as con:
                head = con.exec_driver_sql("select version_num from alembic_version").scalar() if "alembic_version" in tables else None
                ext = {r[0] for r in con.exec_driver_sql("select extname from pg_extension")}
            from alembic.script import ScriptDirectory
            from alembic.config import Config
            cfg = Config(str(APP_ROOT / "alembic.ini")); cfg.set_main_option("script_location", str(APP_ROOT / "alembic"))
            want = ScriptDirectory.from_config(cfg).get_current_head()
            add(PASS if head == want else WARN, "Alembic revision", f"db={head} head={want}",
                "" if head == want else "alembic upgrade head")
            add(PASS if "vector" in ext else WARN, "pgvector extension", "enabled" if "vector" in ext else "not installed",
                "" if "vector" in ext else "use the pgvector/pgvector:pg17 image (docker compose up -d)")
        with make_session(db_url) as s:
            nq = s.scalar(select(func.count()).select_from(m.Question))
            np_ = s.scalar(select(func.count()).select_from(m.Paper))
            ncl = s.scalar(select(func.count(func.distinct(m.Classification.question_id))))
            nver = s.scalar(select(func.count(func.distinct(m.Classification.question_id))).where(m.Classification.status == "verified"))
            ntax = s.scalar(select(func.count()).select_from(m.TaxonomyNode))
            add(PASS if np_ else WARN, "Papers loaded", f"{np_} papers, {nq} questions, {ncl} classified, {nver} human-verified",
                "" if np_ else "python -m src.cli papers-load")
            add(PASS if ntax else FAIL, "Taxonomy", f"{ntax} nodes", "" if ntax else "python -m src.cli taxonomy")
            # recorded source PDFs must still be findable (renames are healed via sha256)
            from .ingestion.paths import resolve_document_path
            docs = s.scalars(select(m.Document)).all()
            lost = [d.filename for d in docs if d.doc_type != "fixture" and resolve_document_path(d) is None]
            add(PASS if not lost else WARN, "Source PDFs findable", f"{len(docs) - len(lost)}/{len(docs)} registered documents located",
                "" if not lost else "missing: " + ", ".join(lost[:4]) + " - restore under data/raw/")
    except Exception as e:  # noqa: BLE001
        add(FAIL, "Database connection", f"{type(e).__name__}: {str(e)[:140]}",
            "check GATE_DB_URL in .env; for Postgres: make pg-up  (Docker Desktop must be running)")

    # ---- raw data + manifest --------------------------------------------------------------
    try:
        from .ingestion import registry as rg
        entries = rg.load_manifest()
        gone = [e.paper_id for e in entries if not Path(e.file).exists()]
        add(PASS if not gone else FAIL, "Manifest source files", f"{len(entries)} manifest papers, {len(gone)} source files missing",
            "" if not gone else "restore: " + ", ".join(gone[:5]))
        regs = {str(Path(e.file).resolve()) for e in entries}
        raw = [p for p in (APP_ROOT / "data/raw/papers").rglob("*.pdf")]
        unreg = [p.name for p in raw if str(p.resolve()) not in regs]
        add(PASS if not unreg else WARN, "Raw papers registered", f"{len(raw) - len(unreg)}/{len(raw)} PDFs in manifests/papers.yaml",
            "" if not unreg else "add to manifests/papers.yaml: " + ", ".join(unreg[:8]))
    except Exception as e:  # noqa: BLE001
        add(FAIL, "Manifest", f"{type(e).__name__}: {e}", "fix manifests/papers.yaml")

    # ---- LLM providers (no secrets) --------------------------------------------------------
    try:
        from .classification import classify as cl
        st = cl.provider_status()
        have = [p["provider"] for p in st if p["key_set"]]
        add(PASS if have else WARN, "LLM provider keys", ("set for: " + ", ".join(have)) if have else "none set (mock/offline only)",
            "" if have else "add a key to .env (see .env.example / docs/13_LLM_SETUP.md)")
        add(PASS if external_calls_allowed() else WARN, "External-call consent (GATE_LLM_ALLOW_EXTERNAL)",
            "1 - question text MAY leave this machine" if external_calls_allowed() else "0 - no question text leaves this machine",
            "" if external_calls_allowed() else "set 1 in .env ONLY when you intend a live LLM run")
        add(PASS, "Free-plan attestation (GATE_LLM_FREE_PLAN_CONFIRMED)", "1 (your statement)" if free_plan_confirmed() else "0")
    except Exception as e:  # noqa: BLE001
        add(WARN, "LLM provider status", f"{type(e).__name__}: {e}")

    # ---- docker (only matters for the PostgreSQL option) ---------------------------------------
    dk = shutil.which("docker")
    if not dk:
        add(WARN, "Docker", "not installed (only needed for PostgreSQL)", "install Docker Desktop, or stay on SQLite")
    else:
        try:
            r = subprocess.run([dk, "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True, timeout=12)
            if r.returncode == 0:
                add(PASS, "Docker engine", f"running (server {r.stdout.strip()})")
            else:
                add(WARN, "Docker engine", "installed but not running", "start Docker Desktop, wait for 'Engine running'")
        except Exception:
            add(WARN, "Docker engine", "did not answer in 12s", "start Docker Desktop")
    free_gb = shutil.disk_usage(APP_ROOT).free / 1e9
    add(PASS if free_gb > 2 else WARN, "Disk space", f"{free_gb:.1f} GB free", "" if free_gb > 2 else "free some space")
    return out

def render(results: list[dict]) -> str:
    lines = []
    for r in results:
        lines.append(f"{r['level']:4s}  {r['name']}" + (f"  -  {r['detail']}" if r["detail"] else ""))
        if r["fix"] and r["level"] != PASS:
            lines.append(f"      fix: {r['fix']}")
    n = {k: sum(1 for r in results if r["level"] == k) for k in (PASS, WARN, FAIL)}
    lines.append(f"\n{n[PASS]} pass, {n[WARN]} warn, {n[FAIL]} fail")
    return "\n".join(lines)
