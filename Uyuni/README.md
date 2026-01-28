# UYUNI - Security Patch Manager

Gestione centralizzata delle patch di sicurezza per Ubuntu/Debian tramite UYUNI Server.

## Panoramica

UYUNI (fork open source di SUSE Manager) non supporta nativamente gli avvisi di sicurezza per distribuzioni non-SUSE. Questo progetto colma questa lacuna sincronizzando automaticamente USN (Ubuntu) e DSA (Debian) verso UYUNI.

## Struttura del Progetto

```
Uyuni/
├── README.md                              # Questo file
│
├── Teoria/                                # Documenti teorici
│   ├── Concetti-Fondamentali-UYUNI.md    # Architettura, sicurezza, concetti tecnici
│   └── Supported-Clients.md               # OS e features supportati
│
├── Infrastructure-Design/                 # Design architetturale
│   ├── Azure Security-First Architecture (Conforme PSN).md
│   └── P3-PATCH-TESTING-DESIGN.md        # Design modulo Patch Testing
│
├── Deployment/                            # Guide operative
│   ├── DEPLOYMENT-GUIDE.md               # Guida deployment API
│   ├── Installazione-UYUNI-Server.md     # Setup UYUNI su Azure
│   ├── Setup-Canali-Ubuntu.md            # Configurazione canali Ubuntu 22.04
│   └── Configurazione-Ubuntu-24.04.md    # Setup completo Ubuntu 24.04
│
└── Initial-Setup/                         # Codice sorgente
    ├── UYUNI Errata Manager - Setup & Deployment.md  # Quick reference
    ├── app-v2.5-IMPROVED.py              # API Flask v2.6
    ├── p3_patch_testing.py               # Modulo P3 Patch Testing
    ├── Dockerfile                         # Container image definition
    ├── requirements.txt                   # Python dependencies
    ├── sql/                               # Schema database
    └── scripts/                           # Script operativi
```

## Quick Start

### 1. Verifica Sistema

```bash
# Health check container pubblico
curl -s http://4.232.4.143:5000/api/health | jq

# Health check container interno (da UYUNI server)
curl -s http://10.172.5.5:5000/api/health | jq
```

### 2. Sync Completo

```bash
# FASE 1: Sync esterni (da PC/Azure Cloud Shell)
curl -X POST http://4.232.4.143:5000/api/sync/usn
curl -X POST http://4.232.4.143:5000/api/sync/dsa/full
curl -X POST http://4.232.4.143:5000/api/sync/oval
curl -X POST http://4.232.4.143:5000/api/sync/nvd

# FASE 2: Push a UYUNI (da server UYUNI o rete interna)
curl -X POST http://10.172.5.5:5000/api/uyuni/push
```

### 3. Verifica in UYUNI

- **Patches**: Web UI > Patches > Patch List
- **CVE Audit**: Web UI > Audit > CVE Audit

## Documentazione

### Teoria e Concetti

| Documento | Contenuto |
|-----------|-----------|
| [Concetti Fondamentali UYUNI](UYUNI.md) | Architettura, sicurezza, comunicazione Salt, gestione vulnerabilità |
| [Supported Clients](Teoria/Supported-Clients.md) | Tabella OS e features supportati |

### Architettura

| Documento | Contenuto |
|-----------|-----------|
| [Azure PSN Architecture](Infrastructure-Design/Azure%20Security-First%20Architecture%20(Conforme%20PSN).md) | Infrastruttura Azure conforme PSN |
| [P3 Patch Testing](Infrastructure-Design/P3-PATCH-TESTING-DESIGN.md) | Design modulo test patch automatizzato |

### Deployment e Operazioni

| Documento | Contenuto |
|-----------|-----------|
| [Deployment Guide](Deployment/DEPLOYMENT-GUIDE.md) | Deploy container API Flask |
| [Installazione UYUNI](Deployment/Installazione-UYUNI-Server.md) | Setup UYUNI Server su Azure |
| [Setup Ubuntu 24.04](Deployment/Configurazione-Ubuntu-24.04.md) | Configurazione completa canali Ubuntu |

## Architettura

```
┌─────────────────────────────────────────────────────────────────┐
│                      AZURE LOGIC APPS                           │
│  logic-usn-sync (6h) │ logic-dsa-sync (daily 03:00)            │
│  logic-oval-sync (weekly Sun 02:00) │ logic-nvd-sync (daily 04:00) │
└─────────────────────────────┬───────────────────────────────────┘
                              │
Internet                      │    VNET PSN (10.172.0.0/16)
    │                         │           │
    ▼                         ▼           ▼
┌─────────────────┐              ┌─────────────────┐
│ Container       │              │ Container       │
│ Pubblico        │──────────────│ Interno         │
│ 4.232.4.143:5000│   Database   │ 10.172.5.5:5000 │
│ (test_group)    │   Condiviso  │ (errata-aci-subnet) │
│                 │              │                 │
│ - Sync USN      │              │ - Push UYUNI    │
│ - Sync DSA      │              │ - P3 Testing    │
│ - Sync OVAL     │              └────────┬────────┘
│ - Sync NVD      │                       │
└─────────────────┘                       ▼
                             ┌─────────────────┐
                             │ Server UYUNI    │
                             │ 10.172.2.5      │
                             │ (podman container) │
                             └─────────────────┘
```

