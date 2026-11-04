import os, subprocess, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Backend switch. Default: every test gets its own throwaway SQLite file.
# Set GATE_TEST_DB_URL to a PostgreSQL URL to run the SAME suite on Postgres:
#     GATE_TEST_DB_URL=postgresql+psycopg://gate_user:***@127.0.0.1:5432/gate_test
# Safety: the database name MUST end in "_test" (the suite TRUNCATEs every
# table between tests) so it can never be pointed at the real gate_cse DB.
# ---------------------------------------------------------------------------
PG_TEST_URL = os.environ.get("GATE_TEST_DB_URL", "").strip()
USING_PG = PG_TEST_URL.startswith("postgresql")

def pytest_configure(config):
    config.addinivalue_line("markers", "sqlite_only: test exercises SQLite-specific behaviour; skipped on Postgres")
    if USING_PG:
        from sqlalchemy.engine import make_url
        name = make_url(PG_TEST_URL).database or ""
        if not name.endswith("_test"):
            pytest.exit(f"REFUSING to run: GATE_TEST_DB_URL database '{name}' must end with '_test' "
                        "(the suite truncates all tables).", returncode=4)

def pytest_collection_modifyitems(config, items):
    if USING_PG:
        skip = pytest.mark.skip(reason="SQLite-specific test (running on PostgreSQL)")
        for item in items:
            if "sqlite_only" in item.keywords:
                item.add_marker(skip)

@pytest.fixture(autouse=True)
def _no_pacing_in_tests(monkeypatch):
    """Real runs are paced to GATE_LLM_RPM requests/minute; tests use instant fake transports, so switch pacing
    off (the pacing logic itself is tested with an injected fake clock in tests/test_run_guard.py)."""
    monkeypatch.setenv("GATE_LLM_RPM", "0")

@pytest.fixture(autouse=True)
def _neutral_owner_routing(monkeypatch):
    """The owner's .env routes every LLM call through FreeLLMAPI only (GATE_LLM_ROUTER_ONLY=1) and may enable
    decision models. Tests must not depend on that personal choice: pin neutral values (set, not deleted, so a
    later load_env() cannot re-import them). Tests that exercise those settings set them explicitly."""
    from src.classification.classify import DEFAULT_PRIORITY
    monkeypatch.setenv("GATE_LLM_ROUTER_ONLY", "0")
    monkeypatch.setenv("GATE_LLM_PRIORITY", DEFAULT_PRIORITY)
    monkeypatch.setenv("GATE_LLM_PROVIDER", "auto")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "")
    monkeypatch.setenv("DECISIONS_ENABLED", "0")

@pytest.fixture(scope="session")
def _pg_migrated():
    """Run `alembic upgrade head` once against the Postgres test database."""
    env = dict(os.environ, GATE_DB_URL=PG_TEST_URL)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)
    return PG_TEST_URL

def _truncate_all(url: str) -> None:
    from sqlalchemy import create_engine, text
    eng = create_engine(url)
    with eng.begin() as con:
        # Earlier tests (notably Streamlit AppTest scripts, which keep their session alive) can leave
        # connections 'idle in transaction'; TRUNCATE needs an exclusive lock and would wait forever.
        # Safe: this database's name was verified to end in '_test' in pytest_configure.
        con.execute(text("select pg_terminate_backend(pid) from pg_stat_activity "
                         "where datname = current_database() and pid <> pg_backend_pid()"))
    with eng.begin() as con:
        names = [r[0] for r in con.execute(text(
            "select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'"))]
        if names:
            con.execute(text("TRUNCATE " + ", ".join(f'"{n}"' for n in names) + " RESTART IDENTITY CASCADE"))
    eng.dispose()

@pytest.fixture()
def blank_db(tmp_path, request):
    """URL of an empty, schema-ready database (SQLite file or Postgres test DB)."""
    if USING_PG:
        url = request.getfixturevalue("_pg_migrated")
        _truncate_all(url)
        return url
    url = f"sqlite:///{tmp_path}/test.db"
    from src.db.session import init_schema
    init_schema(url)
    return url

@pytest.fixture(scope="session")
def fixture_paper(tmp_path_factory):
    """Synthetic paper + key. NOT a real GATE paper - see scripts/make_fixture.py."""
    d = tmp_path_factory.mktemp("fixture")
    pdf, key = d / "fixture_paper.pdf", d / "fixture_key.csv"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_fixture.py"), str(pdf), str(key)], check=True)
    return pdf, key

@pytest.fixture()
def db_url(blank_db):
    return blank_db

@pytest.fixture()
def loaded(db_url, fixture_paper, tmp_path):
    """Taxonomy + one 6-question synthetic paper + key, extracted and reconciled."""
    from src.db.session import make_session
    from src.ingestion import ingest as ig
    from src.ingestion import keys as kmod
    from src.extraction.extract import extract_questions, persist_records, reconcile
    from src.taxonomy import taxonomy as tx

    pdf, key_csv = fixture_paper
    with make_session(db_url) as s:
        tax = tx.load_taxonomy(str(ROOT / "taxonomy.yaml"))
        assert not tx.validate_taxonomy(tax)
        tx.upsert_taxonomy(s, tax)
        doc, _ = ig.register_document(s, pdf, role="fixture", rights_status="fixture")
        pid, state = ig.register_paper(s, 2099, "CS-1", doc.id,
                                       expected_questions=6, expected_marks=8.0)
        assert state == "new"
        recs = extract_questions(pdf, pid, tmp_path / "assets")
        persist_records(s, recs)
        kmod.import_keys_csv(s, pid, key_csv)
        rec = reconcile(s, pid)
        s.commit()
    return db_url, pid, rec
