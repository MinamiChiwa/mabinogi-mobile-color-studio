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
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss-fff"') do set "STAMP=%%t"
set "OUT=%~dp0outputs\atlas-capture-%STAMP%"
echo Checking the runtime. Wait for the manual-entry message before entering dye mode.
echo It will not click the dye entry, apply, confirm, cancel, or open another bottle.
echo Press F9 to stop.
echo This capture tests the 48-step staggered route with full-width marker columns and five coverage fills. It does not select a dye result.
"%PYTHON%" "%~dp0work\studio\live_atlas_capture.py" acquire "%OUT%" --strategy grid --row-stagger 0.05
if errorlevel 1 (
  echo.
  echo Capture stopped or aborted. Inspect the log.json in:
  echo %OUT%
)
pause
