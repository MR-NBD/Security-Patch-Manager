# UYUNI Errata Manager — Deployment Guide v3.1

Microservizio Flask che sincronizza errata di sicurezza (Ubuntu USN, Debian DSA) verso UYUNI Server, arricchendo la severity tramite NVD/CVSS.

---

## Architettura — 2 Container ACI

```
Internet (ubuntu.com, debian.org, nvd.nist.gov)
        │
        ▼
┌─────────────────────────────┐
│  aci-errata-api  (pubblico) │  IP: 4.232.4.142:5000
│  Resource Group: test_group │  ← accesso internet pubblico
│                             │  → /api/sync/usn
│                             │  → /api/sync/dsa
│                             │  → /api/sync/nvd
└──────────────┬──────────────┘
               │ DB condiviso
               ▼
       [PostgreSQL :5432]
        10.172.2.6  (VNet)
        pg-errata-test.postgres.database.azure.com (pubblico)
               │
┌──────────────┴──────────────────┐
│  aci-errata-api-internal (VNet) │  IP: 10.172.5.4:5000
│  RG: ASL0603-spoke10-rg-...    │  ← accesso VNet Azure (no internet)
│                                 │  → /api/uyuni/sync-packages
│                                 │  → /api/uyuni/push
│                                 │  → /api/uyuni/channels
└──────────────┬──────────────────┘
               │ XML-RPC
               ▼
       [UYUNI Server :443]
        10.172.2.17  (VNet)
```

### Regola fondamentale

| Container | Internet | VNet / UYUNI | Endpoints usati |
|---|---|---|---|
| `aci-errata-api` | ✅ | ❌ | `/api/sync/usn`, `/api/sync/dsa`, `/api/sync/nvd` |
| `aci-errata-api-internal` | ❌ | ✅ | `/api/uyuni/sync-packages`, `/api/uyuni/push` |

I due container **condividono lo stesso database** ma accedono tramite endpoint diversi:
- Container pubblico → `pg-errata-test.postgres.database.azure.com` (endpoint pubblico Azure PostgreSQL)
- Container interno → `10.172.2.6:5432` (IP privato VNet)

---

## Variabili d'Ambiente

### Container Pubblico (`aci-errata-api`)

| Variabile | Obbligatoria | Valore |
|---|---|---|
| `DATABASE_URL` | **SI** | `postgresql://errataadmin:...@pg-errata-test.postgres.database.azure.com:5432/uyuni_errata?sslmode=require` |
| `SPM_API_KEY` | Raccomandato | chiave condivisa con container interno |
| `NVD_API_KEY` | Raccomandato | `49b6e254-d81d-4b61-abac-2dbe04471e38` |
| `UYUNI_URL` | No | non necessaria (non fa push) |

### Container Interno (`aci-errata-api-internal`)

| Variabile | Obbligatoria | Valore |
|---|---|---|
| `DATABASE_URL` | **SI** | `postgresql://errataadmin:...@10.172.2.6:5432/uyuni_errata?sslmode=require` |
| `UYUNI_URL` | **SI** | `https://10.172.2.17` |
| `UYUNI_USER` | **SI** | `admin` |
| `UYUNI_PASSWORD` | **SI** | password admin UYUNI |
| `SPM_API_KEY` | Raccomandato | stessa chiave del container pubblico |

> **Nota IP UYUNI**: il server UYUNI ha IP `10.172.2.17` (non `10.172.2.5`). Usare sempre `10.172.2.17`.

---

## Prerequisito: iptables sul server UYUNI

UYUNI gira in un container Podman. Senza una regola di masquerade, il traffico dal container ACI interno viene rifiutato. Da eseguire **una volta sola** sul server UYUNI (`10.172.2.17`):

```bash
# Consente traffico esterno verso il container Podman UYUNI (10.89.0.3)
iptables -t nat -I POSTROUTING -d 10.89.0.3 -p tcp --dport 443 -j MASQUERADE

# Verifica
iptables -t nat -L POSTROUTING -n | grep 10.89.0.3

# Rendi persistente (SUSE/openSUSE)
service iptables save
# oppure:
iptables-save > /etc/iptables/rules.v4
```

