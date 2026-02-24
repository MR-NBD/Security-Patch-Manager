## 1. Stato attuale e Single Points of Failure
### Topologia corrente

```
10.172.2.17  uyuni-server-test   Standard D8as_v5 (8 vCPU, 32 GB)  AZ1
             ├── container: uyuni-server (Salt Master, Tomcat, Apache, Cobbler)
             └── container: uyuni-db    (PostgreSQL — stesso host)

10.172.2.20  uyuni-proxy-test    Standard B2s (2 vCPU, 4 GB)        AZ1
             ├── proxy-httpd
             ├── proxy-salt-broker
             ├── proxy-squid
             ├── proxy-ssh
             └── proxy-tftpd

Client attuali: test-ubuntu-2404 (10.172.2.18), test-rhel9 (10.172.2.19)
```

### Analisi dei rischi

| Componente | Failure Mode | Impatto | Attuale Mitigazione |
|---|---|---|---|
| VM uyuni-server | Crash / manutenzione Azure | Tutti i client Salt offline, nessuna patch management | Nessuna |
| Container uyuni-db | Crash PostgreSQL | Server UYUNI non operativo | Nessuna |
| VM uyuni-proxy | Crash | Tutti i client dietro il proxy offline | Nessuna |
| Disco `/manager_storage` | Corruzione / riempimento | Repo non servibili | LVM resize manuale |
| Disco `/pgsql_storage` | Corruzione | DB irrecuperabile | Nessuna |
| DNS (`/etc/hosts` statici) | Nessun failover automatico | Impossibile redirigere traffico | Nessuna |
| AZ1 intera | Failure di zona Azure | Sistema completamente offline | Nessuna |

### Vincolo architetturale fondamentale

> **UYUNI non supporta clustering active/active nativo del server.**
> La documentazione ufficiale SUSE/UYUNI definisce due soli pattern HA supportati:
> 1. **Active/Passive** con failover manuale o semi-automatico
> 2. **Hub Multi-Server** per scale > 5.000 client (con ISS v2 per content sync)
>
> Il layer proxy è stateless lato gestionale: lo stato dei client risiede tutto nel DB del server.
> Il pattern ufficiale per l'HA dei proxy è la **Proxy Replacement Strategy**, non il load balancing classico.
## 2. Scenario A — Meno di 500 client

Con < 500 client, un singolo server UYUNI è ampiamente sufficiente (capacità documentata: fino a ~1.000 client per server con hardware adeguato). L'obiettivo HA è la **ridondanza del servizio**, non la scalabilità.
### A1 — SLA best-effort (RTO 30-60 min)

**Filosofia**: in caso di failure, si ripristina da backup. Nessuna replica live.
Adatto a contesti dove la gestione patch non è un servizio critico 24/7.

#### Architettura

```
AZ1
┌──────────────────────────────────────────────┐
│  uyuni-server-test  (PRIMARY — sempre attivo) │
│  Standard D8as_v5 · 10.172.2.17              │
│  ├── uyuni-server container                   │
│  └── uyuni-db container                       │
│                                               │
│  Backup giornaliero via mgradm backup create  │
│  → destinazione: Azure Files / Azure Blob     │
└──────────────────────────────────────────────┘
         │
         │
┌────────▼───────────────────────────────────────┐
│  Proxy #1 (AZ1)         Proxy #2 (AZ2)         │
│  uyuni-proxy-1          uyuni-proxy-2           │
│  10.172.2.20            10.172.2.30             │
│  Standard B4ms          Standard B4ms           │
│                                                  │
│  ~50% client → proxy #1                         │
│  ~50% client → proxy #2                         │
│  (DNS: due FQDN distinti, no Azure LB)          │
└─────────────────────────────────────────────────┘

Azure Private DNS Zone: uyuni.internal
  uyuni-server.uyuni.internal    → 10.172.2.17
  uyuni-proxy-1.uyuni.internal   → 10.172.2.20
  uyuni-proxy-2.uyuni.internal   → 10.172.2.30
```

#### Procedura di backup (server)

```bash
# Sul server UYUNI — eseguire via cron ogni notte alle 02:00
mgradm backup create --output /mnt/uyuni-backup/$(date +%Y%m%d)

# Montare Azure Files come destinazione backup
# /etc/fstab:
# //myaccount.file.core.windows.net/uyuni-backup /mnt/uyuni-backup \
#   cifs credentials=/etc/smbcredentials,nofail,vers=3.0 0 0
```

