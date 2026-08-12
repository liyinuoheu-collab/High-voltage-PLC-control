@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run_monitor.py
) else (
  python run_monitor.py
)
if errorlevel 1 pause
