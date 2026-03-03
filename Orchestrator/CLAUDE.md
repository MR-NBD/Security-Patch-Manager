# Security Patch Manager — Note per Claude Code

---

## Deployment sul VM (REGOLA FISSA)

**Usare SEMPRE git per deployare modifiche sul VM. MAI base64.**

```bash
cd /opt/Security-Patch-Manager && git pull origin main
cp -r /opt/Security-Patch-Manager/Orchestrator/app /opt/spm-orchestrator/
sudo systemctl restart spm-orchestrator
```

- VM Orchestrator: `10.172.2.22` — accesso via Azure Bastion (no SCP, no rsync)
- Repo pubblico: `https://github.com/MR-NBD/Security-Patch-Manager.git`
- Clone sul VM: `/opt/Security-Patch-Manager`
- Working dir servizio: `/opt/spm-orchestrator`
- Il base64 copy-paste è **vietato**: stringhe lunghe → errori silenziosi

---

## Architettura generale

```
┌─────────────────────────────────────────────────────────┐
│  SPM-ORCHESTRATOR  (10.172.2.22:5001)                   │
│  Flask 3.x · APScheduler · psycopg2 · PostgreSQL        │
│                                                          │
│  Poller ──────────────────────────────→ UYUNI XML-RPC   │
│  (sync errata ogni 30 min)              10.172.2.17      │
│                                                          │
│  Test Engine ─────────────────────────→ UYUNI XML-RPC   │
│  (patch test su VM test via UYUNI)      (scheduleApply,  │
│                                          scheduleScript,  │
│                                          scheduleReboot)  │
│                                                          │
│  Approval API ────────────────────────→ PostgreSQL       │
│  Deployment Manager ──────────────────→ PostgreSQL       │
│  Notification Manager ────────────────→ PostgreSQL       │
│                           (+ SMTP/webhook se configurati)│
└─────────────────────────────────────────────────────────┘

Test VM Ubuntu 24.04:  10.172.2.18  (UYUNI system_id=1000010000)
Test VM RHEL 9:        10.172.2.19  (UYUNI system_id=1000010008)
UYUNI server:          10.172.2.17  (XML-RPC /rpc/api, SSL verify off)
```

---

## Componenti e file principali

### Flask App

| File | Ruolo |
|---|---|
| `app/main.py` | Entry point, factory `create_app()`, avvio scheduler |
| `app/config.py` | Config da `.env` — `Config.*` |
| `app/utils/logger.py` | Setup logging centralizzato |

### API Blueprints (`app/api/`)

| Blueprint | Prefix | Descrizione |
|---|---|---|
| `health.py` | `/api/v1/health` | Health check |
| `sync.py` | `/api/v1/sync` | Trigger sync UYUNI manuale |
| `queue.py` | `/api/v1/queue` | Gestione coda test patch |
| `tests.py` | `/api/v1/tests` | Test engine status e risultati |
| `approvals.py` | `/api/v1/approvals` | Workflow approvazione patch |
| `deployments.py` | `/api/v1/deployments` | Deployment in produzione |

### Services (`app/services/`)

| File | Ruolo |
|---|---|
| `db.py` | Pool connessioni PostgreSQL (`get_db()`, `init_db()`) |
| `uyuni_client.py` | `UyuniSession` — sync errata da UYUNI (poller) |
| `uyuni_patch_client.py` | `UyuniPatchClient` — applicazione patch su VM test |
| `poller.py` | Sync UYUNI → `errata_cache` (ogni 30 min via APScheduler) |
| `queue_manager.py` | Inserimento in `patch_test_queue` |
| `test_engine.py` | Test automatici patch (fasi, rollback, notifiche) |
| `notification_manager.py` | Scrittura `orchestrator_notifications` + email/webhook |
| `approval_manager.py` | Workflow approve/reject/snooze + re-queue snoozed |
| `deployment_manager.py` | Deploy in produzione + rollback |
| `prometheus_client.py` | Metriche baseline/post-patch (best-effort, opzionale) |
| `salt_client.py` | **NON USATO** — mantenuto ma non importato dal test engine |

---

