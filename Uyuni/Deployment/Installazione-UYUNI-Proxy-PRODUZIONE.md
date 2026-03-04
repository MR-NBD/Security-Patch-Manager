### Architettura Target

```
UYUNI Server (10.172.2.X)          PostgreSQL Server (10.172.2.Z) [PROD]
        │                                       │
        │ ← connessione DB esterna ────────────┘
        │ Salt 4505/4506 + HTTPS 443
        │
UYUNI Proxy (10.172.2.Y) [PROD: IP definitivo]
        │
        ├── Ubuntu Client #1
        ├── Ubuntu Client #2
        └── RHEL 9 Client
```

> **[PROD] PostgreSQL su VM dedicata**: In produzione il database PostgreSQL NON deve risiedere sulla stessa VM del UYUNI Server. Deve essere installato su una VM separata (vedere sezione dedicata in fondo). Il UYUNI Server viene installato con `mgradm install podman --db-host <IP_POSTGRES> ...` per puntare al DB esterno.

### Componenti Container (Proxy 2025.10)

| Container             | Funzione                                                 |
| --------------------- | -------------------------------------------------------- |
| **proxy-httpd**       | HTTP/HTTPS - repository pacchetti e Web forwarding       |
| **proxy-salt-broker** | Broker Salt events tra client e Server                   |
| **proxy-squid**       | Cache proxy per pacchetti (riduce traffico verso Server) |
| **proxy-ssh**         | SSH tunneling per push clients                           |
| **proxy-tftpd**       | TFTP per PXE boot (provisioning automatico)              |

> La dimensione del disco cache Squid determina quanti pacchetti vengono serviti localmente senza contattare il Server. Più grande è, meno traffico di rete tra Proxy e Server. Impostare Squid cache al massimo **60% dello spazio disponibile** sul disco cache.

## DEPLOYMENT

### Configurazione VM Azure

| Parametro          | Valore TEST                         | **Valore PRODUZIONE** `[PROD]`                    |
| ------------------ | ----------------------------------- | ------------------------------------------------- |
| **Subscription**   | ASL0603-spoke10                     | ASL0603-spoke10 *(o subscription produzione)*     |
| **Resource Group** | test_group                          | **prod_group** *(Resource Group dedicato prod)*   |
| **VM Name**        | uyuni-proxy-test                    | **uyuni-proxy-prod**                              |
| **Region**         | Italy North                         | Italy North                                       |
| **Availability**   | Availability Zone 1                 | **Availability Zone 1+2** *(o Availability Set)*  |
| **Security Type**  | Trusted launch (Secure boot + vTPM) | Trusted launch (Secure boot + vTPM)               |
| **Image**          | openSUSE Leap 15.6 - Gen2           | openSUSE Leap 15.6 - Gen2                         |
| **Architecture**   | x64                                 | x64                                               |
| **Size**           | Standard_B2s (2 vCPU, 4 GB RAM)     | **Standard_D4s_v3 (4 vCPU, 16 GB RAM)** minimo   |
| **Username**       | azureuser                           | azureuser                                         |
| **Authentication** | Password                            | **SSH Public Key** *(mai password in produzione)* |
| **OS Disk**        | 40 GB Standard SSD LRS              | **128 GB Premium SSD LRS** *(P10 o superiore)*    |
| **Data Disks**     | 1 disco (64 GB) per cache pacchetti | **1 disco (256 GB+) Premium SSD LRS**             |
| **VNet**           | ASL0603-spoke10-spoke-italynorth    | ASL0603-spoke10-spoke-italynorth                  |
| **Subnet**         | default (10.172.2.0/24)             | **Subnet dedicata per management** se disponibile |
| **Public IP**      | None                                | None                                              |
| **NSG**            | uyuni-proxy-test-nsg                | **uyuni-proxy-prod-nsg**                          |

> **[PROD] Sizing**: `Standard_B2s` è insufficiente per produzione. Con molti client e download simultanei, la CPU e la RAM diventano collo di bottiglia. Minimo consigliato `Standard_D4s_v3`; valutare `Standard_D8s_v3` se gestisce più di 50 client.

> **[PROD] Autenticazione**: In produzione usare **esclusivamente SSH Key**. Disabilitare l'autenticazione password via `/etc/ssh/sshd_config` (`PasswordAuthentication no`) dopo il primo accesso.