> `mgradm backup create` (disponibile da UYUNI 2025.05+) copre:
> - Database PostgreSQL completo
> - Configurazioni (`/etc/rhn/`, `/etc/salt`, `/etc/cobbler/`)
> - Dati applicativi (pillar, states, pub keys)
> **Non copre** il repository pacchetti (`/manager_storage`) — da sincronizzare separatamente
> o accettare che vada ri-sincronizzato post-restore (ore, ma automatico).

#### Restore in caso di failure server

```bash
# 1. Crea nuova VM AZ1 (o AZ2) con openSUSE Leap 15.6 — stesso FQDN
#    o aggiorna record DNS uyuni-server.uyuni.internal → nuovo IP

# 2. Installa prerequisiti (FASE 1-7 della procedura di installazione)

# 3. Restore da backup
mgradm backup restore /mnt/uyuni-backup/20260223

# 4. Ri-sincronizza repository (background, automatico)
#    I Salt minion si riconnetteranno automaticamente quando il server torna online
#    con lo stesso FQDN (la chiave Salt è nel backup)
```

**RTO effettivo**: 30-45 min (creazione VM) + 15-30 min (restore) = ~60 min
**RPO**: 24 ore (backup giornaliero) — con backup ogni 6h → RPO 6h

#### Failover proxy (entrambe le strategie)

Poiché i proxy hanno FQDN separati, il failure di un proxy impatta solo i client assegnati ad esso.

**Recovery opzione 1 — Riassegna client via Web UI**:
```
Systems → System List → seleziona client → Details → Connection → Change Proxy
→ seleziona proxy #2
```

**Recovery opzione 2 — Riassegna client via Salt (bulk)**:
```bash
# Sul server UYUNI, nella shell del container
mgrctl exec -- salt -G 'proxy:uyuni-proxy-1.uyuni.internal' \
  state.apply uyuni_proxy_switch pillar='{"new_proxy": "uyuni-proxy-2.uyuni.internal"}'
```

**Recovery opzione 3 — Proxy Replacement (identità swap)**:
```bash
# Deploy nuovo proxy con stesso FQDN e IP del proxy fallito
# I client non si accorgono del cambio
# Usa reactivation key per preservare system_id e history
```

#### Componenti Azure richiesti

| Componente | Scopo | Costo indicativo |
|---|---|---|
| Azure Private DNS Zone `uyuni.internal` | Failover DNS senza modifiche `/etc/hosts` | ~€0.50/mese |
| Azure Files Standard (100 GB) | Storage backup giornaliero | ~€5/mese |
| VM Proxy #2 Standard B4ms (AZ2) | Ridondanza proxy | ~€60/mese |
| Azure Backup (policy standard, server VM) | Recovery VM-level | ~€10/mese |

---

### A2 — SLA strict (RTO < 15 min)

**Filosofia**: warm standby del server con replica PostgreSQL live. Failover semi-automatico.
Adatto a contesti dove la gestione patch fa parte di un processo operativo continuativo.

#### Architettura

```
AZ1 (PRIMARY)                              AZ2 (STANDBY — warm)
┌──────────────────────┐                  ┌──────────────────────┐
│ uyuni-server PRIMARY │                  │ uyuni-server STANDBY │
│ Standard D8as_v5     │                  │ Standard D8as_v5     │
│ 10.172.2.17          │                  │ 10.172.2.50          │
│                      │                  │                      │
│ uyuni-server: UP     │                  │ uyuni-server: STOPPED│
│ uyuni-db: PRIMARY    │◄─── PgSQL ──────►│ uyuni-db: HOT STANDBY│
│                      │  Streaming Rep.  │                      │
└──────────┬───────────┘  (TCP 5432)      └──────────────────────┘
           │
           ▼
  Azure Files NFS Premium
  /manager_storage (condiviso AZ1+AZ2)
  HA nativa zone-redundant

┌──────────────────────────────────────────┐
│ Proxy #1 (AZ1)      Proxy #2 (AZ2)      │
│ B4ms · 10.172.2.20  B4ms · 10.172.2.30  │
└──────────────────────────────────────────┘

Azure Private DNS Zone: uyuni.internal
  uyuni-server.uyuni.internal → 10.172.2.17   ← cambia a .50 in failover
  uyuni-proxy-1.uyuni.internal → 10.172.2.20
  uyuni-proxy-2.uyuni.internal → 10.172.2.30
```

