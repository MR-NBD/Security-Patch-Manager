# UYUNI - Security Patch Manager

Gestione centralizzata delle patch di sicurezza per Ubuntu/Debian tramite UYUNI Server.

## Panoramica

UYUNI (fork open source di SUSE Manager) non supporta nativamente gli avvisi di sicurezza per distribuzioni non-SUSE. Questo progetto colma questa lacuna sincronizzando automaticamente USN (Ubuntu) e DSA (Debian) verso UYUNI.

---

## Infrastruttura Attuale (2026-01-31)

### Componenti Azure

| Componente | Resource Group | Nome | Endpoint |
|------------|----------------|------|----------|
| Container Pubblico | test_group | aci-errata-api | `errata-api-spm.italynorth.azurecontainer.io:5000` |
| Container Interno | ASL0603-spoke10-rg-spoke-italynorth | aci-errata-api-internal | `10.172.5.4:5000` |
| UYUNI Server | - | uyuni-server-test | `10.172.2.17` |
| ACR | test_group | acaborerrata.azurecr.io | - |
| PostgreSQL | test_group | pg-errata-test | `pg-errata-test.postgres.database.azure.com` |
| Logic Apps | test_group | logic-usn-sync, logic-dsa-sync, logic-oval-sync, logic-nvd-sync | - |
| Private DNS Zone | ASL0603-spoke10-rg-spoke-italynorth | spm.internal | `api.spm.internal` |
| VNET | ASL0603-spoke10-rg-spoke-italynorth | ASL0603-spoke10-spoke-italynorth | `10.172.0.0/16` |
| Subnet ACI | - | errata-aci-subnet | `10.172.5.0/28` |

### Credenziali

| Servizio | Valore |
|----------|--------|
| ACR Password | `ga8BfwRu/awVcxCNhEY259j2hSZxXWnPmHOTVasYWY+ACRBM8B4W` |
| DB User | `errataadmin` |
| DB Password | `ErrataSecure2024` |
| UYUNI User | `admin` |
| UYUNI Password | `password` |
| NVD API Key | `49b6e254-d81d-4b61-abac-2dbe04471e38` |

### Architettura

> **NOTA**: Le Logic Apps (Consumption) non possono raggiungere IP privati. I sync avvengono via Logic Apps sul container pubblico, mentre i push a UYUNI sono gestiti da cron job sul server UYUNI.

```
┌─────────────────────────────────────────────────────────────────┐
│                      AZURE LOGIC APPS                           │
│  logic-usn-sync (6h) │ logic-dsa-sync (daily 03:00)            │
│  logic-oval-sync (weekly Sun 02:00) │ logic-nvd-sync (daily 04:00) │
│                    (Solo SYNC - no push)                        │
└─────────────────────────────┬───────────────────────────────────┘
                              │
Internet                      │    VNET PSN (10.172.0.0/16)
    │                         │           │
    ▼                         ▼           ▼
┌─────────────────────┐          ┌─────────────────────┐
│ Container Pubblico  │          │ Container Interno   │
│ errata-api-spm.     │──────────│ 10.172.5.4:5000     │
│ italynorth.azure    │ Database │ (errata-aci-subnet) │
│ container.io:5000   │ Condiviso│                     │
│                     │          │ - Push UYUNI        │
│ - Sync USN          │          │ - Sync Packages     │
│ - Sync DSA          │          │ - P3 Testing        │
│ - Sync OVAL         │          └──────────┬──────────┘
│ - Sync NVD          │                     │
└─────────────────────┘                     │ Cron Jobs
                                            ▼
                              ┌─────────────────────────┐
                              │ Server UYUNI            │
                              │ 10.172.2.17             │
                              │ (podman container)      │
                              │                         │
                              │ Cron:                   │
                              │ - errata-push.sh (6h)   │
                              │ - sync-channels.sh (1d) │
                              └─────────────────────────┘
```

---

## DEPLOYMENT COMPLETO DA ZERO

