#!/bin/bash
################################################################################
# UYUNI Errata Manager - Sync v3.1
#
# Architettura a 2 container ACI:
#
#   PUBLIC_API  (aci-errata-api, internet pubblico)
#     → /api/sync/usn      — sync Ubuntu Security Notices
#     → /api/sync/dsa      — sync Debian Security Advisories
#     → /api/sync/nvd      — enrichment severity da NVD/CVSS
#
#   INTERNAL_API  (aci-errata-api-internal, VNet Azure)
#     → /api/uyuni/sync-packages — aggiorna cache pacchetti UYUNI
#     → /api/uyuni/push          — push errata a UYUNI Server
#
# I due container condividono lo stesso database PostgreSQL.
# Il container pubblico non ha accesso alla VNet (no UYUNI).
# Il container interno non ha accesso a internet (no USN/DSA/NVD).
#
# Usage:
#   ./errata-sync-v3.sh [--nvd-batch N] [--push-limit N]
#
# Env override:
#   PUBLIC_API=http://...   INTERNAL_API=http://...
#   API_KEY=...             (stesso valore SPM_API_KEY su entrambi i container)
#   NVD_BATCH=100           PUSH_LIMIT=50
################################################################################

set -euo pipefail

# ============================================================
# CONFIGURAZIONE
# ============================================================
LOG_FILE="/var/log/errata-sync.log"
LOCK_FILE="/var/run/errata-sync.lock"
ERROR_LOG="/var/log/errata-sync-errors.log"

# IPs dei due container ACI
PUBLIC_API="${PUBLIC_API:-http://4.232.4.138:5000}"     # aci-errata-api (internet)
INTERNAL_API="${INTERNAL_API:-http://10.172.5.4:5000}"  # aci-errata-api-internal (VNet)
API_KEY="${API_KEY:-spm-key-2024}"

TIMEOUT_HEALTH=30
TIMEOUT_SYNC=3600    # 60 min max per USN+DSA+NVD
TIMEOUT_PUSH=600     # 10 min per packages+push

MAX_RETRIES=3
RETRY_DELAY=60

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
log_error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" | tee -a "$LOG_FILE" | tee -a "$ERROR_LOG"; }

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
    local base_url="$1"
    local method="$2"
    local endpoint="$3"
    local timeout="${4:-300}"

    local attempt=0
    while [[ $attempt -lt $MAX_RETRIES ]]; do
        attempt=$((attempt + 1))
        log "INFO" "[$method ${base_url}${endpoint}] attempt $attempt/$MAX_RETRIES"

        local response
        response=$(curl -sf \
            --max-time "$timeout" \
            -X "$method" \
            -H "Content-Type: application/json" \
            -H "X-API-Key: ${API_KEY}" \
            "${base_url}${endpoint}" 2>&1) && {
            echo "$response"
            return 0
        }

        log "WARNING" "[${endpoint}] attempt $attempt failed"
        [[ $attempt -lt $MAX_RETRIES ]] && sleep "$RETRY_DELAY"
    done

    log_error "[${endpoint}] failed after $MAX_RETRIES attempts"
    return 1
}

