## Uyuni Server — Requisiti Hardware

Il server Uyuni è il componente centrale dell'infrastruttura. Ospita il Salt Master, Taskomatic (job scheduler), Tomcat (Web UI), Apache HTTPD (repository), Cobbler (provisioning PXE) e il database PostgreSQL.
###  Requisiti Minimi e Raccomandati

| Risorsa                 | Minimo Assoluto                             | Produzione Raccomandata                                        |
| ----------------------- | ------------------------------------------- | -------------------------------------------------------------- |
| **CPU**                 | 4 core dedicati 64-bit x86-64               | 8+ core recenti x86-64                                         |
| **RAM**                 | 16 GB                                       | 32 GB                                                          |
| **Partizione root `/`** | 40 GB                                       | 40 GB                                                          |
| **Swap**                | 3 GB (SUMA 4.3) / 8-12 GB (containerizzato) | Swap file-based raccomandato                                   |
| **Storage Repository**  | 100-150 GB baseline                         | Scala per numero di prodotti (vedi sezione 3)                  |
| **Storage PostgreSQL**  | 50 GB                                       | Sul dispositivo di storage più veloce disponibile (SSD locale) |
| **Cache `/var/cache`**  | 10 GB                                       | Scala con il numero di prodotti gestiti                        |

### 1.2 Limite Architetturale

> **Il server singolo non deve superare 10.000 client.** Oltre questa soglia è obbligatoria un'architettura Hub con server periferici multipli. SUSE raccomanda un engagement consulenziale per deployment di questa scala.

### 1.3 Architetture CPU Supportate

- x86-64 (raccomandata per performance)
- ARM (aarch64)
- IBM POWER (ppc64le)
- IBM Z (s390x)

---

## 2. Uyuni Proxy — Requisiti Hardware

Il proxy agisce come nodo intermedio tra client e server. Fornisce cache locale dei pacchetti (Squid), broker delle comunicazioni Salt, serving HTTP/HTTPS dei repository, tunneling SSH per client push-based e TFTP per PXE boot.

### 2.1 Requisiti Minimi e Raccomandati

| Risorsa | Minimo | Produzione Raccomandata |
|---------|--------|-------------------------|
| **CPU** | 2 core dedicati 64-bit | 2+ core moderni |
| **RAM** | 2 GB | 8 GB (16 GB per deployment grandi) |
| **Partizione root `/`** | 40 GB | 40 GB |
| **Storage `/srv`** | 100 GB | Uguale alla dimensione del repository sul server |
| **Cache Squid `/var/cache`** | 100 GB | 60-80% dello spazio disco disponibile |

### 2.2 Capacita Dichiarata

> **Un singolo proxy gestisce 500 - 1.000 client**, in funzione della banda di rete disponibile. Non esiste un hard limit, ma superare 1.000 client per proxy degrada le performance di distribuzione pacchetti.

### 2.3 Ottimizzazione Cache

La cache Squid del proxy dovrebbe idealmente eguagliare la dimensione di `/var/spacewalk` sul server. In questo modo, dopo la prima sincronizzazione completa, tutto il traffico successivo dei client viene servito dalla cache locale senza coinvolgere il server.

Per deployment containerizzati: configurare la cache Squid al massimo **80% dello spazio disponibile** sul volume dedicato.

### 2.4 Componenti Containerizzati del Proxy

In Uyuni 2025.10+ il proxy viene deployato come Pod Podman con 5 container:

| Container | Funzione | Porte |
|-----------|----------|-------|
| `proxy-httpd` | Serving HTTP/HTTPS repository e forwarding | 80, 443 |
| `proxy-salt-broker` | Broker eventi Salt tra client e server | 4505, 4506 |
| `proxy-squid` | Cache proxy pacchetti | Interno |
| `proxy-ssh` | Tunneling SSH per client push-based | 8022 |
| `proxy-tftpd` | TFTP per PXE boot provisioning | 69 |

---

## 3. Storage Repository — Scaling per Prodotto e Canale

Lo storage dei repository e il fattore di scala piu direttamente correlato al numero e alla tipologia di sistemi operativi gestiti. Ogni prodotto/canale sincronizzato consuma spazio in modo significativo.

### 3.1 Spazio Disco per Tipo di Prodotto

| Tipo di Prodotto | Spazio Disco per Prodotto | Cache Aggiuntiva |
|------------------|--------------------------|------------------|
| Ogni prodotto SUSE + Package Hub | **~50 GB** | +100 MB |
| Ogni prodotto Red Hat | **~360 GB** | +1 GB |

### 3.2 Esempi di Dimensionamento

