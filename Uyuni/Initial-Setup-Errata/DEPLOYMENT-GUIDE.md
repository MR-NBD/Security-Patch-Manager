## FASE 1: Build Nuova Immagine v2.5
### Prepara File Locali

```bash
# Sul tuo workstation (o Azure Cloud Shell)
mkdir -p ~/uyuni-errata-manager-v2.5
cd ~/uyuni-errata-manager-v2.5

# Download file dal repository
# (oppure crea i file manualmente con il contenuto fornito)
```
### Crea Dockerfile

```bash
cat > Dockerfile.api << 'EOF'
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libpq-dev gcc libc-dev libbz2-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    flask==3.0.0 \
    flask-cors==4.0.0 \
    gunicorn==21.2.0 \
    psycopg2-binary==2.9.9 \
    requests==2.31.0 \
    packaging==23.2

COPY app-v2.5-IMPROVED.py /app/app.py

# Logging directory
RUN mkdir -p /var/log && touch /var/log/errata-manager.log

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "900", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
EOF
```

**NOTA**: Aggiunta dipendenza `packaging` per version comparison.
### Copia app.py Migliorato
```bash
# Copia il file app-v2.5-IMPROVED.py nella directory
# (già creato nel passo precedente)
cp /path/to/app-v2.5-IMPROVED.py app-v2.5-IMPROVED.py
```
### Build e Push Immagine
```bash
# Variabili
ACR_NAME="acaborerrata"
IMAGE_TAG="v2.5"

# Build su Azure Container Registry
az acr build \
  --registry $ACR_NAME \
  --image errata-api:$IMAGE_TAG \
  --file Dockerfile.api .

# Verifica build
az acr repository show-tags \
  --name $ACR_NAME \
  --repository errata-api \
  --output table
```
## FASE 2: Update Database Schema (se necessario)
La v2.5 riutilizza lo schema v2.4, ma verifica che tutte le tabelle siano presenti:

```bash
# Connetti al database
psql "postgresql://errataadmin:ErrataSecure2024@10.172.2.6:5432/uyuni_errata?sslmode=require"
```

```sql
-- Verifica tabelle critiche
\dt

-- Devono essere presenti:
-- errata, errata_packages, uyuni_package_cache,
-- cves, cve_details, oval_definitions, errata_cve_oval_map

-- Se manca errata_cve_oval_map (per OVAL integration), creala:
CREATE TABLE IF NOT EXISTS errata_cve_oval_map (
    errata_id INTEGER REFERENCES errata(id) ON DELETE CASCADE,
    cve_id VARCHAR(50),
    oval_id VARCHAR(200),
    PRIMARY KEY (errata_id, cve_id, oval_id)
);

CREATE INDEX IF NOT EXISTS idx_ecov_errata ON errata_cve_oval_map(errata_id);
CREATE INDEX IF NOT EXISTS idx_ecov_cve ON errata_cve_oval_map(cve_id);
CREATE INDEX IF NOT EXISTS idx_ecov_oval ON errata_cve_oval_map(oval_id);
```
## FASE 3: Deploy Container v2.5
### Opzione A: Container Interno (architettura attuale a 2 container)

```bash
# Variabili
RG="ASL0603-spoke10-rg-spoke-italynorth"
CONTAINER_NAME="aci-errata-api-internal"
ACR_NAME="acaborerrata"
IMAGE_TAG="v2.5"

# Ottieni password ACR
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

# IMPORTANTE: Prima fai backup del container esistente
az container export \
  --resource-group $RG \
  --name $CONTAINER_NAME \
  --file aci-errata-api-internal-backup.yaml

# Elimina container vecchio
az container delete \
  --resource-group $RG \
  --name $CONTAINER_NAME \
  --yes

# Deploy nuovo container v2.5
az container create \
  --resource-group $RG \
  --name $CONTAINER_NAME \
  --image $ACR_NAME.azurecr.io/errata-api:$IMAGE_TAG \
  --registry-login-server $ACR_NAME.azurecr.io \
  --registry-username $ACR_NAME \
  --registry-password "$ACR_PASSWORD" \
  --os-type Linux \
  --cpu 1 \
  --memory 1.5 \
  --ports 5000 \
  --vnet ASL0603-spoke10-spoke-italynorth \
  --subnet errata-aci-subnet \
  --restart-policy Always \
  --environment-variables \
    FLASK_ENV=production \
    DATABASE_URL="postgresql://errataadmin:ErrataSecure2024@10.172.2.6:5432/uyuni_errata?sslmode=require" \
    UYUNI_URL="https://10.172.2.5" \
    UYUNI_USER="admin" \
    UYUNI_PASSWORD="password" \
    NVD_API_KEY="49b6e254-d81d-4b61-abac-2dbe04471e38"  # Opzionale ma raccomandato
```

