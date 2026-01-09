#!/bin/bash
################################################################################
# UYUNI Errata Manager - Automazione Sync v2.5 - IMPROVED
#
# FIX #6: Error handling robusto, retry logic, logging dettagliato
#
# Questo script automatizza il sync completo di:
# - Ubuntu Security Notices (USN) - incrementale
# - Debian Security Advisories (DSA) - completo automatico
# - NVD CVE enrichment - prioritizzato
# - OVAL definitions per CVE audit
# - Push a UYUNI con version matching
#
# CHANGELOG v2.5:
# - Retry automatico su failure (max 3 tentativi)
# - Lock file per prevenire esecuzioni concorrenti
# - Health check pre-sync
# - Alerting via email su errori critici
# - Metriche dettagliate in log
# - Timeout configurabili
################################################################################

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# ============================================================
# CONFIGURAZIONE
# ============================================================
LOG_FILE="/var/log/errata-sync.log"
LOCK_FILE="/var/run/errata-sync.lock"
ERROR_LOG="/var/log/errata-sync-errors.log"

# API Endpoints (modifica con i tuoi IP)
PUBLIC_API="${PUBLIC_API:-http://4.232.4.154:5000}"        # Container pubblico (USN, DSA, NVD, OVAL)
INTERNAL_API="${INTERNAL_API:-http://10.172.5.5:5000}"    # Container interno (UYUNI push, Cache)

# Timeouts (secondi)
TIMEOUT_HEALTH=30
TIMEOUT_USN=600         # 10 minuti
TIMEOUT_DSA=1800        # 30 minuti (full sync)
TIMEOUT_NVD=900         # 15 minuti
TIMEOUT_OVAL=1200       # 20 minuti
TIMEOUT_PUSH=300        # 5 minuti

# Retry configuration
MAX_RETRIES=3
RETRY_DELAY=60  # seconds

# Alert email (opzionale)
ALERT_EMAIL="${ALERT_EMAIL:-}"

# ============================================================
# LOGGING FUNCTIONS
# ============================================================
log() {
    local level="$1"
    shift
    local message="$*"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $message" | tee -a "$LOG_FILE"
}

log_info() {
    log "INFO" "$@"
}

log_warn() {
    log "WARN" "$@"
}

log_error() {
    log "ERROR" "$@"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$ERROR_LOG"
}

log_success() {
    log "SUCCESS" "$@"
}

# ============================================================
# UTILITY FUNCTIONS
# ============================================================
acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        local pid
        pid=$(cat "$LOCK_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            log_error "Another instance is running (PID: $pid). Exiting."
            exit 1
        else
            log_warn "Stale lock file found (PID: $pid). Removing..."
            rm -f "$LOCK_FILE"
        fi
    fi

    echo $$ > "$LOCK_FILE"
    log_info "Lock acquired (PID: $$)"
}

release_lock() {
    rm -f "$LOCK_FILE"
    log_info "Lock released"
}

# Trap per rilasciare lock anche in caso di errore
trap release_lock EXIT INT TERM

send_alert() {
    local subject="$1"
    local body="$2"

    if [ -n "$ALERT_EMAIL" ]; then
        echo "$body" | mail -s "[UYUNI Errata] $subject" "$ALERT_EMAIL" 2>/dev/null || true
    fi
}

# ============================================================
# API CALL con RETRY LOGIC
# ============================================================
call_api() {
    local method="$1"
    local url="$2"
    local timeout="$3"
    local description="$4"

    local attempt=1
    local response
    local http_code

    while [ $attempt -le $MAX_RETRIES ]; do
        log_info "[$description] Attempt $attempt/$MAX_RETRIES: $method $url"

        if response=$(curl -s -w "\n%{http_code}" -X "$method" -m "$timeout" "$url" 2>&1); then
            http_code=$(echo "$response" | tail -n1)
            body=$(echo "$response" | sed '$d')

            if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
                log_success "[$description] HTTP $http_code - Success"
                echo "$body"
                return 0
            else
                log_warn "[$description] HTTP $http_code - Failed (attempt $attempt/$MAX_RETRIES)"
                echo "$body" | head -n 5 | tee -a "$LOG_FILE"
            fi
        else
            log_warn "[$description] Request failed (attempt $attempt/$MAX_RETRIES): Network error or timeout"
        fi

        if [ $attempt -lt $MAX_RETRIES ]; then
            log_info "Retrying in ${RETRY_DELAY}s..."
            sleep $RETRY_DELAY
        fi

        ((attempt++))
    done

    log_error "[$description] Failed after $MAX_RETRIES attempts"
    return 1
}

