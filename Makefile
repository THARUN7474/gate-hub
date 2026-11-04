# Everyday commands. Windows without make: use  .\scripts\dev.ps1 <verb>  (same verbs).
# Nothing here deletes data or spends money. `pg-down` STOPS the container and KEEPS the volume.
PY ?= $(shell test -x .venv/bin/python && echo .venv/bin/python || echo .venv/Scripts/python.exe)

.PHONY: help setup doctor test test-pg app backup probe load llm pg-up pg-down pg-psql pg-sync
help:
	@echo "setup doctor test test-pg app backup probe load llm pg-up pg-down pg-psql pg-sync"
setup:    ; bash scripts/setup.sh
doctor:   ; $(PY) -m src.cli doctor
test:     ; $(PY) -m pytest tests -q
test-pg:  ; GATE_TEST_DB_URL=$${GATE_TEST_DB_URL:?set GATE_TEST_DB_URL to a *_test Postgres database} $(PY) -m pytest tests -q
app:      ; $(PY) -m streamlit run app.py
backup:   ; $(PY) -m src.cli backup
probe:    ; $(PY) -m src.cli papers-probe
load:     ; $(PY) -m src.cli papers-load
llm:      ; $(PY) -m src.cli llm-status
pg-up:    ; docker compose up -d
pg-down:  ; docker compose stop
pg-psql:  ; docker exec -it gate-postgres psql -U gate_user -d gate_cse
pg-sync:  ; $(PY) -m alembic upgrade head && $(PY) scripts/sqlite_to_postgres.py