### FASE 1: Preparazione File (Azure Cloud Shell)

```bash
# Crea la cartella
mkdir -p ~/errata-api && cd ~/errata-api

# Crea requirements.txt
cat > requirements.txt << 'EOF'
flask==3.0.0
flask-cors==4.0.0
psycopg2-binary==2.9.9
requests==2.31.0
python-dateutil==2.8.2
lxml==5.1.0
gunicorn==21.2.0
packaging==23.2
EOF

# Crea Dockerfile (timeout 1800s per NVD/OVAL)
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./app.py
COPY p3_patch_testing.py ./p3_patch_testing.py

# Create log directory
RUN mkdir -p /var/log && touch /var/log/errata-manager.log

ENV FLASK_ENV=production

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Timeout 1800s (30 min) per sync NVD/OVAL lunghi
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "1800", "--graceful-timeout", "1800", "app:app"]
EOF

echo "File creati in ~/errata-api"
ls -la
```

### FASE 2: Upload File Python

Carica tramite icona **Upload** di Cloud Shell:
1. `Uyuni/Initial-Setup/app-v2.5-IMPROVED.py`
2. `Uyuni/Initial-Setup/p3_patch_testing.py`

Dopo l'upload:

```bash
mv ~/app-v2.5-IMPROVED.py ~/errata-api/app.py
mv ~/p3_patch_testing.py ~/errata-api/

# Verifica
ls -la ~/errata-api
```

### FASE 3: Build Immagine Container

```bash
cd ~/errata-api

# Build su ACR
az acr build \
  --registry acaborerrata \
  --image errata-api:v2.9 \
  --file Dockerfile .

# Verifica
az acr repository show-tags --name acaborerrata --repository errata-api --output table
```

### FASE 4: Deploy Container Pubblico (con DNS)

```bash
# Elimina se esiste
az container delete --resource-group test_group --name aci-errata-api --yes 2>/dev/null

# Attendi
sleep 15

# Crea container pubblico con DNS label
az container create \
  --resource-group test_group \
  --name aci-errata-api \
  --image acaborerrata.azurecr.io/errata-api:v2.9 \
  --registry-login-server acaborerrata.azurecr.io \
  --registry-username acaborerrata \
  --registry-password 'ga8BfwRu/awVcxCNhEY259j2hSZxXWnPmHOTVasYWY+ACRBM8B4W' \
  --dns-name-label errata-api-spm \
  --ports 5000 \
  --cpu 1 \
  --memory 4 \
  --os-type Linux \
  --location italynorth \
  --environment-variables \
    FLASK_ENV=production \
    DATABASE_URL='postgresql://errataadmin:ErrataSecure2024@pg-errata-test.postgres.database.azure.com:5432/uyuni_errata?sslmode=require' \
    NVD_API_KEY='49b6e254-d81d-4b61-abac-2dbe04471e38' \
  --restart-policy Always

# Verifica
az container show --resource-group test_group --name aci-errata-api \
  --query '{FQDN:ipAddress.fqdn, IP:ipAddress.ip, State:instanceView.state}' -o table
```

**DNS risultante**: `errata-api-spm.italynorth.azurecontainer.io:5000`

### FASE 5: Deploy Container Interno

```bash
# Elimina se esiste
az container delete --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal --yes 2>/dev/null

# Attendi
sleep 15

# Crea container interno
az container create \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal \
  --image acaborerrata.azurecr.io/errata-api:v2.9 \
  --registry-login-server acaborerrata.azurecr.io \
  --registry-username acaborerrata \
  --registry-password 'ga8BfwRu/awVcxCNhEY259j2hSZxXWnPmHOTVasYWY+ACRBM8B4W' \
  --ports 5000 \
  --cpu 1 \
  --memory 4 \
  --os-type Linux \
  --location italynorth \
  --ip-address Private \
  --vnet ASL0603-spoke10-spoke-italynorth \
  --subnet errata-aci-subnet \
  --environment-variables \
    FLASK_ENV=production \
    DATABASE_URL='postgresql://errataadmin:ErrataSecure2024@pg-errata-test.postgres.database.azure.com:5432/uyuni_errata?sslmode=require' \
    UYUNI_URL='https://10.172.2.17' \
    UYUNI_USER='admin' \
    UYUNI_PASSWORD='password' \
  --restart-policy Always

# Verifica e salva IP
INTERNAL_IP=$(az container show --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal --query 'ipAddress.ip' -o tsv)
echo "Container Interno IP: $INTERNAL_IP"
```