## Componenti Azure

| Componente | Resource Group | Dettagli |
|------------|----------------|----------|
| Container Pubblico | test_group | aci-errata-api, IP: 4.232.4.143 |
| Container Interno | ASL0603-spoke10-rg-spoke-italynorth | aci-errata-api-internal, IP: 10.172.5.5 |
| ACR | test_group | acaborerrata.azurecr.io |
| PostgreSQL | test_group | pg-errata-test.postgres.database.azure.com |
| Logic Apps | test_group | logic-usn-sync, logic-dsa-sync, logic-oval-sync, logic-nvd-sync |
| NSG | ASL0603-spoke10-rg-spoke-italynorth | nsg-errata-aci (allow port 5000 from VNET) |

## API Endpoints

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/health/detailed` | GET | Health check dettagliato |
| `/api/sync/usn` | POST | Sync Ubuntu USN |
| `/api/sync/dsa/full` | POST | Sync Debian DSA |
| `/api/sync/oval` | POST | Sync OVAL definitions |
| `/api/sync/nvd` | POST | Sync NVD CVE details |
| `/api/uyuni/status` | GET | Stato connessione UYUNI |
| `/api/uyuni/push` | POST | Push errata a UYUNI |
| `/api/patch-test/start` | POST | Avvia test patch (P3) |
| `/api/stats/overview` | GET | Statistiche generali |

## Statistiche Attuali (2026-01-28)

| Metrica | Valore |
|---------|--------|
| CVE totali | 47,620 |
| Errata totali | 115,185 |
| Errata USN | 573 |
| Errata DSA | 114,612 |
| OVAL definitions | 86,827 |

## Fonti Dati

| Fonte | Descrizione | Frequenza |
|-------|-------------|-----------|
| Ubuntu USN | Advisory sicurezza Ubuntu | Ogni 6 ore |
| Debian DSA | Advisory sicurezza Debian | Giornaliero |
| OVAL | Definizioni per CVE audit | Settimanale |
| NVD | CVE enrichment (CVSS scores) | Giornaliero |

## Configurazione Container

### Container Pubblico (aci-errata-api)

```bash
az container create \
  --resource-group test_group \
  --name aci-errata-api \
  --image acaborerrata.azurecr.io/errata-api:v2.9 \
  --registry-login-server acaborerrata.azurecr.io \
  --registry-username acaborerrata \
  --registry-password "<ACR_PASSWORD>" \
  --os-type Linux \
  --cpu 1 \
  --memory 4 \
  --ports 5000 \
  --ip-address Public \
  --environment-variables \
    FLASK_ENV=production \
    DATABASE_URL='postgresql://errataadmin:<DB_PASSWORD>@pg-errata-test.postgres.database.azure.com:5432/uyuni_errata?sslmode=require' \
  --restart-policy Always \
  --location italynorth
```

### Container Interno (aci-errata-api-internal)

```bash
az container create \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal \
  --image acaborerrata.azurecr.io/errata-api:v2.9 \
  --registry-login-server acaborerrata.azurecr.io \
  --registry-username acaborerrata \
  --registry-password "<ACR_PASSWORD>" \
  --os-type Linux \
  --cpu 1 \
  --memory 4 \
  --ports 5000 \
  --ip-address Private \
  --vnet ASL0603-spoke10-spoke-italynorth \
  --subnet errata-aci-subnet \
  --environment-variables \
    FLASK_ENV=production \
    DATABASE_URL='postgresql://errataadmin:<DB_PASSWORD>@pg-errata-test.postgres.database.azure.com:5432/uyuni_errata?sslmode=require' \
    UYUNI_URL='https://10.172.2.5' \
    UYUNI_USER='admin' \
    UYUNI_PASSWORD='<UYUNI_PASSWORD>' \
  --restart-policy Always \
  --location italynorth
```

## Network Configuration

### Route Table (ASL0603-spoke10-spoke-routetable)

| Route | Prefisso | Next Hop |
|-------|----------|----------|
| internal-vnet-traffic | 10.172.0.0/16 | VnetLocal |
| database-route | 172.213.219.93/32 | Internet |
| udr-default-to-hub-nva | 0.0.0.0/0 | 198.18.48.68 |

### NSG Rules (nsg-errata-aci)

| Rule | Priority | Source | Dest Port | Action |
|------|----------|--------|-----------|--------|
| allow-vnet-5000 | 100 | 10.172.0.0/16 | 5000 | Allow |

## Versione

- **API**: v2.9 (timeout 1800s per sync lunghi)
- **Container Image**: acaborerrata.azurecr.io/errata-api:v2.9
- **Ambiente**: PSN (Polo Strategico Nazionale)
- **Ultimo aggiornamento**: 2026-01-28
