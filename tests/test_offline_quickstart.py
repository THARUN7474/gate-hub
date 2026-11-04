"""Offline-by-default DB URL and the quickstart smoke run: a fresh checkout
must work with zero Docker, zero network and zero spend."""
import os, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import session as sess

def test_default_url_is_offline_sqlite(monkeypatch):
    monkeypatch.delenv("GATE_DB_URL", raising=False)
    assert sess.get_url() == sess.DEFAULT_SQLITE_URL

def test_env_and_override_win(monkeypatch):
    monkeypatch.setenv("GATE_DB_URL", "postgresql+psycopg://u:p@h/db")
    assert sess.get_url() == "postgresql+psycopg://u:p@h/db"
    assert sess.get_url("sqlite:///x.db") == "sqlite:///x.db"

def test_quickstart_end_to_end(tmp_path, monkeypatch):
    monkeypatch.delenv("GATE_DB_URL", raising=False)
    from typer.testing import CliRunner
    from src.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["quickstart", "--out-dir", str(tmp_path / "qs")])
    assert result.exit_code == 0, result.output
    assert "quickstart OK" in result.output
    assert (tmp_path / "qs" / "quickstart.db").exists()

def test_quickstart_refuses_real_db(loaded, tmp_path, monkeypatch, capsys):
    """The fixture quickstart must never write into the shipped real DB."""
    db_url, pid, _ = loaded  # fixture db here; make it look real
    from src.db.models import Document, Paper
    from src.db.session import make_session
    with make_session(db_url) as s:
        p = s.scalars(__import__("sqlalchemy").select(Paper)).first()
        d = s.get(Document, p.document_id)
        d.rights_status = "official"  # now indistinguishable from real data
        s.commit()
    from typer.testing import CliRunner
    from src.cli import app
    result = CliRunner().invoke(app, ["quickstart", "--out-dir", str(tmp_path / "qs2"),
                                      "--db-url", db_url])
    assert result.exit_code == 3
    assert "REFUSED" in result.output
