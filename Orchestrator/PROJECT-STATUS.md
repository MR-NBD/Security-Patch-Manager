# SPM-Orchestrator — Project Status & Development Notes

> Documento vivente. Aggiornare ad ogni sessione di sviluppo.
> Ultima modifica: 2026-02-26 (sessione 3)

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
9. [Note future](#9-note-future)
10. [Deploy](#10-deploy)

---

## 1. Architettura attuale

```
VM-ORCHESTRATOR (Ubuntu 24.04 — 10.172.2.22)
├── Flask API       :5001   → Orchestrazione REST
├── PostgreSQL      :5432   → DB locale (spm_orchestrator)
└── APScheduler             → Poller UYUNI (ogni 30 min)

Dipendenze esterne:
├── UYUNI Server    10.172.2.17:443   → XML-RPC (fonte errata + scheduling)
├── Salt API        10.172.2.17:9080  → Esecuzione comandi minion  [TODO]
└── Prometheus      localhost:9090    → Metriche validazione        [TODO]
```

**Gruppi UYUNI monitorati:** prefisso `test-` (es. `test-ubuntu-2404`, `test-rhel9`)
**OS supportati:** Ubuntu 24.04, RHEL 9
**Accesso VM:** Azure Bastion (no SCP/rsync diretto)

---

## 2. Stack tecnologico

| Componente | Tecnologia |
|---|---|
| API | Python 3.x, Flask 3.x |
| Scheduler | APScheduler 3.x (BackgroundScheduler) |
| Database | PostgreSQL 16 (psycopg2, RealDictCursor, ThreadedConnectionPool) |
| UYUNI Client | xmlrpc.client (XML-RPC) |
| Parallelismo | concurrent.futures.ThreadPoolExecutor |
| Bulk DB | psycopg2.extras.execute_values |
| Logging | python-json-logger (JSON strutturato → journald) |
| Servizio | systemd (spm-orchestrator.service) |

---

## 3. Stato implementazione

### COMPLETATO ✓

#### Infrastruttura
- [x] Schema PostgreSQL — 10 tabelle + views + triggers + functions
- [x] Flask app con 3 blueprint (health, sync, queue)
- [x] Systemd service (`spm-orchestrator.service`)
- [x] Logging JSON strutturato (stdout + file opzionale)
- [x] Config centralizzata da `.env`
- [x] ThreadedConnectionPool PostgreSQL (1-10 connessioni)

#### UYUNI Integration
- [x] `UyuniSession` — sessione thread-safe (1 login/logout per ciclo, non per call)
- [x] Fetch gruppi `test-*`, sistemi, errata applicabili, CVEs, pacchetti
- [x] Poller APScheduler → `errata_cache` (sync ogni 30 min + sync iniziale)
- [x] `_parse_uyuni_date` — gestisce `xmlrpc.client.DateTime`, datetime, ISO string
- [x] Severity mapping: Security Advisory → Medium, Bug Fix/Enhancement → Low
- [x] `os_from_group()` — mappa gruppo UYUNI → target_os (ubuntu/rhel/debian)

#### Performance sync (ottimizzato 2026-02-23)
- [x] ThreadPoolExecutor per fetch parallelo sistemi + errata + CVEs
- [x] `execute_values` batch upsert (1 transazione vs 634 individuali)
- [x] CVEs fetchati solo per Security Advisory (non Bug Fix/Enhancement)
- [x] Eliminata chiamata `get_errata_details()` (non necessaria)

#### Queue Manager
- [x] `add_to_queue` — fetch pacchetti on-demand, calcolo Success Score, insert coda
- [x] `get_queue` — lista con filtri (status, target_os, severity, limit, offset)
- [x] `get_queue_item` — dettaglio con errata + risk profile + test results
- [x] `update_queue_item` — aggiorna priority_override / notes
- [x] `remove_from_queue` — rimozione solo se status='queued'
- [x] `get_queue_stats` — aggregati coda (total, by_status, by_os, avg_score)

#### Success Score (0–100)
- [x] Penalità kernel: -30
- [x] Penalità reboot: -15
- [x] Penalità config: -10
- [x] Penalità dipendenze: -3/dep (max -15)
- [x] Penalità dimensione: -2/MB (max -10)
- [x] Penalità storico fallimenti: fino a -20 (se tested ≥ 3)
- [x] Bonus patch piccola (<100 KB): +5
- [x] Pesi configurabili da `orchestrator_config` (DB) o `.env`

#### API Endpoints implementati
- [x] `GET  /api/v1/health`
- [x] `GET  /api/v1/health/detail`
- [x] `GET  /api/v1/sync/status`
- [x] `POST /api/v1/sync/trigger`
- [x] `GET  /api/v1/errata/cache/stats`
- [x] `GET  /api/v1/queue`
- [x] `POST /api/v1/queue`
- [x] `GET  /api/v1/queue/stats`
- [x] `GET  /api/v1/queue/<id>`
- [x] `PATCH /api/v1/queue/<id>`
- [x] `DELETE /api/v1/queue/<id>`

---

### DA IMPLEMENTARE ✗

Vedi [Sezione 8 — Backlog](#8-da-fare--backlog) per dettagli e priorità.

| Componente | Priorità |
|---|---|
| Salt API Client | ~~Alta~~ **FATTO** ✓ |
| Prometheus Client | ~~Alta~~ **FATTO** ✓ |
| Test Engine | ~~Alta (core)~~ **FATTO** ✓ |
| Approval Workflow + API | ~~Media~~ **FATTO** ✓ |
| Production Deployment | ~~Media~~ **FATTO** ✓ |
| NVD Enrichment severity | Bassa (nota futura) |
| Notifiche email | Bassa |
| Streamlit Dashboard | **Media** (prossimo passo) |

---

## 4. API Endpoints

### Health

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/health` | Ping rapido (usato da watchdog) |
| GET | `/api/v1/health/detail` | Health check con DB/UYUNI/Prometheus |

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

### Approvazioni [TODO]

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/approvals/pending` | Patch in attesa approvazione |
| POST | `/api/v1/approvals/<id>/approve` | Approva |
| POST | `/api/v1/approvals/<id>/reject` | Rifiuta |
| POST | `/api/v1/approvals/<id>/snooze` | Rinvia |

### Test Engine [TODO]

| Metodo | Path | Descrizione |
|---|---|---|
| POST | `/api/v1/tests/start` | Avvia test su prossimo elemento coda |
| GET | `/api/v1/tests/<id>` | Stato test in corso |
| GET | `/api/v1/tests/<id>/phases` | Dettaglio fasi test |
| POST | `/api/v1/tests/<id>/rollback` | Forza rollback manuale |

### Deployments [TODO]

| Metodo | Path | Descrizione |
|---|---|---|
| POST | `/api/v1/deployments` | Avvia deployment produzione |
| GET | `/api/v1/deployments/<id>` | Stato deployment |
| POST | `/api/v1/deployments/<id>/rollback` | Rollback deployment |

---

## 5. Database Schema

### Tabelle (10)

| Tabella | Ruolo |
|---|---|
| `errata_cache` | Cache locale errata da UYUNI (sync ogni 30 min) |
| `patch_risk_profile` | Success Score + analisi pacchetti per errata |
| `patch_test_queue` | Coda test patch con stato workflow completo |
| `patch_tests` | Dettaglio singolo test (metriche, snapshot, reboot) |
| `patch_test_phases` | Fasi di ogni test (snapshot/patch/reboot/validate/rollback) |
| `patch_approvals` | Log approvazioni/rifiuti operatore |
| `patch_deployments` | Deployment produzione (multi-sistema) |
| `patch_rollbacks` | Log rollback deployment |
| `orchestrator_notifications` | Notifiche email/webhook inviate |
| `orchestrator_config` | Configurazione runtime (score weights, thresholds, ecc.) |

### Views

| View | Contenuto |
|---|---|
| `v_queue_details` | Coda con join errata + risk profile |
| `v_pending_approvals` | Patch passed in attesa approvazione (con hours_pending) |
| `v_daily_stats` | Statistiche giornaliere ultimi 30 giorni |

### Stati patch_test_queue

```
queued → testing → passed → pending_approval → approved → promoting → prod_applied → completed
                 ↓                           ↓
               failed                      rejected
                 ↓
           (rollback) → rolled_back
```

---

## 6. Decisioni architetturali

### 6.1 UYUNI come source of truth (non SPM-SYNC)
**Decisione:** Il poller interroga UYUNI direttamente via XML-RPC, non SPM-SYNC.
**Motivo:** UYUNI conosce già quali patch sono *applicabili* a ciascun sistema (non ancora installate). Evita di scaricare l'intero catalogo NVD (decine di migliaia di errata irrilevanti).
**Risultato:** Solo 634 errata rilevanti invece di ~50.000.

### 6.2 Session singola UyuniSession (1 login/logout per ciclo)
**Decisione:** `UyuniSession` fa login una sola volta e condivide la chiave tra thread.
**Motivo:** Ogni login/logout XML-RPC costa ~300ms. Con 634 errata in sequenza = ~200s overhead.
**Risultato:** Da ~200s di auth overhead a ~1s.

### 6.3 CVEs fetchati solo per Security Advisory
**Decisione:** `get_errata_cves()` chiamato solo se `advisory_type == "Security Advisory"`.
**Motivo:** Bug Fix e Enhancement Advisory non hanno CVE associati. Risparmio ~60% delle chiamate CVE.

### 6.4 description non sovrascritta in batch upsert
**Decisione:** La colonna `description` è esclusa dall'`ON CONFLICT DO UPDATE`.
**Motivo:** `get_errata_details()` è stata eliminata dal sync per performance. Se la description è stata fetchata in precedenza (on-demand), non va persa al sync successivo.

### 6.5 Pacchetti fetchati on-demand (non durante sync)
**Decisione:** `packages` in `errata_cache` popolato solo quando l'errata viene accodata (`add_to_queue`), non durante il sync.
**Motivo:** Chiamata `get_errata_packages()` ×634 = ~100s aggiuntivi. Il dato è necessario solo per calcolare il Success Score al momento dell'accodamento.

### 6.6 Rollback — due metodi previsti
**Metodo 1 — `snapshot` (system-level):**
- Pre-patch: crea snapshot sistema di test via snapper/UYUNI
- Post-fallimento: ripristino completo snapshot
- Atomico, ma richiede reboot. Usato quando `requires_reboot = True`

**Metodo 2 — `package` (package-level):**
- Post-fallimento: downgrade pacchetto alla versione precedente
- Ubuntu: `apt-get install package=old_version`
- RHEL: `dnf history undo` / `rpm --rollback`
- Più veloce, no reboot. Usato quando `requires_reboot = False`

**Logica di selezione:**
```
Patch fallita:
  ├─ requires_reboot = False  →  rollback package (veloce)
  └─ requires_reboot = True   →  rollback snapshot (sicuro)
```

Il campo `rollback_type` in `patch_tests` e `patch_rollbacks` registra il metodo usato.

---

## 7. Performance e ottimizzazioni

### Sync UYUNI — benchmark (634 errata, 2 gruppi, 2 sistemi)

| Fase | Prima (sequenziale) | Dopo (ottimizzato) |
|---|---|---|
| Auth overhead (N×login) | ~200s | ~1s (1 coppia) |
| `get_errata_details` ×634 | ~100s | 0s (eliminato) |
| `get_relevant_errata` | ~10s | ~2s (parallelo) |
| `get_errata_cves` (solo Security) | ~30s | ~8s (parallelo) |
| DB upsert | ~5s | ~1s (batch) |
| **Totale** | **~340s (5:39 min)** | **~8s** |

**Configurazione parallelismo:** `UYUNI_SYNC_WORKERS=10` (worker errata), `workers×2` per CVE.

---

## 8. Da fare — Backlog

### Priorità Alta — Salt API Client (`services/salt_client.py`)
Prerequisito per il Test Engine. Deve supportare:
- `apply_patch(system_id, advisory_name)` → chiama Salt via UYUNI XML-RPC
- `get_service_status(system_id, services[])` → verifica servizi critici
- `reboot_system(system_id)` → riavvio controllato
- Autenticazione Salt API (token-based, via `/rpc/api` UYUNI o Salt API diretto `:9080`)

### Priorità Alta — Prometheus Client (`services/prometheus_client.py`)
Prerequisito per la validazione post-patch. Deve supportare:
- `get_cpu_usage(system_ip)` → valore % CPU
- `get_memory_usage(system_ip)` → valore % memoria
- `get_metrics_snapshot(system_ip)` → baseline pre-patch e post-patch
- Calcolo delta e valutazione vs threshold (`TEST_CPU_DELTA_THRESHOLD`, `TEST_MEMORY_DELTA_THRESHOLD`)

### Priorità Alta — Test Engine (`services/test_engine.py`)
Core del sistema. Flusso:
```
1. Preleva prossimo elemento coda (status='queued', ordered by priority)
2. Crea snapshot sistema test (snapper/UYUNI)      → patch_test_phases
3. Applica patch via Salt API                       → patch_test_phases
4. Reboot (se requires_reboot=True)                 → patch_test_phases
5. Valida metriche Prometheus (CPU/memoria delta)   → patch_test_phases
6. Verifica servizi critici (systemd)               → patch_test_phases
7a. Successo → status='passed', aggiorna patch_tests
7b. Fallimento → rollback (snapshot o package) → status='failed'
8. Aggiorna patch_test_queue.status
```

### Priorità Media — Approval Workflow
- Endpoint `POST /api/v1/approvals/<id>/approve|reject|snooze`
- Scrittura in `patch_approvals`
- Transizione `passed → pending_approval → approved/rejected`
- API `GET /api/v1/approvals/pending`

### Priorità Media — Production Deployment
- Endpoint `POST /api/v1/deployments`
- Applicazione patch su sistemi produzione via UYUNI/Salt
- Tracking `patch_deployments` (multi-sistema, partial failure)
- Rollback deployment `POST /api/v1/deployments/<id>/rollback`

### Priorità Bassa — Notifiche email
- Invio notifiche per: sync completato, patch failed, pending approval, deployment done
- Scrittura in `orchestrator_notifications`
- SMTP configurabile da `.env`

### Priorità Bassa — Streamlit Dashboard
- Visualizzazione coda patch (con filtri)
- Statistiche sync e Success Score
- Pannello approvazioni operatore
- Vista deployment produzione

---

## 9. Note future

### NVD Enrichment (severity reale)
**Stato:** Non implementato. Documentato per future iterazioni.

**Problema attuale:** La severity in `errata_cache` è mappata dall'`advisory_type` UYUNI:
- `Security Advisory` → `"Medium"` (default conservativo)
- `Bug Fix Advisory` → `"Low"`
- `Product Enhancement Advisory` → `"Low"`

Questa mappatura è imprecisa: una patch di sicurezza può essere Critical, High, Medium o Low a seconda del CVSS score.

**Soluzione futura:**
1. Dopo il sync UYUNI, per ogni errata con CVEs, interrogare NVD API v2:
   `https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-XXXX-YYYY`
2. Estrarre `cvssMetricV31[0].cvssData.baseScore`
3. Mappare CVSS → severity:
   - 9.0–10.0 → `Critical`
   - 7.0–8.9 → `High`
   - 4.0–6.9 → `Medium`
   - 0.1–3.9 → `Low`
4. Aggiornare `errata_cache.severity` con il valore reale
5. NVD ha rate limit: 5 req/30s senza API key, 50 req/30s con API key

**Impatto:** Migliora drasticamente la prioritizzazione della coda e il Success Score.

**Dove:** `services/nvd_client.py` + chiamata post-sync in `poller.py`.

---

### Rollback — due metodi (documentazione decisione)
Vedi [Sezione 6.6](#66-rollback--due-metodi-previsti) per dettagli completi.

---

### Timeout UYUNI (`UYUNI_TIMEOUT_SECONDS`)
**Stato:** Configurato in `Config` ma non ancora utilizzato nel `UyuniSession`.
**Da fare:** Passare timeout al `SafeTransport` di `xmlrpc.client`.

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
cp -r /opt/Security-Patch-Manager/Orchestrator/app /opt/spm-orchestrator/
sudo systemctl restart spm-orchestrator

# Verifica
sudo systemctl status spm-orchestrator --no-pager
journalctl -u spm-orchestrator -n 30 --no-pager
```

### Verifica sync

```bash
curl http://localhost:5001/api/v1/sync/status | python3 -m json.tool
curl -X POST http://localhost:5001/api/v1/sync/trigger | python3 -m json.tool
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
```

### Path VM

| Risorsa | Path |
|---|---|
| App | `/opt/spm-orchestrator/app/` |
| .env | `/opt/spm-orchestrator/.env` |
| Repo | `/opt/Security-Patch-Manager/` |
| Log | `journalctl -u spm-orchestrator` |
| DB | `psql -h localhost -U spm_orch -d spm_orchestrator` |
