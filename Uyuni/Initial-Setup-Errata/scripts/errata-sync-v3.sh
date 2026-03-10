#!/bin/bash
################################################################################
# UYUNI Errata Manager - Sync v3.0
#
# Esegue il sync completo tramite /api/sync/auto:
#   - Rileva canali UYUNI attivi (Ubuntu/Debian)
#   - Sync USN solo se ci sono canali Ubuntu
#   - Sync DSA solo se ci sono canali Debian
#   - NVD enrichment (severity reale da CVSS)
#   - Aggiorna cache pacchetti
#   - Push errata pendenti a UYUNI
#
# Usage: ./errata-sync-v3.sh [--nvd-batch N] [--push-limit N]
################################################################################

set -euo pipefail

# ============================================================
# CONFIGURAZIONE
# ============================================================
LOG_FILE="/var/log/errata-sync.log"
LOCK_FILE="/var/run/errata-sync.lock"
ERROR_LOG="/var/log/errata-sync-errors.log"

API="${API:-http://10.172.5.5:5000}"

TIMEOUT_HEALTH=30
TIMEOUT_AUTO=3600   # 60 min: USN + DSA + NVD + push

MAX_RETRIES=3
RETRY_DELAY=60

# Parametri sync (override via argomenti o env)
NVD_BATCH="${NVD_BATCH:-100}"
PUSH_LIMIT="${PUSH_LIMIT:-50}"

# ============================================================
# ARGOMENTI
# ============================================================
while [[ $# -gt 0 ]]; do
    case "$1" in
        --nvd-batch)  NVD_BATCH="$2";  shift 2 ;;
        --push-limit) PUSH_LIMIT="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# ============================================================
# LOGGING
# ============================================================
log() {
    local level="$1"; shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*" | tee -a "$LOG_FILE"
}
log_error() { log "ERROR" "$@" | tee -a "$ERROR_LOG"; }

# ============================================================
# LOCK
# ============================================================
cleanup() {
    rm -f "$LOCK_FILE"
    log "INFO" "Lock released"
}
trap cleanup EXIT

if [[ -f "$LOCK_FILE" ]]; then
    pid=$(cat "$LOCK_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        log "WARNING" "Already running (PID $pid), exiting"
        exit 0
    fi
    rm -f "$LOCK_FILE"
fi
echo $$ > "$LOCK_FILE"
log "INFO" "Lock acquired (PID: $$)"

# ============================================================
# HELPERS
# ============================================================
api_call() {
    local method="$1"
    local endpoint="$2"
    local timeout="${3:-300}"

    local attempt=0
    while [[ $attempt -lt $MAX_RETRIES ]]; do
        attempt=$((attempt + 1))
        log "INFO" "[$method $endpoint] attempt $attempt/$MAX_RETRIES"

        local response
        response=$(curl -sf \
            --max-time "$timeout" \
            -X "$method" \
            -H "Content-Type: application/json" \
            "${API}${endpoint}" 2>&1) && {
            echo "$response"
            return 0
        }

        log "WARNING" "[$endpoint] attempt $attempt failed"
        if [[ $attempt -lt $MAX_RETRIES ]]; then
            sleep "$RETRY_DELAY"
        fi
    done

    log_error "[$endpoint] failed after $MAX_RETRIES attempts"
    return 1
}

check_status() {
    local response="$1"
    local label="$2"
    local status
    status=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "parse_error")
    if [[ "$status" == "success" ]]; then
        log "SUCCESS" "$label completed"
        return 0
    elif [[ "$status" == "warning" ]]; then
        log "WARNING" "$label: $(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message',''))" 2>/dev/null)"
        return 0
    else
        log_error "$label failed (status=$status)"
        return 1
    fi
}

# ============================================================
# MAIN
# ============================================================
START_TIME=$(date +%s)

log "INFO" "=========================================="
log "INFO" "  UYUNI ERRATA MANAGER SYNC v3.0"
log "INFO" "=========================================="
log "INFO" "API: $API"
log "INFO" "NVD batch: $NVD_BATCH | Push limit: $PUSH_LIMIT"

# Health check
log "INFO" "--- Health check ---"
health=$(curl -sf --max-time "$TIMEOUT_HEALTH" "${API}/api/health") || {
    log_error "API non raggiungibile: ${API}/api/health"
    exit 1
}
log "INFO" "Health: $health"

# Sync auto (pipeline completa)
log "INFO" "--- Auto sync (detect → USN/DSA → NVD → packages → push) ---"
response=$(api_call POST "/api/sync/auto?nvd_batch=${NVD_BATCH}&push_limit=${PUSH_LIMIT}" "$TIMEOUT_AUTO")
check_status "$response" "Auto sync"

# Riepilogo
log "INFO" "--- Riepilogo ---"
echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  Distribuzioni attive: {d.get(\"active_distributions\", [])}')
if 'usn' in d:
    u = d['usn']
    print(f'  USN: {u.get(\"processed\",0)} nuovi errata, {u.get(\"packages_saved\",0)} packages')
if 'dsa' in d:
    ds = d['dsa']
    print(f'  DSA: {ds.get(\"total_errata\",0)} nuovi errata, releases={ds.get(\"releases\",[])}')
if 'nvd' in d:
    n = d['nvd']
    print(f'  NVD: {n.get(\"processed\",0)}/{n.get(\"pending_total\",0)} CVEs, {n.get(\"errata_severity_updated\",0)} severity aggiornate')
if 'packages' in d:
    p = d['packages']
    print(f'  Packages: {p.get(\"total_packages_synced\",0)} totali')
if 'push' in d:
    pu = d['push']
    print(f'  Push: {pu.get(\"pushed\",0)} pushed, {pu.get(\"skipped_version_mismatch\",0)} skipped (version)')
    if pu.get('errors'):
        print(f'  Push errors: {pu[\"errors\"]}')
" 2>/dev/null | tee -a "$LOG_FILE"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

log "INFO" "=========================================="
log "INFO" "  SYNC COMPLETATO in ${MINUTES}m ${SECONDS}s"
log "INFO" "=========================================="
