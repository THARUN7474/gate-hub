"""Locate a registered source PDF even after the owner renamed or moved it.

documents.file_path records where a file was when it was ingested. The raw
folder was later reorganised (CS1.pdf -> CS1_2026.pdf, files moved into year
folders), which silently broke source previews. The SHA-256 is the document's
true identity, so when the recorded path is gone we search data/raw for a file
with the same hash. Read-only; the DB is never modified by a lookup."""
from __future__ import annotations
import hashlib
from functools import lru_cache
from pathlib import Path
from ..settings import APP_ROOT

RAW_ROOT = APP_ROOT / "data" / "raw"

def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

@lru_cache(maxsize=1)
def _index(root: str, signature: tuple) -> dict[str, str]:
    """sha256 -> path for every PDF under root. Cached per (root, file-signature)
    so a changed folder is re-hashed, an unchanged one costs nothing."""
    out: dict[str, str] = {}
    for p in Path(root).rglob("*.pdf"):
        try:
            out[_sha(p)] = str(p)
        except OSError:
            continue
    return out

def _signature(root: Path) -> tuple:
    try:
        return tuple(sorted((str(p), p.stat().st_size, int(p.stat().st_mtime)) for p in root.rglob("*.pdf")))
    except OSError:
        return ()

def resolve_document_path(doc, root: Path | None = None) -> Path | None:
    """Best existing path for a Document row: recorded path (as-is, then relative
    to the app root), else a hash match inside data/raw. None if truly missing."""
    root = Path(root) if root else RAW_ROOT
    rec = Path(doc.file_path)
    for cand in (rec, APP_ROOT / rec):
        if cand.exists():
            return cand
    if not root.exists():
        return None
    hit = _index(str(root), _signature(root)).get(doc.sha256)
    return Path(hit) if hit else None
