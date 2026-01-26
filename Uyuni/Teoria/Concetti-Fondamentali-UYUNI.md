UYUNI supporta **molti sistemi operativi** come client:

| OS | Supporto | Note |
|----|----------|------|
| **SUSE Linux Enterprise** | ✅ Completo | Supporto nativo eccellente |
| **openSUSE Leap/Tumbleweed** | ✅ Completo | Supporto nativo eccellente |
| **Red Hat Enterprise Linux** | ✅ Completo | 7, 8, 9 |
| **CentOS / Rocky / Alma** | ✅ Completo | Errata disponibili |
| **Oracle Linux** | ✅ Completo | |
| **Ubuntu LTS** | ✅ Buono | 20.04, 22.04, 24.04 |
| **Debian** | ✅ Buono | 11, 12 |
| **Amazon Linux** | ✅ Buono | 2, 2023 |
| **Raspberry Pi OS** | ✅ Funziona | |
| **openEuler** | ✅ Nuovo | 22.03 |
**Il server UYUNI** gira su openSUSE, ma **può gestire client di qualsiasi OS supportato**.

## Architettura UYUNI
### 1.1 Componenti Principali

```
┌─────────────────────────────────────────────────────────────────┐
│                    UYUNI SERVER (Container)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Web UI     │  │  Taskomatic  │  │ Salt Master  │          │
│  │   (Tomcat)   │  │  (Scheduler) │  │              │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│         └────────────┬────┴─────────────────┘                   │
│                      │                                          │
│              ┌───────▼────────┐                                 │
│              │   PostgreSQL   │                                 │
│              │   Database     │                                 │
│              └───────┬────────┘                                 │
│                      │                                          │
│  ┌──────────────┐   │   ┌──────────────┐  ┌──────────────┐    │
│  │    Apache    │   │   │   Cobbler    │  │    Squid     │    │
│  │   (HTTPS)    │   │   │(Provisioning)│  │   (Cache)    │    │
│  └──────────────┘   │   └──────────────┘  └──────────────┘    │
│                     │                                          │
└─────────────────────┼──────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
   ┌─────────┐  ┌─────────┐  ┌─────────┐
   │ Client  │  │ Client  │  │ Client  │
   │ Ubuntu  │  │ Debian  │  │  RHEL   │
   │ (Salt)  │  │ (Salt)  │  │ (Salt)  │
   └─────────┘  └─────────┘  └─────────┘
```
### 1.2 Componenti Spiegati

- **Web UI (Tomcat)** :  Interfaccia grafica         
- **Taskomatic** : Scheduler di job asincroni
- **Salt Master** : Comunicazione con client
- **PostgreSQL** : Database centrale
- **Apache HTTPD** : Reverse proxy, serve repo
- **Cobbler** : PXE/Provisioning
- **Squid** : Cache pacchetti (opzionale)
### 1.3 Comunicazione con i Client

```
UYUNI Server                              Client (Salt Minion)
     │                                           │
     │  ◄──── Port 4505 (ZeroMQ PUB) ────────    │  Eventi/Comandi broadcast
     │                                           │
     │  ◄──── Port 4506 (ZeroMQ REQ) ────────    │  Risposte/Return data
     │                                           │
     │  ────► Port 443 (HTTPS) ──────────────►   │  Package download
     │                                           │
```

- UYUNI Salt: ZeroMQ persistent connection (client → server)

**Vantaggi Salt:**
- Scalabilità migliore (migliaia di client)
- Comunicazione real-time
- Minore overhead di connessione
- Event-driven architecture
## Concetti Chiave
### 2.1 Organizations (Multi-Tenancy)

```
┌─────────────────────────────────────────────────────────────┐
│                    UYUNI Server                             │
│                                                             │
│  ┌─────────────────┐    ┌─────────────────┐                 │
│  │  Organization A │    │  Organization B │                 │
│  │  (Tenant 1)     │    │  (Tenant 2)     │                 │
│  │                 │    │                 │                 │
│  │  - Users        │    │  - Users        │                 │
│  │  - Systems      │    │  - Systems      │                 │
│  │  - Channels     │    │  - Channels     │                 │
│  │  - Act. Keys    │    │  - Act. Keys    │                 │
│  │  - Config Ch.   │    │  - Config Ch.   │                 │
│  └─────────────────┘    └─────────────────┘                 │
│           │                      │                          │
│           └──────────┬───────────┘                          │
│                      │                                      │
│              Trust Relationship                             │
│              (Channel Sharing)                              │
└─────────────────────────────────────────────────────────────┘
```

