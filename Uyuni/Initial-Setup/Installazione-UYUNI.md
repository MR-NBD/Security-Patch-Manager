## Per ambiente di Test

Installazione di **UYUNI 2025.10** su **openSUSE Leap 15.6** in ambiente **Azure** con deployment containerizzato tramite **Podman**. 

### Accesso alla VM
L'accesso alla VM avviene **esclusivamente tramite Azure Bastion** (nessun IP pubblico).

> UYUNI è un progetto open-source upstream di SUSE Manager. Dalla versione 2024.10, UYUNI utilizza esclusivamente il deployment containerizzato basato su Podman. La versione 2025.10 introduce un'architettura a **2 container separati** (uno per ilserver e uno per il database PostgreSQL).

>A partire da UYUNI 2025.10, l'OS ufficialmente validato è **openSUSE Tumbleweed**. Tuttavia, **openSUSE Leap 15.6 è pienamente supportato dal progetto** in quanto si basa su quello per costruite le immagini container UYUNI stesse.
### Requisiti Hardware

| Componente       | Test                | Production               |
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
- [FASE 10: Verifica dell'Installazione](#fase-10-verifica-dellinstallazione-test)
- [Troubleshooting](#troubleshooting)
---
## DEPLOYMENT
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

Quando si passerà, implementare:
- Politica password forte (12+ caratteri, complessità)
- Timeout sessione (900 secondi)
- Audit logging JSON
- Backup automatico con cron
- RBAC con ruoli separati (Admin, Channel Admin, System Admin, Viewer)

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

![[png2.png]]
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

![[png1.png]]

Verificare che `System clock synchronized: yes` sia presente.

---
## FASE 3: Configurazione Hostname e DNS
### 3.1 Prerequisiti DNS
UYUNI **RICHIEDE** un DNS funzionante con risoluzione diretta e inversa. Il comando `hostname -f` deve restituire l'FQDN completo.
### 3.2 Configurare l'Hostname
#### Impostare hostname
```bash
hostnamectl set-hostname uyuni-server-test.uyuni.internal
```

Sostituire `uyuni.internal` con il dominio interno Azure o aziendale.
#### Verificare hostname
```bash
hostname
```
```bash
hostname -f
```
### 3.3 Configura il File /etc/hosts
#### Recuperare l'IP privato della VM
```bash
ip addr show eth0 
```
#### Backup del file hosts originale
```bash
cp /etc/hosts /etc/hosts.bak
```
#### Editare il file hosts
```bash
vim /etc/hosts
```

Aggiungere la riga (sostituire con IP e dominio corretto):
```
10.172.2.5    uyuni-server-test.uyuni.internal    uyuni-server-test
```
### 3.4 Verificare la Configurazione DNS

#### Test risoluzione diretta
```bash
ping -c 2 $(hostname -f)
```
#### Verifica FQDN
```bash
hostname -f
```

---
## FASE 4: Configurazione Base Sicurezza (Test)

> **PER PRODUZIONE**: Questa sezione è semplificata per questa fase di test. Per produzione, implementare hardening completo (SSH keys, audit, fail2ban, etc.)
### 4.1 Verificare Stato Servizi Base
#### Verificare che firewalld sia attivo
```bash
systemctl status firewalld
```
#### Se non attivo, abilitalo
```bash
systemctl enable --now firewalld
```
### 4.2 Hardening per produzione (Futuro)
- **SSH Hardening**: Disabilitare password, usa solo chiavi SSH
- **Audit Daemon**: Logging avanzato per compliance
- **Fail2Ban**: Protezione brute-force
- **SELinux/AppArmor**: Controllo accessi mandatorio
---
## FASE 5: Configurazione Storage Dedicato
### 5.1 Identificare i Dischi Disponibili
In Azure, i dischi dati aggiunti durante la creazione della VM
```bash
lsblk
```
### 5.2 Scelta del Metodo di Configurazione Storage
UYUNI offre due metodi per configurare lo storage:

| Metodo | Pro | Contro | Consigliato per |
|--------|-----|--------|-----------------|
| **mgr-storage-server** | Semplice, automatico | No LVM, no resize dinamico | Test rapidi |
| **LVM Manuale** | Flessibile, resize, snapshot | Configurazione manuale | Production, Cloud |
Per ambienti cloud, LVM è preferibile perché permette di espandere i volumi senza downtime.
### 5.3 Configurazione LVM Manuale
#### Disco Repository (es. /dev/sdb)
##### Creare partizione
```bash
parted /dev/sdb --script mklabel gpt
```
```bash
parted /dev/sdb --script mkpart primary 0% 100%
```
##### Configura LVM
```bash
pvcreate /dev/sdb1
```
```bash
vgcreate vg_uyuni_repo /dev/sdb1
```
```bash
lvcreate -l 100%FREE -n lv_repo vg_uyuni_repo
```
##### Formatta XFS
```bash
mkfs.xfs /dev/mapper/vg_uyuni_repo-lv_repo
```
##### Crea mount point e monta
```bash
mkdir -p /manager_storage
```
```bash
mount /dev/mapper/vg_uyuni_repo-lv_repo /manager_storage
```
##### Aggiungi a fstab
```bash
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
L'opzione `nofail` in fstab è importante per evitare problemi di boot se un disco non è disponibile.
#### Reload systemd
```bash
systemctl daemon-reload
```
### 5.5 Collegamento Storage ai Volumi Podman
Bisogna collegare il mount point ai volumi Podman che UYUNI si aspetta.
##### Creare directory per i volumi Podman
```bash
mkdir -p /var/lib/containers/storage/volumes/var-spacewalk
```
```bash
mkdir -p /var/lib/containers/storage/volumes/var-pgsql
```
##### Creare symlink per il mount point LVM
```bash
ln -s /manager_storage /var/lib/containers/storage/volumes/var-spacewalk/_data
```
```bash
ln -s /pgsql_storage /var/lib/containers/storage/volumes/var-pgsql/_data
```
### 5.6 Verificare Configurazione Storage
##### Verificare mount points
```bash
df -hP /manager_storage /pgsql_storage
```
##### Verificare LVM
```bash
lvs
```
```bash
vgs
```
##### Verificare volumi Podman
```bash
ls -la /var/lib/containers/storage/volumes/
```
Output atteso:

![[png6.png]]

---
## FASE 6: Configurazione Firewall
### 6.1 Abilitare Firewalld
```bash
systemctl enable --now firewalld
```

```bash
systemctl status firewalld
```
### 6.2 Configurare Porte UYUNI
#### HTTP/HTTPS (Web UI e client)
```bash
firewall-cmd --permanent --add-port=80/tcp
```
```bash
firewall-cmd --permanent --add-port=443/tcp
```
#### Salt Master (comunicazione con i client)
```bash
firewall-cmd --permanent --add-port=4505/tcp
```
```bash
firewall-cmd --permanent --add-port=4506/tcp
```
#### PostgreSQL (per container db separato - UYUNI 2025.x)
```bash
firewall-cmd --permanent --add-port=5432/tcp
```
### 6.3 Applicare le Modifiche

```bash
firewall-cmd --reload
```
### 6.4 Verifica Configurazione

```bash
firewall-cmd --list-all
```
Output atteso:

![[png5.png]]

> **PER PRODUCTION**: Aggiungere rich rules per limitare l'accesso a subnet specifiche invece di accettare da qualsiasi IP.

---
## FASE 7: Installazione Repository UYUNI
### 7.1 Aggiungere Repository UYUNI Stable per openSUSE Leap 15.6
Il repository corretto per Leap 15.6 utilizza il path delle immagini container.
#### Verificare se il repository è già presente
```bash
zypper lr | grep uyuni
```
#### Se non presente, aggiungere il repository
```bash
zypper ar https://download.opensuse.org/repositories/systemsmanagement:/Uyuni:/Stable/images/repo/Uyuni-Server-POOL-$(arch)-Media1/ uyuni-server-stable
```
### 7.2 Refresh e Installazione dei Pacchetti
#### Accettare chiave GPG e refresh
```bash
zypper --gpg-auto-import-keys refresh
```
#### Installare tool di gestione UYUNI
```bash
zypper install -y mgradm mgrctl mgradm-bash-completion mgrctl-bash-completion
```

#### Se uyuni-storage-setup-server non è già installato eseguire:
```bash
zypper install -y uyuni-storage-setup-server
```
### 7.3 Verificarere Versione Podman
UYUNI richiede Podman >= 4.5.0
```bash
podman --version
```
Output atteso:

![[png4.png]]

### 7.4 Abilitare Podman Socket
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
- **Password CA key**: scegli una password sicura
- **Password amministratore**: password per login Web UI
- **Email**: email per notifiche sistema

### 8.2 Monitoraggio Deployment
In un altro terminale :
#### Monitorare tutti i container
```bash
sudo podman logs -f uyuni-server
```
#### Oppure per il database
```bash
sudo podman logs -f uyuni-db
```
### 8.3 Verificare Container Attivi
**UYUNI 2025.x**: L'architettura prevede **2 container separati**.
Al termine del deployment:

```bash
mgradm status
```

```bash
podman ps
```

Output atteso (UYUNI 2025.10):

![[png3.png]]

Devono essere presenti **entrambi i container** con status "healthy".
### 8.4 Per Produzione: Certificati Custom
Per production, invece del comando base, usa:

```bash
mgradm install podman $(hostname -f) \
  --ssl-ca-root /path/to/ca-root.pem \
  --ssl-server-cert /path/to/server.crt \
  --ssl-server-key /path/to/server.key
```

---
## FASE 9: Configurazione SSL/TLS (NON TESTATA)

Per l'ambiente di test, UYUNI genera automaticamente certificati self-signed durante l'installazione. Questa fase è necessaria solo per production.
### 9.1 Certificati per Test

Durante il deployment (FASE 8), UYUNI crea automaticamente:
- Certificato CA self-signed
- Certificato server self-signed

Questi sono **sufficienti per i test**.
### 9.2 Per Production (Futuro)

Quando passerai in production, dovrai:
- Generare CSR per la CA aziendale
- Ottenere certificato firmato
- Sostituire certificati con `podman secret create --replace`
- Abilitare HSTS
- Configurare certificati per il database

---
## FASE 10: Verificare dell'Installazione (Test)
### 11.1 Verifica Stato Container (UYUNI 2025.x)
#### Status generale
```bash
mgradm status
```
#### Verifica entrambi i container
```bash
podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Output atteso: tutti i container "Up" e "healthy"
### 11.2 Verificare Servizi Interni al Container
#### Verificare Tomcat (Web UI)
```bash
sudo mgrctl exec -- systemctl status tomcat.service --no-pager
```
#### Verificare Salt Master
```bash
sudo mgrctl exec -- systemctl status salt-master.service --no-pager
```
#### Verificrea Taskomatic
```bash
sudo mgrctl exec -- systemctl status taskomatic.service --no-pager
```
### 11.3 Accesso Web UI
#### Credenziali Web UI
- **Username**: `admin`
- **Password**: quella specificata durante l'installazione (FASE 8)

Il browser mostrerà un warning per il certificato self-signed. Clicca "Avanzate" → "Procedi comunque.

---
## Troubleshooting
### I container non si avvia

```bash
# Verificare logs di entrambi i container
podman logs uyuni-server
podman logs uyuni-db

# Verificare stato dettagliato
podman inspect uyuni-server --format '{{.State.Status}}'
podman inspect uyuni-db --format '{{.State.Status}}'

# Riavvia container
mgradm restart
```

### Il database non raggiungibile

```bash
# Verificare container db
podman ps | grep uyuni-db

# Test connessione PostgreSQL
podman exec -it uyuni-db psql -U spacewalk -c "SELECT 1;"

# Verificare logs database
podman logs uyuni-db --tail 50
```

### Problemi Certificati SSL

```bash
# Verificare certificato attivo
mgrctl exec -- openssl x509 -in /etc/pki/tls/certs/spacewalk.crt -text -noout

# Verificare validità
openssl s_client -connect localhost:443 </dev/null 2>/dev/null | openssl x509 -noout -dates
```

### Problemi DNS/Hostname

```bash
# Verificare FQDN all'interno del container
mgrctl exec -- hostname -f

# Deve corrispondere all'hostname host
hostname -f

# Verificare risoluzione dal container
mgrctl exec -- ping -c 1 $(hostname -f)
```

### Storage Pieno

```bash
# Verificare spazio
df -h /manager_storage /pgsql_storage

# Verificare volumi Podman
podman system df

# Pulizia cache repository (con cautela)
mgrctl exec -- spacewalk-repo-sync --clean-cache
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