#### Configurazione PostgreSQL Streaming Replication

Sul container `uyuni-db` PRIMARY:
```bash
podman exec -it uyuni-db bash

# /var/lib/pgsql/data/postgresql.conf
wal_level = replica
max_wal_senders = 3
wal_keep_size = 1GB
hot_standby = on
synchronous_commit = on        # RPO=0, impatto ~15% performance
# oppure:
# synchronous_commit = local   # RPO < 1s, nessun impatto performance
```

```bash
# /var/lib/pgsql/data/pg_hba.conf — aggiungere:
host  replication  replicator  10.172.2.50/32  md5
```

Sul container `uyuni-db` STANDBY:
```bash
# Inizializzazione replica (una tantum)
pg_basebackup -h 10.172.2.17 -U replicator -D /var/lib/pgsql/data \
  -P -Xs -R --checkpoint=fast

# Il flag -R crea automaticamente standby.signal e postgresql.auto.conf
# con primary_conninfo già configurato
```

#### Procedura di failover (RTO target: 10-12 min)

```bash
# STEP 1 (2 min): Verificare che primary sia effettivamente irraggiungibile
ping 10.172.2.17
nc -zv 10.172.2.17 443

# STEP 2 (1 min): Promuovere PostgreSQL standby
podman exec uyuni-db pg_promote
# oppure: touch /var/lib/pgsql/data/failover_trigger

# Verificare che la promozione sia avvenuta
podman exec uyuni-db psql -U spacewalk -c "SELECT pg_is_in_recovery();"
# Deve restituire: f (false = ora è primary)

# STEP 3 (2 min): Avviare il container uyuni-server sul nodo standby
mgradm start

# STEP 4 (1 min): Aggiornare il record DNS
# Azure CLI:
az network private-dns record-set a update \
  --resource-group <rg> \
  --zone-name uyuni.internal \
  --record-set-name uyuni-server \
  --set "aRecords[0].ipv4Address=10.172.2.50"

# STEP 5 (3-4 min): I Salt minion si riconnetteranno automaticamente
# (TTL DNS basso, raccomandato: 60 secondi)

# STEP 6: Verificare
mgradm status
mgrctl exec -- salt-run manage.up
```

**RTO effettivo**: ~10-12 min con operatore disponibile
**RPO**: < 1 sec con `synchronous_commit = on` | < 1 min con `synchronous_commit = local`

#### Storage condiviso — Azure Files NFS Premium

```bash
# Mount su entrambi i nodi (fstab)
myaccount.file.core.windows.net:/myaccount/uyuni-repo \
  /manager_storage nfs \
  vers=4.1,sec=sys,nofail,_netdev 0 0
```

> **Azure Files Premium NFS** è zone-redundant (ZRS) nativamente: sopravvive al failure di una AZ senza intervento manuale. Il mount rimane valido su entrambi i nodi. Latenza: ~1-2 ms (accettabile per repository pacchetti, non per PostgreSQL).
> **Non usare Azure Files per `/pgsql_storage`**: la latenza NFS degrada significativamente le performance di PostgreSQL. Il DB deve rimanere su disco locale con replica logica/fisica.

#### Componenti Azure richiesti (in aggiunta ad A1)

| Componente | Scopo |
|---|---|
| VM Standby D8as_v5 (AZ2) | Standby server UYUNI |
| Azure Files Premium NFS (500 GB+, ZRS) | `/manager_storage` condiviso |
| Azure Private DNS Zone TTL=60s | Failover DNS rapido |

---

## 3. Scenario B — Più di 1000 client

Con > 1.000 client, un singolo server UYUNI inizia a mostrare limiti di performance (Salt event bus saturo, Taskomatic job queue in ritardo, Tomcat thread pool esaurito). Il tuning può estendere la capacità fino a ~2.500-3.000 client, ma oltre è necessaria una distribuzione orizzontale.

### Soglie di scaling documentate (UYUNI Large Deployments Guide)

