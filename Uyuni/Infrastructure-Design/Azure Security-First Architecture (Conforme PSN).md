# Security Patch Manager - Infrastructure Design
Questo documento definisce l'architettura infrastrutturale del Security Patch Manager (SPM) per ambienti B2B IaaS nel contesto PSN, conforme alle linee guida Secure Public Cloud Azure.

**Riferimenti Normativi PSN:**
- PSN_HLD Secure Public Cloud v1.3
- PSN_LLD Network Secure Public Cloud Azure v1.0
- PSN_LLD Secure Public Cloud Azure v1.2
- PSN_LLD SPC Governance Model v1.0
- PSN_LLD Servizio Gestione delle Chiavi v1.1

---
## 1. PRINCIPI DI SICUREZZA AZURE APPLICATI (PSN Compliant)

### 1.1 Principi Generali

| Principio                 | Implementazione                                                  | Riferimento PSN         |
| ------------------------- | ---------------------------------------------------------------- | ----------------------- |
| **Zero Trust**            | Nessun IP pubblico per risorse interne, verifica identità sempre | BR-003, POG-PSN-023     |
| **Network Segmentation**  | VNet separate, subnet dedicate, NSG per ogni subnet              | BR-001, BR-002          |
| **Defense in Depth**      | Multi-layer: NSG + Azure Firewall + Private Endpoints            | BR-002.5, BR-002.6      |
| **Least Privilege**       | RBAC granulare, Managed Identities, no permanent access          | BR-010, POG-PSN-012     |
| **Encryption Everywhere** | TLS 1.3 in transit, encryption at rest con CMK/BYOK              | SR-PSN-046, SR-PSN-047  |
| **Private by Default**    | Private Endpoints per tutti i servizi PaaS                       | POG-PSN-023             |
| **Centralized Logging**   | Log Analytics + Sentinel                                         | SR-PSN-011, POG-PSN-002 |
| **Data Sovereignty**      | Tutti i dati risiedono su territorio italiano                    | BR-003, POG-PSN-007     |
### 1.2 Requisiti di Business PSN (BR)

| ID | Requisito | Applicazione SPM |
|----|-----------|------------------|
| **BR-001** | Soluzione Hub & Spoke | Architettura Master (Hub) + Client (Spoke) |
| **BR-002** | Hub controlla traffico SUD/NORD, NORD/SUD, EST/OVEST | Firewall su Hub con NSG su ogni subnet |
| **BR-002.5** | Traffico controllato tramite Firewall nell'Hub | Azure Firewall Premium in Tenant Master |
| **BR-002.6** | Firewall NGFW con IDS/IPS | Firewall con threat intelligence enabled |
| **BR-002.7** | Firewall logga tutto il traffico | Diagnostic logs → Log Analytics |
| **BR-003** | Accesso admin via Bastion con 2FA + whitelist IP | Azure Bastion Standard + MFA + NSG whitelist |
| **BR-004** | Policy che impediscono IP pubblici su risorse | Azure Policy deny public IP assignment |
| **BR-005** | Lighthouse per monitoring PSN | Configurato per visibilità centralizzata |
### 1.3 Requisiti di Sicurezza PSN (SR)

| ID | Requisito | Implementazione |
|----|-----------|-----------------|
| **SR-PSN-017** | Network Security | NSG su ogni subnet, NGFW su Hub |
| **SR-PSN-029** | Topologia Network | Hub & Spoke con peering |
| **SR-PSN-045** | Network Security | Micro-segmentazione con NSG |
| **SR-PSN-046** | Data Security | Encryption at rest con CMK |
| **SR-PSN-047** | Chiavi di cifratura | BYOK via Thales CipherTrust Manager |
| **SR-PSN-051** | Network Security | Traffico cifrato in transit (TLS 1.3) |
| **SR-PSN-056** | Vulnerability Management | Integrato con SPM P2 prioritization |
| **SR-PSN-060** | Logging | Log Analytics + Sentinel |
### 1.4 Policy di Governance PSN (POG)