### FASE 6: Setup Private DNS Zone

```bash
# Crea Private DNS Zone (ignora errore se esiste)
az network private-dns zone create \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name spm.internal 2>/dev/null || echo "DNS Zone già esistente"

# Link alla VNET (ignora errore se esiste)
az network private-dns link vnet create \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --zone-name spm.internal \
  --name link-vnet-spm \
  --virtual-network ASL0603-spoke10-spoke-italynorth \
  --registration-enabled false 2>/dev/null || echo "Link già esistente"

# Ottieni IP container interno
INTERNAL_IP=$(az container show --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal --query 'ipAddress.ip' -o tsv)

# Elimina record esistente e ricrea
az network private-dns record-set a delete \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --zone-name spm.internal \
  --name api --yes 2>/dev/null

az network private-dns record-set a add-record \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --zone-name spm.internal \
  --record-set-name api \
  --ipv4-address $INTERNAL_IP

echo "DNS Record: api.spm.internal -> $INTERNAL_IP"
```

### FASE 7: Crea Logic Apps

> **IMPORTANTE**: Le Logic Apps (Consumption tier) non possono raggiungere IP privati. I push a UYUNI sono gestiti da cron job sul server UYUNI (vedi FASE 8).

```bash
# Elimina Logic Apps esistenti
az logic workflow delete --resource-group test_group --name logic-usn-sync --yes 2>/dev/null
az logic workflow delete --resource-group test_group --name logic-dsa-sync --yes 2>/dev/null
az logic workflow delete --resource-group test_group --name logic-oval-sync --yes 2>/dev/null
az logic workflow delete --resource-group test_group --name logic-nvd-sync --yes 2>/dev/null

echo "Logic Apps eliminate"
```

```bash
# logic-usn-sync (ogni 6 ore) - Solo sync, no push
az logic workflow create \
  --resource-group test_group \
  --name logic-usn-sync \
  --location italynorth \
  --definition '{
    "definition": {
      "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
      "contentVersion": "1.0.0.0",
      "triggers": {
        "Recurrence": {
          "type": "Recurrence",
          "recurrence": {"frequency": "Hour", "interval": 6}
        }
      },
      "actions": {
        "Sync_USN": {
          "type": "Http",
          "inputs": {
            "method": "POST",
            "uri": "http://errata-api-spm.italynorth.azurecontainer.io:5000/api/sync/usn"
          },
          "runAfter": {}
        }
      }
    }
  }'

echo "logic-usn-sync creata"
```

```bash
# logic-dsa-sync (ogni giorno alle 03:00) - Solo sync con timeout 30min
az logic workflow create \
  --resource-group test_group \
  --name logic-dsa-sync \
  --location italynorth \
  --definition '{
    "definition": {
      "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
      "contentVersion": "1.0.0.0",
      "triggers": {
        "Recurrence": {
          "type": "Recurrence",
          "recurrence": {
            "frequency": "Day",
            "interval": 1,
            "schedule": {"hours": ["3"], "minutes": [0]},
            "timeZone": "Central Europe Standard Time"
          }
        }
      },
      "actions": {
        "Sync_DSA": {
          "type": "Http",
          "inputs": {
            "method": "POST",
            "uri": "http://errata-api-spm.italynorth.azurecontainer.io:5000/api/sync/dsa/full"
          },
          "limit": {"timeout": "PT30M"},
          "runAfter": {}
        }
      }
    }
  }'

echo "logic-dsa-sync creata"
```