| Client | Architettura | Proxy |
|---|---|---|
| < 500 | Single server, no tuning | 1 proxy per ridondanza |
| 500 – 1.500 | Single server + tuning JVM/Salt/PgSQL | 2 proxy (1 per 700 client) |
| 1.500 – 5.000 | Single server heavily tuned | 3-7 proxy (1 per 700 client) |
| > 5.000 | **Hub Architecture** (multi-server) | Proxy per ogni peripheral server |

---

### B1 — SLA best-effort

#### Architettura (1.000-3.000 client)

```
                    Azure Private DNS Zone
                    uyuni.internal

    uyuni-server.uyuni.internal → 10.172.2.17 (aggiornabile)

┌─────────────────────────────────────────────────────────────┐
│  UYUNI Server  Standard D16as_v5 (16 vCPU, 64 GB)          │
│  10.172.2.17  —  Heavily tuned (vedi sezione 4)             │
│  Backup giornaliero via mgradm backup create                │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   Proxy #1        Proxy #2       Proxy #3
   (AZ1)           (AZ2)          (AZ1/AZ2)
   ~400 client     ~400 client    ~400 client + spare
   B4ms            B4ms           B4ms
```

Con 3 proxy e distribuzione equilibrata, il failure di un proxy impatta al massimo 400 client (riassegnabili in 5-10 min via Salt action bulk).

#### Tuning server per > 1.000 client

