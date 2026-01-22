# Security Patch Manager - Infrastructure Design

## Azure Security-First Architecture

Questo documento definisce l'architettura infrastrutturale del Security Patch Manager (SPM) per ambienti B2B IaaS nel contesto PSN, rispettando i principi di sicurezza Azure.

---

## 1. PRINCIPI DI SICUREZZA AZURE APPLICATI

| Principio | Implementazione |
|-----------|-----------------|
| **Zero Trust** | Nessun IP pubblico per risorse interne, verifica identità sempre |
| **Network Segmentation** | VNet separate, subnet dedicate, NSG per ogni subnet |
| **Defense in Depth** | Multi-layer: NSG + Azure Firewall + Private Endpoints |
| **Least Privilege** | RBAC granulare, Managed Identities, no permanent access |
| **Encryption Everywhere** | TLS 1.3 in transit, encryption at rest con CMK |
| **Private by Default** | Private Endpoints per tutti i servizi PaaS |
| **Centralized Logging** | Log Analytics workspace condiviso |

---

## 2. ARCHITETTURA HIGH-LEVEL

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AZURE SUBSCRIPTION                                  │
│                                                                                  │
│  ┌──────────────────────────────────────┐    ┌──────────────────────────────────┐
│  │         TENANT MASTER (Hub)          │    │      TENANT CLIENT (Spoke)       │
│  │         ══════════════════           │    │      ═══════════════════         │
│  │                                      │    │                                  │
│  │  ┌─────────────────────────────┐    │    │  ┌─────────────────────────────┐ │
│  │  │    VNet-Master-Hub          │    │    │  │    VNet-Client-Spoke        │ │
│  │  │    10.100.0.0/16            │    │    │  │    10.172.0.0/16            │ │
│  │  │                             │◄───┼────┼──┤                             │ │
│  │  │  ┌───────────────────────┐  │    │    │  │  ┌───────────────────────┐  │ │
│  │  │  │ Subnet-Master-Server  │  │ Private │  │  │ Subnet-Proxy-Server   │  │ │
│  │  │  │ 10.100.1.0/24         │  │  Link   │  │  │ 10.172.1.0/24         │  │ │
│  │  │  │ ┌──────────────────┐  │  │    │    │  │  │ ┌──────────────────┐  │  │ │
│  │  │  │ │  Master Server   │  │  │    │    │  │  │ │  Proxy Server    │  │  │ │
│  │  │  │ │  (Foreman/UYUNI) │  │  │    │    │  │  │ │  (Smart Proxy)   │  │  │ │
│  │  │  │ └──────────────────┘  │  │    │    │  │  │ └──────────────────┘  │  │ │
│  │  │  └───────────────────────┘  │    │    │  │  └───────────────────────┘  │ │
│  │  │                             │    │    │  │                             │ │
│  │  │  ┌───────────────────────┐  │    │    │  │  ┌───────────────────────┐  │ │
│  │  │  │ Subnet-Data           │  │    │    │  │  │ Subnet-Client-VM      │  │ │
│  │  │  │ 10.100.2.0/24         │  │    │    │  │  │ 10.172.2.0/24         │  │ │
│  │  │  │ ┌──────────────────┐  │  │    │    │  │  │ ┌────┐ ┌────┐ ┌────┐ │  │ │
│  │  │  │ │  PostgreSQL      │  │  │    │    │  │  │ │VM1 │ │VM2 │ │VM3 │ │  │ │
│  │  │  │ │  (Private EP)    │  │  │    │    │  │  │ └────┘ └────┘ └────┘ │  │ │
│  │  │  │ └──────────────────┘  │  │    │    │  │  └───────────────────────┘  │ │
│  │  │  └───────────────────────┘  │    │    │  │                             │ │
│  │  │                             │    │    │  │  ┌───────────────────────┐  │ │
│  │  │  ┌───────────────────────┐  │    │    │  │  │ Subnet-Test           │  │ │
│  │  │  │ Subnet-Management     │  │    │    │  │  │ 10.172.3.0/24         │  │ │
│  │  │  │ 10.100.3.0/24         │  │    │    │  │  │ ┌──────────────────┐  │  │ │
│  │  │  │ ┌──────────────────┐  │  │    │    │  │  │ │  Test VM Clone   │  │  │ │
│  │  │  │ │  Azure Bastion   │  │  │    │    │  │  │ │  (P3 Testing)    │  │  │ │
│  │  │  │ └──────────────────┘  │  │    │    │  │  │ └──────────────────┘  │  │ │
│  │  │  └───────────────────────┘  │    │    │  │  └───────────────────────┘  │ │
│  │  │                             │    │    │  │                             │ │
│  │  └─────────────────────────────┘    │    │  └─────────────────────────────┘ │
│  │                                      │    │                                  │
│  └──────────────────────────────────────┘    └──────────────────────────────────┘
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                        SHARED SERVICES                                     │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐  │  │
│  │  │ Key Vault   │ │ Log         │ │ Private DNS │ │ Azure Container     │  │  │
│  │  │ (Secrets)   │ │ Analytics   │ │ Zones       │ │ Registry            │  │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. DETTAGLIO COMPONENTI

