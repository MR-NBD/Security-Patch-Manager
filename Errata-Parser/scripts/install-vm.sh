#!/bin/bash
################################################################################
# Errata-Parser — Installazione su VM Ubuntu dedicata
#
# Installa errata-parser come servizio systemd su VM Ubuntu.
# Sostituisce i 2 container ACI e le 4 Azure Logic Apps.
# Lo scheduler APScheduler è embedded nell'app.
#
# Usage (dalla VM, come root):
#   bash install-vm.sh
################################################################################

set -euo pipefail

INSTALL_DIR="/opt/errata-parser"
VENV_DIR="$INSTALL_DIR/venv"
SERVICE_NAME="errata-parser"
PORT=5000

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

[[ $EUID -eq 0 ]] || fail "Eseguire come root (sudo bash install-vm.sh)"

# --------------------------------------------------------------------------
# 1. Prerequisiti sistema
# --------------------------------------------------------------------------
info "Installazione prerequisiti sistema..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv libpq-dev curl

python3 -c "import sys; assert sys.version_info >= (3,9)" \
    || fail "Python 3.9+ richiesto (trovato: $(python3 --version))"
info "Python $(python3 --version) OK"

# --------------------------------------------------------------------------
# 2. Directory
# --------------------------------------------------------------------------
info "Creazione directory $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR/logs"
chmod 750 "$INSTALL_DIR/logs"

# Copia file dall'attuale directory del repo
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cp "$REPO_DIR/app.py"           "$INSTALL_DIR/app.py"
cp "$REPO_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"
info "File copiati da $REPO_DIR"

# --------------------------------------------------------------------------
# 3. Virtualenv e dipendenze
# --------------------------------------------------------------------------
info "Creazione virtualenv in $VENV_DIR..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q
info "Dipendenze installate"

# --------------------------------------------------------------------------
# 4. File .env
# --------------------------------------------------------------------------
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    cat > "$INSTALL_DIR/.env" << 'EOF'
# ============================================================
# Errata-Parser — Configurazione
# ============================================================

# Database PostgreSQL
# Fase 1: Azure PostgreSQL  → postgresql://user:pass@host:5432/dbname?sslmode=require
# Fase 2: locale            → postgresql://user:pass@localhost:5432/dbname
DATABASE_URL=CHANGE_ME

# UYUNI Server (VNet)
# NOTA: usare le credenziali LOCALI dell'utente UYUNI, NON la password Azure AD.
# Con SAML attivo (java.sso=true) l'account admin è inaccessibile via browser
# ma continua a funzionare per le API XML-RPC.
UYUNI_URL=https://10.172.2.17
UYUNI_USER=admin
UYUNI_PASSWORD=CHANGE_ME

# API key (protezione endpoint — scegliere una stringa casuale lunga)
SPM_API_KEY=CHANGE_ME

# NVD severity enrichment (opzionale ma raccomandato — aumenta rate limit)
# Registrarsi su https://nvd.nist.gov/developers/request-an-api-key
NVD_API_KEY=

# Scheduler integrato (sostituisce Logic Apps)
SCHEDULER_ENABLED=true

# Logging
LOG_FILE=/opt/errata-parser/logs/errata-parser.log
FLASK_ENV=production
EOF
    warn "IMPORTANTE: verifica le credenziali in $INSTALL_DIR/.env"
else
    info ".env già presente — non sovrascritto"
fi
chmod 600 "$INSTALL_DIR/.env"

# --------------------------------------------------------------------------
# 5. Systemd service
# --------------------------------------------------------------------------
info "Installazione servizio systemd $SERVICE_NAME..."
cat > "/etc/systemd/system/$SERVICE_NAME.service" << EOF
[Unit]
Description=Errata-Parser v3.2 — Sync USN/DSA/NVD → UYUNI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$VENV_DIR/bin/gunicorn \\
    --bind 127.0.0.1:$PORT \\
    --workers 1 \\
    --timeout 1800 \\
    --graceful-timeout 1800 \\
    --access-logfile $INSTALL_DIR/logs/access.log \\
    --error-logfile  $INSTALL_DIR/logs/error.log \\
    app:app
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
info "Servizio $SERVICE_NAME installato e abilitato (non ancora avviato)"

# --------------------------------------------------------------------------
# 6. Logrotate
# --------------------------------------------------------------------------
cat > "/etc/logrotate.d/$SERVICE_NAME" << EOF
$INSTALL_DIR/logs/*.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
    copytruncate
}
EOF
info "Logrotate configurato"

# --------------------------------------------------------------------------
# 7. Riepilogo
# --------------------------------------------------------------------------
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Installazione completata!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Passi successivi:"
echo ""
echo "  1. Verifica credenziali:   nano $INSTALL_DIR/.env"
echo "  2. Avvia il servizio:      systemctl start $SERVICE_NAME"
echo "  3. Controlla lo stato:     systemctl status $SERVICE_NAME"
echo "  4. Logs live:              journalctl -u $SERVICE_NAME -f"
echo ""
echo "  Verifica funzionamento:"
echo "  5. Health:    curl -s http://localhost:$PORT/api/health | python3 -m json.tool"
echo "  6. Scheduler: curl -s http://localhost:$PORT/api/scheduler/jobs | python3 -m json.tool"
echo ""