Vedere [Sezione 4](#4-gestione-avanzata-e-ha-dellapi-xml-rpc) per il tuning dettagliato di Tomcat, Salt e PostgreSQL.

---

### B2 — SLA strict (RTO < 15 min)

Per > 1.000 client con SLA strict, l'architettura Hub diventa la scelta tecnicamente corretta.

#### Architettura Hub (> 3.000 client o multi-sito)

```
                    ┌──────────────────────────┐
                    │   HUB SERVER (Central)    │
                    │   Standard D16as_v5       │
                    │   Accesso SCC / NVD        │
                    │   ISS v2 content sync     │
                    └────────────┬─────────────┘
                                 │ Inter-Server Sync v2
                    ┌────────────┴─────────────┐
                    ▼                           ▼
     ┌──────────────────────┐    ┌──────────────────────┐
     │  PERIPHERAL #1       │    │  PERIPHERAL #2       │
     │  Standard D8as_v5    │    │  Standard D8as_v5    │
     │  AZ1 · 10.172.2.17   │    │  AZ2 · 10.172.2.50   │
     │  OS Group: RHEL      │    │  OS Group: Ubuntu    │
     │  ~500-1500 client    │    │  ~500-1500 client    │
     └──────┬───────────────┘    └──────────────┬───────┘
            │                                   │
     ┌──────┴──────┐                    ┌───────┴──────┐
     Proxy A1  Proxy A2            Proxy B1       Proxy B2
     (AZ1)     (AZ2)               (AZ1)          (AZ2)
```

#### ISS v2 — Inter-Server Synchronization

ISS v2 (deprecata la v1 in SUSE Manager 5.0) consente la sincronizzazione **bidirezionale** dei contenuti tra server:

```bash
# Export dal server hub
inter-server-sync export \
  --channels=ubuntu-24.04-amd64,rhel9-x86_64 \
  --outputDir=/var/spacewalk/iss-export

# Transfer via rsync al peripheral
rsync -avz /var/spacewalk/iss-export/ \
  peripheral-1:/var/spacewalk/iss-import/

# Import sul peripheral
inter-server-sync import \
  --importDir=/var/spacewalk/iss-import
```

> **Vincoli ISS v2**:
> - Hub e peripheral devono essere sulla **stessa versione** UYUNI
> - I nomi delle organizzazioni devono corrispondere (case-sensitive)
> - I repository di pacchetti non vengono sincronizzati via ISS: ogni peripheral deve sincronizzare direttamente dai vendor (o usare un mirror interno)
> - ISS v2 non è un meccanismo di HA real-time: è una sincronizzazione periodica per disaster recovery o distribuzione geografica

#### Peripheral HA (active/passive per ogni peripheral)

Ogni peripheral server può avere il proprio standby, replicando il pattern A2 per ciascuno. In alternativa, in caso di failure di un peripheral, i suoi client possono essere temporaneamente riassegnati al peripheral superstite (se la capacità lo consente).

---

## 4. Gestione avanzata e HA dell'API XML-RPC

L'API XML-RPC di UYUNI è il canale primario usato dallo SPM Orchestrator (e da qualsiasi client esterno) per interrogare e comandare il server. Comprendere la sua architettura interna è fondamentale per progettare un sistema robusto.

### 4.1 Architettura interna dell'API XML-RPC

```
Client esterno (es. SPM Orchestrator)
        │
        │  HTTPS POST /rpc/api
        ▼
Apache HTTPD (porta 443, reverse proxy)
        │
        │  HTTP interno
        ▼
Tomcat (porta 8080, dentro container uyuni-server)
        │
        │  Java Servlet
        ▼
XMLRPC Handler (spacewalk-java)
        │
        ├── Session Store (in-memory, non persistente)
        │   Token = auth.login(user, password) → stringa hex
        │   Scadenza: 30 min di inattività (default)
        │
        ├── Hibernate (ORM) → PostgreSQL
        │   Pool C3P0: max 20 connessioni (default)
        │
        └── Salt API (per scheduleApplyErrata, scheduleScriptRun, ecc.)
            Salt REST API interna → Salt Master
```

#### Implicazioni HA

| Aspetto | Comportamento | Impatto in failover |
|---|---|---|
| Session token | In-memory su Tomcat, non persistito su DB | Tutti i token invalidi dopo failover → re-login obbligatorio |
| Operazioni asincrone | `scheduleApplyErrata` → `action_id` → polling | Un'azione schedulata prima del failover sopravvive nel DB, non va ri-schedulata |
| Salt events | Salt Master in-container, stato su filesystem | I minion si riconnettono automaticamente al nuovo master (stesso FQDN) |
| Cobbler | State su `/var/lib/cobbler`, coperto da backup | Restore necessario solo per ambienti con PXE boot attivo |

### 4.2 Tuning Tomcat per alta concorrenza

Il tuning seguente è necessario per deployment > 500 client o con molti client XML-RPC concorrenti (es. SPM Orchestrator con `UYUNI_SYNC_WORKERS=10`).

#### Parametri critici (file dentro il container `uyuni-server`)

**`/etc/tomcat/server.xml`** (o `/usr/share/tomcat/conf/server.xml`):
```xml
<Connector port="8080" protocol="HTTP/1.1"
    maxThreads="300"          <!-- default: 150 — aumentare con i client -->
    minSpareThreads="25"
    maxConnections="500"
    acceptCount="100"
    connectionTimeout="20000"
    keepAliveTimeout="60000"
/>
```

**`/etc/rhn/rhn.conf`** (principale file di configurazione UYUNI):
```ini
# Thread pool per la message queue di Taskomatic
java.message_queue_thread_pool_size = 50     # default: 5 — aumentare a 50-150

# Hibernate connection pool (deve essere < max_connections PostgreSQL - overhead)
hibernate.c3p0.max_size = 50                 # default: 20
hibernate.c3p0.min_size = 5
hibernate.c3p0.timeout = 300
hibernate.c3p0.acquire_increment = 2

# Worker Salt per eventi concorrenti
java.salt_event_thread_pool_size = 8        # ~CPU_cores / 2
```

> **Regola fondamentale di coerenza**:
> `max_connections (PostgreSQL)` > `hibernate.c3p0.max_size` + `taskomatic.connection_pool_size` + overhead (~20)
> Esempio: max 50 Hibernate + 20 Taskomatic + 20 overhead = PostgreSQL `max_connections = 100`

**Apache HTTPD** (`/etc/apache2/conf.d/zz-spacewalk-www.conf` nel container):
```apache
MaxRequestWorkers 200     # default: 150 — deve essere >= maxThreads Tomcat
ServerLimit       200
```

#### Applicare il tuning senza riavvio completo

```bash
# Modifica rhn.conf dentro il container
mgrctl exec -- bash -c "echo 'java.message_queue_thread_pool_size = 50' >> /etc/rhn/rhn.conf"

# Riavvio solo dei servizi Java (Tomcat + Taskomatic) senza riavviare il container
mgrctl exec -- systemctl restart tomcat taskomatic
```

### 4.3 Tuning PostgreSQL per alta concorrenza

```bash
# Dentro container uyuni-db: /var/lib/pgsql/data/postgresql.conf
shared_buffers = 8GB              # 25% RAM (su 32 GB: 8 GB)
effective_cache_size = 24GB       # 75% RAM
work_mem = 64MB                   # per query sorting (attenzione: per connessione)
maintenance_work_mem = 1GB
max_connections = 100             # coordinare con hibernate.c3p0.max_size
max_wal_size = 4GB
checkpoint_completion_target = 0.9
random_page_cost = 1.1            # per SSD (default 4.0 per HDD)
effective_io_concurrency = 200    # per SSD NVMe
```

#### Tool di supporto ufficiale

```bash
# UYUNI include uno script per raccomandare i parametri ottimali
mgrctl exec -- /usr/lib/susemanager/bin/susemanager-connection-check
```

> **Attenzione**: La documentazione ufficiale UYUNI avverte esplicitamente:
> *"The instructions in this section can have severe and catastrophic performance impacts when improperly used."*
> Applicare sempre in staging prima di produzione. Incrementare `work_mem` moltiplicato per il numero di connessioni può esaurire la RAM.

### 4.4 Gestione sessioni XML-RPC in scenario HA

La gestione delle sessioni è il punto più delicato in un contesto HA perché **i token XML-RPC non sopravvivono al failover del server**.

#### Comportamento attuale dello SPM (UyuniSession)

```
UyuniSession (context manager):
  __enter__: auth.login()  → token
  [operazioni XML-RPC con token]
  __exit__:  auth.logout() → token invalido

UyuniPatchClient:
  Wrappa UyuniSession, re-login ad ogni operazione critica
```

Questo pattern è **già resiliente al failover** nel caso di operazioni brevi: basta ri-istanziare `UyuniSession` dopo il failover e il nuovo `auth.login()` funziona immediatamente sul nuovo server.

#### Punto critico: operazioni long-running

`_wait_action()` nel SPM esegue polling per fino a **30 minuti** con la stessa sessione. Se il server va down durante questa finestra:

```python
# Pattern robusto consigliato per _wait_action()
def _wait_action(self, action_id, timeout=1800, poll_interval=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            completed = self.client.schedule.listCompletedActions(
                self.token, action_id
            )
            if completed:
                return "completed"
            # ... check failed
        except (xmlrpc.client.Fault, ConnectionRefusedError, OSError) as e:
            # Failover o riavvio del server: ri-autentica e riprova
            logger.warning(f"XML-RPC connection lost: {e}, re-authenticating")
            try:
                self._login()   # rinnova self.token
            except Exception:
                time.sleep(30)  # attendi che il server torni online
                continue
        time.sleep(poll_interval)
    raise TimeoutError(f"Action {action_id} timeout after {timeout}s")
```

> Le azioni già schedulate nel DB di UYUNI **non vanno perse** in caso di failover: Taskomatic le ri-esegue all'avvio del server ripristinato. Occorre solo riconnettersi e continuare il polling.

### 4.5 Rate limiting e protezione dell'API

UYUNI non ha rate limiting nativo sull'API XML-RPC, ma il Tomcat connector ha limiti di connessione che, se superati, producono `ConnectionRefusedError`.

#### Limiti pratici osservati

| Carico | Comportamento |
|---|---|
| < 20 richieste XML-RPC concorrenti | Nominale |
| 20-50 richieste concorrenti | Possibili rallentamenti Tomcat |
| > 50 richieste concorrenti | Possibile esaurimento thread pool (default 150 thread ma condivisi con Web UI e Salt) |
| > 100 richieste concorrenti | Degrado severo, possibili timeout 504 |

#### Raccomandazioni per client XML-RPC ad alta frequenza

```ini
# .env SPM Orchestrator — valori bilanciati per non sovraccaricare UYUNI
UYUNI_SYNC_WORKERS=10        # OK per sync errata (operazioni read-only veloci)
                              # Ridurre a 5 se UYUNI è su hardware limitato

# Aggiungere jitter al poller per distribuire il carico
# (non tutte le operazioni ogni esatto multiplo di 30 min)
UYUNI_POLL_INTERVAL_MINUTES=30
UYUNI_POLL_JITTER_SECONDS=120  # ±2 min di variazione casuale
```

#### Monitoraggio salute XML-RPC

```bash
# Health check semplice (non richiede autenticazione)
curl -sk https://uyuni-server.uyuni.internal/rpc/api \
  | grep -o 'UYUNI release [0-9.]*'

# Health check autenticato (verifica funzionalità completa)
python3 -c "
import xmlrpc.client, ssl
ctx = ssl._create_unverified_context()
c = xmlrpc.client.ServerProxy('https://uyuni-server.uyuni.internal/rpc/api',
    context=ctx)
tok = c.auth.login('admin', 'password')
print('OK:', c.api.getVersion())
c.auth.logout(tok)
"
```

#### Integrazione con Azure Monitor (raccomandato)

```bash
# Custom metric: latenza XML-RPC
# Script da eseguire ogni minuto via cron sul server o su VM di monitoring
# Invia a Log Analytics Workspace tramite Data Collector API
START=$(date +%s%N)
curl -sk -o /dev/null https://uyuni-server.uyuni.internal/rpc/api
END=$(date +%s%N)
LATENCY=$(( (END - START) / 1000000 ))
# → inviare LATENCY ms a Azure Monitor Custom Metrics
```

### 4.6 Circuit Breaker pattern per client XML-RPC

In caso di server UYUNI temporaneamente irraggiungibile (riavvio, failover, manutenzione), un client XML-RPC senza circuit breaker rischia di accumulare thread bloccati e saturare il proprio thread pool.

```python
# Pattern circuit breaker minimale per UyuniSession
class UyuniCircuitBreaker:
    """
    Evita la tempesta di retry quando UYUNI è in failover.
    Stati: CLOSED (normale) → OPEN (stop) → HALF_OPEN (test)
    """
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failures = 0
        self.threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit OPEN: UYUNI unreachable, skipping call")
        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.threshold:
                self.state = "OPEN"
                logger.error(f"Circuit OPEN after {self.failures} failures: {e}")
            raise
```

### 4.7 Configurazione SSL/TLS per XML-RPC in produzione

L'attuale configurazione `UYUNI_VERIFY_SSL=false` è accettabile solo in ambiente di test.

```bash
# Produzione: distribuire il certificato CA di UYUNI sul client
# Recuperare CA dal container server
podman cp uyuni-server:/etc/pki/trust/anchors/uyuni-ca.crt \
  /tmp/uyuni-ca.crt

# Sul VM SPM Orchestrator
cp /tmp/uyuni-ca.crt /usr/local/share/ca-certificates/uyuni-ca.crt
update-ca-certificates

# Aggiornare .env
UYUNI_VERIFY_SSL=true
UYUNI_CA_CERT=/usr/local/share/ca-certificates/uyuni-ca.crt
```

In un contesto HA con failover su nuovo IP/VM, il certificato SSL resta valido se:
1. Il FQDN non cambia (gestito da Azure Private DNS)
2. Il certificato è stato emesso per il FQDN (non per l'IP)

---

## 5. Matrice di confronto

| | **A1** | **A2** | **B1** | **B2** |
|---|---|---|---|---|
| **Client supportati** | < 500 | < 500 | 500–3.000 | > 3.000 |
| **SLA** | Best-effort | Strict | Best-effort | Strict |
| **RTO server** | 30-60 min | 10-12 min | 45-60 min | 10-15 min |
| **RPO server** | 24h / 6h | < 1 min | 24h | < 1 min |
| **RTO proxy** | 5-10 min (manuale) | 2-3 min (DNS) | 2-3 min | 2-3 min |
| **Architettura server** | Single + backup | Active/Passive | Single tuned | Hub multi-server |
| **DB HA** | Backup giornaliero | PgSQL streaming | Backup giornaliero | PgSQL per peripheral |
| **Storage** | Dischi locali LVM | Azure Files NFS | Dischi locali LVM | Azure Files NFS |
| **N. proxy** | 2 (AZ1+AZ2) | 2 (AZ1+AZ2) | 3-4 | 2 per peripheral |
| **Proxy HA** | DNS swap manuale | DNS swap manuale | DNS swap manuale | DNS swap manuale |
| **VM aggiuntive** | +1 proxy | +1 server +1 proxy | +2-3 proxy | +3-4 server +proxy |
| **Componenti Azure add.** | DNS, Files, Backup | DNS, Files NFS, Backup | DNS, Files, Backup | DNS, Files NFS, Backup, hub |
| **Complessità operativa** | Bassa | Media | Media | Alta |
| **XML-RPC resilienza** | Re-login post-restore | Re-login post-failover | Re-login post-restore | Re-login per peripheral |

---

## 6. Roadmap implementativa

### Priorità 1 — Obbligatorio per qualsiasi scenario (1-2 settimane)

```
□ Azure Private DNS Zone uyuni.internal
  - Crea zona privata collegata alla VNet ASL0603-spoke10
  - Aggiungi record: uyuni-server, uyuni-proxy, uyuni-proxy-2
  - TTL: 60 secondi per tutti i record critici
  - Verifica che i container Podman risolvano via DNS (non /etc/hosts)

□ mgradm backup create schedulato
  - Mount Azure Files come /mnt/uyuni-backup
  - Cron: 0 2 * * * mgradm backup create --output /mnt/uyuni-backup/$(date +%Y%m%d)
  - Retention: 7 backup giornalieri + 4 settimanali
  - Test di restore documentato e verificato
  - Alerting se il backup non viene prodotto entro le 06:00
```

### Priorità 2 — HA proxy (1 settimana)

```
□ Deploy Proxy #2 su AZ2
  - Standard B4ms (4 vCPU, 16 GB RAM)
  - Disco cache 128 GB Premium SSD
  - Procedura di installazione identica a proxy #1
  - Distribuzione client: ~50% per proxy

□ Documentare procedura di failover proxy
  - Script Salt per bulk-reassign client
  - Runbook testato e approvato
```

### Priorità 3 — Server HA (2-4 settimane, in base allo scenario)

```
□ Scenario A2:
  - Deploy VM standby AZ2 (D8as_v5)
  - Configurazione PostgreSQL streaming replication
  - Mount Azure Files NFS per /manager_storage
  - Test di failover in ambiente non-produttivo
  - Documentare e testare procedura completa
  - RTO target verificato: < 15 min

□ Scenario B (se scale > 1.000 client):
  - Tuning JVM/PostgreSQL del server esistente prima di aggiungere hardware
  - Valutare soglia effettiva di saturazione con carico reale
  - Pianificare Hub architecture solo se necessario
```

### Priorità 4 — XML-RPC hardening (in parallelo con P2/P3)

```
□ SSL verify abilitato (UYUNI_VERIFY_SSL=true) — distribuzione CA cert
□ Circuit breaker pattern in UyuniSession/_wait_action()
□ Jitter sul poller per distribuire il carico
□ Tuning Tomcat (maxThreads=300, message_queue_thread_pool_size=50)
□ Monitoraggio latenza XML-RPC con Azure Monitor
```

---

## 7. Riferimenti

| Documento | URL |
|---|---|
| UYUNI Large Deployments Overview | https://www.uyuni-project.org/uyuni-docs/en/uyuni/specialized-guides/large-deployments/overview.html |
| UYUNI Large Deployments — Tuning | https://www.uyuni-project.org/uyuni-docs/en/uyuni/specialized-guides/large-deployments/tuning.html |
| UYUNI Large Deployments — Hardware | https://www.uyuni-project.org/uyuni-docs/en/uyuni/specialized-guides/large-deployments/hardware-reqs.html |
| UYUNI Backup and Restore | https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/backup-restore.html |
| SUSE Manager 5.0 — Hub Multi-Server | https://documentation.suse.com/suma/5.0/en/suse-manager/specialized-guides/large-deployments/hub-multi-server.html |
| SUSE Manager 5.0 — ISS v2 | https://documentation.suse.com/suma/5.0/en/suse-manager/administration/iss_v2.html |
| SUSE Manager 5.0 — Proxy Setup | https://documentation.suse.com/suma/5.0/en/suse-manager/installation-and-upgrade/uyuni-proxy-setup.html |
| SUSE HA Extension | https://www.suse.com/products/highavailability/ |
| SLE HA — NFS con DRBD e Pacemaker | https://documentation.suse.com/sle-ha/15-SP7/single-html/SLE-HA-nfs-storage/article-nfs-storage.html |
| Azure — Pacemaker su SUSE | https://learn.microsoft.com/en-us/azure/sap/workloads/high-availability-guide-suse-pacemaker |
| mgradm Server Administration | https://deepwiki.com/uyuni-project/uyuni-tools/2.1-mgradm-server-administration |
| PostgreSQL Streaming Replication | https://www.postgresql.org/docs/current/warm-standby.html |

---

*Documento generato con Claude Code · Security Patch Manager Project · Febbraio 2026*
