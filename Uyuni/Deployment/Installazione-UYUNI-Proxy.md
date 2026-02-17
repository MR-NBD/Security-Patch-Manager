Installazione di **UYUNI Proxy 2025.10** su **openSUSE Leap 15.6** in ambiente **Azure** con deployment containerizzato tramite **Podman**.
### Architettura Target
```
UYUNI Server (10.172.2.17)
        │
        │ Salt 4505/4506 + HTTPS 443
        │
UYUNI Proxy (10.172.2.20)
        │
        ├── Ubuntu Client #1
        ├── Ubuntu Client #2
        └── RHEL 9 Client
```
### Componenti Container (Proxy 2025.10)

| Container | Funzione |
|-----------|----------|
| **proxy-httpd** | HTTP/HTTPS - repository pacchetti e Web forwarding |
| **proxy-salt-broker** | Broker Salt events tra client e Server |
| **proxy-squid** | Cache proxy per pacchetti (riduce traffico verso Server) |
| **proxy-ssh** | SSH tunneling per push clients |
| **proxy-tftpd** | TFTP per PXE boot (provisioning automatico) |

> La dimensione del disco cache Squid determina quanti pacchetti vengono serviti localmente senza contattare il Server. Più grande è, meno traffico di rete tra Proxy e Server. Impostare Squid cache al massimo **60% dello spazio disponibile** sul disco cache.
## DEPLOYMENT
### Configurazione VM Azure

| Parametro          | Valore                              |
| ------------------ | ----------------------------------- |
| **Subscription**   | ASL0603-spoke10                     |
| **Resource Group** | test_group                          |
| **VM Name**        | uyuni-proxy-test                    |
| **Region**         | Italy North                         |
| **Availability**   | Availability Zone 1                 |
| **Security Type**  | Trusted launch (Secure boot + vTPM) |
| **Image**          | openSUSE Leap 15.6 - Gen2           |
| **Architecture**   | x64                                 |
| **Size**           | Standard_B2s (2 vCPU, 4 GB RAM)     |
| **Username**       | azureuser                           |
| **Authentication** | Password                            |
| **OS Disk**        | 40 GB Standard SSD LRS              |
| **Data Disks**     | 1 disco (64 GB) per cache pacchetti |
| **VNet**           | ASL0603-spoke10-spoke-italynorth    |
| **Subnet**         | default (10.172.2.0/24)             |
| **Public IP**      | None                                |
| **NSG**            | uyuni-proxy-test-nsg                |
### Configurazione NSG

| Priority | Nome               | Port      | Protocol | Source        | Destination | Action |
| -------- | ------------------ | --------- | -------- | ------------- | ----------- | ------ |
| 100      | AllowHTTPS_Clients | 443       | TCP      | 10.172.2.0/24 | 10.172.2.20 | Allow  |
| 110      | AllowSalt_Clients  | 4505-4506 | TCP      | 10.172.2.0/24 | 10.172.2.20 | Allow  |
| 120      | AllowHTTPS_Server  | 443       | TCP      | 10.172.2.17   | 10.172.2.20 | Allow  |
| 130      | AllowSalt_Server   | 4505-4506 | TCP      | 10.172.2.17   | 10.172.2.20 | Allow  |
| 140      | AllowSSHPush       | 8022      | TCP      | 10.172.2.0/24 | 10.172.2.20 | Allow  |

**Outbound** (dal Proxy):

