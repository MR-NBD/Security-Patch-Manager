## Ubuntu/Debian Errata Management System per Foreman/Katello
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

---
## 1. Panoramica e Obiettivi

### 1.1 Il Problema

Foreman/Katello gestisce VM Ubuntu e Debian mostrando i **pacchetti installati** e **installabili**. Tuttavia, manca il concetto di **errata** (security advisories):

- Ubuntu pubblica **USN** (Ubuntu Security Notices)
- Debian pubblica **DSA/DLA** (Debian Security Advisory / Debian LTS Advisory)

Questi non sono integrati nativamente in Katello community edition.
### 1.2 La Soluzione

Sistema esterno composto da:
1. **errata_parser** (ATIX) - Scarica USN/DSA dai repository ufficiali
2. **errata_server** (ATIX) - API REST per consultare errata
3. **errata_backend** (custom) - Correla errata con host Foreman, salva in PostgreSQL, gestisce storico
4. **Grafana** - Dashboard per visualizzazione
### 1.3 Componenti Deployati

| Componente | Tecnologia | Porta | Funzione |
|------------|------------|-------|----------|
| errata_server | Python/Twisted | 8015 | API REST errata |
| errata_backend | Python/Flask v3 | 5000 | Correlazione, sync e storico |
| Grafana | Grafana 10.2 | 3000 | Dashboard |
| PostgreSQL | Azure Flexible | 5432 | Database |

---
## 2. Architettura
### 2.1 Schema Generale

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AZURE - Italy North                            │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │           VNet: ASL0603-spoke10-spoke-italynorth                    │    │
│  │                                                                     │    │
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
│  │                                                                     │    │
│  │   ┌─────────────────────┐      ┌─────────────────────────────────┐  │    │
│  │   │  Subnet: DBA        │      │  Azure Storage Account          │  │    │
│  │   │  10.172.2.192/26    │      │  sterrata01                     │  │    │
│  │   │                     │      │                                 │  │    │
│  │   │  ┌───────────────┐  │      │  File Shares:                   │  │    │
│  │   │  │  PostgreSQL   │  │      │  • errata-data (JSON errata)    │  │    │
│  │   │  │  Flexible     │◄─┼──────┼──• errata-grafana (Grafana)     │  │    │
│  │   │  │  Server       │  │      │                                 │  │    │
│  │   │  │               │  │      └─────────────────────────────────┘  │    │
│  │   │  │  pgserverrata │  │                                           │    │
│  │   │  │  10.172.2.196 │  │                                           │    │
│  │   │  └───────────────┘  │                                           │    │
│  │   └─────────────────────┘                                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌──────────────────────────┐                                               │
│  │  Azure Container Registry│                                               │
│  │  acrerrata.azurecr.io    │                                               │
│  │                          │                                               │
│  │  Images:                 │                                               │
│  │  • errata_parser:v1      │                                               │
│  │  • errata_server:v1      │                                               │
│  │  • errata_backend:v3     │                                               │
│  └──────────────────────────┘                                               │
└─────────────────────────────────────────────────────────────────────────────┘
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
│  /api/hosts     │────►│  (Flask v3)     │◄────│  (legge JSON)   │
│  /api/packages  │     │                 │     │                 │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                │
                                ▼
                        ┌─────────────────┐
                        │   PostgreSQL    │
                        │   (correlazioni │
                        │    + storico)   │
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

**IMPORTANTE - Cloud Shell Effimera:**
La Cloud Shell di Azure è effimera: i file nella home directory (`~`) vengono persi dopo 20 minuti di inattività o dopo il riavvio della sessione. Solo la directory `~/clouddrive` è persistente (collegata a un Azure File Share).

**Consiglio:** Salvare i file importanti (YAML, script) in `~/clouddrive` oppure su un repository Git.
### 3.2 Foreman/Katello
- Foreman/Katello installato e funzionante
- Host Ubuntu/Debian registrati come Content Host
- Credenziali API (utente con permessi di lettura)
- **IMPORTANTE**: Gli host devono aver inviato l'inventario pacchetti a Foreman
### 3.3 Informazioni da Raccogliere

| Informazione     | Esempio                                |
| ---------------- | -------------------------------------- |
| Subscription ID  | `896dd1f5-30ae-42db-a7d4-c0f8184c6b1c` |
| Resource Group   | `ASL0603-spoke10-rg-spoke-italynorth`  |
| VNet Name        | `ASL0603-spoke10-spoke-italynorth`     |
| Location         | `italynorth`                           |
| IP Foreman       | `10.172.2.17`                          |
| User Foreman     | `admin`                                |
| Password Foreman | `***`                                  |