**ANCHE container pubblico** (per sync esterni):

```bash
RG_PUBLIC="test_group"
CONTAINER_PUBLIC="aci-errata-api"

# Elimina vecchio
az container delete \
  --resource-group $RG_PUBLIC \
  --name $CONTAINER_PUBLIC \
  --yes

# Deploy nuovo (solo sync, no UYUNI vars)
az container create \
  --resource-group $RG_PUBLIC \
  --name $CONTAINER_PUBLIC \
  --image $ACR_NAME.azurecr.io/errata-api:$IMAGE_TAG \
  --registry-login-server $ACR_NAME.azurecr.io \
  --registry-username $ACR_NAME \
  --registry-password "$ACR_PASSWORD" \
  --os-type Linux \
  --cpu 1 \
  --memory 1.5 \
  --ports 5000 \
  --ip-address Public \
  --restart-policy Always \
  --environment-variables \
    DATABASE_URL="postgresql://errataadmin:ErrataSecure2024@pg-errata-test.postgres.database.azure.com:5432/uyuni_errata?sslmode=require"
```
### Opzione B: Container Unificato (DOPO aver ottenuto il NAT Gateway)

```bash
az container create \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-unified \
  --image $ACR_NAME.azurecr.io/errata-api:$IMAGE_TAG \
  --registry-login-server $ACR_NAME.azurecr.io \
  --registry-username $ACR_NAME \
  --registry-password "$ACR_PASSWORD" \
  --os-type Linux \
  --cpu 2 \
  --memory 2 \
  --ports 5000 \
  --vnet ASL0603-spoke10-spoke-italynorth \
  --subnet errata-aci-subnet \
  --restart-policy Always \
  --environment-variables \
    FLASK_ENV=production \
DATABASE_URL="postgresql://errataadmin:ErrataSecure2024@10.172.2.6:5432/uyuni_errata?sslmode=require" \
    UYUNI_URL="https://10.172.2.5" \
    UYUNI_USER="admin" \
    UYUNI_PASSWORD="password" \
    NVD_API_KEY="49b6e254-d81d-4b61-abac-2dbe04471e38"
```
## FASE 4: Testing v2.5
### Health Check Dettagliato
```bash
az container list \
    --output table \
    --query "[?contains(name, 'errata')].{Name:name, ResourceGroup:resourceGroup, State:instanceView.state, IP:ipAddress.ip}"
```

