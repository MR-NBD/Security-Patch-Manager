#!/bin/bash
################################################################################
# UYUNI Errata Manager - Test Suite v3.1
#
# Testa tutti gli endpoint sui due container ACI:
#   PUBLIC_API  (aci-errata-api)          — sync USN, DSA, NVD
#   INTERNAL_API (aci-errata-api-internal) — sync-packages, push UYUNI
#
# Usage:
#   ./test-endpoints.sh
#   PUBLIC_API=http://... INTERNAL_API=http://... API_KEY=... ./test-endpoints.sh
################################################################################

set -euo pipefail

PUBLIC_API="${PUBLIC_API:-http://4.232.4.138:5000}"
INTERNAL_API="${INTERNAL_API:-http://10.172.5.4:5000}"
API_KEY="${API_KEY:-spm-key-2024}"
TIMEOUT=30

PASS=0
FAIL=0
WARN=0

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'

pass() { echo -e "  ${GREEN}✓ PASS${NC} — $*"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}✗ FAIL${NC} — $*"; FAIL=$((FAIL+1)); }
warn() { echo -e "  ${YELLOW}⚠ WARN${NC} — $*"; WARN=$((WARN+1)); }
section() { echo ""; echo -e "${BOLD}━━━ $* ━━━${NC}"; }

get_pub()  { curl -sf --max-time "$TIMEOUT" -H "X-API-Key: $API_KEY" "${PUBLIC_API}$1"  2>&1; }
get_int()  { curl -sf --max-time "$TIMEOUT" -H "X-API-Key: $API_KEY" "${INTERNAL_API}$1" 2>&1; }
post_pub() { curl -sf --max-time "$TIMEOUT" -X POST -H "X-API-Key: $API_KEY" "${PUBLIC_API}$1"  2>&1; }
post_int() { curl -sf --max-time "$TIMEOUT" -X POST -H "X-API-Key: $API_KEY" "${INTERNAL_API}$1" 2>&1; }

field() { echo "$1" | python3 -c "import sys,json; print(json.load(sys.stdin).get('$2',''))" 2>/dev/null; }

echo ""
echo -e "${BOLD}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  UYUNI Errata Manager — Test Suite v3.1        ║${NC}"
echo -e "${BOLD}║  Architettura: 2 container ACI                  ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo "  PUBLIC_API:   $PUBLIC_API"
echo "  INTERNAL_API: $INTERNAL_API"
echo "  API_KEY:      ${API_KEY:+<set>}"

# ============================================================
# 1. RAGGIUNGIBILITÀ
# ============================================================
section "1. Raggiungibilità"

if curl -sf --max-time 10 "${PUBLIC_API}/api/health" > /dev/null 2>&1; then
    pass "Container PUBBLICO raggiungibile"
else
    fail "Container PUBBLICO non raggiungibile — ${PUBLIC_API}"
fi

if curl -sf --max-time 10 "${INTERNAL_API}/api/health" > /dev/null 2>&1; then
    pass "Container INTERNO raggiungibile"
else
    fail "Container INTERNO non raggiungibile — ${INTERNAL_API}"
fi

# ============================================================
# 2. HEALTH — Container PUBBLICO
# ============================================================
section "2. GET /api/health — Container PUBBLICO"

resp=$(curl -sf --max-time "$TIMEOUT" "${PUBLIC_API}/api/health" 2>&1) || { fail "Request failed"; resp="{}"; }
[[ "$(field "$resp" api)" == "ok" ]]       && pass "api = ok"       || fail "api = $(field "$resp" api)"
[[ "$(field "$resp" database)" == "ok" ]]  && pass "database = ok"  || fail "database = $(field "$resp" database)"
[[ "$(field "$resp" version)" == "3.1" ]]  && pass "version = 3.1"  || fail "version = $(field "$resp" version)"

uyuni_pub=$(field "$resp" uyuni)
if [[ "$uyuni_pub" == "not configured" || "$uyuni_pub" == "ok" ]]; then
    warn "uyuni = $uyuni_pub (normale: container pubblico non ha UYUNI_URL)"
else
    warn "uyuni = $uyuni_pub"
fi

# ============================================================
# 3. HEALTH — Container INTERNO
# ============================================================
section "3. GET /api/health — Container INTERNO"

resp=$(curl -sf --max-time "$TIMEOUT" "${INTERNAL_API}/api/health" 2>&1) || { fail "Request failed"; resp="{}"; }
[[ "$(field "$resp" api)" == "ok" ]]       && pass "api = ok"       || fail "api = $(field "$resp" api)"
[[ "$(field "$resp" database)" == "ok" ]]  && pass "database = ok"  || fail "database = $(field "$resp" database)"
[[ "$(field "$resp" version)" == "3.1" ]]  && pass "version = 3.1"  || fail "version = $(field "$resp" version)"

uyuni_int=$(field "$resp" uyuni)
if [[ "$uyuni_int" == "ok" ]]; then
    pass "uyuni = ok"
else
    fail "uyuni = $uyuni_int (container interno deve raggiungere UYUNI)"
fi

# ============================================================
# 4. HEALTH DETAILED — entrambi
# ============================================================
section "4. GET /api/health/detailed"

