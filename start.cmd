@echo off
rem  GATE CSE Intelligence - double-click to start the app.
rem  First run on a new machine sets itself up automatically (needs internet once).
setlocal
cd /d "%~dp0"
title GATE CSE Intelligence

if not exist ".venv\Scripts\python.exe" (
  echo First run: setting things up. This takes a few minutes and needs internet once...
  powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\setup.ps1" -SkipTests
  if errorlevel 1 (
    echo.
    echo Setup did not finish. Open START_HERE.md and look at "If something goes wrong".
    if not defined GATE_NO_PAUSE pause
    exit /b 1
  )
)

set "HEADLESS="
if defined GATE_NO_BROWSER set "HEADLESS=--server.headless true"

echo.
echo ============================================================
echo  GATE CSE Intelligence is starting.
echo  Your browser opens by itself. If not, go to:
echo      http://localhost:8501
echo  To STOP the app: close this window  (or press Ctrl+C).
echo.
echo  Tip: if you only see 2 papers, double-click promote.cmd once
echo       to load the full 2011-2026 dataset (it backs up first).
echo ============================================================
echo.

".venv\Scripts\python.exe" -m streamlit run app.py %HEADLESS% --browser.gatherUsageStats false
if errorlevel 1 (
  echo.
  echo The app stopped with an error. Run doctor.cmd to see what is wrong.
  if not defined GATE_NO_PAUSE pause
)
