```bash
hammer ping
```
serve per **verificare rapidamente lo stato dei servizi principali** di Foreman/Katello.
Cosa fa in pratica:
- interroga i vari **servizi core** (poste come Dynflow, Pulp, Candlepin, PostgreSQL…)
- restituisce un output del tipo _UP/DOWN_
- permette di capire in pochi secondi se l'istanza è _funzionante_ o se c’è un problema di backend
È molto utile quando qualcosa non risponde nell’interfaccia web o quando non si riescono a eseguire task.

### `foreman-maintain` 
E' lo strumento di manutenzione e diagnostica ufficiale di Foreman/Satellite (lo ha sostituito katello-service).
```bash
foreman-maintain service status -b
```
significa:
- **`service status`** → mostra lo stato dei servizi Foreman/Katello
- **`-b` (batch)** → output non interattivo, perfetto per script o automazione (evita prompt)
Cosa fa:
- elenca _tutti_ i servizi gestiti (httpd, dynflow, pulp services, candlepin, foreman, postgres…)
- mostra se sono attivi, inattivi o falliti
- è molto più dettagliato di `hammer ping`



```bash
rpm -qa | grep ansible
```

## `apt update` è sicuro

**`apt update` NON modifica nulla sulla macchina.** 

Fa solo una cosa: scarica l'**elenco aggiornato** dei pacchetti disponibili dai repository configurati. È come "consultare il catalogo" di un negozio senza comprare niente.

| Comando | Cosa fa | Modifica il sistema? |
|---------|---------|---------------------|
| `apt update` | Scarica la lista dei pacchetti disponibili | ❌ No |
| `apt upgrade` | Installa le nuove versioni dei pacchetti | ✅ Sì |
| `apt install` | Installa nuovi pacchetti | ✅ Sì |

## In pratica

Dopo `apt update`:
- Nessun pacchetto viene installato
- Nessun pacchetto viene aggiornato
- Il sistema funziona esattamente come prima

L'unica cosa che cambia è il file `/var/lib/apt/lists/*` che contiene l'indice dei pacchetti, un file di "metadati" che non influenza il funzionamento del sistema.