for label in "PUBLIC:${PUBLIC_API}" "INTERNAL:${INTERNAL_API}"; do
    name="${label%%:*}"
    url="${label#*:}"
    resp=$(curl -sf --max-time "$TIMEOUT" "${url}/api/health/detailed" 2>&1) || { fail "[$name] Request failed"; continue; }
    db=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('database',{}).get('connected','?'))" 2>/dev/null)
    total=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('database',{}).get('errata_total','?'))" 2>/dev/null)
    pending=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('database',{}).get('errata_pending','?'))" 2>/dev/null)
    [[ "$db" == "True" ]] \
        && pass "[$name] DB connected — errata_total=$total, errata_pending=$pending" \
        || fail "[$name] DB connected=$db"
done

# ============================================================
# 5. AUTENTICAZIONE
# ============================================================
section "5. Autenticazione X-API-Key"

for label in "PUBLIC:${PUBLIC_API}" "INTERNAL:${INTERNAL_API}"; do
    name="${label%%:*}"
    url="${label#*:}"
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" -X POST "${url}/api/sync/usn" 2>/dev/null)
    [[ "$code" == "401" ]] && pass "[$name] senza chiave → 401" || warn "[$name] senza chiave → $code (SPM_API_KEY impostata?)"
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" -H "X-API-Key: wrong" -X POST "${url}/api/sync/usn" 2>/dev/null)
    [[ "$code" == "401" ]] && pass "[$name] chiave sbagliata → 401" || warn "[$name] chiave sbagliata → $code"
done

# ============================================================
# 6. CANALI UYUNI — Container INTERNO
# ============================================================
section "6. GET /api/uyuni/channels — Container INTERNO"

resp=$(get_int "/api/uyuni/channels" 2>&1) || { fail "Request failed"; resp="{}"; }
count=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))" 2>/dev/null || echo 0)
dists=$(echo "$resp" | python3 -c "
import sys,json
d=json.load(sys.stdin)
s=set(ch.get('distribution') for ch in d.get('channels',[]) if ch.get('distribution'))
print(', '.join(sorted(s)) or 'nessuna')
" 2>/dev/null || echo "?")
[[ "$count" -gt 0 ]] 2>/dev/null \
    && pass "$count canali rilevati — distribuzioni: $dists" \
    || warn "Nessun canale trovato (count=$count)"

# ============================================================
# 7. SYNC STATUS — Container PUBBLICO
# ============================================================
section "7. GET /api/sync/status — Container PUBBLICO"

resp=$(get_pub "/api/sync/status" 2>&1) || { fail "Request failed"; resp="{}"; }
n=$(echo "$resp" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('logs',[])))" 2>/dev/null || echo 0)
pass "Risposta OK — $n log entries"
echo "$resp" | python3 -c "
import sys,json
for l in json.load(sys.stdin).get('logs',[])[:4]:
    print(f'    [{l.get(\"sync_type\",\"?\")}] {l.get(\"status\",\"?\")} @ {l.get(\"started_at\",\"?\")[:19]}')
" 2>/dev/null || true

# ============================================================
# 8. NVD enrichment — Container PUBBLICO (max 5 CVE)
# ============================================================
section "8. POST /api/sync/nvd?batch_size=5 — Container PUBBLICO"

echo "  (enrichment NVD su max 5 CVE — non distruttivo...)"
resp=$(post_pub "/api/sync/nvd?batch_size=5" 2>&1) || { fail "Request failed"; resp="{}"; }
[[ "$(field "$resp" status)" == "success" ]] \
    && pass "NVD OK — $(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d.get(\"processed\",0)} CVE, {d.get(\"errata_severity_updated\",0)} severity aggiornate')" 2>/dev/null)" \
    || fail "NVD status=$(field "$resp" status)"

# ============================================================
# 9. SYNC PACKAGES — Container INTERNO
# ============================================================
section "9. POST /api/uyuni/sync-packages — Container INTERNO"

echo "  (aggiornamento cache pacchetti — può richiedere 2-5 min...)"
resp=$(curl -sf --max-time 600 -X POST -H "X-API-Key: $API_KEY" "${INTERNAL_API}/api/uyuni/sync-packages" 2>&1) || { fail "Errore o timeout"; resp="{}"; }
[[ "$(field "$resp" status)" == "success" ]] \
    && pass "Package cache OK — $(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_packages_synced',0))" 2>/dev/null) pacchetti" \
    || fail "status=$(field "$resp" status)"

# ============================================================
# 10. PUSH → UYUNI — Container INTERNO (max 3)
# ============================================================
section "10. POST /api/uyuni/push?limit=3 — Container INTERNO"

resp=$(curl -sf --max-time 120 -X POST -H "X-API-Key: $API_KEY" "${INTERNAL_API}/api/uyuni/push?limit=3" 2>&1) || { fail "Errore"; resp="{}"; }
[[ "$(field "$resp" status)" == "success" ]] \
    && pass "Push OK — $(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d.get(\"pushed\",0)} pushed, {d.get(\"skipped_version_mismatch\",0)} skipped')" 2>/dev/null)" \
    || fail "status=$(field "$resp" status)"

# ============================================================
# RIEPILOGO
# ============================================================
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${GREEN}✓ PASS: $PASS${NC}  ${YELLOW}⚠ WARN: $WARN${NC}  ${RED}✗ FAIL: $FAIL${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [[ $FAIL -eq 0 ]]; then
    echo -e "\n  ${GREEN}${BOLD}Tutti i test superati.${NC}"
    exit 0
else
    echo -e "\n  ${RED}${BOLD}$FAIL test falliti.${NC}"
    echo "  Log pubblico:  az container logs --resource-group test_group --name aci-errata-api"
    echo "  Log interno:   az container logs --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal"
    exit 1
fi
