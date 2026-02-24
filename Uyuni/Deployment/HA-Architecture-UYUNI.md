# HA Architecture UYUNI — Documento di Progetto

*Security Patch Manager Project · Febbraio 2026*

---

## 1. Decisioni architetturali fondamentali

Questa sezione documenta le scelte progettuali adottate e le relative motivazioni. Ogni decisione è irreversibile nel senso che orienta tutto il design conseguente: modificarla richiederebbe un redesign significativo.

### 1.1 Vincoli imposti da UYUNI (non modificabili)

> **UYUNI non supporta clustering active/active nativo del server.**
> La documentazione ufficiale SUSE/UYUNI definisce un solo pattern HA supportato per il server: **Active/Passive** con failover manuale o semiautomatico. Lo stato dei client risiede interamente nel database PostgreSQL del server primario.

Il proxy UYUNI (`mgr-proxy`) è per definizione stateless: non ha database proprio, non ha Salt Master proprio. Lo stato di ogni client gestito via proxy vive sul server centrale. Questo è un vincolo architetturale che però diventa un vantaggio per l'HA del proxy.

### 1.2 Scelte progettuali adottate

| Decisione | Scelta adottata | Alternativa scartata | Motivazione |
|---|---|---|---|
| **SSL sul layer HAProxy** | Termination con re-encryption HTTPS al backend | Passthrough (Layer 4, TCP) | Il passthrough permette solo health check TCP (porta aperta = backend sano). La termination permette health check HTTP applicativo: rileva Tomcat bloccato anche quando Apache/porta 443 rimane aperta |
| **Tipo di proxy UYUNI** | Proxy puro (`mgr-proxy`, stateless) | Peripheral Server (stack UYUNI completo per org) | Con ~100 organizzazioni, il modello peripheral richiederebbe ~100 istanze PostgreSQL, ~100 Salt Master, ~100 stack completi ognuno con propria HA active/passive — operativamente insostenibile |
| **Layer HA per XML-RPC** | HAProxy farm infrastrutturale dedicato | Circuit breaker a livello applicativo (Python) | L'HA va risolta all'infrastruttura, non rattoppata nel codice. Un circuit breaker applicativo è un complemento, non la soluzione primaria. Rilevare un backend down e redirigere il traffico è compito del load balancer, non dell'applicazione client |
| **Separazione dei farm HAProxy** | Due farm distinti: uno per XML-RPC, uno per i proxy client | Un unico farm condiviso | Dominio di failure separato: un problema di configurazione su un farm non impatta l'altro. Scaling indipendente. Traffic type diversi (management API vs Salt/content client) |
| **Modalità proxy pair** | Active/Passive per ogni coppia di proxy | Active/Active | Il Salt broker mantiene sessioni TCP long-lived (event bus Salt minion↔master). In active/active, connessioni consecutive dello stesso minion potrebbero finire su nodi diversi, spezzando la sessione Salt. In active/passive il failover causa un solo TCP reset: il minion si riconnette automaticamente in 30-60 secondi |
| **VIP per HAProxy in Azure** | Azure Internal Load Balancer Standard ZRS | Keepalived/VRRP | In Azure il multicast è bloccato: Keepalived in modalità multicast non funziona. La soluzione Azure nativa per VIP floating è l'ILB Standard, che gestisce la disponibilità del VIP tra le zone e non richiede configurazione VRRP |
| **Identità del proxy** | L'identità è il VIP (FQDN del load balancer), non la VM sottostante | Identità legata alla singola VM | UYUNI registra il proxy tramite FQDN. Se l'FQDN è quello del VIP (es. `proxy-orgA.uyuni.internal`) e entrambi i nodi del pair sono configurati identicamente (stessi certificati, stessa configurazione mgr-proxy), il failover è trasparente a UYUNI e ai client |

---

## 2. Topologia complessiva

