## FASE 0: Ricognizione dello Stato Attuale

Prima di toccare qualsiasi cosa, raccogliere informazioni sul setup corrente.

### Recuperare le credenziali del container DB

Il `pg_hba.conf` del container `uyuni-db` accetta **solo connessioni TCP** (non Unix socket) con autenticazione `scram-sha-256`. Le password sono nelle variabili d'ambiente del container:

```bash
podman inspect uyuni-db --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -i pass
```

Output atteso (le password sono in chiaro):
```
MANAGER_PASS=<password utente susemanager>
POSTGRES_PASSWORD=<password superuser postgres>
REPORT_DB_PASS=<password utente report>
```

Salvare questi valori — servono per il dump e per configurare il restore.

Definire le variabili per i comandi successivi:
```bash
PG_SUPERPASS=$(podman inspect uyuni-db --format '{{range .Config.Env}}{{println .}}{{end}}' | grep POSTGRES_PASSWORD | cut -d= -f2)
PG_MGRPASS=$(podman inspect uyuni-db --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^MANAGER_PASS' | cut -d= -f2)
```

### Verificare la versione PostgreSQL nel container

```bash
# ✅ Metodo corretto: TCP + superuser postgres
podman exec -e PGPASSWORD="$PG_SUPERPASS" \
  uyuni-db psql -h localhost -U postgres -d susemanager -c "SELECT version();"
```

> **Versione rilevata nel setup attuale: PostgreSQL 16.9** — il Flexible Server Azure deve essere creato con **PostgreSQL 16**.

### Verificare le estensioni installate

```bash
podman exec -e PGPASSWORD="$PG_SUPERPASS" \
  uyuni-db psql -h localhost -U postgres -d susemanager -c "\dx"
```

Annotare tutte le estensioni — devono essere abilitate sul Flexible Server prima del restore.

### Verificare la dimensione del database

```bash
podman exec -e PGPASSWORD="$PG_SUPERPASS" \
  uyuni-db psql -h localhost -U postgres -d susemanager \
  -c "SELECT pg_size_pretty(pg_database_size('susemanager'));"
```

Utile per stimare i tempi di dump/restore e il dimensionamento dello storage Azure.

### Verificare la configurazione di connessione attuale

```bash
podman exec uyuni-server grep -E "db_host|db_port|db_name|db_user|db_password" /etc/rhn/rhn.conf
```

Annotare i valori. Questi sono i parametri che andremo a modificare.

### Snapshot opzionale della VM (raccomandato)

Dal portale Azure, creare uno snapshot dei dischi della VM prima di procedere. In caso di problemi irrecuperabili, permette di tornare allo stato attuale.

---

## FASE 1: Provisioning Azure Flexible Server

### 1.1 Creare il Flexible Server dal Portale Azure

1. Cercare **Azure Database for PostgreSQL Flexible Server** → **Create**
2. Configurare:

| Parametro              | Valore                                                   |
| ---------------------- | -------------------------------------------------------- |
| **Resource Group**     | test_group *(stesso della VM UYUNI)*                     |
| **Server name**        | `uyuni-db-test-azure`                                    |
| **Region**             | Italy North *(stessa della VM UYUNI)*                    |
| **PostgreSQL version** | **16** *(versione rilevata: 16.9)*                       |
| **Workload type**      | Development *(per il test)*                              |
| **Compute tier**       | Burstable                                                |
| **Compute size**       | Standard_B2ms (2 vCore, 8 GB) — sufficiente per il test |
| **Storage**            | 32 GB+ (adeguare in base alla dimensione DB in FASE 0)   |
| **HA**                 | Disabled *(per il test)*                                 |
| **Backup retention**   | 7 giorni                                                 |
| **Admin username**     | `pgadmin`                                                |
| **Admin password**     | Scegliere una password sicura, annotarla                 |

3. Tab **Networking**:
   - **Connectivity method**: `Private access (VNet Integration)`
   - **VNet**: ASL0603-spoke10-spoke-italynorth *(stessa della VM UYUNI)*
   - **Subnet**: creare una nuova subnet dedicata (es. `postgres-subnet`, 10.172.2.32/28) oppure usare una esistente
   - Azure crea automaticamente una **Private DNS Zone** e la linka alla VNet

4. **Review + Create** → **Create** (richiede ~5-10 minuti)