- Tenant isolation : Organization
- Channel sharing : Trust + Sharing
### 2.2 Software Channels (= Products + Repositories)
**Struttura Gerarchica:**

```
┌─────────────────────────────────────────────────────────────┐
│                    Parent Channel                           │
│                    (Base Channel)                           │
│                    es: ubuntu-2404-amd64                    │
│                                                             │
│    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│    │Child Channel│  │Child Channel│  │Child Channel│        │
│    │ubuntu-2404  │  │ubuntu-2404  │  │ubuntu-2404  │        │
│    │-security    │  │-updates     │  │-backports   │        │
│    └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Mappatura:**

| Foreman/Katello | UYUNI | Note |
|-----------------|-------|------|
| **Product** | Parent Channel | Contenitore logico |
| **Repository** | Child Channel | Repository effettivo |
| **Sync Plan** | Channel → Repositories → Sync | Scheduling sync |
**Tipi di Channel:**

| Tipo | Descrizione | Esempio |
|------|-------------|---------|
| **Vendor Channel** | Da SUSE/RH (via SCC) | SLES 15 SP5 |
| **Custom Channel** | Creato manualmente | My-Ubuntu-2404 |
| **Cloned Channel** | Copia di un altro | ubuntu-2404-prod |

### 2.3 Content Lifecycle Management (= Content Views + Lifecycle Environments)

**Questo è CRITICO da capire bene!**

```
┌────────────────────────────────────────────────────────────────┐
│                    CLM Project                                  │
│                    (= Content View)                             │
│                                                                 │
│  Sources:        Filters:           Environments:               │
│  ┌──────────┐   ┌──────────────┐   ┌─────┐ ┌─────┐ ┌──────┐   │
│  │ Channel  │──►│ Include/Excl │──►│ DEV │►│ QA  │►│ PROD │   │
│  │ ubuntu   │   │ by package   │   └─────┘ └─────┘ └──────┘   │
│  │ -2404    │   │ by date      │                               │
│  │ -updates │   │ by CVE       │   Build      Promote          │
│  └──────────┘   └──────────────┘                               │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

**Workflow CLM:**

```
1. DEFINE      2. FILTER       3. BUILD        4. PROMOTE
   Sources  →     Rules     →    Snapshot  →     Stages
   
   Channels      Include:        Crea "point     DEV → QA → PROD
   da usare      - packages      in time"        
                 - by date       immutabile      
                 Exclude:                        
                 - CVE-xxx                       
```

**Mappatura Dettagliata:**

| Foreman/Katello | UYUNI CLM | Funzione |
|-----------------|-----------|----------|
| Content View | CLM Project | Container di filtri |
| Filters | CLM Filters | Regole include/exclude |
| Publish | Build | Crea snapshot |
| Lifecycle Environment | CLM Environment | DEV/QA/PROD |
| Promote | Promote | Sposta tra environment |
| Composite Content View | CLM Project con multi-source | Aggregazione |

**Tipi di Filtri in UYUNI:**

| Filtro | Foreman | UYUNI | Per Ubuntu/Debian |
|--------|---------|-------|-------------------|
| By Package Name | ✅ | ✅ | ✅ Funziona |
| By Package Version | ✅ | ✅ | ✅ Funziona |
| By Date | ✅ | ✅ | ✅ Funziona |
| By Errata Type | ✅ | ✅ | ❌ No errata Deb |
| By CVE | ✅ | ✅ | ✅ Funziona! |

### 2.4 Activation Keys

Identico concetto a Foreman:

