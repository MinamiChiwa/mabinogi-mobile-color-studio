@echo off
cd /d "%~dp0"
start "" /wait "%~dp0ColorStudio.exe" --native-preflight --korean --output-dir "%~dp0data\korean-preflight"