| Scenario | Canali Tipici | Storage Repo Necessario |
|----------|---------------|------------------------|
| Solo Ubuntu (main, universe, security, updates) | ~17 canali | 100-150 GB |
| Ubuntu + RHEL 9 | + canali RH | 400-500 GB |
| Ubuntu + RHEL + SLES | + canali SUSE | 550-700 GB |
| Multi-OS completo (Ubuntu, RHEL, SLES, Debian) | Tutti | 1-2 TB |

### 3.3 Vincoli Critici

- **La sincronizzazione dei repository FALLISCE se lo spazio disco si esaurisce.** Non esiste graceful degradation o sync parziale.
- **Filesystem raccomandato:** XFS per tutti i volumi.
- **NFS e esplicitamente non supportato** per storage Cobbler e PostgreSQL (rischio perdita dati, incompatibilita con SELinux).
- I volumi repository, database e sistema operativo **devono risiedere su dispositivi di storage separati** per prevenire degradazione delle performance e perdita dati incrociata.

---

## 4. Database PostgreSQL — Requisiti e Tuning

### 4.1 Vincoli Architetturali

- PostgreSQL e l'**unico database supportato** (no MySQL, MariaDB, Oracle, SQL Server)
- Database remoti **non sono supportati** — PostgreSQL deve risiedere sulla stessa macchina del server Uyuni (o nello stesso pod containerizzato)
- Storage NFS per PostgreSQL **non e supportato**
- **Deve risiedere sul dispositivo di storage piu veloce disponibile** — SSD locale obbligatorio, RAID-0 per deployment grandi
- Partizione minima dedicata: **50 GB**

### 4.2 Parametri di Tuning per Scaling

| Parametro PostgreSQL | Default | Range Raccomandato per Scale |
|---------------------|---------|------------------------------|
| `shared_buffers` | 25% RAM | **25-40% RAM** |
| `max_connections` | 400 | Dipende dal workload |
| `work_mem` | Varia | **2-20 MB** |
| `effective_cache_size` | Varia | **75% RAM totale** |

| Parametro Applicativo | Default | Range Raccomandato per Scale |
|----------------------|---------|------------------------------|
| `hibernate.c3p0.max_size` (connection pool) | 20 | **100-200** |

### 4.3 Considerazioni sulle Performance

- Con l'aumento degli endpoint, il numero di query al database cresce linearmente (stato dei sistemi, errata applicabili, inventario pacchetti)
- Le operazioni piu pesanti sono: `errata.listAffectedSystems`, `system.listLatestUpgradablePackages`, e le query di matching CVE-pacchetto
- Per deployment > 1.000 client, il database diventa tipicamente il primo bottleneck se non posizionato su SSD dedicato

---

## 5. Application Tuning — Parametri che Scalano con gli Endpoint

Questi parametri determinano quante risorse il server Uyuni alloca ai vari sotto-sistemi. Devono essere incrementati proporzionalmente al numero di endpoint gestiti.

### 5.1 Tomcat (Web UI e API XML-RPC)

| Parametro | Default | Large Scale (>1.000 client) |
|-----------|---------|------------------------------|
| **`-Xmx`** (heap Java max) | 1 GB | **4-8 GB** |

### 5.2 Java Application (Spacewalk)

| Parametro | Default | Large Scale |
|-----------|---------|-------------|
| `java.message_queue_thread_pool_size` | 5 | **50-150** |
| `java.salt_batch_size` | 200 | **200-500** |
| `java.salt_event_thread_pool_size` | 8 | **20-100** |

### 5.3 Taskomatic (Job Scheduler)

| Parametro | Default | Large Scale |
|-----------|---------|-------------|
| `taskomatic.java.maxmemory` | 4096 MB | **4096-16384 MB** |
| `org.quartz.threadPool.threadCount` | 20 | **20-200** |

### 5.4 Apache HTTPD

| Parametro | Default | Large Scale |
|-----------|---------|-------------|
| `MaxRequestWorkers` | 150 | **150-500** |

### 5.5 Salt Master

| Parametro | Default | Large Scale |
|-----------|---------|-------------|
| `worker_threads` | 8 | **8-32** |

> **Nota:** Ogni Salt worker thread consuma ~70 MB di RAM. Con 32 thread = ~2.2 GB solo per Salt.

### 5.6 Impatto Cumulativo sulla RAM

La RAM necessaria al server e la somma di tutti i sotto-sistemi:

