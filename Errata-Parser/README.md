# Errata-Parser v3.2

Microservizio Flask che sincronizza errata di sicurezza (Ubuntu USN, Debian DSA) verso UYUNI Server, con arricchimento severity tramite NVD/CVSS.

## Architettura

```
Internet (ubuntu.com, debian.org, nvd.nist.gov)
    │
    ▼
┌──────────────────────────────────────────┐
│  Errata-Parser VM (Ubuntu dedicata)      │
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
└──────────────────────────────────────────┘
    │                        │
    ▼                        ▼
[PostgreSQL]           [UYUNI :443]
Fase 1: Azure DB       10.172.2.17
Fase 2: locale
```

**Nessuna Logic App Azure. Nessun container ACI. Tutto sulla VM.**

## Changelog

### v3.2 (2026-03-10)
- **Fix critico**: `version_ge()` supporta versioni Debian/Ubuntu con epoch (`1:2.3.0-1`, `2:8.9p1-3ubuntu0.10`) — prima tutti i push DSA/USN erano silenziosamente skippati
- **Fix**: `_build_package_ids()` gestisce pacchetti con versioni diverse per release multipli (es. jammy + noble sullo stesso USN)
- **Fix**: `errata.publish()` chiamato dopo `errata.create()` — errata ora visibili in UYUNI (alcune versioni creano in draft)
- **Fix**: `_TimeoutTransport` sostituisce `socket.setdefaulttimeout()` globale con timeout per-connessione (thread-safe)
- **Fix**: whitelist release Ubuntu estesa — aggiunto `bionic` (18.04 LTS/ESM), `oracular` (24.10), `plucky` (25.04)

## Deploy

### Prerequisiti

- VM Ubuntu 22.04/24.04 con accesso a internet e alla VNet
- Python 3.9+
- Accesso SSH come root

### Installazione

```bash
# 1. Clona il repo sulla VM
git clone https://github.com/TUO-ORG/Security-Patch-Manager.git /opt/repo
cd /opt/repo

# 2. Esegui lo script di installazione
sudo bash Errata-Parser/scripts/install-vm.sh

# 3. Verifica/aggiorna credenziali
sudo nano /opt/errata-parser/.env

# 4. Avvia
sudo systemctl start errata-parser

# 5. Verifica
curl -s http://localhost:5000/api/health | python3 -m json.tool
curl -s http://localhost:5000/api/scheduler/jobs | python3 -m json.tool
```

### Update

```bash
git pull
sudo bash Errata-Parser/scripts/update-vm.sh
```

### Migrazione DB a PostgreSQL locale (Fase 2 — opzionale)

Elimina la dipendenza da Azure PostgreSQL (~15-30€/mese):

```bash
sudo bash Errata-Parser/scripts/migrate-db-local.sh
```

## Variabili d'Ambiente

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `DATABASE_URL` | **SI** | — | PostgreSQL connection string |
| `UYUNI_URL` | **SI** | — | `https://10.172.2.17` |
| `UYUNI_USER` | **SI** | — | Utente admin UYUNI locale (es. `admin`) |
| `UYUNI_PASSWORD` | **SI** | — | Password locale dell'utente UYUNI — **non la password Azure AD** (vedi nota sotto) |
| `UYUNI_TIMEOUT` | No | `30` | Timeout in secondi per le chiamate XML-RPC |
| `SPM_API_KEY` | Raccomandato | — | Header `X-API-Key` |
| `NVD_API_KEY` | Raccomandato | — | Rate limit NVD API |
| `SCHEDULER_ENABLED` | No | `false` | `true` attiva APScheduler |
| `LOG_FILE` | No | `/var/log/errata-manager.log` | Path log |

> **Nota `UYUNI_PASSWORD`**: UYUNI usa SAML 2.0 (Azure AD) per il login via browser, ma le
> API XML-RPC usano **sempre credenziali locali**, indipendentemente dal SAML.
> `UYUNI_PASSWORD` deve essere la password dell'account locale UYUNI (impostata al momento
> della creazione dell'utente in UYUNI, non collegata ad Azure AD).
> Con `java.sso = true` attivo, l'account `admin` non è accessibile via browser ma
> **continua a funzionare per le API XML-RPC**.

## API Endpoints

Auth: header `X-API-Key` richiesto su tutti tranne `/api/health*` e `/api/scheduler/jobs`.

