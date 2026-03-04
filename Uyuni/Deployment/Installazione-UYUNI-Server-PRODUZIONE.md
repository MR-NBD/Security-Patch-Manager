
### Requisiti Hardware

| Componente       | Test                    | **Production** `[PROD]`      |
| ---------------- | ----------------------- | ---------------------------- |
| CPU              | 4+ core                 | **8+ core**                  |
| RAM              | 16 GB                   | **32+ GB**                   |
| Disco OS         | 64 GB Standard SSD      | **128 GB Premium SSD**       |
| Disco Repository | 256 GB Standard SSD     | **500+ GB Premium SSD**      |
| Disco PostgreSQL | 64 GB Standard SSD      | **100+ GB Premium SSD NVMe** |

### Architettura Target

#### UYUNI SERVER - Host Container (openSUSE Leap 15.6)

In produzione il database PostgreSQL NON deve risiedere sulla stessa VM del server UYUNI. Sono disponibili due opzioni:

**Opzione A — VM dedicata** (IaaS): VM separata con container `uyuni-db`
**Opzione B — Azure Database for PostgreSQL Flexible Server** (PaaS): servizio gestito Azure *(raccomandato)*

```
Opzione A: VM dedicata
┌─────────────────────────────────────┐     ┌──────────────────────────────────┐
│  VM: uyuni-server-prod (10.172.2.X) │     │  VM: uyuni-db-prod (10.172.2.Z)  │
│  Container: uyuni-server            │────▶│  Container: uyuni-db (PostgreSQL)│
│  Disco Repo: 500 GB Premium SSD     │5432 │  Disco PgSQL: 100 GB Premium NVMe│
└─────────────────────────────────────┘     └──────────────────────────────────┘

Opzione B: Azure PaaS (raccomandato)
┌─────────────────────────────────────┐     ┌──────────────────────────────────────┐
│  VM: uyuni-server-prod (10.172.2.X) │     │  Azure DB for PostgreSQL             │
│  Container: uyuni-server            │────▶│  Flexible Server (Private Endpoint)  │
│  Disco Repo: 500 GB Premium SSD     │5432 │  Gestito da Azure (backup, HA, patch)│
└─────────────────────────────────────┘     └──────────────────────────────────────┘
```

| Aspetto              | Opzione A — VM dedicata          | Opzione B — Azure PaaS *(raccomandato)* |
| -------------------- | -------------------------------- | --------------------------------------- |
| Gestione OS/patch    | Manuale                          | Zero — gestito da Azure                 |
| Backup               | Script cron custom               | Integrato, point-in-time restore        |
| Alta disponibilità   | Configurazione manuale           | Zone redundancy nativa (99.99% SLA)     |
| Monitoring           | Azure Monitor + configurazione   | Integrato out-of-the-box                |
| Costo                | VM + disco                       | Più alto, ma zero ops                   |
| Private connectivity | IP privato della VM              | Private Endpoint                        |
| Scaling              | Resize VM + disco (con downtime) | Scaling indipendente senza downtime     |

> **[PROD]**: Questa separazione garantisce risorse dedicate al DB, backup indipendente, scalabilità separata e resilienza isolata dal Server UYUNI. Vedere la **sezione dedicata al database** in fondo al documento per entrambe le configurazioni.

##### Componenti Container (UYUNI 2025.10):

| Container        | Immagine                                               | Funzione                      | VM `[PROD]`                          |
|------------------|--------------------------------------------------------|-------------------------------|--------------------------------------|
| **uyuni-server** | `registry.opensuse.org/uyuni/server:latest`            | Server principale UYUNI       | uyuni-server-prod                    |
| **uyuni-db**     | `registry.opensuse.org/uyuni/server-postgresql:latest` | Database PostgreSQL dedicato  | **uyuni-db-prod** oppure **Azure PaaS** |

##### Servizi nel container uyuni-server:
- Salt Master
- Taskomatic
- Tomcat (Web UI)
- Apache HTTPD (Reverse Proxy)
- Cobbler (Provisioning)

##### Layout Storage (VM Server — senza container DB):
```
sda (OS Disk - 128GB) [PROD: Premium SSD]
 └─/                              (Root filesystem)

sdb (Data Disk - 500GB) [LVM] [PROD: Premium SSD]
 └─vg_uyuni_repo/lv_repo
   └─/manager_storage             (Repository packages + Container storage)
     └─/manager_storage/containers (symlink da /var/lib/containers)
```

> **[PROD]**: In produzione il disco PostgreSQL (`sdc`) viene omesso dalla VM Server perché il container `uyuni-db` gira sulla VM dedicata. Il volume `/pgsql_storage` esiste solo sulla VM `uyuni-db-prod`.

---

## DEPLOYMENT — VM Server UYUNI

### Configurazione VM Azure — Ambiente PRODUZIONE

