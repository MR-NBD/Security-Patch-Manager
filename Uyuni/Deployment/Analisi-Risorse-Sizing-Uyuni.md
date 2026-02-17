**Convenzione:** Ogni valore in questo documento è marcato con la sua origine:
- `[DOC]` = Dato esplicitamente dichiarato nella documentazione ufficiale
- `[CALC]` = Valore calcolato a partire da dati documentati, con formula visibile
- `[INTERP]` = Interpolazione ragionata tra due valori documentati — il ragionamento è esplicitato

---

## 1. Cosa Dichiara la Documentazione Ufficiale

La documentazione Uyuni/SUSE Manager fornisce solo **due punti fissi** di sizing per il server:

| Dato                          | Valore                                      | Fonte                                                                           |
| ----------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------- |
| Requisiti minimi server       | 4 CPU, 16 GB RAM, 50 GB DB, 100-150 GB repo | `[DOC]` Uyuni HW Requirements                                                   |
| Requisiti raccomandati server | 8+ CPU, 32 GB RAM                           | `[DOC]` SUSE Manager 5.0 HW Requirements                                        |
| Limite massimo server singolo | 10.000 client                               | `[DOC]` Large Deployments Overview                                              |
| RAM per "migliaia di client"  | 64 GB+                                      | `[DOC]` Uyuni HW Requirements — letteralmente "64 GB+ for thousands of clients" |
| Requisiti minimi proxy        | 2 CPU, 2 GB RAM                             | `[DOC]` Uyuni Large Deployment HW Reqs                                          |
| Requisiti raccomandati proxy  | 2+ CPU, 8 GB RAM (16 GB per grandi)         | `[DOC]` Uyuni Large Deployment HW Reqs                                          |
| Capacita singolo proxy        | 500-1.000 client                            | `[DOC]` Large Deployment HW Reqs                                                |
| Storage per prodotto SUSE     | ~50 GB per prodotto                         | `[DOC]` SUMA 4.3 HW Requirements                                                |
| Storage per prodotto Red Hat  | ~360 GB per prodotto                        | `[DOC]` SUMA 4.3 HW Requirements                                                |
| Rate onboarding sicuro        | 1 client ogni 15 secondi                    | `[DOC]` Operation Requirements                                                  |
| Banda client pending          | ~2.5 Kb/s per client                        | `[DOC]` Operation Requirements                                                  |

**Cosa la documentazione NON fornisce:** Non esistono tabelle ufficiali di sizing per fasce intermedie (es. "da 500 a 2.000 client servono X risorse"). I valori intermedi nelle tabelle di scaling (sezione 7) sono derivati e il ragionamento e sempre esplicitato.

## Server — Architettura Interna e Perche Ogni Componente Consuma Risorse

Il server Uyuni non e un processo singolo. E un insieme di servizi che competono per CPU, RAM e disco. Per dimensionare correttamente serve capire cosa fa ciascuno e perche scala.

### 2.1 I Servizi del Server e il Loro Consumo

