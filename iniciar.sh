#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Primero ejecutá ./instalar.sh"
  exit 1
fi
echo "Abriendo el panel en http://localhost:8501 (Ctrl+C para cerrar)"
exec .venv/bin/python -m streamlit run app.py
