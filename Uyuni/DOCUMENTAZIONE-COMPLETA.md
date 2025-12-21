# UYUNI Errata Manager - Documentazione Completa

## Indice

1. [Panoramica del Progetto](#panoramica-del-progetto)
2. [Il Problema](#il-problema)
3. [La Soluzione](#la-soluzione)
4. [Architettura](#architettura)
5. [Flusso dei Dati](#flusso-dei-dati)
6. [Risorse Azure Create](#risorse-azure-create)
7. [Setup Passo-Passo](#setup-passo-passo)
8. [Configurazione di Rete](#configurazione-di-rete)
9. [API Endpoints](#api-endpoints)
10. [Errori Incontrati e Soluzioni](#errori-incontrati-e-soluzioni)
11. [Comandi Utili](#comandi-utili)
12. [Prossimi Passi](#prossimi-passi)

---

## Panoramica del Progetto

**UYUNI Errata Manager** è un sistema per sincronizzare automaticamente gli avvisi di sicurezza (errata/advisory) da Ubuntu e Debian verso un server UYUNI, colmando una lacuna nativa di UYUNI che non supporta nativamente gli errata per distribuzioni non-SUSE.

### Contesto

- **Ambiente**: PSN (Polo Strategico Nazionale) italiano, infrastruttura B2B IaaS
- **Server UYUNI**: `uyuni-server-test.uyuni.internal` (10.172.2.5)
- **Sistemi gestiti**: Ubuntu 24.04 (con possibilità di espansione a Debian)
- **Obiettivo**: Gestione centralizzata delle patch di sicurezza

---

## Il Problema

### UYUNI e le Distribuzioni Non-SUSE

UYUNI (fork open source di SUSE Manager) è progettato principalmente per SUSE Linux. Per Ubuntu e Debian:

- ✅ Può gestire i repository e i pacchetti
- ✅ Può distribuire aggiornamenti
- ❌ **NON** importa automaticamente gli avvisi di sicurezza (USN, DSA)
- ❌ **NON** può mostrare quali CVE affliggono i sistemi

### Cosa sono gli Errata?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ERRATA vs OVAL                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ERRATA (USN/DSA)                    │  OVAL                                │
│  ═══════════════                     │  ════                                │
│  "C'è una vulnerabilità CVE-xxx,     │  Definizioni XML per scanning:       │
│   aggiorna il pacchetto Y alla       │  "Se versione < X → vulnerabile"     │
│   versione Z"                        │                                      │
│                                      │                                      │
│  → Documentazione leggibile          │  → Rilevamento automatico            │
│  → Advisory per amministratori       │  → Audit di compliance               │
│                                      │                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Fonti Dati Utilizzate

| Fonte | URL | Formato | Note |
|-------|-----|---------|------|
| Ubuntu USN | `https://ubuntu.com/security/notices.json` | JSON | Paginato, max 20 per request |
| Debian Security Tracker | `https://security-tracker.debian.org/tracker/data/json` | JSON | File unico ~63MB |

---

## La Soluzione

### Componenti

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ARCHITETTURA SOLUZIONE                                  │
│                                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                 │
│  │   Ubuntu     │     │   Debian     │     │              │                 │
│  │   USN API    │     │   Security   │     │   UYUNI      │                 │
│  │              │     │   Tracker    │     │   Server     │                 │
│  └──────┬───────┘     └──────┬───────┘     └──────▲───────┘                 │
│         │                    │                    │                          │
│         │    INTERNET        │                    │  XML-RPC                 │
│         │                    │                    │                          │
│         ▼                    ▼                    │                          │
│  ┌─────────────────────────────────────┐         │                          │
│  │         ERRATA API (Flask)          │─────────┘                          │
│  │         Container ACI               │                                     │
│  │         10.172.5.4:5000             │                                     │
│  └──────────────┬──────────────────────┘                                     │
│                 │                                                            │
│                 │  SQL                                                       │
│                 ▼                                                            │
│  ┌─────────────────────────────────────┐                                     │
│  │      PostgreSQL Database            │                                     │
│  │      (Azure Flexible Server)        │                                     │
│  │      Private Endpoint: 10.172.2.6   │                                     │
│  └─────────────────────────────────────┘                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Stack Tecnologico

| Componente | Tecnologia | Versione |
|------------|------------|----------|
| API | Flask + Gunicorn | 3.0.0 / 21.2.0 |
| Database | PostgreSQL (Azure Flexible) | 16 |
| Container | Azure Container Instance | - |
| Registry | Azure Container Registry | Basic |
| Runtime | Python | 3.11 |

---

## Flusso dei Dati

### 1. Sync Ubuntu USN (Incrementale)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SYNC USN - FLUSSO                                     │
│                                                                              │
│  1. API riceve POST /api/sync/usn                                           │
│                                                                              │
│  2. Query DB: "Qual è l'ultimo USN sincronizzato?"                          │
│     SELECT advisory_id FROM errata WHERE source='usn'                       │
│     ORDER BY issued_date DESC LIMIT 1                                       │
│     → Risultato: USN-7922-3                                                 │
│                                                                              │
│  3. Fetch da Ubuntu API (paginato, 20 alla volta):                          │
│     GET https://ubuntu.com/security/notices.json?limit=20&offset=0          │
│                                                                              │
│  4. Per ogni notice:                                                        │
│     - Se advisory_id già esiste → STOP (incrementale!)                      │
│     - Altrimenti → aggiungi alla lista da processare                        │
│                                                                              │
│  5. Inserisci nuovi errata nel DB:                                          │
│     INSERT INTO errata (advisory_id, title, description, severity...)       │
│     ON CONFLICT (advisory_id) DO NOTHING                                    │
│                                                                              │
│  6. Inserisci CVE associati:                                                │
│     INSERT INTO cves (cve_id) ON CONFLICT DO UPDATE                         │
│     INSERT INTO errata_cves (errata_id, cve_id)                             │
│                                                                              │
│  7. Log sync completato                                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2. Sync Debian DSA (Batch)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SYNC DSA - FLUSSO                                     │
│                                                                              │
│  PROBLEMA: Il JSON Debian è ~63MB con struttura complessa                   │
│                                                                              │
│  Struttura JSON:                                                            │
│  {                                                                          │
│    "nome-pacchetto": {                                                      │
│      "CVE-2024-xxxx": {                                                     │
│        "description": "...",                                                │
│        "releases": {                                                        │
│          "bookworm": {"status": "resolved", "fixed_version": "1.2.3"},      │
│          "bullseye": {"status": "resolved", "fixed_version": "1.2.2"},      │
│          "trixie": {"status": "open"}                                       │
│        }                                                                    │
│      }                                                                      │
│    }                                                                        │
│  }                                                                          │
│                                                                              │
│  SOLUZIONE: Elaborazione a batch di 500 pacchetti                           │
│                                                                              │
│  1. POST /api/sync/dsa?offset=0    → pacchetti 0-499                        │
│  2. POST /api/sync/dsa?offset=500  → pacchetti 500-999                      │
│  3. POST /api/sync/dsa?offset=1000 → pacchetti 1000-1499                    │
│  ... (totale ~3700 pacchetti, ~8 batch)                                     │
│                                                                              │
│  Per ogni pacchetto → Per ogni CVE → Per ogni release target:               │
│  - Se status = "resolved" e fixed_version presente:                         │
│    → Crea errata: DEB-CVE-2024-xxxx-bookworm                                │
│                                                                              │
│  Mapping Urgency → Severity:                                                │
│  - critical/emergency → critical                                            │
│  - high → high                                                              │
│  - medium/not yet assigned → medium                                         │
│  - low/unimportant → low                                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3. Push a UYUNI

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PUSH UYUNI - FLUSSO                                   │
│                                                                              │
│  1. API riceve POST /api/uyuni/push                                         │
│                                                                              │
│  2. Connessione XML-RPC a UYUNI:                                            │
│     client.auth.login("admin", "password")                                  │
│                                                                              │
│  3. Leggi canali configurati:                                               │
│     client.channel.listAllChannels(session_key)                             │
│     → ["ubuntu-24.04-pool-amd64-uyuni", ...]                                │
│                                                                              │
│  4. Mappa canali a distribuzioni:                                           │
│     "ubuntu-24.04-*" → "ubuntu"                                             │
│     "debian-12-*" o "*bookworm*" → "debian-bookworm"                        │
│     "debian-11-*" o "*bullseye*" → "debian-bullseye"                        │
│                                                                              │
│  5. Query errata pending per distribuzioni attive:                          │
│     SELECT * FROM errata                                                    │
│     WHERE distribution IN ('ubuntu') AND sync_status = 'pending'            │
│     LIMIT 10                                                                │
│                                                                              │
│  6. Per ogni errata, chiama XML-RPC:                                        │
│     client.errata.create(session_key, {                                     │
│       'synopsis': 'USN-7922-3: Linux kernel vulnerabilities',               │
│       'advisory_name': 'USN-7922-3',                                        │
│       'advisory_type': 'Security Advisory',                                 │
│       'description': '...',                                                 │
│       ...                                                                   │
│     }, [], keywords, [], target_channels)                                   │
│                                                                              │
│  7. Aggiorna sync_status = 'synced'                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4. Visualizzazione in UYUNI

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     DOVE VEDERE GLI ERRATA IN UYUNI                          │
│                                                                              │
│  ✅ Patches → Patch List → All                                              │
│     Mostra tutti gli errata importati                                       │
│                                                                              │
│  ✅ Patches → Manage Patches → Published                                    │
│     Mostra errata pubblicati                                                │
│                                                                              │
│  ✅ Software → Channel List → (canale) → Patches                            │
│     Mostra errata associati a un canale                                     │
│                                                                              │
│  ❌ Systems → (sistema) → Software → Patches                                │
│     NON mostra errata perché manca associazione pacchetti                   │
│     → Richiede integrazione OVAL per rilevamento                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Risorse Azure Create

### Resource Group: test_group

| Risorsa | Nome | Tipo | Dettagli |
|---------|------|------|----------|
| PostgreSQL | pg-errata-test | Flexible Server | Standard_B1ms, 32GB |
| ACR | acaborerrata | Container Registry | Basic SKU |

### Resource Group: ASL0603-spoke10-rg-spoke-italynorth

| Risorsa | Nome | Tipo | Dettagli |
|---------|------|------|----------|
| Container | aci-errata-api | Container Instance | 1 CPU, 1.5GB RAM |
| Subnet | errata-aci-subnet | VNet Subnet | 10.172.5.0/28, delegata ACI |
| Private Endpoint | pe-pg-errata | Private Endpoint | Per PostgreSQL |

### Configurazione Rete

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              VNet: ASL0603-spoke10-spoke-italynorth                          │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Subnet: default (10.172.2.0/24)                                    │    │
│  │                                                                     │    │
│  │  • UYUNI Server: 10.172.2.5                                         │    │
│  │  • PostgreSQL Private Endpoint: 10.172.2.6                          │    │
│  │  • Altre VM Ubuntu                                                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Subnet: errata-aci-subnet (10.172.5.0/28)                          │    │
│  │  Delegata: Microsoft.ContainerInstance/containerGroups              │    │
│  │  Route Table: ASL0603-spoke10-spoke-routetable                      │    │
│  │                                                                     │    │
│  │  • API Container: 10.172.5.4                                        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Setup Passo-Passo

### Prerequisiti

- Azure CLI installato e autenticato
- Accesso alla subscription Azure
- Server UYUNI già configurato con canali Ubuntu

### Passo 1: Creare il Resource Group (se non esiste)

```bash
az group create --name test_group --location italynorth
```

### Passo 2: Creare PostgreSQL

```bash
az postgres flexible-server create \
  --resource-group test_group \
  --name pg-errata-test \
  --location italynorth \
  --admin-user errataadmin \
  --admin-password 'ErrataSecure2024' \
  --sku-name Standard_B1ms \
  --storage-size 32 \
  --version 16 \
  --public-access 0.0.0.0
```

### Passo 3: Creare Database e Schema

```bash
# Connetti e crea database
az postgres flexible-server db create \
  --resource-group test_group \
  --server-name pg-errata-test \
  --database-name uyuni_errata

# Connetti via psql (da Cloud Shell o VM)
psql "host=pg-errata-test.postgres.database.azure.com port=5432 dbname=uyuni_errata user=errataadmin password=ErrataSecure2024 sslmode=require"
```

```sql
-- Schema Database
CREATE TABLE IF NOT EXISTS errata (
    id SERIAL PRIMARY KEY,
    advisory_id VARCHAR(100) UNIQUE NOT NULL,
    title VARCHAR(500),
    description TEXT,
    severity VARCHAR(50),
    source VARCHAR(50),
    distribution VARCHAR(100),
    issued_date TIMESTAMP,
    sync_status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cves (
    id SERIAL PRIMARY KEY,
    cve_id VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    cvss_score DECIMAL(3,1),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS errata_cves (
    errata_id INTEGER REFERENCES errata(id),
    cve_id INTEGER REFERENCES cves(id),
    PRIMARY KEY (errata_id, cve_id)
);

CREATE TABLE IF NOT EXISTS sync_logs (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(50),
    status VARCHAR(50),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    items_processed INTEGER,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_errata_source ON errata(source);
CREATE INDEX IF NOT EXISTS idx_errata_distribution ON errata(distribution);
CREATE INDEX IF NOT EXISTS idx_errata_sync_status ON errata(sync_status);
CREATE INDEX IF NOT EXISTS idx_errata_severity ON errata(severity);
```

### Passo 4: Creare Azure Container Registry

```bash
az acr create \
  --resource-group test_group \
  --name acaborerrata \
  --sku Basic \
  --admin-enabled true
```

### Passo 5: Creare Subnet per ACI (nella VNet esistente)

```bash
# IMPORTANTE: Richiede route table per policy PSN
az network vnet subnet create \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --vnet-name ASL0603-spoke10-spoke-italynorth \
  --name errata-aci-subnet \
  --address-prefixes 10.172.5.0/28 \
  --delegations Microsoft.ContainerInstance/containerGroups \
  --route-table ASL0603-spoke10-spoke-routetable
```

### Passo 6: Creare Private Endpoint per PostgreSQL

```bash
PG_ID=$(az postgres flexible-server show \
  --resource-group test_group \
  --name pg-errata-test \
  --query id -o tsv)

az network private-endpoint create \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name pe-pg-errata \
  --vnet-name ASL0603-spoke10-spoke-italynorth \
  --subnet default \
  --private-connection-resource-id "$PG_ID" \
  --group-id postgresqlServer \
  --connection-name pg-errata-connection

# Ottieni IP privato
az network private-endpoint show \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name pe-pg-errata \
  --query "customDnsConfigs[0].ipAddresses[0]" \
  --output tsv
# Output: 10.172.2.6
```

### Passo 7: Creare i File dell'Applicazione

```bash
mkdir -p ~/uyuni-errata-manager
cd ~/uyuni-errata-manager

# Crea Dockerfile.api
cat > Dockerfile.api << 'EOF'
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libpq-dev gcc libc-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    flask==3.0.0 \
    flask-cors==4.0.0 \
    gunicorn==21.2.0 \
    psycopg2-binary==2.9.9 \
    requests==2.31.0

COPY app.py /app/

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "600", "app:app"]
EOF
```

### Passo 8: Creare app.py

Vedi sezione [Codice Completo app.py](#codice-completo-apppy) in fondo al documento.

### Passo 9: Build e Push dell'Immagine

```bash
az acr build \
  --registry acaborerrata \
  --image errata-api:v10 \
  --file Dockerfile.api .
```

### Passo 10: Deploy Container

```bash
ACR_PASSWORD=$(az acr credential show --name acaborerrata --query "passwords[0].value" -o tsv)

az container create \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api \
  --image acaborerrata.azurecr.io/errata-api:v10 \
  --registry-login-server acaborerrata.azurecr.io \
  --registry-username acaborerrata \
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
    UYUNI_PASSWORD="password"
```

### Passo 11: Sync Iniziale

```bash
# Da eseguire dal server UYUNI o da una VM nella stessa rete

# Health check
curl http://10.172.5.4:5000/api/health

# Sync Ubuntu USN
curl -X POST http://10.172.5.4:5000/api/sync/usn

# Sync Debian DSA (tutti i batch)
for offset in 0 500 1000 1500 2000 2500 3000 3500; do
  curl -X POST "http://10.172.5.4:5000/api/sync/dsa?offset=$offset&force=true"
done

# Push errata a UYUNI
for i in {1..10}; do
  curl -X POST http://10.172.5.4:5000/api/uyuni/push
done

# Verifica statistiche
curl http://10.172.5.4:5000/api/stats/overview
```

---

## API Endpoints

### Health & Stats

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/health` | GET | Health check (DB + UYUNI) |
| `/api/stats/overview` | GET | Statistiche complete |

### Errata & CVE

| Endpoint | Metodo | Parametri | Descrizione |
|----------|--------|-----------|-------------|
| `/api/errata` | GET | `limit`, `source`, `distribution`, `severity`, `sync_status` | Lista errata |
| `/api/errata/<id>` | GET | - | Dettaglio errata con CVE |
| `/api/cves` | GET | `limit` | Lista CVE |

### Sync

| Endpoint | Metodo | Parametri | Descrizione |
|----------|--------|-----------|-------------|
| `/api/sync/usn` | POST | - | Sync incrementale Ubuntu |
| `/api/sync/dsa` | POST | `offset`, `force` | Sync Debian (batch 500) |
| `/api/sync/status` | GET | - | Ultimi 20 sync logs |

### UYUNI Integration

| Endpoint | Metodo | Parametri | Descrizione |
|----------|--------|-----------|-------------|
| `/api/uyuni/status` | GET | - | Stato connessione + canali |
| `/api/uyuni/channels` | GET | - | Canali con conteggio errata |
| `/api/uyuni/push` | POST | `limit` (default 10) | Push errata pending |

---

## Errori Incontrati e Soluzioni

### 1. Worker Timeout su Debian Sync

**Errore**: `[CRITICAL] WORKER TIMEOUT (pid:22)`

**Causa**: Il JSON Debian è 63MB, troppo grande per elaborarlo in una singola richiesta.

**Soluzione**: 
- Aumentato timeout gunicorn a 600 secondi
- Implementato sync a batch con parametro `offset`
- Ogni batch elabora 500 pacchetti

```bash
# Prima (falliva)
curl -X POST /api/sync/dsa

# Dopo (funziona)
curl -X POST /api/sync/dsa?offset=0
curl -X POST /api/sync/dsa?offset=500
...
```

### 2. Struttura JSON Debian Complessa

**Errore**: Parsing errato, 0 errata importati.

**Causa**: Il JSON Debian ha struttura nested (pacchetto → CVE → release), non flat.

**Soluzione**: Implementato doppio loop:

```python
for package_name, package_data in packages:
    for cve_id, cve_data in package_data.items():
        if not cve_id.startswith('CVE-'):
            continue
        for release_name in ['bookworm', 'bullseye', 'trixie']:
            if release_name in cve_data.get('releases', {}):
                # Crea errata
```

### 3. Container Non Raggiunge Database

**Errore**: `Connection timed out` verso `pg-errata-test.postgres.database.azure.com`

**Causa**: Il container è in una VNet privata con route table che blocca traffico verso internet. Il database ha solo IP pubblico.

**Soluzione**: Creato Private Endpoint per PostgreSQL nella stessa VNet.

```bash
# Crea Private Endpoint
az network private-endpoint create ...

# Usa IP privato nel DATABASE_URL
DATABASE_URL="postgresql://...@10.172.2.6:5432/..."
```

### 4. Subnet Senza Address Prefix

**Errore**: `addressPrefix: null` nella subnet esistente.

**Causa**: Subnet creata precedentemente con configurazione errata.

**Soluzione**: Eliminata e ricreata la subnet con address prefix valido.

### 5. Policy PSN Route Table

**Errore**: `RequestDisallowedByPolicy - Subnets must have PSN Route Table`

**Causa**: Policy aziendale richiede route table su tutte le subnet.

**Soluzione**: Aggiunto parametro `--route-table` alla creazione subnet.

```bash
az network vnet subnet create ... \
  --route-table ASL0603-spoke10-spoke-routetable
```

### 6. Range IP Fuori dalla VNet

**Errore**: `NetcfgSubnetRangeOutsideVnet`

**Causa**: Tentato di creare subnet con range non presente nella VNet.

**Soluzione**: Verificato gli address space disponibili e usato un range valido.

```bash
# Verifica address space
az network vnet show ... --query "addressSpace.addressPrefixes"
# Output: ["10.172.2.0/24", "10.172.3.0/26", "10.172.4.0/26", "10.172.5.0/24"]

# Usa range disponibile
--address-prefixes 10.172.5.0/28
```

### 7. UYUNI: Missing Synopsis

**Errore**: `A required patch attribute (synopsis) was missing`

**Causa**: L'API UYUNI XML-RPC richiede il campo `synopsis` nell'oggetto errata.

**Soluzione**: Aggiunto `synopsis` al dizionario errata_info:

```python
client.errata.create(session_key, {
    'synopsis': errata['title'],  # AGGIUNTO
    'advisory_name': errata['advisory_id'],
    ...
})
```

### 8. UYUNI: DataException su Alcuni Errata

**Errore**: `org.hibernate.exception.DataException: could not execute statement`

**Causa**: Alcuni errata hanno descrizioni troppo lunghe o caratteri speciali.

**Soluzione**: Troncamento descrizioni e gestione errori per continuare con gli altri:

```python
description = (errata['description'] or '')[:2000]  # Tronca
```

### 9. ACR Image Inaccessible

**Errore**: `InaccessibleImage - image is not accessible`

**Causa**: Password ACR scaduta o errata.

**Soluzione**: Rigenerare password e usarla nel deploy:

```bash
ACR_PASSWORD=$(az acr credential show --name acaborerrata --query "passwords[0].value" -o tsv)
```

---

## Comandi Utili

### Gestione Container

```bash
# Stato container
az container show \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api \
  --query "{Status:instanceView.state, IP:ipAddress.ip}" \
  --output table

# Logs
az container logs \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api

# Restart
az container restart \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api

# Elimina
az container delete \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api \
  --yes
```

### Rebuild e Deploy

```bash
cd ~/uyuni-errata-manager

# Build nuova immagine
az acr build --registry acaborerrata --image errata-api:vNEW --file Dockerfile.api .

# Elimina vecchio container
az container delete --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api --yes

# Crea nuovo container
ACR_PASSWORD=$(az acr credential show --name acaborerrata --query "passwords[0].value" -o tsv)

az container create \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api \
  --image acaborerrata.azurecr.io/errata-api:vNEW \
  --registry-login-server acaborerrata.azurecr.io \
  --registry-username acaborerrata \
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
    UYUNI_PASSWORD="password"
```

### Test API

```bash
# Da server UYUNI o VM nella rete

# Health
curl http://10.172.5.4:5000/api/health

# Stats
curl http://10.172.5.4:5000/api/stats/overview

# Sync USN
curl -X POST http://10.172.5.4:5000/api/sync/usn

# Sync DSA (tutti i batch)
for offset in 0 500 1000 1500 2000 2500 3000 3500; do
  echo "Offset: $offset"
  curl -X POST "http://10.172.5.4:5000/api/sync/dsa?offset=$offset&force=true"
  echo ""
done

# Push a UYUNI
curl -X POST http://10.172.5.4:5000/api/uyuni/push

# Canali UYUNI
curl http://10.172.5.4:5000/api/uyuni/channels
```

---

## Prossimi Passi

### 1. Scheduler Automatico
Container separato che esegue sync ogni 6 ore:
- Sync USN incrementale
- Sync DSA completo
- Push automatico a UYUNI

### 2. Integrazione OVAL
Per rilevare vulnerabilità sui sistemi (non solo documentarle):
- Download OVAL definitions da Ubuntu/Debian
- Configurazione scan in UYUNI
- Correlazione con errata esistenti

### 3. Dashboard Grafana
Visualizzazione metriche:
- Errata per severity/distribuzione
- Trend vulnerabilità nel tempo
- Stato sync

### 4. Alerting
Notifiche per:
- Nuovi errata critical/high
- Errori di sync
- Sistemi con patch critiche pending

---

## Codice Completo app.py

```python
import os
import ssl
import xmlrpc.client
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import requests

app = Flask(__name__)
CORS(app)

REQUEST_HEADERS = {'User-Agent': 'UYUNI-Errata-Manager/1.0', 'Accept': 'application/json'}
UYUNI_URL = os.environ.get('UYUNI_URL', '')
UYUNI_USER = os.environ.get('UYUNI_USER', '')
UYUNI_PASSWORD = os.environ.get('UYUNI_PASSWORD', '')

def get_db():
    return psycopg2.connect(os.environ.get('DATABASE_URL'), cursor_factory=RealDictCursor)

def get_uyuni_client():
    if not UYUNI_URL:
        return None, None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    client = xmlrpc.client.ServerProxy(f"{UYUNI_URL}/rpc/api", context=context)
    session_key = client.auth.login(UYUNI_USER, UYUNI_PASSWORD)
    return client, session_key

def map_channel_to_distribution(channel_label):
    channel_lower = channel_label.lower()
    if 'ubuntu' in channel_lower:
        return 'ubuntu'
    if 'debian' in channel_lower:
        if 'bookworm' in channel_lower or 'debian-12' in channel_lower:
            return 'debian-bookworm'
        if 'bullseye' in channel_lower or 'debian-11' in channel_lower:
            return 'debian-bullseye'
        if 'trixie' in channel_lower or 'debian-13' in channel_lower:
            return 'debian-trixie'
    return None

# ... (resto del codice come mostrato nella sezione Setup)
```

Il codice completo è disponibile nel file `app.py` nella directory del progetto.

---

## Costi Stimati (Mensili)

| Risorsa | Costo Stimato |
|---------|---------------|
| PostgreSQL Standard_B1ms | ~€25 |
| Container Instance (1 CPU, 1.5GB) | ~€35 |
| ACR Basic | ~€5 |
| Private Endpoint | ~€7 |
| **TOTALE** | **~€72/mese** |

---

## Contatti e Riferimenti

- **Ubuntu Security Notices**: https://ubuntu.com/security/notices
- **Debian Security Tracker**: https://security-tracker.debian.org/
- **UYUNI Documentation**: https://www.uyuni-project.org/uyuni-docs/
- **UYUNI XML-RPC API**: https://www.uyuni-project.org/uyuni-docs/api/

---

*Documento creato il 21 Dicembre 2024*
*Versione: 1.0*
