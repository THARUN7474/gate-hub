<#
  Everyday commands (Windows):   .\scripts\dev.ps1 <verb>
  Same verbs as the Makefile. Safe by default; nothing here deletes data or spends money.
#>
param([Parameter(Position = 0)][string]$Verb = "help", [Parameter(ValueFromRemainingArguments = $true)]$Rest)
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "No .venv yet - run: powershell -File scripts\setup.ps1"; exit 1 }

function PgUrl {   # builds the local compose URL from .env WITHOUT printing the password
    $pw = (Select-String -Path ".env" -Pattern '^POSTGRES_PASSWORD=(.+)$').Matches[0].Groups[1].Value.Trim()
    return "postgresql+psycopg://gate_user:$pw@127.0.0.1:5432/gate_cse"
}

switch ($Verb) {
    "setup"   { & powershell -ExecutionPolicy Bypass -File "$root\scripts\setup.ps1" @Rest }
    "doctor"  { & $py -m src.cli doctor }
    "test"    { & $py -m pytest tests -q @Rest }
    "test-pg" {   # whole suite on PostgreSQL 17 (needs: pg-up). Uses the separate *_test database.
        docker exec gate-postgres psql -U gate_user -d gate_cse -tc "select 1 from pg_database where datname='gate_test'" | Select-String 1 | Out-Null
        if ($LASTEXITCODE -ne 0) { docker exec gate-postgres psql -U gate_user -d gate_cse -c "CREATE DATABASE gate_test" | Out-Null }
        $env:GATE_TEST_DB_URL = (PgUrl) -replace '/gate_cse$', '/gate_test'
        & $py -m pytest tests -q @Rest
    }
    "app"     { & $py -m streamlit run app.py @Rest }
    "pg-up"   { docker compose up -d; Write-Host "Postgres 17 + pgvector starting. Then: set GATE_DB_URL in .env and run  alembic upgrade head" }
    "pg-down" { docker compose stop; Write-Host "Stopped. Data volume gate_pgdata is KEPT (use 'docker compose down -v' yourself to delete it - not done here)." }
    "pg-psql" { docker exec -it gate-postgres psql -U gate_user -d gate_cse }
    "pg-sync" { $env:GATE_DB_URL = PgUrl; & $py -m alembic upgrade head; & $py scripts\sqlite_to_postgres.py @Rest }
    "backup"  { & $py -m src.cli backup }
    "probe"   { & $py -m src.cli papers-probe @Rest }
    "load"    { & $py -m src.cli papers-load @Rest }
    "llm"     { & $py -m src.cli llm-status }
    "setkey"  { & $py -m src.cli set-key @Rest }          # hidden prompt -> .env, e.g.  .\scripts\dev.ps1 setkey gemini
    "models"  { & $py -m src.cli llm-models @Rest }       # which Gemini models can my key see? (sends only the key)
    "compare"  { & $py -m src.cli classify-compare @Rest }        # pilot: agreement + actual tokens on a spread sample; writes NOTHING
    "classify" { & $py -m src.cli classify @Rest }                # e.g.  classify --provider gemini --years 2022-2026 --dry-run
    "repair-text" { & $py scripts\repair_truncated_text.py @Rest }   # complete a truncated question text (dry run unless --yes)
    "chat-export" { & $py -m src.cli chat-export @Rest }          # NO API: batch folder for ChatGPT/Claude chat
    "chat-import" { & $py -m src.cli chat-import @Rest }          # validate the chat's JSON (add --yes to import as suggestions)
    "review-status" { & $py -m src.cli review-status }             # human-review coverage (numerators/denominators)
    "validate" { & $py -m src.cli validate @Rest }                  # database consistency checks
    "browser-test" { & $py scripts\ui_browser_test.py @Rest }      # real Chromium on a throwaway DB copy
    "promote" {   # make the full dataset LIVE: dry run by default, add -Yes (passed as --yes) to apply
        & $py scripts\promote_to_live.py @Rest
    }
    default {
        Write-Host @"
GATE CSE Intelligence - dev commands
  setup     create venv, install, .env, DB, tests, doctor        (safe to re-run)
  doctor    check Python/packages/DB/schema/PDFs/keys/Docker with fixes
  test      run the test suite on SQLite          test-pg   same suite on PostgreSQL 17
  app       start the Streamlit UI
  backup    verified timestamped DB backup (SQLite or Postgres)
  probe     extract every paper in manifests/papers.yaml in memory and show the 65/100 gate
  load      load papers (+keys) into the current database      (idempotent)
  pg-up / pg-down / pg-psql / pg-sync    PostgreSQL 17 + pgvector via Docker (pg-down keeps the data)
  llm       show provider keys/gates (no secrets)
  setkey    save an API key into .env at a HIDDEN prompt:  .\scripts\dev.ps1 setkey gemini
  models    list the Gemini models your key can see (sends only the key, no question text)
  compare   pilot on already-classified questions: agreement + ACTUAL tokens, writes nothing   (--provider gemini --sample 0.12)
  classify  run classification (skips already-classified, paced, checkpointed): add --dry-run / --years 2022-2026 / --max-calls N
  repair-text  complete a truncated question text (audited); --paper GATE-CS-2025-S1, dry run unless --yes
  chat-export  NO API KEY: write a 10-25 question batch for ChatGPT/Claude chat   (--years 2022-2026 | --paper-id ...)
  chat-import  check the chat's answers.json (dry run); add --yes to import as SUGGESTIONS (never verified)
  review-status  how many questions are classified / verified / have a review rubric
  validate  database consistency checks (duplicates, orphans, NULLs, taxonomy ids, reconciliation)
  promote   put the full 2011-2026 dataset into the LIVE database. Dry run by default;
            apply with:  .\scripts\dev.ps1 promote --yes   (backs up first, proves your reviews are unchanged)
  browser-test   real-browser UI test (Playwright) on a throwaway copy of the database
"@
    }
}
