#!/bin/bash
################################################################################
# UYUNI Errata Manager - Test & Sync Script
#
# Questo script deve essere eseguito da un host con accesso alla VNET
# (es: server UYUNI 10.172.2.5)
#
# ARCHITETTURA A 2 CONTAINER:
# - Container PUBBLICO (4.232.3.251): Sync esterni (USN, DSA, NVD, OVAL)
# - Container INTERNO (10.172.5.4): Push UYUNI + Cache pacchetti
################################################################################

set -euo pipefail

# ============================================================
# CONFIGURAZIONE
# ============================================================
PUBLIC_API="http://4.232.3.251:5000"
INTERNAL_API="http://10.172.5.5:5000"

TIMEOUT_HEALTH=30
TIMEOUT_SHORT=600
TIMEOUT_LONG=1800

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================
# UTILITY FUNCTIONS
# ============================================================
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

test_endpoint() {
    local name="$1"
    local url="$2"

    log_info "Testing $name: $url"

    if response=$(curl -s -m "$TIMEOUT_HEALTH" "$url/api/health" 2>&1); then
        if echo "$response" | grep -q '"api".*"ok"'; then
            log_success "$name is reachable and healthy"
            echo "$response"
            return 0
        else
            log_error "$name responded but unhealthy: $response"
            return 1
        fi
    else
        log_error "$name is unreachable: $response"
        return 1
    fi
}

call_api() {
    local method="$1"
    local url="$2"
    local timeout="$3"
    local description="$4"

    log_info "[$description] $method $url"

    if response=$(curl -s -m "$timeout" -X "$method" "$url" 2>&1); then
        log_success "[$description] Completed"
        echo "$response"
        return 0
    else
        log_error "[$description] Failed: $response"
        return 1
    fi
}

# ============================================================
# TEST FUNCTIONS
# ============================================================
test_connectivity() {
    log_info "============================================================"
    log_info "STEP 1: TESTING CONNECTIVITY"
    log_info "============================================================"

    local public_ok=0
    local internal_ok=0

    if test_endpoint "Public Container" "$PUBLIC_API"; then
        public_ok=1
    fi

    echo ""

    if test_endpoint "Internal Container" "$INTERNAL_API"; then
        internal_ok=1
    fi

    echo ""

    if [ $public_ok -eq 1 ] && [ $internal_ok -eq 1 ]; then
        log_success "Both containers are healthy!"
        return 0
    else
        log_error "One or more containers are not reachable"
        [ $public_ok -eq 0 ] && log_error "- Public container is DOWN"
        [ $internal_ok -eq 0 ] && log_error "- Internal container is DOWN"
        return 1
    fi
}

get_detailed_health() {
    log_info "============================================================"
    log_info "DETAILED HEALTH CHECK"
    log_info "============================================================"

    log_info "Fetching detailed health from internal container..."
    if health=$(curl -s -m "$TIMEOUT_HEALTH" "$INTERNAL_API/api/health/detailed" 2>&1); then
        echo "$health" | python3 -m json.tool 2>/dev/null || echo "$health"
        return 0
    else
        log_error "Failed to get detailed health: $health"
        return 1
    fi
}

# ============================================================
# SYNC FUNCTIONS
# ============================================================
sync_usn() {
    log_info "============================================================"
    log_info "STEP 2: SYNCING UBUNTU USN (via PUBLIC container)"
    log_info "============================================================"

    call_api "POST" "$PUBLIC_API/api/sync/usn" "$TIMEOUT_SHORT" "USN Sync"
}

sync_dsa_full() {
    log_info "============================================================"
    log_info "STEP 3: SYNCING DEBIAN DSA FULL (via PUBLIC container)"
    log_info "============================================================"

    log_warn "This operation may take 15-30 minutes..."
    call_api "POST" "$PUBLIC_API/api/sync/dsa/full" "$TIMEOUT_LONG" "DSA Full Sync"
}

sync_oval() {
    log_info "============================================================"
    log_info "STEP 4: SYNCING OVAL DEFINITIONS (via PUBLIC container)"
    log_info "============================================================"

    log_warn "This operation may take 10-20 minutes..."
    call_api "POST" "$PUBLIC_API/api/sync/oval?platform=all" "$TIMEOUT_LONG" "OVAL Sync"
}

update_package_cache() {
    log_info "============================================================"
    log_info "STEP 5: UPDATING UYUNI PACKAGE CACHE (via INTERNAL container)"
    log_info "============================================================"

    log_warn "This operation may take 5-10 minutes..."
    call_api "POST" "$INTERNAL_API/api/uyuni/sync-packages" "$TIMEOUT_SHORT" "Package Cache Update"
}

push_errata() {
    log_info "============================================================"
    log_info "STEP 6: PUSHING ERRATA TO UYUNI (via INTERNAL container)"
    log_info "============================================================"

    local total_pushed=0
    local batch_limit=20
    local max_batches=50
    local batch=0

    while [ $batch -lt $max_batches ]; do
        log_info "Pushing batch $((batch+1))/$max_batches (limit=$batch_limit)..."

        if response=$(call_api "POST" "$INTERNAL_API/api/uyuni/push?limit=$batch_limit" "$TIMEOUT_SHORT" "Push Batch $((batch+1))"); then
            pushed=$(echo "$response" | grep -o '"pushed":[0-9]*' | cut -d':' -f2)

            if [ -z "$pushed" ] || [ "$pushed" -eq 0 ]; then
                log_info "No more pending errata to push"
                break
            fi

            total_pushed=$((total_pushed + pushed))
            log_success "Pushed $pushed errata (total: $total_pushed)"

            ((batch++))
            sleep 2
        else
            log_error "Push batch failed, stopping"
            break
        fi
    done

    log_success "Push completed: $total_pushed total errata pushed"
}

