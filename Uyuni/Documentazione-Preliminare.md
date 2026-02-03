# Documentazione Preliminare - Security Patch Manager (SPM)

**Documento di raccolta informazioni per la presentazione del progetto**
**Autore**: Alberto Ameglio
**Data**: 2026-02-02
**Versione**: 1.0

---

## INDICE

1. [Standard di Riferimento](#1-standard-di-riferimento)
2. [Evoluzione e Collegamento dei Tool](#2-evoluzione-e-collegamento-dei-tool)
3. [UYUNI - Descrizione Tecnica](#3-uyuni---descrizione-tecnica)
4. [Salt - Architettura e Comunicazioni](#4-salt---architettura-e-comunicazioni)
5. [API XML-RPC](#5-api-xml-rpc)
6. [Workflow Attuale (P1-P5)](#6-workflow-attuale-p1-p5)
7. [Infrastruttura Cloud Attuale](#7-infrastruttura-cloud-attuale)
   - 7.5 [Flusso di Sincronizzazione Dati di Sicurezza](#75-flusso-di-sincronizzazione-dati-di-sicurezza)
8. [Infrastruttura Cloud Target](#8-infrastruttura-cloud-target)
9. [Processi di Configurazione](#9-processi-di-configurazione)
10. [Stato Attuale e Lavori Completati](#10-stato-attuale-e-lavori-completati)
11. [Attività Mancanti](#11-attività-mancanti)
12. [Suggerimenti Aggiuntivi](#12-suggerimenti-aggiuntivi)

---

## 1. STANDARD DI RIFERIMENTO

Il progetto Security Patch Manager si basa su standard internazionali riconosciuti per la gestione delle patch di sicurezza, come definito nel documento **"Automated Patch Management for B2B IaaS Environments v1.1"**.

### 1.1 IEC/ISO 62443 - Industrial Automation Security

Framework industriale che definisce un lifecycle completo per il patch management:

| Fase                         | Descrizione                                                |
| ---------------------------- | ---------------------------------------------------------- |
| **Information Gathering**    | Raccolta informazioni su vulnerabilità e patch disponibili |
| **Monitoring & Evaluation**  | Monitoraggio continuo e valutazione impatto                |
| **Patch Testing**            | Test in ambiente isolato prima del deployment              |
| **Deployment**               | Applicazione controllata delle patch                       |
| **Verification & Reporting** | Verifica successo e documentazione                         |

**Enfasi**: Continuità operativa e validazione vendor.

### 1.2 ISO/IEC 27002 - Information Security Management System (ISMS)

Standard governance-based che definisce principi fondamentali:

- **Preservare funzionalità**: Le patch non devono compromettere le operazioni
- **Minimizzare downtime**: Approccio zero-downtime dove possibile
- **Redundancy**: Sistemi di backup e rollback
- **Coordinamento dedicato**: Team responsabile del processo

### 1.3 NERC CIP-007 - Critical Infrastructure Protection

Standard per infrastrutture critiche (settore elettrico) con focus su:

- **Trusted Sources**: Patch solo da vendor verificati e repository ufficiali
- **Comprehensive Documentation**: Documentazione completa per ogni fase
- **Change Management**: Processo formale di gestione delle modifiche
- **Audit Trail**: Tracciabilità completa delle operazioni

### 1.4 NIST SP 800-40 Rev. 4 - Enterprise Patch Management

Guida NIST per la gestione enterprise delle patch con principi chiave:

| Principio                      | Descrizione                          |
| ------------------------------ | ------------------------------------ |
| **Preparation > Perfection**   | Meglio essere preparati che perfetti |
| **Simplified Decision-Making** | Processo decisionale semplificato    |
| **Automation**                 | Automazione dove possibile           |
| **Continuous Improvement**     | Miglioramento continuo del processo  |

**Risk Responses**: Accept, Mitigate, Transfer, Avoid

**Enfasi**: Proactive patching vs reactive patching.

### 1.5 Contesto Normativo PSN

Il progetto è sviluppato nel contesto del **Polo Strategico Nazionale (PSN)** - Cloud Sicuro per l'Italia Digitale:

- **EU Cybersecurity Act (2019/881)**: Framework europeo per la cybersecurity
- **EUCS**: EU Cloud Cybersecurity Certification Scheme
- **US Homeland Security Act**: Riferimento per best practices
- **OWASP Top 10:2025**: Particolare attenzione a "Software Supply Chain Failures"
- **Data Sovereignty**: Residenza dati sul territorio italiano

---

## 2. EVOLUZIONE E COLLEGAMENTO DEI TOOL

### 2.1 Albero Genealogico dei Tool

```
SPACEWALK (Red Hat, 2008) - Open Source
    │
    ├──────────────────────────────────────────────────────┐
    │                                                      │
    ▼                                                      ▼
RED HAT SATELLITE                                    UYUNI (SUSE, Open Source)
(Commerciale, Red Hat)                                     │
    │                                                      │
    │                                                      ▼
    │                                              SUSE MANAGER
    │                                              (Commerciale, SUSE)
    │
    ▼
SATELLITE 6 (Rewrite basato su Foreman)
    │
    ▼
FOREMAN + KATELLO
(Open Source, Community)
    │
    ├──► ORCHARHINO (ATIX AG, Enterprise)
    │    └── Include: ATIX errata_parser
    │
    └──► Upstream per Satellite 6
```

### 2.2 Tabella Comparativa dei Tool

| Caratteristica | Spacewalk | Foreman-Katello | UYUNI | Red Hat Satellite | Orcharhino |
|---------------|-----------|-----------------|-------|-------------------|------------|
| **Tipologia** | Legacy | Open-source | Open-source | Enterprise | Enterprise |
| **Licenza** | GPL | GPL | GPL v2 | Commerciale | Commerciale |
| **Stato** | Deprecato | Attivo | Attivo | Attivo | Attivo |
| **Supporto** | Community (terminato) | Community | Community | Red Hat | ATIX AG |
| **Multi-OS** | RHEL-focused | Multi-distro | Multi-distro | RHEL-focused | Multi-distro |
| **Scalabilità** | Limitata | Smart-proxy | Container | Capsule | Server+Proxy |
| **Config Mgmt** | - | Puppet/Ansible | Salt | Puppet/Ansible | Puppet/Ansible |
| **Errata Ubuntu/Debian** | No | Plugin | **SPM** | No | errata_parser |

### 2.3 ATIX AG errata_parser

**Cos'è**: Tool sviluppato da ATIX AG per importare errata Ubuntu/Debian in Foreman-Katello.

**Repository**: [github.com/ATIX-AG/errata_parser](https://github.com/ATIX-AG/errata_parser)

**Funzionamento**:
- Scarica USN (Ubuntu Security Notices) e DSA (Debian Security Advisories)
- Converte in formato compatibile con Katello
- Importa via API REST

**Collegamento con SPM**: Il Security Patch Manager si ispira a questo approccio per UYUNI, sviluppando una soluzione analoga con funzionalità estese:
- Sincronizzazione automatizzata via Logic Apps Azure
- Database centralizzato PostgreSQL
- Integrazione OVAL per CVE Audit
- Arricchimento con dati NVD (CVSS scores)

### 2.4 Perché UYUNI

Motivazioni della scelta di UYUNI per il progetto SPM:

| Vantaggio                | Descrizione                          |
| ------------------------ | ------------------------------------ |
| **Open Source**          | GPL v2, nessun costo di licenza      |
| **CVE Audit Nativo**     | Supporto OVAL out-of-box             |
| **Salt Integration**     | Automazione potente e scalabile      |
| **Multi-OS Reale**       | SUSE, RHEL, Ubuntu, Debian           |
| **Architettura Moderna** | Deployment container (Podman)        |
| **Flessibilità**         | API XML-RPC completa per automazione |

---

## 3. UYUNI - DESCRIZIONE TECNICA

### 3.1 Definizione

**UYUNI** è una piattaforma open source per la **gestione centralizzata dell'infrastruttura Linux**, derivata da Spacewalk e mantenuta da SUSE come versione community di SUSE Manager.

### 3.2 Funzionalità Principali

| Funzionalità                 | Descrizione                                             |
| ---------------------------- | ------------------------------------------------------- |
| **Patch Management**         | Distribuzione controllata di aggiornamenti di sicurezza |
| **Configuration Management** | Gestione centralizzata configurazioni via Salt          |
| **Compliance & Auditing**    | Verifica conformità e audit CVE (OVAL)                  |
| **Provisioning**             | Deployment automatizzato di nuovi sistemi (Cobbler)     |
| **Inventory Management**     | Inventario hardware e software centralizzato            |

### 3.3 Architettura Componenti

```
┌─────────────────────────────────────────────────────────────────┐
│                      UYUNI SERVER                                │
│                  (Container Podman o VM)                         │
├─────────────────────────────────────────────────────────────────┤
│  PRESENTATION LAYER                                              │
│  ├── Web UI (Tomcat/Java) - Interfaccia amministrazione         │
│  ├── XML-RPC API (Python/Java) - Automazione programmatica      │
│  └── REST API (limited) - Alcune funzioni moderne               │
├─────────────────────────────────────────────────────────────────┤
│  APPLICATION LAYER                                               │
│  ├── Taskomatic (Java) - Scheduler job asincroni                │
│  ├── Salt Master (Python/ZeroMQ) - Esecuzione remota            │
│  └── Cobbler (Python) - Provisioning PXE/kickstart              │
├─────────────────────────────────────────────────────────────────┤
│  DATA LAYER                                                      │
│  ├── PostgreSQL 14+ - Database centrale                         │
│  ├── Apache HTTPD 2.4 - Reverse proxy e repository server       │
│  └── Squid 5.x - Cache proxy (opzionale)                        │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 Porte di Rete

| Porta | Protocollo | Direzione | Funzione |
|-------|------------|-----------|----------|
| **443** | HTTPS | Client → Server | Web UI, API, repository |
| **4505** | TCP | Client → Server | Salt publish (ZeroMQ PUB) |
| **4506** | TCP | Client → Server | Salt return (ZeroMQ REQ) |
| **5432** | TCP | Interno | PostgreSQL (se esterno) |
| **69** | UDP | PXE → Server | TFTP per provisioning |

### 3.5 Relazione UYUNI - SUSE Manager

| Aspetto | UYUNI | SUSE Manager |
|---------|-------|--------------|
| **Codebase** | Upstream | Downstream (stabilizzato) |
| **Licenza** | GPL v2 | Commerciale |
| **Supporto** | Community | Enterprise SUSE |
| **Release** | Rolling | Versioni stabili |
| **Target** | Qualsiasi Linux | SUSE + altri |

**Nota**: SUSE Manager è essenzialmente UYUNI con supporto commerciale e cicli di release enterprise.

---

## 4. SALT - ARCHITETTURA E COMUNICAZIONI

### 4.1 Cos'è SaltStack

**Salt** (SaltStack) è un motore di automazione e configuration management basato su Python. UYUNI lo utilizza come componente core per:
- Esecuzione comandi remoti
- Configuration management
- Event-driven automation
- Orchestration

### 4.2 Architettura Salt

```
┌─────────────────────────────────────────────────────────────────┐
│                      SALT MASTER                                 │
│                   (su UYUNI Server)                              │
│                                                                  │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │  ZeroMQ PUB     │    │  ZeroMQ REP     │                     │
│  │  Port 4505      │    │  Port 4506      │                     │
│  │  (Publish)      │    │  (Return)       │                     │
│  └────────┬────────┘    └────────▲────────┘                     │
└───────────┼──────────────────────┼──────────────────────────────┘
            │                      │
            │  Comandi             │  Risultati
            ▼                      │
┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│   SALT MINION 1   │    │   SALT MINION 2   │    │   SALT MINION N   │
│   (Client VM)     │    │   (Client VM)     │    │   (Client VM)     │
└───────────────────┘    └───────────────────┘    └───────────────────┘
```

### 4.3 Protocollo di Comunicazione

| Porta | Pattern | Funzione |
|-------|---------|----------|
| **4505** | PUB/SUB | Master pubblica comandi a tutti i minion (broadcast) |
| **4506** | REQ/REP | Minion inviano risultati al master (point-to-point) |

**Caratteristiche**:
- **Connessione persistente**: Minion mantiene connessione attiva
- **Bidirezionale**: Comandi down, risultati up
- **Event-driven**: Notifiche in tempo reale
- **Scalabile**: Migliaia di client con latenza sub-second

### 4.4 Autenticazione PKI

```
SALT PKI HANDSHAKE

1. Minion genera coppia chiavi RSA 4096-bit
   └── /etc/salt/pki/minion/minion.pem (privata)
   └── /etc/salt/pki/minion/minion.pub (pubblica)

2. Minion invia chiave pubblica al Master
   Minion ──────► [minion.pub] ──────► Master

3. Amministratore accetta chiave sul Master
   salt-key -a <minion-id>

4. Master invia sua chiave pubblica al Minion
   Master ──────► [master.pub] ──────► Minion
   └── Salvata in /etc/salt/pki/minion/minion_master.pub

5. Comunicazione cifrata AES-256 stabilita
```

### 4.5 Modalità di Connessione

| Modalità | Agent | Porte | Latenza | Uso |
|----------|-------|-------|---------|-----|
| **Salt Minion** | Sì | 4505/4506 | ms | Standard, alta reattività |
| **Salt-SSH** | No | 22 | secondi | DMZ, ambienti restrittivi |

**Salt Minion** (raccomandato):
- Connessione persistente
- Esecuzione real-time
- Event-driven (beacons, reactors)
- Consumo: ~50MB RAM

**Salt-SSH** (agentless):
- Connessione on-demand via SSH
- Nessun agent da mantenere
- Solo porta 22 richiesta
- Ideale per DMZ e sistemi sensibili

### 4.6 Esempi Comandi Salt

```bash
# Test connettività
salt '*' test.ping

# Informazioni sistema
salt 'minion-id' grains.items

# Esecuzione comando
salt 'minion-id' cmd.run 'apt update'

# Installazione pacchetto
salt 'minion-id' pkg.install nginx

# Applicazione stato
salt 'minion-id' state.apply webserver
```

---

## 5. API XML-RPC

### 5.1 Cos'è XML-RPC

**XML-RPC** è un protocollo RPC (Remote Procedure Call) che usa XML per codificare le chiamate e HTTP come trasporto. UYUNI espone una API XML-RPC completa per l'automazione.

### 5.2 Endpoint

```
https://<uyuni-server>/rpc/api
```

### 5.3 Autenticazione

```python
import xmlrpc.client

# Connessione
client = xmlrpc.client.ServerProxy("https://uyuni-server/rpc/api")

# Login - restituisce session key
session_key = client.auth.login("admin", "password")

# Tutte le chiamate successive usano session_key
systems = client.system.listSystems(session_key)

# Logout (importante per liberare la sessione)
client.auth.logout(session_key)
```

### 5.4 Namespace Principali

| Namespace | Funzione |
|-----------|----------|
| `auth` | Autenticazione (login/logout) |
| `system` | Gestione sistemi registrati |
| `channel` | Gestione canali software |
| `channel.software` | Gestione pacchetti nei canali |
| `errata` | Gestione errata/patch |
| `packages` | Informazioni pacchetti |
| `systemgroup` | Gestione gruppi di sistemi |
| `activationkey` | Gestione activation keys |
| `configchannel` | Configuration channels |
| `schedule` | Scheduling azioni |

### 5.5 Esempi API Comuni

```python
# Lista tutti i sistemi
systems = client.system.listSystems(session_key)

# Dettagli sistema
details = client.system.getDetails(session_key, system_id)

# Lista errata applicabili a un sistema
errata = client.system.getRelevantErrata(session_key, system_id)

# Applica errata a un sistema
client.system.scheduleApplyErrata(session_key, system_id, [errata_id], datetime)

# Crea canale software
client.channel.software.create(session_key, "channel-label", "Channel Name",
                                "Channel Summary", "amd64-deb", "parent-channel")

# Push errata a canale (usato da SPM)
client.errata.publish(session_key, errata_id, [channel_label])
```

### 5.6 Utilizzo nel Progetto SPM

L'API XML-RPC è il punto di integrazione principale tra l'API Flask SPM e UYUNI:

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   SPM API        │     │   UYUNI          │     │   Client VMs     │
│   (Flask)        │────►│   XML-RPC API    │────►│   (Salt Minion)  │
│                  │     │                  │     │                  │
│ - Sync USN/DSA   │     │ - Create Errata  │     │ - Apply Patches  │
│ - Push Errata    │     │ - Publish Errata │     │ - Report Status  │
│ - NVD Enrichment │     │ - Schedule Jobs  │     │                  │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

---

## 6. WORKFLOW ATTUALE (P1-P5)

### 6.1 Overview del Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SECURITY PATCH MANAGER WORKFLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  P1: ACTIVE ENVIRONMENT DISCOVERY                                            │
│  ───────────────────────────────────                                         │
│  • Inventario automatico VM e sistemi                                        │
│  • Raccolta informazioni: OS, versioni, pacchetti                            │
│  • Identificazione asset gestiti                                             │
│                     │                                                        │
│                     ▼                                                        │
│  P2: SECURITY PATCH DISCOVERY & PRIORITIZATION                               │
│  ─────────────────────────────────────────────────                           │
│  • Sync errata da USN/DSA/OVAL                                               │
│  • Correlazione con NVD per CVSS                                             │
│  • Prioritizzazione basata su rischio                                        │
│  • Due modalità:                                                             │
│    - Security Mode: solo rischio                                             │
│    - Smart Mode: rischio + dipendenze + impatto                              │
│                     │                                                        │
│                     ▼                                                        │
│  P3: PATCH TESTING                                                           │
│  ─────────────────────                                                       │
│  • Clone VM in subnet isolata                                                │
│  • Baseline metrics collection                                               │
│  • Applicazione patch su clone                                               │
│  • Confronto metriche pre/post                                               │
│  • Decisione: APPROVED / FAILED                                              │
│                     │                                                        │
│                     ▼                                                        │
│  P4: PATCH DEPLOYMENT                                                        │
│  ─────────────────────                                                       │
│  • Deploy su sistemi produzione                                              │
│  • Rolling update o simultaneo                                               │
│  • Maintenance windows                                                       │
│  • Rollback automatico se necessario                                         │
│                     │                                                        │
│                     ▼                                                        │
│  P5: POST-DEPLOYMENT ASSESSMENT (Opzionale)                                  │
│  ──────────────────────────────────────────────                              │
│  • Verifica successo deployment                                              │
│  • Re-scan vulnerabilità                                                     │
│  • Report compliance                                                         │
│  • Documentazione                                                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Dettaglio P3 - Patch Testing

Il processo P3 è cruciale per garantire che le patch non causino regressioni:

```
P3 - PATCH TESTING WORKFLOW

1. Ricevi errata da testare
   │
2. Per ogni VM target:
   │
   ├──► Crea Snapshot VM sorgente (Azure API)
   │
   ├──► Crea VM Clone in Subnet-Test
   │    (rete completamente isolata)
   │
   ├──► Configura NSG: deny all except from Proxy
   │
   ├──► Avvia baseline metrics collection
   │    (CPU, RAM, disk, network, services)
   │
   ├──► Installa patch su Clone
   │    (apt/yum/zypper via Salt)
   │
   ├──► Periodo stabilizzazione (configurabile)
   │
   ├──► Confronta metriche vs baseline
   │    │
   │    ├── OK ──► Patch APPROVED
   │    │
   │    └── KO ──► Patch FAILED + report
   │
   └──► Cleanup: Delete Clone VM + Snapshot

3. Output: Lista patch testate (approved/failed)
```

---

## 7. INFRASTRUTTURA CLOUD ATTUALE

### 7.1 Componenti Deployati

| Componente | Resource Group | Nome | Endpoint |
|------------|----------------|------|----------|
| Container Pubblico | test_group | aci-errata-api | `errata-api-spm.italynorth.azurecontainer.io:5000` |
| Container Interno | ASL0603-spoke10-rg | aci-errata-api-internal | `10.172.5.4:5000` |
| UYUNI Server | - | uyuni-server-test | `10.172.2.17` |
| ACR | test_group | acaborerrata.azurecr.io | - |
| PostgreSQL | test_group | pg-errata-test | `pg-errata-test.postgres.database.azure.com` |
| Logic Apps | test_group | logic-usn-sync, logic-dsa-sync, logic-oval-sync, logic-nvd-sync | - |
| Private DNS Zone | ASL0603-spoke10-rg | spm.internal | `api.spm.internal` |
| VNET | ASL0603-spoke10-rg | ASL0603-spoke10 | `10.172.0.0/16` |

### 7.2 Architettura Attuale

```
┌───────────────────────────────────────────────────────────────────┐
│                      AZURE LOGIC APPS                             │
│  logic-usn-sync (6h) │ logic-dsa-sync (daily 03:00)               │
│  logic-oval-sync (weekly Sun 02:00) │ logic-nvd-sync (daily 04:00)│
│                    (Solo SYNC - no push)                          │
└─────────────────────────────┬─────────────────────────────────────┘
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

### 7.3 Motivazione Architettura Duale Container

**Problema**: Le Logic Apps (Consumption tier) non possono raggiungere IP privati nella VNET.

**Soluzione**: Due container con ruoli separati:

| Container | Accesso | Funzione |
|-----------|---------|----------|
| **Pubblico** | Internet | Riceve sync da Logic Apps |
| **Interno** | Solo VNET | Push verso UYUNI |

**Database condiviso**: Entrambi i container accedono allo stesso PostgreSQL.

### 7.4 Statistiche Attuali (2026-01-31)

| Metrica | Valore |
|---------|--------|
| Errata totali | 116.261 (USN: 583, DSA: 115.678) |
| Errata pending | 116.078 |
| CVE tracciati | 47.845 |
| CVE con CVSS (NVD) | 228+ |
| OVAL definitions | 50.862 (Ubuntu: 5.359, Debian: 45.503) |
| Pacchetti in cache | 140.937 |
| Canali Ubuntu | 17 |

### 7.5 Flusso di Sincronizzazione Dati di Sicurezza

#### 7.5.1 Schema Generale del Flusso

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              FONTI ESTERNE (Internet)                                    │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐│
│  │   CANONICAL      │  │   DEBIAN         │  │   NIST           │  │   CANONICAL      ││
│  │   USN Feed       │  │   Security       │  │   NVD API        │  │   OVAL Feed      ││
│  │                  │  │   Tracker        │  │                  │  │   + Debian OVAL  ││
│  │ ubuntu.com/     │  │ security-tracker │  │ services.nvd.    │  │ security-        ││
│  │ security/notices│  │ .debian.org      │  │ nist.gov/rest/   │  │ metadata.        ││
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘│
│           │                     │                     │                     │           │
└───────────┼─────────────────────┼─────────────────────┼─────────────────────┼───────────┘
            │                     │                     │                     │
            ▼                     ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           AZURE LOGIC APPS (Scheduler)                                   │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐│
│  │ logic-usn-sync   │  │ logic-dsa-sync   │  │ logic-nvd-sync   │  │ logic-oval-sync  ││
│  │ ────────────────│  │ ────────────────│  │ ────────────────│  │ ────────────────││
│  │ Ogni 6 ore       │  │ Daily 03:00      │  │ Daily 04:00      │  │ Weekly Dom 02:00 ││
│  │                  │  │ Timeout: 30min   │  │ Timeout: 30min   │  │ Timeout: 60min   ││
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘│
│           │                     │                     │                     │           │
└───────────┼─────────────────────┼─────────────────────┼─────────────────────┼───────────┘
            │                     │                     │                     │
            │         POST /api/sync/usn               POST /api/sync/nvd     │
            │                     POST /api/sync/dsa/full      POST /api/sync/oval
            ▼                     ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                    CONTAINER PUBBLICO (errata-api-spm.italynorth.azurecontainer.io)      │
│                                    Flask API v2.6                                        │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                            SYNC & MAPPING ENGINE                                     ││
│  ├─────────────────────────────────────────────────────────────────────────────────────┤│
│  │                                                                                      ││
│  │  USN PARSER                    DSA PARSER                    OVAL PARSER            ││
│  │  ───────────                   ───────────                   ───────────            ││
│  │  • Fetch RSS/JSON feed         • Fetch security-tracker     • Fetch XML OVAL       ││
│  │  • Parse advisory              • Parse advisory HTML         • Parse definitions    ││
│  │  • Extract:                    • Extract:                    • Extract:             ││
│  │    - USN ID                      - DSA ID                      - OVAL ID            ││
│  │    - CVE list                    - CVE list                    - CVE reference      ││
│  │    - Affected packages           - Affected packages           - Affected versions  ││
│  │    - Severity                    - Severity                    - Platform           ││
│  │    - Release date                - Release date                - Test criteria      ││
│  │                                                                                      ││
│  │  NVD ENRICHER                                                                       ││
│  │  ─────────────                                                                      ││
│  │  • Fetch CVE details from NVD API                                                   ││
│  │  • Extract CVSS v3.1 scores                                                         ││
│  │  • Map severity (CRITICAL/HIGH/MEDIUM/LOW)                                          ││
│  │  • Rate limiting: 0.6s between requests (API Key)                                   ││
│  │                                                                                      ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                          │                                               │
│                                          ▼                                               │
│                                   DATABASE MAPPING                                       │
│                                          │                                               │
└──────────────────────────────────────────┼───────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         POSTGRESQL FLEXIBLE SERVER (Azure)                               │
│                      pg-errata-test.postgres.database.azure.com                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   Database: uyuni_errata                                                                 │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│   │   errata    │  │    cves     │  │    oval     │  │  packages   │  │ errata_cve  │  │
│   │  116,261    │  │   47,845    │  │   50,862    │  │  140,937    │  │   (join)    │  │
│   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           │ Accesso via VNET
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                    CONTAINER INTERNO (10.172.5.4:5000) - VNET PSN                        │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                              UYUNI PUSH ENGINE                                       ││
│  ├─────────────────────────────────────────────────────────────────────────────────────┤│
│  │                                                                                      ││
│  │  1. QUERY PENDING ERRATA                                                            ││
│  │     SELECT * FROM errata WHERE pushed_to_uyuni = false LIMIT 50                     ││
│  │                                                                                      ││
│  │  2. PACKAGE RESOLUTION                                                              ││
│  │     • Match errata packages con UYUNI channel packages                              ││
│  │     • Verifica versioni disponibili                                                 ││
│  │     • Skip se pacchetti non trovati                                                 ││
│  │                                                                                      ││
│  │  3. ERRATA CREATION (XML-RPC)                                                       ││
│  │     client.errata.create(session, errata_info, bugs, keywords, packages, channels)  ││
│  │                                                                                      ││
│  │  4. UPDATE STATUS                                                                   ││
│  │     UPDATE errata SET pushed_to_uyuni = true, push_date = NOW()                     ││
│  │                                                                                      ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                          │                                               │
└──────────────────────────────────────────┼───────────────────────────────────────────────┘
                                           │
                                           │ XML-RPC API (port 443)
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              UYUNI SERVER (10.172.2.17)                                  │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ┌────────────────────┐    ┌────────────────────┐    ┌────────────────────┐            │
│  │   ERRATA DATABASE  │    │  SOFTWARE CHANNELS │    │   CVE AUDIT        │            │
│  │   ────────────────│    │  ─────────────────│    │   ─────────────────│            │
│  │   • USN-XXXX-X     │───►│  • ubuntu-2404-    │    │   • OVAL scanning  │            │
│  │   • DSA-XXXX-X     │    │    main-security   │    │   • CVE correlation│            │
│  │   • Severity       │    │  • ubuntu-2404-    │    │   • Vulnerability  │            │
│  │   • CVE links      │    │    universe-sec    │    │     reports        │            │
│  │   • Packages       │    │                    │    │                    │            │
│  └────────────────────┘    └────────────────────┘    └────────────────────┘            │
│                                          │                                               │
│                                          │ Salt (4505/4506)                              │
│                                          ▼                                               │
│                              ┌────────────────────┐                                      │
│                              │    CLIENT VMs      │                                      │
│                              │  (Salt Minions)    │                                      │
│                              └────────────────────┘                                      │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

#### 7.5.2 Dettaglio Flusso per Fonte Dati

**USN (Ubuntu Security Notices)**

| Aspetto | Dettaglio |
|---------|-----------|
| **Source** | https://ubuntu.com/security/notices/rss.xml, https://ubuntu.com/security/cves.json |
| **Trigger** | Logic App ogni 6 ore |
| **Endpoint** | POST /api/sync/usn |
| **Dati Estratti** | USN ID, CVE list, Affected packages, Severity, Release date |
| **Mapping** | → errata, errata_cve, packages tables |

**DSA (Debian Security Advisories)**

| Aspetto | Dettaglio |
|---------|-----------|
| **Source** | https://security-tracker.debian.org/tracker/ |
| **Trigger** | Logic App daily 03:00, Timeout 30min |
| **Endpoint** | POST /api/sync/dsa/full |
| **Dati Estratti** | DSA ID, CVE list, Package, Fixed version, Urgency |
| **Note** | ~115,000 DSA (storico completo Debian) |

**NVD (National Vulnerability Database)**

| Aspetto | Dettaglio |
|---------|-----------|
| **Source** | https://services.nvd.nist.gov/rest/json/cves/2.0 |
| **Trigger** | Logic App daily 04:00 |
| **Endpoint** | POST /api/sync/nvd?batch_size=200&force=true |
| **Purpose** | Arricchimento CVE esistenti con CVSS scores |
| **Rate Limit** | 0.6s tra richieste (con API Key) |
| **Note** | 47K CVE, ~16 ore per sync completo iniziale |

**OVAL (Open Vulnerability Assessment Language)**

| Aspetto | Dettaglio |
|---------|-----------|
| **Source Ubuntu** | https://security-metadata.canonical.com/oval/ |
| **Source Debian** | https://www.debian.org/security/oval/ |
| **Trigger** | Logic App weekly (Domenica 02:00) |
| **Endpoint** | POST /api/sync/oval?platform=ubuntu, POST /api/sync/oval?platform=debian |
| **Use in UYUNI** | CVE Audit scanning per identificare sistemi vulnerabili |
| **Note** | Ubuntu ~5,400 definitions, Debian ~45,500 definitions |

#### 7.5.3 Schema Temporale Automazione

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           SCHEDULING GIORNALIERO                                         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  00:00 ─────────────────────────────────────────────────────────────────────────────────│
│    │                                                                                     │
│  00:30 │  ┌─────────────────────┐                                                       │
│    │   │  │ Cron: errata-push   │ Push errata to UYUNI                                  │
│  01:00 │  └─────────────────────┘                                                       │
│    │   │  ┌─────────────────────┐                                                       │
│    │   │  │ Cron: sync-channels │ Sync Ubuntu repositories                              │
│  02:00 │  └─────────────────────┘                                                       │
│    │   │  ┌─────────────────────┐ (Solo Domenica)                                       │
│    │   │  │ Logic: oval-sync    │ Sync OVAL definitions                                 │
│  03:00 │  └─────────────────────┘                                                       │
│    │   │  ┌─────────────────────┐                                                       │
│    │   │  │ Logic: dsa-sync     │ Sync Debian Security Advisories                       │
│  04:00 │  └─────────────────────┘                                                       │
│    │   │  ┌─────────────────────┐                                                       │
│    │   │  │ Logic: nvd-sync     │ Enrich CVE with CVSS scores                           │
│  05:00 │  └─────────────────────┘                                                       │
│    │                                                                                     │
│  06:00 ─────────────────────────────────────────────────────────────────────────────────│
│    │   │  ┌─────────────────────┐                                                       │
│    │   │  │ Logic: usn-sync     │ Sync Ubuntu Security Notices                          │
│  06:30 │  └─────────────────────┘                                                       │
│    │   │  ┌─────────────────────┐                                                       │
│    │   │  │ Cron: errata-push   │ Push new errata to UYUNI                              │
│    │                                                                                     │
│  12:00 ─────────────────────────────────────────────────────────────────────────────────│
│    │   │  ┌─────────────────────┐                                                       │
│    │   │  │ Logic: usn-sync     │ Sync Ubuntu Security Notices                          │
│  12:30 │  └─────────────────────┘                                                       │
│    │   │  ┌─────────────────────┐                                                       │
│    │   │  │ Cron: errata-push   │ Push new errata to UYUNI                              │
│    │                                                                                     │
│  18:00 ─────────────────────────────────────────────────────────────────────────────────│
│    │   │  ┌─────────────────────┐                                                       │
│    │   │  │ Logic: usn-sync     │ Sync Ubuntu Security Notices                          │
│  18:30 │  └─────────────────────┘                                                       │
│    │   │  ┌─────────────────────┐                                                       │
│    │   │  │ Cron: errata-push   │ Push new errata to UYUNI                              │
│    │                                                                                     │
│  24:00 ─────────────────────────────────────────────────────────────────────────────────│
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

#### 7.5.4 Database Schema Mapping

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              DATABASE SCHEMA MAPPING                                     │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  USN/DSA ──────────┐                                                                     │
│                    ▼                                                                     │
│              ┌──────────────┐                                                            │
│              │    errata    │                                                            │
│              ├──────────────┤          ┌──────────────┐                                 │
│              │ errata_id PK │──────────│  errata_cve  │                                 │
│              │ advisory_name│          ├──────────────┤         ┌──────────────┐        │
│              │ synopsis     │          │ errata_id FK │─────────│     cves     │        │
│              │ description  │          │ cve_id FK    │─────────├──────────────┤        │
│              │ severity     │          └──────────────┘         │ cve_id PK    │◄── NVD │
│              │ issue_date   │                                   │ cvss_score   │        │
│              │ pushed_to_   │                                   │ cvss_vector  │        │
│              │   uyuni      │                                   │ severity     │        │
│              └──────┬───────┘                                   │ nvd_enriched │        │
│                     │                                           └──────────────┘        │
│                     │ 1:N                                                               │
│                     ▼                                                                    │
│              ┌──────────────┐                                                            │
│              │   packages   │                                                            │
│              ├──────────────┤                                   ┌──────────────┐        │
│              │ package_id PK│                                   │     oval     │◄── OVAL│
│              │ errata_id FK │                                   ├──────────────┤        │
│              │ package_name │                                   │ oval_id PK   │        │
│              │ version      │                                   │ cve_ref      │        │
│              │ architecture │                                   │ platform     │        │
│              │ channel_label│                                   │ criteria     │        │
│              └──────────────┘                                   │ affected_ver │        │
│                                                                 └──────────────┘        │
│                                                                                          │
│  STATISTICHE:                                                                            │
│  • errata: 116,261 records (USN: 583, DSA: 115,678)                                     │
│  • cves: 47,845 records                                                                 │
│  • oval: 50,862 records (Ubuntu: 5,359, Debian: 45,503)                                 │
│  • packages: 140,937 records                                                            │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

#### 7.5.5 Flusso Operativo Numerato

| Step | Componente | Azione | Descrizione |
|------|------------|--------|-------------|
| **1** | Internet → Logic Apps | Fetch | Logic Apps schedulano chiamate alle fonti esterne |
| **2** | Logic Apps → Container Pubblico | HTTP POST | Trigger sync endpoints (USN/DSA/NVD/OVAL) |
| **3** | Container Pubblico → PostgreSQL | INSERT/UPDATE | Parsing e salvataggio dati nel database |
| **4** | Container Interno ← PostgreSQL | SELECT | Query errata pending da pushare |
| **5** | Container Interno → UYUNI | XML-RPC | Push errata via API client.errata.create() |
| **6** | UYUNI → Client VMs | Salt | Deploy patch ai sistemi gestiti |

---

## 8. INFRASTRUTTURA CLOUD TARGET

### 8.1 Architettura Target PSN Compliant

L'architettura target segue i principi del Polo Strategico Nazionale:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TENANT MASTER (HUB)                                       │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Subnet-Master-Server (10.100.1.0/24)                                   │ │
│  │ ├── Master Server (UYUNI) - Standard_D4s_v3                            │ │
│  │ ├── API Server (Flask) - ACI                                           │ │
│  │ └── Internal Load Balancer (HA)                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Subnet-Data (10.100.2.0/24)                                            │ │
│  │ ├── PostgreSQL Flexible Server (Private Endpoint)                      │ │
│  │ └── Storage Account (Backup, OVAL, Logs)                               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Subnet-Management (10.100.3.0/24)                                      │ │
│  │ └── Azure Bastion (accesso sicuro)                                     │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│                          │ Private Link                                      │
│                          ▼                                                   │
└──────────────────────────┼──────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TENANT CLIENT (SPOKE) - Per ogni cliente                  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Subnet-Proxy-Server (10.172.1.0/24)                                    │ │
│  │ ├── Proxy Server (Smart Proxy) - Standard_D2s_v3                       │ │
│  │ └── SPM Agent (automazione)                                            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Subnet-Client-VM (10.172.2.0/24)                                       │ │
│  │ └── Client VMs (Salt Minion)                                           │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Subnet-Test (10.172.3.0/24) - ISOLATA                                  │ │
│  │ └── VM Clone per P3 testing                                            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Principi di Sicurezza PSN Implementati

| Principio | Implementazione |
|-----------|-----------------|
| **Zero Trust** | Nessun IP pubblico, verifica identità sempre |
| **Network Segmentation** | VNet separate, subnet dedicate, NSG |
| **Defense in Depth** | NSG + Azure Firewall + Private Endpoints |
| **Least Privilege** | RBAC granulare, Managed Identities |
| **Encryption Everywhere** | TLS 1.3 in transit, CMK/BYOK at rest |
| **Private by Default** | Private Endpoints per tutti i servizi PaaS |
| **Centralized Logging** | Log Analytics + Sentinel |
| **Data Sovereignty** | Dati solo su territorio italiano |

### 8.3 Requisiti PSN Coperti

| ID | Requisito | Stato |
|----|-----------|-------|
| BR-001 | Hub & Spoke | ✅ |
| BR-002 | Firewall control | ✅ |
| BR-003 | Bastion + 2FA | ✅ |
| BR-004 | No public IP policy | ✅ |
| SR-PSN-017 | Network Security | ✅ |
| SR-PSN-046 | Data encryption | ✅ |
| SR-PSN-060 | Logging | ✅ |
| POG-PSN-007 | Data sovereignty Italy | ✅ |

---

## 9. PROCESSI DI CONFIGURAZIONE

### 9.1 Software Channels

I **Channels** sono repository di pacchetti software organizzati gerarchicamente:

```
Parent Channel (Base)
ubuntu-24.04-pool-amd64-uyuni                    ← 0 pacchetti (contenitore)
├── ubuntu-2404-amd64-main-uyuni                 ← ~6,000 pacchetti
├── ubuntu-2404-amd64-main-security-uyuni        ← ~7,600 pacchetti + errata
├── ubuntu-2404-amd64-main-updates-uyuni         ← ~9,000 pacchetti
├── ubuntu-2404-amd64-universe-uyuni             ← ~65,000 pacchetti
├── ubuntu-2404-amd64-universe-security-uyuni    ← errata sicurezza
├── ubuntu-2404-amd64-universe-updates-uyuni     ← ~7,400 pacchetti
└── ubuntu-2404-amd64-uyuni-client               ← Client Tools (venv-salt-minion)
```

**Tipi di Channel**:
- **Vendor**: Da repository ufficiali (SUSE Customer Center)
- **Custom**: Repository esterni (Ubuntu, Debian, RHEL)
- **Cloned**: Copia di altro channel (snapshot point-in-time)

### 9.2 Content Lifecycle Management (CLM)

CLM permette di gestire il ciclo di vita dei contenuti attraverso ambienti:

```
┌─────────────────────────────────────────────────────────────────┐
│                  CONTENT LIFECYCLE MANAGEMENT                    │
│                                                                  │
│   SOURCE          DEV           QA            PROD               │
│   CHANNELS    ENVIRONMENT   ENVIRONMENT   ENVIRONMENT            │
│      │            │             │             │                  │
│      ▼            ▼             ▼             ▼                  │
│  ┌──────┐    ┌──────┐      ┌──────┐      ┌──────┐              │
│  │ Sync │───►│ Build│─────►│Promote─────►│Promote│             │
│  │ Repo │    │ v1.0 │      │ v1.0 │      │ v1.0 │              │
│  └──────┘    └──────┘      └──────┘      └──────┘              │
│                  │             │             │                  │
│                  │  Test OK    │  QA OK      │                  │
│                  └─────────────┴─────────────┘                  │
│                                                                  │
│  Vantaggi:                                                       │
│  • Snapshot immutabili per ogni build                            │
│  • Promozione controllata con approvazioni                       │
│  • Rollback facile a versioni precedenti                         │
│  • Filtri granulari (escludi CVE specifici)                      │
└─────────────────────────────────────────────────────────────────┘
```

### 9.3 Activation Keys

Le **Activation Keys** sono template di configurazione per la registrazione client:

**Esempio**: `ak-ubuntu2404-prod`
- **Base Channel**: `ubuntu-24.04-pool-amd64-uyuni`
- **Child Channels**: security, updates, client-tools
- **System Groups**: production-servers, webservers
- **Config Channels**: base-hardening, monitoring-agent

**Workflow registrazione**:
1. Client esegue bootstrap script con activation key
2. UYUNI assegna automaticamente channels, gruppi, configurazioni
3. Sistema pronto per gestione centralizzata

### 9.4 System Groups

Raggruppamenti logici di sistemi per:

| Funzione | Descrizione |
|----------|-------------|
| **Targeting** | Applicare azioni a gruppi di sistemi |
| **RBAC** | Delegare gestione a team specifici |
| **Reporting** | Report per gruppo |
| **Scheduling** | Finestre di manutenzione per gruppo |

**Esempi di raggruppamento**:
- Per ambiente: dev-servers, qa-servers, prod-servers
- Per ruolo: webservers, databases, kubernetes-nodes
- Per location: datacenter-a, datacenter-b
- Per team: team-alpha, team-beta

### 9.5 Bootstrap Client

Procedura di registrazione client:

```bash
# 1. Pre-requisiti sul client
sudo su -
hostname -f                                    # Verifica hostname
ping -c 2 uyuni-server-test                   # Verifica connettività
nc -zv uyuni-server-test 4505                 # Verifica porta Salt

# 2. Scarica bootstrap script
curl -Sks https://uyuni-server/pub/bootstrap/bootstrap.sh -o /tmp/bootstrap.sh
chmod +x /tmp/bootstrap.sh

# 3. Esegui con activation key
/tmp/bootstrap.sh -a ak-ubuntu2404-prod

# 4. Su UYUNI server - accetta Salt key
salt-key -L                                   # Lista keys
salt-key -a <minion-id>                       # Accetta specifica
```
---
## 11. ATTIVITÀ MANCANTI

### 11.1 Alta Priorità

| Attività | Descrizione | Stato |
|----------|-------------|-------|
| **P1 - Active Environment Discovery** | Implementazione modulo discovery automatico | ⏳ Da fare |
| **P2 - Prioritization Engine** | Algoritmo prioritizzazione basato su CVSS e impatto | ⏳ Da fare |
| **P3 - Patch Testing Automation** | Automazione completa clone VM e test | ⏳ Da fare |
| **P4 - Deployment Automation** | Orchestrazione deployment con Salt | ⏳ Da fare |
| **Multi-Tenant Isolation** | Separazione completa per tenant/cliente | ⏳ Da fare |
| **Dashboard Grafana** | Visualizzazione metriche e KPI | 🔄 Parziale |

### 11.2 Media Priorità

| Attività | Descrizione | Stato |
|----------|-------------|-------|
| **Supporto Debian 12** | Estensione canali per Debian | ⏳ Da fare |
| **Supporto RHEL/Rocky** | Estensione per distribuzioni Red Hat | ⏳ Da fare |
| **Rollback automatico** | Procedura rollback post-deployment | ⏳ Da fare |
| **Notifiche/Alerting** | Sistema notifiche (email, Teams, Slack) | ⏳ Da fare |
| **API REST moderna** | Migrazione da XML-RPC a REST | ⏳ Da fare |

### 11.3 Bassa Priorità / Future

| Attività | Descrizione | Stato |
|----------|-------------|-------|
| **Compliance Reporting** | Report compliance (NIST, ISO) | ⏳ Futuro |
| **Integration ServiceNow** | Integrazione ITSM | ⏳ Futuro |
| **Machine Learning** | Predizione impatto patch | ⏳ Futuro |
| **Mobile App** | Dashboard mobile | ⏳ Futuro |

---

## 12. SUGGERIMENTI AGGIUNTIVI

### 12.1 Per la Presentazione

1. **Demo Live**: Preparare una demo del flusso sync USN → push UYUNI → visualizzazione errata

2. **Metriche di Impatto**: Evidenziare i numeri:
   - 116.000+ errata gestiti
   - 47.000+ CVE tracciati
   - Tempo medio sync: <5 minuti

3. **Confronto Before/After**: Mostrare come era la gestione patch prima vs dopo SPM

4. **ROI Potenziale**: Calcolare risparmio tempo/risorse con automazione

### 12.2 Argomenti da Approfondire

1. **Security Posture**: Come SPM migliora la security posture dell'organizzazione

2. **Compliance**: Mapping con requisiti PSN e standard internazionali

3. **Scalabilità**: Come l'architettura scala per centinaia di tenant

4. **Disaster Recovery**: Procedure di backup e ripristino

### 12.3 Documentazione Aggiuntiva Suggerita

1. **Runbook Operativo**: Procedure per operazioni quotidiane
2. **Troubleshooting Guide**: Problemi comuni e soluzioni
3. **API Reference**: Documentazione completa API SPM
4. **Training Material**: Materiale formazione per operatori

### 12.4 Prossimi Passi Consigliati

1. **Sprint P3**: Completare automazione patch testing
2. **PoC Multi-Tenant**: Validare isolamento con 2-3 tenant reali
3. **Performance Test**: Stress test con migliaia di sistemi
4. **Security Audit**: Revisione sicurezza architettura

---

## RIFERIMENTI

### Documentazione Interna
- `/GeneralDocumentation/Automated_Patch_Management_for_B2B_IaaS_Environments_v1.1.pdf`
- `/Uyuni/Teoria/UYUNI.md`
- `/Uyuni/Infrastructure-Design/Azure Security-First Architecture (Conforme PSN).md`
- `/Uyuni/README.md`

### Standard di Riferimento
- [NIST SP 800-40 Rev. 4](https://csrc.nist.gov/publications/detail/sp/800-40/rev-4/final)
- [ISO/IEC 27002](https://www.iso.org/standard/75652.html)
- [IEC 62443](https://www.iec.ch/cyber-security)
- [NERC CIP-007](https://www.nerc.com/pa/Stand/Pages/CIPStandards.aspx)

### Documentazione Esterna
- [UYUNI Project](https://www.uyuni-project.org/)
- [SaltStack Documentation](https://docs.saltproject.io/)
- [OVAL Language](https://oval.mitre.org/)
- [NVD - National Vulnerability Database](https://nvd.nist.gov/)
