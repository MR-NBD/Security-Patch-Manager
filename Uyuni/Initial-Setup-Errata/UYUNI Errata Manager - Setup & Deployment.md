# UYUNI Errata Manager — Setup & Deployment

Sincronizza automaticamente errata Ubuntu USN e Debian DSA verso UYUNI Server, con arricchimento severity NVD/CVSS.

## Architettura — 2 Container ACI

| Container | IP | Accesso | Ruolo |
|---|---|---|---|
| `aci-errata-api` | `4.232.4.142:5000` | Internet pubblico | Sync USN, DSA, NVD |
| `aci-errata-api-internal` | `10.172.5.4:5000` | VNet Azure | Sync packages, Push UYUNI |

- Il container **pubblico** non ha accesso alla VNet (no NAT Gateway) → non può raggiungere UYUNI
- Il container **interno** non ha accesso a internet → non può sincronizzare da ubuntu.com/debian.org
- Entrambi condividono lo stesso database PostgreSQL (endpoint diverso per ciascuno)

## Quick Start

### 1. Health Check

```bash
# Container pubblico
curl -s http://4.232.4.142:5000/api/health | jq

# Container interno (dal server UYUNI o da VM nella VNet)
curl -s http://10.172.5.4:5000/api/health | jq

# Stato dettagliato
curl -s http://4.232.4.142:5000/api/health/detailed | jq
curl -s http://10.172.5.4:5000/api/health/detailed | jq
```

### 2. Sync Manuale

```bash
# Sync da internet (container pubblico)
curl -s -X POST -H "X-API-Key: spm-key-2024" http://4.232.4.142:5000/api/sync/usn | jq
curl -s -X POST -H "X-API-Key: spm-key-2024" http://4.232.4.142:5000/api/sync/dsa | jq
curl -s -X POST -H "X-API-Key: spm-key-2024" "http://4.232.4.142:5000/api/sync/nvd?batch_size=100" | jq

# Push a UYUNI (container interno — dal server UYUNI)
curl -s -X POST -H "X-API-Key: spm-key-2024" http://10.172.5.4:5000/api/uyuni/sync-packages | jq
curl -s -X POST -H "X-API-Key: spm-key-2024" "http://10.172.5.4:5000/api/uyuni/push?limit=50" | jq
```

### 3. Sync Completo Automatico (Cron)

```bash
# Copia script sul server UYUNI
scp scripts/errata-sync-v3.sh root@10.172.2.17:/root/errata-sync.sh

# Configura cron (domenica 02:00)
cat > /etc/cron.d/errata-sync << 'EOF'
0 2 * * 0 root PUBLIC_API=http://4.232.4.142:5000 INTERNAL_API=http://10.172.5.4:5000 API_KEY=spm-key-2024 /root/errata-sync.sh >> /var/log/errata-sync.log 2>&1
EOF
```

## Prerequisito UYUNI (una volta sola)

Il server UYUNI (`10.172.2.17`) usa Podman e richiede una regola iptables per accettare connessioni esterne:

```bash
ssh root@10.172.2.17
iptables -t nat -I POSTROUTING -d 10.89.0.3 -p tcp --dport 443 -j MASQUERADE
service iptables save
```

## API Endpoints

### Container Pubblico (`4.232.4.142:5000`)

| Endpoint | Metodo | Auth | Descrizione |
|---|---|---|---|
| `/api/health` | GET | No | Stato base |
| `/api/health/detailed` | GET | No | Metriche e alert |
| `/api/sync/usn` | POST | Si | Sync Ubuntu USN |
| `/api/sync/dsa` | POST | Si | Sync Debian DSA |
| `/api/sync/nvd` | POST | Si | Enrichment NVD/CVSS |
| `/api/sync/status` | GET | Si | Log ultimi 20 sync |

### Container Interno (`10.172.5.4:5000`)

| Endpoint | Metodo | Auth | Descrizione |
|---|---|---|---|
| `/api/health` | GET | No | Stato base |
| `/api/health/detailed` | GET | No | Metriche e alert |
| `/api/uyuni/sync-packages` | POST | Si | Aggiorna cache pacchetti |
| `/api/uyuni/push` | POST | Si | Push errata a UYUNI |
| `/api/uyuni/channels` | GET | Si | Canali UYUNI rilevati |
| `/api/sync/status` | GET | Si | Log ultimi 20 sync |

## Documentazione

- **Deployment completo**: [DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md)
- **Schema database**: [sql/errata-schema.sql](sql/errata-schema.sql)
- **Script sync**: [scripts/errata-sync-v3.sh](scripts/errata-sync-v3.sh)
- **Test suite**: [scripts/test-endpoints.sh](scripts/test-endpoints.sh)

## Troubleshooting

```bash
# Log container pubblico
az container logs --resource-group test_group --name aci-errata-api --tail 50

# Log container interno
az container logs --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal --tail 50

# uyuni = "Connection refused" → applicare regola iptables (vedi prerequisito)
# Push skippati → aggiornare prima cache: POST /api/uyuni/sync-packages
```
