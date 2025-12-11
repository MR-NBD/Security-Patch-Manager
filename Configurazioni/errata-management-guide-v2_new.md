# Ubuntu/Debian Errata Management System per Foreman/Katello

## Guida Completa all'Implementazione su Azure

**Versione:** 2.0  
**Data:** Dicembre 2024  
**Ambiente:** Azure - Italy North  
**Stato:** Funzionante e Testato

---

## Indice

1. [Panoramica e Obiettivi](#1-panoramica-e-obiettivi)
2. [Architettura](#2-architettura)
3. [Prerequisiti](#3-prerequisiti)
4. [Configurazione Rete Azure](#4-configurazione-rete-azure)
5. [Azure Container Registry](#5-azure-container-registry)
6. [Build delle Immagini Docker](#6-build-delle-immagini-docker)
7. [Azure Database for PostgreSQL](#7-azure-database-for-postgresql)
8. [Azure Storage Account](#8-azure-storage-account)
9. [Generazione Dati Errata](#9-generazione-dati-errata)
10. [Deploy Container Group (ACI)](#10-deploy-container-group-aci)
11. [Inizializzazione Database](#11-inizializzazione-database)
12. [Test e Verifica](#12-test-e-verifica)
13. [Configurazione Grafana](#13-configurazione-grafana)
14. [Registrazione Host in Foreman](#14-registrazione-host-in-foreman)
15. [Gestione e Manutenzione](#15-gestione-e-manutenzione)
16. [Troubleshooting](#16-troubleshooting)
17. [Costi e Ottimizzazione](#17-costi-e-ottimizzazione)
18. [Limitazioni Note](#18-limitazioni-note)

---

## 1. Panoramica e Obiettivi

### 1.1 Il Problema

Foreman/Katello gestisce VM Ubuntu e Debian mostrando i **pacchetti installati** e **installabili**. Tuttavia, manca il concetto di **errata** (security advisories):

- Ubuntu pubblica **USN** (Ubuntu Security Notices)
- Debian pubblica **DSA/DLA** (Debian Security Advisory / Debian LTS Advisory)

Questi non sono integrati nativamente in Katello community edition (esiste una PR #7961 dal 2019 mai mergiata).

### 1.2 La Soluzione

Sistema esterno composto da:

1. **errata_parser** (ATIX) - Scarica USN/DSA dai repository ufficiali
2. **errata_server** (ATIX) - API REST per consultare errata
3. **errata_backend** (custom) - Correla errata con host Foreman, salva in PostgreSQL
4. **Grafana** - Dashboard per visualizzazione

### 1.3 Componenti Deployati

| Componente | Tecnologia | Porta | Funzione |
|------------|------------|-------|----------|
| errata_server | Python/Twisted | 8015 | API REST errata |
| errata_backend | Python/Flask | 5000 | Correlazione e sync |
| Grafana | Grafana 10.2 | 3000 | Dashboard |
| PostgreSQL | Azure Flexible | 5432 | Database |

---

## 2. Architettura

### 2.1 Schema Generale

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AZURE - Italy North                             │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │           VNet: ASL0603-spoke10-spoke-italynorth                    │    │
│  │                                                                      │    │
│  │   ┌─────────────────────┐      ┌─────────────────────────────────┐  │    │
│  │   │  Subnet: default    │      │  Subnet: errata-aci-subnet      │  │    │
│  │   │  10.172.2.0/27      │      │  10.172.5.0/28                  │  │    │
│  │   │                     │      │  (delegata a ACI)               │  │    │
│  │   │  ┌───────────────┐  │      │  ┌────────────────────────────┐ │  │    │
│  │   │  │   Foreman     │  │      │  │   ACI Container Group      │ │  │    │
│  │   │  │   Katello     │◄─┼──────┼─►│   errata-management        │ │  │    │
│  │   │  │   (RHEL 9)    │  │ API  │  │                            │ │  │    │
│  │   │  │               │  │      │  │  • errata_server (:8015)   │ │  │    │
│  │   │  │  10.172.2.17  │  │      │  │  • errata_backend (:5000)  │ │  │    │
│  │   │  └───────────────┘  │      │  │  • grafana (:3000)         │ │  │    │
│  │   │                     │      │  │                            │ │  │    │
│  │   │                     │      │  │  IP: 10.172.5.4            │ │  │    │
│  │   └─────────────────────┘      │  └────────────────────────────┘ │  │    │
│  │                                └─────────────────────────────────┘  │    │
│  │                                                                      │    │
│  │   ┌─────────────────────┐      ┌─────────────────────────────────┐  │    │
│  │   │  Subnet: DBA        │      │  Azure Storage Account          │  │    │
│  │   │  10.172.2.192/26    │      │  sterrata01                     │  │    │
│  │   │                     │      │                                  │  │    │
│  │   │  ┌───────────────┐  │      │  File Shares:                   │  │    │
│  │   │  │  PostgreSQL   │  │      │  • errata-data (JSON errata)    │  │    │
│  │   │  │  Flexible     │◄─┼──────┼──• errata-grafana (Grafana)     │  │    │
│  │   │  │  Server       │  │      │                                  │  │    │
│  │   │  │               │  │      └─────────────────────────────────┘  │    │
│  │   │  │  pgserverrata │  │                                           │    │
│  │   │  │  10.172.2.196 │  │                                           │    │
│  │   │  └───────────────┘  │                                           │    │
│  │   └─────────────────────┘                                           │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌──────────────────────────┐                                               │
│  │  Azure Container Registry │                                               │
│  │  acrerrata.azurecr.io    │                                               │
│  │                          │                                               │
│  │  Images:                 │                                               │
│  │  • errata_parser:v1      │                                               │
│  │  • errata_server:v1      │                                               │
│  │  • errata_backend:v2     │                                               │
│  └──────────────────────────┘                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Flusso Dati

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Ubuntu USN DB  │     │  Cloud Shell    │     │  Azure File     │
│  (usn.ubuntu.   │────►│  (process_usn.  │────►│  Share          │
│   com)          │     │   py)           │     │  (errata JSON)  │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Foreman API    │     │  errata_backend │     │  errata_server  │
│  /api/hosts     │────►│  (Flask)        │◄────│  (legge JSON)   │
│  /api/packages  │     │                 │     │                 │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   PostgreSQL    │
                        │   (correlazioni)│
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │    Grafana      │
                        │   (dashboard)   │
                        └─────────────────┘
```

### 2.3 Nota sul Parser

Il parser ATIX originale richiede accesso Internet per scaricare gli USN. Poiché i container ACI nella VNet privata non hanno accesso Internet diretto, la generazione dei dati errata viene fatta dalla **Cloud Shell** che ha accesso Internet, e i file JSON vengono caricati su Azure File Share.

---

## 3. Prerequisiti

### 3.1 Ambiente Azure

- Subscription Azure attiva
- VNet esistente con spazio per nuova subnet (/28 minimo)
- Azure Cloud Shell (Bash)
- Permessi per creare risorse

**⚠️ IMPORTANTE - Cloud Shell Effimera:**
La Cloud Shell di Azure è effimera: i file nella home directory (`~`) vengono persi dopo 20 minuti di inattività o dopo il riavvio della sessione. Solo la directory `~/clouddrive` è persistente (collegata a un Azure File Share).

**Consiglio:** Salvare i file importanti (YAML, script) in `~/clouddrive` oppure su un repository Git.

### 3.2 Foreman/Katello

- Foreman/Katello installato e funzionante
- Host Ubuntu/Debian registrati come Content Host
- Credenziali API (utente con permessi di lettura)
- **IMPORTANTE**: Gli host devono aver inviato l'inventario pacchetti a Foreman

### 3.3 Informazioni da Raccogliere

| Informazione | Esempio | Tua Configurazione |
|--------------|---------|-------------------|
| Subscription ID | `896dd1f5-30ae-42db-a7d4-c0f8184c6b1c` | _______________ |
| Resource Group | `ASL0603-spoke10-rg-spoke-italynorth` | _______________ |
| VNet Name | `ASL0603-spoke10-spoke-italynorth` | _______________ |
| Location | `italynorth` | _______________ |
| IP Foreman | `10.172.2.17` | _______________ |
| User Foreman | `admin` | _______________ |
| Password Foreman | `***` | _______________ |

---

## 4. Configurazione Rete Azure

### 4.1 Selezionare la Subscription Corretta

```bash
# Lista subscription disponibili
az account list --output table

# Seleziona la subscription corretta
az account set --subscription "<SUBSCRIPTION_ID>"

# Verifica
az account show --output table
```

### 4.2 Aggiungere Address Space (se necessario)

Se non c'è spazio nella VNet:

1. Portale Azure → **Virtual Networks** → seleziona la VNet
2. **Address space** → **+ Add**
3. Aggiungi: `10.172.5.0/24`
4. **Save**

### 4.3 Creare Subnet per ACI

1. Nella VNet, vai su **Subnets** → **+ Subnet**
2. Configura:

| Campo | Valore |
|-------|--------|
| Name | `errata-aci-subnet` |
| Subnet address range | `10.172.5.0/28` |
| NAT gateway | None |
| Network security group | None |
| Route table | (stesso delle altre subnet) |
| **Subnet delegation** | `Microsoft.ContainerInstance/containerGroups` |

3. **Save**

### 4.4 Aggiungere Service Endpoint per Storage

```bash
az network vnet subnet update \
  --resource-group <RESOURCE_GROUP> \
  --vnet-name <VNET_NAME> \
  --name errata-aci-subnet \
  --service-endpoints Microsoft.Storage
```

---

## 5. Azure Container Registry

### 5.1 Creare ACR (Portale o CLI)

**Portale:**
1. Cerca **Container registries** → **+ Create**
2. Configura:

| Campo | Valore |
|-------|--------|
| Registry name | `acrerrata` (unico globalmente) |
| Location | `Italy North` |
| SKU | `Basic` (~5€/mese) |

3. **Review + create** → **Create**

**CLI:**
```bash
az acr create \
  --resource-group <RESOURCE_GROUP> \
  --name acrerrata \
  --sku Basic \
  --location italynorth
```

### 5.2 Abilitare Admin Access

```bash
az acr update -n acrerrata --admin-enabled true
```

### 5.3 Ottenere Credenziali

```bash
az acr credential show --name acrerrata --output table
```

**Output esempio:**
```
USERNAME    PASSWORD                          PASSWORD2
----------  --------------------------------  --------------------------------
acrerrata   RLlL/hBWxWsw...                   qlmZVhTUM+l0...
```

**⚠️ SALVA username e password - serviranno per il deployment**

---

## 6. Build delle Immagini Docker

Tutti i comandi vanno eseguiti in **Azure Cloud Shell (Bash)**.

### 6.1 Clone Repository ATIX

```bash
cd ~
git clone https://github.com/ATIX-AG/errata_parser.git
git clone https://github.com/ATIX-AG/errata_server.git
```

### 6.2 Build errata_parser

```bash
az acr build --registry acrerrata --image errata_parser:v1 ./errata_parser
```

### 6.3 Build errata_server

```bash
az acr build --registry acrerrata --image errata_server:v1 ./errata_server
```

### 6.4 Creare e Build errata_backend (Custom)

```bash
mkdir -p ~/errata_backend
```

**requirements.txt:**
```bash
cat > ~/errata_backend/requirements.txt << 'EOF'
Flask==3.0.0
Flask-CORS==4.0.0
gunicorn==21.2.0
psycopg2-binary==2.9.9
redis==5.0.1
requests==2.31.0
urllib3==2.1.0
APScheduler==3.10.4
EOF
```

**Dockerfile:**
```bash
cat > ~/errata_backend/Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
EOF
```

**app.py:**
```bash
cat > ~/errata_backend/app.py << 'ENDOFFILE'
"""
Ubuntu/Debian Errata Management Backend
"""
import os
import logging
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL', '')
ERRATA_SERVER_URL = os.environ.get('ERRATA_SERVER_URL', 'http://localhost:8015')
FOREMAN_URL = os.environ.get('FOREMAN_URL', '')
FOREMAN_USER = os.environ.get('FOREMAN_USER', 'admin')
FOREMAN_PASSWORD = os.environ.get('FOREMAN_PASSWORD', '')
FOREMAN_VERIFY_SSL = os.environ.get('FOREMAN_VERIFY_SSL', 'false').lower() == 'true'

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

@app.route('/api/health', methods=['GET'])
def health():
    status = {'status': 'healthy', 'timestamp': datetime.now().isoformat(), 'services': {}}
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
        status['services']['database'] = 'ok'
    except Exception as e:
        status['services']['database'] = f'error: {str(e)}'
        status['status'] = 'degraded'
    try:
        r = requests.get(f"{ERRATA_SERVER_URL}/dep/api/v1/ubuntu", timeout=5)
        status['services']['errata_server'] = 'ok' if r.status_code == 200 else 'error'
    except Exception as e:
        status['services']['errata_server'] = f'error: {str(e)}'
    return jsonify(status)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM hosts")
            total_hosts = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM errata")
            total_errata = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM host_errata WHERE status = 'applicable'")
            applicable = cur.fetchone()['count']
            cur.execute("""
                SELECT e.severity, COUNT(*) as count 
                FROM host_errata he JOIN errata e ON he.errata_id = e.id 
                WHERE he.status = 'applicable' GROUP BY e.severity
            """)
            by_severity = {row['severity']: row['count'] for row in cur.fetchall()}
    return jsonify({'total_hosts': total_hosts, 'total_errata': total_errata, 'applicable_errata': applicable, 'by_severity': by_severity})

@app.route('/api/hosts', methods=['GET'])
def get_hosts():
    release = request.args.get('release')
    query = """
        SELECT h.*, COUNT(he.id) as total_errata,
            COUNT(CASE WHEN e.severity = 'critical' THEN 1 END) as critical_count,
            COUNT(CASE WHEN e.severity = 'important' THEN 1 END) as important_count,
            COUNT(CASE WHEN e.severity = 'moderate' THEN 1 END) as moderate_count,
            COUNT(CASE WHEN e.severity = 'low' THEN 1 END) as low_count
        FROM hosts h
        LEFT JOIN host_errata he ON h.id = he.host_id AND he.status = 'applicable'
        LEFT JOIN errata e ON he.errata_id = e.id WHERE 1=1
    """
    params = []
    if release:
        query += " AND h.os_release = %s"
        params.append(release)
    query += " GROUP BY h.id ORDER BY critical_count DESC, important_count DESC"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            hosts = cur.fetchall()
    return jsonify({'count': len(hosts), 'hosts': [dict(h) for h in hosts]})

@app.route('/api/hosts/<hostname>', methods=['GET'])
def get_host(hostname):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM hosts WHERE hostname = %s", (hostname,))
            host = cur.fetchone()
            if not host:
                return jsonify({'error': 'Host not found'}), 404
            cur.execute("""
                SELECT e.errata_id, e.title, e.severity, e.issued_date, e.cves,
                       he.package_name, he.installed_version, he.fixed_version
                FROM host_errata he JOIN errata e ON he.errata_id = e.id
                WHERE he.host_id = %s AND he.status = 'applicable'
                ORDER BY CASE e.severity WHEN 'critical' THEN 1 WHEN 'important' THEN 2 WHEN 'moderate' THEN 3 ELSE 4 END
            """, (host['id'],))
            errata = cur.fetchall()
    return jsonify({'host': dict(host), 'errata': [dict(e) for e in errata]})

@app.route('/api/errata', methods=['GET'])
def get_errata():
    severity = request.args.get('severity')
    search = request.args.get('search')
    query = """
        SELECT e.*, (SELECT COUNT(*) FROM host_errata he WHERE he.errata_id = e.id AND he.status = 'applicable') as affected_hosts
        FROM errata e WHERE 1=1
    """
    params = []
    if severity:
        query += " AND e.severity = %s"
        params.append(severity)
    if search:
        query += " AND (e.errata_id ILIKE %s OR e.title ILIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])
    query += " ORDER BY e.issued_date DESC NULLS LAST LIMIT 100"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            errata = cur.fetchall()
    return jsonify({'count': len(errata), 'errata': [dict(e) for e in errata]})

def sync_errata():
    logger.info("Starting errata sync...")
    try:
        for os_type in ['ubuntu', 'debian']:
            try:
                r = requests.get(f"{ERRATA_SERVER_URL}/dep/api/v1/{os_type}", timeout=120)
                if r.status_code != 200:
                    continue
                errata_list = r.json()
                logger.info(f"Fetched {len(errata_list)} {os_type} errata")
                with get_db() as conn:
                    with conn.cursor() as cur:
                        for erratum in errata_list:
                            _upsert_erratum(cur, erratum, os_type)
                    conn.commit()
            except Exception as e:
                logger.warning(f"Failed to fetch {os_type} errata: {e}")
        logger.info("Errata sync completed")
    except Exception as e:
        logger.error(f"Errata sync failed: {e}")

def _upsert_erratum(cur, erratum, os_type):
    errata_id = erratum.get('name', '')
    if not errata_id:
        return
    cves = erratum.get('cves', [])
    if isinstance(cves, str):
        cves = [cves]
    severity = _determine_severity(erratum)
    issued = erratum.get('issued')
    issued_date = None
    if issued:
        try:
            if isinstance(issued, (int, float)):
                issued_date = datetime.fromtimestamp(issued).date()
            elif isinstance(issued, str):
                issued_date = datetime.fromisoformat(issued.replace('Z', '+00:00')).date()
        except:
            issued_date = None
    cur.execute("""
        INSERT INTO errata (errata_id, title, description, severity, os_type, issued_date, cves)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (errata_id) DO UPDATE SET
            title = EXCLUDED.title, severity = EXCLUDED.severity, cves = EXCLUDED.cves, updated_at = CURRENT_TIMESTAMP
    """, (errata_id, erratum.get('title', ''), erratum.get('description', ''), severity, os_type, issued_date, cves))
    cur.execute("SELECT id FROM errata WHERE errata_id = %s", (errata_id,))
    errata_db_id = cur.fetchone()['id']
    for pkg in erratum.get('packages', []):
        cur.execute("""
            INSERT INTO errata_packages (errata_id, package_name, fixed_version, architecture, release)
            VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
        """, (errata_db_id, pkg.get('name', ''), pkg.get('version', ''), pkg.get('architecture', 'amd64'), pkg.get('release', '')))

def _determine_severity(erratum):
    title = (erratum.get('title', '') + erratum.get('description', '')).lower()
    cves = erratum.get('cves', [])
    if any(w in title for w in ['critical', 'remote code execution', 'rce']):
        return 'critical'
    elif any(w in title for w in ['important', 'privilege escalation']):
        return 'important'
    elif any(w in title for w in ['moderate', 'denial of service']):
        return 'moderate'
    elif cves:
        return 'low'
    return 'unknown'

def sync_hosts():
    if not FOREMAN_URL or not FOREMAN_PASSWORD:
        logger.warning("Foreman not configured")
        return
    logger.info("Starting host sync from Foreman...")
    try:
        page = 1
        while True:
            r = requests.get(f"{FOREMAN_URL}/api/hosts", auth=(FOREMAN_USER, FOREMAN_PASSWORD),
                params={'per_page': 100, 'page': page, 'search': 'os_title ~ Ubuntu or os_title ~ Debian'},
                verify=FOREMAN_VERIFY_SSL, timeout=60)
            r.raise_for_status()
            data = r.json()
            hosts = data.get('results', [])
            if not hosts:
                break
            with get_db() as conn:
                with conn.cursor() as cur:
                    for host in hosts:
                        _upsert_host(cur, host)
                conn.commit()
            logger.info(f"Synced page {page} ({len(hosts)} hosts)")
            if len(hosts) < 100:
                break
            page += 1
        logger.info("Host sync completed")
    except Exception as e:
        logger.error(f"Host sync failed: {e}")

def _upsert_host(cur, host):
    os_title = host.get('operatingsystem_name', '')
    release = _extract_release(os_title)
    cur.execute("""
        INSERT INTO hosts (foreman_id, hostname, ip_address, os_title, os_release, organization, hostgroup, last_report)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (foreman_id) DO UPDATE SET
            hostname = EXCLUDED.hostname, ip_address = EXCLUDED.ip_address, os_title = EXCLUDED.os_title,
            os_release = EXCLUDED.os_release, last_report = EXCLUDED.last_report, updated_at = CURRENT_TIMESTAMP
    """, (host.get('id'), host.get('name'), host.get('ip'), os_title, release,
          host.get('organization_name'), host.get('hostgroup_name'), host.get('last_report')))
    _sync_host_packages(cur, host)

def _extract_release(os_title):
    os_lower = os_title.lower()
    releases = {'24.04': 'noble', '22.04': 'jammy', '20.04': 'focal', 'noble': 'noble', 'jammy': 'jammy', 'focal': 'focal',
                'bookworm': 'bookworm', 'bullseye': 'bullseye', 'buster': 'buster'}
    for key, val in releases.items():
        if key in os_lower:
            return val
    return None

def _sync_host_packages(cur, host):
    hostname = host.get('name')
    try:
        r = requests.get(f"{FOREMAN_URL}/api/hosts/{hostname}/packages", auth=(FOREMAN_USER, FOREMAN_PASSWORD),
            params={'per_page': 10000}, verify=FOREMAN_VERIFY_SSL, timeout=120)
        if r.status_code != 200:
            return
        packages = r.json().get('results', [])
        cur.execute("SELECT id FROM hosts WHERE foreman_id = %s", (host.get('id'),))
        row = cur.fetchone()
        if not row:
            return
        host_id = row['id']
        cur.execute("DELETE FROM host_packages WHERE host_id = %s", (host_id,))
        for pkg in packages:
            cur.execute("INSERT INTO host_packages (host_id, package_name, package_version, architecture) VALUES (%s, %s, %s, %s)",
                (host_id, pkg.get('name'), pkg.get('version'), pkg.get('arch', 'amd64')))
    except Exception as e:
        logger.debug(f"Failed to sync packages for {hostname}: {e}")

def correlate_errata():
    logger.info("Starting correlation...")
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, hostname, os_release FROM hosts WHERE os_release IS NOT NULL")
                hosts = cur.fetchall()
                for host in hosts:
                    _correlate_host(cur, host)
                conn.commit()
        logger.info("Correlation completed")
    except Exception as e:
        logger.error(f"Correlation failed: {e}")

def _correlate_host(cur, host):
    host_id = host['id']
    release = host['os_release']
    cur.execute("SELECT package_name, package_version FROM host_packages WHERE host_id = %s", (host_id,))
    installed = {row['package_name']: row['package_version'] for row in cur.fetchall()}
    if not installed:
        return
    cur.execute("""
        SELECT e.id, e.errata_id, ep.package_name, ep.fixed_version
        FROM errata e JOIN errata_packages ep ON e.id = ep.errata_id
        WHERE ep.release = %s OR ep.release LIKE %s
    """, (release, f'{release}%'))
    errata_packages = cur.fetchall()
    cur.execute("DELETE FROM host_errata WHERE host_id = %s", (host_id,))
    for row in errata_packages:
        pkg_name = row['package_name']
        pkg_base = pkg_name.rsplit('-', 1)[0] if '-' in pkg_name else pkg_name
        for inst_name, inst_version in installed.items():
            inst_base = inst_name.rsplit('-', 1)[0] if '-' in inst_name else inst_name
            if pkg_base == inst_base or pkg_name == inst_name:
                cur.execute("""
                    INSERT INTO host_errata (host_id, errata_id, package_name, installed_version, fixed_version, status)
                    VALUES (%s, %s, %s, %s, %s, 'applicable') ON CONFLICT DO NOTHING
                """, (host_id, row['id'], inst_name, inst_version, row['fixed_version']))
                break

@app.route('/api/sync', methods=['POST'])
def trigger_sync():
    sync_type = request.json.get('type', 'all') if request.json else 'all'
    if sync_type in ['all', 'errata']:
        sync_errata()
    if sync_type in ['all', 'hosts']:
        sync_hosts()
    if sync_type in ['all', 'correlate']:
        correlate_errata()
    return jsonify({'status': 'completed', 'type': sync_type})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
ENDOFFILE
```

**Build:**
```bash
az acr build --registry acrerrata --image errata_backend:v2 ./errata_backend
```

---

## 7. Azure Database for PostgreSQL

### 7.1 Creare il Server

```bash
az postgres flexible-server create \
  --resource-group <RESOURCE_GROUP> \
  --name pgserverrata \
  --location italynorth \
  --admin-user errata_admin \
  --admin-password "ErrataDB2024!" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 15 \
  --vnet <VNET_NAME> \
  --subnet DBA \
  --yes
```

**Nota:** Il comando richiede 5-10 minuti.

### 7.2 Verificare il Server

```bash
az postgres flexible-server show \
  --resource-group <RESOURCE_GROUP> \
  --name pgserverrata \
  --output table
```

### 7.3 Creare il Database

```bash
az postgres flexible-server db create \
  --resource-group <RESOURCE_GROUP> \
  --server-name pgserverrata \
  --database-name errata_db
```

### 7.4 Trovare l'IP Privato del PostgreSQL

Il server PostgreSQL usa una Private DNS Zone. Per trovare l'IP:

```bash
az network private-dns record-set a list \
  --resource-group <RESOURCE_GROUP> \
  --zone-name pgserverrata.private.postgres.database.azure.com \
  --output json
```

**L'IP sarà nel campo `ipv4Address`** (es. `10.172.2.196`).

**⚠️ IMPORTANTE:** Usare l'IP diretto nel DATABASE_URL, non il FQDN.

**Perché?** Il PostgreSQL Flexible Server usa una Private DNS Zone (`pgserverrata.private.postgres.database.azure.com`) che non è risolvibile dalla subnet ACI a meno che non sia esplicitamente collegata. Usare l'IP diretto evita problemi di risoluzione DNS.

### 7.5 Informazioni Connessione

| Campo | Valore |
|-------|--------|
| Host (IP) | `10.172.2.196` |
| Port | `5432` |
| Database | `errata_db` |
| User | `errata_admin` |
| Password | `ErrataDB2024!` |
| SSL | `require` |

**Connection String:**
```
postgresql://errata_admin:ErrataDB2024!@10.172.2.196:5432/errata_db?sslmode=require
```

---

## 8. Azure Storage Account

### 8.1 Creare Storage Account

```bash
az storage account create \
  --name sterrata01 \
  --resource-group <RESOURCE_GROUP> \
  --location italynorth \
  --sku Standard_LRS \
  --kind StorageV2
```

### 8.2 Creare File Shares

```bash
# Share per dati errata (JSON)
az storage share create \
  --name errata-data \
  --account-name sterrata01 \
  --quota 5

# Share per Grafana
az storage share create \
  --name errata-grafana \
  --account-name sterrata01 \
  --quota 1
```

### 8.3 Ottenere Storage Key

```bash
az storage account keys list --account-name sterrata01 --query "[0].value" --output tsv
```

**⚠️ SALVA la chiave - servirà per il deployment**

---

## 9. Generazione Dati Errata

### 9.1 Perché dalla Cloud Shell?

I container ACI nella VNet privata non hanno accesso Internet diretto. La Cloud Shell invece ha accesso Internet e può scaricare il database USN.

### 9.2 Scaricare Database USN

```bash
cd ~
curl -o usn-db.json.bz2 https://usn.ubuntu.com/usn-db/database.json.bz2
bunzip2 usn-db.json.bz2
ls -la usn-db.json
```

### 9.3 Creare Script di Processamento

**⚠️ Salvare in `~/clouddrive/` per persistenza:**

```bash
cat > ~/clouddrive/process_usn.py << 'ENDOFFILE'
#!/usr/bin/env python3
import json
import os

RELEASES = ['noble', 'jammy', 'focal']
OUTPUT_DIR = os.path.expanduser('~/errata_output')

def main():
    print("Loading USN database...")
    with open(os.path.expanduser('~/usn-db.json'), 'r') as f:
        usn_db = json.load(f)
    
    print(f"Loaded {len(usn_db)} USN entries")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    errata_list = []
    
    for usn_id, usn_data in usn_db.items():
        if not usn_id.startswith('USN-'):
            usn_id = f"USN-{usn_id}"
        
        packages = []
        
        if 'releases' in usn_data:
            for release_name, release_data in usn_data['releases'].items():
                release_base = release_name.split('-')[0].lower()
                if release_base not in RELEASES:
                    continue
                
                if 'sources' in release_data:
                    for pkg_name, pkg_data in release_data['sources'].items():
                        packages.append({
                            'name': pkg_name,
                            'version': pkg_data.get('version', ''),
                            'release': release_base,
                            'component': pkg_data.get('component', 'main'),
                            'architecture': 'all'
                        })
                
                if 'binaries' in release_data:
                    for pkg_name, pkg_data in release_data['binaries'].items():
                        packages.append({
                            'name': pkg_name,
                            'version': pkg_data.get('version', ''),
                            'release': release_base,
                            'component': pkg_data.get('component', 'main'),
                            'architecture': 'amd64'
                        })
        
        if not packages:
            continue
        
        cves = usn_data.get('cves', [])
        if isinstance(cves, dict):
            cves = list(cves.keys())
        
        erratum = {
            'name': usn_id,
            'title': usn_data.get('title', usn_data.get('description', '')[:200] if usn_data.get('description') else ''),
            'description': usn_data.get('description', ''),
            'issued': usn_data.get('timestamp'),
            'cves': cves,
            'packages': packages
        }
        
        errata_list.append(erratum)
    
    print(f"Processed {len(errata_list)} relevant USN entries")
    
    # File must be named ubuntu_errata.json for errata_server
    ubuntu_output = os.path.join(OUTPUT_DIR, 'ubuntu_errata.json')
    with open(ubuntu_output, 'w') as f:
        json.dump(errata_list, f)
    print(f"Written {ubuntu_output}")
    
    # Empty debian errata
    debian_output = os.path.join(OUTPUT_DIR, 'debian_errata.json')
    with open(debian_output, 'w') as f:
        json.dump([], f)
    print(f"Written {debian_output}")

if __name__ == '__main__':
    main()
ENDOFFILE
```

### 9.4 Eseguire lo Script

```bash
python3 ~/clouddrive/process_usn.py
```

**Output atteso:**
```
Loading USN database...
Loaded 6795 USN entries
Processed 3328 relevant USN entries
Written /home/<user>/errata_output/ubuntu_errata.json
Written /home/<user>/errata_output/debian_errata.json
```

### 9.5 Creare File di Configurazione per errata_server

**⚠️ IMPORTANTE:** Il formato di questi file è specifico e deve essere esatto.

**ubuntu_config.json:**
```bash
cat > ~/errata_output/ubuntu_config.json << 'EOF'
{
  "releases": {
    "noble": {
      "aliases": ["noble-security", "noble-updates"],
      "components": ["main", "restricted", "universe", "multiverse"],
      "architectures": ["amd64", "all"]
    },
    "jammy": {
      "aliases": ["jammy-security", "jammy-updates"],
      "components": ["main", "restricted", "universe", "multiverse"],
      "architectures": ["amd64", "all"]
    },
    "focal": {
      "aliases": ["focal-security", "focal-updates"],
      "components": ["main", "restricted", "universe", "multiverse"],
      "architectures": ["amd64", "all"]
    }
  }
}
EOF
```

**debian_config.json:**
```bash
cat > ~/errata_output/debian_config.json << 'EOF'
{
  "releases": {
    "bookworm": {
      "aliases": ["bookworm-security"],
      "components": ["main", "contrib", "non-free"],
      "architectures": ["amd64", "all"]
    },
    "bullseye": {
      "aliases": ["bullseye-security"],
      "components": ["main", "contrib", "non-free"],
      "architectures": ["amd64", "all"]
    }
  }
}
EOF
```

### 9.6 Caricare File su Azure Storage

```bash
# Errata JSON
az storage file upload --account-name sterrata01 --share-name errata-data \
  --source ~/errata_output/ubuntu_errata.json --path ubuntu_errata.json

az storage file upload --account-name sterrata01 --share-name errata-data \
  --source ~/errata_output/debian_errata.json --path debian_errata.json

# Config JSON
az storage file upload --account-name sterrata01 --share-name errata-data \
  --source ~/errata_output/ubuntu_config.json --path ubuntu_config.json

az storage file upload --account-name sterrata01 --share-name errata-data \
  --source ~/errata_output/debian_config.json --path debian_config.json
```

---

## 10. Deploy Container Group (ACI)

### 10.1 Creare File YAML

**⚠️ Salvare in `~/clouddrive/` per persistenza:**

```bash
cat > ~/clouddrive/aci-errata.yaml << 'EOF'
apiVersion: 2021-09-01
location: italynorth
name: errata-management
properties:
  containers:
  - name: errata-server
    properties:
      image: acrerrata.azurecr.io/errata_server:v1
      ports:
      - port: 8015
      environmentVariables:
      - name: TZ
        value: Europe/Rome
      resources:
        requests:
          cpu: 0.25
          memoryInGb: 0.5
      volumeMounts:
      - name: errata-data
        mountPath: /srv/errata

  - name: backend
    properties:
      image: acrerrata.azurecr.io/errata_backend:v2
      ports:
      - port: 5000
      environmentVariables:
      - name: DATABASE_URL
        value: "postgresql://errata_admin:ErrataDB2024!@10.172.2.196:5432/errata_db?sslmode=require"
      - name: ERRATA_SERVER_URL
        value: "http://localhost:8015"
      - name: FOREMAN_URL
        value: "https://10.172.2.17"
      - name: FOREMAN_USER
        value: "admin"
      - name: FOREMAN_PASSWORD
        secureValue: "<PASSWORD_FOREMAN>"
      - name: FOREMAN_VERIFY_SSL
        value: "false"
      resources:
        requests:
          cpu: 0.5
          memoryInGb: 1

  - name: grafana
    properties:
      image: grafana/grafana:10.2.0
      ports:
      - port: 3000
      environmentVariables:
      - name: GF_SECURITY_ADMIN_USER
        value: admin
      - name: GF_SECURITY_ADMIN_PASSWORD
        secureValue: "GrafanaAdmin2024!"
      - name: GF_USERS_ALLOW_SIGN_UP
        value: "false"
      resources:
        requests:
          cpu: 0.25
          memoryInGb: 0.5
      volumeMounts:
      - name: grafana-data
        mountPath: /var/lib/grafana

  imageRegistryCredentials:
  - server: acrerrata.azurecr.io
    username: acrerrata
    password: "<PASSWORD_ACR>"

  osType: Linux
  restartPolicy: Always
  
  ipAddress:
    type: Private
    ports:
    - port: 5000
    - port: 3000
    - port: 8015

  subnetIds:
  - id: /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.Network/virtualNetworks/<VNET_NAME>/subnets/errata-aci-subnet

  volumes:
  - name: errata-data
    azureFile:
      shareName: errata-data
      storageAccountName: sterrata01
      storageAccountKey: "<STORAGE_KEY>"
  - name: grafana-data
    azureFile:
      shareName: errata-grafana
      storageAccountName: sterrata01
      storageAccountKey: "<STORAGE_KEY>"

tags:
  environment: production
  application: errata-management
type: Microsoft.ContainerInstance/containerGroups
EOF
```

### 10.2 Sostituire Placeholder

| Placeholder | Descrizione |
|-------------|-------------|
| `<SUBSCRIPTION_ID>` | ID subscription Azure |
| `<RESOURCE_GROUP>` | Nome resource group |
| `<VNET_NAME>` | Nome VNet |
| `<PASSWORD_FOREMAN>` | Password utente Foreman |
| `<PASSWORD_ACR>` | Password ACR |
| `<STORAGE_KEY>` | Chiave storage account |

### 10.3 Deploy

```bash
az container create \
  --resource-group <RESOURCE_GROUP> \
  --file ~/clouddrive/aci-errata.yaml
```

### 10.4 Verificare Deployment

```bash
az container show \
  --resource-group <RESOURCE_GROUP> \
  --name errata-management \
  --output table
```

**Output atteso:** Status = `Running`, IP = `10.172.5.4`

### 10.5 Verificare Log errata_server

```bash
az container logs \
  --resource-group <RESOURCE_GROUP> \
  --name errata-management \
  --container-name errata-server
```

**Output atteso (senza errori):**
```
Log opened.
Site starting on 8015
Reading config for operatingsystem debian
Reading config for operatingsystem ubuntu
Found releases: {'noble', 'jammy', 'focal'}
...
Parsing data for operatingsystem ubuntu
Pivoting data for operatingsystem ubuntu
Hash of new data: ...
```

---

## 11. Inizializzazione Database

### 11.1 Connettersi a PostgreSQL

Dalla VM Foreman (o altra VM nella VNet):

```bash
psql "host=10.172.2.196 port=5432 dbname=errata_db user=errata_admin password=ErrataDB2024! sslmode=require"
```

### 11.2 Creare le Tabelle

```sql
CREATE TABLE IF NOT EXISTS hosts (
    id SERIAL PRIMARY KEY,
    foreman_id INTEGER UNIQUE,
    hostname VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45),
    os_title VARCHAR(255),
    os_release VARCHAR(50),
    organization VARCHAR(255),
    hostgroup VARCHAR(255),
    last_report TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS host_packages (
    id SERIAL PRIMARY KEY,
    host_id INTEGER REFERENCES hosts(id) ON DELETE CASCADE,
    package_name VARCHAR(255),
    package_version VARCHAR(100),
    architecture VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS errata (
    id SERIAL PRIMARY KEY,
    errata_id VARCHAR(50) UNIQUE NOT NULL,
    title VARCHAR(500),
    description TEXT,
    severity VARCHAR(20),
    os_type VARCHAR(20),
    issued_date DATE,
    cves TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS errata_packages (
    id SERIAL PRIMARY KEY,
    errata_id INTEGER REFERENCES errata(id) ON DELETE CASCADE,
    package_name VARCHAR(255),
    fixed_version VARCHAR(100),
    architecture VARCHAR(20),
    release VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS host_errata (
    id SERIAL PRIMARY KEY,
    host_id INTEGER REFERENCES hosts(id) ON DELETE CASCADE,
    errata_id INTEGER REFERENCES errata(id) ON DELETE CASCADE,
    package_name VARCHAR(255),
    installed_version VARCHAR(100),
    fixed_version VARCHAR(100),
    status VARCHAR(20) DEFAULT 'applicable',
    UNIQUE(host_id, errata_id, package_name)
);

CREATE INDEX IF NOT EXISTS idx_host_packages_host_id ON host_packages(host_id);
CREATE INDEX IF NOT EXISTS idx_host_packages_name ON host_packages(package_name);
CREATE INDEX IF NOT EXISTS idx_errata_packages_errata_id ON errata_packages(errata_id);
CREATE INDEX IF NOT EXISTS idx_errata_packages_name ON errata_packages(package_name);
CREATE INDEX IF NOT EXISTS idx_host_errata_host_id ON host_errata(host_id);
CREATE INDEX IF NOT EXISTS idx_host_errata_errata_id ON host_errata(errata_id);
```

Esci con `\q`.

---

## 12. Test e Verifica

### 12.1 Test Health Check

Dalla VM Foreman:

```bash
curl http://10.172.5.4:5000/api/health
```

**Output atteso:**
```json
{
  "services": {
    "database": "ok",
    "errata_server": "ok"
  },
  "status": "healthy",
  "timestamp": "2024-12-10T..."
}
```

### 12.2 Trigger Sync Iniziale

```bash
curl -X POST http://10.172.5.4:5000/api/sync \
  -H "Content-Type: application/json" \
  -d '{"type": "all"}'
```

**Output atteso:**
```json
{"status":"completed","type":"all"}
```

### 12.3 Verificare Statistiche

```bash
curl http://10.172.5.4:5000/api/stats
```

**Output atteso:**
```json
{
  "total_hosts": 2,
  "total_errata": 3328,
  "applicable_errata": 0,
  "by_severity": {}
}
```

**Nota:** `applicable_errata` sarà 0 se gli host non hanno inviato i pacchetti a Foreman.

### 12.4 Verificare Host

```bash
curl http://10.172.5.4:5000/api/hosts
```

### 12.5 Verificare Errata nel Database

```bash
psql "host=10.172.2.196 port=5432 dbname=errata_db user=errata_admin password=ErrataDB2024! sslmode=require" \
  -c "SELECT release, COUNT(*) FROM errata_packages GROUP BY release;"
```

**Output atteso:**
```
 release | count 
---------+-------
 focal   | 28066
 jammy   | 23146
 noble   |  9100
```

---

## 13. Configurazione Grafana

### 13.1 Accesso

Da browser (tramite VM nella VNet o VPN):

- URL: `http://10.172.5.4:3000`
- User: `admin`
- Password: `GrafanaAdmin2024!`

### 13.2 Configurare Datasource PostgreSQL

1. **Configuration** → **Data Sources** → **Add data source**
2. Seleziona **PostgreSQL**
3. Configura:

| Campo | Valore |
|-------|--------|
| Host | `10.172.2.196:5432` |
| Database | `errata_db` |
| User | `errata_admin` |
| Password | `ErrataDB2024!` |
| TLS/SSL Mode | `require` |

4. **Save & Test**

### 13.3 Query per Dashboard

**Statistiche generali:**
```sql
SELECT 
  (SELECT COUNT(*) FROM hosts) as total_hosts,
  (SELECT COUNT(*) FROM errata) as total_errata,
  (SELECT COUNT(*) FROM host_errata WHERE status = 'applicable') as applicable_errata
```

**Errata per release:**
```sql
SELECT release, COUNT(*) as count 
FROM errata_packages 
GROUP BY release 
ORDER BY count DESC
```

**Host con più errata:**
```sql
SELECT h.hostname, h.os_release, COUNT(he.id) as errata_count
FROM hosts h
LEFT JOIN host_errata he ON h.id = he.host_id AND he.status = 'applicable'
GROUP BY h.id
ORDER BY errata_count DESC
LIMIT 10
```

**Errata per severity:**
```sql
SELECT severity, COUNT(*) as count
FROM errata
GROUP BY severity
ORDER BY count DESC
```

---

## 14. Registrazione Host in Foreman

### 14.1 Prerequisito

Per vedere gli errata applicabili, gli host Ubuntu/Debian devono:
1. Essere registrati come **Content Host** in Katello
2. Aver inviato l'**inventario pacchetti** a Foreman

### 14.2 Su ogni VM Ubuntu

```bash
# Installa katello-host-tools (se non già installato)
sudo apt-get update
sudo apt-get install katello-host-tools

# Invia inventario pacchetti
sudo katello-package-upload
```

### 14.3 Verificare in Foreman

```bash
curl -k -u admin:<password> "https://<foreman>/api/hosts/<hostname>/packages"
```

### 14.4 Rieseguire Sync

Dopo che gli host hanno inviato i pacchetti:

```bash
curl -X POST http://10.172.5.4:5000/api/sync \
  -H "Content-Type: application/json" \
  -d '{"type": "all"}'
```

---

## 15. Gestione e Manutenzione

### 15.1 Comandi ACI

```bash
# Stato
az container show --resource-group <RG> --name errata-management --output table

# Log backend
az container logs --resource-group <RG> --name errata-management --container-name backend

# Log errata-server
az container logs --resource-group <RG> --name errata-management --container-name errata-server

# Restart
az container restart --resource-group <RG> --name errata-management

# Stop (⚠️ ACI continua a costare)
az container stop --resource-group <RG> --name errata-management

# Start
az container start --resource-group <RG> --name errata-management

# Delete
az container delete --resource-group <RG> --name errata-management --yes
```

### 15.2 Comandi PostgreSQL

```bash
# Stop
az postgres flexible-server stop --resource-group <RG> --name pgserverrata

# Start
az postgres flexible-server start --resource-group <RG> --name pgserverrata
```

### 15.3 Aggiornare Errata (Settimanale)

Dalla Cloud Shell:

```bash
# Scarica nuovi USN
cd ~
curl -o usn-db.json.bz2 https://usn.ubuntu.com/usn-db/database.json.bz2
bunzip2 -f usn-db.json.bz2

# Rigenera JSON
python3 ~/clouddrive/process_usn.py

# Carica su storage
az storage file upload --account-name sterrata01 --share-name errata-data \
  --source ~/errata_output/ubuntu_errata.json --path ubuntu_errata.json

# Restart errata-server per ricaricare
az container restart --resource-group <RG> --name errata-management

# Trigger sync
curl -X POST http://10.172.5.4:5000/api/sync \
  -H "Content-Type: application/json" \
  -d '{"type": "errata"}'
```

### 15.4 Script Stop Completo (risparmio costi)

```bash
#!/bin/bash
RG="<RESOURCE_GROUP>"

echo "Stopping Errata Management System..."
az container delete --resource-group $RG --name errata-management --yes
az postgres flexible-server stop --resource-group $RG --name pgserverrata
echo "Done."
```

### 15.5 Script Start Completo

**⚠️ Prerequisito:** Il file `aci-errata.yaml` deve essere salvato in `~/clouddrive/` per persistere tra sessioni Cloud Shell.

```bash
#!/bin/bash
RG="<RESOURCE_GROUP>"

echo "Starting Errata Management System..."
az postgres flexible-server start --resource-group $RG --name pgserverrata
sleep 60  # Attendi PostgreSQL
az container create --resource-group $RG --file ~/clouddrive/aci-errata.yaml
echo "Done."
```

---

## 16. Troubleshooting

### 16.1 Subscription Sbagliata

```
Resource group 'xxx' could not be found
```

**Soluzione:**
```bash
az account set --subscription "<SUBSCRIPTION_ID>"
```

### 16.2 errata_server Errore Config

```
'releases' must be a dict
releases-value must be a dict
```

**Causa:** Formato config.json errato.

**Soluzione:** Usare il formato esatto della sezione 9.5.

### 16.3 Backend Non Connette a Database

```
relation "hosts" does not exist
```

**Causa:** Tabelle non create.

**Soluzione:** Eseguire SQL della sezione 11.2.

### 16.4 applicable_errata = 0

**Causa:** Gli host non hanno inviato i pacchetti a Foreman.

**Verifica:**
```bash
curl -k -u admin:<password> "https://<foreman>/api/hosts/<hostname>/packages"
```

Se `results` è vuoto, l'host non ha inviato i pacchetti.

**Soluzione:** Sezione 14.

### 16.5 Container Non Raggiunge Internet

I container nella subnet privata non hanno accesso Internet. Usare la Cloud Shell per scaricare dati.

### 16.6 PostgreSQL Non Raggiungibile

**Causa:** DNS privato non configurato.

**Soluzione:** Usare l'IP diretto (trovato in sezione 7.4).

### 16.7 Parser ATIX Fallisce (se tentato in ACI)

**Errore 1 - No Internet:**
```
Net::OpenTimeout - Failed to open TCP connection to usn.ubuntu.com:443
```
**Causa:** I container ACI nella VNet privata non hanno accesso Internet.
**Soluzione:** Usare Cloud Shell per generare i dati (sezione 9).

**Errore 2 - Memory Killed:**
```
Killed
```
**Causa:** Il parser richiede molta RAM (>2GB).
**Soluzione:** Se si tenta di usare il parser, allocare almeno 4GB di RAM.

**Errore 3 - ubuntu-esm non configurato:**
```
undefined method `key?' for nil (NoMethodError) - config.key? 'whitelists'
```
**Causa:** Il parser cerca la sezione `ubuntu-esm` nel config.
**Soluzione:** Aggiungere la sezione `ubuntu-esm` nel config oppure usare lo script Python alternativo (sezione 9).

**Errore 4 - Release obsolete (404):**
```
404 "Not Found" - debRelease.rb
```
**Causa:** Il default_config.json contiene release obsolete (stretch, jessie) che non esistono più.
**Soluzione:** Usare solo release supportate: noble, jammy, focal, bookworm, bullseye.

### 16.8 Backend Errore Timestamp

**Errore:**
```
column "issued_date" is of type date but expression is of type numeric
```
**Causa:** Il database USN usa timestamp Unix (numeri), ma la colonna è DATE.
**Soluzione:** Il backend v2 converte automaticamente. Assicurarsi di usare `errata_backend:v2`.

### 16.9 errata_server Non Carica i Dati

**Errori comuni:**
```
'releases' must be a dict
releases-value must be a dict
```

**Causa:** Il formato del file `*_config.json` è errato.

**Formato CORRETTO:**
```json
{
  "releases": {
    "noble": {
      "aliases": ["noble-security", "noble-updates"],
      "components": ["main", "restricted", "universe", "multiverse"],
      "architectures": ["amd64", "all"]
    }
  }
}
```

**Formato ERRATO (lista invece di dict):**
```json
{
  "releases": ["noble", "jammy"]
}
```

**Formato ERRATO (manca la struttura interna):**
```json
{
  "releases": {
    "noble": ["noble-security"]
  }
}
```

### 16.10 File Errata Non Trovati

**Errore:**
```
No such file or directory: '/srv/errata/ubuntu_errata.json'
```

**Causa:** I file non sono stati caricati su Azure File Share o hanno nomi sbagliati.

**Nomi file corretti:**
- `ubuntu_errata.json` (NON `ubuntu.json`)
- `ubuntu_config.json`
- `debian_errata.json`
- `debian_config.json`

---

## 17. Costi e Ottimizzazione

### 17.1 Stima Costi Mensili (Always On)

| Risorsa | SKU | Costo/Mese |
|---------|-----|------------|
| ACI | 1 vCPU, 2.5GB RAM | ~€40-50 |
| PostgreSQL | Standard_B1ms | ~€12-15 |
| Storage | Standard LRS, ~10GB | ~€1-2 |
| ACR | Basic | ~€5 |
| **TOTALE** | | **~€60-70** |

### 17.2 Costi con Sistema Spento

| Risorsa | Costo/Mese |
|---------|------------|
| Storage | ~€1-2 |
| ACR | ~€5 |
| **TOTALE** | **~€6-7** |

### 17.3 Ottimizzazione

- **ACI:** Non ha vero "stop" - eliminare e ricreare quando serve
- **PostgreSQL:** Stop riduce costi ma non li azzera
- **Per test/lab:** Eliminare tutto tranne storage e ACR quando non in uso

---

## 18. Limitazioni Note

### 18.1 Parser ATIX Non Utilizzabile Direttamente

Il parser ATIX (`errata_parser`) non può essere eseguito nei container ACI nella VNet privata perché:
- Richiede accesso Internet per scaricare USN/DSA
- Richiede molta RAM (>4GB per processare tutti i dati)
- La VNet privata non ha NAT gateway configurato

**Workaround:** Generare i dati dalla Cloud Shell con lo script Python.

### 18.2 Correlazione Errata Limitata

La correlazione tra errata e host funziona solo se:
- Gli host sono registrati come Content Host in Katello
- Gli host hanno inviato l'inventario pacchetti a Foreman
- Il nome del pacchetto installato corrisponde (anche parzialmente) al nome nel database errata

### 18.3 Severity Approssimativa

La severity degli errata viene determinata euristicamente cercando parole chiave nel titolo/descrizione:
- "critical", "remote code execution" → Critical
- "important", "privilege escalation" → Important
- "moderate", "denial of service" → Moderate
- Presenza di CVE → Low
- Altro → Unknown

Non è una valutazione CVSS precisa.

### 18.4 Solo Ubuntu Supportato Completamente

Attualmente solo Ubuntu è completamente supportato:
- ✅ Ubuntu: noble, jammy, focal
- ⚠️ Debian: struttura pronta ma dati errata vuoti (lo script processa solo USN)

Per aggiungere Debian, occorrerebbe estendere lo script Python per scaricare e processare DSA/DLA.

### 18.5 Aggiornamento Manuale

Gli errata non si aggiornano automaticamente. È necessario:
1. Rieseguire lo script dalla Cloud Shell
2. Caricare i nuovi JSON su Azure Storage
3. Riavviare i container
4. Trigger sync

Si consiglia di schedulare questo processo settimanalmente.

---

## Appendice A: Valori Configurazione Attuale

| Parametro | Valore |
|-----------|--------|
| Subscription ID | `896dd1f5-30ae-42db-a7d4-c0f8184c6b1c` |
| Resource Group | `ASL0603-spoke10-rg-spoke-italynorth` |
| VNet | `ASL0603-spoke10-spoke-italynorth` |
| Subnet ACI | `errata-aci-subnet` (10.172.5.0/28) |
| Subnet DBA | `DBA` |
| ACR | `acrerrata.azurecr.io` |
| Storage Account | `sterrata01` |
| PostgreSQL Server | `pgserverrata` |
| PostgreSQL IP | `10.172.2.196` |
| Container Group IP | `10.172.5.4` |
| Foreman IP | `10.172.2.17` |

---

## Appendice B: API Reference

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/stats` | GET | Statistiche generali |
| `/api/hosts` | GET | Lista host |
| `/api/hosts?release=noble` | GET | Filtra per release |
| `/api/hosts/<hostname>` | GET | Dettaglio host con errata |
| `/api/errata` | GET | Lista errata |
| `/api/errata?severity=critical` | GET | Filtra per severity |
| `/api/errata?search=CVE-2024` | GET | Cerca errata |
| `/api/sync` | POST | Trigger sync (`{"type": "all"}`) |

---

## Appendice C: Credenziali (⚠️ CAMBIARE IN PRODUZIONE)

| Servizio | Username | Password |
|----------|----------|----------|
| PostgreSQL | `errata_admin` | `ErrataDB2024!` |
| Grafana | `admin` | `GrafanaAdmin2024!` |
| Foreman | `admin` | (la tua) |
| ACR | `acrerrata` | (da `az acr credential show`) |

**⚠️ In produzione usare Azure Key Vault per gestire i secrets.**

---

## Appendice D: File Necessari su Azure File Share

| File | Descrizione |
|------|-------------|
| `ubuntu_config.json` | Config release Ubuntu |
| `debian_config.json` | Config release Debian |
| `ubuntu_errata.json` | Dati errata Ubuntu |
| `debian_errata.json` | Dati errata Debian |

---

*Documento generato: Dicembre 2024 - Versione 2.0*
