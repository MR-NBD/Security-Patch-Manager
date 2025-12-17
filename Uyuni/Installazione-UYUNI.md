## Per ambiente di Test

Installazione di **UYUNI 2025.10** su **openSUSE Leap 15.6** in ambiente **Azure** con deployment containerizzato tramite **Podman**. 

### Accesso alla VM
L'accesso alla VM avviene **esclusivamente tramite Azure Bastion** (nessun IP pubblico).

> UYUNI è un progetto open-source upstream di SUSE Manager. Dalla versione 2024.10, UYUNI utilizza esclusivamente il deployment containerizzato basato su Podman. La versione 2025.10 introduce un'architettura a **2 container separati** (uno per ilserver e uno per il database PostgreSQL).

>A partire da UYUNI 2025.10, l'OS ufficialmente validato è **openSUSE Tumbleweed**. Tuttavia, **openSUSE Leap 15.6 è pienamente supportato dal progetto** in quanto si basa su quello per costruite le immagini container UYUNI stesse.
### Requisiti Hardware

| Componente       | Test (Attuale)      | Production               |
| ---------------- | ------------------- | ------------------------ |
| CPU              | 8 core              | 8+ core                  |
| RAM              | 32 GB               | 32+ GB                   |
| Disco OS         | Default (~30 GB)    | 100 GB SSD               |
| Disco Repository | 128 GB Standard SSD | 500+ GB Premium SSD      |
| Disco PostgreSQL | 32 GB Standard SSD  | 100+ GB Premium SSD NVMe |
### Architettura Target

#### UYUNI SERVER - Host Container (openSUSE Leap 15.6)

##### Componenti Container (UYUNI 2025.10):

| Container | Immagine | Funzione |
|-----------|----------|----------|
| **uyuni-server** | `registry.opensuse.org/uyuni/server:latest` | Server principale UYUNI |
| **uyuni-db** | `registry.opensuse.org/uyuni/server-postgresql:latest` | Database PostgreSQL dedicato |
##### Servizi nel container uyuni-server:
- Salt Master
- Taskomatic
- Tomcat (Web UI)
- Apache HTTPD (Reverse Proxy)
- Cobbler (Provisioning)
##### Funzionalità:
- Salt-based Configuration Management
- Patch Management multi-OS (Ubuntu, Debian, RHEL, SLES, etc.)
- CVE Audit (OVAL-based)
- Content Lifecycle Management
- Role-Based Access Control (RBAC)

##### Layout Storage:
```
sda (OS Disk - 30GB)                     
 └─/                              (Root filesystem)
 └─/var/lib/containers/storage    (Container storage)

sdb (Data Disk 1 - 128GB) [LVM]
 └─vg_uyuni_repo/lv_repo
   └─/manager_storage             (Repository packages)
     └─ symlink → /var/lib/containers/storage/volumes/var-spacewalk

sdc (Data Disk 2 - 32GB) [LVM]                     
 └─vg_uyuni_pgsql/lv_pgsql
   └─/pgsql_storage               (PostgreSQL data)
     └─ symlink → /var/lib/containers/storage/volumes/var-pgsql
``` 

---
## Indice