| Parametro          | Valore TEST                          | **Valore PRODUZIONE** `[PROD]`                      |
| ------------------ | ------------------------------------ | --------------------------------------------------- |
| **Subscription**   | ASL0603-spoke10                      | ASL0603-spoke10 *(o subscription produzione)*       |
| **Resource Group** | test_group                           | **prod_group** *(Resource Group dedicato prod)*     |
| **VM Name**        | uyuni-server-test                    | **uyuni-server-prod**                               |
| **Region**         | Italy North                          | Italy North                                         |
| **Availability**   | Availability Zone 1                  | **Availability Zone 1** *(coordinare con uyuni-db)* |
| **Security Type**  | Trusted launch (Secure boot + vTPM)  | Trusted launch (Secure boot + vTPM)                 |
| **Image**          | openSUSE Leap 15.6 - Gen2            | openSUSE Leap 15.6 - Gen2                           |
| **Architecture**   | x64                                  | x64                                                 |
| **Size**           | Standard_D8as_v5 (8 vCPU, 32 GB RAM) | **Standard_D8as_v5 o superiore** (min. 8 vCPU, 32 GB RAM) |
| **Username**       | azureuser                            | azureuser                                           |
| **Authentication** | Password                             | **SSH Public Key** *(mai password in produzione)*   |
| **OS Disk**        | 64 GB Standard SSD LRS               | **128 GB Premium SSD LRS** (P10 o superiore)        |
| **Data Disks**     | 2 dischi (256 GB + 64 GB)            | **1 disco (500 GB+) Premium SSD LRS** *(solo repo, niente PostgreSQL)* |
| **VNet**           | ASL0603-spoke10-spoke-italynorth     | ASL0603-spoke10-spoke-italynorth                    |
| **Subnet**         | default (10.172.2.0/27)              | **Subnet dedicata management** se disponibile       |
| **Public IP**      | None                                 | None                                                |
| **NSG**            | uyuni-server-test-nsg                | **uyuni-server-prod-nsg**                           |

> **[PROD] Autenticazione**: In produzione usare **esclusivamente SSH Key**. Dopo il primo accesso, disabilitare l'autenticazione password in `/etc/ssh/sshd_config` (`PasswordAuthentication no`).

> **[PROD] Disco dati**: Solo 1 disco dati sulla VM Server (repository). Il secondo disco PostgreSQL viene provisionato sulla VM `uyuni-db-prod` separata.

### Configurazione NSG — Produzione

**Inbound** (verso il Server):

| Priority | Nome            | Port      | Protocol | Source                    | Destination | Action |
| -------- | --------------- | --------- | -------- | ------------------------- | ----------- | ------ |
| 100      | AllowHTTPS      | 443       | TCP      | 10.172.2.0/24             | 10.172.2.X  | Allow  |
| 110      | AllowSalt       | 4505-4506 | TCP      | 10.172.2.0/24             | 10.172.2.X  | Allow  |
| 120      | AllowSSH_Bastion| 22        | TCP      | **IP Azure Bastion ONLY** | 10.172.2.X  | Allow  |
| 4096     | DenyAll         | *         | *        | *                         | *           | Deny   |

> **[PROD]**: NON aprire la porta 5432 (PostgreSQL) in ingresso sulla VM Server. Il traffico PostgreSQL è in uscita dal Server verso la VM `uyuni-db-prod`, non in ingresso.

> **[PROD]**: Limitare la porta 22 esclusivamente all'IP del servizio Azure Bastion. Non aprire SSH a tutta la subnet.

---
## FASE 1: Preparazione del Sistema Base

### 1.1 Dalla VM
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
### 1.2 Aggiornamento Sistema
```bash
zypper refresh
zypper update -y
```
#### Riavvia per applicare aggiornamenti kernel
```bash
reboot
```
### 1.3 Installazione Pacchetti Prerequisiti

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

> **[PROD]**: Valutare l'aggiunta di `audit` (auditd) per il logging di compliance richiesto da framework come ISO 27001 o NIS2.

---
## FASE 2: Configurazione NTP con Chrony

La sincronizzazione temporale è **CRITICA** per il corretto funzionamento di UYUNI, Salt, e i certificati SSL.

### 2.1 Configurazione Chrony

#### Backup configurazione originale
```bash
cp /etc/chrony.conf /etc/chrony.conf.bak
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

> **[PROD]**: Usare **esclusivamente server NTP interni aziendali**. Server NTP pubblici non devono essere usati in reti di produzione isolate o per compliance. Verificare con il team di rete gli indirizzi NTP interni (tipicamente Domain Controller o appliance NTP dedicati).

**[PROD]** Configurazione produzione:
```bash
vim /etc/chrony.conf
```
```
# Server NTP aziendali interni — sostituire con i valori reali
server <NTP_INTERNO_1> iburst
server <NTP_INTERNO_2> iburst

# NON usare server pubblici in produzione
# pool pool.ntp.org iburst

makestep 1.0 3
logdir /var/log/chrony
driftfile /var/lib/chrony/drift
```

### 2.2 Abilita e Avvia il Servizio
```bash
systemctl enable --now chronyd
```
#### Verificare le sorgenti NTP
```bash
chronyc sources -v
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