### 3.1 TENANT MASTER (Hub)

Il Tenant Master è il centro di controllo del sistema SPM.

#### Subnet-Master-Server (10.100.1.0/24)

| Componente | Tipo | Descrizione |
|------------|------|-------------|
| **Master Server** | VM (Standard_D4s_v3) | Foreman/Katello o UYUNI Server |
| **API Server** | ACI / VM | Flask API per sync errata (attuale) |
| **Load Balancer** | Internal LB | Distribuzione carico se HA |

**NSG Rules:**
```
Inbound:
- Allow TCP 443 from Subnet-Proxy-Server (Private Link)
- Allow TCP 5000 from Subnet-Proxy-Server (API)
- Allow TCP 22 from Subnet-Management (Bastion)
- Deny all other

Outbound:
- Allow TCP 443 to Internet (sync USN/DSA/NVD)
- Allow TCP 5432 to Subnet-Data (PostgreSQL)
- Deny all other
```

#### Subnet-Data (10.100.2.0/24)

| Componente | Tipo | Descrizione |
|------------|------|-------------|
| **PostgreSQL** | Azure Database for PostgreSQL Flexible | Database errata, NVD, cache |
| **Storage Account** | Blob Storage | Backup, OVAL files, logs |

**Accesso:**
- Solo via Private Endpoint
- No public access
- Encryption con Customer Managed Key (CMK)

#### Subnet-Management (10.100.3.0/24)

| Componente | Tipo | Descrizione |
|------------|------|-------------|
| **Azure Bastion** | Standard | Accesso sicuro alle VM senza IP pubblici |
| **Jump Box** | VM (optional) | Per troubleshooting avanzato |

---

### 3.2 TENANT CLIENT (Spoke)

Ogni tenant cliente ha una VNet spoke dedicata.

#### Subnet-Proxy-Server (10.172.1.0/24)

| Componente | Tipo | Descrizione |
|------------|------|-------------|
| **Proxy Server (Smart Proxy)** | VM (Standard_D2s_v3) | Esegue P2, P3, P4 |
| **SPM Agent** | Container/Service | Automazione patch management |

**Funzionalità:**
- Riceve policy dal Master
- Esegue discovery locale
- Gestisce Priority Patches List
- Coordina testing (P3)
- Esegue deployment (P4)

#### Subnet-Client-VM (10.172.2.0/24)

| Componente | Tipo | Descrizione |
|------------|------|-------------|
| **Client VMs** | VM varie | Macchine gestite dal SPM |

**Requisiti VM:**
- Salt minion o Ansible target
- SSH key auth (Linux) / WinRM (Windows)
- Agent monitoring (Azure Monitor Agent)

#### Subnet-Test (10.172.3.0/24) - CRITICO PER P3

| Componente | Tipo | Descrizione |
|------------|------|-------------|
| **Test VM Clone** | VM Snapshot/Clone | Copia VM per test patch |
| **Monitoring Agent** | Azure Monitor | Baseline e metriche post-patch |

**Isolamento:**
- NSG: DENY all traffic to/from Subnet-Client-VM
- Rete completamente isolata
- Solo accesso da Proxy Server

---

## 4. NETWORK SECURITY DESIGN

### 4.1 Network Security Groups (NSG)

