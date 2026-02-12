#!/bin/bash
################################################################################
# UYUNI Errata Manager - Remote Sync Script
#
# Questo script deve essere eseguito da AZURE CLOUD SHELL o dal TUO PC
# Opera sul container PUBBLICO per sync esterni (USN, DSA, OVAL, NVD)
#
# NON eseguire dal server UYUNI (non può raggiungere il container pubblico)
################################################################################

set -euo pipefail

# ============================================================
# CONFIGURAZIONE
# ============================================================
PUBLIC_API="http://4.232.4.154:5000"

TIMEOUT_HEALTH=30
TIMEOUT_SHORT=600
TIMEOUT_LONG=1800

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
    log_info "TESTING PUBLIC CONTAINER CONNECTIVITY"
    log_info "============================================================"

    if response=$(curl -s -m "$TIMEOUT_HEALTH" "$PUBLIC_API/api/health" 2>&1); then
        if echo "$response" | grep -q '"api".*"ok"'; then
            log_success "Public container is healthy"
            echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
            return 0
        else
            log_error "Public container unhealthy: $response"
            return 1
        fi
    else
        log_error "Public container unreachable: $response"
        log_info "Note: This script must be run from Azure Cloud Shell or your PC,"
        log_info "      not from the UYUNI server (which is in private VNET)"
        return 1
    fi
}

sync_usn() {
    log_info "============================================================"
    log_info "SYNCING UBUNTU USN"
    log_info "============================================================"

    call_api "POST" "$PUBLIC_API/api/sync/usn" "$TIMEOUT_SHORT" "USN Sync"
}

sync_dsa_full() {
    log_info "============================================================"
    log_info "SYNCING DEBIAN DSA FULL"
    log_info "============================================================"
    log_warn "This may take 15-30 minutes..."

    call_api "POST" "$PUBLIC_API/api/sync/dsa/full" "$TIMEOUT_LONG" "DSA Full Sync"
}

sync_oval() {
    log_info "============================================================"
    log_info "SYNCING OVAL DEFINITIONS"
    log_info "============================================================"
    log_warn "This may take 10-20 minutes..."

    call_api "POST" "$PUBLIC_API/api/sync/oval?platform=all" "$TIMEOUT_LONG" "OVAL Sync"
}

sync_nvd() {
    log_info "============================================================"
    log_info "SYNCING NVD CVE DATA"
    log_info "============================================================"

    call_api "POST" "$PUBLIC_API/api/sync/nvd?batch_size=100&prioritize=true" "$TIMEOUT_SHORT" "NVD Sync"
}

# ============================================================
# MENU
# ============================================================
show_menu() {
    echo ""
    echo "======================================================"
    echo "  Remote Sync Operations (Public Container)"
    echo "======================================================"
    echo ""
    echo "Options:"
    echo "  1) Test connectivity"
    echo "  2) Sync Ubuntu USN (2-5 min)"
    echo "  3) Sync Debian DSA full (15-30 min)"
    echo "  4) Sync OVAL definitions (10-20 min)"
    echo "  5) Sync NVD CVE enrichment (5-10 min)"
    echo "  6) Full external sync (all of the above)"
    echo "  q) Quit"
    echo ""
    echo "NOTE: After external sync, run uyuni-server-sync.sh"
    echo "      on UYUNI server to push errata"
    echo ""
    echo -n "Select option: "
}

# ============================================================
# MAIN
# ============================================================
main() {
    log_info "Remote Sync Script - Public Container Operations"
    log_info "Container: $PUBLIC_API"
    echo ""

    if [ $# -eq 0 ]; then
        # Interactive
        while true; do
            show_menu
            read -r choice

            case $choice in
                1) test_connectivity ;;
                2) sync_usn ;;
                3) sync_dsa_full ;;
                4) sync_oval ;;
                5) sync_nvd ;;
                6)
                    log_info "Starting FULL EXTERNAL SYNC..."
                    test_connectivity && \
                    sync_usn && \
                    sync_dsa_full && \
                    sync_oval && \
                    sync_nvd
                    log_success "External sync completed!"
                    echo ""
                    log_info "Next: Run on UYUNI server:"
                    log_info "  ssh root@10.172.2.5"
                    log_info "  /root/uyuni-server-sync.sh quick"
                    ;;
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
            usn) sync_usn ;;
            dsa) sync_dsa_full ;;
            oval) sync_oval ;;
            nvd) sync_nvd ;;
            full)
                test_connectivity && \
                sync_usn && \
                sync_dsa_full && \
                sync_oval && \
                sync_nvd
                ;;
            *)
                echo "Usage: $0 [test|usn|dsa|oval|nvd|full]"
                echo "  test  - Test public container connectivity"
                echo "  usn   - Sync Ubuntu USN"
                echo "  dsa   - Sync Debian DSA full"
                echo "  oval  - Sync OVAL definitions"
                echo "  nvd   - Sync NVD CVE data"
                echo "  full  - Full external sync (all of above)"
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
