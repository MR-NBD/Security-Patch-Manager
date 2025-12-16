# UYUNI Learning Path - Patch Management Enterprise Multi-Tenant

## Obiettivo
Gestire il patch management in un'organizzazione **multi-tenant** con **sicurezza al primo posto**, utilizzando UYUNI come alternativa open-source a SUSE Manager.

---

## Mappatura Concetti: Foreman/Katello → UYUNI

| Foreman/Katello | UYUNI | Note |
|-----------------|-------|------|
| **Products** | Software Channels (Parent) | Contenitore logico per repository |
| **Repositories** | Software Channels (Child) | Repository effettivi con pacchetti |
| **Content Views** | Content Lifecycle Management (CLM) | Filtering e promozione contenuti |
| **Lifecycle Environments** | CLM Environments | Dev → Test → Prod |
| **Composite Content Views** | CLM Projects | Aggregazione di più filtri |
| **Activation Keys** | Activation Keys | Identico concetto |
| **Host Collections** | System Groups | Raggruppamento host |
| **Host Groups** | System Groups + Activation Keys | Combinazione |
| **Errata** | Patches / Errata / Advisories | CVE, Security, Bugfix |
| **Remote Execution (REX)** | Salt Remote Commands | Basato su Salt invece di SSH |
| **Puppet/Ansible** | Salt States | Configuration Management |
| **Organizations** | Organizations | Multi-tenancy |
| **Locations** | (non presente) | Usare System Groups |
| **Smart Proxies/Capsules** | UYUNI Proxy | Cache e scalabilità |

---

## ESSENZIALI - Priorità Alta

### 1. [Architettura e Concetti Base UYUNI]
**Tempo stimato**: 2-3 ore
- Architettura container-based (Podman)
- Differenze chiave vs Foreman/Katello
- Componenti: Salt Master, Taskomatic, PostgreSQL
- Web UI navigation
- CLI tools: `mgradm`, `mgrctl`, `spacecmd`

**Output**: Comprensione dell'architettura e navigazione base

---

### 2. [Organizations e Multi-Tenancy]
**Tempo stimato**: 3-4 ore
- Creazione Organizations (tenant isolation)
- Trust relationships tra Organizations
- Condivisione canali tra Organizations
- Users e Roles per Organization
- Best practice isolamento dati

**Foreman equivalent**: Organizations
**Criticità sicurezza**: ALTA

**Output**: Ambiente multi-tenant configurato con isolamento

---

### 3. [Software Channels - Struttura e Gestione]
**Tempo stimato**: 4-6 ore
- Concetto Parent/Child Channels
- Vendor Channels (SUSE, RedHat, Ubuntu, Debian)
- Custom Channels
- Channel cloning
- Channel permissions per Organization

**Foreman equivalent**: Products + Repositories
**Criticità sicurezza**: MEDIA

**Output**: Struttura canali per Ubuntu/Debian configurata

---

### 4. [Repository Sync e Content Management]
**Tempo stimato**: 4-6 ore
- Aggiungere repository esterni (Ubuntu, Debian)
- Repository sync scheduling
- Mirror vs On-demand
- GPG key management
- Sync status e troubleshooting
- Storage management

**Foreman equivalent**: Repository sync
**Criticità sicurezza**: MEDIA

**Output**: Repository Ubuntu 22.04/24.04 e Debian 11/12 sincronizzati

---

### 5. [Content Lifecycle Management (CLM)]
**Tempo stimato**: 6-8 ore CRITICO
- CLM Projects (equivalente Content Views)
- CLM Environments (Dev → QA → Staging → Prod)
- Filters: Include/Exclude packages
- Filters: Date-based (freeze point-in-time)
- Filters: CVE-based
- Build e Promote workflow
- Rollback

**Foreman equivalent**: Content Views + Lifecycle Environments
**Criticità sicurezza**:  ALTA

**Output**: Pipeline CLM funzionante con promozione controllata

---

### 6. [Activation Keys e System Registration]
**Tempo stimato**: 3-4 ore
- Creazione Activation Keys
- Associazione Channels
- Associazione System Groups
- Configuration Channels
- Bootstrap script generation
- Registrazione client Salt (Ubuntu/Debian)
- Re-registration e migration

**Foreman equivalent**: Activation Keys
**Criticità sicurezza**: MEDIA

**Output**: Client registrati con canali corretti

---

