#!/bin/bash
################################################################################
# UYUNI Errata Manager - Test Suite v3.1
#
# Verifica tutti gli endpoint dell'API dopo il deploy.
# Usage:
#   ./test-endpoints.sh                          # usa API default (http://10.172.5.5:5000)
#   API=http://localhost:5000 ./test-endpoints.sh
#   API=http://10.172.5.5:5000 API_KEY=mykey ./test-endpoints.sh
################################################################################

set -euo pipefail

API="${API:-http://10.172.5.5:5000}"
API_KEY="${API_KEY:-}"
TIMEOUT=30

PASS=0
FAIL=0
WARN=0

# ============================================================
# HELPERS
# ============================================================
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "  $*"; }
pass() { echo -e "  ${GREEN}✓ PASS${NC} — $*"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}✗ FAIL${NC} — $*"; FAIL=$((FAIL+1)); }
warn() { echo -e "  ${YELLOW}⚠ WARN${NC} — $*"; WARN=$((WARN+1)); }

section() {
    echo ""
    echo -e "${BOLD}━━━ $* ━━━${NC}"
}

# curl con auth header se API_KEY impostata
api_get() {
    local endpoint="$1"
    if [[ -n "$API_KEY" ]]; then
        curl -sf --max-time "$TIMEOUT" -H "X-API-Key: $API_KEY" "${API}${endpoint}" 2>&1
    else
        curl -sf --max-time "$TIMEOUT" "${API}${endpoint}" 2>&1
    fi
}

api_post() {
    local endpoint="$1"
    if [[ -n "$API_KEY" ]]; then
        curl -sf --max-time "$TIMEOUT" -X POST -H "X-API-Key: $API_KEY" "${API}${endpoint}" 2>&1
    else
        curl -sf --max-time "$TIMEOUT" -X POST "${API}${endpoint}" 2>&1
    fi
}

check_field() {
    local json="$1" field="$2" expected="$3"
    local actual
    actual=$(echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$field','MISSING'))" 2>/dev/null || echo "PARSE_ERROR")
    if [[ "$actual" == "$expected" ]]; then
        return 0
    else
        return 1
    fi
}

field_value() {
    local json="$1" field="$2"
    echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$field',''))" 2>/dev/null || echo ""
}

# ============================================================
# MAIN
# ============================================================
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   UYUNI Errata Manager — Test Suite v3.1 ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  API:     $API"
echo "  API_KEY: ${API_KEY:+<set>}${API_KEY:-<non impostata — auth disabilitata>}"

# ============================================================
# 1. RAGGIUNGIBILITÀ
# ============================================================
section "1. Raggiungibilità API"

if curl -sf --max-time 10 "${API}/api/health" > /dev/null 2>&1; then
    pass "API raggiungibile su ${API}"
else
    fail "API NON raggiungibile su ${API} — interrompo"
    echo ""
    echo "Verifica:"
    echo "  az container show --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal"
    exit 1
fi

# ============================================================
# 2. GET /api/health (no auth)
# ============================================================
section "2. GET /api/health"

resp=$(curl -sf --max-time "$TIMEOUT" "${API}/api/health" 2>&1) || { fail "Request failed"; }

if check_field "$resp" "api" "ok"; then
    pass "api = ok"
else
    fail "api field not 'ok': $resp"
fi

db_status=$(field_value "$resp" "database")
if [[ "$db_status" == "ok" ]]; then
    pass "database = ok"
else
    fail "database = $db_status"
fi

uyuni_status=$(field_value "$resp" "uyuni")
if [[ "$uyuni_status" == "ok" ]]; then
    pass "uyuni = ok"
elif [[ "$uyuni_status" == "not configured" ]]; then
    warn "uyuni = not configured (UYUNI_URL non impostata)"
else
    fail "uyuni = $uyuni_status"
fi

version=$(field_value "$resp" "version")
if [[ "$version" == "3.1" ]]; then
    pass "version = 3.1"
else
    fail "version = $version (atteso 3.1)"
fi

# ============================================================
# 3. GET /api/health/detailed (no auth)
# ============================================================
section "3. GET /api/health/detailed"

resp=$(curl -sf --max-time "$TIMEOUT" "${API}/api/health/detailed" 2>&1) || { fail "Request failed"; }

# Campi obbligatori
for field in version timestamp database uyuni sync_status cache alerts; do
    val=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print('present' if '$field' in d else 'missing')" 2>/dev/null)
    if [[ "$val" == "present" ]]; then
        pass "campo '$field' presente"
    else
        fail "campo '$field' mancante nella risposta"
    fi
done

# Database connected
db_conn=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('database',{}).get('connected','?'))" 2>/dev/null)
if [[ "$db_conn" == "True" ]]; then
    errata_total=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('database',{}).get('errata_total','?'))" 2>/dev/null)
    errata_pending=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('database',{}).get('errata_pending','?'))" 2>/dev/null)
    pass "database connected — errata_total=$errata_total, errata_pending=$errata_pending"
