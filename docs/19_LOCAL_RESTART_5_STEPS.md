# Safe local restart in five steps (Windows) - updated 5 Nov 2026

Work in `C:\Users\Tharun\Desktop\2027\gate-hub`. Promotion is done (5 Nov 2026). It is no longer part
of a restart.

## 1. Stop the old app instance, and only that one

Close the black `start.cmd` window; that stops the app. If you're not sure whether something is still
listening on port 8501:

```powershell
$c = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
if ($c) { Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" | Select-Object ProcessId, CommandLine }
```

Stop it **only** if its command line is `... streamlit run app.py` from this folder:
`Stop-Process -Id <that ProcessId>`. Never stop all Python processes. Docker Desktop (FreeLLMAPI,
Postgres) stays running.

## 2. Open the project

1. Open Docker Desktop. The FreeLLMAPI router restarts by itself; check that http://127.0.0.1:3001 opens.
2. Open the folder in VS Code and open a terminal (Ctrl+`).
3. Run `git status`. It should say "nothing to commit" unless you have edits in progress.

## 3. Back up and check health

Double-click `backup.cmd` (a verified copy goes to `backups\`), then run:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m src.cli doctor
```

You want 0 fail. A warning about the FreeLLMAPI key is expected until you save it with
`setkey.cmd freellmapi`.

## 4. Start the app

Double-click `start.cmd` (or run `.\scripts\dev.ps1 app`) and open http://localhost:8501. Quick check:
- Pipeline Status shows 29 papers.
- Review Workspace with Show set to "benchmark sample (gold review)" lists 120 pending questions.

## 5. After working

- After a review session, run `backup.cmd`. Your reviews are in `data\gate_cse.sqlite`, which is not in git.
- After changing code or docs, run `git add .`, then `git commit -m "what changed"`, then `git push`.
- Close the black window to stop the app.
