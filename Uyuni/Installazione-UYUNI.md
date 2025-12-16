# Guida Installazione UYUNI Server - Ambiente di Test

## Panoramica

Questa guida descrive l'installazione di **UYUNI 2025.10** su **openSUSE Leap 15.6** in ambiente **Microsoft Azure** con deployment containerizzato tramite **Podman**. 

> **🧪 AMBIENTE**: Questa guida è configurata per un **ambiente di TEST**. Le sezioni marcate con 🔒 indicano configurazioni aggiuntive da implementare per il passaggio in **PRODUCTION**.

### Obiettivi Ambiente di Test
- ✅ Installazione funzionante di UYUNI
- ✅ Validazione della connettività con i client
- ✅ Test delle funzionalità di patch management
- ✅ Familiarizzazione con l'interfaccia e i comandi

### Accesso alla VM
L'accesso alla VM avviene **esclusivamente tramite Azure Bastion** (nessun IP pubblico).

> **NOTA VERSIONE**: UYUNI è il progetto open-source upstream di SUSE Manager. Dalla versione 2024.x, UYUNI utilizza esclusivamente il deployment containerizzato basato su Podman.

### Requisiti Hardware

| Componente | Test (Attuale) | 🔒 Production |
| --- | --- | --- |
| CPU | 8 core | 8+ core |
| RAM | 32 GB | 32+ GB |
| Disco OS | Default (~30 GB) | 100 GB SSD |
| Disco Repository | 500 GB Standard SSD | 500+ GB Premium SSD |
| Disco PostgreSQL | 100 GB Standard SSD | 100+ GB Premium SSD NVMe |

> **🔒 PER PRODUCTION**: Usare Premium SSD per migliori performance I/O.

### Architettura Target

#### UYUNI SERVER - (openSUSE Tumbleweed)

##### Componenti Container:
- UYUNI Server 2025.10 (Podman Container)
- PostgreSQL 16
- Salt Master
- Taskomatic
- Tomcat (Web UI)
- Apache HTTPD (Reverse Proxy)
- Cobbler (Provisioning)

##### Funzionalità:
- Salt-based Configuration Management
- Patch Management multi-OS
- CVE Audit (OVAL-based)
- Content Lifecycle Management
- Role-Based Access Control (RBAC)

```
sda                     
 └─/var/lib/containers/storage/volumes  (Repository + Data)
sdb 
 └─/manager_storage  (Repository dedicato)
sdc                     
 └─/pgsql_storage    (PostgreSQL dedicato)
nvme0n1                     
 └─root
    ├─/tmp
    ├─/usr
    ├─/home
    ├─/var
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
- [🔒 FASE 9: SSL/TLS (Solo Production)](#-fase-9-configurazione-ssltls-solo-production)
- [🔒 FASE 10: Hardening Post-Installazione (Solo Production)](#-fase-10-hardening-post-installazione-solo-production)
- [FASE 11: Verifica dell'Installazione](#fase-11-verifica-dellinstallazione-test)
- [Checklist Passaggio a Production](#-checklist-passaggio-a-production)
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
| **Data Disks** | 2 dischi (500GB + 100GB) |
| **VNet** | ASL0603-spoke10-spoke-italynorth |
| **Subnet** | default (10.172.2.0/27) |
| **Public IP** | None |
| **NSG** | uyuni-server-test-nsg |

### Accesso tramite Azure Bastion

L'accesso alla VM avviene **esclusivamente tramite Azure Bastion**:

1. Vai su **Portale Azure** → **Virtual machines** → **uyuni-server-test**
2. Clicca **Connect** → **Bastion**
3. Inserisci:
   - **Username**: `azureuser`
   - **Password**: la password impostata durante la creazione
4. Clicca **Connect**

Si aprirà una sessione SSH nel browser.

> **NOTA**: Azure Bastion fornisce accesso sicuro senza esporre porte SSH pubbliche.

### Configurazione NSG per Test

Per l'ambiente di test, configurare il NSG `uyuni-server-test-nsg` con queste regole minime:

| Priority | Nome | Port | Protocol | Source | Action |
|----------|------|------|----------|--------|--------|
| 100 | AllowHTTPS | 443 | TCP | VNet | Allow |
| 110 | AllowSalt | 4505-4506 | TCP | VNet | Allow |

> **NOTA**: SSH non serve nell'NSG perché Bastion usa un canale separato.

### 🔒 Configurazioni Aggiuntive per Production (Futuro)

Quando passerai in production, dovrai aggiungere:
- [ ] Premium SSD per i dischi dati
- [ ] Azure Backup abilitato
- [ ] NSG più restrittivo (IP specifici invece di VNet)
- [ ] Azure Private DNS Zone
- [ ] Certificati SSL firmati da CA aziendale
- [ ] Azure Monitor + Log Analytics

---

## FASE 1: Preparazione del Sistema Base

### 1.1 Accesso alla VM tramite Azure Bastion

1. **Portale Azure** → **Virtual machines** → **uyuni-server-test**
2. Clicca **Connect** → **Bastion**
3. Inserisci credenziali:
   - **Username**: `azureuser`
   - **Password**: la tua password
4. Clicca **Connect**

#### Diventa root
```bash
sudo su -
```

### 1.2 Verifica versione OS

```bash
cat /etc/os-release
```

Output atteso:
```
NAME="openSUSE Leap"
VERSION="15.6"
ID="opensuse-leap"
...
```

### 1.3 Aggiornamento Sistema

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

> **NOTA**: Dopo il reboot, riconnettiti tramite Bastion e torna root con `sudo su -`

### 1.4 Installazione Pacchetti Prerequisiti

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

> **🔒 PER PRODUCTION**: Aggiungere `audit`, `fail2ban`, `rsync`, `htop`, `iotop` per monitoring e sicurezza.

---

## FASE 2: Configurazione NTP con Chrony

La sincronizzazione temporale è **CRITICA** per il corretto funzionamento di UYUNI, Salt, e i certificati SSL.

### 2.1 Configurazione Chrony

#### Backup configurazione originale
```bash
cp /etc/chrony.conf /etc/chrony.conf.bak
```

#### Modifica configurazione per server NTP aziendali (opzionale)
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
```
               Local time: ...
           Universal time: ...
                 RTC time: ...
                Time zone: Europe/Rome (CET, +0100)
