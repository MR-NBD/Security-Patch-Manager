#!/bin/bash
# ============================================================
# SPM Orchestrator - Script di installazione VM Ubuntu 24.04
# ============================================================
# Esegui come root: sudo bash install.sh
# ============================================================

set -euo pipefail

# --- Colori ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# --- Variabili ---
INSTALL_DIR="/opt/spm-orchestrator"
SERVICE_USER="spm"
SERVICE_GROUP="spm"
LOG_DIR="/var/log/spm-orchestrator"
DB_NAME="spm_orchestrator"
DB_USER="spm_orch"
PYTHON_VERSION="python3.11"

# ============================================================
log "=== SPM Orchestrator Installation ==="
# ============================================================

# Verifica root
[[ $EUID -ne 0 ]] && fail "This script must be run as root"

# Verifica Ubuntu 24.04
if ! grep -q "Ubuntu 24.04" /etc/os-release 2>/dev/null; then
    warn "This script is designed for Ubuntu 24.04 - proceed anyway? (y/N)"
    read -r answer
    [[ "$answer" != "y" ]] && fail "Aborted"
fi

# ============================================================
# STEP 1: Dipendenze sistema
# ============================================================
log "Installing system dependencies..."

apt-get update -qq
apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    postgresql \
    postgresql-contrib \
    libpq-dev \
    python3.11-dev \
    curl \
    git \
    jq

log "System dependencies installed"

# ============================================================
# STEP 2: Utente di servizio
# ============================================================
log "Creating service user: ${SERVICE_USER}..."

if ! id "${SERVICE_USER}" &>/dev/null; then
    useradd -r -s /bin/false -d "${INSTALL_DIR}" "${SERVICE_USER}"
    log "User ${SERVICE_USER} created"
else
    warn "User ${SERVICE_USER} already exists"
fi

# ============================================================
# STEP 3: Directory
# ============================================================
log "Creating directories..."

mkdir -p "${INSTALL_DIR}"
mkdir -p "${LOG_DIR}"

chown "${SERVICE_USER}:${SERVICE_GROUP}" "${LOG_DIR}"
log "Directories created"

# ============================================================
# STEP 4: Copia applicazione
# ============================================================
log "Copying application files..."

# Assume che lo script sia nella repo root di Orchestrator/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "${SCRIPT_DIR}")"

cp -r "${REPO_DIR}/app" "${INSTALL_DIR}/"
cp -r "${REPO_DIR}/sql" "${INSTALL_DIR}/"
cp "${REPO_DIR}/requirements.txt" "${INSTALL_DIR}/"

if [[ -f "${REPO_DIR}/.env" ]]; then
    cp "${REPO_DIR}/.env" "${INSTALL_DIR}/.env"
    chmod 640 "${INSTALL_DIR}/.env"
    chown root:"${SERVICE_GROUP}" "${INSTALL_DIR}/.env"
    log ".env file copied"
elif [[ -f "${REPO_DIR}/.env.example" ]]; then
    cp "${REPO_DIR}/.env.example" "${INSTALL_DIR}/.env"
    chmod 640 "${INSTALL_DIR}/.env"
    chown root:"${SERVICE_GROUP}" "${INSTALL_DIR}/.env"
    warn ".env.example copied to .env - EDIT IT BEFORE STARTING: ${INSTALL_DIR}/.env"
else
    fail "No .env or .env.example found. Copy .env.example manually."
fi

chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_DIR}"
log "Application files copied to ${INSTALL_DIR}"

# ============================================================
# STEP 5: Virtual environment Python
# ============================================================
log "Creating Python virtual environment..."

"${PYTHON_VERSION}" -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip -q
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" -q

chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_DIR}/venv"
log "Virtual environment created and packages installed"

# ============================================================
# STEP 6: PostgreSQL
# ============================================================
log "Configuring PostgreSQL..."

# Avvia PostgreSQL
systemctl start postgresql
systemctl enable postgresql

# Genera password casuale se non già in .env
DB_PASSWORD=$(grep "^DB_PASSWORD=" "${INSTALL_DIR}/.env" | cut -d= -f2)

if [[ -z "${DB_PASSWORD}" || "${DB_PASSWORD}" == "change-me" ]]; then
    DB_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)
    sed -i "s/^DB_PASSWORD=.*/DB_PASSWORD=${DB_PASSWORD}/" "${INSTALL_DIR}/.env"
    warn "Generated random DB password (saved to .env)"
fi

# Crea utente e database
su -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'\"" postgres | grep -q 1 || \
    su -c "psql -c \"CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}'\"" postgres

su -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'\"" postgres | grep -q 1 || \
    su -c "psql -c \"CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}\"" postgres

# Aggiorna pg_hba.conf per connessioni locali
PG_HBA=$(su -c "psql -tAc \"SHOW hba_file\"" postgres)
if ! grep -q "${DB_USER}" "${PG_HBA}"; then
    echo "local   ${DB_NAME}   ${DB_USER}   md5" >> "${PG_HBA}"
    systemctl reload postgresql
fi

log "PostgreSQL configured (DB: ${DB_NAME}, User: ${DB_USER})"

# ============================================================
# STEP 7: Schema database
# ============================================================
log "Applying database schema..."

PGPASSWORD="${DB_PASSWORD}" psql \
    -h localhost -U "${DB_USER}" -d "${DB_NAME}" \
    -f "${INSTALL_DIR}/sql/migrations/001_orchestrator_schema.sql" \
    -q && log "Schema applied" || warn "Schema may already exist or failed - check manually"

# ============================================================
# STEP 8: Systemd service
# ============================================================
log "Installing systemd service..."

cp "${REPO_DIR}/systemd/spm-orchestrator.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable spm-orchestrator

log "Systemd service installed (spm-orchestrator)"

# ============================================================
# STEP 9: Firewall (UFW)
# ============================================================
if command -v ufw &>/dev/null; then
    log "Configuring UFW firewall..."
    # Apri porta 5001 solo sulla VNET interna
    ufw allow from 10.172.0.0/16 to any port 5001 comment "SPM Orchestrator API"
    log "UFW: port 5001 open for 10.172.0.0/16"
fi

# ============================================================
# RIEPILOGO
# ============================================================
echo ""
echo "════════════════════════════════════════════════════"
echo -e "${GREEN}  Installation complete!${NC}"
echo "════════════════════════════════════════════════════"
echo ""
echo "  Install dir:  ${INSTALL_DIR}"
echo "  Config file:  ${INSTALL_DIR}/.env"
echo "  Log dir:      ${LOG_DIR}"
echo "  Database:     ${DB_NAME}@localhost"
echo ""
echo "  Next steps:"
echo "  1. Edit config:  nano ${INSTALL_DIR}/.env"
echo "  2. Start:        systemctl start spm-orchestrator"
echo "  3. Check logs:   journalctl -u spm-orchestrator -f"
echo "  4. Test:         curl http://localhost:5001/api/v1/health"
echo ""
warn "Remember to edit .env before starting the service!"