## UYUNI — dettagli integrazione

### UyuniSession (`uyuni_client.py`)
Usata dal **poller** per sync errata:
- 1 login/logout per ciclo di sync
- Thread-safe: `threading.local()` per i proxy XML-RPC
- `get_test_groups()` → gruppi con prefisso `test-`
- `get_relevant_errata(system_id)` → errata applicabili
- `get_errata_cves(advisory_name)` → CVE associati
- `get_errata_packages(advisory_name)` → pacchetti errata

### UyuniPatchClient (`uyuni_patch_client.py`)
Usata dal **test engine** per applicare patch su VM test:
- Wrappa `UyuniSession` come context manager
- Tutte le azioni UYUNI sono **asincrone**: schedule → `action_id` → polling `_wait_action()`
- `_wait_action()`: polling ogni 10s su `schedule.listCompleted/FailedActions`

| Metodo | API UYUNI | Note |
|---|---|---|
| `ping()` | `system.getDetails` | Verifica sistema registrato |
| `take_snapshot(desc)` | `system.scheduleScriptRun` | `snapper create --print-number` |
| `apply_errata(name, pkgs)` | `system.scheduleApplyErrata` | Cattura versioni old prima; timeout 30 min |
| `reboot()` | `system.scheduleReboot` | Solo schedula, non attende |
| `wait_online(timeout)` | ping + echo script | Attesa 30s fissi poi polling ogni 15s |
| `get_failed_services(_, svcs)` | `system.scheduleScriptRun` | `systemctl is-active` per ogni servizio |
| `rollback_snapshot(snap_id)` | `system.scheduleScriptRun` | `snapper undochange N..0` |
| `rollback_packages(pkgs_before)` | `system.scheduleScriptRun` | `apt-get install --allow-downgrades` |

### Auto-discovery sistemi test
`get_test_system_for_os(target_os)` interroga i gruppi UYUNI con prefisso `test-`:
- `test-ubuntu-2404` → system_id=1000010000 (10.172.2.18)
- `test-rhel9` → system_id=1000010008 (10.172.2.19)

La `.env` ha priorità (`TEST_SYSTEM_UBUNTU_ID`, `TEST_SYSTEM_RHEL_ID`).
Se non configurata → auto-discovery automatica.

---

## Test Engine — workflow a fasi

```
_pick_next_queued()         ← FOR UPDATE OF q SKIP LOCKED (PostgreSQL)
    ↓
pre_check                   ← uyuni.ping()
    ↓
① snapshot (best-effort)    ← snapper create (se fallisce su Ubuntu → rollback_type="package")
    ↓
② patch                     ← scheduleApplyErrata (versioni old catturate prima)
    ↓
③ reboot (solo kernel)      ← scheduleReboot + wait_online()
   oppure sleep(wait_after_patch)
    ↓
④ validate (opzionale)      ← Prometheus delta CPU/MEM (skipped se non disponibile)
    ↓
⑤ services (3×retry 10s)   ← systemctl is-active per servizi critici
    ↓
→ pending_approval          ← test superato, in attesa operatore
```

**In caso di fallimento in qualsiasi fase:**
```
⑥ rollback
   rollback_type="snapshot" → snapper undochange N..0
   rollback_type="package"  → apt-get install --allow-downgrades (versioni old reali)
```

### Rollback strategy
- **Snapshot** (`requires_reboot=True`, patch kernel): `snapper undochange N..0` via UYUNI
- **Package** (`requires_reboot=False`): `apt-get --allow-downgrades` con versioni reali catturate da `system.listPackages` prima dell'applicazione
- **Snapper non disponibile** (Ubuntu 24.04): fallback automatico a package rollback
- **Azure rollback**: NON integrato — decisione deliberata. UYUNI copre la maggioranza dei casi. Se il sistema diventa irraggiungibile dopo una patch, l'operatore viene notificato tramite `orchestrator_notifications`.