| Priority | Nome                | Port      | Protocol | Source      | Destination | Action |
| -------- | ------------------- | --------- | -------- | ----------- | ----------- | ------ |
| 100      | AllowHTTPS_ToServer | 443       | TCP      | 10.172.2.20 | 10.172.2.17 | Allow  |
| 110      | AllowSalt_ToServer  | 4505-4506 | TCP      | 10.172.2.20 | 10.172.2.17 | Allow  |
## FASE 1: Preparazione del Sistema Base
### Dalla VM
#### Diventa root
```bash
sudo su -
```
#### Verifica versione OS
```bash
cat /etc/os-release
```
Output atteso:
```
NAME="openSUSE Leap"
VERSION="15.6"
```
### Aggiornamento Sistema
```bash
zypper refresh
```
```bash
zypper update -y
```
#### Riavvia per applicare aggiornamenti kernel
```bash
reboot
```
### Installazione Pacchetti Prerequisiti
```bash
zypper install -y \
  chrony \
  podman \
  firewalld \
  nano \
  wget \
  curl \
  jq
```
## FASE 2: Configurazione NTP con Chrony
La sincronizzazione temporale è **CRITICA** per il corretto funzionamento di Salt e i certificati SSL.
### Configurazione Chrony
#### Backup configurazione originale
```bash
cp /etc/chrony.conf /etc/chrony.conf.bak
```
#### Modifica configurazione
```bash
nano /etc/chrony.conf
```
Configurazione:
```
# Server NTP (sostituire con i propri server aziendali)
server ntp1.inrim.it iburst
server ntp2.inrim.it iburst
pool pool.ntp.org iburst

# Permetti sincronizzazione rapida all'avvio
makestep 1.0 3

# Registra le statistiche
logdir /var/log/chrony

# Drift file
driftfile /var/lib/chrony/drift
```
### Abilita e Avvia il Servizio
```bash
systemctl enable --now chronyd
```
#### Abilita NTP via timedatectl
```bash
timedatectl set-ntp true
```
#### Verificare stato sincronizzazione
```bash
timedatectl status
```

Output atteso:
```
System clock synchronized: yes
NTP service: active
```
## FASE 3: Configurazione Hostname e DNS
### Configurare l'Hostname
#### Impostare hostname
```bash
hostnamectl set-hostname uyuni-proxy-test.uyuni.internal
```
#### Verificare hostname
```bash
hostname -f
```
### Configura il File /etc/hosts
#### Recuperare l'IP privato della VM
```bash
ip addr show eth0
```
#### Editare il file hosts
```bash
nano /etc/hosts
```
Aggiungere:
```
10.172.2.20    uyuni-proxy-test.uyuni.internal    uyuni-proxy-test
10.172.2.17    uyuni-server-test.uyuni.internal    uyuni-server-test
```

> Il Proxy DEVE risolvere l'FQDN del Server UYUNI. Aggiungere anche l'entry del Server nel file hosts se non si usa Azure Private DNS Zone.
### Verificare la Configurazione DNS
#### Test risoluzione diretta
```bash
ping -c 2 $(hostname -f)
```
#### Test risoluzione Server
```bash
ping -c 2 uyuni-server-test.uyuni.internal
```
## FASE 4: Configurazione Firewall
### Abilitare Firewalld
```bash
systemctl enable --now firewalld
```
### Configurare Porte Proxy
#### HTTPS (Web UI e repository pacchetti)
```bash
firewall-cmd --permanent --add-port=443/tcp
```
#### HTTP (repository pacchetti)
```bash
firewall-cmd --permanent --add-port=80/tcp
```
#### Salt (comunicazione con client e Server)
```bash
firewall-cmd --permanent --add-port=4505/tcp
firewall-cmd --permanent --add-port=4506/tcp
```
#### SSH Push (per contact method ssh-push)
```bash
firewall-cmd --permanent --add-port=8022/tcp
```
### Applicare le Modifiche
```bash
firewall-cmd --reload
```
### Verifica Configurazione
```bash
firewall-cmd --list-all
```

