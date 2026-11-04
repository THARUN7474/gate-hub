"""Copy every table from a SQLite database into PostgreSQL, then PROVE parity.

    python scripts/sqlite_to_postgres.py                       # source: data/gate_cse.sqlite, target: $GATE_DB_URL
    python scripts/sqlite_to_postgres.py --source sqlite:///x.sqlite --target postgresql+psycopg://...
    python scripts/sqlite_to_postgres.py --verify-only         # no writes, just compare
    python scripts/sqlite_to_postgres.py --replace             # TRUNCATE the Postgres tables first

Safety:
  * The SQLite source is opened READ-ONLY (mode=ro) - it is never modified.
  * The target must be PostgreSQL and already migrated (`alembic upgrade head`).
  * Idempotent: without --replace only rows whose primary key is absent in the
    target are inserted, so re-running never duplicates and never overwrites a
    review decision that was made on the Postgres side in the meantime.
  * Copies EVERY table in the ORM metadata, including review_events,
    classifications (provider_votes/agreement/combo), answer_keys, documents.
  * Parity = per-table row counts AND a per-table content checksum computed the
    same way on both sides (datetimes normalised to UTC).
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, func, select, text  # noqa: E402
from sqlalchemy.engine import Engine, make_url  # noqa: E402
from src.db.models import Base  # noqa: E402
from src.settings import load_env  # noqa: E402

BATCH = 500

def _readonly_sqlite(url: str) -> str:
    u = make_url(url)
    if u.get_backend_name() != "sqlite":
        return url
    path = Path(u.database).resolve()
    return f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true"

def _norm(v):
    if isinstance(v, dt.datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=dt.timezone.utc)
        return v.astimezone(dt.timezone.utc).isoformat()
    if isinstance(v, float):
        return round(v, 9)
    return v

def _row_key(table, row) -> str:
    d = {c.name: _norm(row[c.name]) for c in table.columns}
    return json.dumps(d, sort_keys=True, default=str, ensure_ascii=False)

def table_digest(eng: Engine, table) -> tuple[int, str]:
    pk = [c for c in table.primary_key.columns]
    stmt = select(table).order_by(*pk)
    h = hashlib.sha256()
    n = 0
    with eng.connect() as con:
        for row in con.execute(stmt).mappings():
            h.update(_row_key(table, row).encode("utf-8")); h.update(b"\n"); n += 1
    return n, h.hexdigest()[:16]

def copy_table(src: Engine, dst: Engine, table, replace: bool) -> dict:
    pk = [c for c in table.primary_key.columns]
    with dst.connect() as con:
        existing = {tuple(r) for r in con.execute(select(*pk))} if not replace else set()
    inserted = skipped = 0
    batch: list[dict] = []
    def flush():
        nonlocal batch, inserted
        if batch:
            with dst.begin() as con:
                con.execute(table.insert(), batch)
            inserted += len(batch); batch = []
    with src.connect() as con:
        for row in con.execute(select(table).order_by(*pk)).mappings():
            key = tuple(row[c.name] for c in pk)
            if key in existing:
                skipped += 1; continue
            d = dict(row)
            for k, v in d.items():
                if isinstance(v, dt.datetime) and v.tzinfo is None:
                    d[k] = v.replace(tzinfo=dt.timezone.utc)   # SQLite stored UTC, naive
            batch.append(d)
            if len(batch) >= BATCH:
                flush()
    flush()
    return {"inserted": inserted, "already_present": skipped}

def reset_sequences(dst: Engine) -> list[str]:
    done = []
    with dst.begin() as con:
        for table in Base.metadata.sorted_tables:
            for col in table.primary_key.columns:
                if col.autoincrement is True or (str(col.type) == "INTEGER" and col.autoincrement == "auto"
                                                 and len(table.primary_key.columns) == 1):
                    seq = con.execute(text("select pg_get_serial_sequence(:t, :c)"),
                                      {"t": table.name, "c": col.name}).scalar()
                    if seq:
                        con.execute(text(f"select setval('{seq}', coalesce((select max({col.name}) from {table.name}), 1), "
                                         f"(select max({col.name}) is not null from {table.name}))"))
                        done.append(f"{table.name}.{col.name}")
    return done

def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=os.environ.get("GATE_SOURCE_DB_URL", "sqlite:///data/gate_cse.sqlite"))
    ap.add_argument("--target", default=os.environ.get("GATE_DB_URL"))
    ap.add_argument("--replace", action="store_true", help="TRUNCATE target tables first")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    a = ap.parse_args()
    if not a.target or not a.target.startswith("postgresql"):
        print("target must be a PostgreSQL URL (set GATE_DB_URL or pass --target)", file=sys.stderr); return 2
    src = create_engine(_readonly_sqlite(a.source))
    dst = create_engine(a.target)
    tables = list(Base.metadata.sorted_tables)
    report: dict = {"source": make_url(a.source).render_as_string(hide_password=True),
                    "target": make_url(a.target).render_as_string(hide_password=True), "tables": {}}
    if not a.verify_only:
        if a.replace:
            with dst.begin() as con:
                con.execute(text("TRUNCATE " + ", ".join(f'"{t.name}"' for t in tables) + " RESTART IDENTITY CASCADE"))
        for t in tables:
            report["tables"][t.name] = {"copy": copy_table(src, dst, t, a.replace)}
        report["sequences_reset"] = reset_sequences(dst)
    ok = True
    for t in tables:
        sn, sh = table_digest(src, t)
        dn, dh = table_digest(dst, t)
        match = (sn == dn and sh == dh)
        ok &= match
        report["tables"].setdefault(t.name, {})["parity"] = {
            "source_rows": sn, "target_rows": dn, "source_sha": sh, "target_sha": dh, "match": match}
    report["all_tables_match"] = ok
    if a.json:
        print(json.dumps(report, indent=2))
    else:
        for name, d in report["tables"].items():
            p = d["parity"]
            c = d.get("copy")
            extra = f"  (+{c['inserted']} new, {c['already_present']} present)" if c else ""
            print(f"{'OK  ' if p['match'] else 'DIFF'} {name:24s} src={p['source_rows']:5d} dst={p['target_rows']:5d} "
                  f"{p['source_sha']} {p['target_sha']}{extra}")
        print("PARITY:", "ALL TABLES MATCH" if ok else "MISMATCH - see DIFF rows")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
