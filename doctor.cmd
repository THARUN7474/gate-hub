@echo off
rem  Health check: PASS / WARN / FAIL for Python, packages, database, PDFs, API keys, Docker - each with the fix.
rem  Read-only. Never prints secrets.
setlocal
cd /d "%~dp0"
title GATE CSE Intelligence - doctor
if not exist ".venv\Scripts\python.exe" (
  echo No environment yet. Double-click setup.cmd first.
  if not defined GATE_NO_PAUSE pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 -m src.cli doctor
echo.
if not defined GATE_NO_PAUSE pause