Output atteso:
```
ports: 80/tcp 443/tcp 4505/tcp 4506/tcp 8022/tcp
```
## FASE 5: Configurazione Storage Cache
### Identificare il Disco Dati
```bash
lsblk
```
### Configurazione LVM per disco cache (es. /dev/sdb)
#### Creare partizione
```bash
parted /dev/sda --script mklabel gpt
parted /dev/sda --script mkpart primary 0% 100%
```
#### Configura LVM
```bash
pvcreate /dev/sda1
vgcreate vg_proxy_cache /dev/sda1
lvcreate -l 100%FREE -n lv_cache vg_proxy_cache
```
#### Formatta XFS
```bash
mkfs.xfs /dev/mapper/vg_proxy_cache-lv_cache
```
#### Crea mount point e monta
```bash
mkdir -p /proxy_storage
mount /dev/mapper/vg_proxy_cache-lv_cache /proxy_storage
```
#### Aggiungi a fstab
```bash
echo "/dev/mapper/vg_proxy_cache-lv_cache /proxy_storage xfs defaults,nofail 0 0" >> /etc/fstab
```
#### Reload systemd
```bash
systemctl daemon-reload
```
### Spostare Container Storage su proxy_storage

```bash
# Crea directory per containers
mkdir -p /proxy_storage/containers

# Ferma eventuali container attivi
systemctl stop podman.socket

# Sposta dati esistenti (se presenti)
mv /var/lib/containers/* /proxy_storage/containers/ 2>/dev/null || true

# Rimuovi directory originale
rm -rf /var/lib/containers

# Crea symlink
ln -s /proxy_storage/containers /var/lib/containers

# Riavvia Podman
systemctl start podman.socket
```

Eseguire questa operazione PRIMA di installare il Proxy.
### Verificare Configurazione Storage
```bash
df -hP /proxy_storage
lvs
```
## FASE 6: Installazione Repository e Pacchetti Proxy
### Aggiungere Repository UYUNI Proxy
```bash
zypper ar https://download.opensuse.org/repositories/systemsmanagement:/Uyuni:/Stable/images/repo/Uyuni-Proxy-POOL-$(arch)-Media1/ uyuni-proxy-stable
```
### Refresh e Installazione
#### Accettare chiave GPG e refresh
```bash
zypper --gpg-auto-import-keys refresh
```
#### Installare tool di gestione Proxy
```bash
zypper install -y mgrpxy mgrpxy-bash-completion uyuni-storage-setup-proxy
```
### Verificare Versione Podman
```bash
podman --version
```

UYUNI richiede Podman >= 4.5.0
### Abilitare Podman Socket
```bash
systemctl enable --now podman.socket
```
## FASE 7: Preparare l'Host Proxy per la Comunicazione Salt

> NON eseguire il bootstrap Salt separatamente prima della FASE 8. Il comando `proxy_container_config_generate_cert` nella FASE 8 crea una registrazione tradizionale (systemid) con un checksum. Se si esegue il bootstrap Salt PRIMA o DOPO la generazione del config, il bootstrap modifica il checksum sul server causando un mismatch: il proxy tenta di autenticarsi con il checksum del config, ma il server si aspetta quello del bootstrap, risultando in errore `Invalid System Credentials` e HTTP 500 su ogni richiesta dei client.

### Sull'Host Proxy: Installare Salt Minion e Certificato CA
Questa fase prepara il minion Salt sull'host proxy senza registrarlo formalmente. Il Salt minion servirà per la gestione post-installazione.
```bash
# Scaricare il certificato CA del Server
curl -Sks https://uyuni-server-test.uyuni.internal/pub/RHN-ORG-TRUSTED-SSL-CERT -o /etc/pki/trust/anchors/uyuni-ca.crt
update-ca-certificates
```

### Sul Server UYUNI: Creare Activation Key per il Proxy (opzionale)
Dalla **Web UI** del Server UYUNI (`https://uyuni-server-test.uyuni.internal`):

1. **Systems → Activation Keys → Create Key**
2. Configurare:

| Campo                   | Valore                                              |
| ----------------------- | --------------------------------------------------- |
| **Key**                 | `1-proxy-asl06-test`                                |
| **Description**         | Activation key per Uyuni Proxy - openSUSE Leap 15.6 |
| **Base Channel**        | Uyuni Default                                       |
| **Add-On Entitlements** | Container Build Host                                |
| **Contact Method**      | Default                                             |

