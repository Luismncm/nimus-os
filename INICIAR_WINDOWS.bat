@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  py -3 -m venv .venv
  if errorlevel 1 python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" goto error_python
".venv\Scripts\python.exe" scripts\check_runtime.py
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto error_dependencies
)
".venv\Scripts\python.exe" scripts\launch_windows.py
if errorlevel 1 goto error_start
exit /b 0
:error_python
echo No se pudo crear Python para NIMUS. Instala Python 3.11 o superior y vuelve a intentar.
goto error
:error_dependencies
echo No se pudieron preparar las dependencias. Revisa el mensaje anterior.
goto error
:error_start
echo No se pudo iniciar NIMUS. Revisa el mensaje anterior.
:error
pause
exit /b 1