| Servizio | Cosa fa | Perche scala con gli endpoint | Risorsa principale |
|----------|---------|-------------------------------|-------------------|
| **Salt Master** | Riceve gli eventi da ogni client (stato, grain, job results) e invia comandi (stati, esecuzioni remote). Ogni client mantiene una connessione ZeroMQ persistente. | Piu client = piu connessioni simultanee, piu eventi da processare al secondo. Il Master deve deserializzare, autenticare e routare ogni messaggio. | CPU + RAM |
| **Tomcat** | Serve la Web UI e l'API XML-RPC/JSON. Ogni pagina di sistema esegue query sul DB per mostrare errata applicabili, pacchetti installati, stato. | Piu sistemi = query piu pesanti. La pagina "Systems" con 5.000 sistemi carica dati per tutti. Le API batch (es. `system.listSystems`) iterano su tutto l'inventario. | RAM (heap Java) + CPU |
| **Taskomatic** | Esegue job schedulati: sync repository, calcolo errata applicabili per ogni sistema, matching CVE, invio notifiche. Ogni job itera su tutti i sistemi o tutti i pacchetti. | Il job "errata cache update" deve ricalcolare quali errata si applicano a ciascun sistema ogni volta che un canale viene sincronizzato. Con N sistemi e M errata, la complessita e O(N*M). | RAM (heap Java) + CPU + I/O disco DB |
| **Apache HTTPD** | Serve i pacchetti RPM/DEB ai client che li scaricano. Durante una finestra di patching, tutti i client del proxy richiedono pacchetti contemporaneamente. | Piu client nella stessa finestra = piu connessioni HTTP simultanee. Ogni connessione Apache occupa un worker process. | CPU + RAM (per worker) |
| **PostgreSQL** | Contiene tutto: inventario sistemi, pacchetti installati, errata, canali, audit log, job history. Ogni operazione dell'UI o dell'API e una query SQL. | Il volume di dati cresce linearmente con i sistemi. Gli indici crescono. Le query di join (es. "quali errata si applicano al sistema X") diventano piu lente con piu dati nelle tabelle. | RAM (shared_buffers) + I/O disco |
| **Cobbler** | Gestisce profili PXE per provisioning automatico di nuovi sistemi. | Scala solo se si usa PXE attivamente. Altrimenti e inattivo. | Trascurabile se non usato |

### 2.2 Come si Traduce in RAM — Il Calcolo

Ogni servizio ha un parametro che controlla quanta RAM puo usare. La RAM totale del server deve coprire la somma di tutti:

| Servizio | Parametro che controlla la RAM | Default `[DOC]` | Valore large scale `[DOC]` | Cosa significa il parametro |
|----------|-------------------------------|-----------------|---------------------------|----------------------------|
| Salt Master | `worker_threads` | 8 | 8-32 | Numero di thread paralleli che processano eventi dai client. Ogni thread gestisce un flusso indipendente di messaggi. Con 8 thread e 5.000 client, i messaggi si accodano. |
| Salt Master | (consumo per thread) | ~70 MB/thread | ~70 MB/thread | Ogni thread carica in memoria il modulo Salt, le grain, i pillar. `[DOC]` Tuning Guide |
| Tomcat | `-Xmx` | 1 GB | 4-8 GB | Heap massimo della JVM Tomcat. Limita quanti oggetti Java (risultati query, sessioni utente, response buffer) possono stare in memoria simultaneamente. |
| Taskomatic | `taskomatic.java.maxmemory` | 4096 MB | 4096-16384 MB | Heap massimo della JVM Taskomatic. I job batch (errata matching, channel sync) caricano grandi dataset in memoria per processarli. |
| PostgreSQL | `shared_buffers` | 25% RAM | 25-40% RAM | Porzione di RAM dedicata alla cache delle pagine del database. Piu e grande, meno PostgreSQL deve leggere da disco. |
| OS + overhead | — | ~2 GB | ~3 GB | Kernel, systemd, container runtime (Podman), logging, monitoring. |

**Calcolo RAM totale per fascia:**

**Fascia < 100 client** `[CALC]`:
```
Salt: 8 thread x 70 MB = 560 MB
Tomcat: 1 GB (default)
Taskomatic: 4 GB (default)
PostgreSQL: 25% x 16 GB = 4 GB
OS: ~2 GB
TOTALE = ~11.5 GB → 16 GB di RAM sono sufficienti
```

**Fascia 1.000 - 5.000 client** `[CALC]`:
```
Salt: 16-32 thread x 70 MB = 1.1 - 2.2 GB
Tomcat: 4-8 GB (documentazione dice 4-8 GB per >1.000)
Taskomatic: 8-16 GB (documentazione dice fino a 16384 MB)
PostgreSQL: 30% x 64 GB = ~19 GB
OS: ~3 GB
TOTALE = ~35 - 48 GB → servono 64 GB per avere margine
```

