@echo off
rem  Save an API key into .env WITHOUT showing it on screen.
rem  Usage:  setkey.cmd gemini            (or groq / openrouter / anthropic / openai)
rem          setkey.cmd gemini --model <model-id>
rem  The key is typed/pasted at a hidden prompt and written only to .env (private, never shared).
rem  This does NOT switch on any external call - that stays your own decision in .env.
setlocal
cd /d "%~dp0"
title GATE CSE Intelligence - save API key
if not exist ".venv\Scripts\python.exe" (
  echo No environment yet. Double-click setup.cmd first.
  if not defined GATE_NO_PAUSE pause
  exit /b 1
)
set "PROV=%~1"
if "%PROV%"=="" set /p PROV=Which provider? (gemini / groq / openrouter / anthropic / openai):
".venv\Scripts\python.exe" -X utf8 -m src.cli set-key %PROV% %2 %3 %4 %5
echo.
if not defined GATE_NO_PAUSE pause
