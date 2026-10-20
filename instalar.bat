@echo off
setlocal
cd /d "%~dp0"
title Monitor Xeneize - Instalacion
echo ==============================================
echo   MONITOR XENEIZE - Instalacion
echo ==============================================
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul || goto nopython

echo [1/4] Creando entorno de Python...
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv || goto error
)

echo [2/4] Instalando dependencias (puede tardar unos minutos)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto error

echo [3/4] Descargando el navegador Chromium...
".venv\Scripts\python.exe" -m playwright install chromium || goto error

echo [4/4] Preparando Streamlit...
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
  >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

echo.
echo Instalacion completa. Para abrir la app, hace doble clic en iniciar.bat
pause
exit /b 0

:nopython
echo No se encontro Python 3.10 o superior.
echo Instalalo desde https://www.python.org/downloads/ tildando "Add Python to PATH"
echo y despues volve a ejecutar instalar.bat
start "" https://www.python.org/downloads/
pause
exit /b 1

:error
echo.
echo Hubo un error durante la instalacion. Revisa los mensajes de arriba.
pause
exit /b 1