> Se hai i canali openSUSE Leap 15.6 sincronizzati sul Server, puoi selezionarli esplicitamente come Base Channel. Altrimenti usa "Universal Default" e Uyuni auto-detecterà l'OS.

3. **Create Activation Key**

## FASE 8: Generare Configurazione Proxy e Certificato SSL
### Opzione A: Via Web UI

1. Sul Server UYUNI, andare su **Systems → Proxy Configuration**
2. Compilare i campi principali:

| Campo                    | Valore                             |
| ------------------------ | ---------------------------------- |
| **Proxy FQDN**           | `uyuni-proxy-test.uyuni.internal`  |
| **Parent FQDN**          | `uyuni-server-test.uyuni.internal` |
| **Proxy SSH Port**       | `8022`                             |
| **Max Squid Cache [MB]** | `38000` (60% di 64 GB)             |
| **SSL Certificate**      | Generate                           |

3. Per la sezione SSL, servono i **file CA del Server UYUNI**. Recuperarli dal Server:
#### Recuperare i file CA dal container Server
```bash
sudo podman cp uyuni-server:/root/ssl-build/RHN-ORG-TRUSTED-SSL-CERT /tmp/ca.crt
sudo podman cp uyuni-server:/root/ssl-build/RHN-ORG-PRIVATE-SSL-KEY /tmp/ca.key
```

> Il file `ca.key` è accessibile solo da root. Se WinSCP restituisce "Permission denied", eseguire sul Server:
> ```bash
> sudo chmod 644 /tmp/ca.key
> ```
> **Dopo il trasferimento**, ripristinare i permessi e cancellare le copie:
> ```bash
> sudo chmod 600 /tmp/ca.key
> sudo rm /tmp/ca.crt /tmp/ca.key
> ```

4. Trasferire i file CA sul proprio PC tramite WinSCP (connessione SSH al Server `10.172.2.17`, navigare a `/tmp/`)

5. Caricare i file nel form Web UI:

| Campo              | File                                                  |
| ------------------ | ----------------------------------------------------- |
| **CA certificate** | `ca.crt` (RHN-ORG-TRUSTED-SSL-CERT)                   |
| **CA private key** | `ca.key` (RHN-ORG-PRIVATE-SSL-KEY)                    |
| **CA password**    | La password CA scelta durante `mgradm install podman` |

6. Compilare i dati del certificato SSL:

| Campo                     | Valore                             |
| ------------------------- | ---------------------------------- |
| **Alternate CNAMEs**      | (vuoto, oppure `uyuni-proxy-test`) |
| **2-letter country code** | `IT`                               |
| **State**                 | Regione (es. `Lazio`)              |
| **City**                  | Città                              |
| **Organization**          | Nome azienda                       |
| **Organization Unit**     | `IT`                               |
| **Email**                 | Email admin                        |

7. Cliccare **Generate**
8. Scaricare il file `config.tar.gz` generato