**Perche la documentazione dice "64 GB+ per migliaia di client":** Il termine "migliaia" (thousands) nella documentazione non specifica una soglia esatta. Dalla somma dei consumi dei sotto-sistemi (calcolo sopra), il punto di svolta e intorno a **1.000-2.000 client**: a quella scala Taskomatic e Tomcat con valori tuned richiedono gia 12-24 GB solo di heap Java, e PostgreSQL ne vuole altri 16-19. Sotto i 1.000 client, 32 GB sono tipicamente sufficienti.

---

## 3. Parametri di Tuning — Cosa Fa Ognuno e Perche va Cambiato

### 3.1 Salt Master

| Parametro | Default `[DOC]` | Large Scale `[DOC]` | Cosa controlla | Perche va aumentato |
|-----------|-----------------|---------------------|----------------|---------------------|
| `worker_threads` | 8 | 8-32 | Numero di processi paralleli che il Salt Master usa per processare eventi in arrivo dai minion. Ogni "evento" e un risultato di un comando, un aggiornamento di grain, un heartbeat. | Con 1.000+ client che rispondono simultaneamente a un comando (es. `state.apply`), 8 thread non riescono a deserializzare e routare tutti gli eventi in tempo. I messaggi si accodano nel buffer ZeroMQ e il sistema appare "lento" o "bloccato". |

**Impatto RAM** `[DOC]`: ~70 MB per thread. 32 thread = ~2.2 GB.

### 3.2 Java Application (Spacewalk/Uyuni)

| Parametro | Default `[DOC]` | Large Scale `[DOC]` | Cosa controlla | Perche va aumentato |
|-----------|-----------------|---------------------|----------------|---------------------|
| `java.message_queue_thread_pool_size` | 5 | 50-150 | Numero di thread che processano i messaggi nella coda interna tra Salt e l'applicazione Java. Quando Salt riceve un evento da un minion, lo inserisce in questa coda. I thread lo prendono, lo interpretano e aggiornano il database. | Con 5 thread e 2.000 client che inviano risultati, la coda cresce piu velocemente di quanto venga svuotata. I job risultano "completed" su Salt ma lo stato non si aggiorna nell'UI per minuti/ore. |
| `java.salt_batch_size` | 200 | 200-500 | Quando Uyuni deve eseguire un'azione su molti sistemi (es. "applica errata a tutti"), li raggruppa in batch di questa dimensione e li invia a Salt in blocchi sequenziali. | Con batch da 200 e 5.000 sistemi, servono 25 batch sequenziali. Aumentare a 500 riduce a 10 batch, dimezzando il tempo totale dell'operazione. Il trade-off: batch piu grandi caricano piu Salt Master e rete. |
| `java.salt_event_thread_pool_size` | 8 | 20-100 | Numero di thread dedicati alla ricezione e parsing degli eventi Salt nel bus eventi dell'applicazione Java. Diverso da `message_queue_thread_pool_size`: questi thread leggono dal bus Salt, quelli scrivono nel DB. | Collo di bottiglia simile a `message_queue`: se arrivano piu eventi di quanti i thread riescano a parsare, si accumula backlog. |

### 3.3 Taskomatic

| Parametro | Default `[DOC]` | Large Scale `[DOC]` | Cosa controlla | Perche va aumentato |
|-----------|-----------------|---------------------|----------------|---------------------|
| `taskomatic.java.maxmemory` | 4096 MB | 4096-16384 MB | Heap massimo della JVM Taskomatic. Taskomatic esegue job batch come: ricalcolo errata applicabili, sync canali, generazione report, cleanup. Questi job caricano in memoria liste di pacchetti e sistemi per fare matching. | Con 5.000 sistemi e 100.000+ pacchetti nei canali, il job "errata cache" deve fare il match tra ogni errata e ogni sistema. Il dataset in memoria cresce linearmente. Con 4 GB di heap e molti sistemi, il job va in OutOfMemoryError o diventa estremamente lento per il garbage collector. |
| `org.quartz.threadPool.threadCount` | 20 | 20-200 | Numero di job Taskomatic che possono eseguire in parallelo. I job includono: errata cache, channel repodata, cleanup, notifications, SSH push checks. | Con 20 thread e molti job schedulati (sync di 17+ canali, errata per ogni canale, report per ogni sistema), i job si accodano. Aumentare i thread permette piu esecuzioni parallele ma richiede proporzionalmente piu CPU e RAM. |