```
┌─────────────────────────────────────────────────────────────────┐
│                    NSG ARCHITECTURE                              │
│                                                                  │
│  ┌──────────────────┐     ┌──────────────────┐                  │
│  │ NSG-Master       │     │ NSG-Proxy        │                  │
│  │ ───────────────  │     │ ───────────────  │                  │
│  │ In: 443,5000     │     │ In: 443,22       │                  │
│  │     from Proxy   │◄────┤     from Master  │                  │
│  │ Out: 443 Internet│     │ Out: 22 to VMs   │                  │
│  │      5432 to DB  │     │      443 to Mstr │                  │
│  └──────────────────┘     └──────────────────┘                  │
│           │                        │                             │
│           │                        ▼                             │
│           │               ┌──────────────────┐                  │
│           │               │ NSG-Client-VM    │                  │
│           │               │ ───────────────  │                  │
│           │               │ In: 22 from Proxy│                  │
│           │               │ Out: 80,443 Repos│                  │
│           │               └──────────────────┘                  │
│           │                                                      │
│           ▼               ┌──────────────────┐                  │
│  ┌──────────────────┐     │ NSG-Test         │                  │
│  │ NSG-Data         │     │ ───────────────  │                  │
│  │ ───────────────  │     │ In: 22 from Proxy│                  │
│  │ In: 5432 from    │     │ Out: DENY ALL    │ ← ISOLATO        │
│  │     Master only  │     │     (no internet)│                  │
│  │ Out: DENY ALL    │     └──────────────────┘                  │
│  └──────────────────┘                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Azure Private Link

Comunicazione sicura tra Tenant Master e Tenant Client:

```
Master Server ──► Private Link Service ──► Private Endpoint ──► Proxy Server
                  (espone servizio)         (consuma servizio)
```

**Configurazione:**
- Private Link Service sul Master Server (port 443, 5000)
- Private Endpoint nel Tenant Client
- DNS privato per risoluzione nomi

### 4.3 Azure Firewall (Hub)

Se architettura Hub-Spoke completa:

```
Internet ◄──► Azure Firewall ◄──► VNet-Master-Hub
                    │
                    └──► VNet-Client-Spoke (via peering)
```

**Rules:**
- DNAT: nessuna (no inbound da internet)
- Application Rules:
  - Allow ubuntu.com/security/* (USN sync)
  - Allow security-tracker.debian.org (DSA sync)
  - Allow nvd.nist.gov (NVD sync)
  - Allow security-metadata.canonical.com (OVAL sync)
- Network Rules:
  - Allow TCP 443 outbound per sync

---

## 5. IDENTITY & ACCESS MANAGEMENT

### 5.1 Azure AD / Entra ID Integration

```
┌─────────────────────────────────────────────────────────────────┐
│                    IDENTITY ARCHITECTURE                         │
│                                                                  │
│  ┌─────────────────┐     ┌─────────────────┐                    │
│  │ Azure AD Tenant │     │ Azure AD Groups │                    │
│  │                 │     │                 │                    │
│  │ ┌─────────────┐ │     │ SPM-Admins      │──► Full Access     │
│  │ │ Users       │ │     │ SPM-Operators   │──► P2,P3,P4 only   │
│  │ │ ──────────  │ │     │ SPM-Viewers     │──► Read-only       │
│  │ │ admin@...   │ │     │ SPM-Auditors    │──► Logs only       │
│  │ │ operator@...│ │     └─────────────────┘                    │
│  │ └─────────────┘ │                                             │
│  └─────────────────┘                                             │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Managed Identities                                          ││
│  │ ─────────────────                                           ││
│  │                                                              ││
│  │  Master-Server-MI ──► KeyVault: Get secrets                 ││
│  │                   ──► Storage: Read/Write blobs             ││
│  │                   ──► PostgreSQL: db_owner                  ││
│  │                                                              ││
│  │  Proxy-Server-MI  ──► KeyVault: Get secrets                 ││
│  │                   ──► Master API: Authenticated calls       ││
│  │                   ──► VM Snapshots: Create/Delete           ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 RBAC Assignments

| Role | Scope | Permissions |
|------|-------|-------------|
| SPM-Admins | Subscription | Contributor |
| SPM-Operators | Resource Groups | VM Contributor, Network Contributor |
| SPM-Viewers | Resource Groups | Reader |
| Proxy-Server-MI | VM RG | Virtual Machine Contributor (per snapshots) |

---

## 6. DATA PROTECTION

### 6.1 Azure Key Vault

Secrets gestiti:

| Secret | Uso |
|--------|-----|
| `db-connection-string` | PostgreSQL connection |
| `uyuni-api-password` | UYUNI XML-RPC auth |
| `nvd-api-key` | NVD API authentication |
| `ssh-private-key` | Accesso VM Linux |
| `winrm-credentials` | Accesso VM Windows |

**Access Policy:**
- Master-Server-MI: Get, List
- Proxy-Server-MI: Get
- SPM-Admins: All operations

