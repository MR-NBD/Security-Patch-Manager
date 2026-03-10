# UYUNI Errata Manager — Setup & Deployment

Sincronizza automaticamente errata Ubuntu USN e Debian DSA verso UYUNI Server, con arricchimento severity tramite NVD/CVSS.

## Quick Start

### 1. Health Check

```bash
# Stato base
curl -s http://10.172.5.5:5000/api/health | jq

# Stato dettagliato (metriche, alert, età sync)
curl -s http://10.172.5.5:5000/api/health/detailed | jq
```

### 2. Sync Completo

```bash
# Pipeline completa: auto-detect distribuzioni → USN → DSA → NVD → push
curl -s -X POST \
  -H "X-API-Key: <api-key>" \
  "http://10.172.5.5:5000/api/sync/auto?nvd_batch=100&push_limit=50" | jq
```

### 3. Automazione (Cron sul server UYUNI)

```bash
# Copia script
scp scripts/errata-sync-v3.sh root@10.172.2.5:/root/errata-sync.sh

# Configura cron (domenica 02:00)
cat > /etc/cron.d/errata-sync << 'EOF'
0 2 * * 0 root API=http://10.172.5.5:5000 /root/errata-sync.sh >> /var/log/errata-sync.log 2>&1
EOF
```

## API Endpoints

| Endpoint | Metodo | Auth | Descrizione |
|---|---|---|---|
| `/api/health` | GET | No | Stato base |
| `/api/health/detailed` | GET | No | Stato dettagliato con alert |
| `/api/sync/auto` | POST | Si | Pipeline completa |
| `/api/sync/usn` | POST | Si | Solo Ubuntu USN |
| `/api/sync/dsa` | POST | Si | Solo Debian DSA |
| `/api/sync/nvd` | POST | Si | Solo NVD enrichment |
| `/api/uyuni/sync-packages` | POST | Si | Aggiorna cache pacchetti |
| `/api/uyuni/push` | POST | Si | Push errata a UYUNI |
| `/api/uyuni/channels` | GET | Si | Canali UYUNI con distribuzione |
| `/api/sync/status` | GET | Si | Log ultimi 20 sync |

Auth: header `X-API-Key: <valore>` su tutti gli endpoint tranne `/api/health*`.

## Documentazione

- **Deployment completo**: [DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md)
- **Schema database**: [sql/errata-schema.sql](sql/errata-schema.sql)
- **Script sync**: [scripts/errata-sync-v3.sh](scripts/errata-sync-v3.sh)

## Troubleshooting

```bash
# Container log
az container logs \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal --tail 100

# Restart
az container restart \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal

# Sync log
curl -s -H "X-API-Key: <key>" http://10.172.5.5:5000/api/sync/status | jq '.logs[:5]'
```
