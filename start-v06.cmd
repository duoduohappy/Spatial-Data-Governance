@echo off
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -X utf8 -m geoacceptance.local_launcher --port 8768 --data-dir work/v06-app-v2
pause