# ============================================================
# HEALTH CHECK
# ============================================================
health_check() {
    log_info "========== HEALTH CHECK =========="

    # Check container pubblico
    if ! call_api "GET" "$PUBLIC_API/api/health" "$TIMEOUT_HEALTH" "Public API Health" > /dev/null; then
        log_error "Public API health check failed"
        send_alert "Health Check Failed" "Public API ($PUBLIC_API) is not responding"
        return 1
    fi

    # Check container interno
    if ! call_api "GET" "$INTERNAL_API/api/health/detailed" "$TIMEOUT_HEALTH" "Internal API Health" > /dev/null; then
        log_error "Internal API health check failed"
        send_alert "Health Check Failed" "Internal API ($INTERNAL_API) is not responding"
        return 1
    fi

    # Check cache freshness
    local health_response
    health_response=$(call_api "GET" "$INTERNAL_API/api/health/detailed" "$TIMEOUT_HEALTH" "Health Detail")

    local cache_age_hours
    cache_age_hours=$(echo "$health_response" | jq -r '.cache.age_hours // 999')

    if (( $(echo "$cache_age_hours > 48" | bc -l) )); then
        log_warn "Package cache is stale (${cache_age_hours}h old). Consider running /api/uyuni/sync-packages"
    fi

    log_success "Health check passed"
    return 0
}

# ============================================================
# SYNC FUNCTIONS
# ============================================================
sync_usn() {
    log_info "========== SYNCING UBUNTU USN =========="

    local response
    if response=$(call_api "POST" "$PUBLIC_API/api/sync/usn" "$TIMEOUT_USN" "USN Sync"); then
        local processed
        local packages_saved
        processed=$(echo "$response" | jq -r '.processed // 0')
        packages_saved=$(echo "$response" | jq -r '.packages_saved // 0')

        log_success "USN sync completed: $processed errata, $packages_saved packages"
        echo "$response" | jq '.' >> "$LOG_FILE"
        return 0
    else
        log_error "USN sync failed"
        send_alert "USN Sync Failed" "Failed to sync Ubuntu Security Notices after $MAX_RETRIES attempts"
        return 1
    fi
}

sync_dsa_full() {
    log_info "========== SYNCING DEBIAN DSA (FULL AUTO) =========="

    local response
    if response=$(call_api "POST" "$PUBLIC_API/api/sync/dsa/full" "$TIMEOUT_DSA" "DSA Full Sync"); then
        local processed
        local packages_saved
        processed=$(echo "$response" | jq -r '.total_errata_created // 0')
        packages_saved=$(echo "$response" | jq -r '.total_packages_saved // 0')

        log_success "DSA full sync completed: $processed errata, $packages_saved packages"
        echo "$response" | jq '.' >> "$LOG_FILE"
        return 0
    else
        log_error "DSA full sync failed"
        send_alert "DSA Sync Failed" "Failed to sync Debian Security Advisories after $MAX_RETRIES attempts"
        return 1
    fi
}

sync_nvd() {
    log_info "========== SYNCING NVD CVE DATA =========="
    log_info "Using PUBLIC container (has internet access)"

    local batch_size=100
    local total_processed=0
    local continue_sync=true

    while $continue_sync; do
        local response
        if response=$(call_api "POST" "$PUBLIC_API/api/sync/nvd?batch_size=$batch_size&prioritize=true" "$TIMEOUT_NVD" "NVD Sync Batch"); then
            local processed
            processed=$(echo "$response" | jq -r '.processed // 0')
            total_processed=$((total_processed + processed))

            log_info "NVD batch processed: $processed CVEs (total: $total_processed)"

            if [ "$processed" -eq 0 ]; then
                continue_sync=false
            fi
        else
            log_warn "NVD sync batch failed, continuing..."
            break
        fi
    done

    log_success "NVD sync completed: $total_processed CVEs enriched"
    return 0
}

sync_oval() {
    log_info "========== SYNCING OVAL DEFINITIONS =========="
    log_info "Using PUBLIC container (has internet access)"

    local response
    if response=$(call_api "POST" "$PUBLIC_API/api/sync/oval?platform=all" "$TIMEOUT_OVAL" "OVAL Sync"); then
        local processed
        processed=$(echo "$response" | jq -r '.total_processed // 0')

        log_success "OVAL sync completed: $processed definitions"
        echo "$response" | jq '.' >> "$LOG_FILE"
        return 0
    else
        log_error "OVAL sync failed"
        return 1
    fi
}

