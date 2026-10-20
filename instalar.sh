#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "=============================================="
echo "  MONITOR XENEIZE - Instalación"
echo "=============================================="

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "No se encontró Python 3.10 o superior. Instalalo desde https://www.python.org/downloads/ y volvé a ejecutar este script."
  exit 1
fi

echo "[1/4] Creando entorno de Python..."
[ -x .venv/bin/python ] || "$PY" -m venv .venv

echo "[2/4] Instalando dependencias (puede tardar unos minutos)..."
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt

echo "[3/4] Descargando el navegador Chromium..."
.venv/bin/python -m playwright install chromium

echo "[4/4] Preparando Streamlit..."
mkdir -p "$HOME/.streamlit"
[ -f "$HOME/.streamlit/credentials.toml" ] || printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"

echo
echo "Instalación completa. Para abrir la app: ./iniciar.sh"
