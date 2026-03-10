# Errata-Parser v3.1

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
| `UYUNI_USER` | **SI** | — | Admin UYUNI |
| `UYUNI_PASSWORD` | **SI** | — | Password admin UYUNI |
| `SPM_API_KEY` | Raccomandato | — | Header `X-API-Key` |
| `NVD_API_KEY` | Raccomandato | — | Rate limit NVD API |
| `SCHEDULER_ENABLED` | No | `false` | `true` attiva APScheduler |
| `LOG_FILE` | No | `/var/log/errata-manager.log` | Path log |

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
export KEY="spm-key-2024"
export API="http://localhost:5000"

# Sync manuale USN
curl -s -X POST -H "X-API-Key: $KEY" $API/api/sync/usn | python3 -m json.tool

# Sync manuale DSA (può richiedere 15-30 min)
curl -s --max-time 1800 -X POST -H "X-API-Key: $KEY" $API/api/sync/dsa | python3 -m json.tool

# Push errata
curl -s -X POST -H "X-API-Key: $KEY" "$API/api/uyuni/push?limit=50" | python3 -m json.tool

# Stato scheduler
curl -s $API/api/scheduler/jobs | python3 -m json.tool
```

## Gestione servizio

```bash
systemctl status errata-parser
systemctl restart errata-parser
journalctl -u errata-parser -f          # log live
journalctl -u errata-parser -n 50       # ultimi 50 log
```

## Troubleshooting

### `uyuni = "error: Connection refused"`
```bash
# Sul server UYUNI: verificare regola iptables
iptables -t nat -L POSTROUTING -n | grep 10.89.0.3
# Se manca:
iptables -t nat -I POSTROUTING -d 10.89.0.3 -p tcp --dport 443 -j MASQUERADE
iptables-save > /etc/sysconfig/iptables
```

### Worker bloccato / no risposta
```bash
systemctl restart errata-parser
# Il worker è unico (--workers 1), se è occupato su una sync lunga
# attendere il completamento o riavviare
```

### Push errata skippati (version mismatch)
```bash
# Aggiornare prima la cache pacchetti
curl -s -X POST -H "X-API-Key: $KEY" $API/api/uyuni/sync-packages
```
