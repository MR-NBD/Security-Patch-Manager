# UYUNI Errata Manager — Deployment Guide v3.1

Microservizio Flask che sincronizza errata di sicurezza (Ubuntu USN, Debian DSA) verso UYUNI Server, arricchendo la severity tramite NVD/CVSS.

---

## Architettura

```
Internet ──► [Errata Manager Container :5000]
                    │  XML-RPC
                    ▼
              [UYUNI Server :443]
                    │
              [PostgreSQL DB :5432]
```

- **Container**: `acaborerrata.azurecr.io/errata-api:v3.1`
- **Resource Group**: `ASL0603-spoke10-rg-spoke-italynorth`
- **Container name**: `aci-errata-api-internal`
- **IP interno**: `10.172.5.5:5000`
- **Database**: PostgreSQL su `10.172.2.6:5432` (db: `uyuni_errata`)
- **UYUNI**: `https://10.172.2.5`

---

## Variabili d'Ambiente

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `DATABASE_URL` | **SI** | — | `postgresql://user:pass@host:5432/db?sslmode=require` |
| `UYUNI_URL` | **SI** | — | es. `https://10.172.2.5` |
| `UYUNI_USER` | **SI** | — | Account admin UYUNI XML-RPC |
| `UYUNI_PASSWORD` | **SI** | — | Password account UYUNI |
| `SPM_API_KEY` | Raccomandato | — | Chiave API (header `X-API-Key`) |
| `NVD_API_KEY` | Raccomandato | — | Chiave NVD per rate limit elevato |
| `UYUNI_VERIFY_SSL` | No | `false` | Verifica certificato UYUNI |
| `CORS_ORIGIN` | No | — | Origin CORS permessa |
| `LOG_FILE` | No | `/var/log/errata-manager.log` | Path log |

---

## Deploy

### 1. Database

Applicare lo schema se non già presente:

```bash
psql "postgresql://errataadmin:ErrataSecure2024@10.172.2.6:5432/uyuni_errata?sslmode=require" \
    -f sql/errata-schema.sql
```

### 2. Build Immagine

```bash
ACR_NAME="acaborerrata"
IMAGE_TAG="v3.1"

az acr build \
  --registry $ACR_NAME \
  --image errata-api:$IMAGE_TAG \
  --file Dockerfile .

# Verifica
az acr repository show-tags --name $ACR_NAME --repository errata-api --output table
```

### 3. Deploy Container

```bash
RG="ASL0603-spoke10-rg-spoke-italynorth"
ACR_NAME="acaborerrata"
IMAGE_TAG="v3.1"
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

# Backup container esistente
az container export \
  --resource-group $RG \
  --name aci-errata-api-internal \
  --file backup-$(date +%Y%m%d).yaml

# Elimina vecchio
az container delete --resource-group $RG --name aci-errata-api-internal --yes

# Deploy v3.1
az container create \
  --resource-group $RG \
  --name aci-errata-api-internal \
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
    UYUNI_PASSWORD="<password>" \
    SPM_API_KEY="<api-key>" \
    NVD_API_KEY="<nvd-api-key>"
```

---

## Verifica Post-Deploy

```bash
# Health base
curl -s http://10.172.5.5:5000/api/health | jq

# Health dettagliato (metriche, alert)
curl -s http://10.172.5.5:5000/api/health/detailed | jq

# Canali UYUNI rilevati
curl -s -H "X-API-Key: <api-key>" http://10.172.5.5:5000/api/uyuni/channels | jq
```

Output atteso (`/api/health`):
```json
{
  "api": "ok",
  "database": "ok",
  "uyuni": "ok",
  "version": "3.1"
}
```

