@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -c "from db import backup_database; print(backup_database())"
if errorlevel 1 (
  echo No se pudo crear el respaldo.
  pause
  exit /b 1
)
echo Respaldo terminado.
pause