### 1.2 Verificare la risoluzione DNS dalla VM UYUNI

```bash
# Dalla VM UYUNI (dopo che il Flexible Server è creato)
host uyuni-db-test-azure.private.postgres.database.azure.com

# Verificare connettività porta
nc -zv uyuni-db-test-azure.private.postgres.database.azure.com 5432
```

Output atteso: indirizzo IP privato (es. 10.172.2.33) e connessione porta riuscita.

> Se `nc` fallisce: verificare in Azure Portal che la subnet sia delegata a `Microsoft.DBforPostgreSQL/flexibleServers` e che la Private DNS Zone sia linkata alla VNet.

### 1.3 Abilitare le Estensioni Richieste

Dal portale Azure → Flexible Server → **Server parameters** → cercare `azure.extensions`:

Aggiungere (separati da virgola): `UUID-OSSP,PGCRYPTO`

Salvare e attendere l'applicazione (non richiede restart).

Verificare dal terminale:
```bash
psql "host=uyuni-db-test-azure.private.postgres.database.azure.com \
  port=5432 dbname=postgres user=pgadmin sslmode=require" \
  -c "SHOW azure.extensions;"
```

### 1.4 Creare Database e Utente UYUNI

```bash
psql "host=uyuni-db-test-azure.private.postgres.database.azure.com \
  port=5432 dbname=postgres user=pgadmin sslmode=require" <<'EOF'
CREATE USER susemanager WITH PASSWORD '<PASSWORD_DB>';
CREATE DATABASE susemanager OWNER susemanager;
GRANT ALL PRIVILEGES ON DATABASE susemanager TO susemanager;
EOF
```

Abilitare le estensioni nel database:
```bash
psql "host=uyuni-db-test-azure.private.postgres.database.azure.com \
  port=5432 dbname=susemanager user=pgadmin sslmode=require" <<'EOF'
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
EOF
```

---

## FASE 2: Dump del Database Locale

> **DOWNTIME**: Il dump viene eseguito con UYUNI fermo per garantire la consistenza dei dati. Pianificare una finestra di manutenzione.

### 2.1 Fermare il Server UYUNI

```bash
mgradm stop
```

Verificare che entrambi i container siano fermi:
```bash
podman ps
```
Output atteso: nessun container attivo (o solo `uyuni-db` se mgradm stop non lo ferma).

```bash
# Se uyuni-db è ancora attivo, fermarlo separatamente
podman stop uyuni-db
```

### 2.2 Eseguire il Dump

```bash
# Creare directory per il dump
mkdir -p /manager_storage/db-backup

# Dump in formato custom (più veloce e compresso)
podman start uyuni-db
sleep 5  # attendere che PostgreSQL sia pronto

PG_SUPERPASS=$(podman inspect uyuni-db --format '{{range .Config.Env}}{{println .}}{{end}}' | grep POSTGRES_PASSWORD | cut -d= -f2)

podman exec -e PGPASSWORD="$PG_SUPERPASS" uyuni-db pg_dump \
  -h localhost \
  -U postgres \
  -d susemanager \
  -Fc \
  -f /tmp/susemanager_dump.pgdump

# Copiare il dump fuori dal container
podman cp uyuni-db:/tmp/susemanager_dump.pgdump /manager_storage/db-backup/susemanager_$(date +%Y%m%d_%H%M).pgdump

# Verificare che il dump sia valido e non vuoto
ls -lh /manager_storage/db-backup/
```

```bash
# Fermare nuovamente il container DB dopo il dump
podman stop uyuni-db
```

---

## FASE 3: Restore su Azure Flexible Server

### 3.1 Installare pg_restore sulla VM (se non presente)

```bash
zypper install -y postgresql
pg_restore --version
```

La versione di `pg_restore` deve essere >= alla versione del dump. Se la versione è inferiore, usare la versione dal container:

```bash
# Alternativa: restore via container
podman start uyuni-db
podman cp /manager_storage/db-backup/susemanager_*.pgdump uyuni-db:/tmp/dump.pgdump
```

### 3.2 Eseguire il Restore

```bash
AZURE_HOST="uyuni-db-test-azure.private.postgres.database.azure.com"
DUMP_FILE=$(ls -t /manager_storage/db-backup/*.pgdump | head -1)

pg_restore \
  -h "$AZURE_HOST" \
  -p 5432 \
  -U susemanager \
  -d susemanager \
  --no-owner \
  --no-acl \
  -v \
  "$DUMP_FILE" 2>&1 | tee /manager_storage/db-backup/restore.log
```