```bash
# logic-oval-sync (ogni domenica alle 02:00) - Ubuntu + Debian separati per evitare OOM
az logic workflow create \
  --resource-group test_group \
  --name logic-oval-sync \
  --location italynorth \
  --definition '{
    "definition": {
      "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
      "contentVersion": "1.0.0.0",
      "triggers": {
        "Recurrence": {
          "type": "Recurrence",
          "recurrence": {
            "frequency": "Week",
            "interval": 1,
            "schedule": {"weekDays": ["Sunday"], "hours": ["2"], "minutes": [0]},
            "timeZone": "Central Europe Standard Time"
          }
        }
      },
      "actions": {
        "Sync_OVAL_Ubuntu": {
          "type": "Http",
          "inputs": {
            "method": "POST",
            "uri": "http://errata-api-spm.italynorth.azurecontainer.io:5000/api/sync/oval?platform=ubuntu"
          },
          "limit": {"timeout": "PT25M"},
          "runAfter": {}
        },
        "Sync_OVAL_Debian": {
          "type": "Http",
          "inputs": {
            "method": "POST",
            "uri": "http://errata-api-spm.italynorth.azurecontainer.io:5000/api/sync/oval?platform=debian"
          },
          "limit": {"timeout": "PT35M"},
          "runAfter": {"Sync_OVAL_Ubuntu": ["Succeeded"]}
        }
      }
    }
  }'

echo "logic-oval-sync creata"
```

```bash
# logic-nvd-sync (ogni giorno alle 04:00) - batch 200, force=true
az logic workflow create \
  --resource-group test_group \
  --name logic-nvd-sync \
  --location italynorth \
  --definition '{
    "definition": {
      "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
      "contentVersion": "1.0.0.0",
      "triggers": {
        "Recurrence": {
          "type": "Recurrence",
          "recurrence": {
            "frequency": "Day",
            "interval": 1,
            "schedule": {"hours": ["4"], "minutes": [0]},
            "timeZone": "Central Europe Standard Time"
          }
        }
      },
      "actions": {
        "Sync_NVD": {
          "type": "Http",
          "inputs": {
            "method": "POST",
            "uri": "http://errata-api-spm.italynorth.azurecontainer.io:5000/api/sync/nvd?batch_size=200&force=true"
          },
          "limit": {"timeout": "PT30M"},
          "runAfter": {}
        }
      }
    }
  }'

echo "logic-nvd-sync creata"
```

```bash
# Verifica Logic Apps
az logic workflow list --resource-group test_group --output table
```

### FASE 8: Configura Cron Jobs sul Server UYUNI

I push a UYUNI e il sync dei canali sono gestiti da cron job sul server UYUNI.

```bash
# Connettiti al server UYUNI
ssh azureuser@uyuni-server-test

# Entra nel container UYUNI
sudo podman exec -it uyuni-server bash
```

**Script Push Errata** (esegue push a batch fino a esaurimento):

```bash
cat > /root/errata-push.sh << 'EOF'
#!/bin/bash
LOG="/var/log/errata-push.log"
API="http://10.172.5.4:5000"

echo "$(date) - Starting errata push" >> $LOG

while true; do
    response=$(curl -s -X POST "$API/api/uyuni/push?limit=50" 2>/dev/null)
    pushed=$(echo "$response" | jq -r '.pushed // 0')

    echo "$(date) - Pushed: $pushed" >> $LOG

    if [ "$pushed" -eq 0 ]; then
        break
    fi

    sleep 2
done

echo "$(date) - Push completed" >> $LOG
EOF
chmod +x /root/errata-push.sh
```

**Script Sync Canali** (sincronizza repository Ubuntu upstream):