### Vincoli PostgreSQL critici
```sql
-- patch_test_queue.status: 'error' NON è un valore valido
-- → in test_engine.py: queue_status = "failed" if final_result == "error" else final_result
CONSTRAINT chk_queue_status CHECK (status IN (
    'queued', 'testing', 'passed', 'failed', 'needs_reboot', 'rebooting',
    'pending_approval', 'approved', 'rejected', 'snoozed',
    'promoting', 'prod_pending', 'prod_applied', 'completed', 'rolled_back'
))

-- patch_tests.result: 'pending_approval' NON è un valore valido
-- → in test_engine.py: test_result = "passed" if final_result == "pending_approval" else final_result
CONSTRAINT chk_test_result CHECK (result IS NULL OR result IN ('passed', 'failed', 'error', 'aborted'))

-- FOR UPDATE su JOIN con LEFT JOIN → errore PostgreSQL
-- → usare FOR UPDATE OF q SKIP LOCKED (non FOR UPDATE SKIP LOCKED)
```

---

## Notification Manager

Chiamato automaticamente alla fine di ogni test da `test_engine._execute_test`.

| Evento | `notification_type` | Condizione config |
|---|---|---|
| Test FAILED / ERROR | `test_failure` | `alert_on_test_failure=true` |
| Test superato, attende approvazione | `pending_approval` | `alert_on_pending_approval=true` |

**Comportamento:**
- Scrive **sempre** in `orchestrator_notifications` (con `delivered=False` se email/webhook off)
- La dashboard legge `WHERE delivered = FALSE` per mostrare banner
- Email SMTP: attivabile con `email_enabled=true` in `orchestrator_config['notification_config']`
- Webhook HTTP POST JSON: attivabile con `webhook_enabled=true` + `webhook_url`
- Best-effort: non solleva mai eccezioni, non blocca il flusso del test

Configurazione via `orchestrator_config` (tabella DB), chiave `notification_config`:
```json
{
  "email_enabled": false,
  "smtp_server": "", "smtp_port": 587, "smtp_tls": true,
  "smtp_user": "", "smtp_password": "",
  "from_address": "spm@example.com",
  "recipients": [],
  "alert_on_test_failure": true,
  "alert_on_pending_approval": true,
  "webhook_enabled": false,
  "webhook_url": "",
  "webhook_auth_header": ""
}
```

---

## Database — tabelle principali

| Tabella | Ruolo |
|---|---|
| `errata_cache` | Cache locale errata da UYUNI (synopsis, severity, packages, CVEs) |
| `patch_risk_profile` | Success Score, requires_reboot, times_tested, last_failure_reason |
| `patch_test_queue` | Coda test ordinata per score/priorità |
| `patch_tests` | Risultati test (fasi, metriche, rollback, failure_reason) |
| `patch_test_phases` | Dettaglio per fase (snapshot/patch/reboot/validate/services/rollback) |
| `patch_approvals` | Audit trail approve/reject/snooze |
| `patch_deployments` | Deploy in produzione |
| `patch_rollbacks` | Rollback deploy produzione |
| `orchestrator_notifications` | Notifiche operatore (delivered=False = non lette) |
| `orchestrator_config` | Configurazione runtime (score_weights, notification_config, ecc.) |

**Migrations:** `Orchestrator/sql/migrations/`
- `001_orchestrator_schema.sql` — schema completo + views + triggers
- `002_fix_errata_cache.sql` — fix errata_cache

---

## API — endpoint principali

```
# Sync UYUNI
POST /api/v1/sync/trigger          → sync manuale errata_cache

# Coda test
GET  /api/v1/queue                 → lista coda
POST /api/v1/queue                 → aggiungi patch in coda
GET  /api/v1/queue/<id>            → dettaglio

# Test Engine
GET  /api/v1/tests/status          → stato engine + stats 24h
POST /api/v1/tests/run             → trigger manuale test (bloccante)
GET  /api/v1/tests/<id>            → dettaglio test con fasi

# Approvazioni
GET  /api/v1/approvals/pending     → lista pending_approval
GET  /api/v1/approvals/pending/<queue_id>
POST /api/v1/approvals/<queue_id>/approve
POST /api/v1/approvals/<queue_id>/reject
POST /api/v1/approvals/<queue_id>/snooze

# Deployment produzione
POST /api/v1/deployments           → crea + esegui deployment (bloccante)
GET  /api/v1/deployments           → lista
GET  /api/v1/deployments/<id>
POST /api/v1/deployments/<id>/rollback
```