```bash
# Verifica health base
curl -s http://10.172.5.5:5000/api/health | jq

# Output atteso:
# {
#   "api": "ok",
#   "database": "ok",
#   "uyuni": "ok",
#   "version": "2.5"
# }

# Verifica health dettagliato (nuovo in v2.5)
curl -s http://10.172.5.5:5000/api/health/detailed | jq
```
**Output atteso (health detailed)**:
```json
{
  "version": "2.5",
  "timestamp": "2026-01-07T10:30:00",
  "database": {
    "connected": true,
    "errata_total": 5234,
    "errata_pending": 127
  },
  "uyuni": {
    "connected": true,
    "url": "https://10.172.2.5"
  },
  "sync_status": {
    "last_usn_sync": "2026-01-07T08:00:00",
    "last_dsa_sync": "2026-01-06T20:00:00",
    "usn_age_hours": 2.5,
    "dsa_age_hours": 14.5
  },
  "cache": {
    "total_packages": 45231,
    "last_update": "2026-01-07T09:00:00",
    "age_hours": 1.5
  },
  "alerts": {
    "failed_pushes_24h": 0,
    "stale_cache": false,
    "stale_usn_sync": false
  }
}
```
### Test Sync USN Ottimizzato
```bash
# Test sync USN (dovrebbe essere molto più veloce in v2.5)
time curl -s -X POST http://4.232.4.142:5000/api/sync/usn | jq

# Output atteso:
# {
#   "status": "success",
#   "source": "usn",
#   "processed": 15,  # Solo nuovi errata
#   "packages_saved": 342,
#   "last_known": "USN-7931-4"
# }
# real	0m45.123s  (prima era ~10min)
```
### Test DSA Full Auto (NUOVO!)
```bash
# Test nuovo endpoint DSA full automatico
time curl -s -X POST http://4.232.4.142:5000/api/sync/dsa/full | jq

# Output atteso:
# {
#   "status": "success",
#   "source": "dsa_full",
#   "total_packages_scanned": 3742,
#   "total_errata_created": 1523,
#   "total_packages_saved": 1523
# }
# real	12m34.567s  (automatico, prima richiedeva 8 comandi manuali)
```
### Test Package Cache Update
```bash
# Aggiorna cache pacchetti UYUNI
curl -s -X POST http://10.172.5.5:5000/api/uyuni/sync-packages | jq

# Verifica statistiche pacchetti
curl -s http://10.172.5.5:5000/api/stats/packages | jq
```
### Test Push con Version Matching (FIX #1)
```bash
# Push 5 errata con version matching migliorato
curl -s -X POST "http://10.172.5.5:5000/api/uyuni/push?limit=5" | jq

# Output atteso:
# {
#   "status": "success",
#   "pushed": 5,
#   "skipped_no_packages": 0,
#   "skipped_version_mismatch": 2,  # NUOVO: pacchetti filtrati per versione
#   "pending_processed": 5,
#   "errors": null
# }
```
### Test OVAL Sync + CVE Mapping (FIX #2)
```bash
# Sync OVAL definitions per CVE audit
curl -s -X POST "http://10.172.5.5:5000/api/sync/oval?platform=all" | jq

# Verifica mappings creati
psql "postgresql://..." << EOF
SELECT COUNT(*) as total_mappings FROM errata_cve_oval_map;
SELECT e.advisory_id, c.cve_id, o.oval_id
FROM errata_cve_oval_map ecov
JOIN errata e ON ecov.errata_id = e.id
JOIN cves c ON ecov.cve_id = c.cve_id
JOIN oval_definitions o ON ecov.oval_id = o.oval_id
LIMIT 10;
EOF
```
## FASE 5: Deploy Script Automazione v2.5
### Copia Script sul Server UYUNI
```bash
# Dal tuo workstation, copia lo script
scp errata-sync-v2.5-IMPROVED.sh user@uyuni-server-test:/tmp/

# Connettiti al server UYUNI
ssh user@uyuni-server-test
sudo su -

# Sposta script in posizione
mv /tmp/errata-sync-v2.5-IMPROVED.sh /root/errata-sync.sh
chmod +x /root/errata-sync.sh
```
### Configura Variabili d'Ambiente
```bash
# Crea file di configurazione
cat > /root/.errata-sync.env << 'EOF'
# API Endpoints
PUBLIC_API=http://4.232.4.142:5000
INTERNAL_API=http://10.172.5.5:5000

# Email alerts (opzionale)
ALERT_EMAIL=your-email@example.com
EOF

chmod 600 /root/.errata-sync.env
```
### Test Manuale
```bash
# Source environment
source /root/.errata-sync.env

# Test esecuzione
/root/errata-sync.sh

# Verifica log
tail -f /var/log/errata-sync.log
```

**Output atteso**:
```
[2026-01-07 11:00:00] [INFO] ==========================================
[2026-01-07 11:00:00] [INFO]   UYUNI ERRATA MANAGER - SYNC v2.5
[2026-01-07 11:00:00] [INFO] ==========================================
[2026-01-07 11:00:00] [INFO] Start time: Tue Jan  7 11:00:00 CET 2026
[2026-01-07 11:00:00] [INFO] Lock acquired (PID: 12345)
[2026-01-07 11:00:05] [INFO] ========== HEALTH CHECK ==========
[2026-01-07 11:00:05] [SUCCESS] Health check passed
[2026-01-07 11:00:05] [INFO] ========== SYNCING UBUNTU USN ==========
[2026-01-07 11:00:45] [SUCCESS] USN sync completed: 12 errata, 234 packages
...
[2026-01-07 11:25:30] [INFO] ==========================================
[2026-01-07 11:25:30] [INFO]   SYNC COMPLETED
[2026-01-07 11:25:30] [INFO] ==========================================
[2026-01-07 11:25:30] [INFO] End time: Tue Jan  7 11:25:30 CET 2026
[2026-01-07 11:25:30] [INFO] Duration: 25m 30s
[2026-01-07 11:25:30] [INFO] Errors encountered: 0
[2026-01-07 11:25:30] [SUCCESS] All sync operations completed successfully!
```
### Setup Cron Job
```bash
# Aggiungi a crontab (esegui ogni domenica alle 02:00)
cat > /etc/cron.d/errata-sync << 'EOF'
# UYUNI Errata Manager - Weekly Sync
0 2 * * 0 root source /root/.errata-sync.env && /root/errata-sync.sh >> /var/log/errata-sync.log 2>&1
EOF

# Verifica cron
crontab -l
```