| ID | Policy | Enforcement |
|----|--------|-------------|
| **POG-PSN-007** | Sovranità dati (Italy) | Azure Policy location = italynorth/italycentral |
| **POG-PSN-014** | MFA obbligatoria | Conditional Access Policy |
| **POG-PSN-017** | Accesso VM solo via Bastion | NSG deny SSH/RDP da internet |
| **POG-PSN-019** | Traffico perimetrale controllato | Azure Firewall + UDR |
| **POG-PSN-020** | IPS/IDS attivo | Azure Firewall Premium con threat intel |
| **POG-PSN-021** | DDoS Protection | DDoS Protection Standard su VNet |
| **POG-PSN-022** | WAF per servizi web | Application Gateway con WAF |
| **POG-PSN-023** | No IP pubblici su risorse | Azure Policy deny |
| **POG-PSN-024** | VNet protection | NSG + Service Endpoints |
## 2. ARCHITETTURA HIGH-LEVEL


## 3. DETTAGLIO COMPONENTI

### 3.1 TENANT MASTER (Hub)

Il Tenant Master è il centro di controllo del sistema SPM.
#### Subnet-Master-Server (10.100.1.0/24)

| Componente        | Tipo                 | Descrizione                                    |
| ----------------- | -------------------- | ---------------------------------------------- |
| **Master Server** | VM (Standard_D4s_v3) | UYUNI Server                                   |
| **API Server**    | ACI / VM             | Flask API per sync errata (attuale)            |
| **Load Balancer** | Internal LB          | Distribuzione carico per **High Availability** |

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
## 4. NETWORK SECURITY DESIGN (PSN Compliant)
### 4.0 Azure Landing Zone Structure (PSN)
L'architettura SPM si inserisce nella struttura Azure Landing Zone definita dal PSN:

```
Tenant Root Group
└── Azure Landing Zones
    ├── Platform (gestito PSN + PA)
    │   ├── Identity (DNS Resolver, Azure AD)
    │   ├── Management (Log Analytics, Sentinel)
    │   └── Connectivity (Hub: Firewall, VPN Gateway, Bastion)
    │
    ├── Landing Zone (workload PA)
    │   ├── Spoke-SPM-Master (SPM Server)
    │   └── Spoke-SPM-Client-{N} (per ogni tenant)
    │
    └── Decommissioned
```

**Management Groups & Responsabilità:**