---
## FASE 3: Configurazione Hostname e DNS

UYUNI **RICHIEDE** un DNS funzionante con risoluzione diretta e inversa. Il comando `hostname -f` deve restituire l'FQDN completo.

### 3.1 Configurare l'Hostname

> **[PROD]**: Il nome host deve seguire la naming convention aziendale approvata e deve essere registrato nell'**Azure Private DNS Zone** prima di procedere. Coordinare con il team DNS prima dell'installazione.

```bash
# [TEST]
hostnamectl set-hostname uyuni-server-test.uyuni.internal

# [PROD] — sostituire con il nome approvato
hostnamectl set-hostname uyuni-server-prod.dominio.aziendale
```

#### Verificare hostname
```bash
hostname -f
```

### 3.2 Configura il File /etc/hosts

> **[PROD]**: L'uso di `/etc/hosts` è accettabile solo temporaneamente durante il setup iniziale. La soluzione definitiva è **Azure Private DNS Zone** (vedere FASE 3.3). Dopo che il DNS è operativo, rimuovere le entry manuali.

```bash
cp /etc/hosts /etc/hosts.bak
nano /etc/hosts
```

Aggiungere (sostituire con IP e dominio reali):
```
# [PROD] — entry temporanee, rimuovere dopo configurazione DNS
10.172.2.X    uyuni-server-prod.dominio.aziendale    uyuni-server-prod
10.172.2.Z    uyuni-db-prod.dominio.aziendale         uyuni-db-prod
```

### 3.3 [PROD] Configurazione Azure Private DNS Zone

1. Nel portale Azure, cercare **Private DNS zones**
2. Creare la zona (es. `dominio.aziendale`) o usare quella esistente
3. Aggiungere i record A:

| Nome               | Tipo | IP         |
| ------------------ | ---- | ---------- |
| uyuni-server-prod  | A    | 10.172.2.X |
| uyuni-db-prod      | A    | 10.172.2.Z |

4. **Virtual network links → Add**: collegare la zona alla VNet con **Auto registration** abilitato

> Il container UYUNI usa una rete Podman separata dall'host. Con Azure Private DNS Zone correttamente linkata alla VNet, anche i processi interni al container risolvono via DNS senza modifiche a `/etc/hosts` del container.

### 3.4 Verificare la Configurazione DNS
```bash
ping -c 2 $(hostname -f)
hostname -f
# [PROD] — verificare anche la risoluzione verso la VM DB
ping -c 2 uyuni-db-prod.dominio.aziendale
```

---
## FASE 4: Configurazione Sicurezza

### 4.1 Verificare Stato Servizi Base
```bash
systemctl status firewalld
systemctl enable --now firewalld
```

### 4.2 [PROD] Hardening SSH

```bash
# Disabilitare autenticazione password dopo aver verificato che la SSH key funzioni
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd
```

> **[PROD]**: Verificare che la connessione SSH via chiave funzioni PRIMA di disabilitare le password. In caso contrario, si perde l'accesso alla VM.

### 4.3 [PROD] Hardening da Implementare

- **Audit Daemon**: abilitare `auditd` per logging avanzato di compliance
- **Fail2Ban**: protezione brute-force su porta 22
- **Timeout sessione**: impostare `ClientAliveInterval 300` e `ClientAliveCountMax 3` in `sshd_config`
- **Banner SSH**: aggiungere banner legale in `/etc/issue.net` e `Banner /etc/issue.net` in `sshd_config`
- **RBAC UYUNI**: configurare ruoli separati (Admin, Channel Admin, System Admin, Viewer)
- **Timeout sessione Web UI**: 900 secondi (configurabile in Admin → General Configuration)

---
## FASE 5: Configurazione Storage Dedicato

### 5.1 Identificare i Dischi Disponibili
```bash
lsblk
```

> **[PROD]**: Sulla VM Server ci sarà solo 1 disco dati (repository). Il secondo disco PostgreSQL non è presente su questa VM — gira sulla VM `uyuni-db-prod`. Verificare che `lsblk` mostri solo `sda` (OS) e `sdb` (repo).

### 5.2 Configurazione LVM — Disco Repository

LVM è il metodo consigliato per ambienti cloud perché permette di espandere i volumi senza downtime.

#### Disco Repository (es. /dev/sdb)

```bash
# Crea partizione
parted /dev/sdb --script mklabel gpt
parted /dev/sdb --script mkpart primary 0% 100%

# Configura LVM
pvcreate /dev/sdb1
vgcreate vg_uyuni_repo /dev/sdb1
lvcreate -l 100%FREE -n lv_repo vg_uyuni_repo

# Formatta XFS
mkfs.xfs /dev/mapper/vg_uyuni_repo-lv_repo

# Crea mount point e monta
mkdir -p /manager_storage
mount /dev/mapper/vg_uyuni_repo-lv_repo /manager_storage

# Aggiungi a fstab
echo "/dev/mapper/vg_uyuni_repo-lv_repo /manager_storage xfs defaults,nofail 0 0" >> /etc/fstab

# Reload systemd
systemctl daemon-reload
```

