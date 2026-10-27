@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo First run: py -3.13 -m venv .venv
  echo Then: .venv\Scripts\python.exe -m pip install -r requirements.lock.txt
  pause
  exit /b 1
)
.venv\Scripts\python.exe -X utf8 -m geoacceptance.server --port 8765
pause
