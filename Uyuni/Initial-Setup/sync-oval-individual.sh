#!/bin/bash
################################################################################
# Sync OVAL Definitions - Individual Platforms
#
# Questo script sincronizza OVAL un platform alla volta per evitare timeout
################################################################################

set -euo pipefail

PUBLIC_API="http://4.232.4.154:5000"
TIMEOUT=1800  # 30 minuti per piattaforma

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ============================================================
# PLATFORMS TO SYNC
# ============================================================
declare -A PLATFORMS=(
    ["ubuntu-noble"]="ubuntu"
    ["ubuntu-jammy"]="ubuntu"
    ["ubuntu-focal"]="ubuntu"
    ["debian-bookworm"]="debian"
    ["debian-bullseye"]="debian"
)

# ============================================================
# SYNC FUNCTION
# ============================================================
sync_oval_platform() {
    local codename="$1"
    local platform="$2"

    log_info "============================================================"
    log_info "Syncing OVAL: $platform $codename"
    log_info "============================================================"

    local url="$PUBLIC_API/api/sync/oval?platform=$platform&codename=$codename"

    log_info "URL: $url"
    log_info "Timeout: ${TIMEOUT}s"
    echo ""

    local start_time=$(date +%s)

    if response=$(curl -s -m "$TIMEOUT" -X POST "$url" 2>&1); then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))

        if echo "$response" | grep -q '"status".*"success"'; then
            local processed=$(echo "$response" | grep -o '"total_processed":[0-9]*' | cut -d':' -f2)
            log_success "Completed in ${duration}s - Processed: $processed definitions"
            echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
            return 0
        else
            log_error "Failed: $response"
            return 1
        fi
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        log_error "Request failed after ${duration}s"
        log_error "Response: $response"
        return 1
    fi
}

# ============================================================
# MAIN
# ============================================================
main() {
    log_info "======================================================"
    log_info "  OVAL Sync - Individual Platforms"
    log_info "======================================================"
    echo ""

    # Test connectivity
    log_info "Testing container connectivity..."
    if ! curl -s -m 10 "$PUBLIC_API/api/health" > /dev/null 2>&1; then
        log_error "Cannot reach container at $PUBLIC_API"
        exit 1
    fi
    log_success "Container is reachable"
    echo ""

    # Check current stats
    log_info "Current OVAL stats:"
    if stats=$(curl -s -m 10 "$PUBLIC_API/api/stats/overview" 2>&1); then
        echo "$stats" | grep -A 20 "oval" | python3 -m json.tool 2>/dev/null || echo "$stats"
    fi
    echo ""

    # Sync each platform
    local total_success=0
    local total_failed=0

    for codename in "${!PLATFORMS[@]}"; do
        platform="${PLATFORMS[$codename]}"

        if sync_oval_platform "$codename" "$platform"; then
            ((total_success++))
        else
            ((total_failed++))
            log_warn "Continuing with next platform..."
        fi

        echo ""
        sleep 2
    done

    # Summary
    log_info "======================================================"
    log_info "  SYNC SUMMARY"
    log_info "======================================================"
    log_info "Total platforms: ${#PLATFORMS[@]}"
    log_success "Successful: $total_success"
    [ $total_failed -gt 0 ] && log_error "Failed: $total_failed" || log_info "Failed: 0"
    echo ""

    # Final stats
    log_info "Final OVAL stats:"
    if stats=$(curl -s -m 10 "$PUBLIC_API/api/stats/overview" 2>&1); then
        echo "$stats" | python3 -m json.tool 2>/dev/null || echo "$stats"
    fi

    if [ $total_failed -eq 0 ]; then
        log_success "All platforms synced successfully!"
        exit 0
    else
        log_warn "Some platforms failed. Check logs above."
        exit 1
    fi
}

# Check if running from correct location
if ! curl -s -m 5 "$PUBLIC_API/api/health" > /dev/null 2>&1; then
    log_error "Cannot reach public container"
    log_info "This script must be run from:"
    log_info "  - Azure Cloud Shell"
    log_info "  - Your local PC with internet access"
    log_info ""
    log_info "Do NOT run from UYUNI server (in private VNET)"
    exit 1
fi

main "$@"
