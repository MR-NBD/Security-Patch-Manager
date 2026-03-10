#!/bin/bash
################################################################################
# Errata-Parser — Update (git pull + restart)
# Usage: sudo bash update-vm.sh
################################################################################

set -euo pipefail

INSTALL_DIR="/opt/errata-parser"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

GREEN='\033[0;32m'; NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC}  $*"; }

info "Copia file aggiornati da $REPO_DIR..."
cp "$REPO_DIR/app.py"           "$INSTALL_DIR/app.py"
cp "$REPO_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"

info "Aggiornamento dipendenze..."
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

info "Restart errata-parser..."
systemctl restart errata-parser
sleep 3

systemctl is-active errata-parser \
    && info "Servizio attivo" \
    || { echo "Errore — controlla: journalctl -u errata-parser -n 30"; exit 1; }

curl -s --max-time 10 http://localhost:5000/api/health | python3 -m json.tool