```
┌─────────────────────────────────────────────────────────────┐
│                    Activation Key                            │
│                    "ak-ubuntu2404-prod"                      │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ Base Channel    │  │ Child Channels  │                   │
│  │ ubuntu-2404-prod│  │ - security      │                   │
│  │                 │  │ - updates       │                   │
│  └─────────────────┘  └─────────────────┘                   │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ System Groups   │  │ Config Channels │                   │
│  │ - webservers    │  │ - base-config   │                   │
│  │ - production    │  │ - ssh-hardening │                   │
│  └─────────────────┘  └─────────────────┘                   │
│                                                              │
│  Contact Method: default (Salt)                              │
│  Universal Default: No                                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.5 System Groups (= Host Collections + Host Groups)

| Foreman/Katello | UYUNI | Note |
|-----------------|-------|------|
| Host Collection | System Group | Raggruppamento statico |
| Host Group | System Group + Activation Key | Template di configurazione |
| Smart Class Parameter | Pillar | Variabili per host/gruppo |

**UYUNI usa System Groups per tutto:**
- Targeting azioni
- Reporting
- RBAC
- Patch scheduling

### 2.6 Patches/Errata

```
┌─────────────────────────────────────────────────────────────┐
│                    Patch/Errata                              │
│                                                              │
│  Advisory ID: RHSA-2024:1234                                │
│  Type: Security                                              │
│  Severity: Critical                                          │
│  CVEs: CVE-2024-1111, CVE-2024-1112                         │
│                                                              │
│  Affected Packages:                                          │
│  - openssl-1.1.1k-1.el8 → openssl-1.1.1k-2.el8             │
│  - openssl-libs-1.1.1k-1.el8 → openssl-libs-1.1.1k-2.el8   │
│                                                              │
│  Affected Systems: 47                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Tipi di Patch:**

| Tipo | Descrizione | Priorità |
|------|-------------|----------|
| **Security** | Vulnerabilità (CVE) | 🔴 Alta |
| **Bugfix** | Correzione bug | 🟡 Media |
| **Enhancement** | Nuove feature | 🟢 Bassa |

**Per Ubuntu/Debian:**
- I "patch" esistono come advisory (USN, DSA)
- **Non sono importati automaticamente** in UYUNI
- **CVE Audit OVAL** funziona e mostra le vulnerabilità
- Puoi importare errata manualmente con script esterni

### 2.7 CVE Audit (OVAL)

**Questo è il punto di forza di UYUNI per Ubuntu/Debian!**

```
CVE Audit funziona così:

1. UYUNI scarica OVAL data:
   - Canonical (Ubuntu)
   - Debian Security Team
   - SUSE
   - Red Hat

2. Analizza i pacchetti installati sui client

3. Correla con CVE database

4. Mostra: "Sistema X ha CVE-2024-xxxx"
```

**Differenza Errata vs CVE Audit:**

| Aspetto | Errata | CVE Audit |
|---------|--------|-----------|
| Dice "cosa aggiornare" | ✅ Bundle di pacchetti | ❌ Solo CVE ID |
| Dice "sei vulnerabile" | ✅ | ✅ |
| Ubuntu/Debian | ❌ Non nativo | ✅ Funziona! |
| Severity info | ✅ | ✅ |
| One-click fix | ✅ "Apply Errata" | ⚠️ Manual package update |

### 2.8 Salt States e Configuration Channels

**Configuration Management in UYUNI:**

```
┌─────────────────────────────────────────────────────────────┐
│                Configuration Channel                         │
│                "webserver-config"                            │
│                                                              │
│  /etc/nginx/nginx.conf                                      │
│  /etc/nginx/sites-available/default                         │
│  /etc/ssl/certs/server.crt                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  Salt State                                  │
│                  "webserver.sls"                             │
│                                                              │
│  nginx:                                                      │
│    pkg.installed: []                                         │
│    service.running:                                          │
│      - enable: True                                          │
│      - require:                                              │
│        - pkg: nginx                                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

| Foreman | UYUNI | Note |
|---------|-------|------|
| Puppet Classes | Salt States | Configuration Management |
| Ansible Roles | Salt Formulas | Riutilizzabili |
| Smart Variables | Pillars | Variabili |
| Facts | Grains | Info sistema |
| Template Files | Jinja Templates | Templating |

---

## Parte 3: CLI Tools

### 3.1 Comandi Principali

| Tool | Funzione | Dove lo esegui |
|------|----------|----------------|
| `mgradm` | Gestione server UYUNI | Host container |
| `mgrctl` | Interazione con container | Host container |
| `spacecmd` | CLI amministrazione | Dentro container |
| `spacewalk-*` | Vari tool legacy | Dentro container |

### 3.2 Esempi Pratici

```bash
# Status server
mgradm status