| Management Group | PSN | Cliente PA | SPM |
|------------------|-----|------------|-----|
| Platform/Connectivity | ✓ | ✓ | - |
| Platform/Management | ✓ | ✓ | Logs |
| Landing Zone/Spoke-SPM | - | ✓ | ✓ |
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
### 4.2 Azure Private Link (PSN Pattern)
Comunicazione sicura tra Tenant Master e Tenant Client secondo pattern PSN:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PRIVATE LINK ARCHITECTURE (PSN)                       │
│                                                                          │
│  TENANT MASTER (Hub)                    TENANT CLIENT (Spoke)           │
│  ═══════════════════                    ═════════════════════           │
│                                                                          │
│  ┌──────────────────┐                   ┌──────────────────┐            │
│  │  Master Server   │                   │  Proxy Server    │            │
│  │  10.100.1.4      │                   │  10.172.1.4      │            │
│  └────────┬─────────┘                   └────────▲─────────┘            │
│           │                                      │                       │
│           ▼                                      │                       │
│  ┌──────────────────┐    Private Link   ┌───────┴────────┐             │
│  │ Private Link     │◄─────────────────►│ Private        │             │
│  │ Service          │                    │ Endpoint       │             │
│  │ (Standard LB)    │                    │ 10.172.1.100   │             │
│  └──────────────────┘                    └────────────────┘             │
│           │                                      │                       │
│           ▼                                      ▼                       │
│  ┌──────────────────┐                   ┌────────────────┐              │
│  │ Private DNS Zone │◄──────────────────│ DNS Resolver   │              │
│  │ spm.privatelink  │    DNS forward    │ (Identity sub) │              │
│  │ .azure.com       │                   └────────────────┘              │
│  └──────────────────┘                                                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```
**Configurazione (conforme BR-002.4):**
- Private Link Service sul Master Server (port 443, 5000)
- Private Endpoint nel Tenant Client (Spoke)
- Private DNS Zone per risoluzione nomi interna
- DNS Resolver nella subscription Identity (per forwarding)
- Nessun traffico transita su internet pubblico
### 4.3 Azure Firewall (Hub) - PSN Requirements
Conforme a BR-002.5, BR-002.6, BR-002.7, POG-PSN-019, POG-PSN-020:
```
┌─────────────────────────────────────────────────────────────────────────┐
│                    FIREWALL ARCHITECTURE (PSN)                           │
│                                                                          │
│                          ┌───────────────┐                               │
│                          │   INTERNET    │                               │
│                          └───────┬───────┘                               │
│                                  │                                       │
│                          ┌───────▼───────┐                               │
│                          │ Azure Firewall│                               │
│                          │   Premium     │                               │
│                          │  (Hub VNet)   │                               │
│                          │               │                               │
│                          │ • NGFW        │                               │
│                          │ • IDS/IPS     │ ◄── SR-PSN-017, POG-PSN-020  │
│                          │ • Threat Intel│                               │
│                          │ • TLS Inspect │                               │
│                          └───────┬───────┘                               │
│                                  │                                       │
│        ┌─────────────────────────┼─────────────────────────┐            │
│        │                         │                         │            │
│        ▼                         ▼                         ▼            │
│  ┌───────────┐            ┌───────────┐            ┌───────────┐        │
│  │ Spoke-SPM │            │ Spoke-SPM │            │ Spoke-PA  │        │
│  │  Master   │◄──────────►│  Client   │            │ Workload  │        │
│  └───────────┘  peering   └───────────┘            └───────────┘        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```
**Azure Firewall Premium Configuration (PSN Compliant):**

| Tipo | Regola | Direzione | Riferimento |
|------|--------|-----------|-------------|
| **DNAT** | Nessuna | - | POG-PSN-023 (no IP pubblici) |
| **Network** | Allow TCP 443 to Internet | Outbound | Sync USN/DSA/NVD |
| **Network** | Allow TCP 5432 Hub→Data subnet | Internal | PostgreSQL |
| **Network** | Allow TCP 443,5000 Spoke→Hub | Internal | API SPM |
| **Application** | Allow ubuntu.com/security/* | Outbound | USN sync |
| **Application** | Allow security-tracker.debian.org | Outbound | DSA sync |
| **Application** | Allow nvd.nist.gov | Outbound | NVD sync |
| **Application** | Allow security-metadata.canonical.com | Outbound | OVAL sync |
**Logging (BR-002.7):**
- Tutti i log → Log Analytics Workspace
- Retention: minimo 90 giorni
- Alert su: deny events, IDS/IPS triggers, anomalies

**Threat Intelligence (POG-PSN-020):**
- Mode: Alert and Deny
- Feed: Microsoft Threat Intelligence
- Categories: Malware, C2, Phishing
## 5. IDENTITY & ACCESS MANAGEMENT
### 5.1 Azure AD / Entra ID Integration
Conforme a SR-PSN-036 → SR-PSN-044, POG-PSN-008 → POG-PSN-016:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    IDENTITY ARCHITECTURE (PSN)                           │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    AZURE AD TENANT (PA)                          │    │
│  │  ┌─────────────────┐     ┌─────────────────┐                    │    │
│  │  │ Privileged      │     │ Azure AD Groups │                    │    │
│  │  │ Identity Mgmt   │     │ (RBAC)          │                    │    │
│  │  │ (PIM)           │     │                 │                    │    │
│  │  │ ═══════════════ │     │ SPM-Admins      │──► Full Access     │    │
│  │  │ • JIT Access    │     │ SPM-Operators   │──► P2,P3,P4 only   │    │
│  │  │ • Time-limited  │     │ SPM-Viewers     │──► Read-only       │    │
│  │  │ • Approval req. │     │ SPM-Auditors    │──► Logs only       │    │
│  │  └─────────────────┘     └─────────────────┘                    │    │
│  │                                                                  │    │
│  │  MFA OBBLIGATORIA (POG-PSN-014)                                 │    │
│  │  ════════════════════════════════                               │    │
│  │  • Conditional Access: Require MFA for all users                │    │
│  │  • Bastion access: 2FA + IP whitelist (BR-003)                  │    │
│  │  • Admin roles: Always require MFA                              │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Managed Identities (SR-PSN-036)                                 │    │
│  │ ═══════════════════════════════                                 │    │
│  │                                                                  │    │
│  │  Master-Server-MI ──► KeyVault: Get secrets                     │    │
│  │                   ──► Storage: Read/Write blobs                 │    │
│  │                   ──► PostgreSQL: db_owner                      │    │
│  │                                                                  │    │
│  │  Proxy-Server-MI  ──► KeyVault: Get secrets                     │    │
│  │                   ──► Master API: Authenticated calls           │    │
│  │                   ──► VM Snapshots: Create/Delete               │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Azure Lighthouse (BR-005) - PSN Monitoring                      │    │
│  │ ═════════════════════════════════════════                       │    │
│  │                                                                  │    │
│  │  PSN Provider Tenant ──► Delegated access to:                   │    │
│  │                         • Platform/Management (Log Analytics)   │    │
│  │                         • Platform/Connectivity (Network)       │    │
│  │                         • Security posture monitoring           │    │
│  │                                                                  │    │
│  │  Scope: Reader + Security Reader                                │    │
│  │  NO write access to customer workloads                          │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```
### 5.2 RBAC Assignments

