"""Engine/session factory. URL from --db-url or GATE_DB_URL (.env). When
neither is set the pipeline runs OFFLINE on a local SQLite file - no Docker,
no psycopg, no network. PostgreSQL stays available by exporting GATE_DB_URL
(see docker-compose.yml); on Postgres prefer `alembic upgrade head`."""
from __future__ import annotations
import os, sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_SQLITE_URL = "sqlite:///data/gate_cse.sqlite"
POSTGRES_URL = "postgresql+psycopg://gate_user:gate@127.0.0.1:5432/gate_cse"

def get_url(override: str | None = None) -> str:
    if override:
        return override
    from ..settings import load_env
    load_env()
    env = os.environ.get("GATE_DB_URL")
    if env:
        return env
    print("GATE_DB_URL unset - offline SQLite mode (data/gate_cse.sqlite). "
          "Export GATE_DB_URL to use PostgreSQL.", file=sys.stderr)
    return DEFAULT_SQLITE_URL

def make_engine(url: str | None = None):
    return create_engine(get_url(url), future=True)

def make_session(url: str | None = None) -> Session:
    return sessionmaker(bind=make_engine(url), expire_on_commit=False)()

def init_schema(url: str | None = None) -> None:
    """Dev shortcut: create tables directly. Real environments use
    `alembic upgrade head` (adds pgvector + FTS index on Postgres)."""
    from .models import Base
    Base.metadata.create_all(make_engine(url))