> **[PROD]**: Non configurare `/pgsql_storage` su questa VM. Il volume PostgreSQL viene creato e montato sulla VM `uyuni-db-prod`.

### 5.3 Spostare Container Storage su manager_storage

```bash
mkdir -p /manager_storage/containers
systemctl stop podman.socket
mv /var/lib/containers/* /manager_storage/containers/ 2>/dev/null || true
rm -rf /var/lib/containers
ln -s /manager_storage/containers /var/lib/containers
systemctl start podman.socket
```

> **NOTA**: Eseguire questa operazione PRIMA di installare UYUNI.

### 5.4 Verificare Configurazione Storage
```bash
# [PROD]: solo manager_storage, niente pgsql_storage su questa VM
df -hP /manager_storage
lvs
vgs
```

> **[PROD]**: Configurare alert Azure Monitor sulla VM per notifica al 70% e 85% di utilizzo del disco `/manager_storage`. Il repository pacchetti cresce nel tempo con la sincronizzazione dei canali.

---
## FASE 6: Configurazione Firewall

### 6.1 Abilitare Firewalld
```bash
systemctl enable --now firewalld
systemctl status firewalld
```
### 6.2 Configurare Porte UYUNI

#### HTTP/HTTPS (Web UI e client)
```bash
firewall-cmd --permanent --add-port=80/tcp
firewall-cmd --permanent --add-port=443/tcp
```
#### Salt Master (comunicazione con i client)
```bash
firewall-cmd --permanent --add-port=4505/tcp
firewall-cmd --permanent --add-port=4506/tcp
```

> **[PROD]**: La porta 5432 (PostgreSQL) NON viene aperta in inbound sulla VM Server. Il traffico verso la VM `uyuni-db-prod` è **outbound** e non richiede regole firewall-cmd in ingresso. Aprire 5432 inbound sulla VM Server sarebbe un errore di sicurezza.

### 6.3 Applicare le Modifiche
```bash
firewall-cmd --reload
```
### 6.4 Verifica Configurazione
```bash
firewall-cmd --list-all
```
Output atteso (senza 5432 in inbound):
```
ports: 80/tcp 443/tcp 4505/tcp 4506/tcp
```

> **[PROD]**: In produzione valutare l'uso di **rich rules** con restrizione per IP sorgente, in aggiunta alle restrizioni NSG Azure (difesa in profondità):
> ```bash
> firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="10.172.2.0/24" port protocol="tcp" port="4505-4506" accept'
> ```

---
## FASE 7: Installazione Repository UYUNI

### 7.1 Aggiungere Repository UYUNI Stable per openSUSE Leap 15.6
```bash
zypper lr | grep uyuni
```
```bash
zypper ar https://download.opensuse.org/repositories/systemsmanagement:/Uyuni:/Stable/images/repo/Uyuni-Server-POOL-$(arch)-Media1/ uyuni-server-stable
```

> **[PROD]**: Se la rete di produzione è isolata (no accesso diretto a internet), configurare un mirror interno o un **Azure Artifact Registry** che replichi il repository UYUNI. Il team networking deve approvare le regole di accesso al repository esterno prima di procedere.

### 7.2 Refresh e Installazione dei Pacchetti
```bash
zypper --gpg-auto-import-keys refresh
```
```bash
zypper install -y mgradm mgrctl mgradm-bash-completion mgrctl-bash-completion
```
```bash
zypper install -y uyuni-storage-setup-server
```
### 7.3 Verificare Versione Podman

UYUNI richiede Podman >= 4.5.0
```bash
podman --version
```
### 7.4 Abilitare Podman Socket
```bash
systemctl enable --now podman.socket
```

---

## FASE 8: Deployment Container UYUNI

> **[PROD] ATTENZIONE — Certificati SSL**: I certificati SSL devono essere forniti **durante questa fase**, non dopo. Se si installa prima con certificati self-signed e si sostituiscono successivamente, è necessario ridistribuire la nuova CA su **tutti i Salt minion** già registrati e su tutti i Proxy. Questo può causare interruzioni di servizio e richiede operazioni manuali su ogni client. **Procurarsi i certificati aziendali firmati dalla CA aziendale PRIMA di eseguire questa fase.**

> **[PROD] ATTENZIONE — Database esterno**: Prima di eseguire questa fase il database deve essere già operativo e raggiungibile dalla VM Server:
> - **Opzione A (VM)**: verificare con `nc -zv 10.172.2.Z 5432`
> - **Opzione B (Azure PaaS)**: verificare con `nc -zv <nome>.postgres.database.azure.com 5432` e che il Private Endpoint sia configurato

### 8.1 Preparazione Certificati SSL per Produzione