sync_nvd() {
    log_info "============================================================"
    log_info "STEP 7: ENRICHING CVE DATA FROM NVD (via PUBLIC container)"
    log_info "============================================================"

    log_warn "This operation is optional and may take time..."
    log_info "Syncing with prioritization (critical/high first)..."

    call_api "POST" "$PUBLIC_API/api/sync/nvd?batch_size=100&prioritize=true" "$TIMEOUT_SHORT" "NVD Sync" || log_warn "NVD sync had issues, continuing..."
}

show_statistics() {
    log_info "============================================================"
    log_info "FINAL STATISTICS"
    log_info "============================================================"

    log_info "Overview:"
    if stats=$(curl -s -m "$TIMEOUT_HEALTH" "$INTERNAL_API/api/stats/overview" 2>&1); then
        echo "$stats" | python3 -m json.tool 2>/dev/null || echo "$stats"
    fi

    echo ""

    log_info "Package stats:"
    if pkg_stats=$(curl -s -m "$TIMEOUT_HEALTH" "$INTERNAL_API/api/stats/packages" 2>&1); then
        echo "$pkg_stats" | python3 -m json.tool 2>/dev/null || echo "$pkg_stats"
    fi
}

# ============================================================
# MAIN MENU
# ============================================================
show_menu() {
    echo ""
    echo "======================================================"
    echo "  UYUNI ERRATA MANAGER - Test & Sync Tool"
    echo "======================================================"
    echo ""
    echo "Options:"
    echo "  1) Test connectivity only"
    echo "  2) Show detailed health"
    echo "  3) Full sync (USN + DSA + OVAL + Cache + Push)"
    echo "  4) Quick sync (USN + Cache + Push)"
    echo "  5) Sync USN only"
    echo "  6) Sync DSA full only"
    echo "  7) Sync OVAL only"
    echo "  8) Update package cache only"
    echo "  9) Push errata to UYUNI only"
    echo " 10) Sync NVD enrichment"
    echo " 11) Show statistics"
    echo "  q) Quit"
    echo ""
    echo -n "Select option: "
}

# ============================================================
# MAIN EXECUTION
# ============================================================
main() {
    if [ $# -eq 0 ]; then
        # Interactive mode
        while true; do
            show_menu
            read -r choice

            case $choice in
                1)
                    test_connectivity
                    ;;
                2)
                    get_detailed_health
                    ;;
                3)
                    log_info "Starting FULL SYNC..."
                    test_connectivity && \
                    sync_usn && \
                    sync_dsa_full && \
                    sync_oval && \
                    update_package_cache && \
                    push_errata && \
                    sync_nvd && \
                    show_statistics
                    log_success "Full sync completed!"
                    ;;
                4)
                    log_info "Starting QUICK SYNC..."
                    test_connectivity && \
                    sync_usn && \
                    update_package_cache && \
                    push_errata && \
                    show_statistics
                    log_success "Quick sync completed!"
                    ;;
                5)
                    sync_usn
                    ;;
                6)
                    sync_dsa_full
                    ;;
                7)
                    sync_oval
                    ;;
                8)
                    update_package_cache
                    ;;
                9)
                    push_errata
                    ;;
                10)
                    sync_nvd
                    ;;
                11)
                    show_statistics
                    ;;
                q|Q)
                    log_info "Exiting..."
                    exit 0
                    ;;
                *)
                    log_error "Invalid option"
                    ;;
            esac

            echo ""
            echo "Press Enter to continue..."
            read -r
        done
    else
        # Non-interactive mode based on argument
        case "$1" in
            test)
                test_connectivity
                ;;
            health)
                get_detailed_health
                ;;
            full)
                test_connectivity && \
                sync_usn && \
                sync_dsa_full && \
                sync_oval && \
                update_package_cache && \
                push_errata && \
                sync_nvd && \
                show_statistics
                ;;
            quick)
                test_connectivity && \
                sync_usn && \
                update_package_cache && \
                push_errata && \
                show_statistics
                ;;
            stats)
                show_statistics
                ;;
            *)
                echo "Usage: $0 [test|health|full|quick|stats]"
                echo "  test  - Test connectivity only"
                echo "  health - Show detailed health"
                echo "  full  - Full sync (USN+DSA+OVAL+Cache+Push+NVD)"
                echo "  quick - Quick sync (USN+Cache+Push)"
                echo "  stats - Show statistics"
                echo ""
                echo "Run without arguments for interactive menu"
                exit 1
                ;;
        esac
    fi
}

# Check dependencies
for cmd in curl python3; do
    if ! command -v $cmd &> /dev/null; then
        log_error "Required command '$cmd' not found. Please install it."
        exit 1
    fi
done

main "$@"