| Componente | Consumo Tipico (Small) | Consumo Tipico (Large) |
|------------|----------------------|----------------------|
| Salt Master (worker threads) | ~560 MB (8 threads) | ~2.2 GB (32 threads) |
| Tomcat (heap) | 1 GB | 4-8 GB |
| Taskomatic (heap) | 4 GB | 4-16 GB |
| PostgreSQL (shared_buffers) | 4 GB (25% di 16 GB) | 16-25 GB (25-40% di 64 GB) |
| Sistema operativo + overhead | ~2 GB | ~3 GB |
| **Totale stimato** | **~11.5 GB** | **~29-54 GB** |

Questo spiega perche la documentazione raccomanda **64+ GB RAM per migliaia di client**: tutti i sotto-sistemi competono per la memoria.

### 5.7 Job Schedulati da Disabilitare per Deployment Grandi

Per ridurre il carico computazionale su deployment con molti endpoint, la documentazione raccomanda di disabilitare i seguenti job non essenziali:

| Job | Frequenza Default | Motivo Disabilitazione |
|-----|-------------------|------------------------|
| `compare-configs-default` | Giornaliero | Confronto configurazioni — pesante su larga scala |
| `cobbler-sync-default` | Orario | Sync Cobbler — inutile se non si usa PXE attivamente |
| `gatherer-matcher-default` | Giornaliero | Gatherer/Subscription matcher — rilevante solo con licenze SUSE |

---

## 6. Rete — Requisiti Porte e Banda

### 6.1 Porte Server (Inbound)

| Porta | Protocollo | Scopo | Sorgente |
|-------|------------|-------|----------|
| 67 | TCP/UDP | DHCP | Client (se PXE) |
| 69 | TCP/UDP | TFTP (PXE boot) | Client (se PXE) |
| 80 | TCP | HTTP bootstrap repository | Client, Proxy |
| 443 | TCP | HTTPS — Web UI, API XML-RPC, comunicazioni client | Client, Proxy, Admin |
| 4505 | TCP | Salt — canale comandi (publish) | Client, Proxy |
| 4506 | TCP | Salt — canale risultati (return) | Client, Proxy |
| 5432 | TCP | PostgreSQL reporting DB | Solo accesso interno/monitoring |
| 5556-5557 | TCP | Prometheus JMX exporter | Monitoring |
| 9100 | TCP | Prometheus node exporter | Monitoring |
| 9187 | TCP | Prometheus PostgreSQL exporter | Monitoring |
| 9800 | TCP | Prometheus Taskomatic exporter | Monitoring |
| 25151 | TCP | Cobbler provisioning | Interno |

### 6.2 Porte Proxy (Inbound)

| Porta | Protocollo | Scopo | Sorgente |
|-------|------------|-------|----------|
| 22 | TCP | SSH amministrativo | Admin |
| 67 | TCP/UDP | DHCP | Client (se PXE) |
| 69 | TCP/UDP | TFTP (PXE boot) | Client (se PXE) |
| 443 | TCP | HTTPS — repository, comunicazioni | Client, Server |
| 4505 | TCP | Salt — canale comandi | Client |
| 4506 | TCP | Salt — canale risultati | Client |
| 8022 | TCP | SSH push per client push-based | Client |

### 6.3 Porte Client (Outbound)

| Porta | Protocollo | Destinazione | Scopo |
|-------|------------|--------------|-------|
| 80 | TCP | Proxy/Server | HTTP bootstrap |
| 443 | TCP | Proxy/Server | HTTPS pacchetti e comunicazioni |
| 4505 | TCP | Proxy/Server | Salt publish |
| 4506 | TCP | Proxy/Server | Salt return |

### 6.4 URL Esterni Richiesti dal Server

Il server necessita di accesso HTTPS in uscita verso:

| URL | Scopo |
|-----|-------|
| `scc.suse.com` | SUSE Customer Center (licenze e registrazione) |
| `updates.suse.com` | Repository aggiornamenti SUSE |
| `installer-updates.suse.com` | Aggiornamenti installer |
| `registry.suse.com` | Registry container SUSE |
| `registry-storage.suse.com` | Storage registry container |
| `registry.opensuse.org` | Registry container Uyuni (per deployment open source) |

### 6.5 Banda — Formula di Dimensionamento

La documentazione ufficiale fornisce la seguente formula per stimare il tempo di distribuzione aggiornamenti:

```
Dimensione_aggiornamenti (MB) x N_client / Velocita_download (MB/s) / 60 = Tempo (minuti)
```

**Esempio dalla documentazione:** 400 MB di aggiornamenti distribuiti a 3.000 client su connessione 1 Gbps = **~169 minuti**.

### 6.6 Banda Consumata da Client Pre-Onboarding

