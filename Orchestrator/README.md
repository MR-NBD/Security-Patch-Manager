# SPM Orchestrator

Componente di orchestrazione per il processo supervisionato di patch management.
Gestisce il flusso automatico: **sync UYUNI → test su VM → approvazione operatore**.

## Architettura

```
VM-ORCHESTRATOR (Ubuntu 24.04 — 10.172.2.22)
├── Flask API        :5001   → REST API orchestrazione (loopback only)
├── Streamlit        :8501   → Dashboard operatore (HTTPS, Azure AD SSO)
├── PostgreSQL       :5432   → Database locale (spm_orchestrator)
└── APScheduler              → Poller UYUNI (30 min) + Test Engine (2 min)

Dipendenze esterne:
├── UYUNI Server    10.172.2.17:443   → XML-RPC (errata + scheduling patch)
├── Prometheus      localhost:9090    → Metriche validazione (opzionale)
└── node_exporter   :9100             → sui sistemi test

Sistemi test:
├── Ubuntu 24.04   10.172.2.18   system_id=1000010000   (gruppo: test-ubuntu-2404)
└── RHEL 9         10.172.2.19   system_id=1000010008   (gruppo: test-rhel9)
```

## Flusso operativo

```
1. Poller (ogni 30 min) → sync errata da UYUNI → errata_cache (PostgreSQL)
2. Operatore → seleziona patch dal gruppo UYUNI → aggiunge in coda
3. Test Engine (ogni 2 min) → preleva dalla coda → esegue test automatico:
      snapshot → patch → [reboot] → validate (Prometheus) → service check
      → fallimento: rollback automatico (snapper o apt downgrade)
      → successo: pending_approval
4. Dashboard → mostra alert + dettaglio CVE/fasi/risk
5. Operatore → approve / reject / snooze
6. Audit trail → note UYUNI sul sistema test + DB (patch_approvals)
```

## Struttura del progetto

```
Orchestrator/
├── app/
│   ├── main.py                      # Flask entry point + scheduler init
│   ├── config.py                    # Config da .env
│   ├── api/
│   │   ├── health.py                # /api/v1/health + /api/v1/notifications
│   │   ├── sync.py                  # /api/v1/sync
│   │   ├── queue.py                 # /api/v1/queue
│   │   ├── tests.py                 # /api/v1/tests
│   │   ├── approvals.py             # /api/v1/approvals
│   │   ├── groups.py                # /api/v1/orgs + /api/v1/groups
│   │   └── prometheus_sd.py         # /api/v1/prometheus/targets
│   ├── services/
│   │   ├── db.py                    # Pool connessioni PostgreSQL
│   │   ├── uyuni_client.py          # UyuniSession — sync errata
│   │   ├── uyuni_patch_client.py    # UyuniPatchClient — applicazione patch
│   │   ├── poller.py                # Sync UYUNI → errata_cache (APScheduler)
│   │   ├── queue_manager.py         # Gestione patch_test_queue
│   │   ├── test_engine.py           # Test automatici patch (fasi + rollback)
│   │   ├── approval_manager.py      # Workflow approve/reject/snooze
│   │   ├── notification_manager.py  # Alert interni → orchestrator_notifications
│   │   └── prometheus_client.py     # Metriche baseline/post-patch (graceful skip)
│   └── utils/
│       ├── logger.py                # JSON logging strutturato
│       └── serializers.py           # Serializzazione RealDictRow
├── streamlit/
│   ├── app.py                       # Azure AD SSO + st.navigation()
│   ├── api_client.py                # Wrapper REST (X-SPM-Key auth)
│   ├── auth_guard.py                # require_auth() per ogni pagina
│   ├── azure_auth.py                # MSAL helpers
│   └── pages/
│       ├── 0_Home.py                # Health + notifiche + sync + stats
│       ├── 1_Gruppi_UYUNI.py        # Gruppi test-* + patch applicabili
│       ├── 2_Test_Batch.py          # Batch test asincrono + polling live
│       └── 3_Approvazioni.py        # Workflow approvazioni + storico
├── sql/migrations/
│   ├── 001_orchestrator_schema.sql  # Schema PostgreSQL completo
│   ├── 002_fix_errata_cache.sql     # Fix errata_cache
│   └── 003_simplify_notifications.sql # Fix constraint notifiche
├── systemd/
│   └── spm-orchestrator.service
├── scripts/
│   └── install.sh
├── requirements.txt
├── .env.example
└── PROJECT-STATUS.md                # Stato dettagliato + backlog
```

