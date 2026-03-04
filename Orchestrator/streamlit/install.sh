#!/usr/bin/env bash
# Installa e avvia il dashboard Streamlit di SPM
# Da eseguire sul VM oppure in locale puntando al VM via SPM_API_URL
#
# Usage:
#   ./install.sh               → installa e avvia (porta 8501)
#   SPM_API_URL=http://10.172.2.22:5001 ./install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== SPM Dashboard — Setup ==="

# Virtualenv se non esiste
if [ ! -d ".venv" ]; then
    echo "Creazione virtualenv..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installazione dipendenze..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo ""
echo "=== Avvio dashboard ==="
echo "URL API: ${SPM_API_URL:-http://10.172.2.22:5001}"
echo "Dashboard: http://localhost:8501"
echo ""

export SPM_API_URL="${SPM_API_URL:-http://10.172.2.22:5001}"
exec streamlit run app.py