I client con Salt key in stato "pending" (non ancora accettati) consumano banda costante:

> **~2.5 Kb/s per client** in stato pending.

| Client Pending | Banda Inbound Costante |
|----------------|----------------------|
| 100 | ~250 Kb/s |
| 500 | ~1.25 Mb/s |
| 1.000 | ~2.5 Mb/s |
| 5.000 | ~12.5 Mb/s |
| 10.000 | ~25 Mb/s |

Questo traffico cessa una volta che le key vengono accettate e l'onboarding completa.

---

## 7. Onboarding — Rate e Vincoli Operativi

### 7.1 Rate di Onboarding Sicuro

| Operazione | Rate Dichiarato | Note |
|------------|-----------------|------|
| Accettazione key + registrazione | **1 client ogni 15 secondi** | Accettazione programmatica |
| Rate superiori | Creano backlog | Degradano performance e esauriscono risorse |

### 7.2 Tempo Stimato di Onboarding per Scala

| N. Client | Tempo Stimato (a 1 client/15s) |
|-----------|-------------------------------|
| 100 | ~25 minuti |
| 500 | ~2 ore |
| 1.000 | ~4 ore |
| 5.000 | ~21 ore |
| 10.000 | ~42 ore |

### 7.3 Vincoli Operativi

- **Cancellazione key Salt:** Deve avvenire in batch e durante orari di basso carico. La cancellazione di key causa spike CPU dovuto alla rotazione delle chiavi AES del Salt Master.
- **Non sovraccaricare l'onboarding:** Rate superiori a 1 client/15s creano code nei job Taskomatic che possono richiedere ore per smaltirsi.
- **Bootstrap via proxy:** Ogni proxy deve avere il proprio script di bootstrap generato con `mgr-bootstrap`. I client devono essere bootstrappati puntando al proxy, non direttamente al server.

---

## 8. Vincoli Architetturali Dichiarati

La documentazione ufficiale stabilisce i seguenti vincoli non negoziabili:

### 8.1 Architettura

| Vincolo | Dettaglio |
|---------|-----------|
| **Connessioni dirette client-server** | Da evitare in produzione — usare sempre i proxy |
| **Limite server singolo** | Massimo 10.000 client |
| **Oltre 10.000 client** | Architettura Hub obbligatoria |
| **PostgreSQL remoto** | Non supportato |
| **PostgreSQL su NFS** | Non supportato (rischio perdita dati) |
| **Cobbler su NFS** | Non supportato (incompatibilita SELinux) |

### 8.2 Storage

| Vincolo | Dettaglio |
|---------|-----------|
| **Filesystem raccomandato** | XFS per tutti i volumi |
| **Volumi separati** | Repository, database e OS su dispositivi distinti |
| **SSD obbligatorio** | Per il volume PostgreSQL in produzione |
| **RAID-0** | Raccomandato per PostgreSQL su deployment > 5.000 client |

### 8.3 Sistema Operativo e Kernel

| Vincolo | Dettaglio |
|---------|-----------|
| **`vm.swappiness`** | Impostare a 10-20 (riduce swap aggressivo) |
| **`elevator`** | `none` su VM virtualizzate |
| **Swap** | File-based raccomandato, 8-12 GB per deployment containerizzati |

### 8.4 Sicurezza (Produzione)

| Requisito | Dettaglio |
|-----------|-----------|
| **Certificati** | CA enterprise (non self-signed) |
| **Password policy** | 12+ caratteri, complessita obbligatoria |
| **Session timeout** | 900 secondi raccomandato |
| **RBAC** | Ruoli multipli: Admin, Channel Admin, System Admin, Viewer |
| **Audit logging** | Formato JSON raccomandato |

---

## 9. Tabella Riepilogativa — Risorse per Scala di Deployment

### 9.1 Server — Scaling

| Scala Endpoint | CPU | RAM | Storage DB | Storage Repo | Swap | Tuning |
|---------------|-----|-----|------------|--------------|------|--------|
| **< 100** | 4 core | 16 GB | 50 GB SSD | 150 GB | 3-8 GB | Default |
| **100 - 500** | 4-8 core | 16-32 GB | 50 GB SSD | 150-300 GB | 8-12 GB | Consigliato |
| **500 - 1.000** | 8 core | 32 GB | 50-100 GB SSD | 300-500 GB | 8-12 GB | Consigliato |
| **1.000 - 5.000** | 8+ core | 32-64 GB | 100+ GB SSD | 500 GB - 2 TB | 12 GB | Obbligatorio |
| **5.000 - 10.000** | 8+ core (top-tier) | 64+ GB | SSD RAID-0 | 2+ TB | 12+ GB | Tutti i parametri al massimo |
| **> 10.000** | Hub: multi-server | 64 GB+ per nodo | SSD RAID-0 per nodo | Per nodo | Per nodo | Architettura Hub |