```
                    ┌──────────────────────────────────────────────────────────────┐
                    │                  UYUNI SERVER — Active/Passive               │
                    │                                                              │
                    │   Primary  AZ1  10.172.2.17        Standby  AZ2  10.172.2.50│
                    │   ├── uyuni-server (UP)             ├── uyuni-server (STOP)  │
                    │   └── uyuni-db (PostgreSQL PRIMARY) └── uyuni-db (HOT STDBY) │
                    │                    ◄── Streaming Replication (TCP 5432) ───► │
                    │                                                              │
                    │   /manager_storage ──► Azure Files NFS Premium ZRS          │
                    │                        (mount su entrambi i nodi)           │
                    └────────────────────────────┬─────────────────────────────────┘
                                                 │ HTTPS :443
                                                 │ (backend XML-RPC)
                    ┌────────────────────────────▼─────────────────────────────────┐
                    │           HAProxy Farm XML-RPC  (Farm A)                     │
                    │                                                              │
                    │   Azure ILB Standard ZRS                                    │
                    │   VIP: xmlrpc.uyuni.internal  →  :443                       │
                    │           │                                                  │
                    │    ┌──────┴──────┐                                           │
                    │    ▼             ▼                                           │
                    │  HAProxy-A1    HAProxy-A2      (entrambi active)             │
                    │  AZ1           AZ2                                           │
                    │    └──────┬──────┘                                           │
                    │           │ SSL Termination + HTTPS re-encryption            │
                    │           │ Health check: HTTP GET /rpc/api ogni 3s          │
                    │           │                                                  │
                    │    Primary  weight=100    Standby  backup (fallback auto)    │
                    └───────────────────────────────────────────────────────────────┘

  Qualsiasi client XML-RPC → xmlrpc.uyuni.internal:443
  (SPM Orchestrator, tool amministrativi, automazioni)

                    ┌──────────────────────────────────────────────────────────────┐
                    │           HAProxy Farm Proxy  (Farm B)                       │
                    │                                                              │
                    │   Azure ILB Standard ZRS                                    │
                    │   VIP pool: un IP per organizzazione                        │
                    │   proxy-orgA.uyuni.internal → VIP-A                         │
                    │   proxy-orgB.uyuni.internal → VIP-B                         │
                    │   proxy-orgN.uyuni.internal → VIP-N  (~100 org)             │
                    │           │                                                  │
                    │    ┌──────┴──────┐                                           │
                    │    ▼             ▼                                           │
                    │  HAProxy-B1    HAProxy-B2      (entrambi active)             │
                    │  AZ1           AZ2                                           │
                    │    └──────┬──────┘                                           │
                    │           │                                                  │
                    │     Per ogni org:                                            │
                    │     :443  → SSL Termination + re-encrypt → Proxy-OrgN active │
                    │     :4505 → TCP mode → Proxy-OrgN active                    │
                    │     :4506 → TCP mode → Proxy-OrgN active                    │
                    │     Fallback automatico a Proxy-OrgN standby                │
                    └──────────────────────────────────────────────────────────────┘

  Per ogni organizzazione (es. Org-A):
  ┌─────────────────────────────────────┐
  │  Proxy-OrgA-1  AZ1   ACTIVE         │  ← riceve tutto il traffico
  │  Proxy-OrgA-2  AZ2   PASSIVE        │  ← in standby, attivato in < 10s
  └─────────────────────────────────────┘
          ↑
  Salt minions Org-A → proxy-orgA.uyuni.internal
```

---

## 3. UYUNI Server — Active/Passive HA

### 3.1 Architettura

Il server UYUNI è il componente con il vincolo architetturale più rigido: non può essere attivo su più nodi contemporaneamente. Il pattern adottato è quindi **active/passive con warm standby**:

- **Primary (AZ1)**: server UYUNI attivo, database PostgreSQL primario
- **Standby (AZ2)**: server UYUNI fermo (`mgradm stop`), database PostgreSQL in hot standby con streaming replication live

Lo standby è "warm" nel senso che il database è sincronizzato in tempo reale e pronto alla promozione, ma il processo applicativo UYUNI (Tomcat, Taskomatic, Salt Master) rimane fermo fino al failover. Questo è necessario perché UYUNI non è progettato per avere due istanze attive sullo stesso database.

**RPO**: < 1 secondo con `synchronous_commit = on` | < 1 minuto con `synchronous_commit = local`
**RTO**: 10-12 minuti con operatore disponibile (procedura documentata nella sezione 8.1)

### 3.2 PostgreSQL Streaming Replication

La replication è configurata a livello di container `uyuni-db`. Il parametro `synchronous_commit` è una scelta di bilanciamento tra RPO e performance:

- `synchronous_commit = on`: il commit ritorna al client solo quando la scrittura è confermata sul WAL standby → RPO=0, impatto ~15% sulle performance di scrittura
- `synchronous_commit = local`: il commit ritorna al client dopo scrittura locale → RPO < 1s, nessun impatto performance

Per un sistema di patch management la scelta raccomandata è `synchronous_commit = local`: un secondo di transazioni perse in caso di failure è accettabile, e l'impatto performance su `synchronous_commit = on` degrada l'esperienza operativa quotidiana.

**Sul container `uyuni-db` PRIMARY** — `/var/lib/pgsql/data/postgresql.conf`:

```ini
wal_level = replica
max_wal_senders = 3
wal_keep_size = 1GB
hot_standby = on
synchronous_commit = local
```

**Sul container `uyuni-db` PRIMARY** — `/var/lib/pgsql/data/pg_hba.conf`:

```
host  replication  replicator  10.172.2.50/32  scram-sha-256
```

**Sul container `uyuni-db` STANDBY** — inizializzazione replica (operazione una tantum):

```bash
# Eseguire sul nodo standby, dentro il container uyuni-db
pg_basebackup -h 10.172.2.17 -U replicator \
  -D /var/lib/pgsql/data \
  -P -Xs -R --checkpoint=fast

# Il flag -R crea automaticamente standby.signal e postgresql.auto.conf
# con primary_conninfo già configurato. La replica parte subito.
```