### 3.4 Apache HTTPD

| Parametro | Default `[DOC]` | Large Scale `[DOC]` | Cosa controlla | Perche va aumentato |
|-----------|-----------------|---------------------|----------------|---------------------|
| `MaxRequestWorkers` | 150 | 150-500 | Numero massimo di connessioni HTTP simultanee che Apache puo servire. Ogni client che scarica un pacchetto occupa un worker per tutta la durata del download. | Durante una finestra di patching, se 300 client dietro un proxy richiedono pacchetti contemporaneamente e Apache ha solo 150 worker, i client in eccesso ricevono `503 Service Unavailable` o attendono in coda. |

### 3.5 PostgreSQL

| Parametro | Default `[DOC]` | Large Scale `[DOC]` | Cosa controlla | Perche va aumentato |
|-----------|-----------------|---------------------|----------------|---------------------|
| `shared_buffers` | 25% RAM | 25-40% RAM | Quantita di RAM che PostgreSQL riserva per la cache delle pagine piu usate del database. Se un dato e in shared_buffers, la query non va su disco. | Con piu sistemi, le tabelle `rhnServer`, `rhnServerPackage`, `rhnErrataCache` crescono. Se non stanno in shared_buffers, ogni query provoca letture disco. Su HDD questo e devastante, su SSD e tollerabile ma comunque piu lento. |
| `effective_cache_size` | Varia | 75% RAM totale | Non alloca realmente memoria. Dice al query planner di PostgreSQL "supponi che ci siano X GB di cache totale (shared_buffers + OS page cache)". Influenza la scelta tra sequential scan e index scan. | Se impostato troppo basso, il planner sceglie sequential scan anche quando un index scan sarebbe piu efficiente, perche assume di non avere cache. |
| `work_mem` | Varia | 2-20 MB | RAM allocata per ogni operazione di sort o hash all'interno di una singola query. Una query complessa puo usare work_mem piu volte (una per ogni sort/hash). | Query pesanti (es. "lista tutti i pacchetti aggiornabili per 5.000 sistemi, ordinati per severita CVE") richiedono sort su dataset grandi. Se work_mem e troppo basso, PostgreSQL fa il sort su disco (temp files), ordini di grandezza piu lento. |
| `hibernate.c3p0.max_size` | 20 | 100-200 | Numero massimo di connessioni nel connection pool tra l'applicazione Java (Tomcat/Taskomatic) e PostgreSQL. | Con 20 connessioni e molti utenti UI + job Taskomatic + API calls simultanei, le richieste attendono una connessione libera. Aumentare a 100-200 elimina l'attesa ma consuma piu RAM su PostgreSQL (~5-10 MB per connessione). |

---

## 4. Proxy — Cosa fa e Perche Servono piu Proxy con piu Endpoint

### 4.1 Ruolo del Proxy

Il proxy **non e un load balancer**. Ogni client e assegnato staticamente a un proxy specifico. Il proxy fa tre cose:

1. **Cache pacchetti (Squid):** Quando il primo client dietro il proxy richiede un pacchetto, il proxy lo scarica dal server e lo mette in cache. Tutti i client successivi lo ricevono dalla cache locale. Questo riduce il traffico server-proxy da `N_client x dimensione_pacchetto` a `1 x dimensione_pacchetto`.

2. **Broker Salt (salt-broker):** I client parlano col proxy sulle porte 4505/4506. Il proxy inoltra i messaggi al server. Il server risponde al proxy, che inoltra ai client. Questo permette al server di avere una sola connessione ZeroMQ per proxy (invece di una per client).

