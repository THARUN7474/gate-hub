"""Dev-only additive schema upgrade for existing SQLite/Postgres databases
created before v6, mirroring alembic 0003 without requiring alembic on the
SQLite quickstart path. Idempotent: checks existing columns first. Also
backfills combo fields for pre-v6 classifications (single-provider rows:
agreement=1.0, combo=confidence, one recorded vote) so old data displays in
the new UI. Never destructive; Postgres users should prefer alembic upgrade."""
from __future__ import annotations
import json
from sqlalchemy import inspect, text
from .session import make_engine

NEW_COLUMNS = {
    "agreement": "FLOAT",
    "combo_score": "FLOAT",
    "provider_votes": "JSON",
    "provider_count": "INTEGER",
}

def missing_schema(url: str | None = None) -> list[str]:
    """Read-only: columns/tables the ORM models expect but this database lacks (empty = up to date)."""
    from .models import Base
    eng = make_engine(url)
    insp = inspect(eng)
    have_tables = set(insp.get_table_names())
    out: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in have_tables:
            out.append(f"table {table.name}")
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        out += [f"{table.name}.{c.name}" for c in table.columns if c.name not in have]
    return out

def sync_missing_columns(url: str | None = None) -> dict:
    """Add any column that exists in the ORM models but not yet in the database
    (nullable columns only - anything else needs a real Alembic migration), and
    create missing tables. Additive and idempotent; never alters or drops data.
    This is what lets a database created by an older version pick up new model
    fields (e.g. questions.printed_label) without Alembic on the SQLite path."""
    from .models import Base
    eng = make_engine(url)
    Base.metadata.create_all(eng)            # new tables only (checkfirst)
    insp = inspect(eng)
    added: dict[str, list[str]] = {}
    skipped: list[str] = []
    with eng.begin() as con:
        for table in Base.metadata.sorted_tables:
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                if not col.nullable and col.default is None and col.server_default is None:
                    skipped.append(f"{table.name}.{col.name} (NOT NULL: needs an Alembic migration)")
                    continue
                ddl = col.type.compile(dialect=eng.dialect)
                con.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))
                added.setdefault(table.name, []).append(col.name)
    return {"added": added, "skipped": skipped}

def upgrade_schema(url: str | None = None) -> dict:
    """Everything `upgrade-dev` does: generic column sync + v6 classification backfill."""
    cols = sync_missing_columns(url)
    cls = upgrade_classifications_table(url)
    return {"columns": cols, "classifications": cls}

def upgrade_classifications_table(url: str | None = None) -> dict:
    eng = make_engine(url)
    insp = inspect(eng)
    if "classifications" not in insp.get_table_names():
        return {"added": [], "backfilled": 0, "note": "no classifications table yet - run init first"}
    existing = {c["name"] for c in insp.get_columns("classifications")}
    added = []
    backfill_ok = eng.dialect.name == "sqlite"
    with eng.begin() as con:
        for col, typ in NEW_COLUMNS.items():
            if col not in existing:
                con.execute(text(f"ALTER TABLE classifications ADD COLUMN {col} {typ}"))
                added.append(col)
        if not backfill_ok:
            return {"added": added, "backfilled": 0,
                    "note": "backfill skipped on non-SQLite; run alembic upgrade + reclassify"}
        res = con.execute(text(
            "SELECT id, model, primary_topic_id, confidence FROM classifications "
            "WHERE combo_score IS NULL"))
        rows = res.fetchall()
        for cid, model, topic, conf in rows:
            votes = json.dumps([{"provider": "legacy inferred suggestion (pre-v6; no provider run recorded)",
                                 "model": model, "topic": topic, "confidence": conf}])
            con.execute(text(
                "UPDATE classifications SET agreement=NULL, combo_score=NULL, "
                "provider_votes=:v, provider_count=0 WHERE id=:i"),
                {"v": votes, "i": cid})
    return {"added": added, "backfilled": len(rows)}
