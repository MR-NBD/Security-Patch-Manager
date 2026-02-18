## Server — CPU e RAM (scala con i client)

Lo storage del repository **non entra in questo calcolo** — è indipendente dal numero di client.

| Fascia client      | vCPU | RAM       | DB Storage (SSD) | Tuning richiesto                          |
| ------------------ | ---- | --------- | ---------------- | ----------------------------------------- |
| **≤ 100**          | 4    | 16 GB     | 50 GB            | Nessuno — valori default                  |
| **100 – 500**      | 8    | 32 GB     | 50 GB            | Nessuno — valori default                  |
| **500 – 1.000**    | 8    | 32 GB     | 100 GB           | Leggero (vedi sezione 4)                  |
| **1.000 – 2.500**  | 8+   | 64 GB     | 100 GB           | Medio (vedi sezione 4)                    |
| **2.500 – 5.000**  | 12+  | 64 GB     | 150 GB           | Medio (vedi sezione 4)                    |
| **5.000 – 10.000** | 16+  | 64–128 GB | 200 GB           | Aggressivo (vedi sezione 4)               |
| **> 10.000**       | —    | —         | —                | **Hub architecture obbligatoria** `[DOC]` |

**Note sui valori:**
- ≤ 100 e 100–500: requisiti minimi e raccomandati dichiarati esplicitamente 
- 1.000+: la documentazione dice "64 GB+ for thousands of clients" senza distinguere 2.000 da 8.000 ù
- Volumi separati obbligatori: OS, DB e repository su dischi distinti 

### Perché RAM scala con i client (sintesi)

| Servizio                    | Consumo RAM a piccola scala | Consumo RAM a grande scala  |
| --------------------------- | --------------------------- | --------------------------- |
| Salt Master (8 thread)      | ~560 MB                     | ~2.2 GB (32 thread × 70 MB) |
| Tomcat (heap JVM)           | 1 GB                        | 4–8 GB                      |
| Taskomatic (heap JVM)       | 4 GB                        | 8–16 GB                     |
| PostgreSQL (shared_buffers) | 4 GB (25% × 16 GB)          | 19–25 GB (30% × 64–128 GB)  |
| OS + overhead               | ~2 GB                       | ~3 GB                       |
| **Totale**                  | **~11.5 GB → 16 GB**        | **~35–50 GB → 64 GB**       |

Il punto di svolta è intorno a **1.000–2.000 client**: a quella scala Taskomatic e Tomcat con parametri tuned richiedono già 12–24 GB di heap Java. `[CALC]`

---

## Proxy — Quanti e Come (scala con i client)

| Fascia client      | N. Proxy | RAM/Proxy | Cache Squid/Proxy  | Note                  |
| ------------------ | -------- | --------- | ------------------ | --------------------- |
| **≤ 500**          | 1        | 8 GB      | ≥ 100 GB           | 1 proxy è sufficiente |
| **500 – 1.000**    | 1–2      | 8 GB      | ≥ dim. repo server | 2 per ridondanza      |
| **1.000 – 2.000**  | 2–4      | 8–16 GB   | ≥ dim. repo server |                       |
| **2.000 – 5.000**  | 4–10     | 16 GB     | ≥ dim. repo server |                       |
| **5.000 – 10.000** | 10–20    | 16 GB     | ≥ dim. repo server |                       |

**Formula:** `N_proxy = ⌈N_client / 700⌉` (700 = valore medio conservativo nel range documentato 500–1.000) 

**Regola cache Squid:** se la cache Squid è >= dello storage repository del server, dopo il primo sync tutti i pacchetti vengono serviti localmente senza più contattare il server. `[DOC]`

---
## Storage Repository (scala con i canali, NON con i client)

> **Principio chiave:** 100 client RHEL e 5.000 client RHEL richiedono **lo stesso** storage repository — i pacchetti sono gli stessi, cambiano solo quanti sistemi li scaricano.

### 3.1 Costo per tipo di canale