---
## 4. Configurazione Rete Azure

### 4.1 Selezionare la Subscription Corretta
#### Lista subscription disponibili
```bash
az account list --output table
```
#### Seleziona la subscription corretta
```bash
az account set --subscription "<SUBSCRIPTION_ID>"
```
#### Verifica
```bash
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
| Registry name | `acrerrata` |
| Resource group | (il tuo) |
| Location | `Italy North` |
| SKU | `Basic` (~5€/mese) |

3. **Review + create** → **Create**
**CLI:**
```bash
az acr create \
  --resource-group <RESOURCE_GROUP> \
  --name acrerrata \
  --sku Basic \
  --location italynorth \
  --admin-enabled true
```
### 5.2 Ottenere Credenziali
```bash
az acr credential show --name acrerrata --output table
```

Salva username e password per il deployment ACI.

---
## 6. Build delle Immagini Docker
### 6.1 errata_parser (Ruby)
```bash
az acr build --registry acrerrata --image errata_parser:v1 https://github.com/ATIX-AG/errata_parser.git
```
### 6.2 errata_server (Python)
```bash
az acr build --registry acrerrata --image errata_server:v1 https://github.com/ATIX-AG/errata_server.git
```
### 6.3 errata_backend v3 (Flask - Custom)
Crea la directory:
```bash
mkdir -p ~/clouddrive/errata_backend
cd ~/clouddrive/errata_backend
```

**app.py:**
```bash
cat > app.py << 'ENDOFFILE'
from flask import Flask, jsonify, request
import psycopg2
import psycopg2.extras
import requests
import os
from datetime import datetime, date