**Verifica stato replication** (da eseguire sul primary):

```bash
podman exec uyuni-db psql -U spacewalk -c \
  "SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn
   FROM pg_stat_replication;"
```

### 3.3 Storage `/manager_storage` — Azure Files NFS Premium ZRS

Il repository dei pacchetti (`/manager_storage`) contiene centinaia di GB di dati binari (RPM, DEB, metadati canali). Non è replicabile via PostgreSQL. La soluzione è uno storage condiviso montato su entrambi i nodi.

**Scelta**: Azure Files NFS Premium con ridondanza ZRS (Zone-Redundant Storage). Il mount è presente su entrambi i nodi (primary e standby). In failover, il nodo standby trova lo storage già montato e aggiornato — non è necessario alcun trasferimento dati.

```
# /etc/fstab su entrambi i nodi (primary e standby)
myaccount.file.core.windows.net:/myaccount/uyuni-repo \
  /manager_storage nfs \
  vers=4.1,sec=sys,nofail,_netdev,rsize=1048576,wsize=1048576 0 0
```

> **Nota**: Azure Files NFS Premium ha latenza ~1-2 ms. È accettabile per repository di pacchetti (letture sequenziali grandi). **Non usare per PostgreSQL**: la latenza NFS degrada significativamente le performance del database. Il database rimane su disco locale con streaming replication.

> **Sicurezza**: Azure Files NFS è accessibile solo tramite Private Endpoint nella VNet. Non esposto su internet.

### 3.4 Tuning PostgreSQL

Il tuning è necessario per garantire le performance del server primario sotto carico operativo normale. I parametri seguono le raccomandazioni per hardware D8as_v5 (8 vCPU, 32 GB RAM).

**`/var/lib/pgsql/data/postgresql.conf`** (dentro container `uyuni-db`):

```ini
# Memoria
shared_buffers = 8GB                  # 25% RAM
effective_cache_size = 24GB           # 75% RAM
work_mem = 64MB                       # per sessione — monitorare OOM
maintenance_work_mem = 1GB

# Connessioni
max_connections = 100                 # coordinare con pool Hibernate (vedi sotto)

# WAL e checkpoint
max_wal_size = 4GB
checkpoint_completion_target = 0.9

# Storage SSD
random_page_cost = 1.1                # SSD Azure Premium (default 4.0 per HDD)
effective_io_concurrency = 200        # SSD NVMe
```

**`/etc/rhn/rhn.conf`** (dentro container `uyuni-server`) — pool Hibernate:

```ini
hibernate.c3p0.max_size = 50          # deve essere < max_connections - overhead
hibernate.c3p0.min_size = 5
hibernate.c3p0.timeout = 300
hibernate.c3p0.acquire_increment = 2
java.message_queue_thread_pool_size = 50
java.salt_event_thread_pool_size = 8
```

> **Regola di coerenza**: `max_connections PostgreSQL` > `hibernate.c3p0.max_size` + `taskomatic connection pool` + overhead (~20).
> Con i valori sopra: 50 Hibernate + 20 Taskomatic + 20 overhead = `max_connections = 100`. Verificare con:
> ```bash
> mgrctl exec -- /usr/lib/susemanager/bin/susemanager-connection-check
> ```

---

## 4. HAProxy Farm XML-RPC (Farm A)

### 4.1 Architettura e razionale

Il Farm A gestisce **esclusivamente** il traffico verso l'API XML-RPC di UYUNI (`/rpc/api`). Qualsiasi client di management — SPM Orchestrator, tool amministrativi, script di automazione, futuri integratori — si connette sempre e solo al VIP di questo farm. Non conosce né deve conoscere l'indirizzo del server UYUNI sottostante.

Componenti:
- **Azure ILB Standard ZRS**: fornisce il VIP stabile (`xmlrpc.uyuni.internal`). L'ILB distribuisce tra i due nodi HAProxy con health probe TCP. Essendo Standard ZRS, sopravvive al failure di una singola Availability Zone.
- **2 nodi HAProxy** (AZ1 + AZ2): entrambi attivi, ricevono traffico dall'ILB. Entrambi mantengono la stessa configurazione backend e lo stesso stato delle health check. La perdita di un nodo HAProxy riduce la capacità del 50% ma non interrompe il servizio.
- **Backend UYUNI**: il server primario riceve tutto il traffico normale. Lo standby è configurato come `backup` — entra in gioco solo quando il primary supera il threshold di failure delle health check.

### 4.2 SSL Termination — motivazione e meccanismo

HAProxy termina la connessione TLS dal client, ispeziona il traffico HTTP, e stabilisce una nuova connessione HTTPS cifrata verso il backend UYUNI. Il client vede il certificato di HAProxy; il backend UYUNI vede la connessione proveniente da HAProxy.

