@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0work\studio"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Project Python is missing. Set up .venv before entering dye mode.
  pause
  exit /b 1
)
"%PYTHON%" "%~dp0work\studio\app.py"
if errorlevel 1 pause
