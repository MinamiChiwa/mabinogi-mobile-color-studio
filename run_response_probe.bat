@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0work\studio"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "PROTOCOL=baseline"
if /i "%~1"=="rotation_compare" set "PROTOCOL=rotation_compare"
if not exist "%PYTHON%" (
  echo Project Python is missing. Set up .venv before entering dye mode.
  pause
  exit /b 1
)
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss-fff"') do set "STAMP=%%t"
set "OUT=%~dp0outputs\response-probe-%STAMP%"
echo Checking the runtime before input-response measurement.
"%PYTHON%" "%~dp0work\studio\live_atlas_capture.py" preflight "%OUT%-preflight"
if errorlevel 1 (
  echo Preflight failed. Report: %OUT%-preflight\preflight.json
  pause
  exit /b 1
)
echo Wait for the manual-entry message, then open the dye countdown in game.
echo This diagnostic measures rotation and wheel response. It does not search for a dye result.
if "%PROTOCOL%"=="baseline" echo Up to 28 baseline conditions; rounded arcs without angular motion are skipped.
if "%PROTOCOL%"=="rotation_compare" echo Comparing 32 original and grouped arcs with equal input timing.
echo Keep the game in the foreground. Press F9 to stop.
"%PYTHON%" "%~dp0work\studio\live_atlas_capture.py" acquire "%OUT%" --strategy response --response-protocol %PROTOCOL%
echo Measurement finished or stopped. Full or partial results are saved here:
echo %OUT%
echo Inspect the game and leave the dye screen manually.
pause