3. **Serving repository (httpd):** Il proxy serve direttamente i metadata dei canali e i pacchetti dalla propria cache senza dover contattare il server per ogni richiesta.

### 4.2 Perche un Proxy ha un Limite di 500-1.000 Client `[DOC]`

Il bottleneck e la **banda di rete durante le finestre di patching**. Se 1.000 client richiedono simultaneamente 400 MB di aggiornamenti dal proxy:

```
[CALC] 400 MB x 1.000 client = 400 GB di traffico totale
Su link 1 Gbps: 400 GB / 125 MB/s = ~53 minuti (se la cache e calda)
Su link 100 Mbps: 400 GB / 12.5 MB/s = ~533 minuti (~9 ore)
```

Il proxy stesso ha CPU e RAM limitati. Squid con 1.000 connessioni simultanee e il salt-broker che inoltra 1.000 stream di eventi consumano risorse significative. Per questo la documentazione dice 8 GB RAM raccomandati e 16 GB per deployment grandi.

### 4.3 Storage del Proxy

| Volume | Cosa contiene | Dimensionamento `[DOC]` | Spiegazione |
|--------|---------------|------------------------|-------------|
| **`/srv`** | Metadata dei canali, script di bootstrap, configurazioni. Non contiene i pacchetti (quelli sono nella cache Squid). | 100 GB minimo | I metadata (repodata XML) di 17+ canali Ubuntu occupano pochi GB, ma il minimo documentato e 100 GB per headroom. |
| **Cache Squid** | Pacchetti RPM/DEB scaricati dai client. E una cache LRU: quando si riempie, i pacchetti meno usati vengono eliminati. | 60-80% del disco dedicato, idealmente >= dimensione repo server `[DOC]` | Se la cache e piu piccola del repo sul server, i pacchetti meno frequenti vengono evicti e devono essere riscaricati dal server. Se >= repo server, dopo il primo sync tutti i pacchetti sono in cache e il server non viene piu contattato. |

### 4.4 Numero di Proxy — Come si Calcola

La formula e semplice: `[CALC]`

```
N_proxy = ceil(N_client / capacita_per_proxy)
```

Dove `capacita_per_proxy` e 500-1.000 `[DOC]`, in funzione di:
- Banda di rete disponibile tra proxy e client
- Dimensione media degli aggiornamenti
- Ampiezza della finestra di patching (se tutti patchano alle 3 di notte, il picco e massimo)

---

## 5. Storage Repository sul Server — Come Cresce

### 5.1 Dati Dichiarati `[DOC]`

| Prodotto | Spazio per prodotto | Fonte |
|----------|-------------------|-------|
| Prodotto SUSE + Package Hub | ~50 GB | SUMA 4.3 HW Requirements |
| Prodotto Red Hat | ~360 GB | SUMA 4.3 HW Requirements |
| Cache per prodotto SUSE | +100 MB | SUMA 4.3 HW Requirements |
| Cache per prodotto Red Hat | +1 GB | SUMA 4.3 HW Requirements |

### 5.2 Calcolo per Scenario `[CALC]`

| Scenario | Calcolo | Risultato |
|----------|---------|-----------|
| Solo Ubuntu 24.04 (4 canali: main, universe, security, updates) | Non e un "prodotto SUSE/RH" — i canali Ubuntu custom occupano ~30-40 GB per architettura amd64 (verificato empiricamente sul nostro deployment: `/manager_storage` usa ~25 GB con 17 canali) | **150-200 GB** (con margine per CLM e crescita) |
| Ubuntu + 1 prodotto RHEL 9 | 150 GB (Ubuntu) + 360 GB (RHEL) | **~510 GB** |
| Ubuntu + RHEL 9 + 1 prodotto SLES | 150 GB + 360 GB + 50 GB | **~560 GB** |
| Multi-OS (Ubuntu + RHEL + SLES + Debian) | 150 + 360 + 50 + ~40 (Debian) | **~600 GB** (minimo, senza CLM aggiuntivo) |

