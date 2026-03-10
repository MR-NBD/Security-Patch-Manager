# Errata-Parser v3.3

Microservizio Flask che sincronizza errata di sicurezza (Ubuntu USN, Debian DSA) verso UYUNI Server, con arricchimento severity tramite NVD/CVSS.

## Architettura

```
Internet (ubuntu.com, debian.org, nvd.nist.gov)
    │
    ▼
┌──────────────────────────────────────────┐
│  VM-ERRATA-PARSER (10.172.2.30)          │
│  /opt/errata-parser — porta 5000         │
│                                          │
│  ┌─────────────────────────────────┐     │
│  │  APScheduler (embedded)         │     │
│  │  USN    → 06:00, 12:00, 18:00  │     │
│  │  DSA    → 03:00                 │     │
│  │  NVD    → 04:00                 │     │
│  │  Pkg    → 01:00                 │     │
│  │  Push   → 00:30,06:30,12:30,.. │     │
│  └─────────────────────────────────┘     │
│                                          │
│  PostgreSQL locale (localhost:5432)      │
└──────────────────────────────────────────┘
    │
    ▼
[UYUNI Server 10.172.2.17:443]
```

**Nessuna Logic App Azure. Nessun container ACI. Nessun Azure PostgreSQL. Tutto sulla VM.**

## Changelog

### v3.3 (2026-03-10)
- **Sicurezza**: `_check_api_key()` ritorna `503` se `SPM_API_KEY` non impostata — non bypassa più silenziosamente l'autenticazione
- **Sicurezza**: audit log di ogni chiamata API (metodo, path, IP) e ogni tentativo di accesso fallito
- **Sicurezza**: `_sanitize_error()` ritorna sempre `"Internal error"` — nessun dettaglio interno esposto nelle risposte API
- **Fix `version_ge()`**: rimpiazzato con algoritmo dpkg completo (epoch + upstream version + debian revision, confronto carattere per carattere). Gestisce correttamente versioni Ubuntu come `8.9p1-3ubuntu0.10`, `7.81.0-1ubuntu1.15`, `1:2.3-4+deb12u1`
- **Fix fallback `version_ge()`**: era `True` (permissivo) → ora `False` (conservativo). Versioni non confrontabili vengono escluse invece di essere incluse silenziosamente
- **Fix cache pacchetti**: `_sync_packages()` non svuota più la cache se `listAllPackages` ritorna lista vuota (canale UYUNI temporaneamente irraggiungibile). Cache preservata
- **Resilienza**: `_get_active_distributions()` usa cache in-memory (TTL 1h) — se UYUNI è temporaneamente offline la sync continua con l'ultimo set di distribuzioni noto
- **Validazione CVE**: introdotto regex `CVE-YYYY-NNNNN` in USN e DSA sync — stringhe non valide (es. descrizioni testuali) non vengono inserite nella tabella `cves`
- **Scheduler monitoring**: `_job_status` traccia `status/last_run/result/error` per ogni job; `/api/scheduler/jobs` espone `failed_count` e dettaglio errori
- **Test**: aggiunta suite pytest con 52 test (version comparison, package matching, CVE regex, auth, health endpoint)
- **Deploy**: `migrate-db-local.sh` non ha più credenziali hardcoded — legge `DATABASE_URL` dal `.env` esistente, genera password locale con `openssl rand`
- **Deploy**: `install-vm.sh` aggiunge `chmod 750` sulla directory dei log

### v3.2 (2026-03-10)
- **Fix critico**: `_try_lock()` usava `cursor.fetchone()[0]` su `RealDictCursor` → `KeyError(0)` → il push verso UYUNI falliva sempre silenziosamente
- **Fix critico**: `version_ge()` supporta versioni con epoch Debian/Ubuntu — prima tutti i push DSA/USN con epoch erano silenziosamente skippati
- **Fix**: `_build_package_ids()` gestisce pacchetti con versioni diverse per release multipli (jammy + noble sullo stesso USN)
- **Fix**: `errata.publish()` chiamato dopo `errata.create()` — errata visibili in UYUNI (alcune versioni creano in draft)
- **Fix**: `_TimeoutTransport` sostituisce `socket.setdefaulttimeout()` globale (thread-safe)
- **Fix**: whitelist release Ubuntu estesa — aggiunto `bionic`, `oracular`, `plucky`