else
    fail "database.connected = $db_conn"
fi

# UYUNI connected
uyuni_conn=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('uyuni',{}).get('connected','?'))" 2>/dev/null)
if [[ "$uyuni_conn" == "True" ]]; then
    pass "uyuni connected"
else
    warn "uyuni.connected = $uyuni_conn"
fi

# Alert stale check
stale_cache=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('alerts',{}).get('stale_cache','?'))" 2>/dev/null)
if [[ "$stale_cache" == "False" ]]; then
    pass "cache non stale"
else
    warn "stale_cache=$stale_cache (cache vecchia o vuota — aggiornare con /api/uyuni/sync-packages)"
fi

# ============================================================
# 4. AUTENTICAZIONE
# ============================================================
section "4. Autenticazione (X-API-Key)"

if [[ -n "$API_KEY" ]]; then
    # Test senza chiave → deve dare 401
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" \
        -X POST "${API}/api/sync/usn" 2>/dev/null)
    if [[ "$http_code" == "401" ]]; then
        pass "Richiesta senza chiave → 401 Unauthorized"
    else
        warn "Richiesta senza chiave → $http_code (atteso 401; SPM_API_KEY non impostata nel container?)"
    fi

    # Test con chiave sbagliata → 401
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" \
        -H "X-API-Key: wrong-key-12345" -X POST "${API}/api/sync/usn" 2>/dev/null)
    if [[ "$http_code" == "401" ]]; then
        pass "Chiave sbagliata → 401 Unauthorized"
    else
        warn "Chiave sbagliata → $http_code"
    fi
else
    warn "API_KEY non impostata — skip test autenticazione"
fi

# ============================================================
# 5. GET /api/uyuni/channels
# ============================================================
section "5. GET /api/uyuni/channels"

resp=$(api_get "/api/uyuni/channels" 2>&1)
http_ok=$?

if [[ $http_ok -eq 0 ]]; then
    count=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))" 2>/dev/null || echo "?")
    channels=$(echo "$resp" | python3 -c "
import sys, json
d = json.load(sys.stdin)
dists = set(ch.get('distribution') for ch in d.get('channels',[]) if ch.get('distribution'))
print(', '.join(sorted(dists)) if dists else 'nessuna distribuzione rilevata')
" 2>/dev/null)
    if [[ "$count" -gt 0 ]] 2>/dev/null; then
        pass "Trovati $count canali — distribuzioni: $channels"
    else
        warn "Nessun canale trovato (count=$count)"
    fi
else
    fail "Errore chiamata /api/uyuni/channels"
fi

# ============================================================
# 6. GET /api/sync/status
# ============================================================
section "6. GET /api/sync/status"

resp=$(api_get "/api/sync/status" 2>&1)
if [[ $? -eq 0 ]]; then
    log_count=$(echo "$resp" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('logs',[])))" 2>/dev/null || echo "?")
    pass "Risposta OK — $log_count log entries"

    # Mostra ultimi sync
    echo "$resp" | python3 -c "
import sys, json
logs = json.load(sys.stdin).get('logs', [])[:5]
for l in logs:
    print(f'    [{l.get(\"sync_type\",\"?\")}] {l.get(\"status\",\"?\")} — {l.get(\"started_at\",\"?\")} ({l.get(\"items_processed\",\"?\")} items)')