- [FASE 1: Preparazione del Sistema Base](#fase-1-preparazione-del-sistema-base)
- [FASE 2: Configurazione NTP con Chrony](#fase-2-configurazione-ntp-con-chrony)
- [FASE 3: Configurazione Hostname e DNS](#fase-3-configurazione-hostname-e-dns)
- [FASE 4: Configurazione Base Sicurezza](#fase-4-configurazione-base-sicurezza-test)
- [FASE 5: Configurazione Storage Dedicato](#fase-5-configurazione-storage-dedicato)
- [FASE 6: Configurazione Firewall](#fase-6-configurazione-firewall)
- [FASE 7: Installazione Repository UYUNI](#fase-7-installazione-repository-uyuni)
- [FASE 8: Deployment Container UYUNI](#fase-8-deployment-container-uyuni)
- [NON TESTATO - FASE 9: SSL/TLS (Solo Production)](#-fase-9-configurazione-ssltls-solo-production)
- [NON TESTATO - FASE 10: Hardening Post-Installazione (Solo Production)](#-fase-10-hardening-post-installazione-solo-production)
- [FASE 11: Verifica dell'Installazione](#fase-11-verifica-dellinstallazione-test)
- [Troubleshooting](#troubleshooting)

---
## DEPLOYMENT SU MICROSOFT AZURE
### Configurazione VM Azure - Ambiente TEST

| Parametro | Valore |
|-----------|--------|
| **Subscription** | ASL0603-spoke10 |
| **Resource Group** | test_group |
| **VM Name** | uyuni-server-test |
| **Region** | Italy North |
| **Availability** | Availability Zone 1 |
| **Security Type** | Trusted launch (Secure boot + vTPM) |
| **Image** | openSUSE Leap 15.6 - Gen2 |
| **Architecture** | x64 |
| **Size** | Standard D8as v5 (8 vCPU, 32 GB RAM) |
| **Username** | azureuser |
| **Authentication** | Password |
| **OS Disk** | Standard SSD LRS |
| **Data Disks** | 2 dischi (128GB + 32GB) |
| **VNet** | ASL0603-spoke10-spoke-italynorth |
| **Subnet** | default (10.172.2.0/27) |
| **Public IP** | None |
| **NSG** | uyuni-server-test-nsg |
### Configurazione NSG per Test
Per l'ambiente di test, configurare il NSG `uyuni-server-test-nsg` con queste regole minime:

| Priority | Nome | Port | Protocol | Source | Action |
|----------|------|------|----------|--------|--------|
| 100 | AllowHTTPS | 443 | TCP | VNet | Allow |
| 110 | AllowSalt | 4505-4506 | TCP | VNet | Allow |
### Configurazioni Aggiuntive per Production (Futuro)
Per il passaggio in production, da valutare:
- Premium SSD per i dischi dati
- Azure Backup abilitato
- NSG più restrittivo (IP specifici invece di VNet)
- Azure Private DNS Zone
- Certificati SSL firmati da CA aziendale
- Azure Monitor + Log Analytics

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

![[image.png]]
### 1.2 Aggiornamento Sistema
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
### 1.3 Installazione Pacchetti Prerequisiti

```bash
zypper install -y \
  chrony \
  podman \
  firewalld \
  vim \
  wget \
  curl \
  jq
```

> **PER PRODUZIONE**: Aggiungere `audit`, `fail2ban`, `rsync`, `htop`, `iotop` per monitoring e sicurezza.

---
## FASE 2: Configurazione NTP con Chrony
La sincronizzazione temporale è **CRITICA** per il corretto funzionamento di UYUNI, Salt, e i certificati SSL.
### 2.1 Configurazione Chrony
#### Backup configurazione originale
```bash
cp /etc/chrony.conf /etc/chrony.conf.bak
```
#### Modifica configurazione per server NTP aziendali (non testato)
```bash
vim /etc/chrony.conf
```

Esempio configurazione con server NTP dedicati:
```
# Server NTP primari (sostituire con i propri server aziendali)
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
### 2.2 Abilita e Avvia il Servizio
```bash
systemctl enable --now chronyd
```
#### Verifica le sorgenti NTP
```bash
chronyc sources -v
```
#### Abilita NTP via timedatectl
```bash
timedatectl set-ntp true
```
#### Verifica stato sincronizzazione
```bash
timedatectl status
```

Output atteso:

![[2025-12-17 14_06_29-Greenshot.png]]

Verificare che `System clock synchronized: yes` sia presente.

---
## FASE 3: Configurazione Hostname e DNS
### 3.1 Prerequisiti DNS
UYUNI **RICHIEDE** un DNS funzionante con risoluzione diretta e inversa. Il comando `hostname -f` deve restituire l'FQDN completo.
### 3.2 Configura l'Hostname
#### Imposta hostname
```bash
hostnamectl set-hostname uyuni-server-test.uyuni.internal
```

Sostituire `uyuni.internal` con il dominio interno Azure o aziendale.
#### Verifica hostname
```bash
hostname
```
```bash
hostname -f
```
### 3.3 Configura il File /etc/hosts
#### Recupera l'IP privato della VM
```bash
ip addr show eth0 
```
#### Backup del file hosts originale
```bash
cp /etc/hosts /etc/hosts.bak
```
#### Edita il file hosts
```bash
vim /etc/hosts
```

Aggiungi la riga (sostituire con IP e dominio corretto):
```
10.172.2.5    uyuni-server-test.uyuni.internal    uyuni-server-test
```
### 3.4 Configurazione DNS Azure (Opzionale ma Consigliato)

Per un ambiente production, configura una **Azure Private DNS Zone**:

1. **Portale Azure** → **Private DNS zones** → **Create**
2. Nome: `uyuni.internal`
3. Link alla VNet `ASL0603-spoke10-spoke-italynorth`
4. Aggiungi record A per `uyuni-server-test`

### 3.5 Verifica la Configurazione DNS

#### Test risoluzione diretta
```bash
ping -c 2 $(hostname -f)
```

#### Verifica FQDN
```bash
hostname -f
```

Output atteso:
```
uyuni-server-test.uyuni.internal
```

> **IMPORTANTE**: Se `hostname -f` non restituisce l'FQDN completo, UYUNI avrà problemi. Verifica `/etc/hosts` e riprova.

---
## FASE 4: Configurazione Base Sicurezza (Test)

> **PER PRODUCTION**: Questa sezione è semplificata per l'ambiente di test. Per production, implementare hardening completo (SSH keys, audit, fail2ban, etc.)

### 4.1 Verifica Stato Servizi Base

```bash
# Verifica che firewalld sia attivo
systemctl status firewalld

# Se non attivo, abilitalo
systemctl enable --now firewalld
```

### 4.2 Hardening Aggiuntivo per Production (Futuro)

Quando passerai in production, implementa:

- [ ] **SSH Hardening**: Disabilita password, usa solo chiavi SSH
- [ ] **Audit Daemon**: Logging avanzato per compliance
- [ ] **Fail2Ban**: Protezione brute-force
- [ ] **SELinux/AppArmor**: Controllo accessi mandatorio

> **NOTA TEST**: Per l'ambiente di test, la configurazione di base con Azure Bastion e NSG è sufficiente.

---
## FASE 5: Configurazione Storage Dedicato
> **CRITICO PER PRODUZIONE**: Utilizzare dischi dedicati per repository e database migliora drasticamente le performance e permette recovery più semplice in caso di problemi.

### 5.1 Identifica i Dischi Disponibili (Azure)

In Azure, i dischi dati aggiunti durante la creazione della VM appaiono come dispositivi aggiuntivi:

```bash
lsblk
```

Esempio output tipico Azure:
```
NAME    SIZE TYPE MOUNTPOINT
sda      30G disk             <- OS principale
├─sda1    2M part 
├─sda2  512M part /boot/efi
├─sda3    1G part /boot
└─sda4 28.5G part /
sdb     128G disk             <- Disco dati 1 (Repository)
sdc      32G disk             <- Disco dati 2 (PostgreSQL)
```

> **ATTENZIONE AZURE**: Verificare sempre con `lsblk` quali sono i dischi dati. I nomi possono variare!

### 5.2 Scelta del Metodo di Configurazione Storage

UYUNI offre due metodi per configurare lo storage:

| Metodo | Pro | Contro | Consigliato per |
|--------|-----|--------|-----------------|
| **mgr-storage-server** | Semplice, automatico | No LVM, no resize dinamico | Test rapidi |
| **LVM Manuale** | Flessibile, resize, snapshot | Configurazione manuale | Production, Cloud |

> **RACCOMANDAZIONE AZURE**: Per ambienti cloud, LVM è preferibile perché permette di espandere i volumi senza downtime.

### 5.3 Metodo A: Script UYUNI (Semplice)

> **NOTA**: Questo metodo formatta i dischi come XFS senza LVM.

```bash
# Installa tool storage
zypper install -y uyuni-storage-setup-server

# Configura storage (sostituisci con i tuoi device)
mgr-storage-server /dev/sdb /dev/sdc
```

### 5.4 Metodo B: Configurazione LVM Manuale (Consigliato per Azure)

Questa configurazione permette espansione futura dei volumi.

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
```

#### Disco PostgreSQL (es. /dev/sdc)
```bash
# Crea partizione
parted /dev/sdc --script mklabel gpt
parted /dev/sdc --script mkpart primary 0% 100%

# Configura LVM
pvcreate /dev/sdc1
vgcreate vg_uyuni_pgsql /dev/sdc1
lvcreate -l 100%FREE -n lv_pgsql vg_uyuni_pgsql

# Formatta XFS
mkfs.xfs /dev/mapper/vg_uyuni_pgsql-lv_pgsql

# Crea mount point e monta
mkdir -p /pgsql_storage
mount /dev/mapper/vg_uyuni_pgsql-lv_pgsql /pgsql_storage

# Aggiungi a fstab
echo "/dev/mapper/vg_uyuni_pgsql-lv_pgsql /pgsql_storage xfs defaults,nofail 0 0" >> /etc/fstab
```

> **NOTA AZURE**: L'opzione `nofail` in fstab è importante per evitare problemi di boot se un disco non è disponibile.

#### Reload systemd
```bash
systemctl daemon-reload
```

### 5.5 Collegamento Storage ai Volumi Podman (CRITICO per LVM)

> **⚠️ IMPORTANTE**: Se hai usato il Metodo B (LVM), devi collegare i mount point ai volumi Podman che UYUNI si aspetta.

```bash
# Crea directory per i volumi Podman
mkdir -p /var/lib/containers/storage/volumes/var-spacewalk
mkdir -p /var/lib/containers/storage/volumes/var-pgsql

# Crea symlink ai tuoi mount point LVM
# (oppure monta direttamente sui volumi - vedi alternativa sotto)
ln -s /manager_storage /var/lib/containers/storage/volumes/var-spacewalk/_data
ln -s /pgsql_storage /var/lib/containers/storage/volumes/var-pgsql/_data
```

**Alternativa (mount bind):**
```bash
# Aggiungi a /etc/fstab
echo "/manager_storage /var/lib/containers/storage/volumes/var-spacewalk/_data none bind 0 0" >> /etc/fstab
echo "/pgsql_storage /var/lib/containers/storage/volumes/var-pgsql/_data none bind 0 0" >> /etc/fstab

# Crea directory e monta
mkdir -p /var/lib/containers/storage/volumes/var-spacewalk/_data
mkdir -p /var/lib/containers/storage/volumes/var-pgsql/_data
mount -a
```

### 5.6 Verifica Configurazione Storage

```bash
# Verifica mount points
df -hP /manager_storage /pgsql_storage

# Verifica LVM
lvs
vgs

# Verifica volumi Podman
ls -la /var/lib/containers/storage/volumes/
```

Output atteso:
```
Filesystem                           Size  Used Avail Use% Mounted on
/dev/mapper/vg_uyuni_repo-lv_repo    128G  2.5G  126G   2% /manager_storage
/dev/mapper/vg_uyuni_pgsql-lv_pgsql   32G  659M   32G   3% /pgsql_storage
```

---
## FASE 6: Configurazione Firewall
### 6.1 Abilita Firewalld

```bash
systemctl enable --now firewalld
```

```bash
systemctl status firewalld
```
### 6.2 Configura Porte UYUNI

```bash
# HTTP/HTTPS (Web UI e client)
firewall-cmd --permanent --add-port=80/tcp
firewall-cmd --permanent --add-port=443/tcp

# Salt Master (comunicazione con i client)
firewall-cmd --permanent --add-port=4505/tcp
firewall-cmd --permanent --add-port=4506/tcp

# PostgreSQL (per container db separato - UYUNI 2025.x)
firewall-cmd --permanent --add-port=5432/tcp
```
### 6.3 Applica le Modifiche

```bash
firewall-cmd --reload
```
### 6.4 Verifica Configurazione

```bash
firewall-cmd --list-all
```

Output atteso:
```
public (active)
  target: default
  interfaces: eth0
  services: ssh
  ports: 80/tcp 443/tcp 4505/tcp 4506/tcp 5432/tcp
```

> **PER PRODUCTION**: Aggiungere rich rules per limitare l'accesso a subnet specifiche invece di accettare da qualsiasi IP.

---
## FASE 7: Installazione Repository UYUNI
### 7.1 Aggiungi Repository UYUNI Stable per openSUSE Leap 15.6

> **NOTA**: Il repository corretto per Leap 15.6 utilizza il path delle immagini container.

```bash
# Verifica se il repository è già presente
zypper lr | grep uyuni

# Se non presente, aggiungi il repository
zypper ar https://download.opensuse.org/repositories/systemsmanagement:/Uyuni:/Stable/images/repo/Uyuni-Server-POOL-$(arch)-Media1/ uyuni-server-stable
```

### 7.2 Refresh e Installa Pacchetti

```bash
# Accetta chiave GPG e refresh
zypper --gpg-auto-import-keys refresh
```

```bash
# Installa tool di gestione UYUNI
zypper install -y mgradm mgrctl mgradm-bash-completion mgrctl-bash-completion
```

> **NOTA**: Se uyuni-storage-setup-server non è già installato:
```bash
zypper install -y uyuni-storage-setup-server
```

### 7.3 Verifica Versione Podman

> **IMPORTANTE**: UYUNI richiede Podman >= 4.5.0

```bash
podman --version
```

Output atteso:
```
podman version 4.9.5 o superiore
```

### 7.4 Abilita Podman Socket

```bash
systemctl enable --now podman.socket
```

> **PER PRODUCTION**: Aggiungere configurazione limiti container in `/etc/containers/containers.conf.d/`

---
## FASE 8: Deployment Container UYUNI
### 8.1 Esegui Deployment

```bash
mgradm install podman $(hostname -f)
```

Il sistema chiederà:
- **Password CA key**: scegli una password sicura (annotala!)
- **Password amministratore**: password per login Web UI (annotala!)
- **Email**: email per notifiche sistema

### 8.2 Monitoraggio Deployment
In un altro terminale (apri una nuova sessione Bastion), monitora il progresso:

```bash
# Monitora tutti i container
sudo podman logs -f uyuni-server

# Oppure per il database
sudo podman logs -f uyuni-db
```

### 8.3 Verifica Container Attivi

> **NOTA UYUNI 2025.x**: L'architettura prevede **2 container separati**.

Al termine del deployment:

```bash
mgradm status
```

```bash
podman ps
```

Output atteso (UYUNI 2025.10):
```
CONTAINER ID  IMAGE                                                 STATUS         NAMES
abc123def456  registry.opensuse.org/uyuni/server-postgresql:latest  Up (healthy)   uyuni-db
def456abc789  registry.opensuse.org/uyuni/server:latest             Up (healthy)   uyuni-server
```

> **IMPORTANTE**: Devono essere presenti **entrambi i container** con status "healthy".

### 8.4 Per Production: Certificati Custom
Per production, invece del comando base, usa:

```bash
mgradm install podman $(hostname -f) \
  --ssl-ca-root /path/to/ca-root.pem \
  --ssl-server-cert /path/to/server.crt \
  --ssl-server-key /path/to/server.key
```

---

## FASE 9: Configurazione SSL/TLS (Solo Production)

> **NOTA TEST**: Per l'ambiente di test, UYUNI genera automaticamente certificati self-signed durante l'installazione. Questa fase è necessaria solo per production.

### 9.1 Certificati per Test

Durante il deployment (FASE 8), UYUNI crea automaticamente:
- Certificato CA self-signed
- Certificato server self-signed

Questi sono **sufficienti per i test**.

> **⚠️ BROWSER WARNING**: Il browser mostrerà un avviso di sicurezza per il certificato self-signed. È normale per l'ambiente di test.

### 9.2 Per Production (Futuro)

Quando passerai in production, dovrai:
- [ ] Generare CSR per la CA aziendale
- [ ] Ottenere certificato firmato
- [ ] Sostituire certificati con `podman secret create --replace`
- [ ] Abilitare HSTS
- [ ] Configurare certificati per il database

---
## FASE 10: Hardening Post-Installazione (Solo Production)

> **NOTA TEST**: Questa fase è opzionale per l'ambiente di test. Implementa solo la verifica base (FASE 11).
### Per Production (Futuro)

Quando passerai in production, implementa:
- [ ] Politica password forte (12+ caratteri, complessità)
- [ ] Timeout sessione (900 secondi)
- [ ] Audit logging JSON
- [ ] Backup automatico con cron
- [ ] RBAC con ruoli separati (Admin, Channel Admin, System Admin, Viewer)

---
## FASE 11: Verifica dell'Installazione (Test)

> **IMPORTANTE**: Questa è la fase principale per validare che l'installazione funzioni correttamente.

### 11.1 Verifica Stato Container (UYUNI 2025.x)

```bash
# Status generale
mgradm status

# Verifica entrambi i container
podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Output atteso: tutti i container "Up" e "healthy"

### 11.2 Verifica Servizi Interni al Container

```bash
# Verifica Tomcat (Web UI)
sudo mgrctl exec -- systemctl status tomcat.service --no-pager

# Verifica Salt Master
sudo mgrctl exec -- systemctl status salt-master.service --no-pager

# Verifica Taskomatic
sudo mgrctl exec -- systemctl status taskomatic.service --no-pager
```

### 11.3 Accesso Web UI

#### Opzione A: Tunneling tramite Bastion (consigliato)

Poiché la VM non ha IP pubblico, per accedere alla Web UI dal tuo PC:

1. **Da Azure Bastion**, crea un tunnel SSH:
   - Usa la funzione "Bastion Tunneling" (se disponibile nel tuo piano)
   - Oppure accedi via Bastion e usa `curl` per test rapidi

2. **Test rapido da Bastion**:
```bash
curl -k https://localhost/rhn/manager/login
```

Se ritorna HTML, il server web funziona.

#### Opzione B: Da una VM nella stessa VNet

Da un'altra VM nella stessa VNet (es. una VM client):
```bash
curl -k https://uyuni-server-test.uyuni.internal/rhn/manager/login
```

#### Credenziali Web UI
- **Username**: `admin`
- **Password**: quella specificata durante l'installazione (FASE 8)

> **CERTIFICATO**: Il browser mostrerà un warning per il certificato self-signed. Clicca "Avanzate" → "Procedi comunque". È normale per l'ambiente di test.

### 11.4 Verifica Logs Container

```bash
# Log server principale
podman logs uyuni-server

# Log database
podman logs uyuni-db

# Log in tempo reale (Ctrl+C per uscire)
podman logs -f uyuni-server
```

### 11.5 Accesso Shell Container

Per diagnostica avanzata:

```bash
# Shell nel container server
mgrctl term

# Shell nel container database
podman exec -it uyuni-db bash
```

Digita `exit` per uscire.

### 11.6 Verifica Porte in Ascolto

```bash
ss -tlnp | grep -E '(443|4505|4506|80|5432)'
```

Output atteso:
```
LISTEN  0  128  *:443   *:*   (httpd)
LISTEN  0  128  *:4505  *:*   (salt-master)
LISTEN  0  128  *:4506  *:*   (salt-master)
LISTEN  0  128  *:5432  *:*   (postgres)
```

### 11.7 Test API (Opzionale)

```bash
# Test endpoint API
sudo mgrctl exec -- curl -s -o /dev/null -w "%{http_code}\n" http://localhost/rpc/api

# Output atteso: 200
```

### 11.8 Test Connettività da Client (Futuro)

Quando registrerai i client, da essi verifica:

```bash
# Test HTTPS
curl -k https://uyuni-server-test.uyuni.internal/rhn/manager/login

# Test Salt ports
nc -zv uyuni-server-test.uyuni.internal 4505
nc -zv uyuni-server-test.uyuni.internal 4506
```

---
## Troubleshooting

### Container non si avvia

```bash
# Verifica logs di entrambi i container
podman logs uyuni-server
podman logs uyuni-db

# Verifica stato dettagliato
podman inspect uyuni-server --format '{{.State.Status}}'
podman inspect uyuni-db --format '{{.State.Status}}'

# Riavvia container
mgradm restart
```

### Database non raggiungibile

```bash
# Verifica container db
podman ps | grep uyuni-db

# Test connessione PostgreSQL
podman exec -it uyuni-db psql -U spacewalk -c "SELECT 1;"

# Verifica logs database
podman logs uyuni-db --tail 50
```

### Problemi Certificati SSL

```bash
# Verifica certificato attivo
mgrctl exec -- openssl x509 -in /etc/pki/tls/certs/spacewalk.crt -text -noout

# Verifica validità
openssl s_client -connect localhost:443 </dev/null 2>/dev/null | openssl x509 -noout -dates
```

### Problemi DNS/Hostname

```bash
# Verifica FQDN all'interno del container
mgrctl exec -- hostname -f

# Deve corrispondere all'hostname host
hostname -f

# Verifica risoluzione dal container
mgrctl exec -- ping -c 1 $(hostname -f)
```

### Storage Pieno

```bash
# Verifica spazio
df -h /manager_storage /pgsql_storage

# Verifica volumi Podman
podman system df

# Pulizia cache repository (con cautela)
mgrctl exec -- spacewalk-repo-sync --clean-cache
```

### Reset Password Admin

```bash
mgrctl exec -- satpasswd -u admin
```

### Problemi Specifici Azure

#### VM non raggiungibile
1. Verifica che la sessione Bastion sia attiva
2. Riprova la connessione Bastion dal portale Azure
3. Come alternativa, usa **Serial Console** (vedi sotto)

#### Disco dati non montato dopo reboot
```bash
# Verifica fstab ha l'opzione nofail
cat /etc/fstab | grep -E "(manager_storage|pgsql_storage)"

# Mount manuale
mount -a

# Verifica
df -h
```

#### Problemi DNS
```bash
# Verifica risoluzione interna
ping $(hostname -f)

# Se fallisce, verifica /etc/hosts
cat /etc/hosts
```

#### Serial Console Azure (alternativa a Bastion)
Se Bastion non funziona:
1. Portale Azure → **Virtual machines** → **uyuni-server-test**
2. Menù → **Help** → **Serial Console**
3. Login con `azureuser` e password
4. Verifica logs: `journalctl -xe`

---

## Comandi Utili - Quick Reference

### Gestione Container
```bash
mgradm status              # Stato generale UYUNI
mgradm restart             # Riavvia tutti i container
mgradm stop                # Ferma tutti i container
mgradm start               # Avvia tutti i container
podman ps                  # Lista container attivi
podman ps -a               # Lista tutti i container
```

### Accesso Container
```bash
mgrctl term                # Shell nel container server
mgrctl exec -- <comando>   # Esegue comando nel container
podman exec -it uyuni-db bash  # Shell nel container db
```

### Logs
```bash
podman logs uyuni-server           # Log server
podman logs uyuni-db               # Log database
podman logs -f uyuni-server        # Log in tempo reale
journalctl -u uyuni-server -f      # Log systemd
```

### Storage
```bash
df -h /manager_storage /pgsql_storage  # Spazio dischi
lvs                                     # Volumi logici
vgs                                     # Volume groups
podman system df                        # Uso storage container
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
