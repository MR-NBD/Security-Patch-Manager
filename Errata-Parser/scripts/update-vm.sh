#!/bin/bash
################################################################################
# Errata-Parser — Update (git pull + migrations + restart)
# Usage: sudo bash update-vm.sh
################################################################################

set -euo pipefail

INSTALL_DIR="/opt/errata-parser"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }

# --------------------------------------------------------------------------
# 1. Copia file aggiornati
# --------------------------------------------------------------------------
info "Copia file aggiornati da $REPO_DIR..."
cp "$REPO_DIR/app.py"           "$INSTALL_DIR/app.py"
cp "$REPO_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"

# --------------------------------------------------------------------------
# 2. Aggiornamento dipendenze
# --------------------------------------------------------------------------
info "Aggiornamento dipendenze Python..."
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

# --------------------------------------------------------------------------
# 3. Migrations DB pendenti
# --------------------------------------------------------------------------
MIGRATIONS_DIR="$REPO_DIR/sql/migrations"
APPLIED_FILE="$INSTALL_DIR/.migrations_applied"
touch "$APPLIED_FILE"

if [[ -d "$MIGRATIONS_DIR" ]]; then
    DB_URL=$(grep "^DATABASE_URL=" "$INSTALL_DIR/.env" | cut -d= -f2-)
    for migration in $(ls "$MIGRATIONS_DIR"/*.sql 2>/dev/null | sort); do
        name=$(basename "$migration")
        if grep -qxF "$name" "$APPLIED_FILE"; then
            info "Migration $name: già applicata — skip"
        else
            info "Applicazione migration $name..."
            psql "$DB_URL" -f "$migration" -v ON_ERROR_STOP=1
            echo "$name" >> "$APPLIED_FILE"
            info "Migration $name: APPLICATA"
        fi
    done
else
    warn "Nessuna directory migrations trovata in $MIGRATIONS_DIR"
fi

# --------------------------------------------------------------------------
# 4. Restart servizio
# --------------------------------------------------------------------------
info "Restart errata-parser..."
systemctl restart errata-parser
sleep 3

systemctl is-active errata-parser \
    && info "Servizio attivo" \
    || { echo "Errore — controlla: journalctl -u errata-parser -n 30"; exit 1; }

# --------------------------------------------------------------------------
# 5. Verifica health
# --------------------------------------------------------------------------
curl -s --max-time 10 http://localhost:5000/api/health | python3 -m json.tool
