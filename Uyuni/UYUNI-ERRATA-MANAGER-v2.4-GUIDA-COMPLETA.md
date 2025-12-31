# UYUNI Errata Manager v2.4 - Guida Completa

## Indice

1. [Panoramica](#1-panoramica)
2. [Architettura](#2-architettura)
3. [Prerequisiti](#3-prerequisiti)
4. [Fase 1: Setup Database PostgreSQL](#4-fase-1-setup-database-postgresql)
5. [Fase 2: Creazione API Flask](#5-fase-2-creazione-api-flask)
6. [Fase 3: Build e Deploy Container](#6-fase-3-build-e-deploy-container)
7. [Fase 4: Configurazione Automazione](#7-fase-4-configurazione-automazione)
8. [Fase 5: Test e Verifica](#8-fase-5-test-e-verifica)
9. [Operazioni e Manutenzione](#9-operazioni-e-manutenzione)
10. [Troubleshooting](#10-troubleshooting)
11. [Riferimenti API](#11-riferimenti-api)

---

## 1. Panoramica

### 1.1 Obiettivo

UYUNI Errata Manager è un sistema automatizzato per sincronizzare security advisories (errata) da fonti pubbliche e integrarli in UYUNI Server, **associando correttamente i pacchetti** per una gestione centralizzata delle patch di sicurezza.

### 1.2 Problema Risolto

UYUNI (fork open source di SUSE Manager) ha supporto limitato per errata Ubuntu/Debian. Questo sistema:

- **Colma il gap**: Importa errata da fonti ufficiali Ubuntu e Debian
- **Associa i pacchetti**: Collega ogni errata ai pacchetti corretti nei canali UYUNI
- **Arricchisce i dati**: Aggiunge CVSS scores da NVD per prioritizzazione
- **Automatizza**: Sync periodico senza intervento manuale

### 1.3 Fonti Dati Integrate

| Fonte | Tipo | Descrizione |
|-------|------|-------------|
| **USN** (Ubuntu Security Notices) | Errata + Pacchetti | Advisory di sicurezza Ubuntu con lista pacchetti affetti |
| **DSA** (Debian Security Advisories) | Errata + Pacchetti | Advisory di sicurezza Debian con pacchetti |
| **NVD** (National Vulnerability Database) | CVE Enrichment | CVSS scores, severity, CWE |
| **OVAL** (Open Vulnerability Assessment Language) | Definitions | Definizioni per vulnerability scanning |

### 1.4 Versione e Changelog

**Versione attuale: 2.4**

| Versione | Data | Modifiche |
|----------|------|-----------|
| 2.3 | Dic 2024 | Versione iniziale con sync errata |
| 2.4 | Dic 2024 | **FIX CRITICO**: Associazione pacchetti agli errata, cache UYUNI |

---

## 2. Architettura

### 2.1 Diagramma Architetturale

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              INTERNET                                        │
│  ┌─────────────┐  ┌─────────────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ ubuntu.com  │  │ security-tracker    │  │ NVD API     │  │ Canonical   │ │
│  │ (USN+PKG)   │  │ .debian.org (DSA)   │  │ (CVSS)      │  │ (OVAL)      │ │
│  └──────┬──────┘  └──────────┬──────────┘  └──────┬──────┘  └──────┬──────┘ │
└─────────┼────────────────────┼────────────────────┼────────────────┼────────┘
          │                    │                    │                │
          ▼                    ▼                    ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AZURE (Resource Group Pubblico)                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              aci-errata-api (Container Pubblico)                     │   │
│  │              IP: 4.232.4.142:5000                                    │   │
│  │              Funzione: Sync da Internet → Database                   │   │
│  │              - /api/sync/usn (con pacchetti)                         │   │
│  │              - /api/sync/dsa (con pacchetti)                         │   │
│  │              - /api/sync/nvd                                         │   │
│  │              - /api/sync/oval                                        │   │
│  └─────────────────────────────────┬───────────────────────────────────┘   │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AZURE (VNet Privata PSN - 10.172.0.0/16)                  │
│                                                                              │
│  ┌─────────────────────┐     ┌─────────────────────────────────────────┐   │
│  │   PostgreSQL        │     │     aci-errata-api-internal             │   │
│  │   10.172.2.6:5432   │◄───►│     10.172.5.4:5000                     │   │
│  │   (Private Endpt)   │     │     Funzione: Push a UYUNI              │   │
│  │                     │     │     - /api/uyuni/sync-packages          │   │
│  │   Tabelle:          │     │     - /api/uyuni/push (CON PACCHETTI)   │   │
│  │   - errata          │     └──────────────────┬──────────────────────┘   │
│  │   - errata_packages │                        │                          │
│  │   - uyuni_pkg_cache │                        │ XML-RPC                  │
│  │   - cves            │                        ▼                          │
│  │   - cve_details     │     ┌─────────────────────────────────────────┐   │
│  │   - oval_definitions│     │        UYUNI Server                     │   │
│  └─────────────────────┘     │        10.172.2.5                       │   │
│                              │        - Errata con pacchetti associati │   │
│                              │        - Patch visibili sui sistemi     │   │
│                              └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Perché Due Container?

L'infrastruttura PSN (Polo Strategico Nazionale) ha restrizioni di rete severe:

| Problema | Soluzione |
|----------|-----------|
| Container nella VNet non possono accedere a Internet | Container pubblico per sync esterni |
| Container pubblico non può raggiungere UYUNI (rete privata) | Container interno per push a UYUNI |
| NAT Gateway bloccato da policy Azure | Architettura a due container |

### 2.3 Flusso Dati Dettagliato

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           FLUSSO COMPLETO                                   │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  STEP 1: SYNC ERRATA (Container Pubblico - settimanale)                   │
│  ─────────────────────────────────────────────────────                    │
│  ubuntu.com/security/notices.json                                          │
│       │                                                                    │
│       ▼                                                                    │
│  API /sync/usn ──► Tabella: errata (advisory_id, title, severity...)      │
│                ──► Tabella: errata_packages (package_name, version)  ←NEW │
│                ──► Tabella: cves (CVE-XXXX-XXXX)                          │
│                                                                            │
│  STEP 2: CACHE PACCHETTI UYUNI (Container Interno)                        │
│  ─────────────────────────────────────────────────                        │
│  UYUNI channel.software.listAllPackages()                                  │
│       │                                                                    │
│       ▼                                                                    │
│  API /uyuni/sync-packages ──► Tabella: uyuni_package_cache            ←NEW│
│                               (channel_label, package_id, package_name)    │
│                                                                            │
│  STEP 3: PUSH CON MATCH PACCHETTI (Container Interno)                     │
│  ─────────────────────────────────────────────────────                    │
│  Per ogni errata pending:                                                  │
│       │                                                                    │
│       ├─► Leggi pacchetti da errata_packages                              │
│       │                                                                    │
│       ├─► Cerca package_id in uyuni_package_cache                         │
│       │   (match per package_name)                                         │
│       │                                                                    │
│       ▼                                                                    │
│  UYUNI errata.create(errata_info, [], keywords, [package_ids], channels)  │
│                                                    ▲                       │
│                                                    │                       │
│                                          PACCHETTI ASSOCIATI!              │
│                                                                            │
│  RISULTATO: Errata visibili in UYUNI con pacchetti → Patch applicabili    │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 2.4 Schema Database

```
┌─────────────────────┐       ┌─────────────────────┐
│       errata        │       │   errata_packages   │  ← NUOVA v2.4
├─────────────────────┤       ├─────────────────────┤
│ id (PK)             │───┐   │ id (PK)             │
│ advisory_id (UNIQUE)│   │   │ errata_id (FK)      │───┐
│ title               │   └──►│ package_name        │   │
│ description         │       │ fixed_version       │   │
│ severity            │       │ release_name        │   │
│ source (usn/dsa)    │       └─────────────────────┘   │
│ distribution        │                                  │
│ issued_date         │       ┌─────────────────────┐   │
│ sync_status         │       │ uyuni_package_cache │ ← NUOVA v2.4
└─────────────────────┘       ├─────────────────────┤   │
                              │ id (PK)             │   │
┌─────────────────────┐       │ channel_label       │   │
│        cves         │       │ package_id          │◄──┘ (match)
├─────────────────────┤       │ package_name        │
│ id (PK)             │       │ package_version     │
│ cve_id (UNIQUE)     │       └─────────────────────┘
└─────────────────────┘
```

---

## 3. Prerequisiti

### 3.1 Risorse Azure

- **Sottoscrizione Azure** con accesso a:
  - Azure Container Instances (ACI)
  - Azure Container Registry (ACR)
  - Azure Database for PostgreSQL Flexible Server
  - Virtual Network con subnet dedicata per ACI

### 3.2 UYUNI Server

- UYUNI Server installato e funzionante (testato con 2024.x)
- Canali Ubuntu 24.04 configurati e sincronizzati
- Credenziali admin per API XML-RPC
- Accesso di rete al container interno (porta 5000)

### 3.3 Strumenti

- Azure CLI (`az`) configurato
- `curl` e `jq` per testing
- `psql` client per PostgreSQL
- Accesso SSH al server UYUNI

### 3.4 Credenziali Necessarie

| Risorsa | Credenziali | Note |
|---------|-------------|------|
| PostgreSQL | Username, Password | Per DATABASE_URL |
| UYUNI | Admin username, Password | Per XML-RPC API |
| NVD API | API Key (opzionale) | Velocizza sync CVE |
| Azure ACR | Username, Password | Per push immagini |

---

## 4. Fase 1: Setup Database PostgreSQL

### 4.1 Creazione Database (Azure)

```bash
# Variabili
RG="test_group"
PG_SERVER="pg-errata-test"
PG_ADMIN="errataadmin"
PG_PASS="YOUR_SECURE_PASSWORD"  # Cambia!
DB_NAME="uyuni_errata"

# Crea server PostgreSQL Flexible
az postgres flexible-server create \
  --resource-group $RG \
  --name $PG_SERVER \
  --admin-user $PG_ADMIN \
  --admin-password $PG_PASS \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 15 \
  --public-access All

# Crea database
az postgres flexible-server db create \
  --resource-group $RG \
  --server-name $PG_SERVER \
  --database-name $DB_NAME
```

### 4.2 Schema Database Completo (v2.4)

```bash
# Connettiti e crea lo schema
psql "postgresql://$PG_ADMIN:$PG_PASS@$PG_SERVER.postgres.database.azure.com:5432/$DB_NAME?sslmode=require" << 'EOF'

-- Tabella principale errata
CREATE TABLE IF NOT EXISTS errata (
    id SERIAL PRIMARY KEY,
    advisory_id VARCHAR(100) UNIQUE NOT NULL,
    title VARCHAR(500),
    description TEXT,
    severity VARCHAR(50),
    source VARCHAR(50) NOT NULL,
    distribution VARCHAR(100),
    issued_date TIMESTAMP,
    sync_status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_errata_source ON errata(source);
CREATE INDEX IF NOT EXISTS idx_errata_distribution ON errata(distribution);
CREATE INDEX IF NOT EXISTS idx_errata_sync_status ON errata(sync_status);
CREATE INDEX IF NOT EXISTS idx_errata_issued_date ON errata(issued_date DESC);

-- Tabella CVE
CREATE TABLE IF NOT EXISTS cves (
    id SERIAL PRIMARY KEY,
    cve_id VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cves_cve_id ON cves(cve_id);

-- Relazione errata-CVE
CREATE TABLE IF NOT EXISTS errata_cves (
    errata_id INTEGER REFERENCES errata(id) ON DELETE CASCADE,
    cve_id INTEGER REFERENCES cves(id) ON DELETE CASCADE,
    PRIMARY KEY (errata_id, cve_id)
);

-- Dettagli CVE da NVD
CREATE TABLE IF NOT EXISTS cve_details (
    cve_id VARCHAR(50) PRIMARY KEY,
    cvss_v3_score DECIMAL(3,1),
    cvss_v3_vector VARCHAR(200),
    cvss_v3_severity VARCHAR(20),
    cvss_v2_score DECIMAL(3,1),
    cvss_v2_vector VARCHAR(200),
    severity VARCHAR(20),
    description TEXT,
    published_date TIMESTAMP,
    last_modified TIMESTAMP,
    cwe_ids TEXT[],
    nvd_last_sync TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cve_details_severity ON cve_details(severity);
CREATE INDEX IF NOT EXISTS idx_cve_details_cvss ON cve_details(cvss_v3_score DESC);

-- OVAL Definitions
CREATE TABLE IF NOT EXISTS oval_definitions (
    oval_id VARCHAR(200) PRIMARY KEY,
    class VARCHAR(50),
    title VARCHAR(500),
    description TEXT,
    severity VARCHAR(50),
    platform VARCHAR(100),
    platform_version VARCHAR(50),
    cve_refs TEXT[],
    advisory_refs TEXT[],
    criteria_xml TEXT,
    source_url VARCHAR(500),
    last_sync TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_oval_platform ON oval_definitions(platform);
CREATE INDEX IF NOT EXISTS idx_oval_severity ON oval_definitions(severity);

-- Mapping errata-CVE-OVAL
CREATE TABLE IF NOT EXISTS errata_cve_oval_map (
    errata_id INTEGER REFERENCES errata(id) ON DELETE CASCADE,
    cve_id VARCHAR(50),
    oval_id VARCHAR(200),
    PRIMARY KEY (errata_id, cve_id, oval_id)
);

-- Stato CVE per sistema
CREATE TABLE IF NOT EXISTS system_cve_status (
    id SERIAL PRIMARY KEY,
    uyuni_system_id INTEGER NOT NULL,
    system_name VARCHAR(255),
    cve_id VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'unknown',
    vulnerable_package VARCHAR(255),
    fixed_version VARCHAR(100),
    last_scan TIMESTAMP,
    UNIQUE(uyuni_system_id, cve_id)
);

-- Risultati scan SCAP
CREATE TABLE IF NOT EXISTS scap_scan_results (
    id SERIAL PRIMARY KEY,
    uyuni_system_id INTEGER NOT NULL,
    system_name VARCHAR(255),
    scan_id VARCHAR(100),
    scan_date TIMESTAMP,
    oval_file VARCHAR(255),
    definitions_evaluated INTEGER,
    definitions_passed INTEGER,
    definitions_failed INTEGER,
    findings JSONB
);

-- Log sincronizzazioni
CREATE TABLE IF NOT EXISTS sync_logs (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    items_processed INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_logs_type ON sync_logs(sync_type, started_at DESC);

-- ============================================================
-- NUOVE TABELLE v2.4 - Associazione Pacchetti
-- ============================================================

-- Pacchetti affetti per ogni errata
CREATE TABLE IF NOT EXISTS errata_packages (
    id SERIAL PRIMARY KEY,
    errata_id INTEGER REFERENCES errata(id) ON DELETE CASCADE,
    package_name VARCHAR(255) NOT NULL,
    fixed_version VARCHAR(100),
    architecture VARCHAR(50),
    release_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(errata_id, package_name, release_name)
);

CREATE INDEX IF NOT EXISTS idx_errata_packages_name ON errata_packages(package_name);
CREATE INDEX IF NOT EXISTS idx_errata_packages_errata ON errata_packages(errata_id);

-- Cache pacchetti UYUNI
CREATE TABLE IF NOT EXISTS uyuni_package_cache (
    id SERIAL PRIMARY KEY,
    channel_label VARCHAR(255) NOT NULL,
    package_id INTEGER NOT NULL,
    package_name VARCHAR(255) NOT NULL,
    package_version VARCHAR(100),
    package_release VARCHAR(100),
    package_arch VARCHAR(50),
    last_sync TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(channel_label, package_id)
);

CREATE INDEX IF NOT EXISTS idx_uyuni_pkg_cache_name ON uyuni_package_cache(package_name);
CREATE INDEX IF NOT EXISTS idx_uyuni_pkg_cache_channel ON uyuni_package_cache(channel_label);

EOF
```

### 4.3 Configurazione Private Endpoint (per VNet)

Se il container interno è in una VNet privata, configura un Private Endpoint per PostgreSQL:

```bash
# Crea Private Endpoint
az network private-endpoint create \
  --name pe-pg-errata \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --vnet-name ASL0603-spoke10-spoke-italynorth \
  --subnet errata-aci-subnet \
  --private-connection-resource-id $(az postgres flexible-server show -g test_group -n pg-errata-test --query id -o tsv) \
  --group-id postgresqlServer \
  --connection-name pg-errata-connection
```

Annota l'**IP privato** del Private Endpoint (es. `10.172.2.6`) per il DATABASE_URL del container interno.

---

## 5. Fase 2: Creazione API Flask

### 5.1 Struttura File

```
uyuni-errata-manager/
├── app.py           # API Flask principale (v2.4)
├── Dockerfile.api   # Dockerfile per container
```

### 5.2 Codice API Completo (app.py v2.4)

Crea il file `app.py`:

```bash
mkdir -p ~/uyuni-errata-manager
cd ~/uyuni-errata-manager

cat > app.py << 'ENDOFPYTHON'
#!/usr/bin/env python3
"""
UYUNI Errata Manager - Enhanced API v2.4
Integra: USN, DSA, NVD, OVAL con ASSOCIAZIONE PACCHETTI
"""

import os
import ssl
import json
import bz2
import time
import xmlrpc.client
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import requests

app = Flask(__name__)
CORS(app)

# ============================================================
# CONFIGURAZIONE
# ============================================================
REQUEST_HEADERS = {
    'User-Agent': 'UYUNI-Errata-Manager/2.4',
    'Accept': 'application/json'
}

DATABASE_URL = os.environ.get('DATABASE_URL')
UYUNI_URL = os.environ.get('UYUNI_URL', '')
UYUNI_USER = os.environ.get('UYUNI_USER', '')
UYUNI_PASSWORD = os.environ.get('UYUNI_PASSWORD', '')

NVD_API_KEY = os.environ.get('NVD_API_KEY', '')
NVD_API_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"

OVAL_SOURCES = {
    'ubuntu': {
        'noble': 'https://security-metadata.canonical.com/oval/com.ubuntu.noble.usn.oval.xml.bz2',
        'jammy': 'https://security-metadata.canonical.com/oval/com.ubuntu.jammy.usn.oval.xml.bz2',
        'focal': 'https://security-metadata.canonical.com/oval/com.ubuntu.focal.usn.oval.xml.bz2',
    },
    'debian': {
        'bookworm': 'https://www.debian.org/security/oval/oval-definitions-bookworm.xml.bz2',
        'bullseye': 'https://www.debian.org/security/oval/oval-definitions-bullseye.xml.bz2',
    }
}

# ============================================================
# UTILITY FUNCTIONS
# ============================================================
def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def get_uyuni_client():
    if not UYUNI_URL:
        return None, None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    client = xmlrpc.client.ServerProxy(f"{UYUNI_URL}/rpc/api", context=context)
    session_key = client.auth.login(UYUNI_USER, UYUNI_PASSWORD)
    return client, session_key

def calculate_severity(cvss_score):
    if cvss_score is None:
        return 'UNKNOWN'
    if cvss_score >= 9.0:
        return 'CRITICAL'
    if cvss_score >= 7.0:
        return 'HIGH'
    if cvss_score >= 4.0:
        return 'MEDIUM'
    return 'LOW'

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

# ============================================================
# HEALTH & STATS ENDPOINTS
# ============================================================
@app.route('/api/health', methods=['GET'])
def health():
    status = {'api': 'ok', 'database': 'unknown', 'uyuni': 'unknown', 'version': '2.4'}
    
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        conn.close()
        status['database'] = 'ok'
    except Exception as e:
        status['database'] = f'error: {str(e)}'
    
    try:
        client, session = get_uyuni_client()
        if client:
            client.auth.logout(session)
            status['uyuni'] = 'ok'
        else:
            status['uyuni'] = 'not configured'
    except Exception as e:
        status['uyuni'] = f'error: {str(e)}'
    
    return jsonify(status)

@app.route('/api/stats/overview', methods=['GET'])
def stats_overview():
    conn = get_db()
    cur = conn.cursor()
    
    stats = {}
    
    cur.execute("""
        SELECT COUNT(*) as total,
            COUNT(CASE WHEN sync_status = 'synced' THEN 1 END) as synced,
            COUNT(CASE WHEN sync_status = 'pending' THEN 1 END) as pending
        FROM errata
    """)
    stats['errata'] = dict(cur.fetchone())
    
    cur.execute("SELECT source, COUNT(*) as count FROM errata GROUP BY source")
    stats['errata_by_source'] = {r['source']: r['count'] for r in cur.fetchall()}
    
    cur.execute("SELECT severity, COUNT(*) as count FROM errata WHERE severity IS NOT NULL GROUP BY severity")
    stats['errata_by_severity'] = {r['severity']: r['count'] for r in cur.fetchall()}
    
    cur.execute("SELECT COUNT(*) as total FROM cves")
    stats['cves'] = dict(cur.fetchone())
    
    cur.execute("""
        SELECT COUNT(*) as total,
            COUNT(CASE WHEN cvss_v3_score IS NOT NULL THEN 1 END) as with_cvss_v3,
            COUNT(CASE WHEN severity = 'CRITICAL' THEN 1 END) as critical,
            COUNT(CASE WHEN severity = 'HIGH' THEN 1 END) as high,
            ROUND(AVG(cvss_v3_score)::numeric, 2) as avg_cvss
        FROM cve_details
    """)
    stats['nvd'] = dict(cur.fetchone())
    
    cur.execute("SELECT platform, COUNT(*) as count FROM oval_definitions GROUP BY platform")
    stats['oval'] = {r['platform']: r['count'] for r in cur.fetchall()}
    
    cur.execute("SELECT sync_type, MAX(started_at) as last_sync FROM sync_logs WHERE status = 'completed' GROUP BY sync_type")
    stats['last_syncs'] = {r['sync_type']: r['last_sync'].isoformat() if r['last_sync'] else None for r in cur.fetchall()}
    
    cur.close()
    conn.close()
    return jsonify(stats)

@app.route('/api/stats/packages', methods=['GET'])
def stats_packages():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) as total FROM errata_packages")
    total_pkg = cur.fetchone()['total']
    
    cur.execute("SELECT COUNT(DISTINCT package_name) as unique_names FROM errata_packages")
    unique_pkg = cur.fetchone()['unique_names']
    
    cur.execute("""
        SELECT e.source, COUNT(DISTINCT ep.id) as pkg_count
        FROM errata e
        JOIN errata_packages ep ON e.id = ep.errata_id
        GROUP BY e.source
    """)
    by_source = {r['source']: r['pkg_count'] for r in cur.fetchall()}
    
    cur.execute("SELECT COUNT(*) as total FROM uyuni_package_cache")
    cache_total = cur.fetchone()['total']
    
    cur.execute("SELECT channel_label, COUNT(*) as count FROM uyuni_package_cache GROUP BY channel_label")
    cache_by_channel = {r['channel_label']: r['count'] for r in cur.fetchall()}
    
    cur.close()
    conn.close()
    
    return jsonify({
        'errata_packages': {
            'total': total_pkg,
            'unique_names': unique_pkg,
            'by_source': by_source
        },
        'uyuni_cache': {
            'total': cache_total,
            'by_channel': cache_by_channel
        }
    })

# ============================================================
# ERRATA ENDPOINTS
# ============================================================
@app.route('/api/errata', methods=['GET'])
def list_errata():
    limit = request.args.get('limit', 100, type=int)
    source = request.args.get('source', None)
    distribution = request.args.get('distribution', None)
    severity = request.args.get('severity', None)
    sync_status = request.args.get('sync_status', None)
    
    conn = get_db()
    cur = conn.cursor()
    
    query = "SELECT id, advisory_id, title, severity, source, distribution, issued_date, sync_status FROM errata WHERE 1=1"
    params = []
    
    if source:
        query += " AND source = %s"
        params.append(source)
    if distribution:
        query += " AND distribution = %s"
        params.append(distribution)
    if severity:
        query += " AND severity = %s"
        params.append(severity)
    if sync_status:
        query += " AND sync_status = %s"
        params.append(sync_status)
    
    query += " ORDER BY issued_date DESC LIMIT %s"
    params.append(limit)
    
    cur.execute(query, params)
    errata = [dict(r) for r in cur.fetchall()]
    
    cur.close()
    conn.close()
    return jsonify({'count': len(errata), 'errata': errata})

@app.route('/api/errata/<advisory_id>/packages', methods=['GET'])
def errata_packages_detail(advisory_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT e.advisory_id, e.title, e.distribution, ep.package_name, ep.fixed_version, ep.release_name
        FROM errata e
        LEFT JOIN errata_packages ep ON e.id = ep.errata_id
        WHERE e.advisory_id = %s
    """, (advisory_id,))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        return jsonify({'error': 'Errata not found'}), 404
    
    return jsonify({
        'advisory_id': rows[0]['advisory_id'],
        'title': rows[0]['title'],
        'distribution': rows[0]['distribution'],
        'packages': [
            {'name': r['package_name'], 'version': r['fixed_version'], 'release': r['release_name']}
            for r in rows if r['package_name']
        ]
    })

# ============================================================
# SYNC USN (con pacchetti)
# ============================================================
@app.route('/api/sync/usn', methods=['POST'])
def sync_usn():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("INSERT INTO sync_logs (sync_type, status, started_at) VALUES ('usn', 'running', NOW()) RETURNING id")
    log_id = cur.fetchone()['id']
    conn.commit()
    
    cur.execute("SELECT advisory_id FROM errata WHERE source = 'usn' ORDER BY issued_date DESC LIMIT 1")
    last_row = cur.fetchone()
    last_usn = last_row['advisory_id'] if last_row else None
    
    new_errata = []
    offset = 0
    found_existing = False
    
    while not found_existing:
        url = f"https://ubuntu.com/security/notices.json?limit=20&offset={offset}"
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except:
            break
        
        notices = data.get('notices', [])
        if not notices:
            break
        
        for notice in notices:
            notice_id = notice.get('id', '')
            if notice_id == last_usn:
                found_existing = True
                break
            
            priority = notice.get('priority', 'medium')
            severity_map = {'critical': 'critical', 'high': 'high', 'medium': 'medium', 'low': 'low', 'negligible': 'low'}
            severity = severity_map.get(priority.lower(), 'medium')
            
            cves = notice.get('cves', [])
            cve_ids = [c if isinstance(c, str) else c.get('id', '') for c in cves] if isinstance(cves, list) else []
            
            # Estrai pacchetti affetti
            packages = []
            release_packages = notice.get('release_packages', {})
            for release_name, pkg_list in release_packages.items():
                release_lower = release_name.lower()
                if any(r in release_lower for r in ['noble', 'jammy', 'focal', 'mantic', 'lunar', 'kinetic']):
                    if isinstance(pkg_list, list):
                        for pkg_info in pkg_list:
                            if isinstance(pkg_info, dict):
                                packages.append({
                                    'name': pkg_info.get('name', ''),
                                    'version': pkg_info.get('version', ''),
                                    'release': release_lower
                                })
            
            new_errata.append({
                'advisory_id': notice_id,
                'title': notice.get('title', '')[:500],
                'description': notice.get('description', '')[:4000],
                'severity': severity,
                'source': 'usn',
                'distribution': 'ubuntu',
                'issued_date': notice.get('published'),
                'cves': cve_ids,
                'packages': packages
            })
        
        offset += 20
        if offset > 500:
            break
    
    processed = 0
    packages_saved = 0
    
    for errata in new_errata:
        try:
            cur.execute("""
                INSERT INTO errata (advisory_id, title, description, severity, source, distribution, issued_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (advisory_id) DO NOTHING RETURNING id
            """, (errata['advisory_id'], errata['title'], errata['description'], errata['severity'], errata['source'], errata['distribution'], errata['issued_date']))
            row = cur.fetchone()
            
            if row:
                errata_id = row['id']
                processed += 1
                
                for cve_id in errata['cves']:
                    if cve_id and cve_id.startswith('CVE-'):
                        cur.execute("INSERT INTO cves (cve_id) VALUES (%s) ON CONFLICT (cve_id) DO UPDATE SET cve_id = EXCLUDED.cve_id RETURNING id", (cve_id,))
                        cve_row = cur.fetchone()
                        cur.execute("INSERT INTO errata_cves (errata_id, cve_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (errata_id, cve_row['id']))
                
                for pkg in errata['packages']:
                    if pkg['name']:
                        cur.execute("""
                            INSERT INTO errata_packages (errata_id, package_name, fixed_version, release_name)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (errata_id, package_name, release_name) DO NOTHING
                        """, (errata_id, pkg['name'], pkg['version'], pkg['release']))
                        packages_saved += 1
                
                conn.commit()
        except Exception as e:
            conn.rollback()
            continue
    
    cur.execute("UPDATE sync_logs SET status = 'completed', completed_at = NOW(), items_processed = %s WHERE id = %s", (processed, log_id))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({
        'status': 'success', 
        'source': 'usn', 
        'processed': processed, 
        'packages_saved': packages_saved,
        'last_known': last_usn
    })

# ============================================================
# SYNC DSA (con pacchetti)
# ============================================================
@app.route('/api/sync/dsa', methods=['POST'])
def sync_dsa():
    offset = request.args.get('offset', 0, type=int)
    batch_size = 500
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("INSERT INTO sync_logs (sync_type, status, started_at) VALUES ('dsa', 'running', NOW()) RETURNING id")
    log_id = cur.fetchone()['id']
    conn.commit()
    
    url = "https://security-tracker.debian.org/tracker/data/json"
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        cur.execute("UPDATE sync_logs SET status = 'error', error_message = %s WHERE id = %s", (str(e), log_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'error': str(e)}), 500
    
    target_releases = ['bookworm', 'bullseye', 'trixie']
    packages = list(data.items())[offset:offset + batch_size]
    processed = 0
    packages_saved = 0
    
    for package_name, package_data in packages:
        if not isinstance(package_data, dict):
            continue
        
        for cve_id, cve_data in package_data.items():
            if not cve_id.startswith('CVE-') or not isinstance(cve_data, dict):
                continue
            
            releases = cve_data.get('releases', {})
            description = cve_data.get('description', '')
            urgency = cve_data.get('urgency', 'medium')
            urgency_map = {'critical': 'critical', 'emergency': 'critical', 'high': 'high', 'medium': 'medium', 'low': 'low', 'unimportant': 'low', 'not yet assigned': 'medium'}
            severity = urgency_map.get(urgency.lower() if urgency else 'medium', 'medium')
            
            for release_name in target_releases:
                if release_name not in releases:
                    continue
                release_data = releases[release_name]
                if not isinstance(release_data, dict) or release_data.get('status') != 'resolved' or not release_data.get('fixed_version'):
                    continue
                
                fixed_version = release_data.get('fixed_version')
                advisory_id = f"DEB-{cve_id}-{release_name}"
                
                try:
                    cur.execute("""
                        INSERT INTO errata (advisory_id, title, description, severity, source, distribution, issued_date)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (advisory_id) DO NOTHING RETURNING id
                    """, (advisory_id, f"{package_name}: {cve_id}", (description or '')[:4000], severity, 'dsa', f"debian-{release_name}"))
                    row = cur.fetchone()
                    
                    if row:
                        errata_id = row['id']
                        processed += 1
                        
                        cur.execute("INSERT INTO cves (cve_id) VALUES (%s) ON CONFLICT (cve_id) DO UPDATE SET cve_id = EXCLUDED.cve_id RETURNING id", (cve_id,))
                        cve_row = cur.fetchone()
                        cur.execute("INSERT INTO errata_cves (errata_id, cve_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (errata_id, cve_row['id']))
                        
                        cur.execute("""
                            INSERT INTO errata_packages (errata_id, package_name, fixed_version, release_name)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (errata_id, package_name, release_name) DO NOTHING
                        """, (errata_id, package_name, fixed_version, release_name))
                        packages_saved += 1
                        
                        conn.commit()
                except:
                    conn.rollback()
                    continue
    
    cur.execute("UPDATE sync_logs SET status = 'completed', completed_at = NOW(), items_processed = %s WHERE id = %s", (processed, log_id))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({
        'status': 'success', 
        'source': 'dsa', 
        'offset': offset, 
        'batch_size': batch_size, 
        'processed': processed,
        'packages_saved': packages_saved,
        'total_packages': len(data), 
        'next_offset': offset + batch_size if offset + batch_size < len(data) else None
    })

# ============================================================
# SYNC NVD
# ============================================================
@app.route('/api/sync/nvd', methods=['POST'])
def sync_nvd():
    batch_size = request.args.get('batch_size', 50, type=int)
    force = request.args.get('force', 'false').lower() == 'true'
    
    conn = get_db()
    cur = conn.cursor()
    
    if force:
        cur.execute("SELECT DISTINCT c.cve_id FROM cves c ORDER BY c.cve_id DESC LIMIT %s", (batch_size,))
    else:
        cur.execute("SELECT DISTINCT c.cve_id FROM cves c LEFT JOIN cve_details cd ON c.cve_id = cd.cve_id WHERE cd.cve_id IS NULL ORDER BY c.cve_id DESC LIMIT %s", (batch_size,))
    
    pending_cves = [r['cve_id'] for r in cur.fetchall()]
    
    if not pending_cves:
        cur.close()
        conn.close()
        return jsonify({'status': 'complete', 'message': 'No CVEs to process', 'processed': 0})
    
    cur.execute("INSERT INTO sync_logs (sync_type, status, started_at) VALUES ('nvd', 'running', NOW()) RETURNING id")
    log_id = cur.fetchone()['id']
    conn.commit()
    
    processed = 0
    errors = []
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    if NVD_API_KEY:
        session.headers['apiKey'] = NVD_API_KEY
    
    for cve_id in pending_cves:
        try:
            url = f"{NVD_API_BASE}?cveId={cve_id}"
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get('vulnerabilities'):
                vuln = data['vulnerabilities'][0]['cve']
                metrics = vuln.get('metrics', {})
                
                cvss_v3_score, cvss_v3_vector, cvss_v3_severity = None, None, None
                if 'cvssMetricV31' in metrics:
                    cvss_data = metrics['cvssMetricV31'][0]['cvssData']
                    cvss_v3_score, cvss_v3_vector = cvss_data['baseScore'], cvss_data['vectorString']
                    cvss_v3_severity = cvss_data.get('baseSeverity', '').upper()
                elif 'cvssMetricV30' in metrics:
                    cvss_data = metrics['cvssMetricV30'][0]['cvssData']
                    cvss_v3_score, cvss_v3_vector = cvss_data['baseScore'], cvss_data['vectorString']
                    cvss_v3_severity = cvss_data.get('baseSeverity', '').upper()
                
                cvss_v2_score, cvss_v2_vector = None, None
                if 'cvssMetricV2' in metrics:
                    cvss_data = metrics['cvssMetricV2'][0]['cvssData']
                    cvss_v2_score, cvss_v2_vector = cvss_data['baseScore'], cvss_data.get('vectorString')
                
                severity = cvss_v3_severity or calculate_severity(cvss_v3_score or cvss_v2_score)
                cwes = [desc['value'] for weakness in vuln.get('weaknesses', []) for desc in weakness.get('description', []) if desc.get('value', '').startswith('CWE-')]
                descriptions = vuln.get('descriptions', [])
                description = next((d['value'] for d in descriptions if d.get('lang') == 'en'), descriptions[0]['value'] if descriptions else '')
                
                cur.execute("""
                    INSERT INTO cve_details (cve_id, cvss_v3_score, cvss_v3_vector, cvss_v3_severity, cvss_v2_score, cvss_v2_vector, severity, description, published_date, last_modified, cwe_ids, nvd_last_sync)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (cve_id) DO UPDATE SET cvss_v3_score = EXCLUDED.cvss_v3_score, cvss_v3_vector = EXCLUDED.cvss_v3_vector, cvss_v3_severity = EXCLUDED.cvss_v3_severity, cvss_v2_score = EXCLUDED.cvss_v2_score, severity = EXCLUDED.severity, cwe_ids = EXCLUDED.cwe_ids, nvd_last_sync = NOW()
                """, (cve_id, cvss_v3_score, cvss_v3_vector, cvss_v3_severity, cvss_v2_score, cvss_v2_vector, severity, description[:4000] if description else None, vuln.get('published'), vuln.get('lastModified'), cwes if cwes else None))
                conn.commit()
                processed += 1
            
            time.sleep(0.6 if NVD_API_KEY else 6)
        except Exception as e:
            errors.append(f"{cve_id}: {str(e)[:100]}")
    
    cur.execute("UPDATE sync_logs SET status = 'completed', completed_at = NOW(), items_processed = %s, error_message = %s WHERE id = %s", (processed, '; '.join(errors[:5]) if errors else None, log_id))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success', 'processed': processed, 'pending_total': len(pending_cves), 'errors_count': len(errors)})

# ============================================================
# SYNC OVAL
# ============================================================
@app.route('/api/sync/oval', methods=['POST'])
def sync_oval():
    platform = request.args.get('platform', 'all')
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("INSERT INTO sync_logs (sync_type, status, started_at) VALUES ('oval', 'running', NOW()) RETURNING id")
    log_id = cur.fetchone()['id']
    conn.commit()
    
    results = {}
    total_processed = 0
    
    platforms_to_sync = OVAL_SOURCES if platform == 'all' else ({platform: OVAL_SOURCES[platform]} if platform in OVAL_SOURCES else {})
    ns = {'oval-def': 'http://oval.mitre.org/XMLSchema/oval-definitions-5'}
    
    for plat, codenames_dict in platforms_to_sync.items():
        for cn, url in codenames_dict.items():
            try:
                resp = requests.get(url, timeout=120)
                resp.raise_for_status()
                xml_content = bz2.decompress(resp.content).decode('utf-8')
                root = ET.fromstring(xml_content)
                definitions = []
                
                for definition in root.findall('.//oval-def:definition', ns):
                    oval_id = definition.get('id')
                    metadata = definition.find('oval-def:metadata', ns)
                    if metadata is None:
                        continue
                    
                    title = metadata.findtext('oval-def:title', '', ns)
                    description = metadata.findtext('oval-def:description', '', ns)
                    severity = 'UNKNOWN'
                    advisory = metadata.find('oval-def:advisory', ns)
                    if advisory is not None:
                        sev_elem = advisory.find('oval-def:severity', ns)
                        if sev_elem is not None and sev_elem.text:
                            severity = sev_elem.text.upper()
                    
                    cve_refs = [ref.get('ref_id') for ref in metadata.findall('.//oval-def:reference[@source="CVE"]', ns) if ref.get('ref_id')]
                    
                    definitions.append({'oval_id': oval_id, 'title': title[:500], 'description': description[:2000], 'severity': severity, 'platform': f"{plat}-{cn}", 'platform_version': cn, 'cve_refs': cve_refs, 'source_url': url})
                
                for defn in definitions:
                    cur.execute("""
                        INSERT INTO oval_definitions (oval_id, title, description, severity, platform, platform_version, cve_refs, source_url, last_sync)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (oval_id) DO UPDATE SET title = EXCLUDED.title, severity = EXCLUDED.severity, cve_refs = EXCLUDED.cve_refs, last_sync = NOW()
                    """, (defn['oval_id'], defn['title'], defn['description'], defn['severity'], defn['platform'], defn['platform_version'], defn['cve_refs'], defn['source_url']))
                
                conn.commit()
                results[f"{plat}-{cn}"] = len(definitions)
                total_processed += len(definitions)
            except Exception as e:
                results[f"{plat}-{cn}"] = f"error: {str(e)[:100]}"
    
    cur.execute("UPDATE sync_logs SET status = 'completed', completed_at = NOW(), items_processed = %s WHERE id = %s", (total_processed, log_id))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success', 'total_processed': total_processed, 'results': results})

# ============================================================
# UYUNI ENDPOINTS
# ============================================================
@app.route('/api/uyuni/status', methods=['GET'])
def uyuni_status():
    try:
        client, session = get_uyuni_client()
        if not client:
            return jsonify({'status': 'not configured', 'url': UYUNI_URL})
        version = client.api.getVersion()
        channels = client.channel.listAllChannels(session)
        systems = client.system.listSystems(session)
        client.auth.logout(session)
        return jsonify({'status': 'connected', 'url': UYUNI_URL, 'api_version': version, 'channels_count': len(channels), 'systems_count': len(systems)})
    except Exception as e:
        return jsonify({'status': 'error', 'url': UYUNI_URL, 'error': str(e)})

@app.route('/api/uyuni/channels', methods=['GET'])
def uyuni_channels():
    try:
        client, session = get_uyuni_client()
        if not client:
            return jsonify({'error': 'UYUNI not configured'}), 500
        channels = client.channel.listAllChannels(session)
        result = [{'id': ch['id'], 'label': ch['label'], 'name': ch['name'], 'mapped_distribution': map_channel_to_distribution(ch['label'])} for ch in channels]
        client.auth.logout(session)
        return jsonify({'count': len(result), 'channels': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/uyuni/sync-packages', methods=['POST'])
def uyuni_sync_packages():
    """Sincronizza la cache dei pacchetti dai canali UYUNI"""
    channel_label = request.args.get('channel', None)
    
    client, session = get_uyuni_client()
    if not client:
        return jsonify({'error': 'UYUNI not configured'}), 500
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        if channel_label:
            channels = [{'label': channel_label}]
        else:
            channels = client.channel.listAllChannels(session)
            channels = [ch for ch in channels if map_channel_to_distribution(ch['label'])]
        
        total_synced = 0
        results = {}
        
        for ch in channels:
            label = ch['label']
            try:
                packages = client.channel.software.listAllPackages(session, label)
                cur.execute("DELETE FROM uyuni_package_cache WHERE channel_label = %s", (label,))
                
                for pkg in packages:
                    cur.execute("""
                        INSERT INTO uyuni_package_cache 
                        (channel_label, package_id, package_name, package_version, package_release, package_arch)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (channel_label, package_id) DO UPDATE SET
                        package_name = EXCLUDED.package_name, last_sync = NOW()
                    """, (label, pkg['id'], pkg['name'], pkg.get('version', ''), pkg.get('release', ''), pkg.get('arch_label', '')))
                
                conn.commit()
                results[label] = len(packages)
                total_synced += len(packages)
            except Exception as e:
                results[label] = f"error: {str(e)}"
                conn.rollback()
        
        client.auth.logout(session)
        cur.close()
        conn.close()
        
        return jsonify({'status': 'success', 'total_packages_synced': total_synced, 'channels': results})
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/uyuni/push', methods=['POST'])
def uyuni_push():
    """Push errata a UYUNI CON associazione pacchetti"""
    limit = request.args.get('limit', 10, type=int)
    
    client, session = get_uyuni_client()
    if not client:
        return jsonify({'error': 'UYUNI not configured'}), 500
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        channels = client.channel.listAllChannels(session)
        channel_map = {}
        for ch in channels:
            dist = map_channel_to_distribution(ch['label'])
            if dist:
                if dist not in channel_map:
                    channel_map[dist] = []
                channel_map[dist].append(ch['label'])
        
        active_distributions = list(channel_map.keys())
        if not active_distributions:
            return jsonify({'status': 'no_channels', 'message': 'No Ubuntu/Debian channels found'})
        
        cur.execute("""
            SELECT * FROM errata 
            WHERE sync_status = 'pending' AND distribution = ANY(%s) 
            ORDER BY issued_date DESC LIMIT %s
        """, (active_distributions, limit))
        pending = cur.fetchall()
        
        pushed = 0
        skipped_no_packages = 0
        errors = []
        
        for errata in pending:
            try:
                dist = errata['distribution']
                if dist not in channel_map:
                    continue
                target_channels = channel_map[dist]
                
                cur.execute("SELECT DISTINCT package_name FROM errata_packages WHERE errata_id = %s", (errata['id'],))
                errata_pkg_names = [r['package_name'] for r in cur.fetchall()]
                
                package_ids = []
                if errata_pkg_names:
                    for channel_label in target_channels:
                        cur.execute("""
                            SELECT DISTINCT package_id FROM uyuni_package_cache 
                            WHERE channel_label = %s AND package_name = ANY(%s)
                        """, (channel_label, errata_pkg_names))
                        package_ids.extend([r['package_id'] for r in cur.fetchall()])
                
                package_ids = list(set(package_ids))
                
                if not package_ids and errata_pkg_names:
                    skipped_no_packages += 1
                    cur.execute("UPDATE errata SET sync_status = 'synced' WHERE id = %s", (errata['id'],))
                    conn.commit()
                    continue
                
                errata_info = {
                    'synopsis': (errata['title'] or errata['advisory_id'])[:200],
                    'advisory_name': errata['advisory_id'],
                    'advisory_type': 'Security Advisory',
                    'advisory_release': 1,
                    'product': dist.replace('-', ' ').title(),
                    'topic': (errata['title'] or '')[:500],
                    'description': (errata['description'] or '')[:2000],
                    'solution': 'Apply the updated packages.',
                    'references': '',
                    'notes': f'Imported by UYUNI Errata Manager v2.4 from {errata["source"].upper()}'
                }
                
                severity = errata.get('severity', 'medium')
                severity_keywords = {
                    'critical': ['critical', 'security'],
                    'high': ['important', 'security'],
                    'medium': ['moderate', 'security'],
                    'low': ['low', 'security']
                }
                keywords = severity_keywords.get(severity, ['moderate', 'security'])
                
                client.errata.create(session, errata_info, [], keywords, package_ids, target_channels)
                
                cur.execute("UPDATE errata SET sync_status = 'synced' WHERE id = %s", (errata['id'],))
                conn.commit()
                pushed += 1
                
            except Exception as e:
                error_msg = str(e)
                if 'already exists' in error_msg.lower():
                    cur.execute("UPDATE errata SET sync_status = 'synced' WHERE id = %s", (errata['id'],))
                    conn.commit()
                    pushed += 1
                else:
                    errors.append(f"{errata['advisory_id']}: {error_msg[:100]}")
        
        client.auth.logout(session)
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'error': str(e)}), 500
    
    cur.close()
    conn.close()
    
    return jsonify({
        'status': 'success',
        'pushed': pushed,
        'skipped_no_packages': skipped_no_packages,
        'pending_processed': len(pending),
        'errors': errors[:5] if errors else None
    })

@app.route('/api/sync/status', methods=['GET'])
def sync_status():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sync_logs ORDER BY started_at DESC LIMIT 20")
    logs = [{'id': r['id'], 'sync_type': r['sync_type'], 'status': r['status'], 'started_at': r['started_at'].isoformat() if r['started_at'] else None, 'completed_at': r['completed_at'].isoformat() if r['completed_at'] else None, 'items_processed': r['items_processed'], 'error_message': r['error_message']} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({'logs': logs})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
ENDOFPYTHON
```

### 5.3 Dockerfile

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
    requests==2.31.0

COPY app.py /app/

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "900", "app:app"]
EOF
```

---

## 6. Fase 3: Build e Deploy Container

### 6.1 Creazione Azure Container Registry

```bash
RG="test_group"
ACR_NAME="acaborerrata"  # Deve essere univoco globalmente

az acr create \
  --resource-group $RG \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true
```

### 6.2 Build Immagine

```bash
cd ~/uyuni-errata-manager

az acr build \
  --registry $ACR_NAME \
  --image errata-api:v2.4 \
  --file Dockerfile.api .
```

### 6.3 Deploy Container Pubblico

```bash
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

az container create \
  --resource-group $RG \
  --name aci-errata-api \
  --image $ACR_NAME.azurecr.io/errata-api:v2.4 \
  --registry-login-server $ACR_NAME.azurecr.io \
  --registry-username $ACR_NAME \
  --registry-password "$ACR_PASSWORD" \
  --os-type Linux \
  --cpu 1 \
  --memory 1.5 \
  --ports 5000 \
  --ip-address Public \
  --environment-variables \
    DATABASE_URL="postgresql://USER:PASS@HOST:5432/DB?sslmode=require" \
  --restart-policy Always
```

### 6.4 Deploy Container Interno (VNet)

```bash
SUBNET_ID="/subscriptions/XXX/resourceGroups/XXX/providers/Microsoft.Network/virtualNetworks/XXX/subnets/XXX"

az container create \
  --resource-group YOUR_VNET_RG \
  --name aci-errata-api-internal \
  --image $ACR_NAME.azurecr.io/errata-api:v2.4 \
  --registry-login-server $ACR_NAME.azurecr.io \
  --registry-username $ACR_NAME \
  --registry-password "$ACR_PASSWORD" \
  --os-type Linux \
  --cpu 1 \
  --memory 1.5 \
  --ports 5000 \
  --subnet "$SUBNET_ID" \
  --environment-variables \
    FLASK_ENV="production" \
    DATABASE_URL="postgresql://USER:PASS@PRIVATE_IP:5432/DB?sslmode=require" \
    UYUNI_URL="https://UYUNI_IP" \
    UYUNI_USER="admin" \
    UYUNI_PASSWORD="YOUR_PASSWORD" \
    NVD_API_KEY="" \
  --restart-policy Always
```

**IMPORTANTE**: Per il container interno, usa l'**IP privato** del Private Endpoint PostgreSQL nel DATABASE_URL.

---

## 7. Fase 4: Configurazione Automazione

### 7.1 Script Automazione (sul server UYUNI)

```bash
cat > /root/errata-sync.sh << 'EOF'
#!/bin/bash
# UYUNI Errata Manager - Script Automazione v2.4

LOG_FILE="/var/log/errata-sync.log"
PUBLIC_API="http://PUBLIC_CONTAINER_IP:5000"
INTERNAL_API="http://INTERNAL_CONTAINER_IP:5000"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a $LOG_FILE
}

log "========== STARTING ERRATA SYNC =========="

# 1. Sync USN
log "Syncing USN from Ubuntu..."
curl -s -m 300 -X POST "$PUBLIC_API/api/sync/usn" >> $LOG_FILE 2>&1

# 2. Aggiorna cache pacchetti UYUNI
log "Updating UYUNI package cache..."
curl -s -m 600 -X POST "$INTERNAL_API/api/uyuni/sync-packages" >> $LOG_FILE 2>&1

# 3. Push errata a UYUNI
log "Pushing errata to UYUNI..."
total_pushed=0
for i in $(seq 1 100); do
    result=$(curl -s -m 120 -X POST "$INTERNAL_API/api/uyuni/push?limit=10")
    pushed=$(echo $result | grep -o '"pushed":[0-9]*' | cut -d: -f2)
    
    [ -z "$pushed" ] && pushed=0
    total_pushed=$((total_pushed + pushed))
    
    if [ "$pushed" = "0" ]; then
        break
    fi
    sleep 1
done

log "Total errata pushed: $total_pushed"
log "========== SYNC COMPLETED =========="
EOF

chmod +x /root/errata-sync.sh
```

### 7.2 Configurazione Cron

```bash
# Esegue ogni domenica alle 05:00
(crontab -l 2>/dev/null | grep -v errata-sync; echo "0 5 * * 0 /root/errata-sync.sh") | crontab -

# Verifica
crontab -l
```

---

## 8. Fase 5: Test e Verifica

### 8.1 Test Container Pubblico

```bash
PUBLIC_IP=$(az container show --resource-group test_group --name aci-errata-api --query "ipAddress.ip" -o tsv)

# Health check
curl -s http://$PUBLIC_IP:5000/api/health | jq

# Test sync USN
curl -s -X POST http://$PUBLIC_IP:5000/api/sync/usn | jq
```

### 8.2 Test Container Interno (dal server UYUNI)

```bash
INTERNAL_IP="10.172.5.4"  # Il tuo IP interno

# Health check
curl -s http://$INTERNAL_IP:5000/api/health | jq

# Deve mostrare:
# {
#   "api": "ok",
#   "database": "ok",
#   "uyuni": "ok",
#   "version": "2.4"
# }
```

### 8.3 Test Sync Pacchetti

```bash
# Popola cache pacchetti UYUNI
curl -s -X POST "http://$INTERNAL_IP:5000/api/uyuni/sync-packages" | jq

# Verifica statistiche
curl -s "http://$INTERNAL_IP:5000/api/stats/packages" | jq
```

### 8.4 Test Push Errata

```bash
# Push 5 errata
curl -s -X POST "http://$INTERNAL_IP:5000/api/uyuni/push?limit=5" | jq

# Verifica in UYUNI Web UI:
# Patches → Manage Patches → cerca gli errata importati
```

---

## 9. Operazioni e Manutenzione

### 9.1 Comandi Utili

```bash
# === STATISTICHE ===
curl -s http://INTERNAL_IP:5000/api/stats/overview | jq
curl -s http://INTERNAL_IP:5000/api/stats/packages | jq

# === SYNC MANUALE ===
# USN (container pubblico)
curl -s -X POST "http://PUBLIC_IP:5000/api/sync/usn" | jq

# Cache pacchetti UYUNI (container interno)
curl -s -X POST "http://INTERNAL_IP:5000/api/uyuni/sync-packages" | jq

# === PUSH A UYUNI ===
curl -s -X POST "http://INTERNAL_IP:5000/api/uyuni/push?limit=10" | jq

# === LOGS ===
az container logs --resource-group test_group --name aci-errata-api
az container logs --resource-group VNET_RG --name aci-errata-api-internal

# === VERIFICA ERRATA SPECIFICO ===
curl -s "http://INTERNAL_IP:5000/api/errata/USN-7931-4/packages" | jq
```

### 9.2 Quando Aggiungi Nuovi Canali

```bash
# 1. Aggiorna cache (rileva automaticamente nuovi canali)
curl -s -X POST "http://INTERNAL_IP:5000/api/uyuni/sync-packages" | jq

# 2. I nuovi errata andranno automaticamente sui nuovi canali
# 3. Per errata già sincronizzati, sono già associati ai canali base
```

---

## 10. Troubleshooting

### Container non raggiunge Database

**Sintomo**: `"database": "error: Connection timed out"`

**Causa**: Container in VNet non raggiunge PostgreSQL

**Soluzione**: 
- Usa Private Endpoint per PostgreSQL
- Nel DATABASE_URL usa l'IP privato del Private Endpoint

### Push fallisce con "Constraint violation"

**Sintomo**: Errore `org.hibernate.exception.Constraint`

**Causa**: Errata già esistente in UYUNI

**Soluzione**: Normale per errata duplicati, il sistema li salta automaticamente

### Errata senza pacchetti

**Sintomo**: `skipped_no_packages` alto

**Causa**: Release dell'errata (es. "bionic") non presente nei tuoi canali (es. hai solo "noble")

**Soluzione**: Normale, solo gli errata con release matching vengono associati

---

## 11. Riferimenti API

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/health` | GET | Health check completo |
| `/api/stats/overview` | GET | Statistiche generali |
| `/api/stats/packages` | GET | Statistiche pacchetti |
| `/api/errata` | GET | Lista errata (con filtri) |
| `/api/errata/<id>/packages` | GET | Pacchetti di un errata |
| `/api/sync/usn` | POST | Sync Ubuntu USN |
| `/api/sync/dsa` | POST | Sync Debian DSA |
| `/api/sync/nvd` | POST | Sync NVD CVSS |
| `/api/sync/oval` | POST | Sync OVAL definitions |
| `/api/uyuni/status` | GET | Stato connessione UYUNI |
| `/api/uyuni/channels` | GET | Lista canali UYUNI |
| `/api/uyuni/sync-packages` | POST | Aggiorna cache pacchetti |
| `/api/uyuni/push` | POST | Push errata a UYUNI |

---

## Appendice: Variabili d'Ambiente

| Variabile | Descrizione | Esempio |
|-----------|-------------|---------|
| `DATABASE_URL` | Connection string PostgreSQL | `postgresql://user:pass@host:5432/db?sslmode=require` |
| `UYUNI_URL` | URL UYUNI Server | `https://10.172.2.5` |
| `UYUNI_USER` | Username UYUNI | `admin` |
| `UYUNI_PASSWORD` | Password UYUNI | `secret` |
| `NVD_API_KEY` | API Key NVD (opzionale) | `xxxxxxxx-xxxx-xxxx-xxxx` |
| `FLASK_ENV` | Ambiente Flask | `production` |

---

*Documento creato: Dicembre 2024*
*Versione: 2.4*
*Autore: UYUNI Errata Manager Project*