> Il certificato generato NON è self-signed. Viene firmato dalla CA interna di Uyuni (creata durante l'installazione del Server). Tutti i client che si fidano già del Server si fideranno anche del Proxy.

### Opzione B: Via spacecmd (CLI — evita il trasferimento dei file CA)
Dal Server UYUNI, questo comando usa la CA già presente nel container senza bisogno di trasferire file:
```bash
mgrctl exec -ti 'spacecmd proxy_container_config_generate_cert -- \
  uyuni-proxy-test.uyuni.internal \
  uyuni-server-test.uyuni.internal \
  38000 \
  admin@example.com \
  -o /tmp/config.tar.gz \
  -p 8022'
```

> Per certificati firmati dalla CA aziendale, vedere sezione "Certificati Custom per Production" in fondo.
## FASE 9: Installazione Container Proxy
### Sull'Host Proxy: Installare i Container
```bash
sudo su -
mgrpxy install podman /tmp/uyuni-proxy-test-config.tar.gz
```

L'installazione:
- Scarica le 5 immagini container dal registry
- Configura il pod `uyuni-proxy-pod`
- Crea il servizio systemd
- Abilita IPv4/IPv6 forwarding
### Fix Bug: Volume mount mancante per systemid

> L'immagine `proxy-httpd` esegue all'avvio lo script `uyuni-configure.py` che legge il `system_id` dal file `httpd.yaml` (contenuto nel config.tar.gz) e lo scrive in `/etc/sysconfig/rhn/systemid`. Tuttavia la directory `/etc/sysconfig/rhn/` non viene montata dal servizio systemd generato da `mgrpxy`. Senza questo fix, il container httpd crasha con errore `FileNotFoundError: '/etc/sysconfig/rhn/systemid'`.

> Creare SOLO la directory, **NON** il file `systemid`. Lo script `uyuni-configure.py` controlla `if not os.path.exists("/etc/sysconfig/rhn/systemid")` prima di scrivere: se trova un file già esistente (anche vuoto), **salta la scrittura** e il systemid resta vuoto. Il file deve essere creato dallo script stesso al primo avvio del container.

#### Creare SOLO la directory sull'host (NON il file)
```bash
mkdir -p /etc/sysconfig/rhn
chmod 755 /etc/sysconfig/rhn
# NON eseguire: touch /etc/sysconfig/rhn/systemid
# Il file verrà creato automaticamente dal container con il contenuto corretto
```

> La directory DEVE avere permessi `755` e il file systemid (una volta creato dal container) deve avere permessi `644`. Con permessi restrittivi (`750` sulla directory o `640` sul file), il processo Apache (wwwrun) all'interno del container non può leggere il systemid e restituisce l'errore `unable to access /etc/sysconfig/rhn/systemid` o `systemid has wrong permissions`.
> Se dopo un bootstrap Salt i permessi cambiano, correggerli con:
> ```bash
> chmod 755 /etc/sysconfig/rhn
> chmod 644 /etc/sysconfig/rhn/systemid
> podman restart uyuni-proxy-httpd
> ```
#### Aggiungere il volume mount al service file
```bash
sed -i 's|-v /etc/sysconfig/proxy:/etc/sysconfig/proxy:ro|-v /etc/sysconfig/proxy:/etc/sysconfig/proxy:ro \\\n-v /etc/sysconfig/rhn:/etc/sysconfig/rhn|' /etc/systemd/system/uyuni-proxy-httpd.service
```
#### Verificare la modifica
```bash
grep sysconfig /etc/systemd/system/uyuni-proxy-httpd.service
```
Output atteso:
```
-v /etc/sysconfig/proxy:/etc/sysconfig/proxy:ro \
-v /etc/sysconfig/rhn:/etc/sysconfig/rhn \
```
#### Ricaricare e avviare
```bash
systemctl daemon-reload
systemctl start uyuni-proxy-pod
sleep 2
systemctl start uyuni-proxy-httpd
```
#### Verificare che il systemid sia stato popolato
```bash
cat /etc/sysconfig/rhn/systemid
```
Output atteso: XML contenente `<string>ID-XXXXXXXXXX</string>` con l'ID del sistema proxy. Se il file è vuoto, verificare che non sia stato creato manualmente prima dell'avvio del container.
### Verificare Container Attivi
```bash
podman ps
```
Output atteso (5 container):
```
CONTAINER ID  IMAGE                                          STATUS         NAMES
xxxx          registry.opensuse.org/uyuni/proxy-httpd        Up (healthy)   proxy-httpd
xxxx          registry.opensuse.org/uyuni/proxy-salt-broker  Up (healthy)   proxy-salt-broker
xxxx          registry.opensuse.org/uyuni/proxy-squid        Up (healthy)   proxy-squid
xxxx          registry.opensuse.org/uyuni/proxy-ssh          Up (healthy)   proxy-ssh
xxxx          registry.opensuse.org/uyuni/proxy-tftpd        Up (healthy)   proxy-tftpd
```
### Verificare Pod
```bash
podman pod ps
```
### Abilitare Avvio Automatico
```bash
systemctl enable uyuni-proxy-pod uyuni-proxy-httpd uyuni-proxy-squid uyuni-proxy-tftpd uyuni-proxy-salt-broker uyuni-proxy-ssh
```
### Verificare dal Server UYUNI
Dalla Web UI:
1. **Systems → System List** → selezionare `uyuni-proxy-test`
2. Tab **Details → Proxy**
3. Verificare status: **Active**
4. Verificare System Type: deve mostrare **Proxy** (potrebbe mostrare anche **Foreign** se non è registrato via Salt)

### (Opzionale) Registrare il Proxy come Salt Minion
Se si vuole gestire il proxy come Salt minion (consigliato per management), eseguire il bootstrap **DOPO** l'installazione container:

Sull'**Host Proxy**:
```bash
curl -Sks https://uyuni-server-test.uyuni.internal/pub/bootstrap/bootstrap.sh | /bin/bash
```

Sul **Server UYUNI**:
```bash
mgrctl exec -- salt-key -a uyuni-proxy-test.uyuni.internal -y
mgrctl exec -- salt 'uyuni-proxy-test.uyuni.internal' test.ping
```

> Il bootstrap Salt modifica il checksum delle credenziali tradizionali sul server. Se dopo il bootstrap il proxy inizia a restituire errori HTTP 500 (`Invalid System Credentials`), è necessario rigenerare il config.tar.gz e reinstallare (vedi sezione Troubleshooting → Checksum Mismatch).
## FASE 10: Configurazione DNS per Server, Proxy e Client

> Il container del Server UYUNI ha un `/etc/hosts` separato dall'host, gestito da Podman e difficile da modificare. Se il Server non riesce a risolvere l'FQDN del Proxy, operazioni come il bootstrap dei client via Proxy falliranno con `Could not resolve hostname`.

Aggiungere su **ogni host** (server, proxy, client):
```bash
echo "10.172.2.17    uyuni-server-test.uyuni.internal    uyuni-server-test" >> /etc/hosts
echo "10.172.2.20    uyuni-proxy-test.uyuni.internal    uyuni-proxy-test" >> /etc/hosts
```

> Il `/etc/hosts` dentro il container Podman del Server è gestito da Podman e non accetta modifiche permanenti via `echo >>` o `sed`. Le modifiche vengono ignorate o sovrascritte al restart del container. Usare Azure Private DNS Zone è l'unica soluzione affidabile per la risoluzione DNS dal container Server.

## FASE 11: Ri-puntare i Client Esistenti al Proxy

Ora i 3 client (2 Ubuntu + 1 RHEL) devono essere reindirizzati dal Server diretto al Proxy.

> **Prerequisito**: La configurazione DNS della FASE 10 deve essere completata prima di procedere. Ogni client DEVE poter risolvere l'FQDN del Proxy.
### Opzione A: Via Web UI
Per **ogni client**:

1. **Systems → System List** → cliccare sul sistema
2. Tab **Details → Connection**
3. Cliccare **Change proxy**
4. Selezionare `uyuni-proxy-test.uyuni.internal` dal menu dropdown
5. Cliccare **Confirm**

Uyuni schedula un'azione che modifica la configurazione Salt del client e riavvia il Salt minion. Verificare lo stato in **Events → History**.

> Se dopo 5 minuti il client risulta offline ("Minion is down"), verificare che il DNS sia configurato correttamente sul client (prerequisito sopra).
### Opzione B: Via CLI (su ogni client manualmente)
Se la Web UI non applica le modifiche, procedere manualmente:
#### Modificare configurazione Salt minion
Per client con `venv-salt-minion` (Ubuntu/RHEL registrati con bootstrap):
```bash
sed -i 's/uyuni-server-test.uyuni.internal/uyuni-proxy-test.uyuni.internal/' /etc/venv-salt-minion/minion.d/susemanager.conf
systemctl restart venv-salt-minion
```

Per client con `salt-minion` standard:
```bash
sed -i 's/uyuni-server-test.uyuni.internal/uyuni-proxy-test.uyuni.internal/' /etc/salt/minion.d/susemanager.conf
systemctl restart salt-minion
```
#### Verificare connessione
```bash
salt-call test.ping
```
Output atteso:
```
local:
    True
```
### Verificare che i Client siano Connessi via Proxy
Dalla Web UI del Server:
1. **Systems → System List** → cliccare su un client
2. Tab **Details → Connection**
3. Verificare che **Proxy** mostri `uyuni-proxy-test.uyuni.internal`

Dalla pagina del Proxy:
1. **Systems → System List** → `uyuni-proxy-test`
2. Tab **Details → Proxy**
3. Deve elencare i client connessi tramite questo proxy
## Troubleshooting
### I container Proxy non si avviano

```bash
# Verificare logs di ogni container
podman logs proxy-httpd
podman logs proxy-salt-broker
podman logs proxy-squid

# Verificare stato pod
podman pod ps

# Riavviare
mgrpxy stop
mgrpxy start

# Oppure via systemd
systemctl restart uyuni-proxy-pod
```
### Client non si connette al Proxy
```bash
# Dal client, verificare configurazione master
cat /etc/salt/minion.d/susemanager.conf

# Test connettività al Proxy
ping uyuni-proxy-test.uyuni.internal

# Verificare porte Salt aperte sul Proxy
nc -zv uyuni-proxy-test.uyuni.internal 4505
nc -zv uyuni-proxy-test.uyuni.internal 4506

# Riavviare Salt minion
systemctl restart salt-minion

# Verificare logs Salt minion
journalctl -u salt-minion -f
```
### Proxy non raggiunge il Server
```bash
# Dall'host Proxy, test connettività verso Server
ping uyuni-server-test.uyuni.internal
nc -zv uyuni-server-test.uyuni.internal 443
nc -zv uyuni-server-test.uyuni.internal 4505
nc -zv uyuni-server-test.uyuni.internal 4506

# Verificare DNS
host uyuni-server-test.uyuni.internal

# Verificare firewall
firewall-cmd --list-all
```
### Problemi Certificati SSL
```bash
# Verificare certificato Proxy
podman exec proxy-httpd openssl x509 -in /etc/pki/tls/certs/spacewalk.crt -text -noout

# Verificare CA del Server
openssl s_client -connect uyuni-server-test.uyuni.internal:443 </dev/null 2>/dev/null | openssl x509 -noout -dates
```
### Checksum Mismatch (Invalid System Credentials / HTTP 500)
Se i client ricevono HTTP 500 dal proxy e nei log del proxy-httpd appare `Invalid System Credentials`, e nel log del server (`/var/log/rhn/rhn_server_xmlrpc.log`) appare `Checksum check failed: XXXX != YYYY`:

**Causa**: Il checksum nel systemid del proxy non corrisponde a quello nel database del server. Questo succede quando:
1. Si esegue il bootstrap Salt PRIMA della generazione del config (il bootstrap modifica il checksum sul server)
2. Si rigenera il config per un sistema già esistente (il comando non aggiorna il checksum server-side)

**Soluzione**:
```bash
# 1. Sul Server: eliminare il sistema proxy dalla Web UI
#    Systems → uyuni-proxy-test → Delete System
#    (spacecmd system_delete ha un bug con i proxy, usare la Web UI)

# 2. Sul Server: eliminare la salt key se presente
mgrctl exec -- salt-key -d uyuni-proxy-test.uyuni.internal -y

# 3. Sul Server: rigenerare il config.tar.gz FRESCO
mgrctl exec -ti -- spacecmd proxy_container_config_generate_cert -- \
  uyuni-proxy-test.uyuni.internal \
  uyuni-server-test.uyuni.internal \
  38000 \
  admin@example.com \
  -o /tmp/config.tar.gz \
  -p 8022

# 4. Trasferire il config al proxy e reinstallare
mgrctl cp server:/tmp/config.tar.gz /tmp/proxy-config.tar.gz
scp /tmp/proxy-config.tar.gz azureuser@10.172.2.20:/tmp/uyuni-proxy-test-config.tar.gz

# 5. Sul Proxy: reinstallare (mgrpxy install sovrascrive)
mgrpxy install podman /tmp/uyuni-proxy-test-config.tar.gz

# 6. Applicare il fix systemid (FASE 9) e avviare
```

> NON eseguire il bootstrap Salt tra la generazione del config e l'installazione. Il bootstrap modifica il checksum e invalida il systemid.

### Verifica Checksum
Per verificare se i checksum corrispondono:
```bash
# Checksum nel systemid del proxy
cat /etc/sysconfig/rhn/systemid | grep -oP 'checksum.*?<string>\K[^<]+'

# Checksum che il server si aspetta (dal log errori)
mgrctl exec -- tail -5 /var/log/rhn/rhn_server_xmlrpc.log
# Il primo valore nel "Checksum check failed: EXPECTED != RECEIVED" è quello del server
```

### Cache Squid piena

```bash
# Verificare spazio
df -h /proxy_storage

# Verificare cache Squid
podman exec proxy-squid du -sh /var/cache/squid/
```
## Certificati Custom per Production
Per ambienti production con CA aziendale:
### 1. Copiare certificati nel container Server
```bash
podman cp ca.crt uyuni-server:/tmp/
podman cp proxy.crt uyuni-server:/tmp/
podman cp proxy.key uyuni-server:/tmp/
```
### 2. Generare configurazione con certificati custom
```bash
mgrctl exec -ti 'spacecmd proxy_container_config -- \
  -p 8022 \
  uyuni-proxy-test.uyuni.internal \
  uyuni-server-test.uyuni.internal \
  38000 \
  admin@example.com \
  /tmp/ca.crt \
  /tmp/proxy.crt \
  /tmp/proxy.key \
  -o /tmp/config.tar.gz'
```
## Comandi Utili - Quick Reference
### Gestione Proxy
```bash
mgrpxy start               # Avvia il proxy
mgrpxy stop                # Ferma il proxy
mgrpxy status              # Stato proxy (se disponibile)
mgrpxy logs                # Visualizza logs
mgrpxy upgrade             # Aggiornamento container
mgrpxy uninstall           # Rimuovi proxy
```
### Container e Pod
```bash
podman ps                  # Lista container attivi
podman pod ps              # Stato pod
podman logs <container>    # Log specifico container
podman logs -f proxy-httpd # Log in tempo reale
```
### Systemd
```bash
systemctl status uyuni-proxy-pod    # Stato servizio
systemctl restart uyuni-proxy-pod   # Riavvia
systemctl enable uyuni-proxy-pod    # Abilita auto-start
journalctl -u uyuni-proxy-pod -f   # Log systemd
```
### Storage
```bash
df -h /proxy_storage                # Spazio disco cache
lvs                                 # Volumi logici
podman system df                    # Uso storage container
```

---
## Riferimenti

- [Proxy Deployment on openSUSE](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/container-deployment/uyuni/proxy-deployment-uyuni.html)
- [Proxy Container Setup](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/container-deployment/uyuni/proxy-container-setup-uyuni.html)
- [Proxy Container Installation](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/container-deployment/uyuni/proxy-container-installation-uyuni.html)
- [Network Requirements](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/network-requirements.html)
- [Client Registration to Proxy](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/client-proxy.html)
- [SSL Certificates](https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/ssl-certs.html)