update_package_cache() {
    log_info "========== UPDATING UYUNI PACKAGE CACHE =========="

    local response
    if response=$(call_api "POST" "$INTERNAL_API/api/uyuni/sync-packages" "$TIMEOUT_PUSH" "Package Cache Sync"); then
        local total_packages
        total_packages=$(echo "$response" | jq -r '.total_packages_synced // 0')

        log_success "Package cache updated: $total_packages packages"
        echo "$response" | jq '.' >> "$LOG_FILE"
        return 0
    else
        log_error "Package cache update failed"
        send_alert "Cache Update Failed" "Failed to sync UYUNI package cache"
        return 1
    fi
}

push_to_uyuni() {
    log_info "========== PUSHING ERRATA TO UYUNI =========="

    local total_pushed=0
    local batch_limit=20
    local max_iterations=500
    local iteration=0

    while [ $iteration -lt $max_iterations ]; do
        local response
        if response=$(call_api "POST" "$INTERNAL_API/api/uyuni/push?limit=$batch_limit" "$TIMEOUT_PUSH" "UYUNI Push Batch $((iteration+1))"); then
            local pushed
            pushed=$(echo "$response" | jq -r '.pushed // 0')
            total_pushed=$((total_pushed + pushed))

            log_info "Batch $((iteration+1)): Pushed $pushed errata (total: $total_pushed)"

            if [ "$pushed" -eq 0 ]; then
                log_info "No more pending errata to push"
                break
            fi

            # Check for warnings
            local skipped_version
            skipped_version=$(echo "$response" | jq -r '.skipped_version_mismatch // 0')
            if [ "$skipped_version" -gt 0 ]; then
                log_warn "Skipped $skipped_version errata due to version mismatch"
            fi
        else
            log_error "Push batch $((iteration+1)) failed, stopping"
            break
        fi

        ((iteration++))
        sleep 1  # Rate limiting
    done

    if [ $total_pushed -gt 0 ]; then
        log_success "UYUNI push completed: $total_pushed errata pushed in $iteration batches"
        return 0
    else
        log_warn "No errata were pushed (might be all synced already)"
        return 0
    fi
}

# ============================================================
# STATISTICS
# ============================================================
print_statistics() {
    log_info "========== SYNC STATISTICS =========="

    local stats
    if stats=$(call_api "GET" "$INTERNAL_API/api/stats/overview" "$TIMEOUT_HEALTH" "Stats Overview"); then
        echo "$stats" | jq '.' | tee -a "$LOG_FILE"
    fi

    local pkg_stats
    if pkg_stats=$(call_api "GET" "$INTERNAL_API/api/stats/packages" "$TIMEOUT_HEALTH" "Package Stats"); then
        echo "$pkg_stats" | jq '.' | tee -a "$LOG_FILE"
    fi
}

# ============================================================
# MAIN EXECUTION
# ============================================================
main() {
    log_info "=========================================="
    log_info "  UYUNI ERRATA MANAGER - SYNC v2.5"
    log_info "=========================================="
    log_info "Start time: $(date)"

    local start_time
    start_time=$(date +%s)

    # Acquire lock
    acquire_lock

    # Pre-sync health check
    if ! health_check; then
        log_error "Health check failed, aborting sync"
        exit 1
    fi

    # Sync pipeline
    local errors=0

    # Step 1: Sync external sources (USN, DSA)
    sync_usn || ((errors++))
    sync_dsa_full || ((errors++))

    # Step 2: Update package cache
    update_package_cache || ((errors++))

    # Step 3: Push errata to UYUNI
    push_to_uyuni || ((errors++))

    # Step 4: Enrich with NVD data (non-blocking)
    sync_nvd || log_warn "NVD sync had issues, continuing..."

    # Step 5: Sync OVAL for CVE audit (non-blocking)
    sync_oval || log_warn "OVAL sync had issues, continuing..."

    # Statistics
    print_statistics

    # Summary
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local duration_min=$((duration / 60))
    local duration_sec=$((duration % 60))

    log_info "=========================================="
    log_info "  SYNC COMPLETED"
    log_info "=========================================="
    log_info "End time: $(date)"
    log_info "Duration: ${duration_min}m ${duration_sec}s"
    log_info "Errors encountered: $errors"

    if [ $errors -gt 0 ]; then
        log_error "Sync completed with $errors errors. Check $ERROR_LOG for details."
        send_alert "Sync Completed with Errors" "Errata sync finished but encountered $errors errors. Check logs: $LOG_FILE"
        exit 1
    else
        log_success "All sync operations completed successfully!"
        exit 0
    fi
}

# ============================================================
# SCRIPT EXECUTION
# ============================================================
# Check dependencies
for cmd in curl jq bc; do
    if ! command -v $cmd &> /dev/null; then
        echo "ERROR: Required command '$cmd' not found. Please install it."
        exit 1
    fi
done

# Run main
main "$@"
