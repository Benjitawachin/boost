@echo off
cd /d "%~dp0"
title Monitor Xeneize
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecuta instalar.bat
  pause
  exit /b 1
)
echo Abriendo el panel en http://localhost:8501
echo No cierres esta ventana mientras uses la app.
".venv\Scripts\python.exe" -m streamlit run app.py
pause