```bash
cat > /root/sync-channels.sh << 'EOF'
#!/bin/bash
LOG="/var/log/channel-sync.log"
echo "$(date) - Starting channel sync" >> $LOG

# Sync security channels (priorità)
spacewalk-repo-sync --channel ubuntu-2404-amd64-main-security-uyuni >> $LOG 2>&1
spacewalk-repo-sync --channel ubuntu-2404-amd64-universe-security-uyuni >> $LOG 2>&1

# Sync updates
spacewalk-repo-sync --channel ubuntu-2404-amd64-main-updates-uyuni >> $LOG 2>&1
spacewalk-repo-sync --channel ubuntu-2404-amd64-universe-updates-uyuni >> $LOG 2>&1

# Sync client tools (solo lunedì)
if [ "$(date +%u)" = "1" ]; then
    spacewalk-repo-sync --channel ubuntu-2404-amd64-uyuni-client >> $LOG 2>&1
fi

echo "$(date) - Channel sync completed" >> $LOG
EOF
chmod +x /root/sync-channels.sh
```

**Configura Cron Jobs**:

```bash
# Push errata ogni 6 ore (offset 30min dai sync Logic Apps)
echo "30 0,6,12,18 * * * root /root/errata-push.sh" > /etc/cron.d/errata-push

# Sync canali ogni notte alle 01:00
echo "0 1 * * * root /root/sync-channels.sh" > /etc/cron.d/uyuni-channel-sync

# Verifica
cat /etc/cron.d/errata-push
cat /etc/cron.d/uyuni-channel-sync
```

### FASE 9: Test

```bash
# Test container pubblico
curl -s http://errata-api-spm.italynorth.azurecontainer.io:5000/api/health | jq

# Test container interno (da UYUNI server)
curl -s http://10.172.5.4:5000/api/health | jq

# Test push manuale (da UYUNI server)
curl -s -X POST "http://10.172.5.4:5000/api/uyuni/push?limit=10" | jq

# Statistiche
curl -s http://errata-api-spm.italynorth.azurecontainer.io:5000/api/stats/overview | jq

# Verifica URL nelle Logic Apps
for app in logic-usn-sync logic-dsa-sync logic-oval-sync logic-nvd-sync; do
  echo "=== $app ==="
  az logic workflow show --resource-group test_group --name $app --query 'definition.actions' -o json 2>/dev/null | grep -o '"uri": "[^"]*"'
done
```

---

## OPERAZIONI QUOTIDIANE

### Sync Manuale

```bash
# Sync USN
curl -s -X POST "http://errata-api-spm.italynorth.azurecontainer.io:5000/api/sync/usn" | jq

# Sync DSA
curl -s -X POST "http://errata-api-spm.italynorth.azurecontainer.io:5000/api/sync/dsa/full" | jq

# Sync OVAL (15-30 min)
curl -s -X POST "http://errata-api-spm.italynorth.azurecontainer.io:5000/api/sync/oval" | jq

# Sync NVD (5-10 min)
curl -s -X POST "http://errata-api-spm.italynorth.azurecontainer.io:5000/api/sync/nvd" | jq

# Push a UYUNI (da UYUNI server o VNET)
curl -s -X POST "http://10.172.5.4:5000/api/uyuni/push" | jq
```

### Monitoraggio

```bash
# Health check
curl -s "http://errata-api-spm.italynorth.azurecontainer.io:5000/api/health" | jq

# Health dettagliato
curl -s "http://errata-api-spm.italynorth.azurecontainer.io:5000/api/health/detailed" | jq

# Statistiche
curl -s "http://errata-api-spm.italynorth.azurecontainer.io:5000/api/stats/overview" | jq

# Log container pubblico
az container logs --resource-group test_group --name aci-errata-api --tail 50

# Log container interno
az container logs --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal --tail 50
```

### Gestione Container

```bash
# STOP container (mantiene IP)
az container stop --resource-group test_group --name aci-errata-api
az container stop --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal

# START container (stesso IP)
az container start --resource-group test_group --name aci-errata-api
az container start --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal

# RESTART container (stesso IP)
az container restart --resource-group test_group --name aci-errata-api
az container restart --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal

# Stato container
az container list --query "[?contains(name, 'errata')].{Name:name, State:instanceView.state, IP:ipAddress.ip}" -o table
```

