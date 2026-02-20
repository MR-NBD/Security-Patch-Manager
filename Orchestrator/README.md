# SPM Orchestrator

Componente di orchestrazione per il processo supervisionato di patch management.
Separato infrastrutturalmente da SPM-SYNC e UYUNI Server.

## Architettura

```
VM-ORCHESTRATOR (Ubuntu 24.04)
├── Flask :5001       → API orchestrazione
├── Streamlit :8501   → Dashboard operatore
└── PostgreSQL :5432  → Database locale
```

Comunica con:
- **SPM-SYNC** `:5000` → polling errata (read-only, ogni 30 min)
- **UYUNI** `:443` → XML-RPC per scheduling patch
- **Salt API** `:9080` → esecuzione comandi sui minion
- **Prometheus** `:9090` → raccolta metriche validazione

## Installazione

```bash
# Su VM Ubuntu 24.04, come root
cp .env.example .env
nano .env              # Configura tutti i parametri
sudo bash scripts/install.sh
```

## Avvio manuale (development)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Configura .env
python -m app.main
```

## Test

```bash
source venv/bin/activate
pytest tests/ -v
```

## API

```
GET  /api/v1/health           → Health check base
GET  /api/v1/health/detail    → Health check con componenti

# (in sviluppo)
GET  /api/v1/risk-profile     → Success Score errata
GET  /api/v1/queue            → Coda test
POST /api/v1/test/start       → Avvia test
GET  /api/v1/approvals/pending → Patch in attesa approvazione
```

Vedi `../Uyuni/Infrastructure-Design/SPM-ORCHESTRATOR-API-SPEC.md` per spec complete.

## Struttura

```
Orchestrator/
├── app/
│   ├── main.py           # Flask entry point
│   ├── config.py         # Configurazione da .env
│   ├── api/
│   │   └── health.py     # /api/v1/health
│   ├── services/
│   │   └── db.py         # Connessione PostgreSQL
│   └── utils/
│       └── logger.py     # Logging JSON strutturato
├── streamlit/            # Dashboard (TODO)
├── sql/migrations/       # Schema PostgreSQL
├── systemd/              # Unit files systemd
├── scripts/
│   └── install.sh        # Setup VM completo
├── tests/
│   └── test_health.py
├── requirements.txt
└── .env.example
```

## Logging

```bash
# Systemd
journalctl -u spm-orchestrator -f

# File
tail -f /var/log/spm-orchestrator/app.log
```