## Setup rapido (VM)

```bash
# Prerequisiti: PostgreSQL, Python 3.11+, systemd
cd /opt
git clone https://github.com/MR-NBD/Security-Patch-Manager.git
cp Security-Patch-Manager/Orchestrator/.env.example spm-orchestrator/.env
nano spm-orchestrator/.env   # Configura UYUNI_URL, UYUNI_PASSWORD, DB_PASSWORD, SPM_API_KEY

# Installa
bash Security-Patch-Manager/Orchestrator/scripts/install.sh

# Applica migrazioni DB nell'ordine
psql -h localhost -U spm_orch -d spm_orchestrator \
    -f Security-Patch-Manager/Orchestrator/sql/migrations/001_orchestrator_schema.sql
psql -h localhost -U spm_orch -d spm_orchestrator \
    -f Security-Patch-Manager/Orchestrator/sql/migrations/002_fix_errata_cache.sql
psql -h localhost -U spm_orch -d spm_orchestrator \
    -f Security-Patch-Manager/Orchestrator/sql/migrations/003_simplify_notifications.sql

# Avvia
sudo systemctl enable --now spm-orchestrator spm-dashboard

# Verifica
curl http://localhost:5001/api/v1/health
curl http://localhost:5001/api/v1/health/detail | python3 -m json.tool
```

## Deploy aggiornamenti (REGOLA FISSA — sempre via git)

```bash
# Locale: commit + push
git add Orchestrator/
git commit -m "descrizione"
git push origin main

# Sul VM (via Azure Bastion)
cd /opt/Security-Patch-Manager && git pull origin main
cp -r Orchestrator/app /opt/spm-orchestrator/
sudo systemctl restart spm-orchestrator
sudo systemctl restart spm-dashboard
```

**MAI base64 copy-paste** — stringhe lunghe su terminale Bastion → errori silenziosi.

## Variabili d'ambiente

Due file `.env` separati:

### Flask API — `/opt/spm-orchestrator/.env`

```bash
# Flask
FLASK_HOST=127.0.0.1      # loopback only in produzione
FLASK_PORT=5001
SECRET_KEY=<random-hex-64>  # python3 -c "import secrets; print(secrets.token_hex(32))"

# Sicurezza API
SPM_API_KEY=<random-hex-32>  # stessa chiave in entrambi i .env

# UYUNI
UYUNI_URL=https://10.172.2.17
UYUNI_USER=admin
UYUNI_PASSWORD=...
UYUNI_VERIFY_SSL=false
UYUNI_POLL_INTERVAL_MINUTES=30
UYUNI_SYNC_WORKERS=10

# Sistemi test (opzionali — default vuoto → auto-discovery da UYUNI)
TEST_SYSTEM_UBUNTU_ID=
TEST_SYSTEM_RHEL_ID=

# Test Engine timing
TEST_WAIT_AFTER_PATCH_SECONDS=300
TEST_REBOOT_DELIVERY_WAIT_SECONDS=60
TEST_REBOOT_STABILIZATION_SECONDS=30

# Prometheus (default localhost:9090 — non impostare se Prometheus è locale)
# PROMETHEUS_URL=http://localhost:9090
```

### Streamlit Dashboard — `Orchestrator/streamlit/.env`

```bash
SPM_API_URL=http://localhost:5001
SPM_API_KEY=<stessa-chiave-Flask>

# Azure AD SSO
AZURE_TENANT_ID=fae8df93-7cf5-40da-b480-f272e15b6242
AZURE_CLIENT_ID=<client-id-app-registration>
AZURE_CLIENT_SECRET=<client-secret>
AZURE_REDIRECT_URI=https://10.172.2.22:8501
```

## API — endpoint principali

