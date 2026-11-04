@echo off
rem  First-time setup (safe to re-run): Python 3.12 environment, packages, .env, tests, health check.
rem  Never overwrites your .env or your database. Needs internet.
setlocal
cd /d "%~dp0"
title GATE CSE Intelligence - setup
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\setup.ps1"
echo.
if errorlevel 1 (echo Setup reported a problem - see the messages above and START_HERE.md.) else (echo Setup finished. Double-click start.cmd to open the app.)
if not defined GATE_NO_PAUSE pause
