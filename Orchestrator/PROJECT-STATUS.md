# SPM-Orchestrator — Project Status & Development Notes

> Documento vivente. Aggiornare ad ogni sessione di sviluppo.
> Ultima modifica: 2026-03-05 (sessione 7)

---

## Indice

1. [Architettura attuale](#1-architettura-attuale)
2. [Stack tecnologico](#2-stack-tecnologico)
3. [Stato implementazione](#3-stato-implementazione)
4. [API Endpoints](#4-api-endpoints)
5. [Database Schema](#5-database-schema)
6. [Decisioni architetturali](#6-decisioni-architetturali)
7. [Performance e ottimizzazioni](#7-performance-e-ottimizzazioni)
8. [Da fare — backlog](#8-da-fare--backlog)
9. [Note tecniche e decisioni rilevanti](#9-note-tecniche-e-decisioni-rilevanti)
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
├── Prometheus      localhost:9090    → Metriche validazione         [DA INSTALLARE]
└── node_exporter   :9100             → sui sistemi test (gia' attivo)

Sistemi di test:
├── Ubuntu 24.04   10.172.2.18   system_id=1000010000   (gruppo UYUNI: test-ubuntu-2404)
└── RHEL 9         10.172.2.19   system_id=1000010008   (gruppo UYUNI: test-rhel9)
```

**Nota Prometheus:** `PROMETHEUS_URL` ha gia' il default `http://localhost:9090` in `config.py`.
Non serve aggiungere la variabile al `.env` — basta installare il server Prometheus sul VM.
Il codice ha graceful degradation completa: se Prometheus non e' raggiungibile, la fase validate
viene saltata silenziosamente e il test continua.

**Gruppi UYUNI monitorati:** prefisso `test-` (es. `test-ubuntu-2404`, `test-rhel9`)
**OS supportati:** Ubuntu 24.04, RHEL 9
**Accesso VM:** Azure Bastion (no SCP/rsync diretto)

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

### COMPLETATO

#### Infrastruttura backend
- [x] Schema PostgreSQL — 10 tabelle + views + triggers + functions
- [x] Flask app factory con 7 blueprint registrati
- [x] Systemd service (`spm-orchestrator.service`)
- [x] Logging JSON strutturato (stdout + file `/var/log/spm-orchestrator/app.log`)
- [x] Config centralizzata da `.env` con defaults sicuri
- [x] ThreadedConnectionPool PostgreSQL (1-10 connessioni) con keepalive
- [x] Reconnect automatico su connessioni stale

#### UYUNI Integration
- [x] `UyuniSession` — sessione thread-safe (1 login/logout per ciclo, non per call)
- [x] Fetch gruppi `test-*`, sistemi, errata applicabili, CVEs, pacchetti
- [x] Poller APScheduler → `errata_cache` (sync ogni 30 min + sync iniziale)
- [x] `_parse_uyuni_date` — gestisce `xmlrpc.client.DateTime`, datetime, ISO string
- [x] Severity mapping: Security Advisory → Medium, Bug Fix/Enhancement → Low
- [x] `os_from_group()` — mappa gruppo UYUNI → target_os (ubuntu/rhel/debian)
- [x] `add_note()` — aggiunge nota su sistema UYUNI (usato da batch summary)
- [x] `validate_credentials()` — verifica credenziali UYUNI (residuo pre-SSO, non piu' usato)
- [x] `get_current_org()` — ritorna nome organizzazione UYUNI (usato dalla dashboard)
- [x] `list_orgs()` — lista tutte le org UYUNI (satellite admin); fallback a org corrente
- [x] `get_system_network_ip()` — risolve IP via system.getNetwork (per Prometheus)
- [x] Auto-discovery attiva quando `system_id`, `system_name` o `system_ip` mancano

#### Performance sync (ottimizzato 2026-02-23)
- [x] ThreadPoolExecutor per fetch parallelo sistemi + errata + CVEs
- [x] `execute_values` batch upsert (1 transazione vs N individuali)
- [x] CVEs fetchati solo per Security Advisory (non Bug Fix/Enhancement)
- [x] Eliminata chiamata `get_errata_details()` (non necessaria)
- [x] `advisory_synopsis` (non `synopsis`) — campo corretto in system.getRelevantErrata

#### Queue Manager
- [x] `add_to_queue` — fetch pacchetti on-demand, calcolo Success Score, insert coda
- [x] `get_queue` — lista con filtri (status, target_os, severity, limit, offset)
- [x] `get_queue_item` — dettaglio con errata + risk profile + test results
- [x] `update_queue_item` — aggiorna priority_override / notes
- [x] `remove_from_queue` — rimozione solo se status='queued'
- [x] `get_queue_stats` — aggregati coda (total, by_status, by_os, avg_score)

#### Success Score (0-100)
- [x] Penalita' kernel: -30
- [x] Penalita' reboot: -15
- [x] Penalita' config: -10
- [x] Penalita' dipendenze: -3/dep (max -15)
- [x] Penalita' dimensione: -2/MB (max -10)
- [x] Penalita' storico fallimenti: fino a -20 (se tested >= 3)
- [x] Bonus patch piccola (<100 KB): +5
- [x] Pesi configurabili da `orchestrator_config` (DB) o `.env`

#### Test Engine
- [x] `run_next_test()` — singolo test bloccante, thread-safe con `_testing_lock`
- [x] Flusso a fasi: pre_check → snapshot → patch → reboot → validate → services
- [x] Rollback: snapshot (snapper undochange) o package (apt downgrade versioni reali)
- [x] Fallback automatico da snapshot a package rollback se snapper non disponibile
- [x] Service check con 6 retry x 20s (tolleranza SSH post-patch)
- [x] `_DEFAULT_SERVICES["ubuntu"]` = `["ssh.socket", "cron", "rsyslog"]`
- [x] Auto-provisioning node_exporter: prima della baseline, l'engine verifica se node_exporter
      e' attivo sul sistema test; se manca lo installa automaticamente via UYUNI
      schedulePackageInstall dai canali software sincronizzati (senza intervento manuale)
- [x] Baseline metriche Prometheus pre-patch + delta post-patch (skipped se non disponibile)
- [x] Poll scheduler ogni 2 minuti (APScheduler)
- [x] Batch asincrono: `start_batch()` → thread background → polling ogni 5s dalla dashboard
- [x] `_add_batch_note()` — aggiunge nota di riepilogo su tutti i sistemi del gruppo UYUNI
- [x] `_prune_old_batches()` — pulizia automatica batch >24h in memoria (chiamata da start_batch)
- [x] Vincoli DB rispettati: queue usa 'failed' (non 'error'), test usa 'passed' (non 'pending_approval')
- [x] `FOR UPDATE OF q SKIP LOCKED` — safe per istanze concorrenti
- [x] Ordinamento coda: priority DESC → no-reboot prima → score DESC → queued_at ASC
- [x] Reboot delivery wait configurabile (`TEST_REBOOT_DELIVERY_WAIT_SECONDS`, default 60s)
- [x] Reboot stabilization wait configurabile (`TEST_REBOOT_STABILIZATION_SECONDS`, default 30s)

#### Approval Workflow
- [x] approve/reject/snooze con audit trail completo in `patch_approvals`
- [x] process_snoozed() ogni 15 min — riporta a pending_approval le patch scadute
- [x] Storia approvazioni con join errata + queue

#### Notification Manager
- [x] Scrittura sempre in `orchestrator_notifications` (delivered=False se canale non configurato)
- [x] Email SMTP opzionale (attivabile via `orchestrator_config`)
- [x] Webhook HTTP POST JSON opzionale
- [x] Dashboard legge notifiche non lette (banner di attenzione)
- [x] Tipi: `test_failure`, `pending_approval`

#### Prometheus Integration
- [x] `PrometheusClient` con graceful degradation completa
- [x] Snapshot CPU% e memoria% via PromQL (node_exporter standard)
- [x] `evaluate_delta()` — confronta baseline vs post-patch con threshold configurabili
- [x] `is_available()` — check disponibilita' prima di ogni uso
- [x] `GET /api/v1/prometheus/targets` — HTTP Service Discovery dinamico per Prometheus
  - Interroga UYUNI per tutti i sistemi test-*
  - Risolve IP via system.getNetwork se il nome profilo non e' un IP
  - Restituisce formato HTTP SD: `[{"targets": ["IP:9100"], "labels": {...}}]`

#### Dashboard Streamlit (4 pagine)
- [x] `app.py` — Azure AD SSO (MSAL OAuth2/OIDC), st.navigation(), sidebar utente+org con selector multi-org
- [x] `0_Home.py` — Health componenti, notifiche non lette, stats coda/test, sync manuale
- [x] `1_Gruppi_UYUNI.py` — Gruppi test-* (filtrati per org), patch con colonna Reboot, aggiunta in coda
- [x] `2_Test_Batch.py` — Selezione patch queued con banner reboot, avvio batch, monitor live polling 5s
- [x] `3_Approvazioni.py` — Pending approvals con dettaglio CVE/fasi/risk, approve/reject/snooze + storico
- [x] `api_client.py` — Wrapper REST, tutte le funzioni ritornano (data, error_str)
- [x] `azure_auth.py` — MSAL helpers: get_auth_url, exchange_code, get_user_info

#### Azure AD SSO
- [x] Tenant: fae8df93-7cf5-40da-b480-f272e15b6242
- [x] App Registration "SPM Dashboard" (OAuth2/OIDC separata da Enterprise App SAML UYUNI)
- [x] Redirect URI: `https://10.172.2.22:8501`
- [x] Operatore identificato da UPN (user_upn) e display_name (user_name)
- [x] UYUNI XML-RPC usa account admin da .env (NON le credenziali dell'operatore)
- [x] UPN operatore registrato nelle note UYUNI e nei record SPM (audit trail)

#### API Endpoints implementati (tutti)
- [x] `GET  /api/v1/health`
- [x] `GET  /api/v1/health/detail`
- [x] `GET  /api/v1/notifications`
- [x] `POST /api/v1/notifications/mark-read`
- [x] `GET  /api/v1/sync/status`
- [x] `POST /api/v1/sync/trigger`
- [x] `GET  /api/v1/errata/cache/stats`
- [x] `GET  /api/v1/queue`
- [x] `POST /api/v1/queue`
- [x] `GET  /api/v1/queue/stats`
- [x] `GET  /api/v1/queue/<id>`
- [x] `PATCH /api/v1/queue/<id>`
- [x] `DELETE /api/v1/queue/<id>`
- [x] `GET  /api/v1/tests/status`
- [x] `POST /api/v1/tests/run`
- [x] `POST /api/v1/tests/batch`
- [x] `GET  /api/v1/tests/batch/<batch_id>/status`
- [x] `GET  /api/v1/tests/<test_id>`
- [x] `GET  /api/v1/approvals/pending`
- [x] `GET  /api/v1/approvals/pending/<queue_id>`
- [x] `POST /api/v1/approvals/<queue_id>/approve`
- [x] `POST /api/v1/approvals/<queue_id>/reject`
- [x] `POST /api/v1/approvals/<queue_id>/snooze`
- [x] `GET  /api/v1/approvals/history`
- [x] `GET  /api/v1/orgs`
- [x] `GET  /api/v1/groups[?org_id=N]`
- [x] `GET  /api/v1/groups/<name>/patches`
- [x] `GET  /api/v1/prometheus/targets`

#### Rimosso (fuori scope)
- deployment_manager.py (produzione out of scope)
- salt_client.py (sostituito da UYUNI XML-RPC diretto)
- api/deployments.py

---

## 4. API Endpoints

### Health & Notifiche

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/health` | Ping rapido (usato da watchdog/load balancer) |
| GET | `/api/v1/health/detail` | Health check con DB/UYUNI/Prometheus |
| GET | `/api/v1/notifications` | Notifiche non lette (param: limit, mark_read) |
| POST | `/api/v1/notifications/mark-read` | Marca come lette (body: {ids: [...]} o {} per tutte) |

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
| POST | `/api/v1/queue` | Aggiungi errata(s) alla coda |
| GET | `/api/v1/queue/stats` | Aggregati coda |
| GET | `/api/v1/queue/<id>` | Dettaglio elemento |
| PATCH | `/api/v1/queue/<id>` | Aggiorna priority_override / notes |
| DELETE | `/api/v1/queue/<id>` | Rimuovi (solo se status='queued') |

### Test Engine

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/tests/status` | Stato engine + stats 24h |
| POST | `/api/v1/tests/run` | Trigger manuale test singolo (bloccante) |
| POST | `/api/v1/tests/batch` | Avvia batch asincrono (body: queue_ids, group_name, operator) |
| GET | `/api/v1/tests/batch/<id>/status` | Polling stato batch |
| GET | `/api/v1/tests/<id>` | Dettaglio test con fasi |
| POST | `/api/v1/tests/validate-operator` | Valida credenziali UYUNI (residuo, non usato) |

### Approvazioni

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/approvals/pending` | Lista patch in attesa (paginata) |
| GET | `/api/v1/approvals/pending/<id>` | Dettaglio patch per revisione |
| POST | `/api/v1/approvals/<id>/approve` | Approva (body: action_by, reason) |
| POST | `/api/v1/approvals/<id>/reject` | Rifiuta (body: action_by, reason) |
| POST | `/api/v1/approvals/<id>/snooze` | Rimanda (body: action_by, snooze_until, reason) |
| GET | `/api/v1/approvals/history` | Storico audit trail |

### Gruppi UYUNI e Organizzazioni

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/orgs` | Lista organizzazioni UYUNI visibili all'account admin |
| GET | `/api/v1/groups[?org_id=N]` | Lista gruppi test-* con sistemi e patch count (filtro org opzionale) |
| GET | `/api/v1/groups/<name>/patches` | Patch applicabili per gruppo (con requires_reboot da DB) |

### Prometheus

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/prometheus/targets` | HTTP Service Discovery dinamico |

---

## 5. Database Schema

### Tabelle (10)

| Tabella | Ruolo |
|---|---|
| `errata_cache` | Cache locale errata da UYUNI (sync ogni 30 min) |
| `patch_risk_profile` | Success Score + analisi pacchetti per errata |
| `patch_test_queue` | Coda test patch con stato workflow completo |
| `patch_tests` | Dettaglio singolo test (metriche, snapshot, reboot) |
| `patch_test_phases` | Fasi di ogni test (snapshot/patch/reboot/validate/services/rollback) |
| `patch_approvals` | Log approvazioni/rifiuti/snooze operatore |
| `patch_deployments` | Deployment produzione (schema presente, non usato — out of scope) |
| `patch_rollbacks` | Log rollback deployment (schema presente, non usato) |
| `orchestrator_notifications` | Notifiche operatore (delivered=False = non lette) |
| `orchestrator_config` | Configurazione runtime (score weights, notification_config, ecc.) |

### Views

| View | Contenuto |
|---|---|
| `v_queue_details` | Coda con join errata + risk profile |
| `v_pending_approvals` | Patch passed in attesa approvazione (con hours_pending) |
| `v_daily_stats` | Statistiche giornaliere ultimi 30 giorni |

### Vincoli critici

```sql
-- patch_test_queue.status: 'error' NON e' un valore valido → usare 'failed'
-- patch_tests.result: 'pending_approval' NON e' un valore valido → usare 'passed'
-- FOR UPDATE su JOIN con LEFT JOIN → usare FOR UPDATE OF q SKIP LOCKED
```

### Stati patch_test_queue

```
queued → testing → pending_approval → approved → [operatore applica su produzione]
                                    → rejected
                                    → snoozed  → pending_approval (allo scadere)
               → failed → rolled_back
```

---

## 6. Decisioni architetturali

### 6.1 UYUNI come source of truth
UYUNI conosce gia' quali patch sono applicabili a ciascun sistema. Il poller interroga
direttamente via XML-RPC: solo 634 errata rilevanti invece di ~50.000.

### 6.2 UyuniSession singola (1 login/logout per ciclo)
Ogni login XML-RPC costa ~300ms. Con 634 errata in sequenza = ~200s overhead.
Soluzione: login una sola volta, chiave condivisa tra thread via `threading.local()`.

### 6.3 Produzione out of scope
Deployment_manager rimosso deliberatamente. Il sistema copre solo il flusso
test → approvazione. L'applicazione in produzione e' competenza dell'operatore su UYUNI.

### 6.4 Azure AD SSO (MSAL) — NON credenziali UYUNI
La dashboard usa Azure AD per autenticare l'operatore. Le chiamate XML-RPC UYUNI
usano sempre le credenziali admin da .env. L'UPN operatore e' registrato nel
audit trail SPM e nelle note UYUNI (add_note), ma non e' mai usato per autenticare su UYUNI.

### 6.5 Prometheus opzionale
Prometheus non e' critico per il flusso base. Se non disponibile:
- La fase validate e' saltata silenziosamente (skipped, non failed)
- Il test engine continua normalmente
- L'health check riporta Prometheus come "unavailable" (non blocca il servizio)
- `PROMETHEUS_URL` ha default `http://localhost:9090` — non serve nel .env
  a meno che il server sia su un host diverso.

### 6.6 Rollback — due metodi
```
Patch fallita:
  ├── requires_reboot = True  →  snapshot (snapper undochange via UYUNI)
  └── requires_reboot = False →  package (apt-get install --allow-downgrades versioni reali)

Se snapper non disponibile (Ubuntu 24.04): fallback automatico a package rollback
in qualsiasi caso, anche per patch kernel.
```

### 6.7 Pacchetti fetchati on-demand
`packages` in `errata_cache` e' popolato solo quando l'errata viene accodata,
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

---

## 8. Da fare — Backlog

> Legenda: **[VM]** = azione sul VM, nessun codice | **[CODICE]** = modifica codebase

---

### [VM] ALTA — Installare Prometheus sul VM orchestrator

node_exporter e' gia' attivo sui test VM (deployato da UYUNI). Serve solo il server:

```bash
# 1. Installa Prometheus
apt-get install -y prometheus

# 2. Configura con HTTP SD (target dinamici da SPM)
cat > /etc/prometheus/prometheus.yml << 'EOF'
global:
  scrape_interval: 60s

scrape_configs:
  - job_name: 'spm-test-vms'
    http_sd_configs:
      - url: 'http://localhost:5001/api/v1/prometheus/targets'
        refresh_interval: 30m
EOF

# 3. Avvia
systemctl enable --now prometheus

# 4. Verifica
curl -s 'http://localhost:9090/api/v1/targets' | python3 -m json.tool | grep health
```

**PROMETHEUS_URL non va aggiunto al .env** — il default `http://localhost:9090` e' gia'
in `config.py`. Aggiungilo solo se il server e' su un host diverso.

---

### [VM] MEDIA — Installare snapper su Ubuntu test VM (10.172.2.18)

Senza snapper il rollback usa `apt downgrade` (meno affidabile per patch kernel).

```bash
# Sul test VM Ubuntu
apt-get install -y snapper
```

Il codice rileva automaticamente snapper mancante e fa fallback a package rollback.
Dopo l'installazione di snapper il rollback snapshot funzionera' senza modifiche al codice.

---

### [VM] MEDIA — Verificare canali UYUNI per node_exporter

L'engine installa automaticamente node_exporter via `system.schedulePackageInstall`,
ma il pacchetto deve essere nei canali UYUNI gia' sincronizzati per il sistema test.

| OS | Pacchetto nel canale UYUNI |
|---|---|
| Ubuntu 24.04 | `prometheus-node-exporter` (universe/main) |
| RHEL 9 | `node_exporter` (EPEL o canale custom) |

Verifica: aprire UYUNI → Software → Channel → cercare il pacchetto nel canale del sistema test.

---

### [VM] MEDIA — Configurare email notifiche

La struttura email e' gia' implementata in `notification_manager.py`. Attivare
dall'interfaccia DB o via `psql`:

```sql
INSERT INTO orchestrator_config (key, value, description)
VALUES (
  'notification_config',
  '{
    "email_enabled": true,
    "smtp_server":   "smtp.asl06.org",
    "smtp_port":     587,
    "smtp_tls":      true,
    "smtp_user":     "spm@asl06.org",
    "smtp_password": "...",
    "from_address":  "spm@asl06.org",
    "recipients":    ["ops@asl06.org"],
    "alert_on_test_failure":    true,
    "alert_on_pending_approval": true,
    "webhook_enabled": false,
    "webhook_url": ""
  }'::jsonb,
  'Configurazione notifiche email/webhook'
)
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
```

Con `email_enabled=true`: l'operatore riceve una email alla fine di ogni test
(fallito o in attesa di approvazione). Il banner in dashboard rimane come fallback
se l'email non viene consegnata.

---

### [CODICE] BASSA — NVD Enrichment severity

Problema: tutte le Security Advisory hanno `severity=Medium` (mapping da advisory_type).
Una CVE puo' essere Critical, High, Medium o Low in base al CVSS score reale.

Soluzione: aggiungere `services/nvd_client.py` che interroga NVD API v2 per ogni errata
con CVEs dopo il sync, aggiornando `errata_cache.severity` con il valore CVSS reale.

Note tecniche:
- NVD API v2: `https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-XXXX-YYYY`
- Rate limit senza API key: 5 req/30s — con key: 50 req/30s
- Solo Security Advisory hanno CVE → ca. 30-40% delle errata (batch fattibile in <60s)
- Hook in `poller.py`: chiamare `nvd_client.enrich_severity()` dopo `_batch_upsert()`

---

### [CODICE] BASSA — Batch persistenti su DB

Problema: `_batches` e' un dict in memoria in `test_engine.py`. Se `spm-orchestrator`
riavvia durante un batch, il batch continua su UYUNI ma il polling dalla dashboard
ritorna 404 (batch non trovato). L'operatore deve controllare i log.

Soluzione: aggiungere tabella `patch_test_batches` con `batch_id`, `status`, `results` (JSONB),
`operator`, `group_name`, `started_at`, `completed_at`. Scrivere il batch su DB invece
che solo in memoria. Compatibile con istanze multiple.

---

### [CODICE] BASSA — Paginazione storico approvazioni

`3_Approvazioni.py` carica `limit=100` hardcoded per il tab Storico. In ambienti con molti
cicli di patch lo storico diventa inutilizzabile. Aggiungere paginazione o filtro per data.

---

## 9. Note tecniche e decisioni rilevanti

### SSH socket activation (Ubuntu 24.04)
`ssh.service` e' inactive tra connessioni su Ubuntu 24.04 con socket activation.
Usare `ssh.socket` (non `ssh.service`) nella lista dei servizi critici. Gia' configurato
in `_DEFAULT_SERVICES["ubuntu"]`.

### Package rollback — limitazione
Il rollback package su Ubuntu puo' fallire se la versione precedente non e' piu' nel
repository apt (rimossa dopo una security patch). In questo caso l'operatore viene
notificato via `orchestrator_notifications` e deve intervenire manualmente.

### Azure AD — SAML vs OAuth2
- UYUNI web UI usa SAML 2.0 con Azure AD (Enterprise App separata)
- SPM Dashboard usa OAuth2/OIDC (App Registration "SPM Dashboard")
- Le due registrazioni Azure AD sono separate e indipendenti

### Timeout UYUNI (risolto)
`UYUNI_TIMEOUT` e' ora propagato tramite `_UyuniTransport` a tutti i ServerProxy XML-RPC.
Aggiunto in sessione 8 (2026-03-05). Prima xmlrpc.client usava il timeout di sistema.

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

### Variabili ambiente critiche

```bash
# /opt/spm-orchestrator/.env
UYUNI_URL=https://10.172.2.17
UYUNI_USER=admin
UYUNI_PASSWORD=...
UYUNI_VERIFY_SSL=false
UYUNI_POLL_INTERVAL_MINUTES=30
UYUNI_SYNC_WORKERS=10
DB_PASSWORD=...

# Azure AD SSO (obbligatori per dashboard)
AZURE_TENANT_ID=fae8df93-7cf5-40da-b480-f272e15b6242
AZURE_CLIENT_ID=<client-id>
AZURE_CLIENT_SECRET=<client-secret>
AZURE_REDIRECT_URI=https://10.172.2.22:8501

# PROMETHEUS_URL — NON necessario se Prometheus e' su localhost:9090 (default)
# Aggiungere solo se su host diverso:
# PROMETHEUS_URL=http://altro-host:9090
```

### Path VM

| Risorsa | Path |
|---|---|
| App Flask | `/opt/spm-orchestrator/app/` |
| .env | `/opt/spm-orchestrator/.env` |
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

-- Coda attuale
SELECT id, errata_id, status, success_score, target_os
  FROM patch_test_queue ORDER BY queued_at DESC LIMIT 20;

-- Notifiche non lette
SELECT id, notification_type, subject, delivered, sent_at
  FROM orchestrator_notifications WHERE delivered = FALSE ORDER BY sent_at DESC;

-- Pending approvals
SELECT queue_id, errata_id, success_score, hours_pending
  FROM v_pending_approvals ORDER BY priority_override DESC, hours_pending DESC;
```
