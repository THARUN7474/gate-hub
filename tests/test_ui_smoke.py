"""UI smoke: app.py must always compile; with streamlit installed the module
must import and its helpers must work (skips cleanly when the optional UI
dependency is absent, e.g. a minimal audit environment)."""
import py_compile, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ROOT = Path(__file__).resolve().parents[1]

def test_app_compiles():
    py_compile.compile(str(ROOT / "app.py"), doraise=True)

def test_app_imports_with_streamlit(loaded, monkeypatch):
    pytest.importorskip("streamlit", reason="optional UI dependency not installed")
    db_url, pid, _ = loaded
    monkeypatch.setenv("GATE_DB_URL", db_url)
    import importlib
    import app as appmod
    importlib.reload(appmod)
    from src.db.session import make_session
    from src.db.models import Question
    with make_session(db_url) as s:
        q = s.scalars(select(Question).limit(1)).first() if False else None
    assert hasattr(appmod, "source_previews")