> **[PROD] Disco dati**: 256 GB è il minimo consigliato per la cache Squid in produzione. Valutare 512 GB se la banda tra Proxy e Server è limitata (cache più grande = meno traffico ripetuto).

### Configurazione NSG

**Inbound** (verso il Proxy):

| Priority | Nome               | Port      | Protocol | Source                    | Destination | Action |
| -------- | ------------------ | --------- | -------- | ------------------------- | ----------- | ------ |
| 100      | AllowHTTPS_Clients | 443       | TCP      | 10.172.2.0/24             | 10.172.2.Y  | Allow  |
| 110      | AllowSalt_Clients  | 4505-4506 | TCP      | 10.172.2.0/24             | 10.172.2.Y  | Allow  |
| 120      | AllowHTTPS_Server  | 443       | TCP      | 10.172.2.X *(UYUNI Srv)*  | 10.172.2.Y  | Allow  |
| 130      | AllowSalt_Server   | 4505-4506 | TCP      | 10.172.2.X *(UYUNI Srv)*  | 10.172.2.Y  | Allow  |
| 140      | AllowSSHPush       | 8022      | TCP      | 10.172.2.0/24             | 10.172.2.Y  | Allow  |
| 150      | AllowSSH_Bastion   | 22        | TCP      | **IP Azure Bastion ONLY** | 10.172.2.Y  | Allow  |

> **[PROD]**: In produzione NON aprire la porta 22 a tutta la subnet. Limitare l'accesso SSH esclusivamente all'IP del servizio Azure Bastion o di un jump host dedicato. Valutare l'eliminazione completa della regola SSH inbound e l'utilizzo esclusivo di Azure Bastion.

**Outbound** (dal Proxy):

| Priority | Nome                | Port      | Protocol | Source      | Destination               | Action |
| -------- | ------------------- | --------- | -------- | ----------- | ------------------------- | ------ |
| 100      | AllowHTTPS_ToServer | 443       | TCP      | 10.172.2.Y  | 10.172.2.X *(UYUNI Srv)*  | Allow  |
| 110      | AllowSalt_ToServer  | 4505-4506 | TCP      | 10.172.2.Y  | 10.172.2.X *(UYUNI Srv)*  | Allow  |

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

> **[PROD]**: In produzione considerare l'aggiunta di `audit` (auditd) e `aide` per il monitoraggio dell'integrità del filesystem, se richiesto dalla policy di sicurezza aziendale.

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

**[TEST]** Configurazione ambiente di test:
```
server ntp1.inrim.it iburst
server ntp2.inrim.it iburst
pool pool.ntp.org iburst
makestep 1.0 3
logdir /var/log/chrony
driftfile /var/lib/chrony/drift
```

> **[PROD]**: In produzione usare **esclusivamente server NTP interni aziendali**. Non usare server NTP pubblici (pool.ntp.org, inrim.it) in reti isolate o per compliance. Verificare con il team di rete l'indirizzo dei NTP server interni (tipicamente i Domain Controller o un appliance NTP dedicato).

**[PROD]** Configurazione produzione (esempio con NTP interni):
```
# Server NTP aziendali interni - sostituire con i valori reali
server <NTP_INTERNO_1> iburst
server <NTP_INTERNO_2> iburst

# NON usare server pubblici in produzione
# pool pool.ntp.org iburst

makestep 1.0 3
logdir /var/log/chrony
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

> **[PROD]**: In produzione l'hostname deve seguire la naming convention aziendale approvata e deve essere registrato nell'**Azure Private DNS Zone** (non in `/etc/hosts`). Coordinare con il team di rete/DNS prima di procedere.

#### Impostare hostname
```bash
# [TEST]
hostnamectl set-hostname uyuni-proxy-test.uyuni.internal