**Nota importante:** Lo storage repository **non scala col numero di client** ma col **numero di prodotti/canali** gestiti. 10 client RHEL e 5.000 client RHEL occupano lo stesso spazio repository (i pacchetti sono gli stessi, vengono serviti a tutti). Quello che scala col numero di client e il **database** (inventario per sistema).

### 5.3 Vincoli `[DOC]`

- La sincronizzazione dei repository **fallisce** se lo spazio disco si esaurisce. Non c'e graceful degradation.
- Filesystem raccomandato: **XFS** per tutti i volumi.
- Repository, database e OS devono stare su **volumi separati**.
- **NFS non e supportato** per Cobbler e PostgreSQL.

---

## 6. Rete — Porte e Banda

### 6.1 Porte Obbligatorie `[DOC]`

**Server (inbound):**

| Porta | Scopo | Chi si connette |
|-------|-------|-----------------|
| 80/TCP | HTTP — bootstrap repo, redirect a HTTPS | Client, Proxy |
| 443/TCP | HTTPS — Web UI, API, download pacchetti, comunicazioni client | Client, Proxy, Amministratori |
| 4505/TCP | Salt publish — il server invia comandi ai client attraverso questo canale ZeroMQ | Client (diretti) o Proxy (broker) |
| 4506/TCP | Salt return — i client inviano risultati dei comandi attraverso questo canale ZeroMQ | Client (diretti) o Proxy (broker) |
| 5432/TCP | PostgreSQL — solo se si espone il reporting DB per BI/monitoring esterno | Opzionale, solo monitoring |

Porte aggiuntive (opzionali): 67-69 (DHCP/TFTP per PXE), 5556-5557/9100/9187/9800 (Prometheus exporters), 25151 (Cobbler).

**Proxy (inbound):**

| Porta | Scopo | Chi si connette |
|-------|-------|-----------------|
| 443/TCP | HTTPS — repository e comunicazioni | Client, Server |
| 4505/TCP | Salt publish (broker) | Client |
| 4506/TCP | Salt return (broker) | Client |
| 8022/TCP | SSH push — per client che non possono mantenere connessioni outbound persistenti (es. DMZ) | Client push-based |

**Client (outbound):** 80, 443, 4505, 4506 verso il proprio proxy (o il server se senza proxy).

### 6.2 Banda — Formula Ufficiale `[DOC]`

```
Dimensione_aggiornamenti (MB) x N_client / Velocita_download (MB/s) / 60 = Tempo (minuti)
```

Esempio dalla documentazione: 400 MB x 3.000 client / (1000 Mbps / 8) / 60 = **~160 minuti**.

### 6.3 Banda Consumata da Client Pending `[DOC]`

Client con Salt key non ancora accettata consumano **~2.5 Kb/s ciascuno** in traffico costante (polling). `[CALC]`: 1.000 client pending = ~2.5 Mb/s inbound costanti. Il traffico cessa dopo l'accettazione della key.

---

## 7. Tabelle di Scaling — Con Giustificazione per Ogni Valore

### 7.1 Server

| Scala | CPU | RAM | Storage DB | Storage Repo | Origine dei valori |
|-------|-----|-----|------------|--------------|-------------------|
| **< 100** | 4 core | 16 GB | 50 GB SSD | 150+ GB | `[DOC]` Requisiti minimi dichiarati: "minimum 4 dedicated 64-bit CPU cores, 16 GB RAM, 50 GB for database, 100-150 GB for repo". |
| **100 - 1.000** | 8 core | 32 GB | 50-100 GB SSD | Dipende dai prodotti (vedi sez. 5) | `[DOC]` Requisiti raccomandati: "recommended 8+ recent x86-64 cores, 32 GB RAM". La documentazione li presenta come "production recommended" senza indicare una soglia di client specifica. Rappresentano il target per qualsiasi deployment di produzione. |
| **1.000 - 10.000** | 8+ core | 64+ GB | 100+ GB SSD (RAID-0 consigliato) | Dipende dai prodotti | `[DOC]` + `[CALC]`: La documentazione dice "64 GB+ for thousands of clients". Il calcolo cumulativo RAM (sezione 2.2) conferma: con parametri tuned per >1.000 client, la somma dei sotto-sistemi supera 35-48 GB. 64 GB e il minimo pratico. La documentazione non distingue tra 2.000 e 8.000: dice solo "8+ cores" e "64 GB+" per tutta la fascia "large". |
| **> 10.000** | Multi-server (Hub) | 64 GB+ per nodo | SSD RAID-0 per nodo | Per nodo | `[DOC]` "Do not exceed 10,000 clients per single server. Hub architecture required." — Large Deployments Overview. |

