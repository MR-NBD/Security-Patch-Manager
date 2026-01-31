#!/bin/bash
#===============================================================================
# SPM - Test End-to-End Remediation
# Simula il flusso completo: alert → n8n → salt → report
#===============================================================================

set -e

# Configurazione
N8N_URL="${N8N_URL:-http://localhost:5678}"
WEBHOOK_PATH="webhook/service-alert"
UYUNI_SERVER="${UYUNI_SERVER:-10.172.2.17}"
TEST_MINION="${TEST_MINION:-}"  # Da impostare

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

print_banner() {
    echo ""
    echo "=============================================="
    echo "  SPM Service Remediation - Test E2E"
    echo "=============================================="
    echo ""
}

#-------------------------------------------------------------------------------
# Funzioni di test
#-------------------------------------------------------------------------------

test_salt_connectivity() {
    log_step "1. Test connettività Salt..."

    if [ -z "$TEST_MINION" ]; then
        log_warn "TEST_MINION non impostato. Cerco minion disponibili..."

        # Lista minion accettati
        MINIONS=$(ssh root@$UYUNI_SERVER "podman exec uyuni-server salt-key -L --out=json" 2>/dev/null | jq -r '.minions[]' | head -5)

        if [ -z "$MINIONS" ]; then
            log_error "Nessun minion trovato!"
            return 1
        fi

        echo "Minion disponibili:"
        echo "$MINIONS"
        echo ""
        read -p "Inserisci il nome del minion da testare: " TEST_MINION
    fi

    # Test ping
    PING_RESULT=$(ssh root@$UYUNI_SERVER "podman exec uyuni-server salt '$TEST_MINION' test.ping" 2>/dev/null)

    if echo "$PING_RESULT" | grep -q "True"; then
        log_info "Salt ping OK per $TEST_MINION"
        return 0
    else
        log_error "Salt ping FAILED per $TEST_MINION"
        echo "$PING_RESULT"
        return 1
    fi
}

test_service_status() {
    log_step "2. Verifica servizio spm-test-service..."

    STATUS=$(ssh root@$UYUNI_SERVER "podman exec uyuni-server salt '$TEST_MINION' service.status spm-test-service" 2>/dev/null)

    echo "$STATUS"

    if echo "$STATUS" | grep -q "True"; then
        log_info "Servizio attivo"
        return 0
    else
        log_warn "Servizio non attivo - verrà avviato"
        ssh root@$UYUNI_SERVER "podman exec uyuni-server salt '$TEST_MINION' service.start spm-test-service" 2>/dev/null
        return 0
    fi
}

simulate_service_crash() {
    log_step "3. Simulazione crash servizio..."

    log_warn "Stopping spm-test-service su $TEST_MINION..."
    ssh root@$UYUNI_SERVER "podman exec uyuni-server salt '$TEST_MINION' service.stop spm-test-service" 2>/dev/null

    sleep 2

    # Verifica che sia effettivamente stoppato
    STATUS=$(ssh root@$UYUNI_SERVER "podman exec uyuni-server salt '$TEST_MINION' service.status spm-test-service" 2>/dev/null)

    if echo "$STATUS" | grep -q "False"; then
        log_info "Servizio stoppato con successo (simulazione crash)"
        return 0
    else
        log_error "Impossibile stoppare il servizio"
        return 1
    fi
}

send_webhook_alert() {
    log_step "4. Invio alert webhook a N8N..."

    # Payload alert (formato Prometheus-like)
    PAYLOAD=$(cat << EOF
{
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "ServiceDown",
        "instance": "$TEST_MINION:9100",
        "job": "node",
        "service": "spm-test-service",
        "severity": "critical",
        "organization": "test"
      },
      "annotations": {
        "description": "Service spm-test-service is down on $TEST_MINION",
        "summary": "Service Down Alert"
      }
    }
  ]
}
EOF
)

    echo "Payload:"
    echo "$PAYLOAD" | jq .
    echo ""

    # Invia webhook
    RESPONSE=$(curl -s -X POST "$N8N_URL/$WEBHOOK_PATH" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD")

    echo "Response:"
    echo "$RESPONSE" | jq . 2>/dev/null || echo "$RESPONSE"

    if echo "$RESPONSE" | grep -q "success.*true\|resolved\|processed"; then
        log_info "Webhook processato con successo"
        return 0
    else
        log_warn "Risposta webhook: $RESPONSE"
        return 0  # Continua comunque
    fi
}

verify_remediation() {
    log_step "5. Verifica remediation..."

    # Attendi che il workflow completi
    log_info "Attesa completamento workflow (10s)..."
    sleep 10

    # Verifica stato servizio
    STATUS=$(ssh root@$UYUNI_SERVER "podman exec uyuni-server salt '$TEST_MINION' service.status spm-test-service" 2>/dev/null)

    echo ""
    echo "Stato servizio dopo remediation:"
    echo "$STATUS"
    echo ""

    if echo "$STATUS" | grep -q "True"; then
        log_info "REMEDIATION RIUSCITA - Servizio riavviato correttamente"
        return 0
    else
        log_error "REMEDIATION FALLITA - Servizio ancora fermo"
        return 1
    fi
}