---

## Deploy

### 1. Database

Applicare lo schema se non già presente (dalla VNet o dal server UYUNI):

```bash
# Dal server UYUNI
psql "postgresql://errataadmin:ErrataSecure2024@10.172.2.6:5432/uyuni_errata?sslmode=require" \
    -f /tmp/errata-schema.sql
```

### 2. Build Immagine (stessa per entrambi i container)

```bash
ACR_NAME="acaborerrata"
IMAGE_TAG="v3.1"

az acr build \
  --registry $ACR_NAME \
  --image errata-api:$IMAGE_TAG \
  --file Dockerfile .

az acr repository show-tags --name $ACR_NAME --repository errata-api --output table
```

### 3. Deploy Container PUBBLICO (`aci-errata-api`)

```bash
RG_PUB="test_group"
ACR_NAME="acaborerrata"
IMAGE_TAG="v3.1"
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

az container delete --resource-group $RG_PUB --name aci-errata-api --yes 2>/dev/null || true
sleep 10

az container create \
  --resource-group $RG_PUB \
  --name aci-errata-api \
  --image $ACR_NAME.azurecr.io/errata-api:$IMAGE_TAG \
  --registry-login-server $ACR_NAME.azurecr.io \
  --registry-username $ACR_NAME \
  --registry-password "$ACR_PASSWORD" \
  --os-type Linux --cpu 1 --memory 1.5 --ports 5000 \
  --ip-address Public \
  --restart-policy Always \
  --environment-variables \
    FLASK_ENV=production \
    DATABASE_URL="postgresql://errataadmin:ErrataSecure2024@pg-errata-test.postgres.database.azure.com:5432/uyuni_errata?sslmode=require" \
    SPM_API_KEY="spm-key-2024" \
    NVD_API_KEY="49b6e254-d81d-4b61-abac-2dbe04471e38"
```

### 4. Deploy Container INTERNO (`aci-errata-api-internal`)

```bash
RG_INT="ASL0603-spoke10-rg-spoke-italynorth"

az container delete --resource-group $RG_INT --name aci-errata-api-internal --yes 2>/dev/null || true
sleep 10

az container create \
  --resource-group $RG_INT \
  --name aci-errata-api-internal \
  --image $ACR_NAME.azurecr.io/errata-api:$IMAGE_TAG \
  --registry-login-server $ACR_NAME.azurecr.io \
  --registry-username $ACR_NAME \
  --registry-password "$ACR_PASSWORD" \
  --os-type Linux --cpu 1 --memory 1.5 --ports 5000 \
  --vnet ASL0603-spoke10-spoke-italynorth \
  --subnet errata-aci-subnet \
  --restart-policy Always \
  --environment-variables \
    FLASK_ENV=production \
    DATABASE_URL="postgresql://errataadmin:ErrataSecure2024@10.172.2.6:5432/uyuni_errata?sslmode=require" \
    UYUNI_URL="https://10.172.2.17" \
    UYUNI_USER="admin" \
    UYUNI_PASSWORD="Admin1234567!" \
    SPM_API_KEY="spm-key-2024" \
    NVD_API_KEY="49b6e254-d81d-4b61-abac-2dbe04471e38"
```

---

## Verifica Post-Deploy

```bash
# Container pubblico (accessibile da internet)
curl -s http://4.232.4.142:5000/api/health | jq
curl -s http://4.232.4.142:5000/api/health/detailed | jq

# Container interno (dal server UYUNI o da altra VM nella VNet)
curl -s http://10.172.5.4:5000/api/health | jq
curl -s http://10.172.5.4:5000/api/health/detailed | jq
```

Output atteso `/api/health` (container pubblico — uyuni non configurato è normale):
```json
{ "api": "ok", "database": "ok", "uyuni": "not configured", "version": "3.1" }
```

Output atteso `/api/health` (container interno):
```json
{ "api": "ok", "database": "ok", "uyuni": "ok", "version": "3.1" }
```

