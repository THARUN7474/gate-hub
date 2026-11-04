"""Ingestion: role detection, hashing, dedup, safe ZIP extraction, paper
registration. Raw files are immutable; derived artefacts carry the source
sha256. Same hash = same document (stored once). A different file claiming an
existing paper identity is FLAGGED for human reconciliation, never merged.
Re-running ingestion is idempotent: no duplicate questions, and human review
decisions are never overwritten (see extraction.persist_records)."""
from __future__ import annotations
import hashlib, re, zipfile
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db.models import Document, Paper, ProcessingRun

MAX_ZIP_FILES = 5000
MAX_ZIP_TOTAL_BYTES = 2 * 1024**3

ROLE_PATTERNS = [
    ("key", re.compile(r"key|answer", re.I)),
    ("syllabus", re.compile(r"syllab", re.I)),
    ("paper", re.compile(r"(CS[-_ ]?\d|paper|question)", re.I)),
]

def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def magic_kind(path: str | Path) -> str:
    with open(path, "rb") as f:
        head = f.read(8)
    if head.startswith(b"%PDF"): return "pdf"
    if head.startswith(b"PK\x03\x04"): return "zip"
    return "other"

def detect_role(filename: str) -> str:
    """Heuristic candidate role. Ambiguous files return 'unknown' and must be
    confirmed by a human or an explicit argument - never silently guessed."""
    for role, pat in ROLE_PATTERNS:
        if pat.search(filename):
            return role
    return "unknown"

def safe_extract_zip(zip_path: str | Path, dest_dir: str | Path) -> list[Path]:
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_FILES:
            raise ValueError(f"zip has {len(infos)} entries, cap {MAX_ZIP_FILES}")
        total = sum(i.file_size for i in infos)
        if total > MAX_ZIP_TOTAL_BYTES:
            raise ValueError(f"zip expands to {total} bytes, cap {MAX_ZIP_TOTAL_BYTES}")
        for info in infos:
            if info.is_dir():
                continue
            target = (dest / info.filename).resolve()
            if not str(target).startswith(str(dest) + "/"):
                raise ValueError(f"zip-slip path rejected: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
            out.append(target)
    return out

def register_document(s: Session, path: str | Path, role: str | None = None,
                      source_url: str | None = None, rights_status: str = "official") -> tuple[Document, bool]:
    path = Path(path)
    digest = sha256_file(path)
    existing = s.scalar(select(Document).where(Document.sha256 == digest))
    if existing:
        return existing, False
    doc = Document(id="doc-" + digest[:16], filename=path.name, sha256=digest,
                   file_path=str(path), source_url=source_url,
                   doc_type=role or detect_role(path.name), rights_status=rights_status)
    s.add(doc)
    return doc, True

def paper_id_for(year: int, session: str, branch: str = "CS") -> str:
    sess = re.sub(r"[^A-Za-z0-9]", "", session.upper().replace(f"{branch}-", "S").replace(branch, "S"))
    return f"GATE-{branch}-{year}-{sess}"

def register_paper(s: Session, year: int, session: str, document_id: str | None,
                   expected_questions: int | None = None, expected_marks: float | None = None,
                   branch: str = "CS", paper_code: str | None = None) -> tuple[str, str]:
    """Returns (paper_id, state): 'new' | 'existing' | 'conflict'.
    'conflict' = a different file already claims this identity: reconcile by hand."""
    pid = paper_id_for(year, session, branch)
    existing = s.get(Paper, pid)
    if existing:
        if existing.document_id == document_id:
            return pid, "existing"
        return pid, "conflict"
    s.add(Paper(id=pid, year=year, branch=branch, session=session, paper_code=paper_code,
                document_id=document_id, expected_questions=expected_questions,
                expected_marks=expected_marks))
    return pid, "new"

def start_run(s: Session, kind: str, file_id: str | None = None,
              model: str | None = None, detail: dict | None = None) -> ProcessingRun:
    run = ProcessingRun(id="run-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"),
                        kind=kind, file_id=file_id, model=model, detail=detail or {})
    s.add(run)
    return run

def finish_run(s: Session, run: ProcessingRun, status: str = "done",
               errors: str | None = None, detail: dict | None = None) -> None:
    run.status = status
    run.errors = errors
    if detail is not None:
        run.detail = detail
    run.finished_at = datetime.now(timezone.utc)
