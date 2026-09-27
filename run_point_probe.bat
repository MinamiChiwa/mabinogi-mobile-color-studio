@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0work\studio"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Project Python is missing. Do not enter dye mode.
  pause
  exit /b 1
)
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss-fff"') do set "STAMP=%%t"
set "OUT=%~dp0outputs\point-probe-%STAMP%"
echo Point sampling diagnostic: one placement and up to 16 tiny motion probes.
echo Wait for the manual-entry message, then enter the dye countdown yourself.
echo It uses 48 bounded zoom steps; this is not a maximum-zoom measurement.
echo It will not click the entry, apply, confirm, cancel, or open another bottle.
echo F9 stops. The point-probe stage has a 25-second hard budget.
"%PYTHON%" "%~dp0work\studio\live_atlas_capture.py" acquire "%OUT%" --strategy probe
if errorlevel 1 (
  echo Diagnostic stopped. Do not start another dye; retain this log for analysis:
) else (
  echo Diagnostic complete. Inspect the game and exit manually when appropriate.
)
echo %OUT%
pause