Ottenere dalla CA aziendale:
- `ca-root.pem` — certificato CA root (o chain completa)
- `server.crt` — certificato del server (con SAN `uyuni-server-prod.dominio.aziendale`)
- `server.key` — chiave privata del server

Trasferire i file sulla VM (tramite Azure Bastion o SCP):
```bash
ls -la /tmp/ssl/
# Atteso: ca-root.pem, server.crt, server.key
```

Verificare che il certificato contenga il SAN corretto:
```bash
openssl x509 -in /tmp/ssl/server.crt -text -noout | grep -A2 "Subject Alternative"
```

### 8.2 Esegui Deployment [TEST — senza DB esterno e senza certificati custom]

```bash
# Solo per test — NON usare in produzione
mgradm install podman $(hostname -f)
```

### 8.3 Esegui Deployment [PROD — con DB esterno e certificati custom]

**Opzione A — VM dedicata:**
```bash
mgradm install podman $(hostname -f) \
  --db-host uyuni-db-prod.dominio.aziendale \
  --db-port 5432 \
  --db-name susemanager \
  --db-user susemanager \
  --db-password '<PASSWORD_DB_SICURA>' \
  --ssl-ca-root /tmp/ssl/ca-root.pem \
  --ssl-server-cert /tmp/ssl/server.crt \
  --ssl-server-key /tmp/ssl/server.key
```

**Opzione B — Azure Database for PostgreSQL Flexible Server:**
```bash
mgradm install podman $(hostname -f) \
  --db-host <nome-server>.postgres.database.azure.com \
  --db-port 5432 \
  --db-name susemanager \
  --db-user susemanager \
  --db-password '<PASSWORD_DB_SICURA>' \
  --db-sslmode require \
  --ssl-ca-root /tmp/ssl/ca-root.pem \
  --ssl-server-cert /tmp/ssl/server.crt \
  --ssl-server-key /tmp/ssl/server.key
```

> **[PROD] Opzione B — Note importanti**:
> - Il nome utente su Azure PaaS è nella forma `susemanager` (senza `@nomeserver`, a differenza di versioni legacy di Azure PostgreSQL Single Server)
> - `--db-sslmode require` è necessario perché Flexible Server impone SSL
> - Il database `susemanager` e l'utente `susemanager` devono essere creati sul Flexible Server **prima** di questo comando (vedere sezione database in fondo)
> - Verificare che `mgradm --help` mostri il flag `--db-sslmode`; se non disponibile, configurare SSL nel file `pg_service.conf` del container

Il sistema chiederà:
- **Password CA key**: necessaria solo se si usa la CA interna UYUNI (non con certificati aziendali)
- **Password amministratore**: password per login Web UI — deve rispettare la policy aziendale (min. 12 caratteri, complessità)
- **Email**: email dell'amministratore per notifiche sistema

> **[PROD]**: Salvare la password amministratore e la password CA key in un **secret manager** (es. Azure Key Vault) immediatamente dopo l'installazione. NON salvarle in file di testo o documenti non protetti.

> **[PROD]**: Il flag `--db-host` è supportato da mgradm per puntare a un'istanza PostgreSQL esterna. Verificare la compatibilità con la versione installata con `mgradm --help` prima di procedere. Se il parametro non fosse disponibile nella versione corrente, consultare la documentazione ufficiale per la procedura alternativa.

### 8.4 Verificare Container Attivi

```bash
mgradm status
podman ps
```

Output atteso (UYUNI 2025.10 con DB esterno — solo container server sulla VM):
```
CONTAINER ID  IMAGE                                      STATUS         NAMES
xxxx          registry.opensuse.org/uyuni/server         Up (healthy)   uyuni-server
```

> **[PROD]**: Con DB esterno, il container `uyuni-db` NON è presente su questa VM. Se appare, significa che mgradm ha ignorato il parametro `--db-host` e ha creato un DB locale — **FERMARE l'installazione e verificare la configurazione**.

### 8.5 Eliminare i file certificati dopo il deployment
```bash
# [PROD] — rimuovere i certificati dalla directory temporanea
rm -rf /tmp/ssl/
```

---

## Verificare dell'Installazione

### Verificare Servizi Interni al Container
```bash
sudo mgrctl exec -- systemctl status tomcat.service --no-pager
sudo mgrctl exec -- systemctl status salt-master.service --no-pager
sudo mgrctl exec -- systemctl status taskomatic.service --no-pager
```

### Verifica Connessione al Database Esterno
```bash
# [PROD] — verificare che il server si connetta al DB esterno
podman exec uyuni-server psql -h uyuni-db-prod.dominio.aziendale -U susemanager -d susemanager -c "SELECT 1;"
```

### Accesso Web UI

#### Credenziali Web UI
- **URL**: `https://uyuni-server-prod.dominio.aziendale`
- **Username**: `admin`
- **Password**: quella specificata durante l'installazione

> **[PROD]**: Con i certificati aziendali installati correttamente, il browser NON mostrerà warning. Se viene mostrato un warning certificato, verificare che la CA aziendale sia nel trust store del browser e che il SAN del certificato corrisponda all'FQDN.

