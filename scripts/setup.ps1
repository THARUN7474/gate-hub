<#
  One-shot, SAFE setup for Windows:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 [-SkipTests] [-Postgres]

  Creates the Python 3.12 venv, installs requirements, creates .env from the template
  (ONLY if it does not exist), prepares the database, runs the tests and `doctor`.
  It NEVER overwrites or modifies an existing .env or database, never prints secrets, never spends money.
#>
param([switch]$SkipTests, [switch]$Postgres)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

Step "Python 3.12 virtual environment"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv python install 3.12 | Out-Null
        uv venv --python 3.12 .venv
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.12 -m venv .venv
    } else {
        throw "Need Python 3.12+. Install uv (https://docs.astral.sh/uv/) or Python 3.12 from python.org, then re-run."
    }
} else { Write-Host ".venv already exists - keeping it" }
$py = Join-Path $root ".venv\Scripts\python.exe"
& $py --version

Step "Install requirements"
if (Get-Command uv -ErrorAction SilentlyContinue) { uv pip install --python $py -r requirements.txt }
else { & $py -m pip install -r requirements.txt }

Step ".env (never overwritten)"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    $chars = (48..57) + (65..90) + (97..122)
    $pw = -join (1..32 | ForEach-Object { [char]($chars | Get-Random) })
    (Get-Content ".env" -Raw) -replace "POSTGRES_PASSWORD=choose-a-strong-local-password", "POSTGRES_PASSWORD=$pw" |
        Set-Content ".env" -Encoding utf8 -NoNewline
    Write-Host ".env created from the template with a random local Postgres password (not shown). LLM keys stay empty."
} else { Write-Host ".env exists - left untouched" }

Step "Database"
if ($Postgres) {
    docker compose up -d
    Write-Host "Postgres container started. Set GATE_DB_URL in .env (see .env.example), then:  .venv\Scripts\python -m alembic upgrade head"
} elseif (Test-Path "data\gate_cse.sqlite") {
    Write-Host "data\gate_cse.sqlite exists - left UNTOUCHED (setup never modifies an existing database)."
    Write-Host "To load all papers into it (backs up first, proves your reviews are unchanged):  .\scripts\dev.ps1 promote"
} else {
    & $py -m src.cli init
    & $py -m src.cli taxonomy
    Write-Host "Fresh SQLite database created. Load papers with:  .venv\Scripts\python -m src.cli papers-load"
}

if (-not $SkipTests) { Step "Tests"; & $py -m pytest tests -q }
Step "Doctor"
& $py -m src.cli doctor
Write-Host "`nNext:  .\scripts\dev.ps1 app     (open the UI)     |     .\scripts\dev.ps1 help" -ForegroundColor Green
