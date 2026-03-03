# Azure POC Manager — Guida rapida

Spegni e accendi tutte le risorse Azure del POC con un comando solo.

---

## Prerequisiti (una volta sola)

```bash
# 1. Azure CLI installato e loggato
az login

# 2. Python 3.8+
python3 --version
```

---

## Comandi principali

```bash
cd tools/

# Spegni tutto (fine giornata)
python3 azure-poc-manager.py stop

# Accendi tutto (mattina)
python3 azure-poc-manager.py start

# Controlla lo stato
python3 azure-poc-manager.py status
```

---

## Filtrare per tipo o nome

```bash
# Solo le VM
python3 azure-poc-manager.py stop --filter vm

# Solo i Logic App
python3 azure-poc-manager.py stop --filter logicapp

# Solo le risorse con "uyuni" nel nome
python3 azure-poc-manager.py stop --filter uyuni

# Solo il PostgreSQL
python3 azure-poc-manager.py status --filter postgres
```

---

## Dry-run (zero rischi)

Mostra cosa verrebbe fatto senza toccare nulla:

```bash
python3 azure-poc-manager.py stop --dry-run
python3 azure-poc-manager.py start --dry-run
```

---

## Config: `poc-resources.json`

Elenco delle risorse gestite. Ogni riga è una risorsa:

```json
{
  "resources": [
    { "name": "nome-vm",    "type": "vm",       "resource_group": "rg-poc" },
    { "name": "nome-aci",   "type": "aci",       "resource_group": "rg-poc" },
    { "name": "nome-pg",    "type": "postgres",  "resource_group": "rg-poc" },
    { "name": "logic-sync", "type": "logicapp",  "resource_group": "rg-poc" }
  ]
}
```

Per aggiungere o rimuovere una risorsa: modifica `poc-resources.json`.

### Tipi supportati

| `type`        | Risorsa Azure                        | Stop            |
|---------------|--------------------------------------|-----------------|
| `vm`          | Virtual Machine                      | deallocate (no costi compute) |
| `aci`         | Container Instance                   | stop            |
| `aks`         | Kubernetes Service                   | stop            |
| `webapp`      | App Service                          | stop            |
| `functionapp` | Function App                         | stop            |
| `postgres`    | PostgreSQL Flexible Server           | stop            |
| `logicapp`    | Logic App workflow                   | disable         |
| `sql`         | Azure SQL serverless *(+ campo `server`)* | pause      |

---

## Note operative

- **VM**: lo stop usa `deallocate` — azzera i costi compute, il disco rimane
- **VM `--no-wait`**: il comando torna subito, Azure impiega 1-3 min in background. Normale vedere stati intermedi nel `status`
- **Logic App**: disable/enable non cancella le esecuzioni in corso, le ferma per quelle future
- **PostgreSQL**: lo stop automatico di Azure scatta dopo 7 giorni anche senza questo script

---

## Uso con config diverso

Utile se hai più ambienti (dev, staging…):

```bash
python3 azure-poc-manager.py stop  --config poc-resources-dev.json
python3 azure-poc-manager.py start --config poc-resources-staging.json
```

---

## Subscription diversa per una risorsa

Aggiungi il campo `subscription` nella riga specifica:

```json
{ "name": "vm-altro", "type": "vm", "resource_group": "rg-altro",
  "subscription": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" }
```
