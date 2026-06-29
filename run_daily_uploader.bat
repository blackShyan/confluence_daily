@echo off
setlocal

set "APP_DIR=%~dp0"
set "PYTHON=%APP_DIR%.venv\Scripts\python.exe"
set "PYTHONW=%APP_DIR%.venv\Scripts\pythonw.exe"

if not exist "%PYTHON%" (
  echo [Confluence Daily Uploader] .venv Python was not found.
  echo Expected: %PYTHON%
  echo.
  echo Run this first:
  echo   python -m venv .venv
  echo   .\.venv\Scripts\python.exe -m pip install -e .
  pause
  exit /b 1
)

cd /d "%APP_DIR%"
if exist "%PYTHONW%" (
  start "" "%PYTHONW%" -m confluence_daily
) else (
  start "" "%PYTHON%" -m confluence_daily
)
