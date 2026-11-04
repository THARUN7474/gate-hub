#!/usr/bin/env bash
# One-shot, SAFE setup (macOS/Linux/Git-Bash):  bash scripts/setup.sh [--skip-tests]
# Creates the Python 3.12 venv, installs requirements, creates .env from the template ONLY if
# missing, prepares the DB, runs tests + doctor. Never overwrites .env or a database, never
# prints secrets, never spends money.
set -euo pipefail
cd "$(dirname "$0")/.."
step() { printf '\n==> %s\n' "$1"; }

step "Python 3.12 virtual environment"
if [ ! -x .venv/bin/python ] && [ ! -x .venv/Scripts/python.exe ]; then
  if command -v uv >/dev/null 2>&1; then uv python install 3.12 >/dev/null; uv venv --python 3.12 .venv
  elif command -v python3.12 >/dev/null 2>&1; then python3.12 -m venv .venv
  else echo "Need Python 3.12+. Install uv (https://docs.astral.sh/uv/) or python3.12, then re-run."; exit 1; fi
else echo ".venv already exists - keeping it"; fi
PY=.venv/bin/python; [ -x "$PY" ] || PY=.venv/Scripts/python.exe
"$PY" --version

step "Install requirements"
if command -v uv >/dev/null 2>&1; then uv pip install --python "$PY" -r requirements.txt; else "$PY" -m pip install -r requirements.txt; fi

step ".env (never overwritten)"
if [ ! -f .env ]; then
  cp .env.example .env
  PW=$("$PY" - <<'EOF'
import secrets, string
print("".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32)))
EOF
)
  "$PY" - "$PW" <<'EOF'
import sys, pathlib
p = pathlib.Path(".env"); t = p.read_text()
p.write_text(t.replace("POSTGRES_PASSWORD=choose-a-strong-local-password", f"POSTGRES_PASSWORD={sys.argv[1]}"))
EOF
  echo ".env created with a random local Postgres password (not shown). LLM keys stay empty."
else echo ".env exists - left untouched"; fi

step "Database"
if [ -f data/gate_cse.sqlite ]; then echo "data/gate_cse.sqlite exists - left UNTOUCHED (setup never modifies an existing database)."; echo "To load all papers into it (backs up first):  $PY scripts/promote_to_live.py --yes"
else "$PY" -m src.cli init && "$PY" -m src.cli taxonomy; echo "Fresh SQLite DB. Load papers: $PY -m src.cli papers-load"; fi

if [ "${1:-}" != "--skip-tests" ]; then step "Tests"; "$PY" -m pytest tests -q; fi
step "Doctor"; "$PY" -m src.cli doctor
printf '\nNext: make app   (or: %s -m streamlit run app.py)\n' "$PY"