**Perché non SSL passthrough**: con il passthrough, HAProxy vede solo un tunnel TCP cifrato. L'unico health check possibile è `TCP connect` (la porta 443 risponde?). Apache HTTPD sul server UYUNI risponde sulla porta 443 anche quando Tomcat (il processo che gestisce XML-RPC) è bloccato o in crash. In questo scenario, passthrough dichiarerebbe il backend sano mentre tutte le richieste XML-RPC fallirebbero con errori 502/503. Con SSL termination, HAProxy invia `GET /rpc/api` ogni 3 secondi e verifica la risposta HTTP: rileva immediatamente il Tomcat non funzionante.

**Certificato su HAProxy**: serve un certificato valido per `xmlrpc.uyuni.internal`. Può essere:
- Emesso dalla CA interna UYUNI (già presente, distribuita ai client via `uyuni-ca.crt`)
- O un certificato da una CA interna aziendale

Il certificato UYUNI originale rimane sul backend — HAProxy usa il proprio certificato lato client e verifica (o meno, su rete interna) il certificato del backend.

### 4.3 Health check applicativo

```
HAProxy → UYUNI backend ogni 3s:
  GET /rpc/api HTTP/1.1
  Host: uyuni-server.uyuni.internal

Risposta attesa: HTTP 200 con body contenente "UYUNI release X.Y"

Se 2 check consecutivi falliscono → backend marcato DOWN
Se 3 check consecutivi riescono → backend marcato UP (dopo failover)
```

Questo endpoint non richiede autenticazione e risponde con le informazioni di versione del server. È il canale più rapido per rilevare che il layer applicativo (Tomcat + XMLRPC handler) è funzionante, non solo che Apache è vivo.

### 4.4 Configurazione HAProxy Farm A

```haproxy
#------------------------------------------------------------
# Frontend: accetta connessioni HTTPS dai client
#------------------------------------------------------------
frontend xmlrpc_frontend
    bind *:443 ssl crt /etc/haproxy/certs/xmlrpc-uyuni-internal.pem
    mode http
    option forwardfor
    default_backend uyuni_xmlrpc_backend

#------------------------------------------------------------
# Backend: UYUNI primary + standby
# Il backup entra solo se il primary fallisce i health check
#------------------------------------------------------------
backend uyuni_xmlrpc_backend
    mode http
    balance roundrobin                        # un solo server attivo normalmente

    option httpchk GET /rpc/api
    http-check expect string "UYUNI release"

    default-server inter 3s fall 2 rise 3 ssl verify none

    server uyuni-primary 10.172.2.17:443 check weight 100
    server uyuni-standby 10.172.2.50:443 check weight 1 backup
```

> La direttiva `backup` in HAProxy significa: questo server è usato solo quando tutti i server non-backup sono down. Non è un weight=0, è proprio una modalità di standby gestita da HAProxy: appena il primary torna up, il traffico torna immediatamente su di esso.

---

## 5. HAProxy Farm Proxy (Farm B)

### 5.1 Architettura

Il Farm B gestisce il traffico dei Salt minion e il download dei pacchetti verso i proxy UYUNI. Gestisce ~100 organizzazioni, ciascuna con il proprio pair di proxy VM (active/passive).

Componenti:
- **Azure ILB Standard ZRS**: VIP pool — un indirizzo IP privato per organizzazione. Tutti gli IP sono frontend dell'ILB, tutti puntano agli stessi due nodi HAProxy come backend.
- **2 nodi HAProxy** (AZ1 + AZ2): entrambi attivi, stessa configurazione, gestiscono tutte le organizzazioni.
- **Per ogni organizzazione**: 2 VM proxy mgr-proxy (AZ1 = active, AZ2 = passive/backup).

### 5.2 Modello di indirizzamento per ~100 organizzazioni

Ogni organizzazione ha un indirizzo IP dedicato nel pool del Farm B. Questo è necessario perché il traffico Salt (porte 4505/4506) è TCP puro: non ha hostname nel payload, quindi l'unico modo per discriminare l'organizzazione di destinazione è l'IP di destinazione.

```
Azure Private DNS Zone: uyuni.internal

proxy-orgA.uyuni.internal → 10.172.3.1   (VIP Org-A)
proxy-orgB.uyuni.internal → 10.172.3.2   (VIP Org-B)
...
proxy-orgN.uyuni.internal → 10.172.3.100 (VIP Org-N)

Tutte queste IP sono frontend dell'Azure ILB Farm B.
Tutti puntano ai backend HAProxy-B1 (AZ1) e HAProxy-B2 (AZ2).
HAProxy distingue l'organizzazione dall'IP di destinazione (dst).
```

**Azure ILB Standard**: supporta fino a 600 regole di load balancing. Con 100 organizzazioni × 3 porte (443, 4505, 4506) = 300 regole — ampiamente nei limiti.

