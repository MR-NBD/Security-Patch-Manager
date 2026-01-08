#!/bin/bash
################################################################################
# UYUNI Errata Manager - UYUNI Server Sync Script
#
# Questo script deve essere eseguito DAL SERVER UYUNI (10.172.2.5)
# Opera SOLO sul container INTERNO (nella stessa VNET)
#
# Per i sync esterni (USN, DSA, OVAL, NVD) usa lo script remoto
################################################################################

set -euo pipefail

# ============================================================
# CONFIGURAZIONE
# ============================================================
INTERNAL_API="http://10.172.5.5:5000"

TIMEOUT_HEALTH=30
TIMEOUT_CACHE=900
TIMEOUT_PUSH=300

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============================================================
# LOGGING
# ============================================================
log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ============================================================
# UTILITY
# ============================================================
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
# FUNCTIONS
# ============================================================
test_connectivity() {
    log_info "============================================================"
    log_info "TESTING INTERNAL CONTAINER CONNECTIVITY"
    log_info "============================================================"

    if response=$(curl -s -m "$TIMEOUT_HEALTH" "$INTERNAL_API/api/health" 2>&1); then
        if echo "$response" | grep -q '"api".*"ok"'; then
            log_success "Internal container is healthy"
            echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
            return 0
        else
            log_error "Internal container unhealthy: $response"
            return 1
        fi
    else
        log_error "Internal container unreachable: $response"
        return 1
    fi
}

get_health() {
    log_info "============================================================"
    log_info "DETAILED HEALTH CHECK"
    log_info "============================================================"

    if health=$(curl -s -m "$TIMEOUT_HEALTH" "$INTERNAL_API/api/health/detailed" 2>&1); then
        echo "$health" | python3 -m json.tool 2>/dev/null || echo "$health"
        return 0
    else
        log_error "Failed to get health: $health"
        return 1
    fi
}

update_cache() {
    log_info "============================================================"
    log_info "UPDATING UYUNI PACKAGE CACHE"
    log_info "============================================================"
    log_warn "This may take 5-10 minutes..."

    call_api "POST" "$INTERNAL_API/api/uyuni/sync-packages" "$TIMEOUT_CACHE" "Package Cache Update"
}

push_errata() {
    log_info "============================================================"
    log_info "PUSHING ERRATA TO UYUNI"
    log_info "============================================================"

    local total_pushed=0
    local batch_limit=20
    local max_batches=50
    local batch=0

    while [ $batch -lt $max_batches ]; do
        log_info "Batch $((batch+1))/$max_batches (limit=$batch_limit)..."

        if response=$(call_api "POST" "$INTERNAL_API/api/uyuni/push?limit=$batch_limit" "$TIMEOUT_PUSH" "Push Batch"); then
            pushed=$(echo "$response" | grep -o '"pushed":[0-9]*' | cut -d':' -f2 || echo "0")

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

    if [ $total_pushed -gt 0 ]; then
        log_success "Push completed: $total_pushed total errata pushed"
    else
        log_info "No errata to push (all synced or pending external sync)"
    fi
}

show_stats() {
    log_info "============================================================"
    log_info "STATISTICS"
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
# MENU
# ============================================================
show_menu() {
    echo ""
    echo "======================================================"
    echo "  UYUNI Server Operations (Internal Container Only)"
    echo "======================================================"
    echo ""
    echo "Options:"
    echo "  1) Test connectivity"
    echo "  2) Show detailed health"
    echo "  3) Update package cache + Push errata (QUICK)"
    echo "  4) Update package cache only"
    echo "  5) Push errata to UYUNI only"
    echo "  6) Show statistics"
    echo "  q) Quit"
    echo ""
    echo "NOTE: For external sync (USN, DSA, OVAL, NVD),"
    echo "      use remote-sync.sh from Azure Cloud Shell"
    echo ""
    echo -n "Select option: "
}

# ============================================================
# MAIN
# ============================================================
main() {
    if [ $# -eq 0 ]; then
        # Interactive
        while true; do
            show_menu
            read -r choice

            case $choice in
                1) test_connectivity ;;
                2) get_health ;;
                3)
                    log_info "Starting QUICK SYNC..."
                    test_connectivity && update_cache && push_errata && show_stats
                    ;;
                4) update_cache ;;
                5) push_errata ;;
                6) show_stats ;;
                q|Q) log_info "Exiting..."; exit 0 ;;
                *) log_error "Invalid option" ;;
            esac

            echo ""
            echo "Press Enter to continue..."
            read -r
        done
    else
        # Non-interactive
        case "$1" in
            test) test_connectivity ;;
            health) get_health ;;
            quick) test_connectivity && update_cache && push_errata && show_stats ;;
            cache) update_cache ;;
            push) push_errata ;;
            stats) show_stats ;;
            *)
                echo "Usage: $0 [test|health|quick|cache|push|stats]"
                echo "  test   - Test internal container connectivity"
                echo "  health - Show detailed health"
                echo "  quick  - Update cache + Push errata"
                echo "  cache  - Update package cache only"
                echo "  push   - Push errata to UYUNI only"
                echo "  stats  - Show statistics"
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
        log_error "Required command '$cmd' not found"
        exit 1
    fi
done

main "$@"
