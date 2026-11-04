"""Timestamped, verified database backups (SQLite and PostgreSQL).

SQLite: uses the sqlite3 online-backup API (a raw file copy of a live WAL
database can be torn), then runs PRAGMA integrity_check on the copy.
PostgreSQL: pg_dump in custom format, run inside the compose container
(`docker exec gate-postgres pg_dump`) or via a local pg_dump if present.
Never modifies the live database."""
from __future__ import annotations
import datetime as dt, os, shutil, sqlite3, subprocess
from pathlib import Path
from sqlalchemy.engine import make_url
from .db.session import get_url
from .settings import APP_ROOT

def _stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")

def backup_sqlite(src_path: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"gate_cse.{_stamp()}.sqlite"
    src = sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
        integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
        counts = {t: dst.execute(f'select count(*) from "{t}"').fetchone()[0]
                  for (t,) in dst.execute("select name from sqlite_master where type='table' order by 1")}
    finally:
        src.close(); dst.close()
    return {"kind": "sqlite", "file": str(dest), "bytes": dest.stat().st_size, "integrity_check": integrity,
            "rows": {k: v for k, v in counts.items() if k in ("papers", "questions", "classifications", "review_events", "answer_keys")}}

def backup_postgres(url: str, out_dir: Path, container: str = "gate-postgres") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    u = make_url(url)
    dest = out_dir / f"gate_cse.{_stamp()}.pgdump"
    docker = shutil.which("docker")
    if shutil.which("pg_dump"):
        env = dict(os.environ, PGPASSWORD=u.password or "")
        cmd = ["pg_dump", "-Fc", "-h", u.host or "127.0.0.1", "-p", str(u.port or 5432), "-U", u.username, "-d", u.database, "-f", str(dest)]
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    elif docker:
        with open(dest, "wb") as f:
            r = subprocess.run([docker, "exec", "-e", f"PGPASSWORD={u.password or ''}", container,
                                "pg_dump", "-Fc", "-U", u.username, "-d", u.database], stdout=f, stderr=subprocess.PIPE)
        r.stderr = r.stderr.decode(errors="replace") if isinstance(r.stderr, bytes) else r.stderr
    else:
        raise RuntimeError("neither pg_dump nor docker is available")
    if r.returncode != 0:
        raise RuntimeError("pg_dump failed: " + (r.stderr or "")[:300])
    return {"kind": "postgresql", "file": str(dest), "bytes": dest.stat().st_size}

def backup(db_url: str | None = None, out_dir: str | Path = "backups") -> dict:
    url = get_url(db_url)
    out = Path(out_dir)
    if not out.is_absolute():
        out = APP_ROOT / out
    u = make_url(url)
    if u.get_backend_name() == "sqlite":
        p = Path(u.database)
        if not p.is_absolute():
            p = APP_ROOT / p
        return backup_sqlite(p, out)
    return backup_postgres(url, out)