" 2>/dev/null || true
else
    fail "Errore chiamata /api/sync/status"
fi

# ============================================================
# 7. POST /api/sync/nvd (solo batch piccolo)
# ============================================================
section "7. POST /api/sync/nvd?batch_size=5"

log "Eseguo enrichment NVD su max 5 CVE (test non distruttivo)..."
resp=$(api_post "/api/sync/nvd?batch_size=5" 2>&1)
if [[ $? -eq 0 ]]; then
    status=$(field_value "$resp" "status")
    if [[ "$status" == "success" ]]; then
        processed=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('processed',0))" 2>/dev/null)
        updated=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('errata_severity_updated',0))" 2>/dev/null)
        pass "NVD sync OK — $processed CVE processati, $updated errata severity aggiornate"
    else
        warn "NVD sync status=$status (risposta: $resp)"
    fi
else
    fail "Errore chiamata /api/sync/nvd"
fi

# ============================================================
# 8. POST /api/uyuni/sync-packages
# ============================================================
section "8. POST /api/uyuni/sync-packages"

log "Aggiornamento cache pacchetti UYUNI (può richiedere 1-5 min)..."
resp=$(curl -sf --max-time 600 -X POST \
    ${API_KEY:+-H "X-API-Key: $API_KEY"} \
    "${API}/api/uyuni/sync-packages" 2>&1)
if [[ $? -eq 0 ]]; then
    status=$(field_value "$resp" "status")
    if [[ "$status" == "success" ]]; then
        total=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_packages_synced',0))" 2>/dev/null)
        pass "Package cache aggiornata — $total pacchetti totali"
    else
        warn "sync-packages status=$status"
    fi
else
    fail "Errore o timeout su /api/uyuni/sync-packages"
fi

# ============================================================
# 9. POST /api/sync/usn
# ============================================================
section "9. POST /api/sync/usn"

log "Sync Ubuntu USN incrementale..."
resp=$(curl -sf --max-time 300 -X POST \
    ${API_KEY:+-H "X-API-Key: $API_KEY"} \
    "${API}/api/sync/usn" 2>&1)
if [[ $? -eq 0 ]]; then
    status=$(field_value "$resp" "status")
    if [[ "$status" == "success" ]]; then
        processed=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('processed',d.get('skipped','?')))" 2>/dev/null)
        pass "USN sync OK — $processed errata processati"
    else
        warn "USN sync status=$status"
    fi
else
    fail "Errore o timeout su /api/sync/usn"
fi

# ============================================================
# 10. POST /api/uyuni/push?limit=3
# ============================================================
section "10. POST /api/uyuni/push?limit=3"

log "Push max 3 errata pending a UYUNI (test conservativo)..."
resp=$(curl -sf --max-time 120 -X POST \
    ${API_KEY:+-H "X-API-Key: $API_KEY"} \
    "${API}/api/uyuni/push?limit=3" 2>&1)
if [[ $? -eq 0 ]]; then
    status=$(field_value "$resp" "status")
    if [[ "$status" == "success" ]]; then
        pushed=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('pushed',0))" 2>/dev/null)
        skipped=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('skipped_version_mismatch',0))" 2>/dev/null)
        pass "Push OK — $pushed pushed, $skipped skipped (version mismatch)"
    else
        warn "Push status=$status"
    fi
else
    fail "Errore su /api/uyuni/push"
fi

# ============================================================
# RIEPILOGO
# ============================================================
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}RIEPILOGO${NC}"
echo -e "  ${GREEN}✓ PASS: $PASS${NC}"
if [[ $WARN -gt 0 ]]; then
    echo -e "  ${YELLOW}⚠ WARN: $WARN${NC}"
fi
if [[ $FAIL -gt 0 ]]; then
    echo -e "  ${RED}✗ FAIL: $FAIL${NC}"
fi
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [[ $FAIL -eq 0 ]]; then
    echo -e "\n  ${GREEN}${BOLD}Tutti i test superati.${NC}"
    exit 0
else
    echo -e "\n  ${RED}${BOLD}$FAIL test falliti — verificare i log del container.${NC}"
    echo "  az container logs --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal --tail 50"
    exit 1
fi
