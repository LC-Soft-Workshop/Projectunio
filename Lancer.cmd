@echo off
cd /d "%~dp0"
if exist "Projectunio.exe" (
  start "" "%~dp0Projectunio.exe"
  exit /b
)
if exist "runtime\python\pythonw.exe" (
  start "" "runtime\python\pythonw.exe" "%~dp0app.py"
) else (
  python app.py
  if errorlevel 1 pause
)