# [PROD] - sostituire con il nome approvato
hostnamectl set-hostname uyuni-proxy-prod.dominio.aziendale
```

#### Verificare hostname
```bash
hostname -f
```

### Configura il File /etc/hosts

> **[PROD]**: In produzione l'uso di `/etc/hosts` per la risoluzione DNS è **sconsigliato** come soluzione permanente. Il metodo corretto è configurare una **Azure Private DNS Zone** (vedere FASE 10). Il file `/etc/hosts` può essere usato temporaneamente durante il setup iniziale, ma deve essere rimosso una volta che il DNS è operativo.

#### Recuperare l'IP privato della VM
```bash
ip addr show eth0
```
#### Editare il file hosts (temporaneo, solo durante il setup iniziale)
```bash
nano /etc/hosts
```
Aggiungere:
```
# [PROD] - sostituire con IP e FQDN reali di produzione
10.172.2.Y    uyuni-proxy-prod.dominio.aziendale    uyuni-proxy-prod
10.172.2.X    uyuni-server-prod.dominio.aziendale   uyuni-server-prod
10.172.2.Z    postgres-prod.dominio.aziendale       postgres-prod
```

### Verificare la Configurazione DNS
#### Test risoluzione diretta
```bash
ping -c 2 $(hostname -f)
```
#### Test risoluzione Server
```bash
# [TEST]
ping -c 2 uyuni-server-test.uyuni.internal

# [PROD]
ping -c 2 uyuni-server-prod.dominio.aziendale
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

> **[PROD]**: In produzione valutare l'uso di **rich rules** con restrizione per IP sorgente al posto di regole aperte, in aggiunta alle restrizioni NSG di Azure. La difesa in profondità (NSG + firewalld) è consigliata. Esempio:
> ```bash
> firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="10.172.2.0/24" port protocol="tcp" port="4505-4506" accept'
> ```

## FASE 5: Configurazione Storage Cache

### Identificare il Disco Dati
```bash
lsblk
```
### Configurazione LVM per disco cache (es. /dev/sdb)