System clock synchronized: yes
              NTP service: active
          RTC in local TZ: no
```

> **IMPORTANTE**: Verificare che `System clock synchronized: yes` sia presente.

---

## FASE 3: Configurazione Hostname e DNS

### 3.1 Prerequisiti DNS

> **CRITICO**: UYUNI **RICHIEDE** un DNS funzionante con risoluzione diretta e inversa. Il comando `hostname -f` deve restituire l'FQDN completo.

### 3.2 Configura l'Hostname

#### Imposta hostname
```bash
hostnamectl set-hostname uyuni-server-test.yourcompany.local
```

> **NOTA**: Sostituisci `yourcompany.local` con il tuo dominio interno Azure o aziendale.

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
# Metodo 1: da metadata Azure
IP_PRIVATO=$(curl -s -H Metadata:true "http://169.254.169.254/metadata/instance/network/interface/0/ipv4/ipAddress/0/privateIpAddress?api-version=2021-02-01&format=text")
echo "IP Privato: $IP_PRIVATO"

# Metodo 2: da ip addr
ip addr show eth0 | grep "inet " | awk '{print $2}' | cut -d/ -f1
```

#### Backup del file hosts originale
```bash
cp /etc/hosts /etc/hosts.bak
```

#### Edita il file hosts
```bash
vim /etc/hosts
```

Aggiungi la seguente riga (sostituire con il tuo IP e dominio):
```
10.172.2.X    uyuni-server-test.yourcompany.local    uyuni-server-test
```

Il file dovrebbe apparire così:
```
127.0.0.1       localhost
::1             localhost
10.172.2.X      uyuni-server-test.yourcompany.local    uyuni-server-test
```

### 3.4 Configurazione DNS Azure (Opzionale ma Consigliato)

Per un ambiente production, configura una **Azure Private DNS Zone**:

1. **Portale Azure** → **Private DNS zones** → **Create**
2. Nome: `yourcompany.local`
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
uyuni-server-test.yourcompany.local
```

> **IMPORTANTE**: Se `hostname -f` non restituisce l'FQDN completo, UYUNI avrà problemi. Verifica `/etc/hosts` e riprova.

---

## FASE 4: Configurazione Base Sicurezza (Test)

> **🔒 PER PRODUCTION**: Questa sezione è semplificata per l'ambiente di test. Per production, implementare hardening completo (SSH keys, audit, fail2ban, etc.)

### 4.1 Verifica Stato Servizi Base

```bash
# Verifica che firewalld sia attivo
systemctl status firewalld

# Se non attivo, abilitalo
systemctl enable --now firewalld
```

### 4.2 🔒 Hardening Aggiuntivo per Production (Futuro)

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
sda      30G disk             <- OS temporaneo Azure
├─sda1   30G part /mnt
sdb     100G disk             <- OS principale
├─sdb1  500M part /boot/efi
├─sdb2    2G part [SWAP]
└─sdb3   97G part /
sdc     500G disk             <- Disco dati 1 (Repository)
sdd     100G disk             <- Disco dati 2 (PostgreSQL)
```

