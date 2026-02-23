# Uyuni — Guida Amministrazione e Troubleshooting

> Ambiente: **UYUNI 2025.10** su **openSUSE Leap 15.6**, deployment containerizzato con **Podman**, Azure.
> Server: `10.172.2.17` | Proxy: `10.172.2.20`

---

## Architettura di Riferimento

### Server (2 container)

| Container | Funzione |
|---|---|
| `uyuni-server` | Tomcat (Web UI), Salt Master, Taskomatic, Apache, Cobbler |
| `uyuni-db` | PostgreSQL dedicato |

**Storage Server:**

```
sda → /                   (OS disk, 64GB)
sdb → /manager_storage    (repo + container storage, LVM: vg_uyuni_repo/lv_repo)
sdc → /pgsql_storage      (PostgreSQL data, LVM: vg_uyuni_pgsql/lv_pgsql)
/var/lib/containers       → symlink a /manager_storage/containers
```

### Proxy (5 container in un pod)

| Container | Funzione |
|---|---|
| `proxy-httpd` | HTTP/HTTPS + scrittura systemid |
| `proxy-salt-broker` | Relay eventi Salt tra client e Server |
| `proxy-squid` | Cache pacchetti locale |
| `proxy-ssh` | SSH tunneling per push clients |
| `proxy-tftpd` | PXE boot per provisioning |

**Storage Proxy:**

```
sda → /                   (OS disk)
sdb → /proxy_storage      (cache Squid, LVM: vg_proxy_cache/lv_cache)
/var/lib/containers       → symlink a /proxy_storage/containers
```

---

## Diagnostica Rapida — Primo Intervento

### 1. Stato generale (primo comando da eseguire sempre)

```bash
# Server
mgradm status

# Proxy
mgrpxy status
```

### 2. Stato container

```bash
podman ps                  # Container attivi
podman ps -a               # Tutti i container (anche fermati/crashed)
podman pod ps              # Stato pod (solo Proxy)
```

**Output atteso Server:**
```
NAMES          STATUS
uyuni-server   Up (healthy)
uyuni-db       Up (healthy)
```

**Output atteso Proxy:**
```
NAMES                STATUS
proxy-httpd          Up (healthy)
proxy-salt-broker    Up (healthy)
proxy-squid          Up (healthy)
proxy-ssh            Up (healthy)
proxy-tftpd          Up (healthy)
```

### 3. Stato servizi systemd

```bash
# Server
systemctl status uyuni-server
systemctl status uyuni-db

# Proxy
systemctl status uyuni-proxy-pod
systemctl status uyuni-proxy-httpd
```

### 4. Stato storage (causa piu' comune di crash)

```bash
df -h                                         # Panoramica tutti i dischi
df -h /manager_storage /pgsql_storage /       # Server: dischi critici
df -h /proxy_storage /                        # Proxy: dischi critici
```

> **REGOLA**: Se qualsiasi disco e' al 100%, Podman smette di funzionare completamente.
> Il sintomo e' `Error: updating container state: unable to open database file`.

### 5. Log container

```bash
podman logs uyuni-server --tail 100
podman logs uyuni-db --tail 50

# Proxy
podman logs proxy-httpd --tail 100
podman logs proxy-salt-broker --tail 50
podman logs proxy-squid --tail 50
```

```bash
# Follow in tempo reale
podman logs -f uyuni-server
podman logs -f proxy-httpd
```

### 6. Log systemd

```bash
journalctl -u uyuni-server -f
journalctl -u uyuni-db -f
journalctl -u uyuni-proxy-pod -f
```

---

## Gestione Servizi

### Server

```bash
# Avvio/Stop/Restart tramite mgradm (metodo preferito)
mgradm start
mgradm stop
mgradm restart

# Tramite systemd (se mgradm non funziona)
systemctl start uyuni-db
sleep 20                              # Il DB deve partire prima del server
systemctl start uyuni-server

systemctl stop uyuni-server
systemctl stop uyuni-db

systemctl restart uyuni-server
systemctl restart uyuni-db

# Reset dopo troppi fallimenti (systemd blocca dopo 5 tentativi)
systemctl reset-failed uyuni-server.service uyuni-db.service
systemctl start uyuni-db
sleep 20
systemctl start uyuni-server
```

