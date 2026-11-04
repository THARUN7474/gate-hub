@echo off
rem  Put the full 2011-2026 dataset into your REAL database (data\gate_cse.sqlite).
rem  Step 1 shows what would be added and changes NOTHING. Step 2 asks you to type YES.
rem  The apply step backs up first and then proves every review you already made is unchanged.
setlocal
cd /d "%~dp0"
title GATE CSE Intelligence - load the full dataset
if not exist ".venv\Scripts\python.exe" (
  echo No environment yet. Double-click setup.cmd first.
  if not defined GATE_NO_PAUSE pause
  exit /b 1
)
echo ---- Step 1: preview (nothing is changed) ----
".venv\Scripts\python.exe" -X utf8 scripts\promote_to_live.py
echo.
echo ---- Step 2 ----
echo To apply this to your real database type YES and press Enter.
echo Anything else cancels and changes nothing.
set "ANSWER="
set /p ANSWER=Your answer:
if /i not "%ANSWER%"=="YES" (
  echo Cancelled. Nothing was changed.
  if not defined GATE_NO_PAUSE pause
  exit /b 0
)
echo.
".venv\Scripts\python.exe" -X utf8 scripts\promote_to_live.py --yes
echo.
if not defined GATE_NO_PAUSE pause