> **[PROD]**: In produzione usare **Premium SSD** (non Standard SSD) per il disco cache. Le I/O della cache Squid possono essere elevate durante i picchi di distribuzione patch. Un disco P15 (256 GB) o P20 (512 GB) è consigliato.

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
mkdir -p /proxy_storage/containers
systemctl stop podman.socket
mv /var/lib/containers/* /proxy_storage/containers/ 2>/dev/null || true
rm -rf /var/lib/containers
ln -s /proxy_storage/containers /var/lib/containers
systemctl start podman.socket
```

Eseguire questa operazione PRIMA di installare il Proxy.

### Verificare Configurazione Storage
```bash
df -hP /proxy_storage
lvdisplay
```

> **[PROD]**: Configurare alert Azure Monitor sul disco dati per soglie di utilizzo al 70% e 85%, in modo da pianificare l'espansione prima di raggiungere il limite.

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

> **[PROD]**: Verificare che il registry `registry.opensuse.org` sia raggiungibile dalla rete di produzione. Se la rete è isolata (no internet), configurare un **Azure Container Registry** (ACR) o un registry interno come mirror, e aggiornare il file `/etc/containers/registries.conf` di conseguenza.

## FASE 7: Preparare l'Host Proxy per la Comunicazione Salt

> NON eseguire il bootstrap Salt separatamente prima della FASE 8. Il comando `proxy_container_config_generate_cert` nella FASE 8 crea una registrazione tradizionale (systemid) con un checksum. Se si esegue il bootstrap Salt PRIMA o DOPO la generazione del config, il bootstrap modifica il checksum sul server causando un mismatch: il proxy tenta di autenticarsi con il checksum del config, ma il server si aspetta quello del bootstrap, risultando in errore `Invalid System Credentials` e HTTP 500 su ogni richiesta dei client.

### Sull'Host Proxy: Installare Salt Minion e Certificato CA

#### Scaricare il certificato CA del Server
```bash
# [TEST]
curl -Sks https://uyuni-server-test.uyuni.internal/pub/RHN-ORG-TRUSTED-SSL-CERT -o /etc/pki/trust/anchors/uyuni-ca.crt

# [PROD]
curl -Sks https://uyuni-server-prod.dominio.aziendale/pub/RHN-ORG-TRUSTED-SSL-CERT -o /etc/pki/trust/anchors/uyuni-ca.crt
```
```bash
update-ca-certificates
```

> **[PROD]**: Se in produzione si usano **certificati aziendali** (CA enterprise), il certificato CA da distribuire ai client è quello della CA aziendale, non quello auto-generato da UYUNI. Assicurarsi che tutti i client abbiano la CA aziendale nel loro trust store prima di procedere.

### Sul Server UYUNI: Creare Activation Key per il Proxy

Dalla **Web UI** del Server UYUNI:

1. **Systems → Activation Keys → Create Key**
2. Configurare:

| Campo                   | TEST                                                  | **PRODUZIONE** `[PROD]`                                |
| ----------------------- | ----------------------------------------------------- | ------------------------------------------------------ |
| **Key**                 | `1-proxy-asl06-test`                                  | `1-proxy-asl06-prod`                                   |
| **Description**         | Activation key per Uyuni Proxy - openSUSE Leap 15.6   | Activation key per Uyuni Proxy PROD - openSUSE Leap 15.6 |
| **Base Channel**        | Uyuni Default                                         | Uyuni Default                                          |
| **Add-On Entitlements** | Container Build Host, Proxy                           | Container Build Host, Proxy                            |
| **Contact Method**      | Default                                               | Default                                                |

3. **Create Activation Key**

## FASE 8: Generare Configurazione Proxy e Certificato SSL

> **[PROD]**: In produzione è **obbligatorio** usare certificati firmati dalla CA aziendale (Opzione B con certificati custom, vedere sezione "Certificati Custom per Production"). L'uso dei certificati auto-generati da UYUNI è accettabile solo in ambienti di test.

### Opzione A: Via Web UI (TEST — non raccomandato per produzione)

1. Sul Server UYUNI, andare su **Systems → Proxy Configuration**
2. Compilare i campi principali:

| Campo                    | TEST                               | **PRODUZIONE** `[PROD]`                       |
| ------------------------ | ---------------------------------- | --------------------------------------------- |
| **Proxy FQDN**           | `uyuni-proxy-test.uyuni.internal`  | `uyuni-proxy-prod.dominio.aziendale`          |
| **Parent FQDN**          | `uyuni-server-test.uyuni.internal` | `uyuni-server-prod.dominio.aziendale`         |
| **Proxy SSH Port**       | `8022`                             | `8022`                                        |
| **Max Squid Cache [MB]** | `38000` (60% di 64 GB)             | **`153600`** (60% di 256 GB) o proporzionale  |
| **SSL Certificate**      | Generate                           | **Use existing** (certificati aziendali)      |

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

> **[PROD]**: Il trasferimento del file `ca.key` tramite WinSCP è accettabile in test ma **non consigliato in produzione**. In produzione usare l'**Opzione B via CLI** (spacecmd) oppure i certificati aziendali via pipeline CI/CD sicura con Key Vault.

### Opzione B: Via spacecmd (CLI)
```bash
# [TEST]
mgrctl exec -ti 'spacecmd proxy_container_config_generate_cert -- \
  uyuni-proxy-test.uyuni.internal \
  uyuni-server-test.uyuni.internal \
  38000 \
  admin@example.com \
  -o /tmp/config.tar.gz \
  -p 8022'

# [PROD]
mgrctl exec -ti 'spacecmd proxy_container_config_generate_cert -- \
  uyuni-proxy-prod.dominio.aziendale \
  uyuni-server-prod.dominio.aziendale \
  153600 \
  sysadmin@azienda.it \
  -o /tmp/config.tar.gz \
  -p 8022'
```

> **[PROD]**: Per certificati firmati dalla CA aziendale, usare `proxy_container_config` (senza `_generate_cert`) passando i certificati pre-emessi. Vedere sezione "Certificati Custom per Production" in fondo.

## FASE 9: Installazione Container Proxy

### Sull'Host Proxy: Installare i Container
```bash
sudo su -
# [TEST]
mgrpxy install podman /tmp/uyuni-proxy-test-config.tar.gz

# [PROD]
mgrpxy install podman /tmp/uyuni-proxy-prod-config.tar.gz
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
```

> La directory DEVE avere permessi `755` e il file systemid (una volta creato dal container) deve avere permessi `644`. Con permessi restrittivi (`750` sulla directory o `640` sul file), il processo Apache (wwwrun) all'interno del container non può leggere il systemid.

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
Output atteso: XML contenente `<string>ID-XXXXXXXXXX</string>`.

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

> **[PROD]**: Configurare un **Azure VM Recovery Services Vault** o snapshot automatici della VM per il disaster recovery. In caso di corruzione, il Proxy è stateless (lo stato è sul Server): reinstallare dalla FASE 9 è sufficiente, ma avere uno snapshot OS velocizza il ripristino.

### Verificare dal Server UYUNI
Dalla Web UI:
1. **Systems → System List** → selezionare `uyuni-proxy-prod`
2. Tab **Details → Proxy**
3. Verificare status: **Active**

### (Opzionale) Registrare il Proxy come Salt Minion
Se si vuole gestire il proxy come Salt minion (consigliato per management), eseguire il bootstrap **DOPO** l'installazione container:

Sull'**Host Proxy**:
```bash
# [TEST]
curl -Sks https://uyuni-server-test.uyuni.internal/pub/bootstrap/bootstrap.sh | /bin/bash

# [PROD]
curl -Sks https://uyuni-server-prod.dominio.aziendale/pub/bootstrap/bootstrap.sh | /bin/bash
```

Sul **Server UYUNI**:
```bash
# [TEST]
mgrctl exec -- salt-key -a uyuni-proxy-test.uyuni.internal -y

# [PROD]
mgrctl exec -- salt-key -a uyuni-proxy-prod.dominio.aziendale -y
mgrctl exec -- salt 'uyuni-proxy-prod.dominio.aziendale' test.ping
```

> Il bootstrap Salt modifica il checksum delle credenziali tradizionali sul server. Se dopo il bootstrap il proxy inizia a restituire errori HTTP 500 (`Invalid System Credentials`), è necessario rigenerare il config.tar.gz e reinstallare (vedi sezione Troubleshooting → Checksum Mismatch).

## FASE 10: Configurazione DNS per Server, Proxy e Client

> **[PROD]**: In produzione la risoluzione DNS tramite `/etc/hosts` è **inaccettabile** come soluzione definitiva. È **obbligatorio** configurare una **Azure Private DNS Zone** prima di mettere in produzione il Proxy.

### [PROD] Configurazione Azure Private DNS Zone

1. Nel portale Azure, cercare **Private DNS zones**
2. Creare la zona (es. `uyuni.aziendale.internal` o usare la zona esistente)
3. Aggiungere i record A:

| Nome               | Tipo | IP                 |
| ------------------ | ---- | ------------------ |
| uyuni-server-prod  | A    | 10.172.2.X         |
| uyuni-proxy-prod   | A    | 10.172.2.Y         |
| postgres-prod      | A    | 10.172.2.Z         |

4. Collegare la Private DNS Zone alla VNet:
   - **Virtual network links → Add**
   - Abilitare **Auto registration** se si vuole registrazione automatica delle VM

> Il container del Server UYUNI ha un `/etc/hosts` separato dall'host, gestito da Podman. Le modifiche a `/etc/hosts` sull'host non sono visibili al container. Con **Azure Private DNS Zone** correttamente configurata e linkata alla VNet, anche i container Podman risolvono via DNS senza modifiche manuali.

Aggiungere su **ogni host** (server, proxy, client) — solo come fallback temporaneo durante setup:
```bash
# [PROD] - solo se DNS non ancora operativo
echo "10.172.2.X    uyuni-server-prod.dominio.aziendale    uyuni-server-prod" >> /etc/hosts
echo "10.172.2.Y    uyuni-proxy-prod.dominio.aziendale    uyuni-proxy-prod" >> /etc/hosts
```

## FASE 11: Ri-puntare i Client Esistenti al Proxy

> **Prerequisito**: La configurazione DNS della FASE 10 deve essere completata prima di procedere.

### Opzione A: Via Web UI
Per **ogni client**:

1. **Systems → System List** → cliccare sul sistema
2. Tab **Details → Connection**
3. Cliccare **Change proxy**
4. Selezionare `uyuni-proxy-prod.dominio.aziendale` dal menu dropdown
5. Cliccare **Confirm**

### Opzione B: Via CLI (su ogni client manualmente)

Per client con `venv-salt-minion` (Ubuntu/RHEL registrati con bootstrap):
```bash
# [TEST → PROD]: sostituire server-test con server-prod e proxy-test con proxy-prod
sed -i 's/uyuni-server-prod.dominio.aziendale/uyuni-proxy-prod.dominio.aziendale/' /etc/venv-salt-minion/minion.d/susemanager.conf
systemctl restart venv-salt-minion
```

Per client con `salt-minion` standard:
```bash
sed -i 's/uyuni-server-prod.dominio.aziendale/uyuni-proxy-prod.dominio.aziendale/' /etc/salt/minion.d/susemanager.conf
systemctl restart salt-minion
```

> **[PROD]**: In produzione, pianificare la migrazione dei client al Proxy in finestre di manutenzione. Non migrare tutti i client simultaneamente: procedere a gruppi (es. 20% alla volta) per identificare eventuali problemi prima che impattino tutti i sistemi.

### Verificare che i Client siano Connessi via Proxy
Dalla Web UI del Server:
1. **Systems → System List** → cliccare su un client
2. Tab **Details → Connection**
3. Verificare che **Proxy** mostri `uyuni-proxy-prod.dominio.aziendale`

---

## [PROD] PostgreSQL su VM Dedicata

> Questa sezione descrive la configurazione del database PostgreSQL separato per il **UYUNI Server** in produzione. Il Proxy in sé non usa PostgreSQL direttamente, ma il Server che gestisce il Proxy deve avere un DB dedicato per garantire resilienza e scalabilità.

### Motivazione

| Aspetto          | PostgreSQL su UYUNI Server VM      | PostgreSQL su VM dedicata `[PROD]`         |
| ---------------- | ---------------------------------- | ------------------------------------------ |
| **Isolamento**   | Risorse CPU/RAM condivise          | Risorse dedicate                           |
| **Backup**       | Backup VM completa (costoso)       | Backup solo DB (efficiente)                |
| **Scalabilità**  | Limitata dalla VM Server           | Scalabile indipendentemente               |
| **Manutenzione** | DB update = downtime Server        | DB update senza downtime applicativo       |
| **Resilienza**   | VM failure = perdita tutto         | Alta disponibilità separata per DB e App   |

### Configurazione VM PostgreSQL

| Parametro          | Valore raccomandato                          |
| ------------------ | -------------------------------------------- |
| **VM Name**        | `postgres-uyuni-prod`                        |
| **OS**             | Ubuntu 22.04 LTS o RHEL 9 (supportato da PG) |
| **Size**           | Standard_D4s_v3 (4 vCPU, 16 GB RAM) minimo  |
| **OS Disk**        | 64 GB Premium SSD LRS                        |
| **Data Disk**      | 256 GB+ Premium SSD LRS per `/var/lib/postgresql` |
| **IP**             | 10.172.2.Z (IP privato fisso)                |
| **Public IP**      | **None**                                     |

### Installazione PostgreSQL (su VM dedicata)

```bash
# Ubuntu 22.04
sudo apt install -y postgresql postgresql-contrib

# Configurare accesso da UYUNI Server
sudo nano /etc/postgresql/*/main/postgresql.conf
# listen_addresses = '10.172.2.Z'   # solo IP privato, mai '*' in produzione