> **ATTENZIONE AZURE**: Il disco `/dev/sda` in Azure è tipicamente il disco temporaneo e **NON deve essere usato per dati persistenti**! Usa solo i dischi dati aggiuntivi (sdc, sdd, etc.)

#### Verifica dischi con Azure metadata
```bash
# Verifica che i dischi siano persistenti
curl -H Metadata:true "http://169.254.169.254/metadata/instance/compute/storageProfile?api-version=2021-02-01" | jq
```

### 5.2 Preparazione Storage con Script UYUNI

UYUNI fornisce uno script dedicato per la configurazione dello storage. Questo script:
- Configura i volumi persistenti necessari
- Monta i dischi nelle posizioni corrette
- Configura i permessi appropriati

#### Installa gli strumenti UYUNI (se non già installati)
```bash
# Repository per openSUSE Leap 15.6
zypper ar https://download.opensuse.org/repositories/systemsmanagement:/Uyuni:/Stable/openSUSE_Leap_15.6/ uyuni-stable
```
```bash
zypper --gpg-auto-import-keys refresh
```
```bash
zypper install -y mgradm mgrctl uyuni-storage-setup-server
```

#### Configura storage separato per repository e database

**Per Azure (tipicamente /dev/sdc e /dev/sdd):**
```bash
# Verifica prima i dischi corretti!
lsblk

# Configura storage (sostituisci con i tuoi device)
mgr-storage-server /dev/sdc /dev/sdd
```

Questo comando:
- Configura `/dev/sdc` per i volumi repository (montato su `/manager_storage`)
- Configura `/dev/sdd` per PostgreSQL (montato su `/pgsql_storage`)
- Utilizza filesystem XFS (raccomandato)
- Configura mount automatico in `/etc/fstab`

> **IMPORTANTE AZURE**: Non usare mai `/dev/sda` che è il disco temporaneo Azure!

### 5.3 Verifica Configurazione Storage

```bash
lsblk -f
```

```bash
df -hP /manager_storage /pgsql_storage
```

Output atteso:
```
Filesystem      Size  Used Avail Use% Mounted on
/dev/sdc1       500G   33M  500G   1% /manager_storage
/dev/sdd1       100G   33M  100G   1% /pgsql_storage
```

### 5.4 Alternativa: Configurazione LVM Manuale

Se si preferisce configurare manualmente LVM (ad esempio per snapshot):

> **NOTA**: Per VM Azure, LVM non è generalmente raccomandato. È preferibile usare dischi managed separati con Azure Backup. Se necessario, procedi come segue:

#### Disco Repository (es. /dev/sdc in Azure)
```bash
parted /dev/sdc --script mklabel gpt
parted /dev/sdc --script mkpart primary 0% 100%
pvcreate /dev/sdc1
vgcreate vg_uyuni_repo /dev/sdc1
lvcreate -l 100%FREE -n lv_repo vg_uyuni_repo
mkfs.xfs /dev/mapper/vg_uyuni_repo-lv_repo
mkdir -p /manager_storage
mount /dev/mapper/vg_uyuni_repo-lv_repo /manager_storage
echo "/dev/mapper/vg_uyuni_repo-lv_repo /manager_storage xfs defaults,nofail 0 0" >> /etc/fstab
```

#### Disco PostgreSQL (es. /dev/sdd in Azure)
```bash
parted /dev/sdd --script mklabel gpt
parted /dev/sdd --script mkpart primary 0% 100%
pvcreate /dev/sdd1
vgcreate vg_uyuni_pgsql /dev/sdd1
lvcreate -l 100%FREE -n lv_pgsql vg_uyuni_pgsql
mkfs.xfs /dev/mapper/vg_uyuni_pgsql-lv_pgsql
mkdir -p /pgsql_storage
mount /dev/mapper/vg_uyuni_pgsql-lv_pgsql /pgsql_storage
echo "/dev/mapper/vg_uyuni_pgsql-lv_pgsql /pgsql_storage xfs defaults,nofail 0 0" >> /etc/fstab
```

> **NOTA AZURE**: L'opzione `nofail` in fstab è importante per evitare problemi di boot se un disco non è disponibile.

#### Reload systemd
```bash
systemctl daemon-reload
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
  ports: 80/tcp 443/tcp 4505/tcp 4506/tcp
```

