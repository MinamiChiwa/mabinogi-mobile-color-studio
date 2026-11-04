@echo off
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\build_local_package.py
if errorlevel 1 (
  echo Build failed. Check artifacts\local-builds for logs.
  pause
  exit /b 1
)
explorer.exe "%~dp0发布包"
