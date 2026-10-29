@echo off
setlocal
cd /d "%~dp0"
rem Qt 版启动入口。原 run_studio.bat 仍可在需要时启动 Tk 版做对照。
set "PYTHONPATH=%~dp0work\studio"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" "%~dp0run_qt.py"
if errorlevel 1 pause