> Con un numero superiore a ~150-180 organizzazioni e 3 porte ciascuna si avvicina al limite dell'ILB. In quel caso: split in due ILB (Farm B-1 e Farm B-2) o consolidamento porte. Decisione da rivalutare quando necessario.

### 5.3 Active/Passive per pair — motivazione

Il Salt minion mantiene due connessioni TCP persistenti verso il proxy:
- Porta 4505 (publish port): il master invia comandi, il minion ascolta
- Porta 4506 (return port): il minion risponde, il master ascolta

Queste connessioni sono **long-lived** e stateful a livello Salt (il minion si autentica al Salt Master attraverso il proxy). Se HAProxy distribuisse le connessioni in round-robin tra due proxy VM (active/active), connessioni successive dello stesso minion potrebbero arrivare su VM diverse, ciascuna con il proprio stato del broker Salt — risultato: sessione corrotta o minion non raggiungibile.

Il modello active/passive è la soluzione corretta:
- Un solo proxy VM riceve tutto il traffico dell'organizzazione in condizioni normali
- Failover automatico all'altro nodo solo in caso di failure
- Il minion subisce un TCP reset e si riconnette al nodo ora attivo — comportamento nativo Salt, nessuna configurazione client richiesta

### 5.4 Identità del proxy: VIP ≠ VM

Questo è il principio architetturale che rende il failover trasparente a UYUNI.

UYUNI registra ogni proxy tramite il suo FQDN (`proxy-orgA.uyuni.internal`). I client (minion) sono configurati per connettersi a quel FQDN. Se il FQDN risolve al VIP del Farm B, e il VIP instrada al proxy VM attivo, allora:

- **UYUNI** vede un proxy con FQDN `proxy-orgA.uyuni.internal` → identità stabile
- **I minion** si connettono a `proxy-orgA.uyuni.internal` → endpoint stabile
- **Le VM proxy** (AZ1 e AZ2) sono entrambe configurate con lo stesso FQDN, gli stessi certificati `mgr-proxy`, la stessa configurazione UYUNI
- In failover, il nodo standby diventa active e presenta la stessa identità

**Requisito operativo**: i due nodi del pair devono essere configurati identicamente al momento del deploy. Qualsiasi modifica alla configurazione del proxy va applicata su entrambi i nodi in modo sincrono (o gestita via configuration management).

### 5.5 Modalità traffico per tipo di porta

Il proxy UYUNI espone tre tipologie di traffico con requisiti diversi:

| Porta | Protocollo | Modalità HAProxy | Health Check |
|---|---|---|---|
| 443 | HTTPS | SSL Termination + re-encrypt | HTTP `GET /pub/bootstrap/` (risponde 200/301) |
| 4505 | TCP (Salt PUB) | TCP mode (Layer 4) | TCP connect |
| 4506 | TCP (Salt RET) | TCP mode (Layer 4) | TCP connect |

**Porta 443**: SSL termination permette a HAProxy di verificare che il proxy HTTPD risponda correttamente, non solo che la porta sia aperta. Il certificato lato HAProxy è quello del VIP dell'organizzazione (`proxy-orgA.uyuni.internal`).

**Porte 4505/4506**: il protocollo Salt su queste porte usa ZeroMQ su TCP. Non è HTTP: HAProxy non può ispezionare il payload. TCP connect è il check più affidabile disponibile — verifica che il processo `salt-broker` stia effettivamente ascoltando.

### 5.6 Configurazione HAProxy Farm B (struttura per organizzazione)

```haproxy
#------------------------------------------------------------
# Frontend Org-A: VIP 10.172.3.1
#------------------------------------------------------------

frontend proxy_orgA_https
    bind 10.172.3.1:443 ssl crt /etc/haproxy/certs/proxy-orgA.pem
    mode http
    option forwardfor
    default_backend proxy_orgA_https_backend

frontend proxy_orgA_salt_pub
    bind 10.172.3.1:4505
    mode tcp
    default_backend proxy_orgA_salt_pub_backend

frontend proxy_orgA_salt_ret
    bind 10.172.3.1:4506
    mode tcp
    default_backend proxy_orgA_salt_ret_backend

#------------------------------------------------------------
# Backend Org-A: Active/Passive
# primary = nodo AZ1 (active)
# backup  = nodo AZ2 (passive, attivato automaticamente)
#------------------------------------------------------------

backend proxy_orgA_https_backend
    mode http
    option httpchk GET /pub/bootstrap/
    default-server inter 5s fall 2 rise 3 ssl verify none
    server proxy-orgA-1 10.172.X.Y:443 check           # AZ1 — active
    server proxy-orgA-2 10.172.X.Z:443 check backup    # AZ2 — passive

backend proxy_orgA_salt_pub_backend
    mode tcp
    default-server inter 5s fall 2 rise 3
    server proxy-orgA-1 10.172.X.Y:4505 check
    server proxy-orgA-2 10.172.X.Z:4505 check backup

backend proxy_orgA_salt_ret_backend
    mode tcp
    default-server inter 5s fall 2 rise 3
    server proxy-orgA-1 10.172.X.Y:4506 check
    server proxy-orgA-2 10.172.X.Z:4506 check backup

# Ripetere il blocco per ogni organizzazione (Org-B, Org-C, ... Org-N)
# L'aggiunta di una nuova organizzazione richiede solo questo blocco +
# 2 VM proxy VM + 1 record DNS + 1 frontend IP sull'Azure ILB
```