| Role | Scope | Permissions |
|------|-------|-------------|
| SPM-Admins | Subscription | Contributor |
| SPM-Operators | Resource Groups | VM Contributor, Network Contributor |
| SPM-Viewers | Resource Groups | Reader |
| Proxy-Server-MI | VM RG | Virtual Machine Contributor (per snapshots) |
## 6. DATA PROTECTION (PSN BYOK)
### 6.1 Key Management System (PSN Architecture)
Conforme a SR-PSN-046 → SR-PSN-050, BR-001 → BR-007 del LLD Gestione Chiavi:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    KEY MANAGEMENT SYSTEM (PSN)                           │
│                                                                          │
│  PSN Data Center (On-Premise)           Azure Secure Public Cloud       │
│  ════════════════════════════           ═════════════════════════       │
│                                                                          │
│  ┌─────────────────────┐               ┌─────────────────────┐          │
│  │ Thales Luna HSM     │               │ Azure Managed HSM   │          │
│  │ (Root of Trust)     │───BYOK───────►│ (Azure Key Vault    │          │
│  │                     │               │  Premium)           │          │
│  │ • FIPS 140-2 L3     │               │                     │          │
│  │ • Region Nord+Sud   │               │ • CMK per storage   │          │
│  └─────────────────────┘               │ • CMK per database  │          │
│           │                            │ • CMK per VM disks  │          │
│           ▼                            └─────────────────────┘          │
│  ┌─────────────────────┐                        │                       │
│  │ CipherTrust Manager │                        │                       │
│  │ (Key Lifecycle)     │                        ▼                       │
│  │                     │               ┌─────────────────────┐          │
│  │ • Key generation    │               │ SPM Resources       │          │
│  │ • Key rotation      │               │ • PostgreSQL (TDE)  │          │
│  │ • Key revocation    │               │ • Storage (SSE)     │          │
│  │ • Audit logging     │               │ • VM Disks (ADE)    │          │
│  └─────────────────────┘               └─────────────────────┘          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```
**Requisiti BYOK (BR-001, BR-002):**
- Chiavi generate e archiviate ESTERNAMENTE al CSP
- Chiavi sotto pieno controllo del PSN
- Residenza chiavi: territorio italiano
### 6.2 Azure Key Vault Premium (SPM)
Secrets gestiti:

| Secret | Uso | Encryption |
|--------|-----|------------|
| `db-connection-string` | PostgreSQL connection | RSA-HSM |
| `uyuni-api-password` | UYUNI XML-RPC auth | RSA-HSM |
| `nvd-api-key` | NVD API authentication | RSA-HSM |
| `ssh-private-key` | Accesso VM Linux | RSA-HSM |
| `winrm-credentials` | Accesso VM Windows | RSA-HSM |
**Access Policy (conforme SR-PSN-042):**
- Master-Server-MI: Get, List
- Proxy-Server-MI: Get
- SPM-Admins: All operations (via PIM JIT)
### 6.3 Encryption Matrix (PSN Compliant)

| Data | Encryption | Key Source | Riferimento PSN |
|------|------------|------------|-----------------|
| PostgreSQL | TDE + CMK | BYOK (HSM) | SR-PSN-047 |
| Blob Storage | SSE + CMK | BYOK (HSM) | SR-PSN-046 |
| VM Disks | Azure Disk Encryption | CMK | SR-PSN-046 |
| In Transit | TLS 1.3 | - | SR-PSN-051 |
| Backup | Encrypted at rest | BYOK | SR-PSN-058 |
### 6.4 Data Classification (PSN)

| Tipo Dato | Protezione | Requisito |
|-----------|------------|-----------|
| Dati ordinari | At-rest + In-transit | TDE + TLS |
| Dati critici | At-rest + In-transit + In-use | + Confidential Computing |
## 7. MONITORING & LOGGING (PSN SOC Integration)
### 7.1 Log Analytics Workspace + Microsoft Sentinel
Conforme a SR-PSN-011 → SR-PSN-016, POG-PSN-002 → POG-PSN-004:

```
┌─────────────────────────────────────────────────────────────────────────┐
│           SECURITY MONITORING ARCHITECTURE (PSN)                         │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────┐      │
│  │              LOG ANALYTICS WORKSPACE                           │      │
│  │              (Subscription: Management)                        │      │
│  │              ═══════════════════════════                       │      │
│  │                                                                │      │
│  │  Data Sources:                                                 │      │
│  │  ├── Azure Activity Logs                                       │      │
│  │  ├── Azure AD Sign-in & Audit Logs (SR-PSN-022)               │      │
│  │  ├── NSG Flow Logs (SR-PSN-017)                               │      │
│  │  ├── Azure Firewall Logs (BR-002.7)                           │      │
│  │  ├── VM Diagnostics (Azure Monitor Agent)                     │      │
│  │  ├── PostgreSQL Logs                                          │      │
│  │  ├── Key Vault Audit Logs                                     │      │
│  │  └── Application Logs (SPM API)                               │      │
│  │                                                                │      │
│  │  Solutions Enabled:                                            │      │
│  │  ├── AgentHealthAssessment                                    │      │
│  │  ├── AntiMalware                                              │      │
│  │  ├── AzureActivity                                            │      │
│  │  ├── ChangeTracking                                           │      │
│  │  ├── Security                                                 │      │
│  │  ├── SecurityInsights (Sentinel)                              │      │
│  │  ├── SQLAdvancedThreatProtection                              │      │
│  │  ├── SQLVulnerabilityAssessment                               │      │
│  │  └── VMInsight                                                │      │
│  │                                                                │      │
│  └───────────────────────────────────────────────────────────────┘      │
│                              │                                           │
│                              ▼                                           │
│  ┌───────────────────────────────────────────────────────────────┐      │
│  │              MICROSOFT SENTINEL                                │      │
│  │              ══════════════════                                │      │
│  │                                                                │      │
│  │  Connectors:                                                   │      │
│  │  ├── Azure Activity                                           │      │
│  │  ├── Azure AD Identity Protection                             │      │
│  │  ├── Microsoft Defender for Cloud                             │      │
│  │  ├── Azure Firewall                                           │      │
│  │  └── Custom (SPM API logs)                                    │      │
│  │                                                                │      │
│  │  Analytics Rules (SPM Specific):                              │      │
│  │  ├── Failed patch deployment pattern                          │      │
│  │  ├── P3 test anomalies                                        │      │
│  │  ├── Unauthorized API access                                  │      │
│  │  ├── Mass SSH failures to VMs                                 │      │
│  │  └── Privilege escalation attempts                            │      │
│  │                                                                │      │
│  │  Playbooks (SOAR):                                            │      │
│  │  ├── Auto-isolate compromised VM                              │      │
│  │  ├── Notify SOC on critical alert                             │      │
│  │  └── Auto-block IP on brute force                             │      │
│  │                                                                │      │
│  └───────────────────────────────────────────────────────────────┘      │
│                              │                                           │
│                              ▼                                           │
│  ┌───────────────────────────────────────────────────────────────┐      │
│  │              PSN SOC (via Lighthouse)                          │      │
│  │              ════════════════════════                          │      │
│  │                                                                │      │
│  │  • Security posture monitoring (POG-PSN-002)                  │      │
│  │  • Workload security monitoring (POG-PSN-003)                 │      │
│  │  • Security alerts notification (POG-PSN-004)                 │      │
│  │                                                                │      │
│  └───────────────────────────────────────────────────────────────┘      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```
### 7.2 Microsoft Defender for Cloud
Conforme a SR-PSN-013, SR-PSN-021, SR-PSN-023:

| Feature | Status | Riferimento |
|---------|--------|-------------|
| Defender for Servers | Enabled (P2) | SR-PSN-021 |
| Defender for Databases | Enabled | SQL threat detection |
| Defender for Key Vault | Enabled | Secret access anomaly |
| Vulnerability Assessment | Enabled | SR-PSN-023, SR-PSN-056 |
| Secure Score monitoring | Active | POG-PSN-002 |
### 7.3 Azure Monitor Alerts (SPM Specific)

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| Patch Deployment Failed | Custom metric from API | Sev 1 | SOC + Email |
| P3 Test Failed | Custom metric | Sev 2 | Email |
| High CPU on Master | CPU > 80% for 5min | Sev 3 | Email |
| DB Connection Failed | Availability < 99% | Sev 1 | SOC + PagerDuty |
| NSG Deny Spike | > 100 denies in 5min | Sev 2 | SOC |
| Brute Force Detected | > 10 failed SSH in 1min | Sev 1 | Auto-block + SOC |
### 7.4 Log Retention (SR-PSN-060)

| Log Type | Retention | Storage |
|----------|-----------|---------|
| Security Logs | 365 giorni | Log Analytics + Archive |
| Activity Logs | 90 giorni | Log Analytics |
| Firewall Logs | 90 giorni | Log Analytics |
| Application Logs | 30 giorni | Log Analytics |
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
### 8.2 Flusso P3 - Patch Testing
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
## 12. AZURE POLICY (PSN Enforcement)
### 12.1 Policy Assignments (Landing Zone)
Conforme al modello Policy Driven Governance del PSN:

| Policy | Scope | Effect | Riferimento |
|--------|-------|--------|-------------|
| **Deny-PublicIP** | All subscriptions | Deny | POG-PSN-023 |
| **Deny-RDP-From-Internet** | All subscriptions | Deny | POG-PSN-017 |
| **Deny-SSH-From-Internet** | All subscriptions | Deny | POG-PSN-017 |
| **Allowed-Locations** | All subscriptions | Deny (only italynorth) | POG-PSN-007 |
| **Require-NSG-On-Subnet** | All subscriptions | Audit/Deny | SR-PSN-045 |
| **Deploy-DiagSettings-LogAnalytics** | All subscriptions | DeployIfNotExists | SR-PSN-060 |
| **Require-TLS-1.2-Minimum** | All subscriptions | Deny | SR-PSN-051 |
| **Deny-Storage-Public-Access** | All subscriptions | Deny | POG-PSN-023 |
| **Policy-Lock-Listino** | All subscriptions | Deny | Blocca risorse non in listino PSN |
### 12.2 Custom Policy Definitions (SPM Specific)

```json
// Policy: Require-P3-Test-Before-Deployment
{
  "mode": "All",
  "policyRule": {
    "if": {
      "allOf": [
        {"field": "type", "equals": "Microsoft.Compute/virtualMachines"},
        {"field": "tags['SPM-PatchStatus']", "equals": "PendingDeployment"},
        {"field": "tags['SPM-P3-Tested']", "notEquals": "true"}
      ]
    },
    "then": {
      "effect": "audit"
    }
  }
}
```
## 13. BACKUP SYSTEM (PSN Sovereign)
### 13.1 Architettura Backup PSN
Conforme a BR-005, SR-PSN-058, SR-PSN-059:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BACKUP ARCHITECTURE (PSN)                             │
│                                                                          │
│  Azure Secure Public Cloud              PSN Data Center (On-Premise)    │
│  ═════════════════════════              ═════════════════════════════   │
│                                                                          │
│  ┌─────────────────────┐               ┌─────────────────────────┐      │
│  │ SPM Master Server   │               │ Veeam Backup Manager    │      │
│  │ SPM Proxy Server    │               │ (On-Premise PSN)        │      │
│  │ PostgreSQL          │───Backup──────│                         │      │
│  │ Storage Account     │   Agent       │ • Veeam B&R             │      │
│  └─────────────────────┘               │ • Repository on PSN     │      │
│           │                            │   storage               │      │
│           │                            │ • Encryption BYOK       │      │
│           ▼                            └─────────────────────────┘      │
│  ┌─────────────────────┐                                                │
│  │ Virtual Server      │               SOVRANITÀ DEL DATO:              │
│  │ Agent (VSA)         │               • Backup risiedono in Italia     │
│  │ (Media Agent)       │               • Chiavi gestite da HSM PSN      │
│  │                     │               • Retention conforme normativa   │
│  └─────────────────────┘                                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```
### 13.2 Backup Policy

