#!/bin/bash
#===============================================================================
# SPM - Deploy N8N per Service Remediation
# Da eseguire sul server UYUNI o su una VM dedicata
#===============================================================================

set -e

echo "=============================================="
echo "  SPM N8N Deployment"
echo "=============================================="

# Configurazione
N8N_DATA_DIR="/opt/n8n/data"
N8N_PORT=5678
N8N_USER="admin"
N8N_PASSWORD="SecureN8nPass2024"
N8N_HOST="n8n.spm.internal"
TIMEZONE="Europe/Rome"

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

#-------------------------------------------------------------------------------
# 1. Verifica prerequisiti
#-------------------------------------------------------------------------------
log_info "Verifica prerequisiti..."

if ! command -v podman &> /dev/null; then
    log_error "Podman non installato. Installalo con: sudo zypper install podman"
    exit 1
fi

#-------------------------------------------------------------------------------
# 2. Crea directory dati
#-------------------------------------------------------------------------------
log_info "Creazione directory dati..."

sudo mkdir -p "$N8N_DATA_DIR"
sudo chown 1000:1000 "$N8N_DATA_DIR"

#-------------------------------------------------------------------------------
# 3. Stop container esistente (se presente)
#-------------------------------------------------------------------------------
if podman container exists n8n 2>/dev/null; then
    log_warn "Container n8n esistente trovato, rimozione..."
    podman stop n8n 2>/dev/null || true
    podman rm n8n 2>/dev/null || true
fi

#-------------------------------------------------------------------------------
# 4. Deploy N8N
#-------------------------------------------------------------------------------
log_info "Deploy container N8N..."

podman run -d \
  --name n8n \
  --restart=always \
  -p ${N8N_PORT}:5678 \
  -v ${N8N_DATA_DIR}:/home/node/.n8n:Z \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER="${N8N_USER}" \
  -e N8N_BASIC_AUTH_PASSWORD="${N8N_PASSWORD}" \
  -e GENERIC_TIMEZONE="${TIMEZONE}" \
  -e TZ="${TIMEZONE}" \
  -e N8N_HOST="${N8N_HOST}" \
  -e N8N_PROTOCOL=http \
  -e WEBHOOK_URL="http://${N8N_HOST}:${N8N_PORT}" \
  -e N8N_ENCRYPTION_KEY="$(openssl rand -hex 32)" \
  -e EXECUTIONS_DATA_PRUNE=true \
  -e EXECUTIONS_DATA_MAX_AGE=168 \
  docker.n8n.io/n8nio/n8n:latest

#-------------------------------------------------------------------------------
# 5. Attendi startup
#-------------------------------------------------------------------------------
log_info "Attesa avvio N8N..."

for i in {1..30}; do
    if curl -s "http://localhost:${N8N_PORT}/healthz" > /dev/null 2>&1; then
        log_info "N8N avviato correttamente!"
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

#-------------------------------------------------------------------------------
# 6. Crea systemd service per persistenza
#-------------------------------------------------------------------------------
log_info "Creazione systemd service..."

sudo tee /etc/systemd/system/n8n.service > /dev/null << EOF
[Unit]
Description=N8N Workflow Automation
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/podman start -a n8n
ExecStop=/usr/bin/podman stop n8n
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable n8n

#-------------------------------------------------------------------------------
# 7. Configura firewall (se attivo)
#-------------------------------------------------------------------------------
if command -v firewall-cmd &> /dev/null; then
    log_info "Configurazione firewall..."
    sudo firewall-cmd --permanent --add-port=${N8N_PORT}/tcp 2>/dev/null || true
    sudo firewall-cmd --reload 2>/dev/null || true
fi

#-------------------------------------------------------------------------------
# 8. Output finale
#-------------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "  N8N DEPLOYMENT COMPLETATO"
echo "=============================================="
echo ""
echo "Accesso WebUI:"
echo "  URL:      http://$(hostname -I | awk '{print $1}'):${N8N_PORT}"
echo "  User:     ${N8N_USER}"
echo "  Password: ${N8N_PASSWORD}"
echo ""
echo "Comandi utili:"
echo "  - Status:    podman ps | grep n8n"
echo "  - Logs:      podman logs -f n8n"
echo "  - Restart:   podman restart n8n"
echo "  - Shell:     podman exec -it n8n sh"
echo ""
echo "Prossimi step:"
echo "  1. Accedi alla WebUI"
echo "  2. Configura credenziali SMTP/IMAP"
echo "  3. Configura SSH credentials per UYUNI"
echo "  4. Importa workflow da: Automation/n8n-workflows/"
echo ""