**Perche non ci sono fasce intermedie piu granulari (es. 2.000 vs 5.000 vs 8.000)?** Perche la documentazione ufficiale non le fornisce. I requisiti dichiarati sono: minimo (16 GB), raccomandato produzione (32 GB), large scale (64 GB+), e Hub (>10.000). Qualsiasi fascia intermedia sarebbe un'interpolazione non supportata dalla documentazione. L'unico strumento per determinare il sizing esatto tra 1.000 e 10.000 client e il **monitoraggio in produzione** (Prometheus + Grafana) e il tuning iterativo.

### 7.2 Proxy

| Scala | N. Proxy | RAM/Proxy | Cache Squid | Origine dei valori |
|-------|----------|-----------|-------------|-------------------|
| **< 500** | 1 | 2-8 GB | 100 GB | `[DOC]` Requisiti minimi proxy: "2 GB minimum, 8 GB recommended". Un proxy gestisce 500-1.000 client. |
| **500 - 1.000** | 1-2 | 8 GB | >= repo server | `[DOC]` "A single proxy serves 500-1,000 clients". A 1.000 si e al limite superiore dichiarato, il secondo proxy fornisce ridondanza. `[DOC]` "Making the proxy cache the same size as /var/spacewalk on the server avoids most traffic after first sync." |
| **1.000 - 5.000** | 2-10 | 8-16 GB | >= repo server | `[CALC]` Da 1.000/500 = 2 proxy (limite conservativo) a 5.000/500 = 10 proxy (limite conservativo). Il range 500-1.000 della documentazione e il motivo per cui il numero e un range e non un valore fisso. `[DOC]` "16 GB for large deployments". |
| **5.000 - 10.000** | 10-20 | 16 GB | >= repo server | `[CALC]` Da 5.000/500 = 10 a 10.000/500 = 20 (usando il limite conservativo di 500 client/proxy). |

### 7.3 Rete

| Scala | Banda Server-Proxy | Origine |
|-------|-------------------|---------|
| **< 500** | 100 Mbps sufficiente | `[CALC]` Dalla formula: 400 MB x 500 client / 12.5 MB/s = ~2.7 ore. Accettabile per finestre di patching notturne. |
| **500 - 1.000** | 1 Gbps raccomandato | `[CALC]` 400 MB x 1.000 / 125 MB/s = ~53 min. Con 100 Mbps sarebbero ~9 ore. |
| **1.000 - 10.000** | 1 Gbps per proxy (o aggregato 10 Gbps) | `[CALC]` Ogni proxy serve al massimo 1.000 client. La banda per proxy e la stessa della fascia precedente. Il link tra server e i proxy aggregati deve sostenere N_proxy x traffico_unitario, ma i proxy hanno cache quindi il traffico post-prima-sync e minimo. |

---

## 8. Onboarding — Vincoli Operativi `[DOC]`