### 7. [Patch Management Operativo]
**Tempo stimato**: 6-8 ore CRITICO
- Errata/Patch types: Security, Bugfix, Enhancement
- CVE Audit (OVAL data)
- Patch scheduling
- Patch applicazione singola/massiva
- Maintenance Windows
- Pre/Post patch actions
- Reboot management
- Patch compliance reporting

**Foreman equivalent**: Errata management
**Criticità sicurezza**: ALTA

**Output**: Workflow patching completo con scheduling

---

### 8. [System Groups e Targeting]
**Tempo stimato**: 2-3 ore
- Creazione System Groups (equivalente Host Collections)
- Dynamic Groups (formula-based)
- Static Groups
- Nested Groups
- Targeting per patch/azioni

**Foreman equivalent**: Host Collections + Host Groups
**Criticità sicurezza**: BASSA

**Output**: Gruppi organizzati per ambiente/ruolo/criticità

---

### 9. [Salt Remote Commands]
**Tempo stimato**: 4-6 ore
- Esecuzione comandi remoti via Salt
- Salt States base
- Scheduling remote commands
- Output collection
- Targeting avanzato (grains, pillars)
- Sicurezza: whitelisting comandi

**Foreman equivalent**: Remote Execution (REX)
**Criticità sicurezza**: ALTA

**Output**: Capacità di eseguire comandi su fleet

---

### 10. [RBAC - Role-Based Access Control]
**Tempo stimato**: 4-6 ore CRITICO per sicurezza
- Ruoli predefiniti
- Ruoli custom
- Permissions granulari
- Separation of duties
- Audit trail
- Integration LDAP/AD (opzionale)

**Foreman equivalent**: Roles + Permissions
**Criticità sicurezza**:  ALTA

**Output**: Matrice RBAC per team operations

---

## IMPORTANTI - Priorità Media

### 11. [Automazione con Salt States]
**Tempo stimato**: 8-10 ore
- Salt States per configuration management
- Salt Formulas
- Pillars (variabili per host/gruppo)
- Grains (facts del sistema)
- State orchestration
- Highstate

**Foreman equivalent**: Puppet/Ansible integration
**Criticità sicurezza**:  MEDIA

**Output**: Stati Salt per configurazioni base

---

### 12. [Reporting e Compliance]
**Tempo stimato**: 4-6 ore
- Report predefiniti
- Custom reports
- CVE compliance dashboard
- Patch compliance
- Export CSV/PDF
- Scheduled reports

**Foreman equivalent**: Report templates
**Criticità sicurezza**:  MEDIA (per audit)

**Output**: Dashboard compliance per management

---

### 13. [Audit e Logging]
**Tempo stimato**: 3-4 ore
- Audit log UYUNI
- Event history
- Action tracking
- User activity
- Integration con SIEM (syslog)
- Log retention

**Foreman equivalent**: Audit log
**Criticità sicurezza**:  ALTA

**Output**: Audit trail configurato

---

### 14. [Maintenance Windows e Change Management]
**Tempo stimato**: 3-4 ore
- Definizione Maintenance Windows
- Action Chains (sequenze di azioni)
- Pre-checks automatici
- Rollback procedures
- Integration con ticketing (manual)

**Foreman equivalent**: REX scheduling + Host parameters
**Criticità sicurezza**: MEDIA

**Output**: Workflow change management

---

### 15. [UYUNI Proxy (Scalabilità)]
**Tempo stimato**: 4-6 ore
- Quando usare un Proxy
- Deployment Proxy
- Content caching
- Salt Broker
- Network segmentation

**Foreman equivalent**: Smart Proxy / Capsule
**Criticità sicurezza**:  MEDIA

**Output**: Decisione se serve proxy per la tua architettura

---

### 16. [Gestione Ubuntu/Debian Specifico]
**Tempo stimato**: 4-6 ore
- Ubuntu Security Notices (USN)
- Debian Security Advisories (DSA)
- APT repository management
- Package holds
- Distribution upgrade management
- Kernel management

**Foreman equivalent**: Errata for Deb (con limitazioni)
**Criticità sicurezza**: 🔒🔒🔒 ALTA

**Output**: Gestione completa sistemi Debian-based

---

## 🟢 OPZIONALI - Priorità Bassa (ma utili)

### 17. [Monitoring Integration]
**Tempo stimato**: 4-6 ore
- Prometheus exporters nativi
- Grafana dashboards
- Alerting
- Integration con Azure Monitor
- Health checks

**Output**: Monitoring infrastruttura UYUNI

---

