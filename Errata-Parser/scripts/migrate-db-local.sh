#!/bin/bash
################################################################################
# Errata-Parser — Migrazione DB da Azure PostgreSQL a PostgreSQL locale
#
# Fase 2 opzionale: risparmia ~15-30€/mese eliminando Azure DB.
# Eseguire DOPO che il servizio è stabile su VM.
#
# Usage: sudo bash migrate-db-local.sh
################################################################################

set -euo pipefail

ENV_FILE="/opt/errata-parser/.env"

# Legge DATABASE_URL corrente dal .env (punta ad Azure PostgreSQL)
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE non trovato. Assicurarsi che il servizio sia già installato."
    exit 1
fi
AZURE_URL=$(grep "^DATABASE_URL=" "$ENV_FILE" | cut -d= -f2-)
if [[ -z "$AZURE_URL" || "$AZURE_URL" == "CHANGE_ME" ]]; then
    echo "ERROR: DATABASE_URL non configurata in $ENV_FILE"
    exit 1
fi

LOCAL_DB="uyuni_errata"
LOCAL_USER="errataparser"
# Genera password casuale sicura (non hardcoded nel codice sorgente)
LOCAL_PASS=$(openssl rand -base64 32 | tr -d '/+=' | head -c 40)
DUMP_FILE="/tmp/errata-dump-$(date +%Y%m%d-%H%M%S).sql"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }

# --------------------------------------------------------------------------
# 1. Installa PostgreSQL locale
# --------------------------------------------------------------------------
info "Installazione PostgreSQL locale..."
apt-get install -y -qq postgresql postgresql-client
systemctl enable postgresql
systemctl start postgresql
info "PostgreSQL locale avviato"

# --------------------------------------------------------------------------
# 2. Crea utente e database locale
# --------------------------------------------------------------------------
info "Creazione database locale $LOCAL_DB..."
sudo -u postgres psql << EOF
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$LOCAL_USER') THEN
    CREATE USER $LOCAL_USER WITH PASSWORD '$LOCAL_PASS';
  END IF;
END \$\$;
CREATE DATABASE $LOCAL_DB OWNER $LOCAL_USER;
GRANT ALL PRIVILEGES ON DATABASE $LOCAL_DB TO $LOCAL_USER;
EOF
info "Database locale creato"

# --------------------------------------------------------------------------
# 3. Dump da Azure
# --------------------------------------------------------------------------
info "Dump da Azure PostgreSQL (potrebbe richiedere 2-5 minuti)..."
pg_dump "$AZURE_URL" \
    --no-owner --no-acl \
    --file "$DUMP_FILE"
info "Dump salvato in $DUMP_FILE ($(du -sh $DUMP_FILE | cut -f1))"

# --------------------------------------------------------------------------
# 4. Restore su locale
# --------------------------------------------------------------------------
info "Restore su PostgreSQL locale..."
PGPASSWORD="$LOCAL_PASS" psql \
    -h localhost -U "$LOCAL_USER" -d "$LOCAL_DB" \
    -f "$DUMP_FILE"
info "Restore completato"

# --------------------------------------------------------------------------
# 5. Verifica
# --------------------------------------------------------------------------
ERRATA_COUNT=$(PGPASSWORD="$LOCAL_PASS" psql \
    -h localhost -U "$LOCAL_USER" -d "$LOCAL_DB" \
    -tAc "SELECT COUNT(*) FROM errata;")
info "Errata nel DB locale: $ERRATA_COUNT"

# --------------------------------------------------------------------------
# 6. Aggiorna .env
# --------------------------------------------------------------------------
LOCAL_URL="postgresql://$LOCAL_USER:$LOCAL_PASS@localhost:5432/$LOCAL_DB"
warn "Aggiornamento DATABASE_URL in $ENV_FILE..."
sed -i "s|^DATABASE_URL=.*|DATABASE_URL=$LOCAL_URL|" "$ENV_FILE"
info "DATABASE_URL aggiornato a localhost"
info "Password DB locale generata: $LOCAL_PASS  (salvata in $ENV_FILE)"

# --------------------------------------------------------------------------
# 7. Restart servizio
# --------------------------------------------------------------------------
systemctl restart errata-parser
sleep 3
curl -s http://localhost:5000/api/health | python3 -m json.tool

echo ""
info "Migrazione completata!"
warn "Ora puoi eliminare il database Azure PostgreSQL per risparmiare costi."
rm -f "$DUMP_FILE"