## Infrastruttura

| Componente | Valore |
|---|---|
| VM | `10.172.2.30` |
| Servizio | `errata-parser` (systemd) |
| Porta | `5000` (loopback only) |
| Repo sul VM | `/opt/repo` |
| Install dir | `/opt/errata-parser` |
| Log applicativo | `/opt/errata-parser/logs/errata-parser.log` |
| Log gunicorn | `/opt/errata-parser/logs/error.log` |
| DB | PostgreSQL locale `localhost:5432/uyuni_errata` |
| UYUNI | `10.172.2.17:443` |

## Deploy

### Prerequisiti

- VM Ubuntu 22.04/24.04 con accesso a internet e alla VNet
- Python 3.9+
- Accesso SSH come root

### Installazione (prima volta)

```bash
# 1. Clona il repo sulla VM
git clone https://github.com/MR-NBD/Security-Patch-Manager.git /opt/repo
cd /opt/repo

# 2. Esegui lo script di installazione
bash Errata-Parser/scripts/install-vm.sh

# 3. Configura le credenziali
nano /opt/errata-parser/.env

# 4. Avvia
systemctl start errata-parser

# 5. Verifica
curl -s http://localhost:5000/api/health | python3 -m json.tool
```

### Update (versioni successive)

```bash
cd /opt/repo && git pull
cp Errata-Parser/app.py /opt/errata-parser/app.py
systemctl restart errata-parser
curl -s http://localhost:5000/api/health | python3 -m json.tool
```

### Migrazione DB a PostgreSQL locale

Se il servizio punta ancora a un DB remoto, migra in locale:

```bash
# Richiede postgresql e postgresql-client installati
apt-get install -y postgresql postgresql-client
bash /opt/repo/Errata-Parser/scripts/migrate-db-local.sh
```

Lo script legge `DATABASE_URL` dal `.env` esistente, esegue dump + restore, aggiorna il `.env` con `localhost` e genera una password locale sicura.

### Esecuzione test

```bash
cd /opt/repo/Errata-Parser
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Variabili d'Ambiente

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `DATABASE_URL` | **SI** | — | PostgreSQL connection string |
| `UYUNI_URL` | **SI** | — | `https://10.172.2.17` |
| `UYUNI_USER` | **SI** | — | Utente admin UYUNI locale (es. `admin`) |
| `UYUNI_PASSWORD` | **SI** | — | Password locale dell'utente UYUNI — **non la password Azure AD** |
| `SPM_API_KEY` | **SI** | — | Header `X-API-Key` — obbligatoria, senza di essa tutti gli endpoint autenticati ritornano `503` |
| `UYUNI_TIMEOUT` | No | `30` | Timeout in secondi per le chiamate XML-RPC |
| `NVD_API_KEY` | Raccomandato | — | Rate limit NVD API (senza: 1 req/6s, con: 1 req/0.6s) |
| `SCHEDULER_ENABLED` | No | `false` | `true` attiva APScheduler |
| `LOG_FILE` | No | `/opt/errata-parser/logs/errata-parser.log` | Path log |

> **Nota `UYUNI_PASSWORD`**: UYUNI usa SAML 2.0 (Azure AD) per il login via browser, ma le
> API XML-RPC usano **sempre credenziali locali**, indipendentemente dal SAML.
> Con `java.sso = true` attivo, l'account `admin` non è accessibile via browser ma
> **continua a funzionare per le API XML-RPC**.

## API Endpoints

Auth: header `X-API-Key` richiesto su tutti tranne `/api/health` e `/api/health/detailed`.
Se `SPM_API_KEY` non è impostata nel `.env`, tutti gli endpoint autenticati ritornano `503`.