> Il flag `--no-owner` è necessario perché Azure PaaS non supporta il cambio di owner tramite `pg_restore` (mancanza di superuser). Le tabelle vengono comunque create di proprietà di `susemanager`.

### 3.3 Verificare il Restore

```bash
AZURE_HOST="uyuni-db-test-azure.private.postgres.database.azure.com"

# Contare le tabelle nel DB Azure
psql "host=$AZURE_HOST port=5432 dbname=susemanager user=susemanager sslmode=require" \
  -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"

# Confrontare con il DB originale (container locale)
podman start uyuni-db
podman exec uyuni-db psql -U susemanager -d susemanager \
  -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
podman stop uyuni-db
```

I conteggi devono corrispondere. Verificare anche alcune tabelle chiave:
```bash
psql "host=$AZURE_HOST port=5432 dbname=susemanager user=susemanager sslmode=require" \
  -c "SELECT count(*) FROM rhnServer;"

psql "host=$AZURE_HOST port=5432 dbname=susemanager user=susemanager sslmode=require" \
  -c "SELECT count(*) FROM rhnErrata;"
```

---

## FASE 4: Riconfigurare UYUNI per Usare il DB Esterno

### 4.1 Trovare il File di Configurazione

```bash
# Verificare il contenuto attuale di rhn.conf nel container server
# (il container server può essere avviato senza il DB per leggere la config)
podman start uyuni-server
podman exec uyuni-server cat /etc/rhn/rhn.conf | grep db_
```

### 4.2 Aggiornare la Configurazione DB

```bash
AZURE_HOST="uyuni-db-test-azure.private.postgres.database.azure.com"
DB_PASS="<PASSWORD_DB>"  # la stessa usata in FASE 1.4

# Modificare rhn.conf nel container
podman exec uyuni-server bash -c "
  sed -i 's/^db_host.*/db_host = $AZURE_HOST/' /etc/rhn/rhn.conf
  sed -i 's/^db_port.*/db_port = 5432/' /etc/rhn/rhn.conf
  sed -i 's/^db_ssl_enabled.*/db_ssl_enabled = 1/' /etc/rhn/rhn.conf
"

# Verificare le modifiche
podman exec uyuni-server grep -E "db_host|db_port|db_ssl" /etc/rhn/rhn.conf
```

> Se `rhn.conf` non contiene `db_ssl_enabled`, aggiungerlo:
> ```bash
> podman exec uyuni-server bash -c "echo 'db_ssl_enabled = 1' >> /etc/rhn/rhn.conf"
> ```

### 4.3 Verificare se mgradm ha una config separata

```bash
# Cercare file di configurazione mgradm sull'host
ls /etc/mgradm* 2>/dev/null
cat /etc/mgradm.yaml 2>/dev/null || echo "non trovato"

# Cercare in Podman secrets
podman secret ls
```

Se mgradm usa un file di configurazione separato con i parametri DB, aggiornare anche quello. Il parametro chiave è `db_host`.

### 4.4 Fermare il Container Server e Riavviare

```bash
podman stop uyuni-server

# Avviare SOLO il container server (NON uyuni-db)
# mgradm start avvierebbe entrambi — avviare manualmente solo il server
podman start uyuni-server
```

> **IMPORTANTE**: NON avviare `uyuni-db`. Se parte il container locale, UYUNI si connette a quello invece dell'Azure PaaS.

---

## FASE 5: Verifica Funzionamento

### 5.1 Verificare i Log di Avvio

```bash
podman logs uyuni-server --tail 50 -f
```

Cercare:
- Assenza di errori `connection refused` verso il DB
- Presenza di log `Hibernate SessionFactory built` o simili (indicano connessione DB riuscita)
- Tomcat avviato correttamente

### 5.2 Verificare Connettività DB dall'Interno del Container

```bash
podman exec uyuni-server bash -c "
  psql 'host=uyuni-db-test-azure.private.postgres.database.azure.com \
    port=5432 dbname=susemanager user=susemanager sslmode=require' \
    -c 'SELECT 1;'
"
```

### 5.3 Verificare la Web UI