### 6.2 Encryption

| Data | Encryption |
|------|------------|
| PostgreSQL | TDE + CMK |
| Blob Storage | SSE + CMK |
| VM Disks | Azure Disk Encryption |
| In Transit | TLS 1.3 |

---

## 7. MONITORING & LOGGING

### 7.1 Log Analytics Workspace

Tutti i log centralizzati:

```
┌─────────────────────────────────────────────────────────────────┐
│                 LOG ANALYTICS WORKSPACE                          │
│                 ═══════════════════════                          │
│                                                                  │
│  Sources:                                                        │
│  ├── Azure Activity Logs                                         │
│  ├── NSG Flow Logs                                               │
│  ├── Azure Firewall Logs                                         │
│  ├── VM Diagnostics (Azure Monitor Agent)                        │
│  ├── PostgreSQL Logs                                             │
│  ├── Key Vault Audit Logs                                        │
│  └── Application Logs (SPM API)                                  │
│                                                                  │
│  Alerts:                                                         │
│  ├── Failed patch deployment                                     │
│  ├── P3 test failure                                             │
│  ├── Unauthorized access attempt                                 │
│  ├── NSG deny events spike                                       │
│  └── VM health degradation                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Azure Monitor Alerts

| Alert | Condition | Action |
|-------|-----------|--------|
| Patch Deployment Failed | Custom metric from API | Email + Teams |
| P3 Test Failed | Custom metric | Email |
| High CPU on Master | CPU > 80% for 5min | Email |
| DB Connection Failed | Availability < 99% | PagerDuty |

---

## 8. DEPLOYMENT ARCHITECTURE PER MODULI SPM

### 8.1 Mapping Componenti → Moduli

```
┌─────────────────────────────────────────────────────────────────┐
│                    SPM MODULES DEPLOYMENT                        │
│                                                                  │
│  TENANT MASTER                     TENANT CLIENT                 │
│  ────────────                      ─────────────                 │
│                                                                  │
│  ┌──────────────────┐             ┌──────────────────┐          │
│  │ Master Server    │             │ Proxy Server     │          │
│  │ ════════════════ │             │ ════════════════ │          │
│  │                  │             │                  │          │
│  │ • NVD Discovery  │────────────►│ • P2 Execution   │          │
│  │   (sync NVD DB)  │   policy    │   (prioritize)   │          │
│  │                  │   push      │                  │          │
│  │ • Errata Sync    │             │ • P3 Coordinator │          │
│  │   (USN/DSA/OVAL) │             │   (test mgmt)    │          │
│  │                  │             │                  │          │
│  │ • Central DB     │◄────────────│ • P4 Executor    │          │
│  │   (PostgreSQL)   │   status    │   (deployment)   │          │
│  │                  │   report    │                  │          │
│  │ • Dashboard      │             │ • Monitoring     │          │
│  │   (Visualization)│             │   Agent          │          │
│  │                  │             │                  │          │
│  └──────────────────┘             └────────┬─────────┘          │
│                                            │                     │
│                                            ▼                     │
│                              ┌──────────────────────────┐       │
│                              │      Client VMs          │       │
│                              │      ══════════          │       │
│                              │  ┌────┐ ┌────┐ ┌────┐   │       │
│                              │  │VM1 │ │VM2 │ │VM3 │   │       │
│                              │  └────┘ └────┘ └────┘   │       │
│                              └──────────────────────────┘       │
│                                            │                     │
│                              ┌─────────────┴─────────────┐      │
│                              │      Test Subnet          │      │
│                              │      ═══════════          │      │
│                              │  ┌──────────────────────┐ │      │
│                              │  │ VM Clone (Snapshot)  │ │      │
│                              │  │ • P3 Test Execution  │ │      │
│                              │  │ • Isolated Network   │ │      │
│                              │  └──────────────────────┘ │      │
│                              └───────────────────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 Flusso P3 - Patch Testing (Dettaglio Infrastruttura)

