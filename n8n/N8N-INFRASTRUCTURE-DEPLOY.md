# n8n Infrastructure — Deploy Guide

## Infrastruttura

```
vm-n8n (10.172.2.5) — Ubuntu 24.04 — Standard D2ls v5 (2 vCPU, 4 GB RAM)
ASL0603-spoke10-spoke-italynorth/default

Stack:
├── n8n           :5678   → workflow automation (backend PostgreSQL)
├── PostgreSQL    :5432   → database (interno, non esposto)
├── Prometheus    :9090   → raccolta metriche (solo localhost)
├── Node Exporter         → metriche OS (CPU, RAM, disco, rete)
└── Grafana       :3000   → dashboard monitoring
```

### Accesso

| Servizio   | URL                          | Credenziali             |
|------------|------------------------------|-------------------------|
| n8n        | http://10.172.2.5:5678       | admin / N8nSecure2024!  |
| Grafana    | http://10.172.2.5:3000       | admin / GrafanaSecure2024! |
| Prometheus | http://10.172.2.5:9090       | solo dalla VM           |

> Accesso alla VM: Azure Bastion → vm-n8n

---

## Struttura file sul VM

```
/home/azureuser/
├── .n8n/                          # dati n8n (workflow, config, encryption key)
│   ├── database.sqlite            # (legacy — non più usato, PostgreSQL attivo)
│   ├── backup-workflows.json      # backup export workflow
│   ├── backup-credentials.json    # backup export credenziali
│   └── config                     # encryption key (NON eliminare mai)
└── n8n-prod/
    ├── docker-compose.yml
    ├── .env                        # secrets (non committare)
    ├── prometheus/
    │   └── prometheus.yml
    └── grafana/
        └── provisioning/
            ├── datasources/
            │   └── datasource.yml
            └── dashboards/
                └── dashboard.yml
```

---

## Deploy da zero

### Prerequisiti

- VM Ubuntu 24.04 nella VNET Azure
- Docker 29.x e Docker Compose v5.x installati
- Porta 5678 e 3000 aperte sull'NSG (inbound da VirtualNetwork)

### 1. Installa Docker (se non presente)

```bash
sudo apt-get update && sudo apt-get upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker azureuser
# logout + login per applicare i permessi
```

### 2. Crea struttura directory

```bash
mkdir -p /home/azureuser/n8n-prod/prometheus
mkdir -p /home/azureuser/n8n-prod/grafana/provisioning/datasources
mkdir -p /home/azureuser/n8n-prod/grafana/provisioning/dashboards
```

### 3. Crea i file di configurazione

Usa Python per evitare problemi di encoding da copy-paste via Bastion:

```bash
python3 - << 'PYEOF'
# incolla il contenuto del file target (vedi sezione File di configurazione)
PYEOF
```

### 4. Avvia lo stack

```bash
cd /home/azureuser/n8n-prod
docker compose up -d
docker compose ps
```

### 5. Verifica metriche n8n

```bash
curl -s -u admin:N8nSecure2024! http://localhost:5678/metrics | head -20
```

---

## File di configurazione

### `docker-compose.yml`

```yaml
services:

  postgres:
    image: postgres:16-alpine
    container_name: n8n-postgres
    restart: always
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - n8n-net

  n8n:
    image: n8nio/n8n:latest
    container_name: n8n
    restart: always
    ports:
      - "5678:5678"
    environment:
      DB_TYPE: postgresdb
      DB_POSTGRESDB_HOST: postgres
      DB_POSTGRESDB_PORT: 5432
      DB_POSTGRESDB_DATABASE: ${POSTGRES_DB}
      DB_POSTGRESDB_USER: ${POSTGRES_USER}
      DB_POSTGRESDB_PASSWORD: ${POSTGRES_PASSWORD}
      N8N_BASIC_AUTH_ACTIVE: "true"
      N8N_BASIC_AUTH_USER: ${N8N_BASIC_AUTH_USER}
      N8N_BASIC_AUTH_PASSWORD: ${N8N_BASIC_AUTH_PASSWORD}
      N8N_SECURE_COOKIE: "false"
      GENERIC_TIMEZONE: Europe/Rome
      N8N_HOST: 10.172.2.5
      N8N_PORT: 5678
      N8N_PROTOCOL: http
      WEBHOOK_URL: http://10.172.2.5:5678/
      N8N_METRICS: "true"
      N8N_METRICS_PREFIX: "n8n_"
      N8N_METRICS_INCLUDE_DEFAULT_METRICS: "true"
      N8N_LOG_LEVEL: info
      N8N_LOG_OUTPUT: console
    volumes:
      - /home/azureuser/.n8n:/home/node/.n8n
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - n8n-net

  prometheus:
    image: prom/prometheus:latest
    container_name: n8n-prometheus
    restart: always
    ports:
      - "127.0.0.1:9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/prometheus
      - --storage.tsdb.retention.time=15d
    networks:
      - n8n-net

  node-exporter:
    image: prom/node-exporter:latest
    container_name: n8n-node-exporter
    restart: always
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - --path.procfs=/host/proc
      - --path.rootfs=/rootfs
      - --path.sysfs=/host/sys
      - --collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)
    networks:
      - n8n-net

  grafana:
    image: grafana/grafana:latest
    container_name: n8n-grafana
    restart: always
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: ${GRAFANA_ADMIN_USER}
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD}
      GF_USERS_ALLOW_SIGN_UP: "false"
      GF_SERVER_DOMAIN: 10.172.2.5
      GF_ANALYTICS_REPORTING_ENABLED: "false"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
    depends_on:
      - prometheus
    networks:
      - n8n-net

networks:
  n8n-net:
    driver: bridge

volumes:
  postgres_data:
  prometheus_data:
  grafana_data:
```