app = Flask(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL')
ERRATA_SERVER_URL = os.environ.get('ERRATA_SERVER_URL', 'http://localhost:8015')
FOREMAN_URL = os.environ.get('FOREMAN_URL')
FOREMAN_USER = os.environ.get('FOREMAN_USER')
FOREMAN_PASSWORD = os.environ.get('FOREMAN_PASSWORD')
FOREMAN_VERIFY_SSL = os.environ.get('FOREMAN_VERIFY_SSL', 'true').lower() == 'true'

def get_db():
    return psycopg2.connect(DATABASE_URL)

def determine_severity(erratum):
    title = (erratum.get('title') or '').lower()
    desc = (erratum.get('description') or '').lower()
    text = title + ' ' + desc
    if any(w in text for w in ['critical', 'remote code execution', 'rce', 'arbitrary code']):
        return 'critical'
    if any(w in text for w in ['important', 'privilege escalation', 'authentication bypass']):
        return 'important'
    if any(w in text for w in ['moderate', 'denial of service', 'dos', 'memory leak']):
        return 'moderate'
    if erratum.get('cves'):
        return 'low'
    return 'unknown'

@app.route('/api/health')
def health():
    status = {'status': 'healthy', 'services': {}, 'timestamp': datetime.utcnow().isoformat()}
    try:
        conn = get_db()
        conn.close()
        status['services']['database'] = 'ok'
    except:
        status['services']['database'] = 'error'
        status['status'] = 'unhealthy'
    try:
        r = requests.get(f"{ERRATA_SERVER_URL}/errata/ubuntu", timeout=5)
        status['services']['errata_server'] = 'ok' if r.status_code == 200 else 'error'
    except:
        status['services']['errata_server'] = 'error'
    return jsonify(status)

@app.route('/api/stats')
def stats():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as count FROM hosts")
    total_hosts = cur.fetchone()['count']
    cur.execute("SELECT COUNT(*) as count FROM errata")
    total_errata = cur.fetchone()['count']
    cur.execute("""
        SELECT e.severity, COUNT(*) as count 
        FROM host_errata he JOIN errata e ON he.errata_id = e.id 
        GROUP BY e.severity
    """)
    by_severity = {row['severity']: row['count'] for row in cur.fetchall()}
    cur.execute("SELECT COUNT(*) as count FROM host_errata")
    applicable = cur.fetchone()['count']
    conn.close()
    return jsonify({
        'total_hosts': total_hosts,
        'total_errata': total_errata,
        'applicable_errata': applicable,
        'by_severity': by_severity
    })

@app.route('/api/hosts')
def list_hosts():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    release = request.args.get('release')
    if release:
        cur.execute("SELECT * FROM hosts WHERE os_release = %s", (release,))
    else:
        cur.execute("SELECT * FROM hosts")
    hosts = cur.fetchall()
    conn.close()
    return jsonify({'hosts': hosts, 'total': len(hosts)})

@app.route('/api/hosts/<hostname>')
def get_host(hostname):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM hosts WHERE hostname = %s", (hostname,))
    host = cur.fetchone()
    if not host:
        conn.close()
        return jsonify({'error': 'Host not found'}), 404
    cur.execute("""
        SELECT he.*, e.errata_id, e.title, e.severity, e.cves, e.issued_date
        FROM host_errata he
        JOIN errata e ON he.errata_id = e.id
        WHERE he.host_id = %s
        ORDER BY e.severity, e.issued_date DESC
    """, (host['id'],))
    errata = cur.fetchall()
    conn.close()
    return jsonify({'host': host, 'errata': errata, 'errata_count': len(errata)})

@app.route('/api/errata')
def list_errata():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    severity = request.args.get('severity')
    search = request.args.get('search')
    query = "SELECT * FROM errata WHERE 1=1"
    params = []
    if severity:
        query += " AND severity = %s"
        params.append(severity)
    if search:
        query += " AND (errata_id ILIKE %s OR title ILIKE %s OR %s = ANY(cves))"
        params.extend([f'%{search}%', f'%{search}%', search])
    query += " ORDER BY issued_date DESC NULLS LAST LIMIT 100"
    cur.execute(query, params)
    errata = cur.fetchall()
    conn.close()
    return jsonify({'errata': errata, 'total': len(errata)})

def sync_errata():
    conn = get_db()
    cur = conn.cursor()
    for os_type in ['ubuntu', 'debian']:
        try:
            r = requests.get(f"{ERRATA_SERVER_URL}/errata/{os_type}", timeout=30)
            if r.status_code != 200:
                continue
            errata_list = r.json()
            for erratum in errata_list:
                errata_id = erratum.get('name') or erratum.get('id')
                title = erratum.get('title', '')[:500]
                description = erratum.get('description', '')
                severity = determine_severity(erratum)
                cves = erratum.get('cves', [])
                issued = erratum.get('issued')
                if isinstance(issued, (int, float)):
                    issued_date = date.fromtimestamp(issued)
                elif isinstance(issued, str):
                    try:
                        issued_date = datetime.fromisoformat(issued.replace('Z', '+00:00')).date()
                    except:
                        issued_date = None
                else:
                    issued_date = None
                cur.execute("""
                    INSERT INTO errata (errata_id, title, description, severity, os_type, cves, issued_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (errata_id) DO UPDATE SET
                        title = EXCLUDED.title, severity = EXCLUDED.severity,
                        cves = EXCLUDED.cves, issued_date = EXCLUDED.issued_date
                    RETURNING id
                """, (errata_id, title, description, severity, os_type, cves, issued_date))
                db_errata_id = cur.fetchone()[0]
                for pkg in erratum.get('packages', []):
                    cur.execute("""
                        INSERT INTO errata_packages (errata_id, package_name, fixed_version, architecture, release)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (db_errata_id, pkg.get('name'), pkg.get('version'), pkg.get('architecture', 'amd64'), pkg.get('release', '')))
            conn.commit()
        except Exception as e:
            print(f"Error syncing {os_type}: {e}")
            conn.rollback()
    conn.close()

def sync_hosts():
    conn = get_db()
    cur = conn.cursor()
    try:
        r = requests.get(f"{FOREMAN_URL}/api/hosts?per_page=1000",
                        auth=(FOREMAN_USER, FOREMAN_PASSWORD), verify=FOREMAN_VERIFY_SSL, timeout=30)
        if r.status_code != 200:
            conn.close()
            return
        for host in r.json().get('results', []):
            os_title = host.get('operatingsystem_name', '')
            if 'Ubuntu' not in os_title and 'Debian' not in os_title:
                continue
            hostname = host.get('name')
            foreman_id = host.get('id')
            ip = host.get('ip')
            org = host.get('organization_name', '')
            hostgroup = host.get('hostgroup_name', '')
            os_release = ''
            if '24.04' in os_title or 'noble' in os_title.lower():
                os_release = 'noble'
            elif '22.04' in os_title or 'jammy' in os_title.lower():
                os_release = 'jammy'
            elif '20.04' in os_title or 'focal' in os_title.lower():
                os_release = 'focal'
            elif '12' in os_title or 'bookworm' in os_title.lower():
                os_release = 'bookworm'
            elif '11' in os_title or 'bullseye' in os_title.lower():
                os_release = 'bullseye'
            cur.execute("""
                INSERT INTO hosts (foreman_id, hostname, ip_address, os_title, os_release, organization, hostgroup)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (foreman_id) DO UPDATE SET
                    hostname = EXCLUDED.hostname, ip_address = EXCLUDED.ip_address,
                    os_title = EXCLUDED.os_title, os_release = EXCLUDED.os_release,
                    organization = EXCLUDED.organization, hostgroup = EXCLUDED.hostgroup,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (foreman_id, hostname, ip, os_title, os_release, org, hostgroup))
            host_id = cur.fetchone()[0]
            pr = requests.get(f"{FOREMAN_URL}/api/hosts/{foreman_id}/packages?per_page=10000",
                             auth=(FOREMAN_USER, FOREMAN_PASSWORD), verify=FOREMAN_VERIFY_SSL, timeout=60)
            if pr.status_code == 200:
                cur.execute("DELETE FROM host_packages WHERE host_id = %s", (host_id,))
                for pkg in pr.json().get('results', []):
                    name = pkg.get('name', '')
                    nvra = pkg.get('nvra', '')
                    version = nvra.replace(name + '-', '').rsplit('.', 1)[0] if nvra else ''
                    cur.execute("""
                        INSERT INTO host_packages (host_id, package_name, package_version, architecture)
                        VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING
                    """, (host_id, name, version, 'amd64'))
            conn.commit()
    except Exception as e:
        print(f"Error syncing hosts: {e}")
        conn.rollback()
    conn.close()

def correlate_errata():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, hostname, os_release FROM hosts")
    hosts = cur.fetchall()
    for host in hosts:
        host_id = host['id']
        release = host['os_release']
        cur.execute("SELECT package_name, package_version FROM host_packages WHERE host_id = %s", (host_id,))
        installed = {row['package_name']: row['package_version'] for row in cur.fetchall()}
        if not installed:
            continue
        cur.execute("""
            SELECT e.id, ep.package_name, ep.fixed_version
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
        conn.commit()
    conn.close()

def save_snapshot():
    """Salva uno snapshot giornaliero dello stato errata per ogni host"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    today = date.today()
    
    cur.execute("SELECT id, hostname, organization FROM hosts")
    hosts = cur.fetchall()
    
    for host in hosts:
        host_id = host['id']
        hostname = host['hostname']
        organization = host['organization']
        
        cur.execute("""
            SELECT e.severity, COUNT(*) as count
            FROM host_errata he
            JOIN errata e ON he.errata_id = e.id
            WHERE he.host_id = %s
            GROUP BY e.severity
        """, (host_id,))
        
        counts = {row['severity']: row['count'] for row in cur.fetchall()}
        total = sum(counts.values())
        
        cur.execute("""
            INSERT INTO errata_history 
            (snapshot_date, host_id, hostname, organization, total_errata, critical_count, important_count, moderate_count, low_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_date, host_id) DO UPDATE SET
                total_errata = EXCLUDED.total_errata,
                critical_count = EXCLUDED.critical_count,
                important_count = EXCLUDED.important_count,
                moderate_count = EXCLUDED.moderate_count,
                low_count = EXCLUDED.low_count
        """, (
            today, host_id, hostname, organization, total,
            counts.get('critical', 0),
            counts.get('important', 0),
            counts.get('moderate', 0),
            counts.get('low', 0)
        ))
    
    conn.commit()
    conn.close()
    return {'snapshot_date': str(today), 'hosts_processed': len(hosts)}

@app.route('/api/snapshot', methods=['POST'])
def trigger_snapshot():
    """Endpoint per triggerare manualmente uno snapshot"""
    result = save_snapshot()
    return jsonify({'status': 'completed', 'result': result})

@app.route('/api/history')
def get_history():
    """Restituisce lo storico errata"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    hostname = request.args.get('hostname')
    organization = request.args.get('organization')
    days = int(request.args.get('days', 30))
    
    query = """
        SELECT snapshot_date, hostname, organization, total_errata, 
               critical_count, important_count, moderate_count, low_count
        FROM errata_history
        WHERE snapshot_date >= CURRENT_DATE - INTERVAL '%s days'
    """
    params = [days]
    
    if hostname:
        query += " AND hostname = %s"
        params.append(hostname)
    if organization and organization != '%' and organization != '%%':
        query += " AND organization = %s"
        params.append(organization)
    
    query += " ORDER BY snapshot_date, hostname"
    
    cur.execute(query, params)
    history = cur.fetchall()
    conn.close()
    
    return jsonify({'history': history, 'total': len(history)})

@app.route('/api/sync', methods=['POST'])
def trigger_sync():
    sync_type = request.json.get('type', 'all') if request.json else 'all'
    if sync_type in ['all', 'errata']:
        sync_errata()
    if sync_type in ['all', 'hosts']:
        sync_hosts()
    if sync_type in ['all', 'correlate']:
        correlate_errata()
    if sync_type in ['all', 'snapshot']:
        save_snapshot()
    return jsonify({'status': 'completed', 'type': sync_type})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
ENDOFFILE
```

**Dockerfile:**
```bash
cat > Dockerfile << 'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 5000
CMD ["python", "app.py"]
EOF
```

**requirements.txt:**
```bash
cat > requirements.txt << 'EOF'
flask==3.0.0
psycopg2-binary==2.9.9
requests==2.31.0
EOF
```

**Build:**
```bash
az acr build --registry acrerrata --image errata_backend:v3 .
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
### 7.2 Creare il Database
```bash
az postgres flexible-server db create \
  --resource-group <RESOURCE_GROUP> \
  --server-name pgserverrata \
  --database-name errata_db
```
### 7.3 Trovare l'IP Privato del PostgreSQL
```bash
az network private-dns record-set a list \
  --resource-group <RESOURCE_GROUP> \
  --zone-name pgserverrata.private.postgres.database.azure.com \
  --output json
```

L'IP sarà nel campo `ipv4Address` (es. `10.172.2.196`).

**IMPORTANTE:** Usare l'IP diretto nel DATABASE_URL, non il FQDN.

**Perché?** Il PostgreSQL Flexible Server usa una Private DNS Zone che non è risolvibile dalla subnet ACI a meno che non sia esplicitamente collegata.

---
## 8. Azure Storage Account
### 8.1 Creare Storage Account
```bash
az storage account create \
  --name sterrata01 \
  --resource-group <RESOURCE_GROUP> \
  --location italynorth \
  --sku Standard_LRS
```
### 8.2 Creare File Shares
```bash
az storage share create --name errata-data --account-name sterrata01 --quota 5
az storage share create --name errata-grafana --account-name sterrata01 --quota 1
```
### 8.3 Ottenere Chiave
```bash
az storage account keys list --account-name sterrata01 --output table
```

---
## 9. Generazione Dati Errata
### 9.1 Dalla Cloud Shell - Scarica USN Database

```bash
cd ~
curl -o usn-db.json.bz2 https://usn.ubuntu.com/usn-db/database.json.bz2
bunzip2 -f usn-db.json.bz2
```
### 9.2 Crea Script di Processamento
**Salvare in `~/clouddrive/` per persistenza:**

```bash
cat > ~/clouddrive/process_usn.py << 'ENDOFFILE'
#!/usr/bin/env python3
import json
import os
from datetime import datetime

USN_DB = os.path.expanduser('~/usn-db.json')
OUTPUT_DIR = os.path.expanduser('~/errata_output')
RELEASES = {'noble', 'jammy', 'focal'}

os.makedirs(OUTPUT_DIR, exist_ok=True)

def main():
    print("Loading USN database...")
    with open(USN_DB, 'r') as f:
        usn_data = json.load(f)
    
    print(f"Loaded {len(usn_data)} USN entries")
    
    errata_list = []
    for usn_id, usn_data in usn_data.items():
        if not usn_id.startswith('USN-'):
            usn_id = f"USN-{usn_id}"
        
        releases_data = usn_data.get('releases', {})
        packages = []
        
        for release_name, release_data in releases_data.items():
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
    
    ubuntu_output = os.path.join(OUTPUT_DIR, 'ubuntu_errata.json')
    with open(ubuntu_output, 'w') as f:
        json.dump(errata_list, f)
    print(f"Written {ubuntu_output}")
    
    debian_output = os.path.join(OUTPUT_DIR, 'debian_errata.json')
    with open(debian_output, 'w') as f:
        json.dump([], f)
    print(f"Written {debian_output}")

if __name__ == '__main__':
    main()
ENDOFFILE
```
### 9.3 Eseguire lo Script
```bash
python3 ~/clouddrive/process_usn.py
```
### 9.4 Creare File di Configurazione
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
### 9.5 Caricare su Azure Storage
```bash
az storage file upload --account-name sterrata01 --share-name errata-data \
  --source ~/errata_output/ubuntu_errata.json --path ubuntu_errata.json
```
```bash
az storage file upload --account-name sterrata01 --share-name errata-data \
  --source ~/errata_output/debian_errata.json --path debian_errata.json
```
```bash
az storage file upload --account-name sterrata01 --share-name errata-data \
  --source ~/errata_output/ubuntu_config.json --path ubuntu_config.json
```
```bash
az storage file upload --account-name sterrata01 --share-name errata-data \
  --source ~/errata_output/debian_config.json --path debian_config.json
```

---
## 10. Deploy Container Group (ACI)
### 10.1 Creare File YAML
**Salvare in `~/clouddrive/` per persistenza:**

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
      image: acrerrata.azurecr.io/errata_backend:v3
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
### 10.2 Deploy

```bash
az container create \
  --resource-group <RESOURCE_GROUP> \
  --file ~/clouddrive/aci-errata.yaml
```

---
## 11. Inizializzazione Database
### 11.1 Connessione al Database
```bash
psql "host=10.172.2.196 port=5432 dbname=errata_db user=errata_admin password=ErrataDB2024! sslmode=require"
```
### 11.2 Creare le Tabelle

```sql
-- Hosts
CREATE TABLE IF NOT EXISTS hosts (
    id SERIAL PRIMARY KEY,
    foreman_id INTEGER UNIQUE NOT NULL,
    hostname VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45),
    os_title VARCHAR(100),
    os_release VARCHAR(50),
    organization VARCHAR(255),
    hostgroup VARCHAR(255),
    last_report TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Host packages
CREATE TABLE IF NOT EXISTS host_packages (
    id SERIAL PRIMARY KEY,
    host_id INTEGER REFERENCES hosts(id) ON DELETE CASCADE,
    package_name VARCHAR(255) NOT NULL,
    package_version VARCHAR(100),
    architecture VARCHAR(20) DEFAULT 'amd64',
    UNIQUE(host_id, package_name, architecture)
);

-- Errata
CREATE TABLE IF NOT EXISTS errata (
    id SERIAL PRIMARY KEY,
    errata_id VARCHAR(50) UNIQUE NOT NULL,
    title VARCHAR(500),
    description TEXT,
    severity VARCHAR(20),
    os_type VARCHAR(20),
    issued_date DATE,
    cves TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Errata packages
CREATE TABLE IF NOT EXISTS errata_packages (
    id SERIAL PRIMARY KEY,
    errata_id INTEGER REFERENCES errata(id) ON DELETE CASCADE,
    package_name VARCHAR(255) NOT NULL,
    fixed_version VARCHAR(100),
    architecture VARCHAR(20) DEFAULT 'amd64',
    release VARCHAR(50)
);

-- Host-Errata correlation
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

-- History for trending
CREATE TABLE IF NOT EXISTS errata_history (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    host_id INTEGER REFERENCES hosts(id) ON DELETE CASCADE,
    hostname VARCHAR(255),
    organization VARCHAR(255),
    total_errata INTEGER DEFAULT 0,
    critical_count INTEGER DEFAULT 0,
    important_count INTEGER DEFAULT 0,
    moderate_count INTEGER DEFAULT 0,
    low_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(snapshot_date, host_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_host_packages_host_id ON host_packages(host_id);
CREATE INDEX IF NOT EXISTS idx_errata_packages_errata_id ON errata_packages(errata_id);
CREATE INDEX IF NOT EXISTS idx_host_errata_host_id ON host_errata(host_id);
CREATE INDEX IF NOT EXISTS idx_host_errata_errata_id ON host_errata(errata_id);
CREATE INDEX IF NOT EXISTS idx_errata_history_date ON errata_history(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_errata_history_host ON errata_history(host_id);
CREATE INDEX IF NOT EXISTS idx_errata_history_org ON errata_history(organization);
```

---
## 12. Test e Verifica
### 12.1 Health Check

```bash
curl http://10.172.5.4:5000/api/health
```
### 12.2 Sync Iniziale
```bash
curl -X POST http://10.172.5.4:5000/api/sync \
  -H "Content-Type: application/json" \
  -d '{"type": "all"}'
```
### 12.3 Statistiche
```bash
curl http://10.172.5.4:5000/api/stats
```
### 12.4 Creare Snapshot
```bash
curl -X POST http://10.172.5.4:5000/api/snapshot
```
### 12.5 Verificare Storico
```bash
curl http://10.172.5.4:5000/api/history
```

---
## 13. Configurazione Grafana

Vedi la guida dedicata: [Grafana-Errata-Dashboard](Foreman-Katello/Configurazione-Tutorial/Grafana-Errata-Dashboard.md)

---
## 14. Registrazione Host in Foreman

Vedi la guida dedicata: [Guida-Registrazione-Host-Ubuntu-24.04](Foreman-Katello/Configurazione-Tutorial/Guida-Registrazione-Host-Ubuntu-24.04.md)

---
## 15. Gestione e Manutenzione
### 15.1 Comandi ACI
#### Stato
```bash
az container show --resource-group <RG> --name errata-management --output table
```
#### Log backend
```bash
az container logs --resource-group <RG> --name errata-management --container-name backend
```
#### Log errata-server
```bash
az container logs --resource-group <RG> --name errata-management --container-name errata-server
```
#### Restart
```bash
az container restart --resource-group <RG> --name errata-management
```
#### Stop
```bash
az container stop --resource-group <RG> --name errata-management
```
#### Delete
```bash
az container delete --resource-group <RG> --name errata-management --yes
```
### 15.2 Aggiornare Errata (Settimanale)
#### Scarica nuovi USN
```bash
cd ~
curl -o usn-db.json.bz2 https://usn.ubuntu.com/usn-db/database.json.bz2
bunzip2 -f usn-db.json.bz2
```
#### Rigenera JSON
```bash
python3 ~/clouddrive/process_usn.py
```
#### Carica su storage
```bash
az storage file upload --account-name sterrata01 --share-name errata-data \
  --source ~/errata_output/ubuntu_errata.json --path ubuntu_errata.json
```
#### Restart errata-server per ricaricare
```bash
az container restart --resource-group <RG> --name errata-management
```
#### Trigger sync
```bash
curl -X POST http://10.172.5.4:5000/api/sync \
  -H "Content-Type: application/json" \
  -d '{"type": "all"}'
```

---
## 16. Troubleshooting
### 16.1 Backend Non Connette a Database
```
relation "hosts" does not exist
```
**Soluzione:** Eseguire SQL della sezione 11.
### 16.2 applicable_errata = 0

**Causa:** Gli host non hanno inviato i pacchetti a Foreman.
**Soluzione:** Vedi guida registrazione host, FASE 10.
### 16.3 errata_server Errore Config
```
'releases' must be a dict
```
**Soluzione:** Verificare formato config.json (sezione 9.4).

---
## Limitazioni Note

- Parser ATIX non utilizzabile in ACI (no Internet)
- Correlazione richiede Content Host registrato
- Severity è euristica (non CVSS)
- Solo Ubuntu completamente supportato
- Aggiornamento errata manuale

---
## API Reference

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/stats` | GET | Statistiche generali |
| `/api/hosts` | GET | Lista host |
| `/api/hosts/<hostname>` | GET | Dettaglio host con errata |
| `/api/errata` | GET | Lista errata |
| `/api/sync` | POST | Trigger sync (`{"type": "all"}`) |
| `/api/snapshot` | POST | Crea snapshot storico |
| `/api/history` | GET | Storico errata (params: days, hostname, organization) |

---
## Valori Configurazione Attuale

| Parametro | Valore |
|-----------|--------|
| Subscription ID | `896dd1f5-30ae-42db-a7d4-c0f8184c6b1c` |
| Resource Group | `ASL0603-spoke10-rg-spoke-italynorth` |
| VNet | `ASL0603-spoke10-spoke-italynorth` |
| Subnet ACI | `errata-aci-subnet` (10.172.5.0/28) |
| ACR | `acrerrata.azurecr.io` |
| Storage Account | `sterrata01` |
| PostgreSQL IP | `10.172.2.196` |
| Container Group IP | `10.172.5.4` |
| Foreman IP | `10.172.2.17` |