| Tipo canale | Storage stimato per canale | Riferimento |
|-------------|---------------------------|-------------|
| Ubuntu / Debian | ~2 GB raw / ~8 GB con 2 ambienti CLM | `[EMP]` 17 canali Ubuntu = ~25 GB sul nostro deployment |
| openSUSE / SLES | ~15 GB/canale | `[DOC]` ~50 GB per prodotto (3–4 canali/prodotto) |
| RHEL / AlmaLinux / Rocky | ~90 GB/canale | `[DOC]` ~360 GB per prodotto (4 canali/prodotto) |

> **Attenzione CLM:** Content Lifecycle Management crea copie dei canali per ogni ambiente (es. Dev/Test/Prod). Ogni ambiente moltiplica lo storage raw. Il fattore 4× nella colonna "con CLM" assume 2 ambienti CLM attivi.

### 3.2 Scenario A — Solo Ubuntu / Debian

| Canali | Storage raw | Con 2 ambienti CLM | Raccomandato (con margine) |
|--------|------------|-------------------|--------------------------|
| **5** | ~10 GB | ~40 GB | **100 GB** |
| **10** | ~20 GB | ~80 GB | **150 GB** |
| **15** | ~30 GB | ~120 GB | **200 GB** |
| **20** | ~40 GB | ~160 GB | **250 GB** |

### 3.3 Scenario B — Ubuntu + RHEL/AlmaLinux

> Un prodotto RHEL = ~360 GB. Domina completamente. Ogni prodotto RHEL aggiunto vale quanto ~180 canali Ubuntu.

| Canali Ubuntu | Prodotti RHEL | Canali RHEL equiv. | Storage totale stimato |
|--------------|--------------|-------------------|----------------------|
| 5 | 1 | 4 | ~10 + 360 = **~370 GB** |
| 10 | 1 | 4 | ~20 + 360 = **~380 GB** |
| 10 | 2 | 8 | ~20 + 720 = **~740 GB** |
| 15 | 2 | 8 | ~30 + 720 = **~750 GB** |
| 20 | 2 | 8 | ~40 + 720 = **~760 GB** |
| 15 | 3 | 12 | ~30 + 1.080 = **~1.1 TB** |

### 3.4 Scenario C — Ubuntu + SLES/openSUSE

| Canali Ubuntu | Prodotti SUSE | Canali SUSE equiv. | Storage totale stimato |
|--------------|--------------|-------------------|----------------------|
| 10 | 1 | 3–4 | ~20 + 50 = **~70 GB** |
| 15 | 2 | 6–8 | ~30 + 100 = **~130 GB** |
| 20 | 3 | 9–12 | ~40 + 150 = **~190 GB** |

---
## Impatto dei Canali su Taskomatic (effetto combinato)

I canali influenzano anche CPU e RAM del server tramite **Taskomatic**, non solo lo storage. Ogni volta che un canale viene sincronizzato, Taskomatic ricalcola le errata applicabili per **ogni sistema** iscritto a quel canale.

```
Carico Taskomatic ∝ N_canali × N_client
```

| Client × Canali | Pressione Taskomatic | Heap Taskomatic consigliato |
|-----------------|---------------------|---------------------------|
| 500 × 10 | Bassa | 4 GB (default) |
| 1.000 × 15 | Media | 8 GB |
| 2.000 × 20 | Alta | 12–16 GB |
| 5.000 × 20 | Molto alta | 16 GB + tuning thread pool |

Questo non cambia la fascia RAM server (rimane la stessa sezione 1), ma influenza quanto overhead rimane disponibile. Con molti canali E molti client, stare sul limite basso della fascia RAM è rischioso.

---
## Onboarding — Limiti Operativi

| Operazione | Limite | Calcolo |
|------------|--------|---------|
| Rate massimo onboarding | **1 client ogni 15 sec** `[DOC]` | Ogni accettazione key innesca registrazione DB + calcolo canali + cache errata |
| Onboarding 500 client | ~2 ore | `[CALC]` 500 × 15s = 7.500s |
| Onboarding 1.000 client | ~4 ore | `[CALC]` 1.000 × 15s = 15.000s |
| Onboarding 5.000 client | ~21 ore | `[CALC]` 5.000 × 15s = 75.000s |
| Client pending (key non accettata) | ~2.5 Kb/s ciascuno `[DOC]` | 1.000 client pending = ~2.5 Mb/s costanti |

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