---

## Automazione Sync (Cron sul server UYUNI)

Copiare lo script:
```bash
scp scripts/errata-sync-v3.sh root@10.172.2.17:/root/errata-sync.sh
ssh root@10.172.2.17 chmod +x /root/errata-sync.sh
```

Configurare cron:
```bash
cat > /etc/cron.d/errata-sync << 'EOF'
# UYUNI Errata Manager v3.1 - Sync settimanale domenica 02:00
0 2 * * 0 root \
  PUBLIC_API=http://4.232.4.142:5000 \
  INTERNAL_API=http://10.172.5.4:5000 \
  API_KEY=spm-key-2024 \
  /root/errata-sync.sh >> /var/log/errata-sync.log 2>&1
EOF
```

Log rotation:
```bash
cat > /etc/logrotate.d/errata-sync << 'EOF'
/var/log/errata-sync.log /var/log/errata-sync-errors.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
}
EOF
```

---

## Test Suite

```bash
scp scripts/test-endpoints.sh root@10.172.2.17:/root/

ssh root@10.172.2.17
PUBLIC_API=http://4.232.4.142:5000 \
INTERNAL_API=http://10.172.5.4:5000 \
API_KEY=spm-key-2024 \
bash /root/test-endpoints.sh
```

---

## API Reference

Auth: header `X-API-Key` richiesto su tutti gli endpoint tranne `/api/health*`.

### Container Pubblico (`4.232.4.142:5000`)

| Endpoint | Metodo | Descrizione |
|---|---|---|
| `/api/health` | GET | Stato base (no auth) |
| `/api/health/detailed` | GET | Metriche e alert (no auth) |
| `/api/sync/usn` | POST | Sync Ubuntu USN |
| `/api/sync/dsa` | POST | Sync Debian DSA |
| `/api/sync/nvd` | POST | Enrichment NVD/CVSS |
| `/api/sync/status` | GET | Log ultimi 20 sync |

### Container Interno (`10.172.5.4:5000`)

| Endpoint | Metodo | Descrizione |
|---|---|---|
| `/api/health` | GET | Stato base (no auth) |
| `/api/health/detailed` | GET | Metriche e alert (no auth) |
| `/api/uyuni/sync-packages` | POST | Aggiorna cache pacchetti UYUNI |
| `/api/uyuni/push` | POST | Push errata pending a UYUNI |
| `/api/uyuni/channels` | GET | Canali UYUNI con distribuzione |
| `/api/sync/status` | GET | Log ultimi 20 sync |

### Parametri

| Endpoint | Parametro | Default | Max |
|---|---|---|---|
| `/api/sync/nvd` | `batch_size` | 50 | 500 |
| `/api/sync/nvd` | `force` | false | — |
| `/api/uyuni/push` | `limit` | 10 | 200 |

---

## Troubleshooting

### Container non risponde

```bash
# Pubblico
az container logs --resource-group test_group --name aci-errata-api --tail 50
az container restart --resource-group test_group --name aci-errata-api

# Interno
az container logs --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal --tail 50
az container restart --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal
```

### Container interno: `uyuni = "error: Connection refused"`

Il traffico dal container ACI verso UYUNI è bloccato da Netavark (Podman). Applicare la regola iptables sul server UYUNI:

```bash
ssh root@10.172.2.17
iptables -t nat -I POSTROUTING -d 10.89.0.3 -p tcp --dport 443 -j MASQUERADE
service iptables save
```

Verificare che UYUNI_URL sia `https://10.172.2.17` (non `10.172.2.5`).

### Push errata skippati (version mismatch)

Aggiornare prima la cache pacchetti, poi ripetere il push:
```bash
curl -s -X POST -H "X-API-Key: spm-key-2024" http://10.172.5.4:5000/api/uyuni/sync-packages | jq
```

### Sync DSA lento

Il tracker Debian (~63 MB) richiede 5-15 minuti. Timeout gunicorn 1800s. Comportamento normale.