### [PROD] Configurazione Post-Installazione Obbligatoria

1. **Politica password** (Admin → Users → User List → admin → Change Password):
   - Minimo 12 caratteri, complessità attivata

2. **Timeout sessione** (Admin → General Configuration):
   - Session Timeout: `900` secondi

3. **HSTS** (Admin → General Configuration):
   - Enable HSTS: attivare

4. **RBAC — Creare utenti con ruoli separati** (Admin → Users → Create User):
   - `uyuni-admin` — UYUNI Administrator
   - `uyuni-channelmgr` — Channel Administrator
   - `uyuni-sysmgr` — System Group Administrator
   - `uyuni-viewer` — Solo lettura

5. **Backup automatico** — configurare cron per backup DB (vedere sezione PostgreSQL)

6. **Azure Monitor** — configurare alert su CPU, RAM, disco

---

## [PROD] Configurazione Database PostgreSQL Esterno

Questa sezione descrive la configurazione del database **prima** del deployment del Server UYUNI. Scegliere una delle due opzioni.

---

### Opzione A — VM Dedicata (IaaS)

#### Configurazione VM Azure — uyuni-db-prod

| Parametro          | Valore                                           |
| ------------------ | ------------------------------------------------ |
| **VM Name**        | uyuni-db-prod                                    |
| **Resource Group** | prod_group                                       |
| **Region**         | Italy North (stessa AZ di uyuni-server-prod)     |
| **Size**           | Standard_D4s_v3 (4 vCPU, 16 GB RAM) minimo      |
| **OS**             | openSUSE Leap 15.6 - Gen2                        |
| **Authentication** | SSH Public Key                                   |
| **OS Disk**        | 64 GB Premium SSD LRS                            |
| **Data Disk**      | 100 GB+ Premium SSD NVMe (P15 o superiore)       |
| **IP**             | 10.172.2.Z (IP privato fisso)                    |
| **Public IP**      | None                                             |
| **NSG**            | uyuni-db-prod-nsg                                |

#### NSG per uyuni-db-prod

| Priority | Nome              | Port | Protocol | Source      | Destination | Action |
| -------- | ----------------- | ---- | -------- | ----------- | ----------- | ------ |
| 100      | AllowPG_FromUyuni | 5432 | TCP      | 10.172.2.X  | 10.172.2.Z  | Allow  |
| 110      | AllowSSH_Bastion  | 22   | TCP      | IP Bastion  | 10.172.2.Z  | Allow  |
| 4096     | DenyAll           | *    | *        | *           | *           | Deny   |

#### Preparazione VM uyuni-db-prod

Eseguire sulla VM `uyuni-db-prod` le stesse FASI 1-4 del documento (OS update, NTP, hostname, firewall), poi procedere con:

```bash
# Disco PostgreSQL (es. /dev/sdb)
parted /dev/sdb --script mklabel gpt
parted /dev/sdb --script mkpart primary 0% 100%

pvcreate /dev/sdb1
vgcreate vg_uyuni_pgsql /dev/sdb1
lvcreate -l 100%FREE -n lv_pgsql vg_uyuni_pgsql

mkfs.xfs /dev/mapper/vg_uyuni_pgsql-lv_pgsql

mkdir -p /pgsql_storage
mount /dev/mapper/vg_uyuni_pgsql-lv_pgsql /pgsql_storage
echo "/dev/mapper/vg_uyuni_pgsql-lv_pgsql /pgsql_storage xfs defaults,nofail 0 0" >> /etc/fstab
systemctl daemon-reload
```

#### Installazione Container PostgreSQL UYUNI

```bash
zypper ar https://download.opensuse.org/repositories/systemsmanagement:/Uyuni:/Stable/images/repo/Uyuni-Server-POOL-$(arch)-Media1/ uyuni-server-stable
zypper --gpg-auto-import-keys refresh
zypper install -y mgradm mgrctl podman
systemctl enable --now podman.socket

# Avviare solo il container database
mgradm install podman --db-only \
  --db-data-path /pgsql_storage \
  $(hostname -f)
```

> Se il parametro `--db-only` non fosse disponibile, avviare il container manualmente:
> ```bash
> podman run -d \
>   --name uyuni-db \
>   -e POSTGRES_DB=susemanager \
>   -e POSTGRES_USER=susemanager \
>   -e POSTGRES_PASSWORD='<PASSWORD_DB_SICURA>' \
>   -v /pgsql_storage:/var/lib/postgresql/data \
>   -p 5432:5432 \
>   registry.opensuse.org/uyuni/server-postgresql:latest
> systemctl enable uyuni-db
> ```

#### Verifica Accessibilità dal Server (Opzione A)

```bash
nc -zv 10.172.2.Z 5432
```
Output atteso: `Connection to 10.172.2.Z 5432 port [tcp/postgresql] succeeded!`

#### Backup PostgreSQL (Opzione A)