### Proxy

```bash
# Tramite mgrpxy (metodo preferito)
mgrpxy start
mgrpxy stop

# Tramite systemd
systemctl start uyuni-proxy-pod
systemctl stop uyuni-proxy-pod
systemctl restart uyuni-proxy-pod

# Riavviare solo un container specifico
podman restart proxy-httpd
podman restart proxy-salt-broker
podman restart proxy-squid

# Reset dopo fallimenti
systemctl reset-failed uyuni-proxy-pod.service
systemctl start uyuni-proxy-pod
```

### Accesso shell ai container

```bash
# Server: shell interattiva
mgrctl term

# Server: eseguire un singolo comando
mgrctl exec -- <comando>
mgrctl exec -- systemctl status tomcat.service --no-pager
mgrctl exec -- systemctl status salt-master.service --no-pager
mgrctl exec -- systemctl status taskomatic.service --no-pager

# Database: shell psql
podman exec -it uyuni-db psql -U spacewalk

# Proxy: shell in un container specifico
podman exec -it proxy-httpd bash
podman exec -it proxy-squid bash
```

---

## Problemi Comuni e Soluzioni

### Problema 1: Podman non funziona — "unable to open database file"

**Sintomo:**
```
Error: updating container state: unable to open database file: no such file or directory
```
Tutti i comandi `podman` falliscono, incluso `podman ps`.

**Causa:** Il disco che ospita `/var/lib/containers` (symlink a `/manager_storage/containers` sul Server o `/proxy_storage/containers` sul Proxy) e' pieno. Podman non riesce ad aprire/scrivere il suo database SQLite di stato.

**Diagnosi:**
```bash
df -h
# Cercare righe con Use% = 100%
```

**Soluzione:** Liberare spazio (vedi sezione Storage) prima di qualsiasi altra operazione.

---

### Problema 2: I container non partono — "Start request repeated too quickly"

**Sintomo in `systemctl status`:**
```
uyuni-server.service: Start request repeated too quickly.
uyuni-server.service: Failed with result 'exit-code'.
```

**Causa:** Systemd ha raggiunto il limite di restart (5 tentativi). Non ritenta piu'.

**Soluzione:**
```bash
systemctl reset-failed uyuni-server.service uyuni-db.service
# Poi avviare normalmente (vedi sezione Gestione Servizi)
```

---

### Problema 3: Storage pieno — /manager_storage al 100%

**Diagnosi approfondita:**
```bash
du -sh /manager_storage/* 2>/dev/null | sort -rh | head -20

# Pacchetti sincronizzati per canale
du -sh /manager_storage/packages/* 2>/dev/null | sort -rh | head -10

# Immagini container
du -sh /manager_storage/containers/* 2>/dev/null | sort -rh | head -10

# Uso storage Podman (funziona solo se podman e' operativo)
podman system df
```

**Pulizia sicura:**
```bash
# Rimuovi immagini container non usate (con podman operativo)
podman image prune -a

# Rimuovi volumi orfani
podman volume prune

# Pulizia completa cache Podman
podman system prune -a

# Pulizia cache repository Uyuni (dall'interno del container)
mgrctl exec -- spacewalk-repo-sync --clean-cache
```

**Se podman non funziona (disco pieno), pulizia manuale:**
```bash
# Trova file grandi
find /manager_storage -size +1G -type f 2>/dev/null | sort

# Rimuovi file temporanei
find /manager_storage -name "*.tmp" -delete
find /manager_storage -name "*.log" -size +100M

# Rimuovi immagini container manualmente (solo se sicuro)
# Le immagini sono in /manager_storage/containers/storage/overlay/
ls -lh /manager_storage/containers/storage/overlay/ | sort -k5 -rh
```

---