### `.env`

```env
# PostgreSQL
POSTGRES_DB=n8n
POSTGRES_USER=n8n
POSTGRES_PASSWORD=N8nPostgres2024!

# n8n auth
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=N8nSecure2024!

# Grafana
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=GrafanaSecure2024!
```

### `prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: [localhost:9090]

  - job_name: n8n
    static_configs:
      - targets: [n8n:5678]
    metrics_path: /metrics
    basic_auth:
      username: admin
      password: N8nSecure2024!

  - job_name: node-exporter
    static_configs:
      - targets: [node-exporter:9100]
```

### `grafana/provisioning/datasources/datasource.yml`

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

### `grafana/provisioning/dashboards/dashboard.yml`

```yaml
apiVersion: 1
providers:
  - name: default
    type: file
    editable: true
    options:
      path: /etc/grafana/provisioning/dashboards
```

---

## Migrazione SQLite → PostgreSQL

Da eseguire quando si ha già un'istanza n8n con SQLite e si vuole migrare.

### Export dal container esistente

```bash
# Se il container è running
docker exec n8n n8n export:workflow --all \
  --output=/home/node/.n8n/backup-workflows.json

docker exec n8n n8n export:credentials --all \
  --output=/home/node/.n8n/backup-credentials.json
```

```bash
# Se il container non è running (export da immagine temporanea)
docker run --rm \
  -v /home/azureuser/.n8n:/home/node/.n8n \
  --entrypoint n8n \
  n8nio/n8n:latest \
  export:workflow --all --output=/home/node/.n8n/backup-workflows.json

docker run --rm \
  -v /home/azureuser/.n8n:/home/node/.n8n \
  --entrypoint n8n \
  n8nio/n8n:latest \
  export:credentials --all --output=/home/node/.n8n/backup-credentials.json
```

### Import nel nuovo stack PostgreSQL

```bash
# Aspetta che n8n sia avviato
sleep 10

docker exec n8n n8n import:workflow \
  --input=/home/node/.n8n/backup-workflows.json

docker exec n8n n8n import:credentials \
  --input=/home/node/.n8n/backup-credentials.json
```

> Il workflow viene importato come **disattivato** — riattivarlo manualmente dalla UI.

---

## Grafana — Dashboard

Il datasource Prometheus è già configurato automaticamente al primo avvio.

### Dashboard 1 — Node Exporter Full (metriche VM)

**Dashboards** → **New** → **Import** → ID `1860` → **Load** → **Import**

### Dashboard 2 — n8n Overview (dashboard manuale)

Non esiste un dashboard community stabile per n8n. Creare manualmente:

**Dashboards** → **New** → **New dashboard** → **Add visualization**

Aggiungere i seguenti pannelli:

| Pannello | Query | Unit | Tipo |
|---|---|---|---|
| Memoria n8n | `n8n_process_resident_memory_bytes` | bytes (SI) | Time series |
| CPU n8n | `rate(n8n_process_cpu_seconds_total[5m])` | percent (0.0-1.0) | Time series |
| Esecuzioni workflow | `n8n_workflow_executions_total` | — | Stat |
| CPU VM | `100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)` | percent (0-100) | Gauge |

> **Attenzione**: Il campo query di Grafana via browser può convertire le virgolette dritte in tipografiche.
> Per il pannello CPU VM usare la modalità **Builder** per inserire il filtro `mode="idle"`,
> poi tornare in **Code** per completare la query.

Salvare come `n8n Overview`.

---

## Operazioni quotidiane

```bash
# Stato stack
cd /home/azureuser/n8n-prod && docker compose ps

# Log in tempo reale
docker compose logs n8n -f
docker compose logs n8n-grafana -f

# Riavvio
docker compose restart

# Aggiornamento immagini
docker compose pull && docker compose up -d

# Backup PostgreSQL
docker exec n8n-postgres pg_dump -U n8n n8n > backup_$(date +%Y%m%d).sql

# Restore PostgreSQL
docker exec -i n8n-postgres psql -U n8n n8n < backup_20260101.sql
```

---

## Troubleshooting

| Problema | Causa probabile | Soluzione |
|---|---|---|
| n8n non si avvia | PostgreSQL non healthy | `docker compose logs n8n-postgres` |
| Metriche non in Prometheus | n8n non espone /metrics | Verifica `N8N_METRICS=true` in .env |
| Grafana non vede dati | Datasource mal configurato | Grafana → Datasources → Test |
| Credenziali non funzionano dopo import | Encryption key diversa | Verifica che `/home/azureuser/.n8n/config` sia lo stesso dell'originale |
| YAML error su docker compose | Encoding da copy-paste Bastion | Usa il metodo Python per scrivere i file |
| Query Grafana CPU con errore `unexpected identifier "idle"` | Virgolette tipografiche nel browser | Usa Builder mode per inserire il filtro, poi torna in Code |
| Dashboard n8n ID non trovato | Nessun dashboard community stabile | Creare manualmente (vedi sezione Grafana) |
| Workflow importato inattivo | Import disattiva sempre i workflow | Aprire il workflow → clicca **Publish** |

---

## Note importanti

- **`/home/azureuser/.n8n/config`** contiene l'encryption key delle credenziali — non eliminare mai, non sovrascrivere
- **`.env`** non va mai committato su git
- Prometheus è esposto solo su `127.0.0.1:9090` — non raggiungibile dall'esterno della VM
- I file YAML su questa VM vanno scritti via Python (`python3 - << 'PYEOF'`) per evitare problemi di encoding da Bastion