> **🔒 PER PRODUCTION**: Aggiungere rich rules per limitare l'accesso a subnet specifiche invece di accettare da qualsiasi IP.

---

## FASE 7: Installazione Repository UYUNI

### 7.1 Aggiungi Repository UYUNI Stable per openSUSE Leap 15.6

> **NOTA**: Se hai già aggiunto il repository nella FASE 5, salta al punto 7.2.

```bash
# Verifica se il repository è già presente
zypper lr | grep uyuni

# Se non presente, aggiungilo
zypper ar https://download.opensuse.org/repositories/systemsmanagement:/Uyuni:/Stable/openSUSE_Leap_15.6/ uyuni-stable
```

### 7.2 Refresh e Installa Pacchetti

```bash
# Accetta chiave GPG e refresh
zypper --gpg-auto-import-keys refresh
```

```bash
# Installa tool di gestione UYUNI
zypper install -y mgradm mgrctl mgradm-bash-completion
```

### 7.3 Verifica Versione Podman

> **IMPORTANTE**: UYUNI richiede Podman >= 4.5.0

```bash
podman --version
```

Output atteso:
```
podman version 4.x.x o superiore
```

### 7.4 Abilita Podman Socket

```bash
systemctl enable --now podman.socket
```

> **🔒 PER PRODUCTION**: Aggiungere configurazione limiti container in `/etc/containers/containers.conf.d/`

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

> **⏱️ TEMPO**: Il deployment richiede 15-30 minuti. Non interrompere il processo.

### 8.2 Monitoraggio Deployment

In un altro terminale (apri una nuova sessione Bastion), monitora il progresso:

```bash
sudo journalctl -f -u uyuni-server
```

Oppure:

```bash
sudo podman logs -f uyuni-server
```

### 8.3 Verifica Container Attivo

Al termine del deployment:

```bash
mgradm status
```

```bash
podman ps
```

Output atteso:
```
CONTAINER ID  IMAGE                                      STATUS         NAMES
abc123def456  registry.opensuse.org/uyuni/server:latest  Up 10 minutes  uyuni-server
```

### 🔒 8.4 Per Production: Certificati Custom

Per production, invece del comando base, usa:

```bash
mgradm install podman $(hostname -f) \
  --ssl-ca-root /path/to/ca-root.pem \
  --ssl-server-cert /path/to/server.crt \
  --ssl-server-key /path/to/server.key
```

---

## 🔒 FASE 9: Configurazione SSL/TLS (Solo Production)

> **NOTA TEST**: Per l'ambiente di test, UYUNI genera automaticamente certificati self-signed durante l'installazione. Questa fase è necessaria solo per production.

### 9.1 Certificati per Test

Durante il deployment (FASE 8), UYUNI crea automaticamente:
- Certificato CA self-signed
- Certificato server self-signed

Questi sono **sufficienti per i test**.

> **⚠️ BROWSER WARNING**: Il browser mostrerà un avviso di sicurezza per il certificato self-signed. È normale per l'ambiente di test.

### 🔒 9.2 Per Production (Futuro)

Quando passerai in production, dovrai:
- [ ] Generare CSR per la CA aziendale
- [ ] Ottenere certificato firmato
- [ ] Sostituire certificati con `podman secret create --replace`
- [ ] Abilitare HSTS
- [ ] Configurare certificati per il database

---

## 🔒 FASE 10: Hardening Post-Installazione (Solo Production)

> **NOTA TEST**: Questa fase è opzionale per l'ambiente di test. Implementa solo la verifica base (FASE 11).

### 🔒 Per Production (Futuro)

Quando passerai in production, implementa:
- [ ] Politica password forte (12+ caratteri, complessità)
- [ ] Timeout sessione (900 secondi)
- [ ] Audit logging JSON
- [ ] Backup automatico con cron
- [ ] RBAC con ruoli separati (Admin, Channel Admin, System Admin, Viewer)

---

## FASE 11: Verifica dell'Installazione (Test)

> **IMPORTANTE**: Questa è la fase principale per validare che l'installazione funzioni correttamente.

### 11.1 Verifica Stato Servizi Container

```bash
mgradm status
```

Output atteso: tutti i servizi "running"

### 11.2 Accesso Web UI

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
curl -k https://uyuni-server-test.yourcompany.local/rhn/manager/login
```

#### Credenziali Web UI
- **Username**: `admin`
- **Password**: quella specificata durante l'installazione (FASE 8)

> **⚠️ CERTIFICATO**: Il browser mostrerà un warning per il certificato self-signed. Clicca "Avanzate" → "Procedi comunque". È normale per l'ambiente di test.

### 11.3 Verifica Logs Container

```bash
# Log completo
podman logs uyuni-server