| Vincolo | Valore | Fonte | Spiegazione |
|---------|--------|-------|-------------|
| Rate massimo sicuro | 1 client ogni 15 secondi | Operation Requirements | L'accettazione della key Salt innesca: registrazione nel DB, calcolo dei canali applicabili, generazione della cache errata per quel sistema, download dei grain. Tutto questo richiede ~15 secondi per sistema. |
| Tempo per 1.000 client | ~4 ore | `[CALC]` 1.000 x 15s = 15.000s = 250 min | — |
| Tempo per 10.000 client | ~42 ore | `[CALC]` 10.000 x 15s = 150.000s | — |
| Cancellazione key | In batch, off-peak | Operation Requirements | La cancellazione di una key causa la rigenerazione della chiave AES del Salt Master, che e un'operazione CPU-intensive e temporaneamente blocca la comunicazione con tutti gli altri client. |

---

## 9. Vincoli Architetturali Non Negoziabili `[DOC]`

| Vincolo | Dettaglio | Conseguenza Pratica |
|---------|-----------|---------------------|
| Max 10.000 client per server | Hard limit architetturale | Oltre servono piu server (Hub) |
| PostgreSQL solo locale | No database remoti, no NFS | Il DB deve stare sulla stessa macchina/pod del server |
| PostgreSQL su SSD | Deve essere sul dispositivo piu veloce | HDD per il DB degrada tutto il sistema oltre poche centinaia di client |
| NFS vietato per DB e Cobbler | Rischio perdita dati, incompatibilita SELinux | Storage locale o SAN con accesso a blocchi |
| XFS raccomandato | Per tutti i volumi | ext4 funziona ma XFS ha migliori performance con file grandi (pacchetti RPM/DEB) |
| Volumi separati | OS, DB, Repository su dischi distinti | Evita che un sync di canale che riempie il disco repository impatti il database |
| Kernel tuning | `vm.swappiness=10-20`, `elevator=none` (VM) | Riduce lo swap aggressivo che degraderebbe Taskomatic e PostgreSQL |
| Proxy obbligatori in produzione | I client non dovrebbero connettersi direttamente al server | Senza proxy, il server gestisce sia il processing che il serving dei pacchetti — i due carichi competono |

---

## 10. Architettura Hub (oltre 10.000 Endpoint) `[DOC]`

Quando i client superano 10.000, la documentazione prescrive l'architettura Hub:

- **1 Hub Server** centrale: coordina i server periferici, sincronizza contenuti e policy
- **N Server Periferici**: ciascuno gestisce fino a 10.000 client con i propri proxy
- **Hub Online Synchronization** (SUSE Multi-Linux Manager 5.1): sincronizzazione automatica dei contenuti tra Hub e periferici

Ogni nodo periferico ha gli stessi requisiti di un server standalone, dimensionati in base ai propri client diretti.

> SUSE raccomanda un engagement consulenziale per la progettazione di architetture Hub.

---

## Fonti

| Documento | URL |
|-----------|-----|
| Uyuni Hardware Requirements | https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/hardware-requirements.html |
| SUSE Manager 5.0 HW Requirements | https://documentation.suse.com/suma/5.0/en/suse-manager/installation-and-upgrade/hardware-requirements.html |
| SUSE Manager 4.3 HW Requirements | https://documentation.suse.com/suma/4.3/en/suse-manager/installation-and-upgrade/hardware-requirements.html |
| SUSE Multi-Linux Manager 5.1 HW Reqs | https://documentation.suse.com/multi-linux-manager/5.1/en/docs/installation-and-upgrade/hardware-requirements.html |
| Uyuni Large Deployment HW Reqs | https://www.uyuni-project.org/uyuni-docs/en/uyuni/specialized-guides/large-deployments/hardware-reqs.html |
| SUSE Manager Large Deployments Overview | https://documentation.suse.com/suma/4.3/en/suse-manager/specialized-guides/large-deployments/overview.html |
| SUSE Manager Tuning Guide | https://documentation.suse.com/suma/4.3/en/suse-manager/specialized-guides/large-deployments/tuning.html |
| SUSE Manager Operation Requirements | https://documentation.suse.com/suma/4.3/en/suse-manager/specialized-guides/large-deployments/operation-reqs.html |
| Uyuni Network Requirements | https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/network-requirements.html |