```bash
cat > /etc/cron.daily/backup-uyuni-db <<'EOF'
#!/bin/bash
BACKUP_DIR="/backup/postgresql"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
podman exec uyuni-db pg_dump -U susemanager susemanager | gzip > $BACKUP_DIR/susemanager_$DATE.sql.gz
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete
EOF
chmod +x /etc/cron.daily/backup-uyuni-db
```

> **[PROD]**: Integrare con **Azure Blob Storage** per retention off-VM. Testare il restore periodicamente.

---

### Opzione B — Azure Database for PostgreSQL Flexible Server (PaaS) *(Raccomandato)*

Non richiede provisioning di VM, OS, patch o storage. Azure gestisce backup, HA e aggiornamenti minori automaticamente.

#### Provisioning Flexible Server dal Portale Azure

1. Cercare **Azure Database for PostgreSQL Flexible Server**
2. **Create → Flexible server**

| Parametro                | Valore consigliato                              |
| ------------------------ | ----------------------------------------------- |
| **Resource Group**       | prod_group                                      |
| **Server name**          | uyuni-db-prod                                   |
| **Region**               | Italy North                                     |
| **PostgreSQL version**   | 16 (o la versione usata internamente da UYUNI)  |
| **Workload type**        | Production                                      |
| **Compute tier**         | General Purpose                                 |
| **Compute size**         | Standard_D4ds_v5 (4 vCore, 16 GB RAM) minimo    |
| **Storage**              | 128 GB+ con auto-grow abilitato                 |
| **HA**                   | Zone-redundant standby *(99.99% SLA)*           |
| **Backup retention**     | 7+ giorni, Geo-redundant backup abilitato       |
| **Authentication**       | PostgreSQL authentication only                  |
| **Admin username**       | `pgadmin` *(NON usare `susemanager` come admin)*|
| **Admin password**       | Salvare in Azure Key Vault                      |

3. Tab **Networking**:
   - **Connectivity method**: `Private access (VNet Integration)`
   - **VNet**: ASL0603-spoke10-spoke-italynorth
   - **Subnet**: subnet dedicata (delegata a `Microsoft.DBforPostgreSQL/flexibleServers`)
   - **Private DNS zone**: creare una nuova zona privata (es. `uyuni-db-prod.private.postgres.database.azure.com`) — Azure la crea automaticamente

4. **Disable public access**: assicurarsi che **Public access** sia `Disabled`

> **[PROD]**: Con VNet Integration il Flexible Server ottiene un IP privato nella subnet e non è mai raggiungibile da internet. Non è necessario configurare NSG separato — la comunicazione avviene interamente nella VNet.

#### Creazione Database e Utente UYUNI

Connettersi al Flexible Server tramite Azure Bastion → psql, oppure dal portale con **Cloud Shell**:

```sql
-- Connettersi come admin (pgadmin)
CREATE USER susemanager WITH PASSWORD '<PASSWORD_DB_SICURA>';
CREATE DATABASE susemanager OWNER susemanager;

-- Abilitare le estensioni richieste da UYUNI
\c susemanager
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

> **[PROD]**: Le estensioni `uuid-ossp` e `pgcrypto` devono essere abilitate prima del deployment UYUNI. Verificare che siano presenti in `SHOW azure.extensions;` sul Flexible Server. In caso contrario abilitarle da **Server parameters → azure.extensions**.

#### Verifica Accessibilità dal Server (Opzione B)

Dalla VM `uyuni-server-prod`:
```bash
# Verificare risoluzione DNS del Flexible Server (via Private DNS Zone)
host uyuni-db-prod.private.postgres.database.azure.com

# Verificare connettività porta 5432
nc -zv uyuni-db-prod.private.postgres.database.azure.com 5432
```

#### Backup PostgreSQL (Opzione B)

Il backup è **gestito automaticamente da Azure**:
- Backup automatici giornalieri inclusi nel servizio
- Point-in-time restore fino a 35 giorni (configurabile)
- Geo-redundant backup abilitabile per DR in altra region

Non è necessario configurare cron job. Verificare la policy di retention da **Azure Portal → Flexible Server → Backup and restore**.

---

## Troubleshooting

### I container non si avviano
```bash
podman logs uyuni-server
podman inspect uyuni-server --format '{{.State.Status}}'
mgradm restart
```

### Il database non è raggiungibile

**Opzione A — VM dedicata:**
```bash
# Verifica connettività
nc -zv uyuni-db-prod.dominio.aziendale 5432

# Verificare NSG tra le due VM in Azure Portal
# Verificare che il container DB sia attivo (accedere alla VM uyuni-db-prod via Bastion)
podman ps | grep uyuni-db
podman logs uyuni-db --tail 30

# Test connessione PostgreSQL
podman exec -it uyuni-db psql -U susemanager -c "SELECT 1;"
```

**Opzione B — Azure PaaS:**
```bash
# Verificare risoluzione DNS (Private DNS Zone)
host uyuni-db-prod.private.postgres.database.azure.com