check_status() {
    local response="$1"
    local label="$2"
    local status
    status=$(echo "$response" | python3 -c \
        "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null \
        || echo "parse_error")

    if [[ "$status" == "success" ]]; then
        log "SUCCESS" "$label completato"
        return 0
    elif [[ "$status" == "warning" ]]; then
        local msg
        msg=$(echo "$response" | python3 -c \
            "import sys,json; print(json.load(sys.stdin).get('message',''))" 2>/dev/null)
        log "WARNING" "$label: $msg"
        return 0
    else
        log_error "$label fallito (status=$status) — response: ${response:0:200}"
        return 1
    fi
}

health_check() {
    local base_url="$1"
    local label="$2"
    local health
    health=$(curl -sf --max-time "$TIMEOUT_HEALTH" "${base_url}/api/health" 2>&1) || {
        log_error "[$label] non raggiungibile: ${base_url}/api/health"
        return 1
    }
    log "INFO" "[$label] health: $health"
    return 0
}

# ============================================================
# MAIN
# ============================================================
START_TIME=$(date +%s)
ERRORS=0

log "INFO" "=========================================="
log "INFO" "  UYUNI ERRATA MANAGER SYNC v3.1"
log "INFO" "=========================================="
log "INFO" "PUBLIC_API:   $PUBLIC_API"
log "INFO" "INTERNAL_API: $INTERNAL_API"
log "INFO" "NVD batch: $NVD_BATCH | Push limit: $PUSH_LIMIT"

# ============================================================
# FASE 1 — Health check entrambi i container
# ============================================================
log "INFO" "--- [1/5] Health check ---"

health_check "$PUBLIC_API"  "public"  || { log_error "Container pubblico non disponibile — interruzione"; exit 1; }
health_check "$INTERNAL_API" "internal" || { log_error "Container interno non disponibile — interruzione"; exit 1; }

# ============================================================
# FASE 2 — Sync USN (Ubuntu) — container PUBBLICO
# ============================================================
log "INFO" "--- [2/5] Sync Ubuntu USN (container pubblico) ---"
response=$(api_call "$PUBLIC_API" POST "/api/sync/usn" "$TIMEOUT_SYNC") || { ERRORS=$((ERRORS+1)); response="{}"; }
check_status "$response" "USN sync" || ERRORS=$((ERRORS+1))

echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'processed' in d:
    print(f'  USN: {d[\"processed\"]} nuovi errata, {d.get(\"packages_saved\",0)} packages (last known: {d.get(\"last_known\",\"?\")})')
elif 'skipped' in d:
    print(f'  USN: skipped ({d[\"skipped\"]})')
" 2>/dev/null | tee -a "$LOG_FILE" || true

# ============================================================
# FASE 3 — Sync DSA (Debian) — container PUBBLICO
# ============================================================
log "INFO" "--- [3/5] Sync Debian DSA (container pubblico) ---"
response=$(api_call "$PUBLIC_API" POST "/api/sync/dsa" "$TIMEOUT_SYNC") || { ERRORS=$((ERRORS+1)); response="{}"; }
check_status "$response" "DSA sync" || ERRORS=$((ERRORS+1))

echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'total_errata' in d:
    print(f'  DSA: {d[\"total_errata\"]} errata, releases={d.get(\"releases\",[])}')
elif 'skipped' in d:
    print(f'  DSA: skipped ({d[\"skipped\"]})')
" 2>/dev/null | tee -a "$LOG_FILE" || true

# ============================================================
# FASE 4 — NVD enrichment — container PUBBLICO
# ============================================================
log "INFO" "--- [4/5] NVD enrichment (container pubblico) ---"
response=$(api_call "$PUBLIC_API" POST "/api/sync/nvd?batch_size=${NVD_BATCH}" "$TIMEOUT_SYNC") || { ERRORS=$((ERRORS+1)); response="{}"; }
check_status "$response" "NVD sync" || ERRORS=$((ERRORS+1))

echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'processed' in d:
    print(f'  NVD: {d[\"processed\"]}/{d.get(\"pending_total\",\"?\")} CVEs, {d.get(\"errata_severity_updated\",0)} severity aggiornate')
" 2>/dev/null | tee -a "$LOG_FILE" || true

# ============================================================
# FASE 5 — Package cache + Push → UYUNI — container INTERNO
# ============================================================
log "INFO" "--- [5/5] Sync packages + Push UYUNI (container interno) ---"

# 5a. Aggiorna cache pacchetti UYUNI
log "INFO" "  Aggiornamento cache pacchetti..."
response=$(api_call "$INTERNAL_API" POST "/api/uyuni/sync-packages" "$TIMEOUT_PUSH") || { ERRORS=$((ERRORS+1)); response="{}"; }
check_status "$response" "Package cache" || ERRORS=$((ERRORS+1))

echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'total_packages_synced' in d:
    print(f'  Packages: {d[\"total_packages_synced\"]} totali')
" 2>/dev/null | tee -a "$LOG_FILE" || true

# 5b. Push errata a UYUNI
log "INFO" "  Push errata a UYUNI..."
response=$(api_call "$INTERNAL_API" POST "/api/uyuni/push?limit=${PUSH_LIMIT}" "$TIMEOUT_PUSH") || { ERRORS=$((ERRORS+1)); response="{}"; }
check_status "$response" "Push UYUNI" || ERRORS=$((ERRORS+1))

echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'pushed' in d:
    print(f'  Push: {d[\"pushed\"]} pushed, {d.get(\"skipped_version_mismatch\",0)} skipped (version mismatch)')
    if d.get('errors'):
        print(f'  Push errors: {d[\"errors\"]}')
" 2>/dev/null | tee -a "$LOG_FILE" || true

# ============================================================
# RIEPILOGO
# ============================================================
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECS=$((DURATION % 60))

log "INFO" "=========================================="
if [[ $ERRORS -eq 0 ]]; then
    log "INFO" "  SYNC COMPLETATO in ${MINUTES}m ${SECS}s — OK"
else
    log "INFO" "  SYNC COMPLETATO in ${MINUTES}m ${SECS}s — $ERRORS ERRORI"
fi
log "INFO" "=========================================="

exit $([[ $ERRORS -eq 0 ]] && echo 0 || echo 1)
