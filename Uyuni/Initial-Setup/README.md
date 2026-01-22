# UYUNI Errata Manager v2.5 - Setup & Deployment

Sistema per sincronizzare automaticamente gli avvisi di sicurezza (USN/DSA) verso UYUNI Server.

## Struttura

```
Initial-Setup/
├── app-v2.5-IMPROVED.py     # API Flask principale
├── scripts/                  # Script operativi
│   ├── errata-sync-v2.5-IMPROVED.sh  # Sync completo automatizzato
│   ├── test-and-sync.sh              # Script interattivo test & sync
│   ├── remote-sync.sh                # Sync esterni (da PC/Cloud Shell)
│   ├── uyuni-server-sync.sh          # Sync interni (da server UYUNI)
│   ├── check-containers.sh           # Verifica stato container
│   ├── deploy-oval-fix.sh            # Deploy container con fix
│   ├── sync-oval-individual.sh       # Sync OVAL singole piattaforme
│   ├── monitor-oval-sync.sh          # Monitor sync OVAL
│   ├── fix-container-timeout.sh      # Fix timeout container
│   └── QUICK-START.sh                # Quick start setup
└── docs/                     # Documentazione
    ├── DEPLOYMENT-GUIDE-v2.5.md           # Guida deployment principale
    ├── README-v2.5-IMPROVEMENTS.md        # Changelog v2.5
    ├── UYUNI-ERRATA-MANAGER-v2.4-GUIDA-COMPLETA.md  # Guida completa background
    ├── Installazione-UYUNI.md             # Installazione server UYUNI
    ├── UYUNI-Guida-02-Setup-Ubuntu2204-CLM.md       # Setup Ubuntu CLM
    └── RICHIESTA-NAT-GATEWAY-PSN.md       # Template richiesta NAT Gateway
```

## Quick Start

### 1. Health Check Container

```bash
# Verifica stato container
./scripts/check-containers.sh

# Test connettività
curl -s http://10.172.5.5:5000/api/health | jq
```

### 2. Sync Completo

**Architettura a 2 Container:**
- **Container Pubblico** (4.232.4.32): Sync USN, DSA, OVAL, NVD
- **Container Interno** (10.172.5.5): Push UYUNI, Cache pacchetti

```bash
# FASE 1: Sync esterni (da PC/Azure Cloud Shell)
./scripts/remote-sync.sh full

# FASE 2: Sync interni (da server UYUNI)
ssh root@10.172.2.5
/root/uyuni-server-sync.sh quick
```

### 3. Automazione (Cron)

```bash
# Sul server UYUNI
cat > /etc/cron.d/errata-sync << 'EOF'
0 2 * * 0 root /root/errata-sync.sh >> /var/log/errata-sync.log 2>&1
EOF
```

## API Endpoints Principali

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/health` | GET | Health check base |
| `/api/health/detailed` | GET | Health check dettagliato |
| `/api/sync/usn` | POST | Sync Ubuntu USN |
| `/api/sync/dsa/full` | POST | Sync Debian DSA completo |
| `/api/sync/oval?platform=all` | POST | Sync OVAL definitions |
| `/api/uyuni/sync-packages` | POST | Update cache pacchetti |
| `/api/uyuni/push` | POST | Push errata a UYUNI |
| `/api/stats/overview` | GET | Statistiche generali |

## Documentazione

- **Deployment**: [docs/DEPLOYMENT-GUIDE-v2.5.md](docs/DEPLOYMENT-GUIDE-v2.5.md)
- **Changelog v2.5**: [docs/README-v2.5-IMPROVEMENTS.md](docs/README-v2.5-IMPROVEMENTS.md)
- **Guida Completa**: [docs/UYUNI-ERRATA-MANAGER-v2.4-GUIDA-COMPLETA.md](docs/UYUNI-ERRATA-MANAGER-v2.4-GUIDA-COMPLETA.md)

## Ambiente

| Componente | Valore |
|------------|--------|
| Container Pubblico | 4.232.4.32:5000 |
| Container Interno | 10.172.5.5:5000 |
| Server UYUNI | 10.172.2.5 |
| Database PostgreSQL | 10.172.2.6:5432 |
| Versione API | 2.5 |

## Troubleshooting

### Container non risponde
```bash
az container restart --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal
```

### Verificare log
```bash
az container logs --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal
```

### Statistiche errata
```bash
curl -s http://10.172.5.5:5000/api/stats/overview | jq
```

---

**Versione**: 2.5
**Ultimo aggiornamento**: 2026-01-22
