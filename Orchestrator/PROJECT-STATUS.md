# SPM-Orchestrator — Project Status & Development Notes

> Documento vivente. Aggiornare ad ogni sessione di sviluppo.
> Ultima modifica: 2026-03-12 (sessione 14)

---

## Indice

1. [Architettura attuale](#1-architettura-attuale)
2. [Stack tecnologico](#2-stack-tecnologico)
3. [Stato implementazione](#3-stato-implementazione)
4. [API Endpoints](#4-api-endpoints)
5. [Database Schema](#5-database-schema)
6. [Decisioni architetturali](#6-decisioni-architetturali)
7. [Performance e ottimizzazioni](#7-performance-e-ottimizzazioni)
8. [Backlog](#8-backlog)
9. [Note tecniche](#9-note-tecniche)
10. [Deploy](#10-deploy)

---

## 1. Architettura attuale

```
VM-ORCHESTRATOR (Ubuntu 24.04 — 10.172.2.22)
├── Flask API        :5001   → Orchestrazione REST
├── Streamlit        :8501   → Dashboard operatore (HTTPS, cert self-signed)
├── PostgreSQL       :5432   → DB locale (spm_orchestrator)
└── APScheduler              → Poller UYUNI (ogni 30 min) + Test Engine poll (ogni 2 min)

Dipendenze esterne:
├── UYUNI Server    10.172.2.17:443   → XML-RPC (fonte errata + scheduling patch)
├── Prometheus      localhost:9090    → Metriche validazione         [ATTIVO]
└── node_exporter   :9100             → sui sistemi test (auto-provisioning via UYUNI)

Sistemi di test:
├── Ubuntu 24.04   10.172.2.18   system_id=1000010000   (gruppo UYUNI: test-ubuntu-2404)
└── RHEL 9         10.172.2.19   system_id=1000010008   (gruppo UYUNI: test-rhel9)
```

**Note architetturali:**
- `PROMETHEUS_URL` ha default `http://localhost:9090` — non serve nel `.env`
- Prometheus non è critico: se non disponibile la fase `validate` è skippata silenziosamente
- Gruppi UYUNI monitorati: prefisso `test-` (es. `test-ubuntu-2404`, `test-rhel9`)
- Accesso VM: Azure Bastion (no SCP/rsync diretto)

---

## 2. Stack tecnologico

| Componente | Tecnologia |
|---|---|
| API | Python 3.x, Flask 3.x, Flask-CORS |
| Scheduler | APScheduler 3.x (BackgroundScheduler) |
| Database | PostgreSQL 16 (psycopg2, RealDictCursor, ThreadedConnectionPool) |
| UYUNI Client | xmlrpc.client (XML-RPC) |
| Parallelismo | concurrent.futures.ThreadPoolExecutor |
| Bulk DB | psycopg2.extras.execute_values |
| Logging | python-json-logger (JSON strutturato → journald + file) |
| Servizio Flask | systemd (spm-orchestrator.service) |
| Dashboard | Streamlit 1.x (spm-dashboard.service, HTTPS con cert self-signed) |
| Autenticazione | Azure AD SSO via MSAL (OAuth2/OIDC) |
| Prometheus Client | requests (HTTP API PromQL) |

---

## 3. Stato implementazione

### Versione corrente: 1.3.0

### COMPLETATO

#### Infrastruttura backend
- [x] Schema PostgreSQL — 10 tabelle + views + triggers + functions
- [x] Flask app factory con 7 blueprint registrati
- [x] Systemd service (`spm-orchestrator.service`)
- [x] Logging JSON strutturato (stdout + file `/var/log/spm-orchestrator/app.log`)
- [x] Config centralizzata da `.env` con defaults sicuri
- [x] ThreadedConnectionPool PostgreSQL (1-10 connessioni) con keepalive
- [x] Reconnect automatico su connessioni stale (fix double-putconn: `returned=True` prima del putconn per evitare corruzione pool)

#### UYUNI Integration
- [x] `UyuniSession` — sessione thread-safe (1 login/logout per ciclo, non per call)
- [x] Fetch gruppi `test-*`, sistemi, errata applicabili, CVEs, pacchetti
- [x] Poller APScheduler → `errata_cache` (sync ogni 30 min + sync iniziale)
- [x] `_parse_uyuni_date` — gestisce `xmlrpc.client.DateTime`, datetime, ISO string
- [x] Severity mapping: Security Advisory → Medium, Bug Fix/Enhancement → Low
- [x] `os_from_group()` — mappa gruppo UYUNI → target_os (ubuntu/rhel/debian)
- [x] `add_note()` — aggiunge nota su sistema UYUNI (usato da batch summary)
- [x] `get_current_org()` — ritorna nome organizzazione UYUNI
- [x] `list_orgs()` — lista tutte le org UYUNI (satellite admin); fallback a org corrente
- [x] `get_system_network_ip()` — risolve IP via system.getNetwork (per Prometheus)
- [x] Auto-discovery attiva quando `system_id`, `system_name` o `system_ip` mancano
- [x] `advisory_synopsis` (non `synopsis`) — campo corretto in system.getRelevantErrata
- [x] `UYUNI_TIMEOUT` propagato via `_UyuniTransport` (nessun timeout di sistema implicito)

#### Performance sync (ottimizzato 2026-02-23)
- [x] ThreadPoolExecutor per fetch parallelo sistemi + errata + CVEs
- [x] `execute_values` batch upsert (1 transazione vs N individuali)
- [x] CVEs fetchati solo per Security Advisory (non Bug Fix/Enhancement)
- [x] `as_completed()` con `timeout=Config.UYUNI_TIMEOUT * 3` — evita hang indefinito

#### Queue Manager
- [x] `add_to_queue` — fetch pacchetti on-demand, calcolo Success Score, insert coda
- [x] `add_to_queue` ritorna `row["superseded"]` con lista errata auto-soppressi
- [x] `extract_advisory_base()` — `USN-7412-2` → `USN-7412` (None per non-USN)
- [x] `_suppress_older_queued_errata()` — sopprime errata più vecchie per famiglia USN o package overlap
- [x] `get_queue` — lista con filtri (status, target_os, severity, limit, offset)
- [x] `get_queue_stats` — include `retry_pending` e `superseded` nei conteggi
- [x] `remove_from_queue` — rimozione solo se status='queued'

#### Success Score (0-100)
- [x] Penalità kernel: -30, reboot: -15, config: -10
- [x] Penalità dipendenze: -3/dep (max -15)
- [x] Penalità dimensione: -2/MB (max -10)
- [x] Penalità storico fallimenti: fino a -20 (se tested >= 3)
- [x] Bonus patch piccola (<100 KB): +5
- [x] Pesi configurabili da `orchestrator_config` (DB)

#### Test Engine
- [x] `run_next_test()` — singolo test bloccante, thread-safe con `_testing_lock`
- [x] Flusso a fasi: **pre_check** → snapshot → patch → reboot → validate → services → rollback → **post_rollback**
- [x] `_phase_preflight()` — verifica servizi baseline, spazio disco (min 500 MB), reboot pendente
- [x] `_phase_verify_rollback()` — verifica servizi dopo rollback (best-effort)
- [x] `_rollback_and_verify()` — rollback + verifica combinati
- [x] `_classify_error()` — INFRA / TRANSIENT / PATCH / REGRESSION
- [x] `_maybe_retry()` — INFRA: max 2 retry 2h delay; TRANSIENT: max 3 retry 30min delay
- [x] `_pick_next_queued()` — include anche `retry_pending` con `retry_after <= NOW()`
- [x] Rollback Ubuntu → `apt-get --allow-downgrades`, RHEL → `dnf install` (target_os propagato)
- [x] Fallback automatico da snapshot a package rollback se snapper non disponibile
- [x] Service check con 6 retry x 20s (tolleranza SSH post-patch)
- [x] `_DEFAULT_SERVICES["ubuntu"]` = `["ssh.socket", "cron", "rsyslog"]`
- [x] Auto-provisioning `ensure_node_exporter()` + `ensure_snapper()` via UYUNI channels
- [x] Baseline metriche Prometheus pre-patch + delta post-patch (skipped se non disponibile)
- [x] `_wait_action()` — `schedule.listCompletedSystems/listFailedSystems` (scoped per action_id)
- [x] Batch asincrono: `start_batch()` → thread background → polling ogni 5s dashboard
- [x] Batch persistenti su DB (`patch_test_batches`) — sopravvivono al restart Flask
- [x] `cancel_batch()` — cancella tra un test e il successivo (status='cancelled')
- [x] Ordinamento coda: priority DESC → no-reboot prima → score DESC → queued_at ASC
- [x] Timing configurabile: `TEST_REBOOT_DELIVERY_WAIT_SECONDS` (60s), `TEST_REBOOT_STABILIZATION_SECONDS` (30s)

#### Approval Workflow
- [x] approve/reject/snooze con audit trail completo in `patch_approvals`
- [x] `process_snoozed()` ogni 15 min — riporta a pending_approval le patch scadute

#### Notification Manager
- [x] Scrittura sempre in `orchestrator_notifications` (delivered=FALSE → banner dashboard)
- [x] Canale unico: `dashboard` — audit esteso delegato a note UYUNI (`add_note`)
- [x] Tipi: `test_failure`, `pending_approval`
- [x] Fix storico: constraint `channel='dashboard'` (bug critico migration 003)

#### Sicurezza API
- [x] `FLASK_HOST=127.0.0.1` — Flask binds solo su loopback
- [x] `SPM_API_KEY` — header `X-SPM-Key` obbligatorio su tutti gli endpoint tranne `/health*` e `/prometheus/targets`
- [x] Warning all'avvio se `SECRET_KEY` è il valore di default
- [x] Validazione `ids` (lista interi positivi, max 1000) in `POST /notifications/mark-read`
- [x] Azure AD SSO — `require_auth()` su ogni pagina Streamlit (defense-in-depth)

#### Dashboard Streamlit (4 pagine)
- [x] `app.py` — Azure AD SSO (MSAL OAuth2/OIDC), `st.navigation()`, sidebar multi-org
- [x] `0_Home.py` — Health componenti, notifiche non lette, stats coda/test, sync manuale; **"Avviato il"** (data/ora avvio servizio) invece di uptime in minuti; **"Patch pendenti"** = queued+retry_pending+pending_approval+failed (patch che richiedono azione, non il totale storico)
- [x] `1_Gruppi_UYUNI.py` — Gruppi test-* per org, patch con colonna **Reboot** e **Stato** (🟢 Ultima / ⬜ Superata), toggle "Solo patch più recenti", aggiunta in coda
- [x] `2_Test_Batch.py` — Tab **"Panoramica"** (stats engine, 6 metriche status, stats 24h, tabella completa tutte le patch con stato/fase KO/motivo/durata/data ordinata per data decrescente) + Tab **"Avvia Batch"** (selezione + lancio); family color grouping; rendering fasi delegato a `test_render.py`
- [x] `3_Approvazioni.py` — Tab **"In attesa"** (approve/reject/snooze con pipeline visuale) + Tab **"Fallite & Retry"** (tabella retry_pending con retry countdown + expander fallite con failure_reason e test detail) + Tab **"Storico"** paginato
- [x] `test_render.py` — modulo condiviso rendering test: `render_pipeline()`, `render_phases_table()`, `render_prometheus_section()`, `render_test_detail()`
- [x] `api_client.py` — Wrapper REST, ritorna `(data, error_str)`

#### Groups API
- [x] `_enrich_reboot_info()` — arricchisce requires_reboot/affects_kernel da DB o inferenza
- [x] `_enrich_latest_info()` — arricchisce is_latest/superseded_by (famiglia USN + package overlap)
- [x] Ordinamento: latest first → no-reboot first → data discendente
- [x] Multi-org: `GET /api/v1/orgs` + filtro `org_id` su `/api/v1/groups`

#### Prometheus Integration
- [x] `PrometheusClient` con graceful degradation completa
- [x] `GET /api/v1/prometheus/targets` — HTTP Service Discovery dinamico da UYUNI
- [x] `is_available()` usa `Config.PROMETHEUS_TIMEOUT` (non hardcoded 5s)

#### Sessione 16 — Dashboard UX, dati coerenti, patch fallite visibili (2026-03-12)

**Backend**
- [x] **`queue_manager.reset_stale_testing()`**: nuova funzione — resetta `testing → queued` all'avvio. Chiama `main.py` dopo `init_db()` con log warning. Risolve patch bloccate in "In test" dopo riavvio Flask.
- [x] **`queue_manager.get_queue_stats()`**: `ubuntu` e `rhel` ora contano solo patch in stati attivi (`queued + retry_pending + testing + failed`), non più tutta la coda storica (incluse `pending_approval`, `approved`, ecc.).
- [x] **`queue_manager.get_queue()`**: aggiunto `t.failure_reason`, `t.failure_phase` (da `patch_tests`) e `q.retry_count`, `q.retry_after` in ogni item restituito dalla lista coda.

**Frontend `0_Home.py`**
- [x] **"Errata totali" → "Patch applicabili"** con help tooltip. Rimossa chiamata lenta a UYUNI (`groups_list`) per il conteggio sistemi. Caption mostra `Ubuntu: X | RHEL: Y` da `errata_cache.by_os`.
- [x] **Caption coda**: rimossa metrica `passed` (sempre 0 — le patch passate vanno in `pending_approval`). Sostituita con `In retry`. Mostra solo i valori > 0: `Ubuntu | RHEL | In retry | Falliti`.

**Frontend `2_Test_Batch.py`**
- [x] **Ristrutturato con due tab**: "Panoramica" e "Avvia Batch".
- [x] **Tab "Panoramica"**: stato engine, 6 metriche (queued/retry/testing/pending_approval/failed/approved), stats ultime 24h, tabella completa di tutte le patch in ogni stato con colonne Stato, Errata, OS, Gravità, Score, Reboot, Fase KO, Motivo, Durata, Data — ordinata per data decrescente.
- [x] **Tab "Avvia Batch"**: identico a prima (selezione + family grouping + lancio).

**Frontend `3_Approvazioni.py`**
- [x] **Nuovo tab "Fallite & Retry"**: tabella `retry_pending` con retry #, prossimo tentativo, motivo; expander per ogni patch `failed` con failure_phase, failure_reason e `tr.render_test_detail()` completo.

#### Sessione 15 — `3_Approvazioni.py` arricchimento + refactoring rendering (2026-03-12)
- [x] **Nuovo modulo `streamlit/test_render.py`**: estratte le funzioni di rendering test da `2_Test_Batch.py` in modulo condiviso (`render_pipeline`, `render_phases_table`, `render_prometheus_section`, `render_test_detail`, `fmt_duration`, `elapsed`, `phase_detail`)
- [x] **`3_Approvazioni.py`**: sostituito display minimale fasi (icone + caption) con `tr.render_test_detail()` — pipeline visuale, tabella fasi con durate e dettaglio, metriche Prometheus, motivo fallimento
- [x] **`2_Test_Batch.py`**: rimosse definizioni locali di funzioni ora in `test_render.py`; rimosso import `datetime`/`timezone` (non più usati direttamente); chiamate aggiornate a `tr.*`

#### Sessione 14 — Bug fix, refactoring, UX (2026-03-12)
- [x] **Bug fix — `db.py`**: double-putconn nel path di riconnessione: se `conn.closed=True` e il secondo `getconn()` fallisce, la vecchia connessione già restituita al pool veniva messa nel `finally` una seconda volta → corruzione pool. Fix: `returned=True` prima del primo putconn.
- [x] **Bug fix — `test_engine.py`**: import `get_test_system_for_os` presente ma mai usato → rimosso
- [x] **Bug fix — `uyuni_patch_client.py`**: variabile `arch` assegnata ma mai usata nel calcolo versione → rimossa
- [x] **Bug fix — `api/sync.py`**: `import psycopg2` (intero modulo) solo per `psycopg2.ProgrammingError` → sostituito con `from psycopg2 import ProgrammingError`
- [x] **Bug fix — `api/health.py`**: `serialize_row` importata ma mai usata → rimossa
- [x] **Bug fix — test suite**: 2 test legacy `priority_override` rimasti dalla sessione 13 → rimossi (276/276 ✓)
- [x] **Docstring stale**: `queue_manager.py` e `api/queue.py` citavano ancora `priority_override` in `update_queue_item` → aggiornati
- [x] **Dead code — `2_Test_Batch.py`**: condizione `s not in ("reboot", "rollback")` in `_render_pipeline` — "rollback" non è mai in `_PIPELINE_STEPS` → semplificato a `s != "reboot"`
- [x] **Versione**: bump `1.2.1` → `1.3.0` in `config.py`
- [x] **UX — Home — Avviato il**: metric "Uptime (min)" sostituito con "Avviato il" (data) + caption "alle HH:MM UTC". Nuovo campo `started_at` in `/api/v1/health/detail` (ISO UTC). Dopo una settimana di uptime i minuti non hanno senso.
- [x] **UX — Home — Patch pendenti**: metric "Totale" (accumulava anche `passed`/`approved` → sempre crescente) sostituito con **"Patch pendenti"** = `queued + retry_pending + pending_approval + failed`. Solo patch che richiedono ancora azione operatore. Tooltip spiega la formula.
- [x] **Migration 006** applicata sul VM: `retry_count`, `retry_after`, `superseded_by` in `patch_test_queue`

#### Azure AD SSO
- [x] Tenant: fae8df93-7cf5-40da-b480-f272e15b6242
- [x] App Registration "SPM Dashboard" (OAuth2/OIDC separata da Enterprise App SAML UYUNI)
- [x] UPN operatore registrato nelle note UYUNI e nei record SPM (audit trail)

---

## 4. API Endpoints

### Health & Notifiche

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/health` | Ping rapido |
| GET | `/api/v1/health/detail` | Health check con DB/UYUNI/Prometheus; include `started_at` (ISO UTC) |
| GET | `/api/v1/notifications` | Notifiche non lette |
| POST | `/api/v1/notifications/mark-read` | Marca come lette (body: `{ids: [...]}`) |

### Sync UYUNI

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/sync/status` | Stato poller + statistiche ultimo run |
| POST | `/api/v1/sync/trigger` | Trigger manuale sync (bloccante) |
| GET | `/api/v1/errata/cache/stats` | Statistiche errata_cache locale |

### Queue

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/queue` | Lista coda (filtri: status, target_os, severity) |
| POST | `/api/v1/queue` | Aggiungi errata(s); risposta include `superseded: [...]` |
| GET | `/api/v1/queue/stats` | Aggregati (include retry_pending, superseded) |
| GET | `/api/v1/queue/<id>` | Dettaglio elemento |
| PATCH | `/api/v1/queue/<id>` | Aggiorna notes |
| DELETE | `/api/v1/queue/<id>` | Rimuovi (solo se status='queued') |

### Test Engine

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/tests/status` | Stato engine + stats 24h |
| POST | `/api/v1/tests/run` | Trigger manuale test singolo (bloccante) |
| POST | `/api/v1/tests/batch` | Avvia batch asincrono |
| GET | `/api/v1/tests/batch/<id>/status` | Polling stato batch |
| POST | `/api/v1/tests/batch/<id>/cancel` | Cancella batch in esecuzione |
| GET | `/api/v1/tests/<id>` | Dettaglio test con fasi |

### Approvazioni

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/approvals/pending` | Lista patch in attesa (paginata) |
| GET | `/api/v1/approvals/pending/<id>` | Dettaglio patch per revisione |
| POST | `/api/v1/approvals/<id>/approve` | Approva |
| POST | `/api/v1/approvals/<id>/reject` | Rifiuta |
| POST | `/api/v1/approvals/<id>/snooze` | Rimanda |
| GET | `/api/v1/approvals/history` | Storico audit trail |

### Gruppi UYUNI e Organizzazioni

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/orgs` | Lista organizzazioni UYUNI |
| GET | `/api/v1/groups[?org_id=N]` | Gruppi test-* con sistemi e patch count |
| GET | `/api/v1/groups/<name>/patches` | Patch per gruppo con `is_latest`, `superseded_by` |

### Prometheus

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/prometheus/targets` | HTTP Service Discovery dinamico |

---

## 5. Database Schema

### Tabelle

| Tabella | Ruolo |
|---|---|
| `errata_cache` | Cache locale errata da UYUNI (sync ogni 30 min) |
| `patch_risk_profile` | Success Score + analisi pacchetti per errata |
| `patch_test_queue` | Coda test patch con stato workflow completo |
| `patch_tests` | Dettaglio singolo test (metriche, snapshot, reboot) |
| `patch_test_phases` | Fasi di ogni test (pre_check/snapshot/patch/reboot/validate/services/rollback/post_rollback) |
| `patch_test_batches` | Batch asincroni persistenti (running/completed/cancelled/error) |
| `patch_approvals` | Log approvazioni/rifiuti/snooze operatore |
| `patch_deployments` | Deployment produzione (schema presente, non usato — out of scope) |
| `patch_rollbacks` | Log rollback deployment (schema presente, non usato) |
| `orchestrator_notifications` | Notifiche operatore dashboard (delivered=FALSE = non lette) |
| `orchestrator_config` | Configurazione runtime (score_weights, critical_services, ecc.) |

### Migrations applicate

| File | Contenuto | Stato |
|---|---|---|
| `001_orchestrator_schema.sql` | Schema completo + views + triggers + config iniziale | ✅ APPLICATA |
| `002_fix_errata_cache.sql` | Fix errata_cache | ✅ APPLICATA |
| `003_simplify_notifications.sql` | Fix constraint `channel` (bug critico) | ✅ APPLICATA |
| `004_batch_persistence.sql` | Tabella `patch_test_batches` | ✅ APPLICATA |
| `005_critical_services_config.sql` | Configurazione runtime servizi critici | ✅ APPLICATA |
| `006_retry_grouping.sql` | retry_count, retry_after, superseded_by; stati retry_pending, superseded | ✅ APPLICATA |

### Views

| View | Contenuto |
|---|---|
| `v_queue_details` | Coda con join errata + risk profile |
| `v_pending_approvals` | Patch passed in attesa approvazione (con hours_pending) |
| `v_daily_stats` | Statistiche giornaliere ultimi 30 giorni |

### Stati patch_test_queue

```
queued         → testing → pending_approval → approved → [operatore applica su produzione]
                                             → rejected
                                             → snoozed  → pending_approval (allo scadere)
                        → failed → rolled_back
                        → failed → retry_pending → queued (allo scadere retry_after)
superseded     (rimossa dalla vista principale — sostituita da patch più recente)
```

### Vincoli critici

```sql
-- patch_test_queue.status: 'error' NON è un valore valido → usare 'failed'
-- patch_tests.result: 'pending_approval' NON è un valore valido → usare 'passed'
-- FOR UPDATE su JOIN con LEFT JOIN → usare FOR UPDATE OF q SKIP LOCKED
-- superseded va escluso dal duplicate check (può essere re-accodato)
```

---

## 6. Decisioni architetturali

### 6.1 UYUNI come source of truth
UYUNI conosce già quali patch sono applicabili a ciascun sistema. Il poller interroga
direttamente via XML-RPC: solo ~634 errata rilevanti invece di ~50.000.

### 6.2 UyuniSession singola (1 login/logout per ciclo)
Ogni login XML-RPC costa ~300ms. Con 634 errata in sequenza = ~200s overhead.
Soluzione: login una sola volta, chiave condivisa tra thread via `threading.local()`.

### 6.3 Produzione out of scope
Il sistema copre solo il flusso test → approvazione. L'applicazione in produzione
è competenza dell'operatore su UYUNI (deployment_manager rimosso deliberatamente).

### 6.4 Azure AD SSO — NON credenziali UYUNI
La dashboard usa Azure AD per autenticare l'operatore. Le chiamate XML-RPC UYUNI
usano sempre le credenziali admin da `.env`. L'UPN operatore è registrato nel
audit trail SPM e nelle note UYUNI, ma non è mai usato per autenticare su UYUNI.

### 6.5 Prometheus opzionale con graceful degradation
- Se non disponibile: fase `validate` skippata silenziosamente, test continua
- `PROMETHEUS_URL` ha default `http://localhost:9090` — non serve nel `.env`
- `is_available()` controlla prima di ogni uso (timeout da `Config.PROMETHEUS_TIMEOUT`)

### 6.6 Rollback — due metodi + fallback automatico

```
Patch fallita:
  ├── requires_reboot = True  →  snapshot (snapper undochange via UYUNI)
  └── requires_reboot = False →  package rollback

Package rollback:
  ├── Ubuntu  →  apt-get install --allow-downgrades 'pkg=version'
  └── RHEL    →  dnf install -y 'pkg-version'

Se snapper non disponibile: fallback automatico a package rollback
(anche per patch kernel — prefer rollable over nothing)
```

Post-rollback: `_phase_verify_rollback()` controlla servizi critici (best-effort).

### 6.7 Retry intelligente (sessione 11)

```
Classificazione errore:
  INFRA      → [INFRA] in reason, pre_check fallito, sistema offline
               → max 2 retry, delay 2h
  TRANSIENT  → timeout, connection error, socket, reboot fallito
               → max 3 retry, delay 30min
  PATCH      → applicazione patch fallita (fase 'patch')
               → no retry (problema intrinseco della patch)
  REGRESSION → servizi down o validate fallito post-patch
               → no retry (richiede analisi manuale)
```

### 6.8 Supersessione patch (sessione 11)
L'operatore sceglie le patch più recenti dalla vista arricchita (`is_latest`, `superseded_by`).
Al momento dell'inserimento in coda, le patch più vecchie con stessa famiglia USN o
package overlap vengono automaticamente marcate come `superseded`.
Il toggle "Solo patch più recenti" in dashboard filtra la vista per OS.

### 6.9 Pacchetti fetchati on-demand
`packages` in `errata_cache` è popolato solo quando l'errata viene accodata,
non durante il sync. Risparmio: ~100s per 634 errata.

---

## 7. Performance e ottimizzazioni

### Sync UYUNI — benchmark (634 errata, 2 gruppi, 2 sistemi)

| Fase | Prima (sequenziale) | Dopo (ottimizzato) |
|---|---|---|
| Auth overhead (N login) | ~200s | ~1s (1 coppia) |
| `get_errata_details` x634 | ~100s | 0s (eliminato) |
| `get_relevant_errata` | ~10s | ~2s (parallelo) |
| `get_errata_cves` (solo Security) | ~30s | ~8s (parallelo) |
| DB upsert | ~5s | ~1s (batch) |
| **Totale** | **~340s (5:39 min)** | **~12s** |

**Configurazione parallelismo:** `UYUNI_SYNC_WORKERS=10`

### `_wait_action()` ottimizzato (sessione 10)
Usa `schedule.listCompletedSystems(key, action_id)` / `listFailedSystems(key, action_id)`
invece di `listCompletedActions` / `listFailedActions` (globali). Riduce drasticamente
il payload su istanze UYUNI con molte azioni storiche.

---

## 8. Backlog

### [CODICE — priorità media] Refactoring `test_engine.py`

Il file è 1200+ righe. Può essere spezzato in moduli separati senza cambiare il comportamento:
- `app/services/test_phases.py` — le funzioni `_phase_*` (snapshot, patch, reboot, validate, services, rollback)
- `app/services/test_batch.py` — batch asincrono: `start_batch`, `get_batch_status`, `cancel_batch`, `_run_batch_background`
- `app/services/test_engine.py` — solo: retry/classificazione errori, `run_next_test`, `get_engine_status`

Prerequisito: nessuna modifica funzionale, solo riorganizzazione file.

### [COMPLETATO] NVD Enrichment severity — integrazione con Errata-Parser

La severity NVD-enriched arriva in Orchestrator **tramite UYUNI** (fonte unica di verità):

```
NVD NIST → Errata-Parser (10.172.2.30)
               ↓ errata.create / errata.setDetails
           UYUNI (10.172.2.17)
               ↓ errata.getDetails (durante sync)
           Orchestrator errata_cache.severity = Critical | High | Medium | Low
```

**Come funziona:**
- Errata-Parser crea/aggiorna errata in UYUNI con severity NVD-enriched
  - USN/DSA: via `errata.create()` al primo push
  - RHEL: via `errata.setDetails()` post-NVD enrichment
- Orchestrator poller, durante il sync, chiama `errata.getDetails(advisory_name)`
  per ogni Security Advisory → legge la severity reale invece del mapping statico
- Mapping UYUNI label → interno: Critical→Critical, Important→High, Moderate→Medium, Low→Low
- Fallback: se UYUNI restituisce "Unspecified" o errore → `severity_from_advisory_type()`

**File modificati (v1.2.1):**
- `app/services/uyuni_client.py`: aggiunto `_UYUNI_SEVERITY_MAP` + `get_errata_details_severity()`
- `app/services/poller.py`: step ④ esteso con fetch severity parallelo (stesso executor CVE)

**Performance:** le chiamate `errata.getDetails` vengono parallelizzate insieme ai CVE
nello stesso ThreadPoolExecutor — overhead minimo rispetto al sync esistente.

### [CODICE — futuro] Validazione funzionale
Oltre a `systemctl is-active`, validare che i servizi siano effettivamente operativi
(es. HTTP health check per webserver, query DB per database, ecc.).
Non implementato: richiede configurazione per-servizio, out of scope per ora.

---

## 9. Note tecniche

### SSH socket activation (Ubuntu 24.04)
`ssh.service` è inactive tra connessioni su Ubuntu 24.04 con socket activation.
Usare `ssh.socket` (non `ssh.service`) nella lista dei servizi critici.
Già configurato in `_DEFAULT_SERVICES["ubuntu"]` e in `orchestrator_config` (migration 005).

### Package rollback — limitazione
Il rollback package può fallire se la versione precedente non è più nel repository
(rimossa dopo una security patch successiva). In questo caso l'operatore viene
notificato via `orchestrator_notifications` e deve intervenire manualmente.
Snapper evita questo problema — installarlo sui sistemi test è raccomandato.

### Azure AD — SAML vs OAuth2
- UYUNI web UI usa SAML 2.0 con Azure AD (Enterprise App separata)
- SPM Dashboard usa OAuth2/OIDC (App Registration "SPM Dashboard")
- Le due registrazioni Azure AD sono separate e indipendenti

### Fasi registrate in patch_test_phases
Tutti i nomi fase validi (usati per il DB e per i log):
`pre_check`, `snapshot`, `patch`, `reboot`, `validate`, `services`, `rollback`, `post_rollback`

### Retry e concurrent batch
Il retry è gestito a livello di singolo item in coda, non a livello di batch.
Se un batch è in esecuzione e un item fa retry, l'item riapparirà nella coda
solo dopo `retry_after` ed essere processato da un batch successivo (o da `run_next_test`).

---

## 10. Deploy

### Procedura standard (REGOLA FISSA — usare sempre git)

```bash
# Committare modifiche locali prima
git add Orchestrator/
git commit -m "descrizione modifiche"
git push origin main

# Sul VM (via Azure Bastion)
cd /opt/Security-Patch-Manager && git pull origin main

# Backend Flask
cp -r /opt/Security-Patch-Manager/Orchestrator/app /opt/spm-orchestrator/
sudo systemctl restart spm-orchestrator

# Frontend Streamlit (legge i file direttamente, basta restart)
sudo systemctl restart spm-dashboard

# Verifica
sudo systemctl status spm-orchestrator --no-pager
sudo systemctl status spm-dashboard --no-pager
journalctl -u spm-orchestrator -n 30 --no-pager
```

### Verifica rapida

```bash
curl http://localhost:5001/api/v1/health
curl http://localhost:5001/api/v1/health/detail | python3 -m json.tool
curl -X POST http://localhost:5001/api/v1/sync/trigger | python3 -m json.tool
curl http://localhost:5001/api/v1/prometheus/targets | python3 -m json.tool
```

### Variabili ambiente

```bash
# /opt/spm-orchestrator/.env
UYUNI_URL=https://10.172.2.17
UYUNI_USER=admin
UYUNI_PASSWORD=...
UYUNI_VERIFY_SSL=false
UYUNI_POLL_INTERVAL_MINUTES=30
UYUNI_SYNC_WORKERS=10
DB_PASSWORD=...
SPM_API_KEY=<token-hex-32>

# Test Engine timing (tutti opzionali — defaults in config.py)
TEST_WAIT_AFTER_PATCH_SECONDS=300
TEST_WAIT_AFTER_REBOOT_SECONDS=180
TEST_REBOOT_DELIVERY_WAIT_SECONDS=60
TEST_REBOOT_STABILIZATION_SECONDS=30

# PROMETHEUS_URL — NON necessario se Prometheus è su localhost:9090 (default)

# /opt/Security-Patch-Manager/Orchestrator/streamlit/.env
SPM_API_URL=http://localhost:5001
SPM_API_KEY=<stesso-token-hex-32>
AZURE_TENANT_ID=fae8df93-7cf5-40da-b480-f272e15b6242
AZURE_CLIENT_ID=<client-id>
AZURE_CLIENT_SECRET=<client-secret>
AZURE_REDIRECT_URI=https://10.172.2.22:8501
```

### Path VM

| Risorsa | Path |
|---|---|
| App Flask | `/opt/spm-orchestrator/app/` |
| .env Flask | `/opt/spm-orchestrator/.env` |
| Venv Flask | `/opt/spm-orchestrator/venv/` |
| Repo | `/opt/Security-Patch-Manager/` |
| Streamlit | `/opt/Security-Patch-Manager/Orchestrator/streamlit/` |
| Venv Streamlit | `/opt/Security-Patch-Manager/Orchestrator/streamlit/.venv/` |
| SSL cert | `/opt/spm-orchestrator/ssl/cert.pem` + `key.pem` |
| Log Flask | `journalctl -u spm-orchestrator` + `/var/log/spm-orchestrator/app.log` |
| DB | `psql -h localhost -U spm_orch -d spm_orchestrator` |

### Query DB utili

```sql
-- Ultimi test
SELECT id, errata_id, result, failure_phase, failure_reason, duration_seconds
  FROM patch_tests ORDER BY started_at DESC LIMIT 10;

-- Coda attuale (include retry_pending e superseded)
SELECT id, errata_id, status, success_score, target_os, retry_count, retry_after
  FROM patch_test_queue ORDER BY queued_at DESC LIMIT 20;

-- Retry programmati
SELECT id, errata_id, retry_count, retry_after
  FROM patch_test_queue WHERE status = 'retry_pending'
  ORDER BY retry_after ASC;

-- Patch soppresse
SELECT id, errata_id, superseded_by, queued_at
  FROM patch_test_queue WHERE status = 'superseded'
  ORDER BY queued_at DESC LIMIT 20;

-- Notifiche non lette
SELECT id, notification_type, subject, delivered, sent_at
  FROM orchestrator_notifications WHERE delivered = FALSE ORDER BY sent_at DESC;

-- Pending approvals
SELECT queue_id, errata_id, success_score, hours_pending
  FROM v_pending_approvals ORDER BY priority_override DESC, hours_pending DESC;
```