### 5.7 Scalabilità: aggiunta di una nuova organizzazione

Il design è stato pensato per essere esteso senza redesign. Aggiungere un'organizzazione richiede:

1. **2 VM proxy** (AZ1 + AZ2) con mgr-proxy configurato identicamente con FQDN del nuovo spoke
2. **1 indirizzo IP** dal pool VIP proxy (es. 10.172.3.N)
3. **1 record DNS** `proxy-orgN.uyuni.internal → 10.172.3.N` nella Private DNS Zone
4. **1 frontend IP** sull'Azure ILB Farm B puntato ai backend HAProxy-B1/B2
5. **1 blocco frontend+backend** in HAProxy (struttura identica all'esempio sopra)
6. Reload HAProxy (zero downtime): `systemctl reload haproxy`

Nessun riavvio dei nodi HAProxy, nessun impatto sulle organizzazioni esistenti.

---

## 6. DNS — Azure Private DNS Zone

### 6.1 Struttura zone

**Zona**: `uyuni.internal` — collegata alla VNet hub (accessibile da tutti gli spoke via VNet peering).

```
# Server UYUNI — punta al VIP del Farm A (HAProxy XML-RPC)
xmlrpc.uyuni.internal          A  →  VIP Farm A (es. 10.172.2.100)

# Proxy per organizzazioni — ognuno punta al proprio VIP nel Farm B
proxy-orgA.uyuni.internal      A  →  10.172.3.1
proxy-orgB.uyuni.internal      A  →  10.172.3.2
...
proxy-orgN.uyuni.internal      A  →  10.172.3.100

# Record interni (non esposti ai client) — per la replica PgSQL e mgmt
uyuni-primary.uyuni.internal   A  →  10.172.2.17
uyuni-standby.uyuni.internal   A  →  10.172.2.50
```

### 6.2 TTL e failover

**TTL raccomandato**: 60 secondi per tutti i record critici.

**Punto chiave**: in questa architettura, i record DNS **non cambiano mai** durante un failover. Il failover è gestito interamente da HAProxy tramite health check. Questo è un cambiamento radicale rispetto all'approccio precedente (che richiedeva aggiornamento manuale dei record DNS con Azure CLI).

L'unico caso in cui un record DNS viene modificato è l'aggiunta di una nuova organizzazione (nuovo record proxy-orgN) — operazione pianificata, non emergenziale.

---

## 7. Procedure operative

### 7.1 Failover UYUNI Server (RTO target: 10-12 min)

Il failover del server è semiautomatico: richiede un operatore. I passi seguenti assumono che il primary (10.172.2.17) sia effettivamente irraggiungibile.

```bash
# STEP 1 — Verificare che il primary sia irraggiungibile (2 min)
# Evitare failover per problemi di rete temporanei
ping 10.172.2.17
nc -zv 10.172.2.17 443
nc -zv 10.172.2.17 5432
# Se tutti e tre falliscono → procedere al failover

# STEP 2 — Promuovere PostgreSQL standby a primary (1 min)
podman exec uyuni-db pg_promote

# Verificare la promozione
podman exec uyuni-db psql -U spacewalk -c "SELECT pg_is_in_recovery();"
# Deve restituire: f  (false = è ora primary, non più standby)

# STEP 3 — Avviare UYUNI sul nodo standby (2-3 min)
mgradm start

# Verificare stato
mgradm status
mgrctl exec -- salt-run manage.up

# STEP 4 — HAProxy rileva automaticamente il nuovo backend attivo
# uyuni-standby (10.172.2.50) è già nel backend del Farm A come server backup
# Una volta che UYUNI è avviato, /rpc/api risponde → HAProxy lo attiva
# Nessuna modifica DNS richiesta
# Il traffico XML-RPC si sposta automaticamente sul nuovo primary in < 30s

# STEP 5 — Notificare il team e pianificare il ripristino del primary originale
```

> **Nota post-failover**: dopo il ripristino del primary originale, va ricostituita la streaming replication in senso inverso (il vecchio primary ora diventa standby). La procedura è simmetrica a quella di setup iniziale.

### 7.2 Failover Proxy (automatico, RTO < 10s)

Il failover dei proxy è **completamente automatico** tramite HAProxy. Nessun intervento umano richiesto.

```
Scenario: Proxy-OrgA-1 (AZ1) va offline

t=0s   HAProxy health check fallisce su Proxy-OrgA-1 (porta 443 o 4505/4506)
t=5s   Secondo health check fallisce (inter=5s, fall=2)
t=5s   HAProxy marca Proxy-OrgA-1 DOWN
t=5s   HAProxy attiva Proxy-OrgA-2 (nodo backup AZ2)
t=5-35s I minion di Org-A ricevono TCP reset → si riconnettono automaticamente
        a proxy-orgA.uyuni.internal → VIP → HAProxy → Proxy-OrgA-2

Nessun cambio DNS. Nessuna notifica manuale. Nessun intervento.

Quando Proxy-OrgA-1 torna online:
t=0s   Health check inizia a rispondere
t=15s  Terzo check consecutivo OK (rise=3) → HAProxy marca Proxy-OrgA-1 UP
t=15s  Proxy-OrgA-1 torna active, Proxy-OrgA-2 torna passive (backup)
       Il traffico torna sul nodo primario (AZ1) automaticamente
```

### 7.3 Aggiunta nuova organizzazione

```bash
# 1. Deploy 2 VM proxy con mgr-proxy configurato
#    FQDN: proxy-orgN.uyuni.internal
#    Registrazione in UYUNI come proxy (identità = FQDN del VIP)
#    VM1: AZ1, IP 10.172.X.Y
#    VM2: AZ2, IP 10.172.X.Z

# 2. Assegnare VIP dal pool Farm B
#    VIP: 10.172.3.N

# 3. Aggiungere record DNS
az network private-dns record-set a add-record \
  --resource-group <rg> \
  --zone-name uyuni.internal \
  --record-set-name proxy-orgN \
  --ipv4-address 10.172.3.N

# 4. Aggiungere frontend IP all'Azure ILB Farm B
#    (via Azure Portal o Terraform)

# 5. Aggiungere blocco frontend+backend in haproxy.cfg su HAProxy-B1 e HAProxy-B2
#    (identico alla struttura documentata in sezione 5.6)

# 6. Reload HAProxy senza downtime
systemctl reload haproxy   # su HAProxy-B1
systemctl reload haproxy   # su HAProxy-B2

# 7. Verificare health check
curl -sk https://proxy-orgN.uyuni.internal/pub/bootstrap/ | head -5
```

### 7.4 Health check manuale

```bash
# Verifica Farm A (XML-RPC) — deve rispondere con info versione
curl -sk https://xmlrpc.uyuni.internal/rpc/api \
  | grep -o 'UYUNI release [0-9.]*'

# Verifica backend attivo su HAProxy Farm A
# (dalla pagina stats HAProxy o via socket)
echo "show servers state uyuni_xmlrpc_backend" \
  | socat stdio /var/run/haproxy/admin.sock

# Verifica Salt broker raggiungibile su Org-A
nc -zv proxy-orgA.uyuni.internal 4505
nc -zv proxy-orgA.uyuni.internal 4506

# Verifica replication PostgreSQL
podman exec uyuni-db psql -U spacewalk -c \
  "SELECT client_addr, state, write_lag, flush_lag, replay_lag
   FROM pg_stat_replication;"

# Verifica minion connessi (da UYUNI server)
mgrctl exec -- salt-run manage.up
mgrctl exec -- salt-run manage.down
```

---

## 8. Componenti Azure richiesti

| Componente | Quantità | Scopo |
|---|---|---|
| **VM D8as_v5** (AZ1) | 1 | UYUNI Server Primary |
| **VM D8as_v5** (AZ2) | 1 | UYUNI Server Standby |
| **VM Standard_D2s_v5** (AZ1) | 1 | HAProxy Farm A — nodo 1 (XML-RPC) |
| **VM Standard_D2s_v5** (AZ2) | 1 | HAProxy Farm A — nodo 2 (XML-RPC) |
| **VM Standard_D4s_v5** (AZ1) | 1 | HAProxy Farm B — nodo 1 (Proxy) |
| **VM Standard_D4s_v5** (AZ2) | 1 | HAProxy Farm B — nodo 2 (Proxy) |
| **VM B4ms** (AZ1) × N org | ~100 | Proxy-OrgN-1 (active) per organizzazione |
| **VM B4ms** (AZ2) × N org | ~100 | Proxy-OrgN-2 (passive) per organizzazione |
| **Azure ILB Standard ZRS** | 2 | Farm A (1 VIP) + Farm B (~100 VIP) |
| **Azure Files Premium NFS ZRS** (500 GB+) | 1 | `/manager_storage` condiviso primary/standby |
| **Azure Private DNS Zone** `uyuni.internal` | 1 | Risoluzione FQDN per tutti i componenti |
| **Azure Backup** (policy standard) | 2 VM | Recovery VM-level per server primary e standby |
| **Dischi Premium SSD** da 128 GB | ~100 | Cache Squid per ogni proxy VM |

> **HAProxy Farm B sizing**: i nodi D4s_v5 gestiscono la tabella di routing per ~100 organizzazioni (300 regole di load balancing in memoria) e il forwarding TCP/HTTP per tutti i client. HAProxy è estremamente efficiente in memoria e CPU per questo tipo di workload. Rivalutare il sizing se il numero di organizzazioni supera 300.

---

## 9. Roadmap implementativa

### Fase 1 — Fondamenta (prerequisito tutto il resto)

```
□ Azure Private DNS Zone uyuni.internal
  - Collegata alla VNet hub (accessibile da tutti gli spoke)
  - Record iniziali: uyuni-primary, uyuni-standby, xmlrpc
  - TTL 60s su tutti i record critici
  - Verifica risoluzione dai container Podman (sostituisce /etc/hosts)

□ Azure Files NFS Premium ZRS
  - Storage account con tier Premium, NFS enabled, ZRS
  - Private Endpoint nella VNet
  - Mount su primary e standby in /etc/fstab
  - Test: scrittura da primary, lettura da standby
```

### Fase 2 — UYUNI Server HA

```
□ Deploy VM standby AZ2
  - openSUSE Leap 15.6, stessa versione UYUNI del primary
  - mgradm installato ma server fermo (mgradm stop)
  - /manager_storage montato su Azure Files

□ PostgreSQL Streaming Replication
  - Configurazione primary (postgresql.conf, pg_hba.conf)
  - pg_basebackup da standby
  - Verifica pg_stat_replication (lag < 1s)
  - Test failover in ambiente non produttivo
```

### Fase 3 — HAProxy Farm A (XML-RPC)

```
□ Deploy 2 VM HAProxy (AZ1 + AZ2)
  - HAProxy 2.8+ (versione LTS)
  - Certificato per xmlrpc.uyuni.internal

□ Azure ILB Standard ZRS
  - 1 frontend IP per Farm A
  - Backend: HAProxy-A1, HAProxy-A2
  - Health probe TCP:443

□ Configurazione HAProxy
  - Frontend HTTPS con SSL termination
  - Backend uyuni_xmlrpc_backend (primary + standby backup)
  - Health check HTTP GET /rpc/api

□ Test
  - Verifica health check applicativo (fermando Tomcat ma lasciando Apache)
  - Verifica failover automatico primary → standby
  - Verifica ritorno su primary al restore
```

### Fase 4 — HAProxy Farm B (Proxy)

```
□ Deploy 2 VM HAProxy (AZ1 + AZ2)
  - HAProxy 2.8+ (versione LTS)
  - Dimensionati per gestione ~100 org (D4s_v5)

□ Azure ILB Standard ZRS Farm B
  - Pool IP per organizzazioni (es. 10.172.3.0/24)

□ Prima organizzazione pilota (Org-A)
  - Deploy 2 VM proxy (AZ1 + AZ2) con mgr-proxy
  - Configurazione HAProxy (3 frontend × 2 nodi backend)
  - Record DNS proxy-orgA.uyuni.internal
  - Test failover automatico proxy

□ Procedura standardizzata per aggiunta organizzazioni
  - Checklist operativa documentata e testata
  - Automazione (Terraform/Ansible) per deploy proxy VM + config HAProxy
```

### Fase 5 — Operatività e monitoraggio

```
□ Test failover completo end-to-end
  - Failover server (primary → standby): verificare RTO < 12 min
  - Failover proxy: verificare RTO < 10s automatico
  - Failover HAProxy node: verificare continuità servizio

□ Azure Monitor
  - Alert su health probe HAProxy (Farm A e Farm B)
  - Alert su PostgreSQL replication lag > 10s
  - Alert su Azure Files NFS availability
  - Dashboard riassuntiva stato HA

□ Backup e DR
  - mgradm backup create schedulato ogni 6h → Azure Files
  - Test restore documentato e verificato
  - Runbook failover server approvato dal team
```

---

## 10. Riferimenti

| Documento | URL |
|---|---|
| UYUNI Proxy Setup | https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/proxy-setup.html |
| UYUNI Backup and Restore | https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/backup-restore.html |
| HAProxy 2.8 Configuration Manual | https://www.haproxy.org/download/2.8/doc/configuration.txt |
| PostgreSQL Streaming Replication | https://www.postgresql.org/docs/current/warm-standby.html |
| Azure ILB Standard — Load balancing rules | https://learn.microsoft.com/en-us/azure/load-balancer/load-balancer-overview |
| Azure Files NFS — Performance | https://learn.microsoft.com/en-us/azure/storage/files/files-nfs-protocol |
| Azure Private DNS Zone | https://learn.microsoft.com/en-us/azure/dns/private-dns-overview |
| mgradm Server Administration | https://deepwiki.com/uyuni-project/uyuni-tools/2.1-mgradm-server-administration |

---

*Documento aggiornato: Febbraio 2026 · Security Patch Manager Project*
