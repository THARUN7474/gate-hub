# Safe local restart in five steps (Windows)

Reconciled from `docs/GATE_v7_docs_update/18_LOCAL_RESTART_5_STEPS.md`. Every command here was run on this machine on 4 Nov 2026
(except the `--yes`/`YES` promotion, which is your decision). Work in `C:\Users\Tharun\Desktop\2027\gate-hub`.

## 1. Stop the old instance - only that one
Close the black `start.cmd` window (that stops the app). If you are unsure whether something still listens on port 8501:
```powershell
$c = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
if ($c) { Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" | Select-Object ProcessId, CommandLine }
```
Stop it **only** if the command line is `... streamlit run app.py` from this folder: `Stop-Process -Id <that ProcessId>`.
Never stop all Python processes. PostgreSQL/Docker does not need stopping for an app restart.

## 2. Back up and check health
Double-click `backup.cmd` (a verified copy goes to `backups\`), then `doctor.cmd`. You want `0 fail`.
Note the backup file name it prints.

## 3. Preview the promotion (changes nothing)
Double-click `promote.cmd` and read the preview **only**; at the question type anything except `YES` to cancel.
(Or `.\scripts\dev.ps1 promote`.) Today it shows: 29 papers in the manifest, 2 already live, 27 to be added (the schema column it used to list was added
through the app's upgrade button on 4 Nov, 14:15). A rehearsal on a copy (4 Nov) ended with 29 papers / 1,885 questions, 1,300 key rows,
all 3 existing review events and all 65 classifications byte-unchanged.

## 4. Promote - only if you decide to
Run `promote.cmd` again and type `YES` (or `.\scripts\dev.ps1 promote --yes`). It backs up first, adds the schema column, loads the
papers and keys, and then proves every earlier review event and classification is unchanged; any mismatch prints FAIL and the backup
to restore. After it says DONE, optionally complete 2025 Q59's text: `.\scripts\dev.ps1 repair-text --paper GATE-CS-2025-S1` (preview),
then add `--yes`.

## 5. Start and check
Double-click `start.cmd` and open http://localhost:8501. Look at Pipeline Status, Question Browser, Analysis Matrix, Review Workspace
and Approve Queue. In Review Workspace open 2026 CS-1 Q21, Q37, Q48: compare the image with the text, answer the five review checks,
save without verifying, reload the page, and confirm the checks and the audit history are still there.

## No API key needed
Browsing and reviewing the 65 existing suggestions needs no key. To add more suggestions without a key use the chat round trip in
`docs/20_CHAT_ASSISTED_CLASSIFICATION.md`. Unattended runs over all 28 papers need an API provider (`docs/13_LLM_SETUP.md`).
