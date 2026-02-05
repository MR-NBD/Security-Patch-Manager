# SPM Orchestrator - Design Document

**Versione:** 1.0
**Data:** 2026-02-05
**Stato:** Approvato per implementazione

---

## Indice

1. [Obiettivo del Sistema](#1-obiettivo-del-sistema)
2. [Architettura a Due Componenti](#2-architettura-a-due-componenti)
3. [Workflow End-to-End](#3-workflow-end-to-end)
4. [Diagramma Stati Patch](#4-diagramma-stati-patch)
5. [Decisioni Architetturali](#5-decisioni-architetturali)
6. [Matrice Nativo vs Sviluppo](#6-matrice-nativo-vs-sviluppo)
7. [Schema Database](#7-schema-database)
8. [API Specification](#8-api-specification)
9. [Prometheus & Grafana](#9-prometheus--grafana)
10. [Success Score Algorithm](#10-success-score-algorithm)
11. [Struttura Progetto](#11-struttura-progetto)
12. [Lacune e Rischi](#12-lacune-e-rischi)
13. [Roadmap Implementazione](#13-roadmap-implementazione)
14. [Checklist Pre-Implementazione](#14-checklist-pre-implementazione)

---

## 1. Obiettivo del Sistema

```
┌─────────────────────────────────────────────────────────────────────┐
│  GOAL: Automatizzare il patch management con supervisione umana    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  INPUT                           OUTPUT                             │
│  ─────                           ──────                             │
│  • Errata Ubuntu (USN)           • Sistemi PROD patchati           │
│  • Errata Debian (DSA)           • Zero downtime imprevisti        │
│  • Errata RHEL (RHSA)            • Audit trail completo            │
│  • CVE/CVSS data                 • Report compliance               │
│                                                                     │
│  VINCOLI                                                            │
│  ───────                                                            │
│  • Operatore approva prima di PROD                                 │
│  • Test automatico su ambiente dedicato                            │
│  • Rollback possibile (package + system level)                     │
│  • Priorità: patch più "sicure" prima (Success Score)              │
│  • Gestione reboot controllata                                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Architettura a Due Componenti

I due componenti sono **separati** per garantire manutenibilità, scalabilità e fault isolation.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ARCHITETTURA SEPARATA                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  COMPONENTE 1: SPM-SYNC (Esistente)                                │
│  ══════════════════════════════════                                │
│  Container: errata-sync-api                                        │
│  Porta: 5000                                                       │
│  Responsabilità:                                                   │
│  • Sync USN, DSA, NVD, OVAL                                        │
│  • Normalizzazione errata                                          │
│  • Push errata a UYUNI                                             │
│  • Cache pacchetti                                                 │
│                                                                     │
│  Database: PostgreSQL (tabelle esistenti)                          │
│  • errata, cves, packages, oval_definitions                        │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  COMPONENTE 2: SPM-ORCHESTRATOR (Nuovo)                            │
│  ══════════════════════════════════════                            │
│  Container: patch-orchestrator-api                                 │
│  Porta: 5001                                                       │
│  Responsabilità:                                                   │
│  • Success Score calculation                                       │
│  • Test queue management                                           │
│  • Test orchestration (Salt, Prometheus)                           │
│  • Approval workflow                                               │
│  • Rollback management                                             │
│  • Notifications                                                   │
│                                                                     │
│  Database: PostgreSQL (nuove tabelle)                              │
│  • patch_risk_profile, patch_test_queue, patch_tests               │
│  • patch_approvals, patch_deployments, notifications               │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  COMUNICAZIONE                                                      │
│  ─────────────                                                      │
│                                                                     │
│  ┌─────────────┐         Database          ┌──────────────────┐    │
│  │  SPM-SYNC   │◄───── (PostgreSQL) ──────►│ SPM-ORCHESTRATOR │    │
│  │   :5000     │        condiviso          │      :5001       │    │
│  └──────┬──────┘                           └────────┬─────────┘    │
│         │                                           │               │
│         │  Webhook (opzionale)                      │               │
│         └──────── POST /webhook/new-errata ────────►│               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Stack Tecnologico

```
┌─────────────────────────────────────────────────────────────────────┐
│                      TECHNOLOGY STACK                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  PRESENTATION LAYER                                                 │
│  ──────────────────                                                 │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │
│  │   Streamlit   │  │    Grafana    │  │  UYUNI WebUI  │           │
│  │   (Approval)  │  │  (Monitoring) │  │   (Admin)     │           │
│  └───────────────┘  └───────────────┘  └───────────────┘           │
│                                                                     │
│  API LAYER                                                          │
│  ─────────                                                          │
│  ┌───────────────────────────────────┐  ┌───────────────┐          │
│  │          SPM API (Flask)          │  │ UYUNI XML-RPC │          │
│  │  • /api/sync/*      (SYNC)        │  │               │          │
│  │  • /api/uyuni/*     (SYNC)        │  │               │          │
│  │  • /api/v1/*        (ORCHESTRATOR)│  │               │          │
│  └───────────────────────────────────┘  └───────────────┘          │
│                                                                     │
│  DATA LAYER                                                         │
│  ──────────                                                         │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │
│  │  PostgreSQL   │  │  Prometheus   │  │  UYUNI DB     │           │
│  │  (SPM Data)   │  │  (Time-series)│  │  (Systems)    │           │
│  └───────────────┘  └───────────────┘  └───────────────┘           │
│                                                                     │
│  INFRASTRUCTURE LAYER                                               │
│  ────────────────────                                               │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │
│  │  Salt Master  │  │ node_exporter │  │   snapper/    │           │
│  │  (via UYUNI)  │  │ (all systems) │  │   LVM snap    │           │
│  └───────────────┘  └───────────────┘  └───────────────┘           │
│                                                                     │
│  TARGET SYSTEMS                                                     │
│  ──────────────                                                     │
│  ┌───────────────┐  ┌───────────────┐                              │
│  │  TEST-VM-01   │  │  PROD-*       │                              │
│  │  TEST-VM-02   │  │  (N systems)  │                              │
│  │  (Ubuntu/RHEL)│  │               │                              │
│  └───────────────┘  └───────────────┘                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Workflow End-to-End

```
┌─────────────────────────────────────────────────────────────────────┐
│                         WORKFLOW COMPLETO                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐│
│  │ FASE 1: DISCOVERY & SYNC (Automatico - ogni 6h)                ││
│  │ ──────────────────────────────────────────────                 ││
│  │ • SPM-SYNC sincronizza USN/DSA/NVD/OVAL                        ││
│  │ • SPM-ORCHESTRATOR calcola Success Score per ogni errata       ││
│  │ • Push errata su canali UYUNI DEV                              ││
│  │ • UYUNI CLM: Build ambiente DEV                                ││
│  └────────────────────────────────────────────────────────────────┘│
│                                    │                                │
│                                    ▼                                │
│  ┌────────────────────────────────────────────────────────────────┐│
│  │ FASE 2: PROMOTE TO TEST (Automatico)                           ││
│  │ ────────────────────────────────────                           ││
│  │ • UYUNI CLM: Promote DEV → TEST                                ││
│  │ • Sistemi TEST ricevono nuovi canali                           ││
│  └────────────────────────────────────────────────────────────────┘│
│                                    │                                │
│                                    ▼                                │
│  ┌────────────────────────────────────────────────────────────────┐│
│  │ FASE 3: AUTOMATED TESTING (Automatico - ordinato per Score)    ││
│  │ ──────────────────────────────────────────────────────────     ││
│  │ Per ogni errata (ordine: Success Score DESC):                  ││
│  │                                                                 ││
│  │   3.1 PRE-PATCH                                                ││
│  │       • Snapshot sistema (snapper/LVM)                         ││
│  │       • Query Prometheus: baseline metriche                    ││
│  │       • Salva stato servizi                                    ││
│  │                                                                 ││
│  │   3.2 APPLY PATCH                                              ││
│  │       • Salt: applica errata                                   ││
│  │       • Attendi stabilizzazione (5 min)                        ││
│  │                                                                 ││
│  │   3.3 VALIDATION                                               ││
│  │       • Query Prometheus: post-patch metriche                  ││
│  │       • Check: servizi critici UP                              ││
│  │       • Check: reboot required?                                ││
│  │       • Se reboot required → reboot → re-check                 ││
│  │       • Confronta baseline vs post-patch                       ││
│  │                                                                 ││
│  │   3.4 VERDICT                                                  ││
│  │       • PASS: tutti i criteri soddisfatti                      ││
│  │       • FAIL: rollback automatico, log motivo                  ││
│  │       • Aggiorna Success Score (storico)                       ││
│  │       • Notifica Grafana/Email se FAIL                         ││
│  └────────────────────────────────────────────────────────────────┘│
│                                    │                                │
│                                    ▼                                │
│  ┌────────────────────────────────────────────────────────────────┐│
│  │ FASE 4: APPROVAL GATE (Manuale - Operatore)                    ││
│  │ ───────────────────────────────────────────                    ││
│  │ • Dashboard Streamlit mostra patch testate                     ││
│  │ • Operatore vede: errata, severity, test result, metriche     ││
│  │ • Operatore decide: APPROVE o REJECT o SNOOZE                  ││
│  │ • Email digest giornaliero con pending approvals               ││
│  │ • Opzionale: crea ticket su ITSM                               ││
│  └────────────────────────────────────────────────────────────────┘│
│                                    │                                │
│                    ┌───────────────┴───────────────┐                │
│                    ▼                               ▼                │
│              APPROVED                          REJECTED             │
│                    │                               │                │
│                    ▼                               ▼                │
│  ┌─────────────────────────────┐   ┌─────────────────────────────┐ │
│  │ FASE 5: PROMOTE TO PROD     │   │ LOG & INVESTIGATE           │ │
│  │ ───────────────────────     │   │ ─────────────────           │ │
│  │ • CLM: Promote TEST → PROD  │   │ • Salva motivo rejection    │ │
│  │ • Schedule maintenance      │   │ • Crea ticket (opzionale)   │ │
│  │   window                    │   │ • Notifica security team    │ │
│  └──────────────┬──────────────┘   └─────────────────────────────┘ │
│                 │                                                   │
│                 ▼                                                   │
│  ┌────────────────────────────────────────────────────────────────┐│
│  │ FASE 6: PRODUCTION DEPLOYMENT                                  ││
│  │ ─────────────────────────────                                  ││
│  │ • Snapshot pre-patch (per rollback)                            ││
│  │ • Applica patch (simultaneo - canary in roadmap futura)        ││
│  │ • Check reboot required                                        ││
│  │ • Se reboot: schedule in maintenance window                    ││
│  │ • Verifica post-deployment                                     ││
│  │                                                                 ││
│  │ SE PROBLEMA:                                                   ││
│  │ • Alert immediato                                              ││
│  │ • Opzioni rollback: Package-only o Full System                 ││
│  │ • Operatore sceglie via Dashboard                              ││
│  └────────────────────────────────────────────────────────────────┘│
│                                    │                                │
│                                    ▼                                │
│  ┌────────────────────────────────────────────────────────────────┐│
│  │ FASE 7: REPORTING & COMPLIANCE                                 ││
│  │ ─────────────────────────────                                  ││
│  │ • UYUNI CVE Audit: verifica vulnerabilità risolte             ││
│  │ • Grafana: dashboard compliance                                ││
│  │ • Report automatico: patch applicate, pending, failed          ││
│  │ • Audit trail completo in DB                                   ││
│  └────────────────────────────────────────────────────────────────┘│
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Diagramma Stati Patch

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PATCH STATE MACHINE                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                         ┌─────────┐                                │
│                         │ SYNCED  │ ← Errata importato da USN/DSA  │
│                         └────┬────┘                                │
│                              │                                      │
│                              ▼                                      │
│                         ┌─────────┐                                │
│                         │ QUEUED  │ ← In coda test (per Score)     │
│                         └────┬────┘                                │
│                              │                                      │
│                              ▼                                      │
│                         ┌─────────┐                                │
│                         │ TESTING │ ← Test in corso                │
│                         └────┬────┘                                │
│                              │                                      │
│              ┌───────────────┼───────────────┐                     │
│              ▼               ▼               ▼                      │
│        ┌──────────┐   ┌──────────┐   ┌──────────────┐             │
│        │  PASSED  │   │  FAILED  │   │ NEEDS_REBOOT │             │
│        └────┬─────┘   └────┬─────┘   └──────┬───────┘             │
│             │              │                │                       │
│             │              │                ▼                       │
│             │              │         ┌──────────┐                  │
│             │              │         │ REBOOTING│                  │
│             │              │         └────┬─────┘                  │
│             │              │              │                         │
│             │              │    ┌─────────┴─────────┐              │
│             │              │    ▼                   ▼               │
│             │              │  PASSED             FAILED             │
│             │              │    │                   │               │
│             ▼              ▼    ▼                   ▼               │
│        ┌─────────────────────────┐         ┌─────────────┐        │
│        │   PENDING_APPROVAL     │         │  ROLLED_BACK │        │
│        └───────────┬────────────┘         └─────────────┘        │
│                    │                                               │
│        ┌───────────┼───────────┐                                  │
│        ▼           ▼           ▼                                   │
│  ┌──────────┐ ┌─────────┐ ┌─────────┐                            │
│  │ APPROVED │ │REJECTED │ │ SNOOZED │                            │
│  └────┬─────┘ └─────────┘ └────┬────┘                            │
│       │                        │                                   │
│       ▼                        │ (dopo N giorni)                   │
│  ┌───────────┐                 │                                   │
│  │ PROMOTING │                 └──────► PENDING_APPROVAL           │
│  └─────┬─────┘                                                     │
│        │                                                           │
│        ▼                                                           │
│  ┌────────────┐                                                   │
│  │PROD_PENDING│ ← In attesa maintenance window                    │
│  └─────┬──────┘                                                   │
│        │                                                           │
│        ▼                                                           │
│  ┌────────────┐                                                   │
│  │PROD_APPLIED│                                                   │
│  └─────┬──────┘                                                   │
│        │                                                           │
│        ├─────────────────┐                                         │
│        ▼                 ▼                                         │
│  ┌───────────┐   ┌──────────────┐                                 │
│  │ COMPLETED │   │PROD_ROLLBACK │                                 │
│  └───────────┘   └──────────────┘                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Decisioni Architetturali

| Decisione | Scelta | Motivazione |
|-----------|--------|-------------|
| **Reboot in TEST** | Auto-reboot + continue | Test orchestrator gestisce reboot e wait automaticamente |
| **VM Test** | 1 per OS | Test sequenziali, coda ordinata per Success Score |
| **Failed patch retry** | Auto-retry nuova versione | Tracking versione errata, auto re-queue |
| **Canary deployment** | Post-MVP | Per ora deploy simultaneo su tutti i PROD |
| **Dashboard** | Streamlit | Bassa complessità, Python-native, ~200 righe |
| **Monitoring** | Prometheus + Grafana | Stack standard, UYUNI Formulas disponibili |
| **Rollback** | Ibrido (Package + System) | Scelta operatore basata su contesto |
| **Prioritizzazione** | Success Score | Patch più sicure prima |
| **Componenti** | Separati | SPM-SYNC e SPM-ORCHESTRATOR indipendenti |

---

## 6. Matrice Nativo vs Sviluppo

| Funzionalità | UYUNI | SPM-SYNC | SPM-ORCHESTRATOR |
|--------------|-------|----------|------------------|
| Sync errata RHEL | ✅ | - | - |
| Sync errata Ubuntu/Debian | - | ✅ | - |
| CVE enrichment (CVSS) | - | ✅ | - |
| Push errata a UYUNI | - | ✅ | - |
| CLM (ambienti DEV/TEST/PROD) | ✅ | - | - |
| **Success Score calculation** | - | - | 🔨 |
| **Prioritized test queue** | - | - | 🔨 |
| Scheduling patch | ✅ | - | - |
| **Snapshot pre-patch** | - | - | 🔨 (Salt) |
| **Baseline metrics collection** | - | - | 🔨 |
| Applicazione patch | ✅ | - | - |
| **Post-patch validation** | - | - | 🔨 |
| **Reboot detection & management** | ✅ (parziale) | - | 🔨 |
| **Auto-rollback on fail** | - | - | 🔨 |
| **Approval dashboard** | - | - | 🔨 (Streamlit) |
| **Email notifications** | - | - | 🔨 |
| CLM Promote | ✅ | - | - |
| **Rollback trigger** | ✅ (parziale) | - | 🔨 |
| CVE Audit report | ✅ | - | - |
| **Monitoring dashboard** | - | - | ⚙️ (Grafana) |
| **Alerting** | - | - | ⚙️ (Grafana) |

**Legenda:** ✅ Nativo | 🔨 Da sviluppare | ⚙️ Da configurare

---

## 7. Schema Database

### Nuove Tabelle per SPM-ORCHESTRATOR

```sql
-- ============================================================
-- SCHEMA DATABASE SPM-ORCHESTRATOR
-- ============================================================

-- 1. Risk Profile (per Success Score)
CREATE TABLE patch_risk_profile (
    errata_id VARCHAR(50) PRIMARY KEY,

    -- Fattori rischio
    affects_kernel BOOLEAN DEFAULT FALSE,
    requires_reboot BOOLEAN DEFAULT FALSE,
    modifies_config BOOLEAN DEFAULT FALSE,
    dependency_count INTEGER DEFAULT 0,
    package_count INTEGER DEFAULT 1,
    total_size_kb INTEGER DEFAULT 0,

    -- Storico
    times_tested INTEGER DEFAULT 0,
    times_failed INTEGER DEFAULT 0,
    last_failure_reason TEXT,

    -- Score (calcolato da trigger o applicazione)
    success_score INTEGER DEFAULT 50,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_risk_score ON patch_risk_profile(success_score DESC);

-- 2. Test Queue (coda test ordinata)
CREATE TABLE patch_test_queue (
    id SERIAL PRIMARY KEY,
    errata_id VARCHAR(50) NOT NULL,
    errata_version VARCHAR(20),  -- Per tracking nuove versioni
    target_os VARCHAR(20) NOT NULL,  -- 'ubuntu' o 'rhel'
    priority INTEGER DEFAULT 0,  -- Override manuale
    success_score INTEGER DEFAULT 50,  -- Cached from risk_profile

    status VARCHAR(20) DEFAULT 'queued',
    -- queued, testing, passed, failed, needs_reboot,
    -- rebooting, pending_approval, approved, rejected,
    -- snoozed, promoting, prod_pending, prod_applied,
    -- completed, rolled_back

    queued_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Riferimento a dettagli test
    test_id INTEGER
);

CREATE INDEX idx_queue_status ON patch_test_queue(status);
CREATE INDEX idx_queue_priority ON patch_test_queue(success_score DESC, priority DESC);
CREATE INDEX idx_queue_os ON patch_test_queue(target_os);

-- 3. Test Results
CREATE TABLE patch_tests (
    id SERIAL PRIMARY KEY,
    queue_id INTEGER REFERENCES patch_test_queue(id),
    errata_id VARCHAR(50) NOT NULL,

    -- Sistema test
    test_system_id INTEGER,  -- UYUNI system ID
    test_system_name VARCHAR(100),

    -- Snapshot
    snapshot_id VARCHAR(100),
    snapshot_type VARCHAR(20),  -- 'snapper', 'lvm', 'azure'

    -- Timing
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_seconds INTEGER,

    -- Risultato
    result VARCHAR(20),  -- 'passed', 'failed', 'error'
    failure_reason TEXT,
    required_reboot BOOLEAN DEFAULT FALSE,
    reboot_successful BOOLEAN,

    -- Metriche (JSON per flessibilità)
    baseline_metrics JSONB,
    post_patch_metrics JSONB,
    metrics_delta JSONB,

    -- Servizi
    services_baseline JSONB,
    services_post_patch JSONB,
    failed_services TEXT[],

    -- Config
    test_config JSONB  -- Thresholds usati, etc.
);

CREATE INDEX idx_tests_errata ON patch_tests(errata_id);
CREATE INDEX idx_tests_result ON patch_tests(result);

-- Aggiorna foreign key in queue
ALTER TABLE patch_test_queue
    ADD CONSTRAINT fk_queue_test
    FOREIGN KEY (test_id) REFERENCES patch_tests(id);

-- 4. Approvals
CREATE TABLE patch_approvals (
    id SERIAL PRIMARY KEY,
    queue_id INTEGER REFERENCES patch_test_queue(id),
    errata_id VARCHAR(50) NOT NULL,

    action VARCHAR(20) NOT NULL,  -- 'approved', 'rejected', 'snoozed'
    approved_by VARCHAR(100),
    approved_at TIMESTAMP DEFAULT NOW(),

    reason TEXT,
    snooze_until TIMESTAMP,  -- Se snoozed

    -- Per audit
    ip_address VARCHAR(45),
    user_agent TEXT
);

CREATE INDEX idx_approvals_errata ON patch_approvals(errata_id);
CREATE INDEX idx_approvals_action ON patch_approvals(action);

-- 5. Production Deployments
CREATE TABLE patch_deployments (
    id SERIAL PRIMARY KEY,
    approval_id INTEGER REFERENCES patch_approvals(id),
    errata_id VARCHAR(50) NOT NULL,

    -- Sistemi target
    target_systems INTEGER[],  -- UYUNI system IDs
    total_systems INTEGER,

    -- Stato
    status VARCHAR(20) DEFAULT 'pending',
    -- pending, scheduled, in_progress, completed,
    -- partial_failure, rolled_back

    -- Timing
    scheduled_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Risultati
    systems_succeeded INTEGER DEFAULT 0,
    systems_failed INTEGER DEFAULT 0,
    failed_system_ids INTEGER[],

    -- Rollback
    rollback_performed BOOLEAN DEFAULT FALSE,
    rollback_type VARCHAR(20),  -- 'package', 'system'
    rollback_at TIMESTAMP
);

CREATE INDEX idx_deployments_status ON patch_deployments(status);
CREATE INDEX idx_deployments_errata ON patch_deployments(errata_id);

-- 6. Rollback History
CREATE TABLE patch_rollbacks (
    id SERIAL PRIMARY KEY,
    deployment_id INTEGER REFERENCES patch_deployments(id),
    errata_id VARCHAR(50) NOT NULL,

    rollback_type VARCHAR(20) NOT NULL,  -- 'package', 'system'
    target_systems INTEGER[],

    reason TEXT,
    initiated_by VARCHAR(100),

    status VARCHAR(20) DEFAULT 'in_progress',
    -- in_progress, completed, failed

    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,

    -- Risultati
    systems_succeeded INTEGER DEFAULT 0,
    systems_failed INTEGER DEFAULT 0,
    error_details JSONB
);

CREATE INDEX idx_rollbacks_deployment ON patch_rollbacks(deployment_id);

-- 7. Notifiche
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    -- 'test_failed', 'pending_approval', 'prod_failed',
    -- 'daily_digest', 'rollback_initiated'

    errata_id VARCHAR(50),
    queue_id INTEGER,

    recipient VARCHAR(200),  -- email o webhook URL
    channel VARCHAR(20),  -- 'email', 'webhook', 'grafana'

    subject VARCHAR(200),
    body TEXT,

    sent_at TIMESTAMP DEFAULT NOW(),
    delivered BOOLEAN DEFAULT FALSE,
    error_message TEXT
);

CREATE INDEX idx_notifications_type ON notifications(type, sent_at);
CREATE INDEX idx_notifications_delivered ON notifications(delivered);

-- 8. Configuration
CREATE TABLE orchestrator_config (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Default configuration
INSERT INTO orchestrator_config (key, value, description) VALUES
('score_weights', '{
    "kernel_penalty": 30,
    "reboot_penalty": 15,
    "config_penalty": 10,
    "dependency_penalty_per": 3,
    "dependency_penalty_max": 15,
    "size_penalty_per_mb": 2,
    "size_penalty_max": 10,
    "history_penalty_max": 20
}', 'Pesi per calcolo Success Score'),

('test_thresholds', '{
    "cpu_delta_percent": 20,
    "memory_delta_percent": 15,
    "max_failed_services": 0,
    "wait_after_patch_seconds": 300,
    "wait_after_reboot_seconds": 180
}', 'Soglie per validazione test'),

('notification_config', '{
    "email_enabled": true,
    "smtp_server": "",
    "recipients": [],
    "digest_time": "08:00",
    "webhook_enabled": false,
    "webhook_url": ""
}', 'Configurazione notifiche'),

('test_systems', '{
    "ubuntu": {"system_id": null, "system_name": "test-ubuntu-01"},
    "rhel": {"system_id": null, "system_name": "test-rhel-01"}
}', 'Sistemi di test per OS');
```

---

## 8. API Specification

### Componente 1: SPM-SYNC (Porta 5000) - Nessuna Modifica

Endpoint esistenti, nessuna modifica richiesta.

### Componente 2: SPM-ORCHESTRATOR (Porta 5001)

#### Health & Status

```
GET /api/v1/health

Response:
{
    "status": "healthy",
    "version": "1.0.0",
    "components": {
        "database": "connected",
        "prometheus": "connected",
        "uyuni": "connected",
        "salt": "connected"
    },
    "queue_stats": {
        "queued": 12,
        "testing": 1,
        "pending_approval": 5
    }
}
```

#### Success Score API

```
GET /api/v1/risk-profile
GET /api/v1/risk-profile/{errata_id}
POST /api/v1/risk-profile/calculate
```

#### Queue Management API

```
GET /api/v1/queue
POST /api/v1/queue/add
POST /api/v1/queue/sync
DELETE /api/v1/queue/{queue_id}
PATCH /api/v1/queue/{queue_id}
```

#### Test Execution API

```
POST /api/v1/test/start
GET /api/v1/test/{test_id}
GET /api/v1/test/{test_id}/result
POST /api/v1/test/{test_id}/abort
```

#### Approval Workflow API

```
GET /api/v1/approvals/pending
POST /api/v1/approvals/{queue_id}/approve
POST /api/v1/approvals/{queue_id}/reject
POST /api/v1/approvals/{queue_id}/snooze
POST /api/v1/approvals/batch
```

#### Deployment & Rollback API

```
GET /api/v1/deployments
GET /api/v1/deployments/{deployment_id}
POST /api/v1/deployments/{deployment_id}/start
POST /api/v1/rollback
GET /api/v1/rollback/{rollback_id}
```

#### Notifications API

```
GET /api/v1/notifications/config
PUT /api/v1/notifications/config
POST /api/v1/notifications/test
```

#### Reports API

```
GET /api/v1/reports/summary
GET /api/v1/reports/compliance
```

*Per dettagli completi su request/response bodies, vedere sezione API Details in appendice.*

---

## 9. Prometheus & Grafana

### Recording Rules

```yaml
groups:
  - name: patch_testing_metrics
    interval: 15s
    rules:
      - record: instance:cpu_usage:avg5m
        expr: |
          100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

      - record: instance:memory_usage:percent
        expr: |
          (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100

      - record: instance:services_failed:count
        expr: |
          count by (instance) (systemd_unit_state{state="failed"} == 1)

      - record: instance:services_running:count
        expr: |
          count by (instance) (systemd_unit_state{state="active", type="service"} == 1)
```

### Alert Rules

```yaml
groups:
  - name: patch_testing_alerts
    rules:
      - alert: TestSystemDown
        expr: up{job="patch-test-systems"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Test system {{ $labels.instance }} is down"

      - alert: ServiceFailedAfterPatch
        expr: instance:services_failed:count{job="patch-test-systems"} > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Services failed on {{ $labels.instance }}"

      - alert: PendingApprovalsTooLong
        expr: spm_pending_approvals_count > 0 and spm_oldest_pending_approval_hours > 48
        labels:
          severity: warning
        annotations:
          summary: "Patches pending approval for > 48 hours"
```

### Query per Validation

```python
PROMETHEUS_QUERIES = {
    "cpu_avg_5m": 'avg_over_time(instance:cpu_usage:avg5m{instance=~"$INSTANCE"}[5m])',
    "memory_percent": 'instance:memory_usage:percent{instance=~"$INSTANCE"}',
    "services_running": 'instance:services_running:count{instance=~"$INSTANCE"}',
    "services_failed": 'instance:services_failed:count{instance=~"$INSTANCE"}',
    "reboot_required": 'node_reboot_required{instance=~"$INSTANCE"}',
}
```

---

## 10. Success Score Algorithm

### Formula

```
SUCCESS_SCORE = 100 - (
    KERNEL_PENALTY         +    # 30 punti se tocca kernel/boot
    REBOOT_PENALTY         +    # 15 punti se richiede reboot
    CONFIG_PENALTY         +    # 10 punti se modifica config
    DEPENDENCY_PENALTY     +    # 0-15 punti (scala con n. dipendenze)
    SIZE_PENALTY           +    # 0-10 punti (scala con dimensione)
    HISTORY_PENALTY             # 0-20 punti (% fallimenti storici)
)

Ordine test: SUCCESS_SCORE DESC (prima i più alti = più sicuri)
```

### Pattern Recognition

```python
KERNEL_PATTERNS = [
    r'^linux-image', r'^linux-headers', r'^linux-modules',
    r'^kernel-', r'^grub', r'^shim-signed', r'^systemd-boot',
    r'^dracut', r'^initramfs',
]

REBOOT_PATTERNS = [
    r'^linux-', r'^kernel-', r'^glibc', r'^libc6',
    r'^systemd$', r'^dbus$', r'^openssl',
]

CONFIG_PATTERNS = [
    r'^openssh', r'^nginx', r'^apache2?', r'^httpd',
    r'^postgresql', r'^mysql', r'^mariadb',
]
```

### Score Interpretation

| Score Range | Risk Level | Recommendation |
|-------------|------------|----------------|
| 80-100 | Low | Safe to test early |
| 60-79 | Medium | Standard testing |
| 40-59 | High | Careful monitoring required |
| 0-39 | Very High | Consider manual review first |

---

## 11. Struttura Progetto

```
spm-orchestrator/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Flask app entry point
│   ├── config.py                  # Configuration management
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py              # /api/v1/health
│   │   ├── risk_profile.py        # /api/v1/risk-profile/*
│   │   ├── queue.py               # /api/v1/queue/*
│   │   ├── test.py                # /api/v1/test/*
│   │   ├── approvals.py           # /api/v1/approvals/*
│   │   ├── deployments.py         # /api/v1/deployments/*
│   │   ├── rollback.py            # /api/v1/rollback/*
│   │   ├── notifications.py       # /api/v1/notifications/*
│   │   └── reports.py             # /api/v1/reports/*
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── success_score.py       # Score calculation
│   │   ├── test_orchestrator.py   # Test execution logic
│   │   ├── prometheus_client.py   # Prometheus queries
│   │   ├── salt_client.py         # Salt API client
│   │   ├── uyuni_client.py        # UYUNI XML-RPC client
│   │   ├── notification_service.py # Email/webhook
│   │   └── snapshot_service.py    # Snapshot management
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── database.py            # SQLAlchemy models
│   │
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
│
├── salt-states/
│   ├── snapshot/
│   │   ├── create.sls
│   │   ├── restore.sls
│   │   └── delete.sls
│   ├── validation/
│   │   ├── reboot_check.sls
│   │   └── service_check.sls
│   └── pillar/
│       └── spm.sls
│
├── grafana/
│   ├── dashboards/
│   │   ├── patch-testing.json
│   │   └── compliance.json
│   └── provisioning/
│       └── dashboards.yml
│
├── prometheus/
│   ├── prometheus.yml
│   ├── rules/
│   │   ├── recording.yml
│   │   └── alerts.yml
│   └── alertmanager.yml
│
├── streamlit/
│   ├── app.py                     # Dashboard principale
│   ├── pages/
│   │   ├── 1_queue.py
│   │   ├── 2_approvals.py
│   │   ├── 3_deployments.py
│   │   └── 4_reports.py
│   └── requirements.txt
│
├── sql/
│   ├── schema.sql                 # Schema completo
│   └── migrations/
│       └── 001_initial.sql
│
├── docker/
│   ├── Dockerfile.orchestrator
│   ├── Dockerfile.streamlit
│   └── docker-compose.yml
│
├── tests/
│   └── ...
│
├── requirements.txt
└── README.md
```

---

## 12. Lacune e Rischi

### Lacune Identificate

| # | Lacuna | Impatto | Soluzione |
|---|--------|---------|-----------|
| L1 | Fallimento test su sistema TEST | Sistema TEST resta compromesso | Rebuild automatico da snapshot base |
| L2 | Timeout test | Test bloccato blocca coda | Timeout + kill + mark as failed |
| L3 | Concorrenza test | Test sequenziale lento | Future: test paralleli su più VM |
| L4 | Dipendenze tra patch | Ordine errato | Gestire ordine dipendenze oltre Score |
| L5 | UYUNI non raggiungibile | Test incompleto | Retry con backoff + stato pending_retry |
| L6 | Stato parziale PROD | Patch su alcuni sistemi | Tracking per-system dello stato |
| L7 | Rollback parziale | Solo alcuni sistemi problematici | Logica rollback selettivo |
| L8 | Validazione app-specifica | Check generici insufficienti | Framework custom health checks |

### Rischi e Mitigazioni

| Rischio | Probabilità | Impatto | Mitigazione |
|---------|-------------|---------|-------------|
| Prometheus down | Bassa | Alto | Fallback a check via Salt |
| Storage snapshot pieno | Media | Alto | Cleanup policy + alert |
| Dipendenze circolari | Bassa | Medio | Pre-check dipendenze |
| Operatore non approva | Media | Medio | Reminder + escalation |
| Falso positivo (FAIL ok) | Media | Basso | Review manuale, threshold config |
| Falso negativo (PASS ko) | Bassa | Alto | Smoke test custom, osservazione post-PROD |

---

## 13. Roadmap Implementazione

### Fase A: Database & API Core
- [ ] Schema database (tabelle sopra)
- [ ] API: Success Score calculation
- [ ] API: Queue management
- [ ] API: Test orchestration
- [ ] API: Approval endpoints
- [ ] API: Rollback trigger

### Fase B: Salt States
- [ ] State: snapshot create (snapper)
- [ ] State: snapshot restore
- [ ] State: reboot required check
- [ ] State: service health check

### Fase C: Prometheus/Grafana
- [ ] Deploy exporters via UYUNI Formula
- [ ] Recording rules per validation
- [ ] Alert rules
- [ ] Dashboard: patch testing
- [ ] Dashboard: compliance

### Fase D: Streamlit Dashboard
- [ ] Vista queue
- [ ] Vista test results
- [ ] Approval/Reject/Snooze buttons
- [ ] Rollback trigger
- [ ] Filtri e ricerca

### Fase E: Notifications
- [ ] Email digest giornaliero
- [ ] Alert immediato su failure
- [ ] Webhook per ITSM (opzionale)

---

## 14. Checklist Pre-Implementazione

| # | Item | Stato | Note |
|---|------|-------|------|
| 1 | UYUNI CLM configurato (DEV/TEST/PROD) | ⬜ | Prerequisito |
| 2 | System Groups definiti | ⬜ | test-systems, prod-systems |
| 3 | Prometheus server installato | ⬜ | UYUNI Formula o standalone |
| 4 | node_exporter su sistemi TEST | ⬜ | UYUNI Formula |
| 5 | Grafana installato | ⬜ | UYUNI Formula o standalone |
| 6 | Connessione SPM → Prometheus | ⬜ | Network/firewall |
| 7 | Snapper/LVM su sistemi TEST | ⬜ | Per snapshot |
| 8 | SMTP server per email | ⬜ | Per notifiche |
| 9 | Spazio storage per snapshot | ⬜ | Capacity planning |
| 10 | Sistemi TEST dedicati | ⬜ | Non production |

---

## Appendice: API Details

*Vedere file separato `SPM-ORCHESTRATOR-API-SPEC.md` per specifiche complete request/response.*

---

## Changelog

| Versione | Data | Autore | Modifiche |
|----------|------|--------|-----------|
| 1.0 | 2026-02-05 | - | Documento iniziale |
