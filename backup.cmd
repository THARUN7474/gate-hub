@echo off
rem  Make a verified, timestamped copy of your database into the backups folder. Safe to run any time.
setlocal
cd /d "%~dp0"
title GATE CSE Intelligence - backup
if not exist ".venv\Scripts\python.exe" (
  echo No environment yet. Double-click setup.cmd first.
  if not defined GATE_NO_PAUSE pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 -m src.cli backup
echo.
echo Backups are in the "backups" folder next to this file.
if not defined GATE_NO_PAUSE pause
