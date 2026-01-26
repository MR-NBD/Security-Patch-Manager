## Indice
1. [Panoramica](#1-panoramica)
2. [Architettura Tecnica](#2-architettura-tecnica)
3. [Modello di Sicurezza](#3-modello-di-sicurezza)
4. [Concetti Fondamentali](#4-concetti-fondamentali)
5. [Comunicazione Client-Server](#5-comunicazione-client-server)
6. [Gestione Vulnerabilità](#6-gestione-vulnerabilità)
7. [Posizionamento e Confronto](#7-posizionamento-e-confronto)
## Panoramica
### Cos'è UYUNI
UYUNI è una piattaforma open source per la **gestione centralizzata dell'infrastruttura Linux**, derivata da Spacewalk (il progetto upstream di Red Hat Satellite) e mantenuta da SUSE come versione community di SUSE Manager.

**Funzionalità principali:**
- **Patch Management**: distribuzione controllata di aggiornamenti di sicurezza
- **Configuration Management**: gestione centralizzata delle configurazioni via Salt
- **Compliance & Auditing**: verifica conformità e audit CVE
- **Provisioning**: deployment automatizzato di nuovi sistemi
- **Inventory Management**: inventario hardware e software centralizzato
### Origini e Posizionamento

```
Spacewalk (Red Hat, 2008)
    │
    ├──► Red Hat Satellite (commerciale)
    │
    └──► UYUNI (open source, SUSE)
            │
            └──► SUSE Manager (commerciale)
```

| Prodotto | Licenza | Supporto | Target |
|----------|---------|----------|--------|
| **UYUNI** | GPL v2 | Community | Qualsiasi Linux |
| SUSE Manager | Commerciale | Enterprise | SUSE + altri |
| Red Hat Satellite | Commerciale | Enterprise | RHEL |
| Foreman/Katello | GPL | Community | RHEL-based |
### Sistemi Operativi Supportati
**Server UYUNI**: openSUSE Leap 15.x (unico OS supportato per il server)
**Client gestibili**:

| Famiglia                 | Versioni            | Livello Supporto |
| ------------------------ | ------------------- | ---------------- |
| SUSE Linux Enterprise    | 12, 15              | Completo         |
| openSUSE Leap            | 15.x                | Completo         |
| Red Hat Enterprise Linux | 7, 8, 9             | Completo         |
| CentOS / Rocky / Alma    | 7, 8, 9             | Completo         |
| Oracle Linux             | 7, 8, 9             | Completo         |
| **Ubuntu LTS**           | 20.04, 22.04, 24.04 | Buono            |
| **Debian**               | 11, 12              | Buono            |
| Amazon Linux             | 2, 2023             | Buono            |
## Architettura Tecnica
### Componenti del Server
- **UYUNI SERVER** : Container Podman o VM
	- **PRESENTATION LAYER** : 
		- **Web UI** : Tomcat
		- **XML-RPC** : API
		- **REST API** : limited
	- **APPLICATION LAYER** : 
		- **Taskomatic** : Scheduler
		- **Salt Master** : Automation
		- **Cobbler** : Provisioning
	- **DATA LAYER** : 
		- **PostgreSQL** : Database
		- **Apache** : Repos
		- **Squid** : Cache
### Descrizione Componenti

| Componente       | Tecnologia    | Funzione                                     |
| ---------------- | ------------- | -------------------------------------------- |
| **Web UI**       | Java/Tomcat   | Interfaccia grafica di amministrazione       |
| **XML-RPC API**  | Python/Java   | API programmatica per automazione            |
| **Taskomatic**   | Java          | Scheduler per job asincroni (sync, patching) |
| **Salt Master**  | Python/ZeroMQ | Esecuzione remota e configuration management |
| **Cobbler**      | Python        | Provisioning PXE e kickstart/autoyast        |
| **PostgreSQL**   | 14+           | Database centrale (sistemi, canali, errata)  |
| **Apache HTTPD** | 2.4           | Reverse proxy e repository server            |
| **Squid**        | 5.x           | Cache proxy per pacchetti (opzionale)        |
### Porte di Rete

| Porta    | Protocollo | Direzione       | Funzione                  |
| -------- | ---------- | --------------- | ------------------------- |
| **443**  | HTTPS      | Client → Server | Web UI, API, repository   |
| **4505** | TCP        | Client → Server | Salt publish (ZeroMQ PUB) |
| **4506** | TCP        | Client → Server | Salt return (ZeroMQ REQ)  |
| **5432** | TCP        | Interno         | PostgreSQL (se esterno)   |
| **69**   | UDP        | PXE → Server    | TFTP per provisioning     |
## Sicurezza
### Autenticazione
**Metodi supportati:**
- **Local**: utenti nel database UYUNI
- **LDAP/Active Directory**: integrazione enterprise
- **Kerberos/GSSAPI**: SSO enterprise
- **PAM**: autenticazione di sistema

**Multi-Factor Authentication**: supportato via PAM o integrazione esterna
### Autorizzazione (RBAC)
UYUNI implementa un modello Role-Based Access Control:

**GERARCHIA RUOLI** 
```                                                    
  SUSE Manager Administrator                                         
  └── Organization Administrator                                     
       └── Channel Administrator                                    
       └── Configuration Administrator                               
       └── System Group Administrator                               
            └── System Group User (per gruppo specifico)
```

| Ruolo                  | Permessi                              |
| ---------------------- | ------------------------------------- |
| **Org Admin**          | Gestione completa dell'organizzazione |
| **Channel Admin**      | Creazione/modifica canali software    |
| **Config Admin**       | Gestione configuration channels       |
| **System Group Admin** | Gestione sistemi nei gruppi assegnati |
### Multi-Tenancy (Organizations)
UYUNI supporta **isolamento multi-tenant** tramite Organizations:

![[Untitled Diagram.drawio.png]]

**Casi d'uso:**
- Separazione ambienti (DEV/QA/PROD)
- Multi-cliente in ambienti MSP
- Separazione dipartimentale
### Sicurezza Comunicazioni
**Client-Server (Salt):**
- Autenticazione PKI con chiavi RSA 4096-bit
- Comunicazione cifrata AES-256
- Fingerprint verification per prevenire MITM
**Repository:**
- Trasporto HTTPS con TLS 1.2+
- Firma GPG dei pacchetti
- Checksum SHA256 per integrità
**Database:**
- Connessione locale via socket Unix (default)
- SSL/TLS per connessioni remote
- Password hashing bcrypt
### Audit Trail
Tutte le operazioni sono tracciate:
- Login/logout utenti
- Modifiche configurazione
- Azioni su sistemi
- Applicazione patch
Log disponibili in:
- Web UI: Admin → Audit
- Database: tabelle `rhn*_log`
- Sistema: `/var/log/rhn/`
## Concetti Fondamentali
### Software Channels
I **Channels** sono repository di pacchetti software organizzati gerarchicamente:

**GERARCHIA CHANNELS** 
```
   Parent Channel (Base)                                             
   ubuntu-2404-pool-amd64                                            
   └── Contiene: pacchetti base del sistema                          
       ├── Child Channel: ubuntu-2404-security-amd64                 
       │   └── Contiene: aggiornamenti di sicurezza                  
       │                                                             
       ├── Child Channel: ubuntu-2404-updates-amd64                  
       │   └── Contiene: aggiornamenti stabili                       
       │                                                             
       └── Child Channel: ubuntu-2404-backports-amd64                
           └── Contiene: backport da versioni successive
```
**Tipi di Channel:**

| Tipo       | Origine                | Uso                    |
| ---------- | ---------------------- | ---------------------- |
| **Vendor** | SUSE Customer Center   | SLES, openSUSE         |
| **Custom** | Repository esterni     | Ubuntu, Debian, RHEL   |
| **Cloned** | Copia di altro channel | Snapshot point-in-time |
### Content Lifecycle Management (CLM)
CLM permette di gestire il ciclo di vita dei contenuti attraverso ambienti:

![[dueUntitled Diagram.drawio-1.png]]

**Vantaggi:**
- **Snapshot immutabili**: ogni build crea uno stato congelato
- **Promozione controllata**: DEV → QA → PROD con approvazioni
- **Rollback facile**: torna a qualsiasi build precedente
- **Filtri granulari**: escludi pacchetti problematici o CVE specifici
### Activation Keys
Le **Activation Key** sono template di configurazione per la registrazione client:

**ACTIVATION KEY** : "ak-ubuntu2404-prod"

- **Base Channel**: `ubuntu-2404-prod-pool-amd64`
- **Child Channels**:  
	- `ubuntu-2404-prod-security`
	- `ubuntu-2404-prod-updates`
- **System Groups**: 
	- production-servers
	- webservers
- **Config Channels**:
	- base-hardening
	- monitoring-agent
- **Contact Method**: Salt Minion (default)

**Workflow registrazione:**
1. Client si registra con activation key
2. UYUNI assegna automaticamente channels, gruppi, configurazioni
3. Sistema pronto per gestione centralizzata
### System Groups
Raggruppamenti logici di sistemi per:

| Funzione       | Descrizione                          |
| -------------- | ------------------------------------ |
| **Targeting**  | Applicare azioni a gruppi di sistemi |
| **RBAC**       | Delegare gestione a team specifici   |
| **Reporting**  | Report per gruppo                    |
| **Scheduling** | Finestre di manutenzione per gruppo  |

**Esempi di raggruppamento:**
- Per ambiente: dev-servers, qa-servers, prod-servers
- Per ruolo: webservers, databases, kubernetes-nodes
- Per location: datacenter-a, datacenter-b
- Per team: team-alpha, team-beta
## Comunicazione Client-Server
### Architettura Salt
UYUNI utilizza **SaltStack** come motore di automazione:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SALT ARCHITECTURE                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                      UYUNI Server                                   │
│                    (Salt Master)                                    │
│                          │                                          │
│            ┌─────────────┼─────────────┐                            │
│            │             │             │                            │
│            ▼             ▼             ▼                            │
│     ┌──────────┐  ┌──────────┐  ┌──────────┐                        │
│     │  ZeroMQ  │  │  ZeroMQ  │  │  Event   │                        │
│     │   PUB    │  │   REQ    │  │   Bus    │                        │
│     │  :4505   │  │  :4506   │  │          │                        │
│     └────┬─────┘  └────┬─────┘  └────┬─────┘                        │
│          │             │             │                              │
│          └─────────────┼─────────────┘                              │
│                        │                                            │
│          ══════════════╪══════════════ (Network)                    │
│                        │                                            │
│            ┌───────────┼───────────┐                                │
│            │           │           │                                │
│            ▼           ▼           ▼                                │
│     ┌──────────┐ ┌──────────┐ ┌──────────┐                          │
│     │  Salt    │ │  Salt    │ │  Salt    │                          │
│     │  Minion  │ │  Minion  │ │  Minion  │                          │
│     │ (Client) │ │ (Client) │ │ (Client) │                          │
│     └──────────┘ └──────────┘ └──────────┘                          │ 
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```
### Protocollo di Comunicazione

| Porta | Pattern | Funzione |
|-------|---------|----------|
| **4505** | PUB/SUB | Master pubblica comandi a tutti i minion |
| **4506** | REQ/REP | Minion inviano risultati al master |

**Caratteristiche:**
- **Connessione persistente**: minion mantiene connessione attiva
- **Bidirezionale**: comandi down, risultati up
- **Event-driven**: notifiche in tempo reale
- **Scalabile**: migliaia di client con latenza sub-second
### Autenticazione PKI

#### SALT PKI HANDSHAKE
1. Minion genera coppia chiavi RSA 4096-bit
	`/etc/salt/pki/minion/minion.pem` (privata)
	`/etc/salt/pki/minion/minion.pub` (pubblica)
2. Minion invia chiave pubblica al Master
	`Minion ──────► [minion.pub] ──────► Master`
3. Amministratore accetta chiave sul Master
	`salt-key -a <minion-id>`
4. Master invia sua chiave pubblica al Minion 
	`Master ──────► [master.pub] ──────► Minion
	Salvata in `/etc/salt/pki/minion/minion_master.pub`
5. Comunicazione cifrata AES-256 stabilita
### Modalità di Connessione

| Modalità        | Agent | Porte     | Latenza | Uso                       |
| --------------- | ----- | --------- | ------- | ------------------------- |
| **Salt Minion** | Sì    | 4505/4506 | ms      | Standard, alta reattività |
| **Salt-SSH**    | No    | 22        | secondi | DMZ, ambienti restrittivi |
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
## Gestione Vulnerabilità
### Errata/Patch Management
Gli **Errata** (o Patch) sono advisory di sicurezza che raggruppano:
- Descrizione vulnerabilità
- CVE associati
- Pacchetti da aggiornare
- Severity rating

#### ERRATA
**USN-7234-1**
- **Type** : Security Advisory
- **Severity** : Critical
- **Released** : 2026-01-15

- **CVEs** : CVE-2026-1234, CVE-2026-1235

- **Packages** : 
	- openssl 3.0.2-0ubuntu1.14
	- libssl3 3.0.2-0ubuntu1.14

- **Affected** : Ubuntu 24.04 LTS

**Nota Ubuntu/Debian**: UYUNI non importa nativamente gli errata per Ubuntu e Debian. Il progetto Security Patch Manager risolve questa lacuna sincronizzando USN e DSA.
### CVE Audit (OVAL)
UYUNI include un sistema di **CVE Audit** basato su OVAL (Open Vulnerability Assessment Language):

#### CVE AUDIT WORKFLOW
1. UYUNI scarica OVAL definitions
	- Canonical (Ubuntu)
	- Debian Security Team
	- SUSE/Red Hat
2. Analizza pacchetti installati sui client
	- Hardware refresh / package profile
3. Correla con database CVE
	- Package version < Fixed version = VULNERABLE
4. Report: "Sistema X ha CVE-2026-xxxx"
	- Visibile in: Audit → CVE Audit
### Confronto Errata vs CVE Audit

| Aspetto | Errata | CVE Audit |
|---------|--------|-----------|
| Dice "cosa aggiornare" | Bundle pacchetti | Solo CVE ID |
| Dice "sei vulnerabile" | Sì | Sì |
| Ubuntu/Debian nativo | No | **Sì (via OVAL)** |
| Severity info | Sì | Sì |
| One-click fix | Sì ("Apply Errata") | Manuale |
### Workflow Patching

#### PATCHING WORKFLOW

1. **DISCOVERY**
	- Sync canali con upstream
	- Import errata (USN/DSA)
	- CVE Audit scan
2. **ASSESSMENT**
	- Identifica sistemi vulnerabili
	- Prioritizza per severity (CVSS)
	- Valuta impatto business
3. **TESTING (Environment DEV/QA)**
	- CLM: Build nuovo snapshot
	- Applica patch in ambiente test
	- Verifica compatibilità applicazioni
4. **DEPLOYMENT**
	- CLM: Promote a PROD
	- Schedule maintenance window
	- Applica patch (rolling o simultaneo)
5. **VERIFICATION**
	- Verifica installazione patch
	- Re-scan CVE Audit
	- Report compliance

## Posizionamento e Confronto
### UYUNI vs Alternative

| Feature          | UYUNI       | Foreman/Katello | Ansible AWX | Landscape   |
| ---------------- | ----------- | --------------- | ----------- | ----------- |
| **Patch Mgmt**   | Completo    | Completo        | Limitato    | Ubuntu only |
| **Config Mgmt**  | Salt        | Puppet/Ansible  | Ansible     | Limitato    |
| **CVE Audit**    | OVAL nativo | Plugin          | No          | Limitato    |
| **Multi-OS**     | Ampio       | RHEL-focused    | Ampio       | Ubuntu only |
| **Architettura** | Container   | Complessa       | Container   | SaaS        |
| **Licenza**      | Open Source | Open Source     | Open Source | Commerciale |
### Punti di Forza UYUNI
1. **CVE Audit nativo**: funziona out-of-box con OVAL
2. **Salt integration**: automazione potente e scalabile
3. **Multi-OS reale**: gestisce SUSE, RHEL, Ubuntu, Debian
4. **Architettura moderna**: deployment container
5. **Costo**: completamente open source
### Limitazioni Note
1. **Errata Ubuntu/Debian**: non importati nativamente (risolto con SPM)
2. **Web UI**: meno moderna rispetto a Foreman
3. **Community**: più piccola rispetto a Ansible/Foreman
4. **Documentazione**: principalmente in inglese, alcune lacune
### Casi d'Uso Ideali
**UYUNI è ideale per:**
- Ambienti misti SUSE + Ubuntu + Debian + RHEL
- Requisiti di CVE Audit e compliance
- Organizzazioni che preferiscono Salt a Puppet/Ansible
- Budget limitato (no licensing)
**Considerare alternative se:**
- Ambiente 100% RHEL → Satellite o Foreman
- Solo Ubuntu → Landscape
- Focus su IaC e CI/CD → Ansible AWX/Tower
## Riferimenti

### Documentazione Ufficiale
- [UYUNI Documentation](https://www.uyuni-project.org/uyuni-docs/)
- [Salt Documentation](https://docs.saltproject.io/)
- [OVAL Language](https://oval.mitre.org/)

### Standard di Sicurezza
- [CVE - Common Vulnerabilities and Exposures](https://cve.mitre.org/)
- [CVSS - Common Vulnerability Scoring System](https://www.first.org/cvss/)
- [NVD - National Vulnerability Database](https://nvd.nist.gov/)