### 9.2 Proxy — Scaling

| Scala Endpoint | N. Proxy | CPU/Proxy | RAM/Proxy | Cache Squid/Proxy | Note |
|---------------|----------|-----------|-----------|-------------------|------|
| **< 500** | 1 | 2 core | 2-8 GB | 100 GB | Configurazione minima |
| **500 - 1.000** | 1-2 | 2 core | 8 GB | >= repo server | Cache deve eguagliare repo |
| **1.000 - 2.000** | 2-4 | 2+ core | 8-16 GB | >= repo server | Distribuzione geografica se possibile |
| **2.000 - 5.000** | 4-10 | 2+ core | 8-16 GB | >= repo server | Load distribution obbligatoria |
| **5.000 - 10.000** | 10-20 | 2+ core | 16 GB | >= repo server | Proxy tier obbligatorio |

### 9.3 Rete — Scaling

| Scala Endpoint | Banda Minima Server-Proxy | Banda Minima Proxy-Client | Porte Firewall |
|---------------|--------------------------|--------------------------|----------------|
| **< 500** | 100 Mbps | 100 Mbps | Standard (vedi sezione 6) |
| **500 - 1.000** | 1 Gbps | 100 Mbps - 1 Gbps | Standard |
| **1.000 - 5.000** | 1 Gbps | 1 Gbps per proxy | Standard |
| **5.000 - 10.000** | 10 Gbps o multipli 1 Gbps | 1 Gbps per proxy | Standard |

---

## 10. Architettura Hub (oltre 10.000 Endpoint)

Per deployment che superano il limite di 10.000 client per server singolo, la documentazione SUSE Manager / Multi-Linux Manager definisce l'architettura Hub.

### 10.1 Concetto

L'architettura Hub prevede:
- **1 Hub Server** centrale che coordina i server periferici
- **N Server Periferici**, ciascuno con il proprio set di proxy e client (max 10.000 per server periferico)
- **Hub Online Synchronization** (introdotto in SUSE Multi-Linux Manager 5.1) per la sincronizzazione automatica dei contenuti tra nodi

### 10.2 Requisiti per Nodo Hub

Ogni server periferico nell'architettura Hub ha gli stessi requisiti di un server standalone (vedi sezione 1), dimensionati in base al numero di client che gestisce direttamente.

### 10.3 Quando Adottare l'Architettura Hub

| Condizione | Azione |
|------------|--------|
| > 10.000 client totali | Hub obbligatorio |
| Distribuzione multi-geografica con latenza elevata | Hub consigliato |
| Requisiti di isolamento tra business unit | Hub consigliato |
| Necessita di manutenzione indipendente per segmenti | Hub consigliato |

> **Nota:** SUSE raccomanda un engagement consulenziale dedicato per la progettazione e il deployment di architetture Hub.

---

## 11. Fonti Ufficiali

| Documento | URL |
|-----------|-----|
| Uyuni Hardware Requirements | https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/hardware-requirements.html |
| SUSE Manager 5.0 Hardware Requirements | https://documentation.suse.com/suma/5.0/en/suse-manager/installation-and-upgrade/hardware-requirements.html |
| SUSE Manager 4.3 Hardware Requirements | https://documentation.suse.com/suma/4.3/en/suse-manager/installation-and-upgrade/hardware-requirements.html |
| SUSE Multi-Linux Manager 5.1 Hardware Requirements | https://documentation.suse.com/multi-linux-manager/5.1/en/docs/installation-and-upgrade/hardware-requirements.html |
| Uyuni Large Deployment HW Requirements | https://www.uyuni-project.org/uyuni-docs/en/uyuni/specialized-guides/large-deployments/hardware-reqs.html |
| SUSE Manager Large Deployments Overview | https://documentation.suse.com/suma/4.3/en/suse-manager/specialized-guides/large-deployments/overview.html |
| SUSE Manager Tuning Large Scale | https://documentation.suse.com/suma/4.3/en/suse-manager/specialized-guides/large-deployments/tuning.html |
| SUSE Manager Operation Requirements | https://documentation.suse.com/suma/4.3/en/suse-manager/specialized-guides/large-deployments/operation-reqs.html |
| Uyuni Network Requirements | https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/network-requirements.html |
| SUSE Multi-Linux Manager 5.1 What's New | https://www.suse.com/c/suse-multi-linux-manager-5-1-whats-new/ |
