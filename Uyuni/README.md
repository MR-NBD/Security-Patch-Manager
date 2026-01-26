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
    ├── sql/                               # Schema database
    └── scripts/                           # Script operativi
```

## Quick Start

### 1. Verifica Sistema

```bash
curl -s http://10.172.5.5:5000/api/health | jq
```

### 2. Sync Completo

```bash
# FASE 1: Sync esterni (da PC/Azure Cloud Shell)
curl -X POST http://4.232.4.32:5000/api/sync/usn
curl -X POST http://4.232.4.32:5000/api/sync/dsa/full

# FASE 2: Sync interni (da server UYUNI)
curl -X POST http://10.172.5.5:5000/api/uyuni/sync-packages
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
Internet                          VNET Privata (10.172.0.0/16)
    │                                     │
    ▼                                     ▼
┌─────────────────┐              ┌─────────────────┐
│ Container       │              │ Container       │
│ Pubblico        │──────────────│ Interno         │
│ 4.232.4.32:5000 │   Database   │ 10.172.5.5:5000 │
│                 │   Condiviso  │                 │
│ - Sync USN      │              │ - Push UYUNI    │
│ - Sync DSA      │              │ - Cache pkgs    │
│ - Sync OVAL     │              │ - P3 Testing    │
│ - Sync NVD      │              └────────┬────────┘
└─────────────────┘                       │
                                          ▼
                              ┌─────────────────┐
                              │ Server UYUNI    │
                              │ 10.172.2.5      │
                              └─────────────────┘
```

## API Endpoints

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/health/detailed` | GET | Health check dettagliato |
| `/api/sync/usn` | POST | Sync Ubuntu USN |
| `/api/sync/dsa/full` | POST | Sync Debian DSA |
| `/api/sync/oval` | POST | Sync OVAL definitions |
| `/api/uyuni/sync-packages` | POST | Update cache pacchetti |
| `/api/uyuni/push` | POST | Push errata a UYUNI |
| `/api/patch-test/start` | POST | Avvia test patch (P3) |
| `/api/stats/overview` | GET | Statistiche generali |

## Fonti Dati

| Fonte | Descrizione |
|-------|-------------|
| Ubuntu USN | Advisory sicurezza Ubuntu |
| Debian DSA | Advisory sicurezza Debian |
| OVAL | Definizioni per CVE audit |
| NVD | CVE enrichment (CVSS scores) |

## Versione

- **API**: v2.6 (con modulo P3 Patch Testing)
- **Ambiente**: PSN (Polo Strategico Nazionale)
- **Ultimo aggiornamento**: 2026-01-26