| Endpoint | Metodo | Auth | Descrizione |
|---|---|---|---|
| `/api/health` | GET | No | Stato API, DB, UYUNI, versione |
| `/api/health/detailed` | GET | No | Metriche complete, alert staleness |
| `/api/scheduler/jobs` | GET | **SI** | Stato job: next_run, last_run, status, error |
| `/api/sync/usn` | POST | **SI** | Sync Ubuntu USN (manuale) |
| `/api/sync/dsa` | POST | **SI** | Sync Debian DSA (manuale, ~15-30 min) |
| `/api/sync/nvd` | POST | **SI** | Enrichment NVD/CVSS |
| `/api/sync/auto` | POST | **SI** | Pipeline completa (USN+DSA+NVD+Pkg+Push) |
| `/api/sync/status` | GET | **SI** | Log ultimi 20 sync |
| `/api/uyuni/sync-packages` | POST | **SI** | Aggiorna cache pacchetti UYUNI |
| `/api/uyuni/push` | POST | **SI** | Push errata pendenti verso UYUNI |
| `/api/uyuni/channels` | GET | **SI** | Canali UYUNI attivi con distribuzione mappata |

### Parametri query string

| Endpoint | Parametro | Default | Max |
|---|---|---|---|
| `/api/sync/nvd` | `batch_size` | 50 | 500 |
| `/api/sync/nvd` | `force` | `false` | — |
| `/api/uyuni/push` | `limit` | 10 | 200 |
| `/api/sync/auto` | `nvd_batch` | 100 | 500 |
| `/api/sync/auto` | `push_limit` | 50 | 200 |

## Operazioni manuali

```bash
export KEY="$(grep SPM_API_KEY /opt/errata-parser/.env | cut -d= -f2)"
export API="http://localhost:5000"

# Health check (no auth)
curl -s $API/api/health | python3 -m json.tool

# Stato scheduler con dettaglio last_run e errori
curl -s -H "X-API-Key: $KEY" $API/api/scheduler/jobs | python3 -m json.tool

# Canali UYUNI attivi
curl -s -H "X-API-Key: $KEY" $API/api/uyuni/channels | python3 -m json.tool

# Sync manuale USN
curl -s -X POST -H "X-API-Key: $KEY" $API/api/sync/usn | python3 -m json.tool

# Sync manuale DSA (può richiedere 15-30 min)
curl -s --max-time 1800 -X POST -H "X-API-Key: $KEY" $API/api/sync/dsa | python3 -m json.tool

# Aggiorna cache pacchetti UYUNI
curl -s -X POST -H "X-API-Key: $KEY" $API/api/uyuni/sync-packages | python3 -m json.tool

# Push errata (limit=50 per batch)
curl -s -X POST -H "X-API-Key: $KEY" "$API/api/uyuni/push?limit=50" | python3 -m json.tool

# Pipeline completa
curl -s --max-time 3600 -X POST -H "X-API-Key: $KEY" $API/api/sync/auto | python3 -m json.tool

# Log sync recenti
curl -s -H "X-API-Key: $KEY" $API/api/sync/status | python3 -m json.tool
```

## Gestione servizio

```bash
systemctl status errata-parser
systemctl restart errata-parser
journalctl -u errata-parser -f              # log live
journalctl -u errata-parser -n 50          # ultimi 50 righe
tail -f /opt/errata-parser/logs/errata-parser.log   # log applicativo
tail -f /opt/errata-parser/logs/error.log           # log gunicorn
```

## Note architettura UYUNI

UYUNI gira come container Podman su openSUSE (`10.172.2.17`).
La web UI usa **SAML 2.0 con Azure AD** — questo riguarda solo il browser,
**non tocca le API XML-RPC** che continuano ad usare credenziali locali (`admin`/password).
Le chiamate di errata-parser verso `/rpc/api` sono indipendenti dal SAML.

## Troubleshooting

### `uyuni: "error: Internal error"` nel health check

Diagnosi rapida — testa la connessione UYUNI con le credenziali dal `.env`:

```bash
python3 - <<'EOF'
env = {}
with open('/opt/errata-parser/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip().strip('"').strip("'")

import ssl, xmlrpc.client

class T(xmlrpc.client.SafeTransport):
    def __init__(self, timeout, context=None):
        super().__init__(context=context)
        self._timeout = timeout
    def make_connection(self, host):
        conn = super().make_connection(host)
        if hasattr(conn, 'timeout'):
            conn.timeout = self._timeout
        return conn

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

client = xmlrpc.client.ServerProxy(
    f"{env['UYUNI_URL']}/rpc/api",
    transport=T(30, ctx)
)
try:
    print(f"API version: {client.api.getVersion()}")
    s = client.auth.login(env['UYUNI_USER'], env['UYUNI_PASSWORD'])
    print("Login OK")
    client.auth.logout(s)
except Exception as e:
    print(f"ERRORE: {type(e).__name__}: {e}")
EOF
```

Causa più comune: `UYUNI_PASSWORD` nel `.env` non aggiornata dopo cambio password.
Aggiorna il `.env` e riavvia: `systemctl restart errata-parser`

### TLS handshake timeout verso UYUNI

Il sintomo è: TCP si connette a `10.172.2.17:443` ma la risposta non arriva mai.
La causa è tipicamente il web server interno di UYUNI hung.

```bash
# Step 1 — verifica TCP
nc -zv 10.172.2.17 443

# Step 2 — verifica TLS (deve completare in <5s)
timeout 15 openssl s_client -connect 10.172.2.17:443 2>&1 | head -5

# Se timeout → UYUNI è hung, riavviare dal server UYUNI (10.172.2.17):
mgradm restart
# attendere 90 secondi prima di riprovare
```

> **Nota**: usare `mgradm restart`, non `systemctl restart tomcat`.
> Solo `mgradm restart` ricarica correttamente tutta la stack containerizzata.
> Verificare i log del container: `podman logs uyuni-server --tail 50`

### Worker errata-parser bloccato (WORKER TIMEOUT in error.log)

Si verifica quando UYUNI è hung durante una sync. Dopo aver riavviato UYUNI con `mgradm restart`:

```bash
systemctl restart errata-parser
```

### Job scheduler in errore

Controllare lo stato dei job con dettaglio errore:

```bash
export KEY="$(grep SPM_API_KEY /opt/errata-parser/.env | cut -d= -f2)"
curl -s -H "X-API-Key: $KEY" http://localhost:5000/api/scheduler/jobs | python3 -m json.tool
```

Il campo `status` per ogni job può essere `never_run`, `running`, `ok`, `error`.
In caso di `error`, il campo `error` contiene il messaggio. `failed_count` indica quanti job sono in errore.

### Push ritorna `pending_processed: 0`

**A) Tutte le errata per i canali attivi sono già state pushate** (normale).
Verificare con health/detailed:
```bash
curl -s http://localhost:5000/api/health/detailed | python3 -m json.tool
```
Se `errata_pending > 0` ma la distribuzione non corrisponde ai canali UYUNI (es. errata Debian ma nessun canale Debian attivo in UYUNI), il comportamento è corretto.

**B) Nessuna errata nel DB** → eseguire la prima sync:
```bash
export KEY="$(grep SPM_API_KEY /opt/errata-parser/.env | cut -d= -f2)"
curl -s --max-time 300 -X POST -H "X-API-Key: $KEY" http://localhost:5000/api/sync/usn | python3 -m json.tool
```

### Push errata skippati (version mismatch)

Se `/api/uyuni/push` ritorna `skipped_version_mismatch > 0`, la versione corretta
del pacchetto non è ancora nella cache UYUNI. Aggiornare prima la cache:

```bash
export KEY="$(grep SPM_API_KEY /opt/errata-parser/.env | cut -d= -f2)"
curl -s -X POST -H "X-API-Key: $KEY" http://localhost:5000/api/uyuni/sync-packages | python3 -m json.tool
curl -s -X POST -H "X-API-Key: $KEY" "http://localhost:5000/api/uyuni/push?limit=50" | python3 -m json.tool
```
