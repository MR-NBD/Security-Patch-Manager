#!/bin/bash
#===============================================================================
# SPM - Setup Test Service per Remediation Demo
# Da eseguire su una VM Ubuntu 24.04 gestita da UYUNI
#===============================================================================

set -e

echo "=============================================="
echo "  SPM Test Service Setup"
echo "=============================================="

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

#-------------------------------------------------------------------------------
# 1. Crea il servizio di test
#-------------------------------------------------------------------------------
log_info "Creazione script servizio..."

sudo tee /opt/spm-test-service.sh > /dev/null << 'SCRIPT'
#!/bin/bash
#===============================================================================
# SPM Test Service - Servizio dummy per test remediation
#===============================================================================

LOG_FILE="/var/log/spm-test-service.log"
PID_FILE="/var/run/spm-test-service.pid"
HEALTH_FILE="/tmp/spm-test-health"

# Cleanup on exit
cleanup() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Service stopping (signal received)" >> "$LOG_FILE"
    rm -f "$PID_FILE" "$HEALTH_FILE"
    exit 0
}

trap cleanup SIGTERM SIGINT SIGHUP

# Write PID
echo $$ > "$PID_FILE"
echo "healthy" > "$HEALTH_FILE"

# Log startup
echo "$(date '+%Y-%m-%d %H:%M:%S') - Service started (PID: $$)" >> "$LOG_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') - Host: $(hostname)" >> "$LOG_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') - IP: $(hostname -I | awk '{print $1}')" >> "$LOG_FILE"

# Main loop
COUNTER=0
while true; do
    COUNTER=$((COUNTER + 1))
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Heartbeat #$COUNTER" >> "$LOG_FILE"

    # Simula qualche lavoro
    LOAD=$(awk '{print $1}' /proc/loadavg)
    MEM=$(free -m | awk '/Mem:/ {printf "%.1f%%", $3/$2*100}')
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Status: Load=$LOAD, Memory=$MEM" >> "$LOG_FILE"

    # Update health file
    echo "healthy $(date +%s)" > "$HEALTH_FILE"

    sleep 30
done
SCRIPT

sudo chmod +x /opt/spm-test-service.sh

#-------------------------------------------------------------------------------
# 2. Crea systemd unit
#-------------------------------------------------------------------------------
log_info "Creazione systemd unit..."

sudo tee /etc/systemd/system/spm-test-service.service > /dev/null << 'UNIT'
[Unit]
Description=SPM Test Service for Remediation Demo
Documentation=https://github.com/your-org/spm
After=network.target

[Service]
Type=simple
ExecStart=/opt/spm-test-service.sh
ExecStop=/bin/kill -SIGTERM $MAINPID
PIDFile=/var/run/spm-test-service.pid
Restart=no
# Restart=no per permettere test remediation manuale
# In produzione usa: Restart=on-failure, RestartSec=5s
User=root
Group=root
StandardOutput=journal
StandardError=journal
SyslogIdentifier=spm-test-service

[Install]
WantedBy=multi-user.target
UNIT

#-------------------------------------------------------------------------------
# 3. Abilita e avvia servizio
#-------------------------------------------------------------------------------
log_info "Abilitazione servizio..."

sudo systemctl daemon-reload
sudo systemctl enable spm-test-service
sudo systemctl start spm-test-service

#-------------------------------------------------------------------------------
# 4. Crea script di utilità
#-------------------------------------------------------------------------------
log_info "Creazione script utilità..."

# Script per simulare crash
sudo tee /opt/spm-simulate-crash.sh > /dev/null << 'CRASH'
#!/bin/bash
# Simula crash del servizio (per test)
echo "Simulazione crash spm-test-service..."
sudo systemctl stop spm-test-service
echo "Servizio stoppato. Attendi remediation automatica o riavvia manualmente con:"
echo "  sudo systemctl start spm-test-service"
CRASH
sudo chmod +x /opt/spm-simulate-crash.sh

# Script per verificare stato
sudo tee /opt/spm-check-status.sh > /dev/null << 'STATUS'
#!/bin/bash
echo "=== SPM Test Service Status ==="
echo ""
systemctl status spm-test-service --no-pager
echo ""
echo "=== Ultimi Log ==="
journalctl -u spm-test-service -n 10 --no-pager
echo ""
echo "=== Health File ==="
cat /tmp/spm-test-health 2>/dev/null || echo "Health file non trovato"
STATUS
sudo chmod +x /opt/spm-check-status.sh

#-------------------------------------------------------------------------------
# 5. Verifica installazione
#-------------------------------------------------------------------------------
log_info "Verifica installazione..."

sleep 2

if systemctl is-active --quiet spm-test-service; then
    log_info "Servizio attivo e funzionante!"
    echo ""
    echo "=============================================="
    echo "  SETUP COMPLETATO"
    echo "=============================================="
    echo ""
    echo "Comandi utili:"
    echo "  - Verifica stato:    /opt/spm-check-status.sh"
    echo "  - Simula crash:      /opt/spm-simulate-crash.sh"
    echo "  - Log live:          journalctl -fu spm-test-service"
    echo "  - Restart manuale:   sudo systemctl restart spm-test-service"
    echo ""
    echo "Informazioni Salt:"
    echo "  - Minion ID:         $(cat /etc/salt/minion_id 2>/dev/null || hostname)"
    echo "  - Service name:      spm-test-service"
    echo ""
    echo "Test Salt dal server UYUNI:"
    echo "  salt '$(hostname)' service.status spm-test-service"
    echo "  salt '$(hostname)' service.restart spm-test-service"
    echo ""
else
    log_error "Il servizio non si è avviato correttamente!"
    systemctl status spm-test-service --no-pager
    exit 1
fi