### Problema 4: Espansione disco LVM (Azure)

Usare quando il disco fisico e' stato espanso da Azure Portal ma la partizione/LVM non vede ancora lo spazio.

**Step 1 — Forza la rilettura del disco dal kernel:**
```bash
echo 1 > /sys/class/block/sdb/device/rescan
lsblk /dev/sdb
```

**Step 2 — Espandi la partizione** (necessario se il PV e' su partizione, non su disco raw):
```bash
growpart /dev/sdb 1
# Se non installato: zypper install cloud-utils-growpart

lsblk /dev/sdb   # Verifica che sdb1 abbia la nuova dimensione
```

**Step 3 — Espandi il Physical Volume LVM:**
```bash
pvresize /dev/sdb1
pvs                          # Verifica PFree aumentata
```

**Step 4 — Espandi il Logical Volume:**
```bash
lvextend -l +100%FREE /dev/vg_uyuni_repo/lv_repo

# Per Proxy:
lvextend -l +100%FREE /dev/vg_proxy_cache/lv_cache
```

**Step 5 — Espandi il filesystem (online, senza umount):**
```bash
df -T /manager_storage       # Verifica tipo filesystem

# Se XFS (default su openSUSE):
xfs_growfs /manager_storage

# Se ext4:
resize2fs /dev/mapper/vg_uyuni_repo-lv_repo
```

**Step 6 — Verifica:**
```bash
df -h /manager_storage
```

---

### Problema 5: Database PostgreSQL non raggiungibile

**Diagnosi:**
```bash
# Verifica che il container db sia in running
podman ps | grep uyuni-db

# Test connessione diretta
podman exec -it uyuni-db psql -U spacewalk -c "SELECT 1;"

# Log database
podman logs uyuni-db --tail 100

# Verifica spazio disco PostgreSQL
df -h /pgsql_storage
```

**Soluzione:**
```bash
# Riavvia prima il DB, poi il server
systemctl restart uyuni-db
sleep 30
systemctl restart uyuni-server
```

---

### Problema 6: Problemi DNS / Hostname

**Sintomo:** Salt non raggiunge i client, o il Proxy non trova il Server.

**Diagnosi:**
```bash
# Sull'host
hostname -f                               # Deve restituire FQDN completo

# All'interno del container Server
mgrctl exec -- hostname -f
mgrctl exec -- ping -c 1 uyuni-proxy-test.uyuni.internal

# Dal proxy verso il server
ping uyuni-server-test.uyuni.internal
nc -zv uyuni-server-test.uyuni.internal 443
nc -zv uyuni-server-test.uyuni.internal 4505
nc -zv uyuni-server-test.uyuni.internal 4506
```

> **NOTA:** Il `/etc/hosts` dentro il container Podman e' gestito da Podman e non accetta modifiche permanenti. L'unica soluzione affidabile e' Azure Private DNS Zone oppure aggiornare `/etc/hosts` sull'host prima di avviare i container.

---

### Problema 7: Problemi certificati SSL

```bash
# Verifica certificato attivo nel container Server
mgrctl exec -- openssl x509 -in /etc/pki/tls/certs/spacewalk.crt -text -noout

# Verifica validita' da esterno
openssl s_client -connect uyuni-server-test.uyuni.internal:443 </dev/null 2>/dev/null | openssl x509 -noout -dates

# Proxy: verifica certificato
podman exec proxy-httpd openssl x509 -in /etc/pki/tls/certs/spacewalk.crt -text -noout

# Reset password admin
mgrctl exec -- satpasswd -u admin
```

---

### Problema 8: Proxy — Checksum Mismatch (HTTP 500 / Invalid System Credentials)

**Sintomo:** I client ricevono errori HTTP 500 dal proxy. Nel log del Server:
```
Checksum check failed: EXPECTED != RECEIVED
```

**Causa:** Il checksum nel `systemid` del proxy non corrisponde a quello nel database del Server. Succede tipicamente dopo un bootstrap Salt eseguito nel momento sbagliato.

**Diagnosi:**
```bash
# Verifica checksum nel systemid del proxy
grep -oP 'checksum.*?<string>\K[^<]+' /etc/sysconfig/rhn/systemid

# Verifica cosa si aspetta il server
mgrctl exec -- tail -20 /var/log/rhn/rhn_server_xmlrpc.log
```

**Soluzione (procedura completa):**
```bash
# 1. Sul Server (Web UI): Systems → uyuni-proxy-test → Delete System
#    (usare sempre la Web UI, spacecmd ha un bug con i proxy)

# 2. Elimina la salt key se presente
mgrctl exec -- salt-key -d uyuni-proxy-test.uyuni.internal -y

# 3. Rigenera config.tar.gz fresco dal Server
mgrctl exec -ti -- spacecmd proxy_container_config_generate_cert -- \
  uyuni-proxy-test.uyuni.internal \
  uyuni-server-test.uyuni.internal \
  38000 \
  admin@example.com \
  -o /tmp/config.tar.gz \
  -p 8022

# 4. Trasferisci il config al proxy
mgrctl cp server:/tmp/config.tar.gz /tmp/proxy-config.tar.gz
# poi copiare al proxy via SCP o altro metodo

# 5. Sul Proxy: reinstalla
mgrpxy install podman /tmp/uyuni-proxy-test-config.tar.gz

# 6. Applica il fix directory systemid e avvia
mkdir -p /etc/sysconfig/rhn
chmod 755 /etc/sysconfig/rhn
systemctl daemon-reload
systemctl start uyuni-proxy-pod
sleep 5
systemctl start uyuni-proxy-httpd
```

> **Regola d'oro:** NON eseguire mai il bootstrap Salt tra la generazione del `config.tar.gz` e l'installazione `mgrpxy install`.

---

### Problema 9: Proxy — systemid vuoto o permessi errati

**Sintomo:** `proxy-httpd` crasha con `FileNotFoundError: '/etc/sysconfig/rhn/systemid'` o `systemid has wrong permissions`.

**Diagnosi:**
```bash
cat /etc/sysconfig/rhn/systemid             # Deve contenere XML con ID-XXXXXXXXXX
ls -la /etc/sysconfig/rhn/                  # Permessi: dir 755, file 644
```

**Soluzione:**
```bash
# Se la directory manca
mkdir -p /etc/sysconfig/rhn
chmod 755 /etc/sysconfig/rhn
# NON creare il file systemid manualmente — lo crea il container al primo avvio

# Se i permessi sono sbagliati (dopo bootstrap Salt)
chmod 755 /etc/sysconfig/rhn
chmod 644 /etc/sysconfig/rhn/systemid
podman restart proxy-httpd
```

---

### Problema 10: Client Salt non risponde / offline

**Diagnosi:**
```bash
# Dal Server: verifica minion accettato
mgrctl exec -- salt-key -L

# Dal Server: test ping
mgrctl exec -- salt 'nome-client' test.ping

# Dal client: verifica configurazione master
cat /etc/venv-salt-minion/minion.d/susemanager.conf   # Ubuntu/RHEL con venv
cat /etc/salt/minion.d/susemanager.conf                # Salt standard

# Dal client: verifica connettivita' al Server o Proxy
nc -zv uyuni-server-test.uyuni.internal 4505
nc -zv uyuni-server-test.uyuni.internal 4506

# Dal client: log Salt minion
journalctl -u venv-salt-minion -f
journalctl -u salt-minion -f
```

**Soluzione: reindirizza client al Proxy (CLI):**
```bash
# venv-salt-minion (Ubuntu/RHEL con bootstrap)
sed -i 's/uyuni-server-test.uyuni.internal/uyuni-proxy-test.uyuni.internal/' \
  /etc/venv-salt-minion/minion.d/susemanager.conf
systemctl restart venv-salt-minion

# salt-minion standard
sed -i 's/uyuni-server-test.uyuni.internal/uyuni-proxy-test.uyuni.internal/' \
  /etc/salt/minion.d/susemanager.conf
systemctl restart salt-minion
```

---

## Monitoraggio Continuo

### Health check rapido

```bash
# Server — tutti i servizi critici in un colpo
echo "=== Container ===" && podman ps --format "{{.Names}}\t{{.Status}}"
echo "=== Disco ===" && df -h /manager_storage /pgsql_storage / | grep -v tmpfs
echo "=== RAM ===" && free -h
echo "=== NTP ===" && timedatectl status | grep synchronized
```

### Log interni Uyuni (dentro il container Server)

```bash
mgrctl exec -- tail -f /var/log/rhn/rhn_server_xmlrpc.log     # API calls
mgrctl exec -- tail -f /var/log/rhn/rhn_server_satellite.log   # Salt events
mgrctl exec -- tail -f /var/log/tomcat/catalina.out            # Tomcat/Web UI
mgrctl exec -- tail -f /var/log/salt/master                    # Salt Master
mgrctl exec -- tail -f /var/log/taskomatic/taskomatic.log      # Job scheduler
```

### Verifica sincronizzazione NTP (critica per Salt e certificati)

```bash
timedatectl status
chronyc sources -v
```

---

## Quick Reference — Comandi Piu' Usati

### Server

```bash
mgradm status                              # Stato generale
mgradm restart                             # Riavvia tutto
podman ps                                  # Container attivi
podman logs uyuni-server --tail 100        # Log server
podman logs uyuni-db --tail 50             # Log database
mgrctl term                                # Shell nel container
mgrctl exec -- salt '*' test.ping          # Ping tutti i client
df -h /manager_storage /pgsql_storage      # Stato storage
podman system df                           # Uso storage container
lvs && vgs                                 # Stato LVM
```

### Proxy

```bash
mgrpxy start / stop                        # Gestione proxy
podman ps                                  # Container attivi
podman pod ps                              # Stato pod
podman logs proxy-httpd --tail 100         # Log httpd
podman logs proxy-salt-broker --tail 50    # Log salt broker
podman logs proxy-squid --tail 50          # Log cache
df -h /proxy_storage                       # Stato disco cache
cat /etc/sysconfig/rhn/systemid            # Verifica systemid
```

### LVM Storage

```bash
lsblk                                      # Layout dischi
pvs                                        # Physical volumes
vgs                                        # Volume groups
lvs                                        # Logical volumes
df -h                                      # Spazio filesystem
growpart /dev/sdb 1                        # Espandi partizione (post-Azure resize)
pvresize /dev/sdb1                         # Aggiorna PV dopo growpart
lvextend -l +100%FREE /dev/vg_uyuni_repo/lv_repo  # Espandi LV
xfs_growfs /manager_storage               # Espandi filesystem XFS
```

---

## Tabella Diagnostica — Errore → Causa → Azione

| Errore / Sintomo | Causa probabile | Prima azione |
|---|---|---|
| `unable to open database file` | Disco pieno (Podman DB su disco saturo) | `df -h` → libera spazio |
| `Start request repeated too quickly` | Systemd ha esaurito i tentativi | `systemctl reset-failed` |
| HTTP 500 sui client via proxy | Checksum mismatch systemid | Vedi Problema 8 |
| `FileNotFoundError: systemid` | Directory `/etc/sysconfig/rhn` mancante | `mkdir -p /etc/sysconfig/rhn && chmod 755` |
| Salt client offline | DNS, porte firewall, master config | `nc -zv server 4505` dal client |
| `Could not resolve hostname` | DNS non configurato nel container | Aggiungi a `/etc/hosts` host, usa Azure DNS |
| Container `Exited (137)` | OOM kill | `free -h` → la VM ha poca RAM |
| `System clock synchronized: no` | NTP non sincronizzato | `systemctl restart chronyd` |
| Web UI non risponde | Tomcat down | `mgrctl exec -- systemctl status tomcat` |
| Repo sync lento/bloccato | Disco quasi pieno o rete | `df -h` + `podman logs uyuni-server` |