## FASE 6: Monitoring e Validazione
### Setup Log Rotation
```bash
cat > /etc/logrotate.d/errata-sync << 'EOF'
/var/log/errata-sync.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
    create 0640 root root
}

/var/log/errata-sync-errors.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
    create 0640 root root
}
EOF
```
### Verifica Errata in UYUNI
```bash
# Web UI:
# Vai a: Patches → Patch List → All
# Filtra per "Imported by UYUNI Errata Manager v2.5"

# CLI check:
spacecmd errata_list | grep -i usn | head -5
```
### Verifica CVE Audit (NEW!)
```bash
# Web UI:
# Vai a: Audit → CVE Audit
# Cerca per CVE ID (es. CVE-2024-1234)
# Dovresti vedere sistemi vulnerabili grazie all'integrazione OVAL

# CLI check:
psql "postgresql://..." << EOF
-- Verifica CVE con OVAL mappati
SELECT c.cve_id, cd.cvss_v3_score, cd.severity, COUNT(ecov.oval_id) as oval_count
FROM cves c
JOIN cve_details cd ON c.cve_id = cd.cve_id
LEFT JOIN errata_cve_oval_map ecov ON c.cve_id = ecov.cve_id
WHERE cd.severity IN ('CRITICAL', 'HIGH')
GROUP BY c.cve_id, cd.cvss_v3_score, cd.severity
ORDER BY cd.cvss_v3_score DESC
LIMIT 20;
EOF
```
---

## Troubleshooting v2.5
### Container non risponde
```bash
# Verifica stato
az container show \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal \
  --query "instanceView.state"

# Verifica log
az container logs \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal \
  --tail 100

# Restart
az container restart \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal
```
### Version matching non funziona
```bash
# Verifica che la libreria packaging sia installata
curl http://10.172.5.5:5000/api/health
# Deve ritornare version: "2.5"

# Test version comparison
psql "postgresql://..." << EOF
-- Verifica pacchetti con versioni
SELECT package_name, package_version, fixed_version
FROM errata_packages ep
JOIN errata e ON ep.errata_id = e.id
WHERE e.advisory_id = 'USN-7931-4'
LIMIT 5;
EOF
```
### Sync DSA full troppo lento
```bash
# Il sync full DSA può richiedere 15-30 minuti (è normale)
# Monitora progress con:
watch -n 5 'curl -s http://10.172.5.5:5000/api/stats/overview | jq ".errata_by_source"'
```
### Email alerts non arrivano

```bash
# Verifica configurazione mail sul server UYUNI
echo "Test email" | mail -s "Test" your-email@example.com

# Se non funziona, installa postfix/sendmail
zypper install postfix
systemctl enable --now postfix
```

---

## Metriche di Successo
Dopo il deployment v2.5, dovresti vedere:

| Metrica | Prima (v2.4) | Dopo (v2.5) | Miglioramento |
|---------|--------------|-------------|---------------|
| **Tempo sync USN** | ~10 min | ~2 min | ✅ 5x più veloce |
| **Comandi DSA sync** | 8 manuali | 1 automatico | ✅ 100% automazione |
| **Errata con package IDs** | ~70% | ~95% | ✅ +25% coverage |
| **CVE visibili per sistema** | ❌ 0% | ✅ 100% (via OVAL) | ✅ Feature nuova |
| **Retry su failure** | ❌ No | ✅ 3 attempts | ✅ +99% reliability |
| **Tempo totale sync** | ~45 min | ~25 min | ✅ 1.8x più veloce |

---

## Riferimenti

- [app-v2.5-IMPROVED.py](./app-v2.5-IMPROVED.py) - Codice sorgente API
- [errata-sync-v2.5-IMPROVED.sh](./errata-sync-v2.5-IMPROVED.sh) - Script automazione
- [UYUNI-ERRATA-MANAGER-v2.4-GUIDA-COMPLETA.md](UYUNI-ERRATA-MANAGER.md) - Documentazione base
