# UYUNI Errata Manager - Guida Completa all'Implementazione

## Indice

1. [Panoramica del Progetto](#1-panoramica-del-progetto)
2. [Architettura](#2-architettura)
3. [Prerequisiti](#3-prerequisiti)
4. [Fase 1: Setup Database PostgreSQL](#4-fase-1-setup-database-postgresql)
5. [Fase 2: Creazione API Flask](#5-fase-2-creazione-api-flask)
6. [Fase 3: Build e Deploy Container](#6-fase-3-build-e-deploy-container)
7. [Fase 4: Configurazione Automazione](#7-fase-4-configurazione-automazione)
8. [Fase 5: Test e Verifica](#8-fase-5-test-e-verifica)
9. [Operazioni Quotidiane](#9-operazioni-quotidiane)
10. [Troubleshooting](#10-troubleshooting)
11. [Riferimenti API](#11-riferimenti-api)

---

## 1. Panoramica del Progetto

### 1.1 Obiettivo

Creare un sistema automatizzato per sincronizzare security advisories (errata) da fonti pubbliche e integrarli in UYUNI Server per la gestione centralizzata delle patch di sicurezza.

### 1.2 Fonti Dati Integrate

| Fonte | Tipo | Descrizione |
|-------|------|-------------|
| **USN** (Ubuntu Security Notices) | Errata | Advisory di sicurezza Ubuntu |
| **DSA** (Debian Security Advisories) | Errata | Advisory di sicurezza Debian |
| **NVD** (National Vulnerability Database) | CVE Enrichment | CVSS scores, severity, CWE |
| **OVAL** (Open Vulnerability Assessment Language) | Definitions | Definizioni per vulnerability scanning |

### 1.3 Perché Questo Sistema?

UYUNI (fork open source di SUSE Manager) ha supporto limitato per errata Ubuntu/Debian. Questo sistema:

- **Colma il gap**: Importa errata da fonti ufficiali Ubuntu e Debian
- **Arricchisce i dati**: Aggiunge CVSS scores da NVD per prioritizzazione
- **Automatizza**: Sync periodico senza intervento manuale
- **Integra OVAL**: Definizioni per OpenSCAP vulnerability scanning

---

## 2. Architettura

### 2.1 Diagramma Architetturale

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              INTERNET                                        │
│  ┌─────────────┐  ┌─────────────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ ubuntu.com  │  │ security-tracker    │  │ NVD API     │  │ Canonical   │ │
│  │ (USN)       │  │ .debian.org (DSA)   │  │ (CVSS)      │  │ (OVAL)      │ │
│  └──────┬──────┘  └──────────┬──────────┘  └──────┬──────┘  └──────┬──────┘ │
└─────────┼────────────────────┼────────────────────┼────────────────┼────────┘
          │                    │                    │                │
          ▼                    ▼                    ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AZURE (test_group)                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              aci-errata-api (Container Pubblico)                     │   │
│  │              IP: 72.146.54.227:5000                                  │   │
│  │              Funzione: Sync da Internet                              │   │
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
│  │                     │     │     Funzione: Push a UYUNI              │   │
│  │   Database:         │     └──────────────────┬──────────────────────┘   │
│  │   - errata          │                        │                          │
│  │   - cves            │                        │ XML-RPC                  │
│  │   - cve_details     │                        ▼                          │
│  │   - oval_definitions│     ┌─────────────────────────────────────────┐   │
│  │   - errata_cves     │     │        UYUNI Server                     │   │
│  │   - sync_logs       │     │        10.172.2.5                       │   │
│  └─────────────────────┘     │        - Gestione Patch                 │   │
│                              │        - Client Ubuntu/Debian           │   │
│                              └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Scelte Architetturali e Motivazioni

#### Perché Due Container?

L'infrastruttura PSN (Polo Strategico Nazionale) ha restrizioni di rete severe:

| Problema | Soluzione |
|----------|-----------|
| Container nella VNet non possono accedere a Internet | Container pubblico per sync esterni |
| Container pubblico non può raggiungere UYUNI (rete privata) | Container interno per push a UYUNI |
| NAT Gateway bloccato da policy Azure | Architettura a due container |

**Tentativo fallito**: Abbiamo provato a creare un NAT Gateway per dare accesso internet al container nella VNet, ma le policy PSN lo bloccano:
```
(RequestDisallowedByPolicy) Resource 'nat-gateway-errata-pip' was disallowed by policy.
Reasons: 'Non è possibile creare risorse cloud di questo tipo'
```

#### Database Condiviso

Entrambi i container usano lo stesso database PostgreSQL. Questo permette:
- Container pubblico scrive errata/CVE/OVAL
- Container interno legge e pusha a UYUNI
- Nessuna duplicazione dati

#### Perché PostgreSQL e non SQLite?

- **Accesso concorrente**: Più container possono accedere simultaneamente
- **Scalabilità**: Supporta grandi volumi (112.000+ errata)
- **Azure Managed**: Backup automatici, alta disponibilità

### 2.3 Flusso Dati

```
1. SYNC (Container Pubblico - ogni domenica alle 04:00)
   ┌──────────────┐
   │ ubuntu.com   │──► API /sync/usn ──► Tabella: errata + cves
   └──────────────┘
   ┌──────────────┐
   │ debian.org   │──► API /sync/dsa ──► Tabella: errata + cves
   └──────────────┘
   ┌──────────────┐
   │ NVD API      │──► API /sync/nvd ──► Tabella: cve_details (CVSS)
   └──────────────┘
   ┌──────────────┐
   │ Canonical    │──► API /sync/oval ──► Tabella: oval_definitions
   └──────────────┘

2. PUSH (Container Interno - dopo sync)
   ┌──────────────┐
   │ Database     │──► API /uyuni/push ──► UYUNI XML-RPC ──► Errata visibili in UI
   └──────────────┘
```

---

## 3. Prerequisiti

### 3.1 Risorse Azure

- **Sottoscrizione Azure** con accesso a:
  - Azure Container Instances (ACI)
  - Azure Container Registry (ACR)
  - Azure Database for PostgreSQL Flexible Server
  - Virtual Network (se in ambiente enterprise)

### 3.2 UYUNI Server

- UYUNI Server installato e funzionante
- Canali Ubuntu configurati (es. Ubuntu 24.04 LTS)
- Credenziali admin per API XML-RPC

### 3.3 Strumenti Locali

- Azure CLI (`az`)
- `curl` e `jq` per testing
- Accesso SSH al server UYUNI

### 3.4 Credenziali Necessarie

| Risorsa | Credenziali |
|---------|-------------|
| PostgreSQL | Username, Password |
| UYUNI | Admin username, Password |
| NVD API | API Key (gratuita, opzionale ma consigliata) |
| Azure ACR | Username, Password |

**Ottenere NVD API Key**: https://nvd.nist.gov/developers/request-an-api-key

---

## 4. Fase 1: Setup Database PostgreSQL

### 4.1 Creazione Database (Azure)

```bash
# Variabili
RG="test_group"
PG_SERVER="pg-errata-test"
PG_ADMIN="errataadmin"
PG_PASS="ErrataSecure2024"  # Cambia con password sicura
DB_NAME="uyuni_errata"

# Crea server PostgreSQL
az postgres flexible-server create \
  --resource-group $RG \
  --name $PG_SERVER \
  --admin-user $PG_ADMIN \
  --admin-password $PG_PASS \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 15

# Crea database
az postgres flexible-server db create \
  --resource-group $RG \
  --server-name $PG_SERVER \
  --database-name $DB_NAME
```

### 4.2 Schema Database

Esegui questi comandi SQL per creare le tabelle:

```sql
-- Tabella principale errata
CREATE TABLE errata (
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

CREATE INDEX idx_errata_source ON errata(source);
CREATE INDEX idx_errata_distribution ON errata(distribution);
CREATE INDEX idx_errata_sync_status ON errata(sync_status);
CREATE INDEX idx_errata_issued_date ON errata(issued_date DESC);

-- Tabella CVE
CREATE TABLE cves (
    id SERIAL PRIMARY KEY,
    cve_id VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cves_cve_id ON cves(cve_id);

-- Relazione errata-CVE
CREATE TABLE errata_cves (
    errata_id INTEGER REFERENCES errata(id) ON DELETE CASCADE,
    cve_id INTEGER REFERENCES cves(id) ON DELETE CASCADE,
    PRIMARY KEY (errata_id, cve_id)
);

-- Dettagli CVE da NVD
CREATE TABLE cve_details (
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

CREATE INDEX idx_cve_details_severity ON cve_details(severity);
CREATE INDEX idx_cve_details_cvss ON cve_details(cvss_v3_score DESC);

-- OVAL Definitions
CREATE TABLE oval_definitions (
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

CREATE INDEX idx_oval_platform ON oval_definitions(platform);
CREATE INDEX idx_oval_severity ON oval_definitions(severity);

-- Mapping errata-CVE-OVAL
CREATE TABLE errata_cve_oval_map (
    errata_id INTEGER REFERENCES errata(id) ON DELETE CASCADE,
    cve_id VARCHAR(50),
    oval_id VARCHAR(200),
    PRIMARY KEY (errata_id, cve_id, oval_id)
);

-- Stato CVE per sistema
CREATE TABLE system_cve_status (
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

CREATE INDEX idx_system_cve_status ON system_cve_status(uyuni_system_id, status);

-- Risultati scan SCAP
CREATE TABLE scap_scan_results (
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
CREATE TABLE sync_logs (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    items_processed INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE INDEX idx_sync_logs_type ON sync_logs(sync_type, started_at DESC);
```

### 4.3 Esecuzione SQL via Azure CLI

```bash
# Esegui ogni CREATE TABLE separatamente
az postgres flexible-server execute \
  --name pg-errata-test \
  --admin-user errataadmin \
  --admin-password "ErrataSecure2024" \
  --database-name uyuni_errata \
  --querytext "CREATE TABLE errata (...);"
```

---

## 5. Fase 2: Creazione API Flask

### 5.1 Struttura File

```
uyuni-errata-manager/
├── app.py           # API Flask principale
├── Dockerfile.api   # Dockerfile per container
└── auto-sync.sh     # Script automazione (va sul server UYUNI)
```

### 5.2 Codice API (app.py)

Crea il file `app.py` con il seguente contenuto:

```python
#!/usr/bin/env python3
"""
UYUNI Errata Manager - Enhanced API v2.3
Integra: USN, DSA, NVD, OVAL, OpenSCAP, CVE Audit
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
    'User-Agent': 'UYUNI-Errata-Manager/2.3',
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
    status = {'api': 'ok', 'database': 'unknown', 'uyuni': 'unknown', 'version': '2.3'}
    
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
    
    cur.execute("SELECT severity, COUNT(*) as count FROM errata GROUP BY severity ORDER BY count DESC")
    stats['errata_by_severity'] = {r['severity'] or 'unknown': r['count'] for r in cur.fetchall()}
    
    cur.execute("SELECT COUNT(*) as total FROM cves")
    stats['cves'] = {'total': cur.fetchone()['total']}
    
    try:
        cur.execute("""
            SELECT COUNT(*) as total,
                COUNT(CASE WHEN cvss_v3_score IS NOT NULL THEN 1 END) as with_cvss_v3,
                COUNT(CASE WHEN severity = 'CRITICAL' THEN 1 END) as critical,
                COUNT(CASE WHEN severity = 'HIGH' THEN 1 END) as high,
                ROUND(AVG(cvss_v3_score)::numeric, 2) as avg_cvss
            FROM cve_details
        """)
        row = cur.fetchone()
        stats['nvd'] = dict(row) if row else {'total': 0}
    except:
        stats['nvd'] = {'total': 0}
    
    try:
        cur.execute("SELECT platform, COUNT(*) as count FROM oval_definitions GROUP BY platform")
        stats['oval'] = {r['platform']: r['count'] for r in cur.fetchall()}
    except:
        stats['oval'] = {}
    
    try:
        cur.execute("SELECT status, COUNT(*) as count FROM system_cve_status GROUP BY status")
        stats['system_cve_status'] = {r['status']: r['count'] for r in cur.fetchall()}
    except:
        stats['system_cve_status'] = {}
    
    cur.execute("""
        SELECT sync_type, MAX(completed_at) as last_sync 
        FROM sync_logs WHERE status = 'completed' GROUP BY sync_type
    """)
    stats['last_syncs'] = {r['sync_type']: r['last_sync'].isoformat() if r['last_sync'] else None for r in cur.fetchall()}
    
    cur.close()
    conn.close()
    return jsonify(stats)

# ============================================================
# ERRATA ENDPOINTS
# ============================================================
@app.route('/api/errata', methods=['GET'])
def list_errata():
    limit = request.args.get('limit', 100, type=int)
    source = request.args.get('source')
    distribution = request.args.get('distribution')
    severity = request.args.get('severity')
    sync_status = request.args.get('sync_status')
    
    conn = get_db()
    cur = conn.cursor()
    
    query = "SELECT * FROM errata WHERE 1=1"
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

@app.route('/api/cves', methods=['GET'])
def list_cves():
    limit = request.args.get('limit', 100, type=int)
    severity = request.args.get('severity')
    
    conn = get_db()
    cur = conn.cursor()
    
    query = """
        SELECT c.id, c.cve_id, cd.cvss_v3_score, cd.cvss_v3_vector, cd.severity, cd.cwe_ids, cd.published_date
        FROM cves c
        LEFT JOIN cve_details cd ON c.cve_id = cd.cve_id
    """
    params = []
    
    if severity:
        query += " WHERE cd.severity = %s"
        params.append(severity.upper())
    
    query += " ORDER BY cd.cvss_v3_score DESC NULLS LAST LIMIT %s"
    params.append(limit)
    
    cur.execute(query, params)
    cves = [dict(r) for r in cur.fetchall()]
    
    cur.close()
    conn.close()
    return jsonify({'count': len(cves), 'cves': cves})

# ============================================================
# SYNC USN
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
            
            new_errata.append({
                'advisory_id': notice_id,
                'title': notice.get('title', '')[:500],
                'description': notice.get('description', '')[:4000],
                'severity': severity,
                'source': 'usn',
                'distribution': 'ubuntu',
                'issued_date': notice.get('published'),
                'cves': cve_ids
            })
        
        offset += 20
        if offset > 500:
            break
    
    processed = 0
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
        except:
            continue
    
    cur.execute("UPDATE sync_logs SET status = 'completed', completed_at = NOW(), items_processed = %s WHERE id = %s", (processed, log_id))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success', 'source': 'usn', 'processed': processed, 'last_known': last_usn})

# ============================================================
# SYNC DSA
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
                except:
                    continue
    
    cur.execute("UPDATE sync_logs SET status = 'completed', completed_at = NOW(), items_processed = %s WHERE id = %s", (processed, log_id))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success', 'source': 'dsa', 'offset': offset, 'batch_size': batch_size, 'processed': processed, 'total_packages': len(data), 'next_offset': offset + batch_size if offset + batch_size < len(data) else None})

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
    
    return jsonify({'status': 'success', 'processed': processed, 'pending_total': len(pending_cves), 'errors_count': len(errors), 'errors': errors[:5] if errors else None, 'rate_limit': 'with API key (fast)' if NVD_API_KEY else 'without API key (slow)'})

@app.route('/api/nvd/status', methods=['GET'])
def nvd_status():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) as total FROM cves")
    total_cves = cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) as total FROM cve_details")
    enriched = cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) as total FROM cve_details WHERE cvss_v3_score IS NOT NULL")
    with_cvss = cur.fetchone()['total']
    
    stats = {'total_cves': total_cves, 'enriched_cves': enriched, 'pending': total_cves - enriched, 'with_cvss_v3': with_cvss, 'enrichment_percentage': round((enriched / total_cves * 100), 1) if total_cves > 0 else 0}
    
    cur.execute("SELECT severity, COUNT(*) as count FROM cve_details GROUP BY severity ORDER BY count DESC")
    stats['by_severity'] = {r['severity'] or 'unknown': r['count'] for r in cur.fetchall()}
    
    cur.execute("SELECT MAX(nvd_last_sync) as last_sync FROM cve_details")
    row = cur.fetchone()
    stats['last_sync'] = row['last_sync'].isoformat() if row and row['last_sync'] else None
    
    cur.execute("SELECT cve_id, cvss_v3_score, severity FROM cve_details WHERE cvss_v3_score IS NOT NULL ORDER BY cvss_v3_score DESC LIMIT 10")
    stats['top_critical'] = [dict(r) for r in cur.fetchall()]
    
    cur.close()
    conn.close()
    return jsonify(stats)

# ============================================================
# SYNC OVAL
# ============================================================
@app.route('/api/sync/oval', methods=['POST'])
def sync_oval():
    platform = request.args.get('platform', 'all')
    codename = request.args.get('codename', None)
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("INSERT INTO sync_logs (sync_type, status, started_at) VALUES ('oval', 'running', NOW()) RETURNING id")
    log_id = cur.fetchone()['id']
    conn.commit()
    
    results = {}
    total_processed = 0
    
    platforms_to_sync = OVAL_SOURCES if platform == 'all' else ({platform: OVAL_SOURCES[platform]} if platform in OVAL_SOURCES else {})
    ns = {'oval': 'http://oval.mitre.org/XMLSchema/oval-definitions-5', 'oval-def': 'http://oval.mitre.org/XMLSchema/oval-definitions-5'}
    
    for plat, codenames_dict in platforms_to_sync.items():
        for cn, url in codenames_dict.items():
            if codename and cn != codename:
                continue
            try:
                resp = requests.get(url, timeout=120)
                resp.raise_for_status()
                xml_content = bz2.decompress(resp.content).decode('utf-8')
                root = ET.fromstring(xml_content)
                definitions = []
                
                for definition in root.findall('.//oval-def:definition', ns):
                    oval_id = definition.get('id')
                    def_class = definition.get('class')
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
                    advisory_refs = [ref.get('ref_id') for ref in metadata.findall('.//oval-def:reference[@source="USN"]', ns) if ref.get('ref_id')]
                    
                    definitions.append({'oval_id': oval_id, 'class': def_class, 'title': title[:500] if title else None, 'description': description[:2000] if description else None, 'severity': severity, 'platform': f"{plat}-{cn}", 'platform_version': cn, 'cve_refs': cve_refs, 'advisory_refs': advisory_refs, 'source_url': url})
                
                for d in definitions:
                    cur.execute("""
                        INSERT INTO oval_definitions (oval_id, class, title, description, severity, platform, platform_version, cve_refs, advisory_refs, source_url, last_sync)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (oval_id) DO UPDATE SET title = EXCLUDED.title, severity = EXCLUDED.severity, cve_refs = EXCLUDED.cve_refs, advisory_refs = EXCLUDED.advisory_refs, last_sync = NOW()
                    """, (d['oval_id'], d['class'], d['title'], d['description'], d['severity'], d['platform'], d['platform_version'], d['cve_refs'], d['advisory_refs'], d['source_url']))
                
                conn.commit()
                results[f"{plat}-{cn}"] = len(definitions)
                total_processed += len(definitions)
            except Exception as e:
                results[f"{plat}-{cn}"] = f"error: {str(e)[:100]}"
    
    try:
        cur.execute("""
            INSERT INTO errata_cve_oval_map (errata_id, cve_id, oval_id)
            SELECT DISTINCT e.id, c.cve_id, od.oval_id
            FROM errata e JOIN errata_cves ec ON e.id = ec.errata_id JOIN cves c ON ec.cve_id = c.id JOIN oval_definitions od ON c.cve_id = ANY(od.cve_refs)
            ON CONFLICT DO NOTHING
        """)
        mapped = cur.rowcount
    except:
        mapped = 0
    
    cur.execute("UPDATE sync_logs SET status = 'completed', completed_at = NOW(), items_processed = %s WHERE id = %s", (total_processed, log_id))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success', 'results': results, 'total_definitions': total_processed, 'cve_oval_mappings_created': mapped})

@app.route('/api/oval/status', methods=['GET'])
def oval_status():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT platform, COUNT(*) as count, MAX(last_sync) as last_sync FROM oval_definitions GROUP BY platform ORDER BY platform")
    platforms = [{'platform': r['platform'], 'count': r['count'], 'last_sync': r['last_sync'].isoformat() if r['last_sync'] else None} for r in cur.fetchall()]
    
    cur.execute("SELECT severity, COUNT(*) as count FROM oval_definitions GROUP BY severity")
    by_severity = {r['severity']: r['count'] for r in cur.fetchall()}
    
    cur.execute("SELECT COUNT(*) as total FROM errata_cve_oval_map")
    mappings = cur.fetchone()['total']
    
    cur.execute("SELECT COUNT(*) as total FROM oval_definitions")
    total = cur.fetchone()['total']
    
    cur.close()
    conn.close()
    return jsonify({'total_definitions': total, 'platforms': platforms, 'by_severity': by_severity, 'errata_cve_oval_mappings': mappings})

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

@app.route('/api/uyuni/push', methods=['POST'])
def uyuni_push():
    """Push errata a UYUNI - SENZA issue_date/update_date (non supportati da API)"""
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
        
        cur.execute("SELECT * FROM errata WHERE sync_status = 'pending' AND distribution = ANY(%s) ORDER BY issued_date DESC LIMIT %s", (active_distributions, limit))
        pending = cur.fetchall()
        
        pushed = 0
        errors = []
        
        for errata in pending:
            try:
                dist = errata['distribution']
                if dist not in channel_map:
                    continue
                target_channels = channel_map[dist]
                
                # NOTA: UYUNI API errata.create NON accetta issue_date e update_date
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
                    'notes': f'Imported by UYUNI Errata Manager from {errata["source"].upper()}'
                }
                
                severity = errata.get('severity', 'medium')
                severity_keywords = {'critical': ['critical'], 'high': ['important'], 'medium': ['moderate'], 'low': ['low']}
                keywords = severity_keywords.get(severity, ['moderate'])
                
                client.errata.create(session, errata_info, [], keywords, [], target_channels)
                cur.execute("UPDATE errata SET sync_status = 'synced' WHERE id = %s", (errata['id'],))
                pushed += 1
            except Exception as e:
                error_msg = str(e)
                if 'already exists' in error_msg.lower():
                    cur.execute("UPDATE errata SET sync_status = 'synced' WHERE id = %s", (errata['id'],))
                    pushed += 1
                else:
                    errors.append(f"{errata['advisory_id']}: {error_msg[:100]}")
        
        conn.commit()
        client.auth.logout(session)
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'error': str(e)}), 500
    
    cur.close()
    conn.close()
    return jsonify({'status': 'success', 'pushed': pushed, 'pending_remaining': len(pending) - pushed, 'errors': errors[:5] if errors else None})

# ============================================================
# SYNC STATUS
# ============================================================
@app.route('/api/sync/status', methods=['GET'])
def sync_status():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sync_logs ORDER BY started_at DESC LIMIT 20")
    logs = [{'id': r['id'], 'sync_type': r['sync_type'], 'status': r['status'], 'started_at': r['started_at'].isoformat() if r['started_at'] else None, 'completed_at': r['completed_at'].isoformat() if r['completed_at'] else None, 'items_processed': r['items_processed'], 'error_message': r['error_message']} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({'logs': logs})

# ============================================================
# AUDIT ENDPOINTS
# ============================================================
@app.route('/api/audit/cve', methods=['GET'])
def audit_cve():
    severities = request.args.get('severity', 'CRITICAL,HIGH').upper().split(',')
    limit = request.args.get('limit', 50, type=int)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT cve_id, cvss_v3_score, severity, description, cwe_ids, published_date FROM cve_details WHERE severity = ANY(%s) ORDER BY cvss_v3_score DESC NULLS LAST LIMIT %s", (severities, limit))
    results = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({'filters': {'severity': severities, 'limit': limit}, 'count': len(results), 'cves': results})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
```

### 5.3 Dockerfile (Dockerfile.api)

```dockerfile
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
```

---

## 6. Fase 3: Build e Deploy Container

### 6.1 Creazione Azure Container Registry

```bash
RG="test_group"
ACR_NAME="acaborerrata"

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
  --image errata-api:v2.3 \
  --file Dockerfile.api .
```

### 6.3 Deploy Container Pubblico (per sync da internet)

```bash
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

az container create \
  --resource-group test_group \
  --name aci-errata-api \
  --image ${ACR_NAME}.azurecr.io/errata-api:v2.3 \
  --registry-login-server ${ACR_NAME}.azurecr.io \
  --registry-username $ACR_NAME \
  --registry-password "$ACR_PASSWORD" \
  --os-type Linux \
  --cpu 1 \
  --memory 2 \
  --ports 5000 \
  --ip-address Public \
  --restart-policy Always \
  --environment-variables \
    FLASK_ENV=production \
    DATABASE_URL="postgresql://errataadmin:ErrataSecure2024@pg-errata-test.postgres.database.azure.com:5432/uyuni_errata?sslmode=require" \
    UYUNI_URL="" \
    UYUNI_USER="" \
    UYUNI_PASSWORD="" \
    NVD_API_KEY="YOUR_NVD_API_KEY"
```

**Nota**: Il container pubblico NON ha configurazione UYUNI perché non può raggiungerlo.

### 6.4 Deploy Container Interno (per push a UYUNI)

```bash
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

az container create \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal \
  --image ${ACR_NAME}.azurecr.io/errata-api:v2.3 \
  --registry-login-server ${ACR_NAME}.azurecr.io \
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
    UYUNI_PASSWORD="YOUR_UYUNI_PASSWORD" \
    NVD_API_KEY="YOUR_NVD_API_KEY"
```

### 6.5 Verifica Deploy

```bash
# Container pubblico
az container show --resource-group test_group --name aci-errata-api \
  --query "{Status:instanceView.state, IP:ipAddress.ip}" -o table

# Container interno
az container show --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal \
  --query "{Status:instanceView.state, IP:ipAddress.ip}" -o table
```

---

## 7. Fase 4: Configurazione Automazione

### 7.1 Script auto-sync.sh (sul server UYUNI)

```bash
mkdir -p /root/errata-manager

cat > /root/errata-manager/auto-sync.sh << 'EOF'
#!/bin/bash
# UYUNI Errata Manager - Auto Sync Script

LOG_FILE="/var/log/uyuni-errata-sync.log"
PUBLIC_API="http://72.146.54.227:5000"   # IP container pubblico
INTERNAL_API="http://10.172.5.4:5000"    # IP container interno

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a $LOG_FILE
}

log "========== STARTING SYNC =========="

# 1. Sync USN (container pubblico)
log "Syncing USN..."
curl -s -X POST "$PUBLIC_API/api/sync/usn" >> $LOG_FILE 2>&1

# 2. Sync DSA (container pubblico)
log "Syncing DSA..."
for offset in 0 500 1000 1500 2000 2500 3000 3500; do
    curl -s -X POST "$PUBLIC_API/api/sync/dsa?offset=$offset" >> $LOG_FILE 2>&1
    sleep 2
done

# 3. Sync NVD (container pubblico) - 100 CVE per run
log "Syncing NVD..."
curl -s -X POST "$PUBLIC_API/api/sync/nvd?batch_size=100" >> $LOG_FILE 2>&1

# 4. Sync OVAL (container pubblico)
log "Syncing OVAL..."
curl -s -X POST "$PUBLIC_API/api/sync/oval" >> $LOG_FILE 2>&1

# 5. Push a UYUNI (container interno) - batch di 2 per evitare timeout
log "Pushing to UYUNI..."
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25; do
    result=$(curl -s -X POST "$INTERNAL_API/api/uyuni/push?limit=2")
    pushed=$(echo $result | jq -r '.pushed // 0')
    log "Push batch $i: $pushed errata"
    if [ "$pushed" = "0" ]; then
        break
    fi
    sleep 1
done

log "========== SYNC COMPLETED =========="
EOF

chmod +x /root/errata-manager/auto-sync.sh
```

**IMPORTANTE**: Aggiorna gli IP nel file con quelli reali dei tuoi container!

### 7.2 Configurazione Cron

```bash
# Aggiungi al crontab
(crontab -l 2>/dev/null; echo "0 4 * * 0 /root/errata-manager/auto-sync.sh") | crontab -

# Verifica
crontab -l
```

Questo esegue il sync ogni domenica alle 04:00 (dopo il sync canali UYUNI configurato alle 02:00).

---

## 8. Fase 5: Test e Verifica

### 8.1 Test Container Pubblico

```bash
# Ottieni IP
PUBLIC_IP=$(az container show --resource-group test_group --name aci-errata-api --query "ipAddress.ip" -o tsv)

# Health check
curl -s http://$PUBLIC_IP:5000/api/health | jq

# Test sync USN
curl -s -X POST http://$PUBLIC_IP:5000/api/sync/usn | jq
```

### 8.2 Test Container Interno (dal server UYUNI)

```bash
# Health check
curl -s http://10.172.5.4:5000/api/health | jq

# Output atteso:
# {
#   "api": "ok",
#   "database": "ok",
#   "uyuni": "ok",
#   "version": "2.3"
# }

# Test push
curl -s -X POST "http://10.172.5.4:5000/api/uyuni/push?limit=2" | jq
```

### 8.3 Verifica in UYUNI Web UI

1. Accedi a `https://YOUR_UYUNI_SERVER`
2. Vai a **Patches** → **Manage Patches**
3. Dovresti vedere gli errata importati

---

## 9. Operazioni Quotidiane

### 9.1 Comandi Utili

```bash
# === STATISTICHE ===
curl -s http://10.172.5.4:5000/api/stats/overview | jq

# === SYNC MANUALE ===
# USN (Ubuntu)
curl -s -X POST "http://72.146.54.227:5000/api/sync/usn" | jq

# DSA (Debian)
curl -s -X POST "http://72.146.54.227:5000/api/sync/dsa?offset=0" | jq

# NVD (CVSS enrichment)
curl -s -X POST "http://72.146.54.227:5000/api/sync/nvd?batch_size=50" | jq

# OVAL
curl -s -X POST "http://72.146.54.227:5000/api/sync/oval" | jq

# === PUSH A UYUNI ===
curl -s -X POST "http://10.172.5.4:5000/api/uyuni/push?limit=2" | jq

# === LOGS ===
# Logs sync
curl -s http://10.172.5.4:5000/api/sync/status | jq

# Logs container
az container logs --resource-group test_group --name aci-errata-api
az container logs --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal
```

### 9.2 Monitoraggio

```bash
# Verifica errata pending
curl -s "http://10.172.5.4:5000/api/errata?sync_status=pending&distribution=ubuntu" | jq '.count'

# CVE critici
curl -s "http://10.172.5.4:5000/api/audit/cve?severity=CRITICAL" | jq
```

---

## 10. Troubleshooting

### 10.1 Container non raggiunge Internet

**Sintomo**: Sync USN/DSA/NVD/OVAL falliscono con "Network is unreachable"

**Causa**: Container nella VNet privata senza NAT Gateway

**Soluzione**: Usare architettura a due container (pubblico per sync, interno per UYUNI)

### 10.2 Push UYUNI fallisce con "Invalid argument: issue_date"

**Causa**: UYUNI API non accetta issue_date/update_date nel dizionario errata_info

**Soluzione**: Rimuovere questi campi dal codice (già fatto in v2.3)

### 10.3 Worker Timeout nel container

**Sintomo**: `WORKER TIMEOUT (pid:XX)` nei logs

**Causa**: Push di troppi errata in una singola richiesta

**Soluzione**: Usare `limit=2` nel push invece di valori più alti

### 10.4 NVD Sync molto lento

**Causa**: Senza API key, NVD limita a 5 richieste/30 secondi

**Soluzione**: Registrarsi per API key gratuita su https://nvd.nist.gov/developers/request-an-api-key

### 10.5 Errata non appaiono in UYUNI

**Verifica**:
1. Controlla che ci siano canali Ubuntu/Debian in UYUNI
2. Verifica mapping distribuzione:
   ```bash
   curl -s http://10.172.5.4:5000/api/uyuni/channels | jq
   ```
3. Controlla errata pending per quella distribuzione:
   ```bash
   curl -s "http://10.172.5.4:5000/api/errata?sync_status=pending&distribution=ubuntu" | jq '.count'
   ```

---

## 11. Riferimenti API

### Endpoints Principali

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/stats/overview` | GET | Statistiche complete |
| `/api/errata` | GET | Lista errata (con filtri) |
| `/api/cves` | GET | Lista CVE |
| `/api/sync/usn` | POST | Sync Ubuntu USN |
| `/api/sync/dsa` | POST | Sync Debian DSA |
| `/api/sync/nvd` | POST | Sync NVD CVSS |
| `/api/sync/oval` | POST | Sync OVAL definitions |
| `/api/sync/status` | GET | Log sincronizzazioni |
| `/api/nvd/status` | GET | Stato enrichment NVD |
| `/api/oval/status` | GET | Stato OVAL |
| `/api/uyuni/status` | GET | Stato connessione UYUNI |
| `/api/uyuni/channels` | GET | Lista canali UYUNI |
| `/api/uyuni/push` | POST | Push errata a UYUNI |
| `/api/audit/cve` | GET | CVE critici |

### Parametri Query

**GET /api/errata**
- `limit`: Numero risultati (default: 100)
- `source`: Filtra per fonte (usn, dsa)
- `distribution`: Filtra per distribuzione (ubuntu, debian-bookworm, ecc.)
- `severity`: Filtra per severity
- `sync_status`: Filtra per stato (pending, synced)

**POST /api/sync/dsa**
- `offset`: Offset per paginazione (0, 500, 1000, ...)

**POST /api/sync/nvd**
- `batch_size`: Numero CVE per batch (default: 50)
- `force`: Rielabora anche CVE già processati (true/false)

**POST /api/uyuni/push**
- `limit`: Numero errata per batch (default: 10, consigliato: 2)

---

## Appendice: Variabili d'Ambiente

| Variabile | Descrizione | Esempio |
|-----------|-------------|---------|
| `DATABASE_URL` | Connection string PostgreSQL | `postgresql://user:pass@host:5432/db?sslmode=require` |
| `UYUNI_URL` | URL UYUNI Server | `https://10.172.2.5` |
| `UYUNI_USER` | Username UYUNI | `admin` |
| `UYUNI_PASSWORD` | Password UYUNI | `secret` |
| `NVD_API_KEY` | API Key NVD (opzionale) | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `FLASK_ENV` | Ambiente Flask | `production` |

---

*Documento creato: Dicembre 2024*
*Versione: 2.3*