# Verifica connettività porta
nc -zv uyuni-db-prod.private.postgres.database.azure.com 5432

# Se nc fallisce: verificare in Azure Portal che
# - Il Flexible Server sia in stato "Available"
# - La VNet Integration sia configurata sulla subnet corretta
# - La subnet sia delegata a Microsoft.DBforPostgreSQL/flexibleServers
# - La Private DNS Zone sia linkata alla VNet della VM Server

# Test connessione autenticata (dalla VM Server)
psql "host=uyuni-db-prod.private.postgres.database.azure.com \
  port=5432 dbname=susemanager user=susemanager sslmode=require" \
  -c "SELECT 1;"
```

### Problemi Certificati SSL
```bash
# Verificare certificato attivo
mgrctl exec -- openssl x509 -in /etc/pki/tls/certs/spacewalk.crt -text -noout

# Verificare validità e SAN
mgrctl exec -- openssl x509 -in /etc/pki/tls/certs/spacewalk.crt -noout -dates -ext subjectAltName

# Test connessione HTTPS
openssl s_client -connect uyuni-server-prod.dominio.aziendale:443 </dev/null 2>/dev/null | openssl x509 -noout -dates
```

### [PROD] Sostituzione Certificati SSL Post-Installazione

> Questa procedura è necessaria solo se si è installato con certificati self-signed e si vuole passare a certificati aziendali. **Eseguire PRIMA di registrare qualsiasi client per minimizzare l'impatto.**

```bash
# 1. Aggiornare i Podman secrets con i nuovi certificati
podman secret rm uyuni-server-cert uyuni-server-key uyuni-ca-cert
podman secret create uyuni-server-cert /path/to/server.crt
podman secret create uyuni-server-key /path/to/server.key
podman secret create uyuni-ca-cert /path/to/ca-root.pem

# 2. Rigenerare i certificati tramite mgradm
mgradm ssl regen-cert

# 3. Riavviare il server
mgradm restart

# 4. Se ci sono client già registrati, ridistribuire la CA
#    tramite Salt State o manualmente su ogni client:
mgrctl exec -- salt '*' state.apply channels
```

### Problemi DNS/Hostname
```bash
# Verificare FQDN all'interno del container
mgrctl exec -- hostname -f
hostname -f

# Verificare risoluzione dal container
mgrctl exec -- ping -c 1 $(hostname -f)

# [PROD] — verificare risoluzione DB dall'interno del container
mgrctl exec -- ping -c 1 uyuni-db-prod.dominio.aziendale
```

### Storage Pieno
```bash
df -h /manager_storage /
podman system df
mgrctl exec -- spacewalk-repo-sync --clean-cache
```

### Espansione Disco Azure (LVM)
```bash
# 1. Ferma la VM da Azure Portal
# 2. Disks → seleziona il disco → aumenta dimensione
# 3. Avvia la VM

lsblk
sudo growpart /dev/sdb 1
sudo pvresize /dev/sdb1
sudo lvextend -l +100%FREE /dev/vg_uyuni_repo/lv_repo
sudo xfs_growfs /manager_storage
```

### Reset Password Admin
```bash
mgrctl exec -- satpasswd -u admin
```

---

## Comandi Utili - Quick Reference

### Gestione Container
```bash
mgradm status              # Stato generale UYUNI
mgradm restart             # Riavviare tutti i container
mgradm stop                # Ferma tutti i container
mgradm start               # Avvia tutti i container
podman ps                  # Lista container attivi
podman ps -a               # Lista tutti i container
```

### Accesso Container
```bash
mgrctl term                      # Shell nel container server
mgrctl exec -- <comando>         # Esegue comando nel container
# [PROD] accesso DB — dalla VM uyuni-db-prod
podman exec -it uyuni-db bash
```

### Logs
```bash
podman logs uyuni-server           # Log server
podman logs -f uyuni-server        # Log in tempo reale
journalctl -u uyuni-server -f      # Log systemd
```

### Storage
```bash
df -h /manager_storage         # Spazio disco repository
lvs                            # Volumi logici
vgs                            # Volume groups
podman system df               # Uso storage container
```

---

## Riferimenti

- [Documentazione Ufficiale UYUNI 2025.10](https://www.uyuni-project.org/uyuni-docs/en/uyuni/index.html)
- [Installation and Upgrade Guide](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/uyuni-installation-and-upgrade-overview.html)
- [Server Deployment on openSUSE](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/container-deployment/uyuni/server-deployment-uyuni.html)
- [Network Requirements](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/network-requirements.html)
- [SSL Certificates](https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/ssl-certs.html)
- [Client Configuration Guide](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/uyuni-client-config-overview.html)
- [GitHub UYUNI Project](https://github.com/uyuni-project/uyuni)
- [UYUNI Release Notes 2025.10](https://www.uyuni-project.org/pages/stable-version.html)
- [Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/overview)
- [Flexible Server — Private Access (VNet Integration)](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-networking-private)
- [Flexible Server — Extensions](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-extensions)