# Accesso shell container
mgrctl term

# Dentro il container:
spacecmd -u admin -p password system_list
spacecmd softwarechannel_list
spacecmd errata_list

# Sync canale
spacewalk-repo-sync -c ubuntu-2404-amd64-main

# Aggiungere canali comuni
spacewalk-common-channels -u admin -p password -a amd64 'ubuntu-2404*'
```

---

## Parte 4: Flusso Operativo Tipico

### 4.1 Setup Iniziale (una tantum)

```
1. Crea Organization(s)
         │
         ▼
2. Crea/Sincronizza Channels
   - spacewalk-common-channels per Ubuntu
   - Sync manuale o schedulato
         │
         ▼
3. Configura CLM (opzionale ma raccomandato)
   - Crea Project
   - Definisci Environments (DEV/QA/PROD)
   - Crea Filters
   - Build iniziale
         │
         ▼
4. Crea Activation Keys
   - Una per environment
   - Associa channels
         │
         ▼
5. Registra Client
   - Bootstrap script
   - salt-minion install
```

### 4.2 Operazioni Ricorrenti

```
Weekly/Monthly:
┌────────────────────────────────────────┐
│ 1. Sync Channels (automatico/manuale)  │
│         │                              │
│         ▼                              │
│ 2. CVE Audit - Verifica vulnerabilità  │
│         │                              │
│         ▼                              │
│ 3. CLM Build - Nuovo snapshot DEV      │
│         │                              │
│         ▼                              │
│ 4. Test in DEV                         │
│         │                              │
│         ▼                              │
│ 5. Promote DEV → QA → PROD             │
│         │                              │
│         ▼                              │
│ 6. Schedule Patch su sistemi PROD      │
│         │                              │
│         ▼                              │
│ 7. Verifica compliance                 │
└────────────────────────────────────────┘
```

---

## Parte 5: Confronto Finale

### Feature Matrix per il Tuo Caso

| Feature | Foreman/Katello | UYUNI | Per Ubuntu/Debian |
|---------|-----------------|-------|-------------------|
| Repo Sync | ✅ | ✅ | ✅ Entrambi |
| Content Views/CLM | ✅ | ✅ | ⚠️ Filtri limitati |
| Errata Management | ⚠️ Script | ⚠️ Script | ⚠️ Entrambi |
| **CVE Audit** | ⚠️ Limitato | ✅ OVAL | ✅ **UYUNI meglio** |
| Remote Execution | ✅ SSH | ✅ Salt | ✅ Salt più potente |
| Config Management | ✅ Puppet/Ansible | ✅ Salt | ✅ Entrambi |
| Multi-tenancy | ✅ | ✅ | ✅ Entrambi |
| Web UI | ✅ | ✅ | ✅ Entrambi |
| Architettura | ⚠️ Complessa | ✅ Container | ✅ UYUNI più semplice |

---

## Prossimi Passi Suggeriti

Ora che hai i concetti base, ti consiglio questo ordine di apprendimento pratico:

### Settimana 1-2: Hands-On Base
1. **[Guida 2]** Registra il primo client Ubuntu sul tuo server di test
2. **[Guida 3]** Esplora la Web UI e i comandi base
3. **[Guida 4]** Crea i primi canali per Ubuntu 24.04

### Settimana 3-4: Content Management
4. **[Guida 5]** Content Lifecycle Management completo
5. **[Guida 6]** Activation Keys e System Groups
6. **[Guida 7]** CVE Audit in pratica

### Settimana 5-6: Operations
7. **[Guida 8]** Patch Management workflow
8. **[Guida 9]** Salt Remote Commands
9. **[Guida 10]** Primo Salt State

---

## Risorse Ufficiali

- [Documentazione UYUNI](https://www.uyuni-project.org/uyuni-docs/)
- [Client Supportati](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/supported-features.html)
- [Ubuntu Features](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/supported-features-ubuntu.html)
- [Debian Features](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/supported-features-debian.html)
- [Salt Documentation](https://docs.saltproject.io/)

---

*Prossima guida: Registrazione primo client Ubuntu 24.04*

**Vuoi che proceda con la Guida 2 (registrazione client) o preferisci approfondire qualche concetto di questa guida?**