```
┌─────────────────────────────────────────────────────────────────┐
│                    P3 - PATCH TESTING FLOW                       │
│                                                                  │
│  1. Proxy riceve Priority Patches List                          │
│     │                                                            │
│     ▼                                                            │
│  2. Per ogni VM target:                                          │
│     │                                                            │
│     ├──► Crea Snapshot VM ──────────────────────────────────┐   │
│     │    (Azure API: az snapshot create)                    │   │
│     │                                                        │   │
│     ├──► Crea VM Clone in Subnet-Test ◄─────────────────────┘   │
│     │    (az vm create --source-snapshot)                        │
│     │                                                            │
│     ├──► Configura NSG isolamento totale                         │
│     │    (deny all except from Proxy)                            │
│     │                                                            │
│     ├──► Avvia Azure Monitor baseline collection                 │
│     │    (CPU, RAM, disk, network, services)                     │
│     │                                                            │
│     ├──► Installa patch su Clone                                 │
│     │    (apt/yum/zypper via SSH)                                │
│     │                                                            │
│     ├──► Periodo stabilizzazione (configurable)                  │
│     │                                                            │
│     ├──► Confronta metriche vs baseline                          │
│     │    │                                                       │
│     │    ├── OK ──► Patch APPROVED                               │
│     │    │                                                       │
│     │    └── KO ──► Patch FAILED + report                        │
│     │                                                            │
│     └──► Cleanup: Delete Clone VM + Snapshot                     │
│                                                                  │
│  3. Output: List Tested Patch (approved/failed)                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 9. SIZING RECOMMENDATIONS

### 9.1 Tenant Master

| Componente | SKU | vCPU | RAM | Storage |
|------------|-----|------|-----|---------|
| Master Server | Standard_D4s_v3 | 4 | 16 GB | 256 GB SSD |
| PostgreSQL | GP_Gen5_4 | 4 | 20 GB | 512 GB |
| Storage Account | Standard_LRS | - | - | 1 TB |

### 9.2 Tenant Client (per tenant)

| Componente | SKU | vCPU | RAM | Storage |
|------------|-----|------|-----|---------|
| Proxy Server | Standard_D2s_v3 | 2 | 8 GB | 128 GB SSD |
| Test VM | Same as target | Variable | Variable | Variable |

---

## 10. COST OPTIMIZATION

### 10.1 Strategie

| Strategia | Risparmio | Applicazione |
|-----------|-----------|--------------|
| Reserved Instances | 30-60% | Master Server, Proxy Server |
| Auto-shutdown | Variable | Test VMs (shutdown after test) |
| Spot VMs | 60-90% | Test VMs (non-critical) |
| Storage tiering | 30-50% | Cold storage per backup vecchi |

### 10.2 Test VM Lifecycle

```
Test VM creata ──► Test eseguito ──► Test completato ──► VM eliminata
     │                                                        │
     └────────────────── MAX 4 ore ───────────────────────────┘
```

---

## 11. DISASTER RECOVERY

### 11.1 Backup Strategy

| Componente | Frequenza | Retention | Tipo |
|------------|-----------|-----------|------|
| PostgreSQL | Daily | 30 giorni | Geo-redundant |
| Master Server | Weekly | 4 settimane | Azure Backup |
| Configuration | On change | Unlimited | Git repo |

### 11.2 RTO/RPO

| Componente | RTO | RPO |
|------------|-----|-----|
| Master Server | 4h | 24h |
| PostgreSQL | 1h | 1h |
| Proxy Server | 2h | N/A (stateless) |

---

## 12. COMPLIANCE MAPPING

| Requisito | Standard | Implementazione |
|-----------|----------|-----------------|
| Network Isolation | ISO 27001, NIST | VNet separation, NSG, Private Link |
| Encryption | GDPR, ISO 27001 | TLS 1.3, CMK, Azure Disk Encryption |
| Access Control | ISO 27001, NIST | Azure AD, RBAC, MFA |
| Audit Logging | SOC 2, ISO 27001 | Log Analytics, Key Vault audit |
| Patch Management | NIST 800-40 | SPM framework (P2, P3, P4) |

---

## 13. DIAGRAMMA PER DRAW.IO

Struttura consigliata per creare il diagramma in Draw.io:

```
Layers:
├── L1: Azure Subscription boundary
├── L2: Tenant Master (VNet + Subnets)
├── L3: Tenant Client (VNet + Subnets)
├── L4: Shared Services
├── L5: Network connections (Private Link, Peering)
└── L6: Security components (NSG, Firewall, Bastion)

Icone Azure da usare:
- Virtual Network
- Subnet
- Virtual Machine
- Azure Database for PostgreSQL
- Key Vault
- Storage Account
- Load Balancer
- Private Link Service
- Private Endpoint
- Network Security Group
- Azure Bastion
- Azure Monitor
- Log Analytics
- Azure Active Directory
```

---

**Versione:** 1.0
**Data:** 2026-01-22
**Autore:** Security Patch Management Team