**IMPORTANTE**: Usa `stop/start` invece di `delete/create` per mantenere lo stesso IP!

---

## SE L'IP DEL CONTAINER INTERNO CAMBIA

Se elimini e ricrei il container interno, l'IP cambierà. Aggiorna:

```bash
# 1. Ottieni nuovo IP
INTERNAL_IP=$(az container show --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal --query 'ipAddress.ip' -o tsv)
echo "Nuovo IP: $INTERNAL_IP"

# 2. Aggiorna DNS record
az network private-dns record-set a delete --resource-group ASL0603-spoke10-rg-spoke-italynorth --zone-name spm.internal --name api --yes
az network private-dns record-set a add-record --resource-group ASL0603-spoke10-rg-spoke-italynorth --zone-name spm.internal --record-set-name api --ipv4-address $INTERNAL_IP

# 3. Ricrea Logic Apps con nuovo IP (vedi FASE 7)
```

---

## API Endpoints

| Endpoint | Metodo | Descrizione | Container |
|----------|--------|-------------|-----------|
| `/api/health` | GET | Health check | Entrambi |
| `/api/health/detailed` | GET | Health check dettagliato | Entrambi |
| `/api/sync/usn` | POST | Sync Ubuntu USN | Pubblico |
| `/api/sync/dsa/full` | POST | Sync Debian DSA | Pubblico |
| `/api/sync/oval` | POST | Sync OVAL definitions | Pubblico |
| `/api/sync/nvd` | POST | Sync NVD CVE details | Pubblico |
| `/api/uyuni/status` | GET | Stato connessione UYUNI | Interno |
| `/api/uyuni/push` | POST | Push errata a UYUNI | Interno |
| `/api/stats/overview` | GET | Statistiche generali | Entrambi |

---

## Automazione Completa

### Logic Apps (Azure) - Solo Sync

| Logic App | Frequenza | Azione | Timeout |
|-----------|-----------|--------|---------|
| logic-usn-sync | Ogni 6 ore | Sync USN | default |
| logic-dsa-sync | Daily 03:00 | Sync DSA full | 30 min |
| logic-oval-sync | Weekly Sun 02:00 | Sync OVAL Ubuntu + Debian | 25+35 min |
| logic-nvd-sync | Daily 04:00 | Sync NVD (batch 200, force) | 30 min |

### Cron Jobs (Server UYUNI) - Push e Canali

| Cron Job | Frequenza | Azione |
|----------|-----------|--------|
| errata-push.sh | Ogni 6 ore (00:30, 06:30...) | Push errata a UYUNI |
| sync-channels.sh | Daily 01:00 | Sync repository Ubuntu upstream |

> **Nota**: I push sono sfasati di 30 minuti rispetto ai sync per garantire che i nuovi errata siano già nel database.

---

## Troubleshooting

### Container non risponde

```bash
# Verifica stato
az container show --resource-group test_group --name aci-errata-api --query 'instanceView.state' -o tsv

# Restart
az container restart --resource-group test_group --name aci-errata-api

# Vedi log
az container logs --resource-group test_group --name aci-errata-api --tail 100
```

### Sync timeout

Il Dockerfile è configurato con timeout 1800s (30 min). Se ancora timeout:

```bash
# Verifica che l'immagine sia v2.9 con timeout corretto
az container show --resource-group test_group --name aci-errata-api --query 'containers[0].image' -o tsv
```

### Push fallisce

```bash
# Verifica connettività a UYUNI
curl -s http://10.172.5.4:5000/api/uyuni/status | jq

# Verifica credenziali nel container interno
az container show --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal --query 'containers[0].environmentVariables' -o table
```

---

## Statistiche (2026-01-31)

| Metrica | Valore |
|---------|--------|
| Errata totali | 116.261 (USN: 583, DSA: 115.678) |
| Errata pending | 116.078 |
| CVE tracciati | 47.845 |
| CVE con CVSS (NVD) | 228+ |
| OVAL definitions | 50.862 (Ubuntu: 5.359, Debian: 45.503) |
| Pacchetti in cache | 140.937 |
| Canali Ubuntu | 17 (main, universe, security, updates, CLM) |