Output atteso (`/api/health/detailed`):
```json
{
  "version": "3.1",
  "timestamp": "2026-03-10T10:00:00",
  "database": {
    "connected": true,
    "errata_total": 5234,
    "errata_pending": 42
  },
  "uyuni": {
    "connected": true,
    "url": "https://10.172.2.5"
  },
  "sync_status": {
    "last_usn_sync": "2026-03-10T08:00:00",
    "usn_age_hours": 2.0,
    "last_dsa_sync": "2026-03-09T20:00:00",
    "dsa_age_hours": 14.0,
    "last_nvd_sync": "2026-03-10T08:30:00",
    "nvd_age_hours": 1.5
  },
  "cache": {
    "total_packages": 45231,
    "last_update": "2026-03-10T09:00:00",
    "age_hours": 1.0
  },
  "alerts": {
    "failed_syncs_24h": 0,
    "stale_cache": false,
    "stale_usn_sync": false,
    "stale_dsa_sync": false
  }
}
```

---

## Automazione Sync (Cron sul server UYUNI)

Copiare `scripts/errata-sync-v3.sh` sul server UYUNI:

```bash
scp scripts/errata-sync-v3.sh root@10.172.2.5:/root/errata-sync.sh
ssh root@10.172.2.5 chmod +x /root/errata-sync.sh
```

Configurare cron:

```bash
cat > /etc/cron.d/errata-sync << 'EOF'
# UYUNI Errata Manager - Sync settimanale (domenica 02:00)
0 2 * * 0 root API=http://10.172.5.5:5000 /root/errata-sync.sh >> /var/log/errata-sync.log 2>&1
EOF
```

Log rotation:

```bash
cat > /etc/logrotate.d/errata-sync << 'EOF'
/var/log/errata-sync.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
}
/var/log/errata-sync-errors.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
}
EOF
```

---

## API Reference

Tutti gli endpoint (eccetto `/api/health*`) richiedono l'header `X-API-Key`.

| Endpoint | Metodo | Auth | Descrizione |
|---|---|---|---|
| `/api/health` | GET | No | Stato base: API, DB, UYUNI |
| `/api/health/detailed` | GET | No | Stato dettagliato con metriche e alert |
| `/api/sync/auto` | POST | Si | Pipeline completa (USN + DSA + NVD + push) |
| `/api/sync/usn` | POST | Si | Solo sync Ubuntu USN |
| `/api/sync/dsa` | POST | Si | Solo sync Debian DSA |
| `/api/sync/nvd` | POST | Si | Solo enrichment NVD/CVSS |
| `/api/uyuni/sync-packages` | POST | Si | Aggiorna cache pacchetti UYUNI |
| `/api/uyuni/push` | POST | Si | Push errata pending a UYUNI |
| `/api/uyuni/channels` | GET | Si | Lista canali UYUNI con distribuzione |
| `/api/sync/status` | GET | Si | Log ultimi 20 sync |

### Parametri `/api/sync/auto`

| Parametro | Default | Max | Descrizione |
|---|---|---|---|
| `nvd_batch` | 100 | 500 | CVE da processare per run |
| `push_limit` | 50 | 200 | Errata da pushare per run |

### Parametri `/api/sync/nvd`

| Parametro | Default | Descrizione |
|---|---|---|
| `batch_size` | 50 | CVE da processare |
| `force` | false | Ri-processa CVE già enrichiti |

### Parametri `/api/uyuni/push`

| Parametro | Default | Max | Descrizione |
|---|---|---|---|
| `limit` | 10 | 200 | Errata da pushare |

---

## Troubleshooting

### Container non risponde

```bash
# Stato
az container show \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal \
  --query "instanceView.state"

# Log
az container logs \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal \
  --tail 100

# Restart
az container restart \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal
```

### Sync DSA lento

Il download del tracker Debian (~63 MB) richiede 5-15 minuti. Il timeout gunicorn è impostato a 1800s. Normale comportamento.

### Push errata skippati (version mismatch)

I pacchetti nella cache UYUNI non hanno ancora la versione fissa. Aggiornare prima la cache:

```bash
curl -s -X POST -H "X-API-Key: <key>" http://10.172.5.5:5000/api/uyuni/sync-packages | jq
```

Poi rieseguire il push.

### Verifica errata in UYUNI

```bash
# Web UI: Patches → Patch List → Filter: "Imported by UYUNI Errata Manager v3.1"

# API
curl -s "http://10.172.5.5:5000/api/sync/status" -H "X-API-Key: <key>" | jq '.logs[:5]'
```