Aprire `https://<IP-VM-UYUNI>` (tramite Azure Bastion o VPN):
- Il login deve funzionare
- La lista sistemi deve mostrare i client registrati
- Verificare **Admin → Task Schedules** — i job schedulati devono essere visibili

### 5.4 Verificare i Servizi Interni

```bash
mgrctl exec -- systemctl status tomcat.service --no-pager
mgrctl exec -- systemctl status salt-master.service --no-pager
mgrctl exec -- systemctl status taskomatic.service --no-pager
```

### 5.5 Test Funzionale: Ping a un Client Salt

```bash
mgrctl exec -- salt '*' test.ping
```

Se i minion rispondono, Salt Master è operativo e il DB esterno funziona correttamente.

---

## FASE 6: Decisione — Conferma o Rollback

### Se tutto funziona ✓

```bash
# Il container uyuni-db locale può essere rimosso
podman stop uyuni-db
podman rm uyuni-db

# Verificare che UYUNI continui a funzionare senza il container locale
podman ps  # deve mostrare solo uyuni-server
mgrctl exec -- salt '*' test.ping
```

> Il volume `/pgsql_storage` può essere mantenuto come backup temporaneo e rimosso in un secondo momento dopo la conferma definitiva.

### Se qualcosa non funziona ✗ — Rollback

```bash
# 1. Fermare il container server
podman stop uyuni-server

# 2. Ripristinare la configurazione DB originale nel container
podman start uyuni-server
podman exec uyuni-server bash -c "
  sed -i 's/^db_host.*/db_host = localhost/' /etc/rhn/rhn.conf
  sed -i 's/^db_ssl_enabled.*/db_ssl_enabled = 0/' /etc/rhn/rhn.conf
"
podman stop uyuni-server

# 3. Riavviare tutto con mgradm (container locale)
mgradm start

# 4. Verificare che UYUNI funzioni come prima
podman ps
mgrctl exec -- salt '*' test.ping
```

---

## Problemi Comuni

### Errore: SSL required

```
FATAL: SSL connection is required
```

Aggiungere `sslmode=require` alla stringa di connessione o abilitare `db_ssl_enabled = 1` in `rhn.conf`.

### Errore: pg_restore — role "susemanager" does not exist

Normale con `--no-owner`. Verificare che il restore sia completato comunque e che le tabelle siano presenti. Se le tabelle sono vuote, verificare i permessi:
```bash
psql "host=<AZURE_HOST> ... user=pgadmin" \
  -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO susemanager;"
```

### Errore: extension "uuid-ossp" does not exist

L'estensione non è stata abilitata correttamente. Verificare in **Server parameters → azure.extensions** che `UUID-OSSP` sia nella lista, poi:
```bash
psql "host=<AZURE_HOST> ... user=pgadmin -d susemanager" \
  -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"
```

### Tomcat non si avvia — errore connessione DB

```bash
# Verificare il log Tomcat dentro il container
podman exec uyuni-server journalctl -u tomcat -n 50 --no-pager
# oppure
podman exec uyuni-server tail -100 /var/log/rhn/rhn_web_api.log
```

Cercare `connection refused` o `authentication failed` per identificare se il problema è di rete o di credenziali.

### UYUNI si connette ancora al container locale invece di Azure

```bash
# Verificare quale DB sta usando effettivamente
podman exec uyuni-server psql \
  "$(grep db_host /etc/rhn/rhn.conf | awk '{print $3}')" \
  -U susemanager -c "SELECT inet_server_addr();"
```

L'IP restituito deve essere quello del Flexible Server Azure, non `127.0.0.1`.

---

## Risultato Atteso

Al termine della procedura, UYUNI funziona con:

```
VM uyuni-server-test
└── Container: uyuni-server (attivo)
    └── Connessione DB → Azure Flexible Server (uyuni-db-test-azure)

Container: uyuni-db (fermato/rimosso — non più necessario)
```

Se il test ha esito positivo, la stessa architettura viene adottata in produzione seguendo `Installazione-UYUNI-Server-PRODUZIONE.md`, con il Flexible Server dimensionato per il carico di produzione.

---

## Riferimenti

- [Azure Database for PostgreSQL Flexible Server — VNet Integration](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-networking-private)
- [pg_dump / pg_restore](https://www.postgresql.org/docs/current/app-pgdump.html)
- [UYUNI SSL Configuration](https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/ssl-certs.html)