| Metodo | Endpoint | Descrizione |
|---|---|---|
| GET | `/api/v1/health` | Ping (load balancer / watchdog) |
| GET | `/api/v1/health/detail` | Stato DB + UYUNI + Prometheus |
| GET | `/api/v1/notifications` | Alert non letti (banner dashboard) |
| POST | `/api/v1/notifications/mark-read` | Marca come letti |
| POST | `/api/v1/sync/trigger` | Sync manuale errata_cache |
| GET | `/api/v1/queue` | Lista coda test |
| POST | `/api/v1/queue` | Aggiunge patch in coda |
| POST | `/api/v1/tests/run` | Esegui prossimo test (bloccante) |
| POST | `/api/v1/tests/batch` | Avvia batch asincrono |
| GET | `/api/v1/tests/batch/<id>/status` | Polling stato batch |
| GET | `/api/v1/approvals/pending` | Patch in attesa approvazione |
| POST | `/api/v1/approvals/<id>/approve` | Approva |
| POST | `/api/v1/approvals/<id>/reject` | Rifiuta |
| POST | `/api/v1/approvals/<id>/snooze` | Rimanda |
| GET | `/api/v1/orgs` | Organizzazioni UYUNI |
| GET | `/api/v1/groups` | Gruppi test-* con sistemi e patch count |
| GET | `/api/v1/prometheus/targets` | HTTP Service Discovery (Prometheus) |

Tutti gli endpoint (eccetto `/health*` e `/prometheus/targets`) richiedono header `X-SPM-Key`.

## Sicurezza

- **Binding**: Flask su `127.0.0.1` (loopback only) — non esposto direttamente in rete
- **API Key**: `SPM_API_KEY` condivisa tra Flask e Streamlit — validata su ogni richiesta
- **Azure AD SSO**: Dashboard autenticata via MSAL OAuth2/OIDC (App Registration separata da UYUNI SAML)
- **UYUNI XML-RPC**: account admin da `.env` — le credenziali operatore non transitano mai
- **Audit trail**: UPN Azure AD dell'operatore registrato in `patch_approvals` e nelle note UYUNI
- **TLS**: Streamlit serve HTTPS con cert self-signed (obbligatorio per redirect URI Azure AD su IP)

## Notifiche

Il sistema usa esclusivamente notifiche interne alla dashboard:
- Ogni evento (test fallito, patch da approvare) scrive in `orchestrator_notifications`
- `delivered=FALSE` → banner visibile nella Home della dashboard
- L'operatore marca le notifiche come lette dal banner
- L'audit completo del batch è scritto nelle **note UYUNI** del sistema test (`add_note`)

Non sono previsti canali email o webhook — il sistema è progettato per uso in rete isolata.

## Comandi utili sul VM

```bash
# Stato servizi
sudo systemctl status spm-orchestrator spm-dashboard
journalctl -u spm-orchestrator -f
sudo tail -f /var/log/spm-orchestrator/app.log

# DB
psql -h localhost -U spm_orch -d spm_orchestrator

# Ultimi test
SELECT id, errata_id, result, failure_phase, duration_seconds
  FROM patch_tests ORDER BY started_at DESC LIMIT 10;

# Coda
SELECT id, errata_id, status, success_score FROM patch_test_queue
  ORDER BY queued_at DESC LIMIT 20;

# Notifiche non lette
SELECT notification_type, subject, sent_at
  FROM orchestrator_notifications WHERE delivered = FALSE ORDER BY sent_at DESC;

# API manuale
curl -s http://localhost:5001/api/v1/health | python3 -m json.tool
curl -X POST http://localhost:5001/api/v1/sync/trigger | python3 -m json.tool
```

## Scalabilità

Il sistema è progettato per gestire centinaia di sistemi e migliaia di patch:

- **Sync UYUNI**: parallelizzato con `ThreadPoolExecutor` (configura `UYUNI_SYNC_WORKERS`)
- **DB**: `ThreadedConnectionPool` con keepalive per connessioni stabili
- **Test Engine**: un test alla volta per sistema (mutex), batch asincrono per gruppi
- **Auto-discovery**: sistemi test risolti dinamicamente da UYUNI (no config hardcoded)
- **Prometheus HTTP SD**: target dinamici — ogni sistema aggiunto a un gruppo `test-*` viene
  scoperto automaticamente entro 30 min

Per ambienti con molti sistemi, aumentare `UYUNI_SYNC_WORKERS` (default 10) e verificare
che il pool PostgreSQL (`maxconn=10` in `db.py`) sia adeguato al numero di thread concorrenti.