test_direct_salt_restart() {
    log_step "Test diretto Salt (senza N8N)..."

    echo "Eseguo: salt '$TEST_MINION' service.restart spm-test-service"
    RESULT=$(ssh root@$UYUNI_SERVER "podman exec uyuni-server salt '$TEST_MINION' service.restart spm-test-service" 2>/dev/null)

    echo "$RESULT"

    if echo "$RESULT" | grep -q "True"; then
        log_info "Restart diretto OK"
        return 0
    else
        log_error "Restart diretto FAILED"
        return 1
    fi
}

#-------------------------------------------------------------------------------
# Menu principale
#-------------------------------------------------------------------------------

show_menu() {
    echo ""
    echo "Seleziona test da eseguire:"
    echo "  1) Test completo E2E (tutti gli step)"
    echo "  2) Solo test connettività Salt"
    echo "  3) Solo simulazione crash"
    echo "  4) Solo invio webhook"
    echo "  5) Solo verifica remediation"
    echo "  6) Test Salt diretto (senza N8N)"
    echo "  7) Configura variabili"
    echo "  q) Esci"
    echo ""
}

configure_vars() {
    echo ""
    echo "Configurazione attuale:"
    echo "  N8N_URL=$N8N_URL"
    echo "  UYUNI_SERVER=$UYUNI_SERVER"
    echo "  TEST_MINION=$TEST_MINION"
    echo ""

    read -p "N8N URL [$N8N_URL]: " new_n8n
    [ -n "$new_n8n" ] && N8N_URL="$new_n8n"

    read -p "UYUNI Server [$UYUNI_SERVER]: " new_uyuni
    [ -n "$new_uyuni" ] && UYUNI_SERVER="$new_uyuni"

    read -p "Test Minion [$TEST_MINION]: " new_minion
    [ -n "$new_minion" ] && TEST_MINION="$new_minion"

    echo ""
    log_info "Configurazione aggiornata"
}

run_full_e2e() {
    print_banner

    log_info "Configurazione:"
    echo "  N8N URL:      $N8N_URL"
    echo "  UYUNI Server: $UYUNI_SERVER"
    echo "  Test Minion:  ${TEST_MINION:-<da selezionare>}"
    echo ""

    # Esegui tutti i test in sequenza
    test_salt_connectivity || exit 1
    echo ""

    test_service_status || exit 1
    echo ""

    simulate_service_crash || exit 1
    echo ""

    send_webhook_alert
    echo ""

    verify_remediation

    echo ""
    echo "=============================================="
    echo "  TEST E2E COMPLETATO"
    echo "=============================================="
}

#-------------------------------------------------------------------------------
# Main
#-------------------------------------------------------------------------------

# Se eseguito con argomenti
if [ $# -gt 0 ]; then
    case "$1" in
        --full|-f)
            run_full_e2e
            ;;
        --salt-test|-s)
            test_salt_connectivity
            ;;
        --crash|-c)
            simulate_service_crash
            ;;
        --webhook|-w)
            send_webhook_alert
            ;;
        --verify|-v)
            verify_remediation
            ;;
        --direct|-d)
            test_direct_salt_restart
            ;;
        --help|-h)
            echo "Usage: $0 [option]"
            echo "Options:"
            echo "  --full, -f     Test completo E2E"
            echo "  --salt-test, -s    Test connettività Salt"
            echo "  --crash, -c    Simula crash servizio"
            echo "  --webhook, -w  Invia webhook alert"
            echo "  --verify, -v   Verifica remediation"
            echo "  --direct, -d   Test Salt diretto"
            echo ""
            echo "Environment variables:"
            echo "  N8N_URL        URL di N8N (default: http://localhost:5678)"
            echo "  UYUNI_SERVER   IP/hostname UYUNI (default: 10.172.2.17)"
            echo "  TEST_MINION    Salt minion ID da testare"
            ;;
        *)
            log_error "Opzione non riconosciuta: $1"
            exit 1
            ;;
    esac
    exit $?
fi

# Menu interattivo
print_banner

while true; do
    show_menu
    read -p "Scelta: " choice

    case "$choice" in
        1) run_full_e2e ;;
        2) test_salt_connectivity ;;
        3) simulate_service_crash ;;
        4) send_webhook_alert ;;
        5) verify_remediation ;;
        6) test_direct_salt_restart ;;
        7) configure_vars ;;
        q|Q) echo "Bye!"; exit 0 ;;
        *) log_warn "Scelta non valida" ;;
    esac
done