### 18. [Backup e Disaster Recovery]
**Tempo stimato**: 4-6 ore
- Backup strategy
- `mgradm backup`
- Database backup
- Recovery procedures
- High Availability (panoramica)

**Criticità sicurezza**: ALTA

**Output**: Procedure DR documentate

---

### 19. [API e Automazione Esterna]
**Tempo stimato**: 6-8 ore
- XMLRPC API
- API authentication
- Scripting con Python
- Integration con CI/CD
- spacecmd scripting

**Output**: Script automazione custom

---

### 20. [Image e Container Management]
**Tempo stimato**: 4-6 ore
- OS Image building
- Kiwi images
- Container image management
- PXE provisioning (se necessario)

**Output**: Capacità provisioning (se richiesto)

---

### 21. [Virtualization Management]
**Tempo stimato**: 2-3 ore
- Gestione VM guests
- Virtual host inventory
- Resource monitoring

**Output**: Visibilità su VM

---

### 22. [Retail/Edge (Branch Server)]
**Tempo stimato**: 4-6 ore
- UYUNI per branch offices
- Offline operation
- Content staging

**Output**: Architettura distribuita (se necessario)

---

### 23. [spacecmd - CLI Avanzato]
**Tempo stimato**: 3-4 ore
- Batch operations
- Scripting
- Report generation
- Automation recipes

**Output**: Produttività CLI

---

### 24. [Troubleshooting Avanzato]
**Tempo stimato**: Ongoing
- Log analysis
- Salt debugging
- Database queries
- Performance tuning
- Common issues

**Output**: Capacità troubleshooting

---

## 📋 Percorso Consigliato per il Tuo Caso

### Fase 1: Fondamentali (Settimana 1-2)
1. ✅ Architettura e Concetti Base
2. ✅ Organizations e Multi-Tenancy
3. ✅ Software Channels
4. ✅ Repository Sync

### Fase 2: Content Management (Settimana 3-4)
5. ✅ Content Lifecycle Management (CLM) ⭐
6. ✅ Activation Keys
7. ✅ System Groups

### Fase 3: Operations (Settimana 5-6)
8. ✅ Patch Management Operativo ⭐
9. ✅ Salt Remote Commands
10. ✅ RBAC ⭐

### Fase 4: Enterprise Features (Settimana 7-8)
11. Audit e Logging
12. Reporting e Compliance
13. Maintenance Windows
14. Gestione Ubuntu/Debian Specifico

### Fase 5: Avanzato (Ongoing)
15. Salt States (automazione)
16. API e scripting
17. Monitoring
18. Backup/DR

---

## 🔒 Focus Sicurezza - Guide Prioritarie

Per il tuo requisito "sicurezza al primo posto", queste guide sono **non negoziabili**:

| # | Guida | Motivo Sicurezza |
|---|-------|------------------|
| 2 | Multi-Tenancy | Isolamento dati tra tenant |
| 5 | CLM | Controllo su cosa viene deployato |
| 7 | Patch Management | Riduzione superficie attacco |
| 10 | RBAC | Principio least privilege |
| 13 | Audit | Tracciabilità azioni |
| 16 | Ubuntu/Debian Security | CVE management specifico |

---

## ❓ Domande per Definire Priorità

Prima di iniziare, considera:

1. **Quanti tenant/organizzazioni** devi gestire?
2. **Quanti sistemi** totali (approssimativo)?
3. **Hai già un workflow di patching** definito o devi crearlo?
4. **Usi già Salt** o parti da zero?
5. **Hai requisiti di compliance** specifici (ISO 27001, SOC2, etc.)?
6. **Network topology**: tutti i client raggiungono UYUNI direttamente o servono proxy?
7. **Integration**: devi integrare con SIEM, ticketing, CI/CD?

---

## 📚 Risorse Ufficiali

- [UYUNI Documentation](https://www.uyuni-project.org/uyuni-docs/)
- [Salt Documentation](https://docs.saltproject.io/)
- [UYUNI GitHub](https://github.com/uyuni-project/uyuni)
- [SUSE Manager Docs](https://documentation.suse.com/suma/) (compatibile 95%)

---

## 🎯 Come Vuoi Procedere?

Posso creare guide dettagliate per ciascun argomento. Suggerisco di iniziare da:

**Opzione A**: Seguire il percorso consigliato (sequenziale)

**Opzione B**: Iniziare dalle guide di sicurezza prioritarie

**Opzione C**: Partire da un argomento specifico che ti interessa

Fammi sapere quale preferisci e con quale guida vuoi iniziare!