| Endpoint | Metodo | Descrizione |
|---|---|---|
| `/api/health` | GET | Stato API, DB, UYUNI |
| `/api/health/detailed` | GET | Metriche complete |
| `/api/scheduler/jobs` | GET | Stato e prossime esecuzioni job |
| `/api/sync/usn` | POST | Sync Ubuntu USN (manuale) |
| `/api/sync/dsa` | POST | Sync Debian DSA (manuale) |
| `/api/sync/nvd` | POST | Enrichment NVD/CVSS (manuale) |
| `/api/sync/auto` | POST | Pipeline completa |
| `/api/sync/status` | GET | Log ultimi 20 sync |
| `/api/uyuni/sync-packages` | POST | Cache pacchetti UYUNI |
| `/api/uyuni/push` | POST | Push errata pendenti |
| `/api/uyuni/channels` | GET | Canali UYUNI attivi |

### Parametri

| Endpoint | Parametro | Default | Max |
|---|---|---|---|
| `/api/sync/nvd` | `batch_size` | 50 | 500 |
| `/api/uyuni/push` | `limit` | 10 | 200 |

## Operazioni manuali

```bash
export KEY="$(grep SPM_API_KEY /opt/errata-parser/.env | cut -d= -f2)"
export API="http://localhost:5000"

# Health check
curl -s $API/api/health | python3 -m json.tool

# Canali UYUNI attivi
curl -s -H "X-API-Key: $KEY" $API/api/uyuni/channels | python3 -m json.tool

# Sync manuale USN
curl -s -X POST -H "X-API-Key: $KEY" $API/api/sync/usn | python3 -m json.tool

# Sync manuale DSA (può richiedere 15-30 min)
curl -s --max-time 1800 -X POST -H "X-API-Key: $KEY" $API/api/sync/dsa | python3 -m json.tool

# Aggiorna cache pacchetti UYUNI (necessario prima del push se ci sono version mismatch)
curl -s -X POST -H "X-API-Key: $KEY" $API/api/uyuni/sync-packages | python3 -m json.tool

# Push errata
curl -s -X POST -H "X-API-Key: $KEY" "$API/api/uyuni/push?limit=50" | python3 -m json.tool

# Pipeline completa
curl -s --max-time 3600 -X POST -H "X-API-Key: $KEY" $API/api/sync/auto | python3 -m json.tool

# Stato scheduler
curl -s $API/api/scheduler/jobs | python3 -m json.tool

# Log sync recenti
curl -s -H "X-API-Key: $KEY" $API/api/sync/status | python3 -m json.tool
```

## Gestione servizio

```bash
systemctl status errata-parser
systemctl restart errata-parser
journalctl -u errata-parser -f                         # log live
journalctl -u errata-parser -n 50                      # ultimi 50 log
tail -f /opt/errata-parser/logs/errata-parser.log      # log applicativo
tail -f /opt/errata-parser/logs/error.log              # log gunicorn
```

## Note architettura UYUNI

UYUNI gira come container Podman su openSUSE (`10.172.2.17`).
La web UI usa **SAML 2.0 con Azure AD** — questo riguarda solo il browser,
**non tocca le API XML-RPC** che continuano ad usare credenziali locali (`admin`/password).
Le chiamate di errata-parser verso `/rpc/api` sono indipendenti dal SAML.

## Troubleshooting

### `uyuni: "error: Internal error"` nel health check

L'errore è oscurato perché il messaggio di UYUNI contiene parole sensibili.
Diagnosi rapida — legge le credenziali dal `.env` e testa la connessione:

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
**La causa è il web server interno di UYUNI hung**, non un problema di rete.

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

Si verifica quando UYUNI è hung durante una sync e il worker rimane bloccato
sull'handshake TLS. Dopo aver riavviato UYUNI con `mgradm restart`:

```bash
systemctl restart errata-parser
```

### Push errata skippati (version mismatch)

Se `/api/uyuni/push` ritorna `skipped_version_mismatch > 0`, la versione corretta
del pacchetto non è ancora nella cache UYUNI. Aggiornare prima la cache:

```bash
export KEY="$(grep SPM_API_KEY /opt/errata-parser/.env | cut -d= -f2)"
curl -s -X POST -H "X-API-Key: $KEY" http://localhost:5000/api/uyuni/sync-packages | python3 -m json.tool
# poi riprovare il push
curl -s -X POST -H "X-API-Key: $KEY" "http://localhost:5000/api/uyuni/push?limit=50" | python3 -m json.tool
```