sudo nano /etc/postgresql/*/main/pg_hba.conf
# Aggiungere riga per UYUNI Server:
# host    susemanager    susemanager    10.172.2.X/32    scram-sha-256
```

```bash
# Creare utente e database UYUNI
sudo -u postgres psql <<EOF
CREATE USER susemanager WITH PASSWORD '<PASSWORD_SICURA>';
CREATE DATABASE susemanager OWNER susemanager;
\q
EOF
```

```bash
# Aprire porta PostgreSQL nel firewall (solo verso UYUNI Server)
sudo ufw allow from 10.172.2.X to any port 5432
```

### NSG per VM PostgreSQL

| Priority | Nome              | Port | Protocol | Source      | Destination | Action |
| -------- | ----------------- | ---- | -------- | ----------- | ----------- | ------ |
| 100      | AllowPG_FromUyuni | 5432 | TCP      | 10.172.2.X  | 10.172.2.Z  | Allow  |
| 4096     | DenyAll           | *    | *        | *           | *           | Deny   |

### Installazione UYUNI Server con DB esterno

Al momento dell'installazione del UYUNI Server, usare i parametri `--db-*` per puntare al PostgreSQL esterno:

```bash
mgradm install podman \
  --db-host 10.172.2.Z \
  --db-port 5432 \
  --db-name susemanager \
  --db-user susemanager \
  --db-password '<PASSWORD_SICURA>' \
  uyuni-server-prod.dominio.aziendale
```

> Se il Server è già installato con DB locale, la migrazione al DB esterno richiede `pg_dump` + restore e riconfigurazone. Pianificare questa operazione in una finestra di manutenzione dedicata.

### Backup PostgreSQL

In produzione configurare backup automatici del DB:

```bash
# Esempio script backup giornaliero (da eseguire sulla VM PostgreSQL)
cat > /etc/cron.daily/backup-uyuni-db <<'EOF'
#!/bin/bash
BACKUP_DIR="/backup/postgresql"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
sudo -u postgres pg_dump susemanager | gzip > $BACKUP_DIR/susemanager_$DATE.sql.gz
# Mantenere solo gli ultimi 7 backup
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete
EOF
chmod +x /etc/cron.daily/backup-uyuni-db
```

> **[PROD]**: Integrare i backup con **Azure Backup** o trasferirli su **Azure Blob Storage** per garantire la retention fuori dalla VM. Testare il restore periodicamente.

---

## Troubleshooting

### I container Proxy non si avviano

```bash
podman logs proxy-httpd
podman logs proxy-salt-broker
podman logs proxy-squid
podman pod ps
mgrpxy stop
mgrpxy start
systemctl restart uyuni-proxy-pod
```

### Client non si connette al Proxy
```bash
cat /etc/salt/minion.d/susemanager.conf
ping uyuni-proxy-prod.dominio.aziendale
nc -zv uyuni-proxy-prod.dominio.aziendale 4505
nc -zv uyuni-proxy-prod.dominio.aziendale 4506
systemctl restart salt-minion
journalctl -u salt-minion -f
```

### Proxy non raggiunge il Server
```bash
ping uyuni-server-prod.dominio.aziendale
nc -zv uyuni-server-prod.dominio.aziendale 443
nc -zv uyuni-server-prod.dominio.aziendale 4505
nc -zv uyuni-server-prod.dominio.aziendale 4506
host uyuni-server-prod.dominio.aziendale
firewall-cmd --list-all
```

### Problemi Certificati SSL
```bash
podman exec proxy-httpd openssl x509 -in /etc/pki/tls/certs/spacewalk.crt -text -noout
openssl s_client -connect uyuni-server-prod.dominio.aziendale:443 </dev/null 2>/dev/null | openssl x509 -noout -dates
```

### Checksum Mismatch (Invalid System Credentials / HTTP 500)

**Causa**: Il checksum nel systemid del proxy non corrisponde a quello nel database del server.

**Soluzione**:
```bash
# 1. Sul Server: eliminare il sistema proxy dalla Web UI
#    Systems → uyuni-proxy-prod → Delete System

# 2. Sul Server: eliminare la salt key se presente
mgrctl exec -- salt-key -d uyuni-proxy-prod.dominio.aziendale -y

# 3. Sul Server: rigenerare il config.tar.gz FRESCO
mgrctl exec -ti -- spacecmd proxy_container_config_generate_cert -- \
  uyuni-proxy-prod.dominio.aziendale \
  uyuni-server-prod.dominio.aziendale \
  153600 \
  sysadmin@azienda.it \
  -o /tmp/config.tar.gz \
  -p 8022

# 4. Trasferire il config al proxy e reinstallare
mgrctl cp server:/tmp/config.tar.gz /tmp/proxy-config.tar.gz
scp /tmp/proxy-config.tar.gz azureuser@10.172.2.Y:/tmp/uyuni-proxy-prod-config.tar.gz

# 5. Sul Proxy: reinstallare
mgrpxy install podman /tmp/uyuni-proxy-prod-config.tar.gz

# 6. Applicare il fix systemid (FASE 9) e avviare
```

### Verifica Checksum
```bash
cat /etc/sysconfig/rhn/systemid | grep -oP 'checksum.*?<string>\K[^<]+'
mgrctl exec -- tail -5 /var/log/rhn/rhn_server_xmlrpc.log
```

### Cache Squid piena

```bash
df -h /proxy_storage
podman exec proxy-squid du -sh /var/cache/squid/
```

---

## Certificati Custom per Production

> **[PROD]**: In produzione questa procedura è **obbligatoria**, non opzionale.

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
  uyuni-proxy-prod.dominio.aziendale \
  uyuni-server-prod.dominio.aziendale \
  153600 \
  sysadmin@azienda.it \
  /tmp/ca.crt \
  /tmp/proxy.crt \
  /tmp/proxy.key \
  -o /tmp/config.tar.gz'
```

> **[PROD]**: I certificati aziendali devono avere nel campo **Subject Alternative Name (SAN)** l'FQDN completo del Proxy. Coordinarsi con il team PKI aziendale per l'emissione del certificato con i SAN corretti prima di questa fase.

---

## Comandi Utili - Quick Reference

### Gestione Proxy
```bash
mgrpxy start               # Avvia il proxy
mgrpxy stop                # Ferma il proxy
mgrpxy status              # Stato proxy
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