| Componente | Frequenza | Retention | Storage |
|------------|-----------|-----------|---------|
| PostgreSQL DB | Daily | 30 giorni | PSN On-Premise |
| SPM Master VM | Weekly | 4 settimane | PSN On-Premise |
| Configuration | On-change | Unlimited | Git + PSN Storage |
| Snapshots P3 | Temporary | Max 4 ore | Azure (auto-delete) |
### 13.3 Disaster Recovery (SR-PSN-059)

| Componente | RTO | RPO | Strategy |
|------------|-----|-----|----------|
| Master Server | 4h | 24h | Restore from backup |
| PostgreSQL | 1h | 1h | Geo-redundant + Veeam |
| Proxy Server | 2h | N/A | Stateless, redeploy |
| Configuration | 15min | Real-time | Git repo |
## 14. COMPLIANCE MAPPING
### 14.1 Standard Compliance

| Requisito | Standard | Implementazione |
|-----------|----------|-----------------|
| Network Isolation | ISO 27001, NIST | VNet separation, NSG, Private Link |
| Encryption | GDPR, ISO 27001 | TLS 1.3, CMK, Azure Disk Encryption |
| Access Control | ISO 27001, NIST | Azure AD, RBAC, MFA |
| Audit Logging | SOC 2, ISO 27001 | Log Analytics, Key Vault audit |
| Patch Management | NIST 800-40 | SPM framework (P2, P3, P4) |

### 14.2 PSN Compliance Checklist

| Requisito PSN | Stato | Note |
|---------------|-------|------|
| BR-001 Hub & Spoke | ✅ | Architettura Master/Client |
| BR-002 Firewall control | ✅ | Azure Firewall Premium |
| BR-003 Bastion + 2FA | ✅ | Azure Bastion + MFA |
| BR-004 No public IP policy | ✅ | Azure Policy deny |
| BR-005 Lighthouse | ✅ | Delegated access |
| SR-PSN-017 Network Security | ✅ | NSG + Firewall |
| SR-PSN-046 Data encryption | ✅ | CMK/BYOK |
| SR-PSN-047 Key management | ✅ | HSM + Key Vault |
| SR-PSN-060 Logging | ✅ | Log Analytics + Sentinel |
| POG-PSN-007 Data sovereignty | ✅ | Italy only |
| POG-PSN-014 MFA | ✅ | Conditional Access |
| POG-PSN-020 IDS/IPS | ✅ | Firewall threat intel |
