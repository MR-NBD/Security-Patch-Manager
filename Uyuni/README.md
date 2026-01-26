# UYUNI - Security Patch Manager

Gestione centralizzata delle patch di sicurezza per Ubuntu/Debian tramite UYUNI Server.

## Panoramica

UYUNI (fork open source di SUSE Manager) non supporta nativamente gli avvisi di sicurezza per distribuzioni non-SUSE. Questo progetto colma questa lacuna sincronizzando automaticamente USN (Ubuntu) e DSA (Debian) verso UYUNI.

## Struttura del Progetto

```
Uyuni/
├── README.md                              # Questo file
├── DOCUMENTAZIONE-COMPLETA.md             # Documentazione architetturale completa
├── UYUNI-Guida-01-Concetti-Fondamentali.md    # Concetti base UYUNI
├── Configurazione-System-Ubuntu-24.04.md  # Setup sistema Ubuntu
├── uyuni-client-management-guide.md       # Guida gestione client
│
├── Initial-Setup/                         # Setup e deployment
│   ├── README.md                          # Guida rapida setup
│   ├── app-v2.5-IMPROVED.py              # API Flask v2.5
│   ├── scripts/                           # Script operativi
│   └── docs/                              # Documentazione deployment
│
└── Note-Teoriche/                         # Background teorico
    └── Supported Clients and Features.md
```

## Quick Start

### 1. Verifica Sistema

```bash
cd Initial-Setup
./scripts/check-containers.sh
```

### 2. Sync Completo (Prima Esecuzione)

```bash
# Da PC/Azure Cloud Shell - sync esterni
./scripts/remote-sync.sh full

# Da server UYUNI - sync interni
ssh root@10.172.2.5
/root/uyuni-server-sync.sh quick
```

### 3. Verifica in UYUNI

- **Patches**: Web UI > Patches > Patch List
- **CVE Audit**: Web UI > Audit > CVE Audit

## Documentazione Principale

| Documento | Contenuto |
|-----------|-----------|
| [Initial-Setup/README.md](UYUNI%20Errata%20Manager%20-%20Setup%20&%20Deployment.md) | Guida rapida setup e script |
| [Initial-Setup/docs/DEPLOYMENT-GUIDE-v2.5.md](Initial-Setup/docs/DEPLOYMENT-GUIDE-v2.5.md) | Guida deployment completa |
| [DOCUMENTAZIONE-COMPLETA.md](DOCUMENTAZIONE-COMPLETA.md) | Architettura e background |
| [UYUNI-Guida-01-Concetti-Fondamentali.md](UYUNI-Guida-01-Concetti-Fondamentali.md) | Concetti base UYUNI |

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
│ - Sync OVAL     │              │                 │
│ - Sync NVD      │              └────────┬────────┘
└─────────────────┘                       │
                                          ▼
                              ┌─────────────────┐
                              │ Server UYUNI    │
                              │ 10.172.2.5      │
                              └─────────────────┘
```

## Fonti Dati

| Fonte | URL | Descrizione |
|-------|-----|-------------|
| Ubuntu USN | ubuntu.com/security/notices | Advisory sicurezza Ubuntu |
| Debian DSA | security-tracker.debian.org | Advisory sicurezza Debian |
| OVAL | security-metadata.canonical.com | Definizioni per CVE audit |
| NVD | nvd.nist.gov | CVE enrichment (CVSS scores) |

## Versione Corrente

- **API**: v2.5
- **Features**:
  - Version matching migliorato
  - Integrazione OVAL per CVE audit
  - Sync ottimizzato (5x pi veloce)
  - Retry automatico con exponential backoff
  - Health check dettagliato

---

**Ambiente**: PSN (Polo Strategico Nazionale)
**Ultimo aggiornamento**: 2026-01-22