---

## Versione

- **API**: v2.6 (app-v2.5-IMPROVED.py)
- **Container Image**: acaborerrata.azurecr.io/errata-api:v2.9
- **Gunicorn Timeout**: 1800s (30 min)
- **Ambiente**: PSN (Polo Strategico Nazionale)
- **Ultimo aggiornamento**: 2026-01-31

---

## Note Tecniche

### Limitazioni Logic Apps Consumption
Le Logic Apps (Consumption tier) non possono raggiungere IP privati nella VNET. Per questo motivo:
- I sync avvengono tramite Logic Apps → Container Pubblico
- I push avvengono tramite Cron Job sul Server UYUNI → Container Interno

### OVAL Memory Usage
Il sync OVAL con `platform=all` può causare OOM sul container (4GB RAM). Per evitarlo:
- Ubuntu e Debian sono sincronizzati separatamente
- Il sync Debian (40K+ definitions) richiede ~35 minuti

### NVD Rate Limiting
L'API NVD ha rate limiting:
- Con API Key: 0.6s tra richieste (50 CVE/min)
- Senza API Key: 6s tra richieste (10 CVE/min)
- 47K CVE richiedono ~16 ore con API Key per sync completo

---

## Service Remediation Automatico (N8N)

Sistema per gestire automaticamente i disservizi delle VM 24/7.

### Architettura

```
[Alert Email/Webhook] → [N8N Parser] → [VM Resolver] → [Salt Executor] → [Report Email]
                                            ↓
                                    [UYUNI Server]
                                    [Salt Master]
                                            ↓
                                    [VM Minions]
```

### Componenti

| Componente | Ubicazione | Funzione |
|------------|------------|----------|
| N8N | Container Podman | Orchestrazione workflow |
| Salt Master | Container UYUNI | Esecuzione comandi remoti |
| Salt Minion | VM gestite | Agent per remediation |

### Quick Start

```bash
# 1. Deploy N8N (sul server UYUNI o VM dedicata)
bash Automation/scripts/deploy-n8n.sh

# 2. Setup servizio test su VM Ubuntu
bash Automation/scripts/setup-test-service.sh

# 3. Importa workflow in N8N
# Vai a http://<n8n-host>:5678
# Settings > Import Workflow > Automation/n8n-workflows/service-remediation-workflow.json

# 4. Configura credenziali in N8N:
#    - SSH Key per UYUNI Server
#    - SMTP per invio email

# 5. Test end-to-end
bash Automation/scripts/test-remediation-e2e.sh --full
```

### Workflow N8N

1. **Trigger**: Webhook riceve alert (Prometheus, Zabbix, email)
2. **Parser**: Estrae vmName, service, organization dal payload
3. **Salt Commands**: Genera comandi `salt '<minion>' service.restart <service>`
4. **Execute**: SSH al container UYUNI, esegue Salt
5. **Report**: Genera HTML report con esito
6. **Email**: Invia notifica al team

### Test Manuale Remediation

```bash
# Simula crash del servizio
ssh root@<vm-ubuntu> /opt/spm-simulate-crash.sh

# Invia alert al webhook
curl -X POST http://n8n-host:5678/webhook/service-alert \
  -H "Content-Type: application/json" \
  -d '{"vmName":"vm-test-ubuntu","service":"spm-test-service","severity":"critical"}'

# Verifica stato
ssh root@<uyuni-server> "podman exec uyuni-server salt 'vm-test-ubuntu' service.status spm-test-service"
```

### Documentazione Completa

Vedi `Automation/N8N-SERVICE-REMEDIATION.md` per:
- Configurazione dettagliata N8N
- Parser per vari formati alert (Prometheus, Zabbix, custom)
- Integrazione UYUNI API XMLRPC
- Salt States per remediation
- Troubleshooting