# Log in tempo reale (Ctrl+C per uscire)
podman logs -f uyuni-server
```

### 11.4 Accesso Shell Container

Per diagnostica avanzata:

```bash
mgrctl term
```

Questo apre una shell all'interno del container. Digita `exit` per uscire.

### 11.5 Verifica Porte in Ascolto

```bash
ss -tlnp | grep -E '(443|4505|4506|80)'
```

Output atteso:
```
LISTEN  0  128  *:443   *:*  users:(("httpd",...))
LISTEN  0  128  *:4505  *:*  users:(("salt-master",...))
LISTEN  0  128  *:4506  *:*  users:(("salt-master",...))
```

### 11.6 Test Connettività da Client (Futuro)

Quando registrerai i client, da essi verifica:

```bash
# Test HTTPS
curl -k https://uyuni-server-test.yourcompany.local/rhn/manager/login

# Test Salt ports
nc -zv uyuni-server-test.yourcompany.local 4505
nc -zv uyuni-server-test.yourcompany.local 4506
```

### 11.7 Checklist Test Completato

- [ ] `mgradm status` mostra tutti i servizi running
- [ ] `curl -k https://localhost/...` ritorna HTML
- [ ] Porte 443, 4505, 4506 in ascolto
- [ ] Nessun errore critico in `podman logs uyuni-server`

Se tutti i check passano, **l'installazione di test è completata con successo!**

---

## Ambiente di Test - Riepilogo

| Componente | Valore |
| --- | --- |
| **VM Name** | uyuni-server-test |
| **FQDN** | uyuni-server-test.yourcompany.local |
| **IP Server (Private)** | 10.172.2.x (dalla subnet) |
| **Accesso** | Azure Bastion (no IP pubblico) |
| **Cloud Provider** | Microsoft Azure |
| **Region** | Italy North |
| **Resource Group** | test_group |
| **VM Size** | Standard D8as v5 (8 vCPU, 32 GB RAM) |
| **OS Host** | openSUSE Leap 15.6 Gen2 |
| **Versione UYUNI** | 2025.10 |
| **Deployment Type** | Containerized (Podman) |
| **Certificati** | Self-signed (test) |
| **Storage Repository** | /manager_storage (500GB) |
| **Storage Database** | /pgsql_storage (100GB) |

---

## NEXT STEPS (Test)

Dopo aver completato l'installazione:

1. **Sincronizza un repository** (es. Ubuntu 24.04) dalla Web UI
2. **Registra un client di test** per validare la connettività Salt
3. **Testa l'applicazione di una patch** su un client
4. **Familiarizza con l'interfaccia** e le funzionalità

---

## 🔒 CHECKLIST: Passaggio a Production

Quando sarai pronto per production, implementa:

- [ ] **Infrastruttura**
  - [ ] Premium SSD per dischi dati
  - [ ] Azure Backup configurato
  - [ ] Availability Zone / Set per HA

- [ ] **Sicurezza**
  - [ ] Certificati SSL firmati da CA aziendale
  - [ ] SSH solo con chiavi (no password)
  - [ ] Audit daemon configurato
  - [ ] Fail2ban attivo
  - [ ] NSG con IP specifici (non VNet generico)

- [ ] **Monitoring**
  - [ ] Azure Monitor + Log Analytics
  - [ ] Prometheus/Grafana per metriche UYUNI

- [ ] **Backup & DR**
  - [ ] Script backup automatico
  - [ ] Test restore verificato
  - [ ] Documentazione DR

---

## Troubleshooting

### Container non si avvia

```bash
# Verifica logs
podman logs uyuni-server

# Verifica stato dettagliato
systemctl status uyuni-server.service

# Riavvia container
mgradm restart
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
```

### Storage Pieno

```bash
# Verifica spazio
df -h /manager_storage /pgsql_storage

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

## Riferimenti

- [Documentazione Ufficiale UYUNI](https://www.uyuni-project.org/uyuni-docs/)
- [Installation and Upgrade Guide](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/uyuni-installation-and-upgrade-overview.html)
- [Network Requirements](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/network-requirements.html)
- [SSL Certificates](https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/ssl-certs.html)
- [Client Configuration Guide](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/uyuni-client-config-overview.html)
- [GitHub UYUNI Project](https://github.com/uyuni-project/uyuni)

---

*Documento per installazione UYUNI in ambiente di TEST su Azure.*
*Per il passaggio in production, seguire la checklist nella sezione dedicata.*
*Ultima revisione: Dicembre 2025*