---

## Variabili d'ambiente rilevanti (`.env`)

```bash
# UYUNI
UYUNI_URL=https://10.172.2.17
UYUNI_USER=admin
UYUNI_PASSWORD=...
UYUNI_VERIFY_SSL=false
UYUNI_POLL_INTERVAL_MINUTES=30
UYUNI_SYNC_WORKERS=10          # worker ThreadPoolExecutor per sync parallelo

# Sistemi test (opzionale — se vuoti usa auto-discovery da gruppi UYUNI)
TEST_SYSTEM_UBUNTU_ID=1000010000
TEST_SYSTEM_UBUNTU_NAME=10.172.2.18
TEST_SYSTEM_UBUNTU_IP=10.172.2.18
TEST_SYSTEM_RHEL_ID=1000010008
TEST_SYSTEM_RHEL_NAME=10.172.2.19
TEST_SYSTEM_RHEL_IP=10.172.2.19

# Test Engine timing
TEST_WAIT_AFTER_PATCH_SECONDS=300   # attesa stabilizzazione post-patch (no reboot)
TEST_WAIT_AFTER_REBOOT_SECONDS=180  # timeout wait_online dopo reboot

# Prometheus (opzionale)
PROMETHEUS_URL=http://localhost:9090
```

---

## Comandi utili sul VM

```bash
# Stato servizio
sudo systemctl status spm-orchestrator
sudo journalctl -u spm-orchestrator -f

# Log applicazione
sudo tail -f /var/log/spm-orchestrator/app.log

# PostgreSQL
psql -h localhost -U spm_orch -d spm_orchestrator

# Query utili
SELECT id, errata_id, status, failure_phase, failure_reason
  FROM patch_tests ORDER BY started_at DESC LIMIT 10;

SELECT id, notification_type, subject, delivered, sent_at
  FROM orchestrator_notifications ORDER BY sent_at DESC LIMIT 10;

SELECT id, errata_id, status, success_score
  FROM patch_test_queue ORDER BY queued_at DESC LIMIT 10;

# Test manuale API
curl -s http://localhost:5001/api/v1/health | python3 -m json.tool
curl -s http://localhost:5001/api/v1/tests/status | python3 -m json.tool
curl -X POST http://localhost:5001/api/v1/sync/trigger | python3 -m json.tool
curl -X POST http://localhost:5001/api/v1/tests/run | python3 -m json.tool

# Aggiungere patch in coda (esempio)
curl -X POST http://localhost:5001/api/v1/queue \
  -H "Content-Type: application/json" \
  -d '{"errata_id":"USN-7412-2","target_os":"ubuntu","created_by":"operator"}'
```

---

## Stato attuale e cosa manca

### Implementato e funzionante
- Sync UYUNI → `errata_cache` (parallelo, ~15-20s per 634 errata)
- Auto-discovery sistemi test da gruppi UYUNI (`test-ubuntu-2404`, `test-rhel9`)
- Test engine completo con fasi: snapshot → patch → reboot → validate → services
- Rollback: snapshot (snapper) o package (apt downgrade con versioni reali)
- Fallback package rollback quando snapper non disponibile (Ubuntu 24.04)
- Service check con 3 retry × 10s (tolleranza riavvio servizi post-patch)
- Workflow approvazione (approve/reject/snooze + re-queue automatico)
- Deployment manager (produzione)
- Notification manager (DB sempre + email/webhook opzionali)
- Prometheus (best-effort, graceful skip se non disponibile)

### Da fare / prossime sessioni
- Dashboard Streamlit (lettura API + visualizzazione notifiche non lette)
- Test end-to-end completo con approvazione → deploy produzione
- Verifica rollback package con versioni reali (fix implementata, da testare)
- Configurare `TEST_WAIT_AFTER_PATCH_SECONDS=30` in `.env` per testing rapido
- Eventuale integrazione email/webhook notifiche quando l'ambiente è pronto
