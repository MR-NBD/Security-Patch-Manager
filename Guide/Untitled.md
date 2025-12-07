# Guida Completa: Foreman 3.15 + Katello 4.17 con Ubuntu 24.04

## Panoramica

Questa guida descrive l'installazione di **Foreman 3.15** con **Katello 4.17** e **Puppet 8** su **RHEL 9.x**. L'obiettivo finale è gestire il patch management di VM Ubuntu tramite Remote Execution (SSH), con **controllo totale degli aggiornamenti da Foreman**.

### Principi Chiave di questa Guida

|Principio|Descrizione|
|---|---|
|**Controllo centralizzato**|Tutti i comandi vengono eseguiti da Foreman via Remote Execution|
|**Nessun aggiornamento automatico**|La VM Ubuntu non si aggiorna mai autonomamente|
|**Minime operazioni sulla VM**|Solo configurazione iniziale, poi tutto da Foreman|

### Limitazioni Note - Ubuntu in Katello

> **IMPORTANTE**: Ubuntu/Debian in Katello ha limitazioni rispetto a RHEL/CentOS:

|Funzionalità|Ubuntu|RHEL/CentOS|
|---|---|---|
|**Errata** (Security, Bugfix, Enhancement)|❌ **Non disponibile**|✅ Sì|
|Lista pacchetti installati|✅ Sì|✅ Sì|
|Pacchetti aggiornabili|✅ Sì|✅ Sì|
|Remote Execution|✅ Sì|✅ Sì|
|Content View / Lifecycle|✅ Sì|✅ Sì|

Per gli aggiornamenti di sicurezza Ubuntu, useremo **Job Templates personalizzati** che eseguono `apt` commands.

---

### Requisiti Hardware Minimi

|Componente|Minimo|Raccomandato|
|---|---|---|
|CPU|4 core|8 core|
|RAM|20 GB|32 GB|
|Disco OS|50 GB|100 GB|
|Disco Pulp (`/var/lib/pulp`)|100 GB|300+ GB|
|Disco PostgreSQL (`/var/lib/pgsql`)|20 GB|50 GB|

### Architettura Target

```
┌─────────────────────────────────────────────────────────────────┐
│              FOREMAN + KATELLO SERVER (RHEL 9.6)                │
│                   foreman-katello-test.localdomain              │
│                          10.172.2.15                            │
├─────────────────────────────────────────────────────────────────┤
│  Componenti:           │  Plugin Attivi:                        │
│  - Foreman 3.15        │  - Remote Execution (SSH)              │
│  - Katello 4.17        │  - Ansible                             │
│  - Puppet 8            │  - Templates                           │
│  - Pulp                │                                        │
│  - PostgreSQL          │                                        │
│  - Candlepin           │                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ SSH (Remote Execution)
                              │ HTTPS (Content)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VM UBUNTU 24.04 LTS                          │
│                       test-lorenzo-1                            │
│                         10.172.2.5                              │
├─────────────────────────────────────────────────────────────────┤
│  - Aggiornamenti automatici DISABILITATI                        │
│  - subscription-manager (da ATIX)                               │
│  - Registrata come Content Host                                 │
│  - Gestita SOLO via Remote Execution                            │
└─────────────────────────────────────────────────────────────────┘
```

### Ambiente di Riferimento

|Componente|Nome|Valore|
|---|---|---|
|Server Foreman|hostname|foreman-katello-test.localdomain|
|Server Foreman|IP|10.172.2.15|
|Organization|Name|PSN-ASL06|
|Organization|**Label**|**myorg** ← usato per subscription-manager|
|Location|Name|Italy-North|
|VM Ubuntu|hostname|test-lorenzo-1|
|VM Ubuntu|IP|10.172.2.5|
|Content View|Name|CV-Ubuntu-2404|
|Activation Key|Name|ak-ubuntu-2404-prod|

> **CRITICO**: Per la registrazione con `subscription-manager`, si usa il **Label** dell'organizzazione (`myorg`), NON il Name (`PSN-ASL06`).

---

# PARTE 1: INSTALLAZIONE SERVER FOREMAN/KATELLO (RHEL 9.6)

---

## FASE 1: Verifica la Preparazione del Sistema

### 1.1 Verifica versione OS e SELinux

```bash
cat /etc/os-release
```

```bash
rpm -q selinux-policy
```

> **IMPORTANTE**: Foreman/Katello 4.17 richiede almeno `selinux-policy >= 38.1.45-3.el9_5`.

### 1.2 Registrazione RHEL e Aggiornamento Sistema

```bash
sudo su -
subscription-manager register
subscription-manager repos --enable=rhel-9-for-x86_64-baseos-rpms
subscription-manager repos --enable=rhel-9-for-x86_64-appstream-rpms
dnf upgrade --releasever=9.6 -y
reboot
```

### 1.3 Verifica Post-Aggiornamento

```bash
rpm -q selinux-policy
```

Output atteso: `selinux-policy-38.1.53-5.el9_6` o superiore.

---

## FASE 2: Configurazione NTP con Chrony

```bash
sudo su -
dnf install -y chrony
systemctl enable --now chronyd
chronyc sources
timedatectl set-ntp true
timedatectl status
```

---

## FASE 3: Configurazione Hostname e Networking

### 3.1 Configura hostname

```bash
hostnamectl set-hostname foreman-katello-test.localdomain
hostname -f
```

### 3.2 Configura /etc/hosts

```bash
cp /etc/hosts /etc/hosts.bak
echo "10.172.2.15    foreman-katello-test.localdomain    foreman-katello-test" >> /etc/hosts
ping -c 2 $(hostname -f)
```

---

## FASE 4: Configurazione Firewall

```bash
firewall-cmd --add-port={53,80,443,5646,5647,8000,8140,9090}/tcp --permanent
firewall-cmd --add-port={53,67,68,69}/udp --permanent
firewall-cmd --add-service={http,https,dns,dhcp,tftp,puppetmaster} --permanent
firewall-cmd --reload
firewall-cmd --list-all
```

---

## FASE 5: Configurazione Storage LVM per Pulp

```bash
# Identifica disco (es. /dev/sda)
lsblk

# Crea struttura LVM
parted /dev/sda --script mklabel gpt
parted /dev/sda --script mkpart primary 0% 100%
pvcreate /dev/sda1
vgcreate vg_pulp /dev/sda1
lvcreate -l 100%FREE -n lv_pulp vg_pulp

# Formatta e monta
mkfs.xfs /dev/mapper/vg_pulp-lv_pulp
mkdir -p /var/lib/pulp
mount /dev/mapper/vg_pulp-lv_pulp /var/lib/pulp
echo "/dev/mapper/vg_pulp-lv_pulp /var/lib/pulp xfs defaults 0 0" >> /etc/fstab

# SELinux
restorecon -Rv /var/lib/pulp/
systemctl daemon-reload
```

## FASE 5-bis: Configurazione Storage LVM per PostgreSQL

```bash
parted /dev/sdb --script mklabel gpt
parted /dev/sdb --script mkpart primary 0% 100%
pvcreate /dev/sdb1
vgcreate vg_pgsql /dev/sdb1
lvcreate -l 100%FREE -n lv_pgsql vg_pgsql
mkfs.xfs /dev/mapper/vg_pgsql-lv_pgsql
mkdir -p /var/lib/pgsql
mount /dev/mapper/vg_pgsql-lv_pgsql /var/lib/pgsql
echo "/dev/mapper/vg_pgsql-lv_pgsql /var/lib/pgsql xfs defaults 0 0" >> /etc/fstab
restorecon -Rv /var/lib/pgsql/
systemctl daemon-reload
```

---

## FASE 6: Installazione Repository

```bash
# CodeReady Builder
subscription-manager repos --enable codeready-builder-for-rhel-9-$(arch)-rpms

# EPEL
dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
dnf config-manager --set-enabled epel

# Pulisci cache
dnf clean all
dnf makecache

# Repository Foreman 3.15
dnf install -y https://yum.theforeman.org/releases/3.15/el9/x86_64/foreman-release.rpm

# Repository Katello 4.17
dnf install -y https://yum.theforeman.org/katello/4.17/katello/el9/x86_64/katello-repos-latest.rpm

# Repository Puppet 8
dnf install -y https://yum.puppet.com/puppet8-release-el-9.noarch.rpm

# Verifica
dnf repolist enabled
```

---

## FASE 7: Installazione Foreman-Katello

```bash
dnf upgrade -y
dnf install -y foreman-installer-katello

foreman-installer --scenario katello \
  --foreman-initial-admin-username admin \
  --foreman-initial-admin-password 'Temporanea1234' \
  --enable-foreman-plugin-remote-execution \
  --enable-foreman-proxy-plugin-remote-execution-script \
  --enable-foreman-plugin-ansible \
  --enable-foreman-proxy-plugin-ansible \
  --enable-foreman-plugin-templates \
  --enable-foreman-cli-katello \
  --foreman-proxy-registration true \
  --foreman-proxy-templates true
```

> **NOTA**: L'installazione richiede 15-30 minuti.

---

## FASE 8: Verifica dell'Installazione

```bash
foreman-maintain service status
```

Accedi a: `https://foreman-katello-test.localdomain`

- Username: `admin`
- Password: `Temporanea1234`

---

## FASE 9: Configurazione Post-Installazione

### 9.1 Crea Organization e Location

> **CRITICO**: Il **Label** dell'organizzazione (`myorg`) è quello che userai con `subscription-manager`, non il Name!

```bash
# Crea Organization - NOTA IL LABEL!
hammer organization create --name "PSN-ASL06" --label "myorg"

# Crea Location
hammer location create --name "Italy-North"

# Associa
hammer organization add-location --name "PSN-ASL06" --location "Italy-North"
```

### 9.2 Verifica Label Organization

```bash
hammer organization list
```

Output:

```
---|----------------------|----------------------|-------------|---------------------
ID | TITLE                | NAME                 | DESCRIPTION | LABEL               
---|----------------------|----------------------|-------------|---------------------
3  | PSN-ASL06            | PSN-ASL06            |             | myorg               
```

> Il **Label** `myorg` è quello da usare per la registrazione!

### 9.3 Associa Smart Proxy

```bash
hammer organization add-smart-proxy \
  --name "PSN-ASL06" \
  --smart-proxy "foreman-katello-test.localdomain"

hammer location add-smart-proxy \
  --name "Italy-North" \
  --smart-proxy "foreman-katello-test.localdomain"
```

### 9.4 Verifica chiave SSH per Remote Execution

```bash
cat /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy.pub
```

> Salva questa chiave, servirà per la VM Ubuntu.

---

## FASE 10: Configurazione Content Credentials (Chiavi GPG)

```bash
mkdir -p /etc/pki/rpm-gpg/import

curl -o /etc/pki/rpm-gpg/import/ubuntu-archive-keyring.gpg \
  "http://archive.ubuntu.com/ubuntu/project/ubuntu-archive-keyring.gpg"

gpg --no-default-keyring \
  --keyring /etc/pki/rpm-gpg/import/ubuntu-archive-keyring.gpg \
  --export --armor > /etc/pki/rpm-gpg/import/ubuntu-keys-ascii.asc

hammer content-credentials create \
  --organization "PSN-ASL06" \
  --name "Ubuntu Archive Key" \
  --content-type "gpg_key" \
  --path "/etc/pki/rpm-gpg/import/ubuntu-keys-ascii.asc"
```

---

## FASE 11: Creazione Product e Repository Ubuntu 24.04

```bash
# Product
hammer product create \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --label "ubuntu_2404_lts" \
  --description "Repository Ubuntu 24.04 Noble Numbat per patch management"

# Repository Security
hammer repository create \
  --organization "PSN-ASL06" \
  --product "Ubuntu 24.04 LTS" \
  --name "Ubuntu 24.04 Security" \
  --label "ubuntu_2404_security" \
  --content-type "deb" \
  --url "http://security.ubuntu.com/ubuntu" \
  --deb-releases "noble-security" \
  --deb-components "main,universe,restricted,multiverse" \
  --deb-architectures "amd64" \
  --download-policy "on_demand" \
  --gpg-key "Ubuntu Archive Key"

# Repository Updates
hammer repository create \
  --organization "PSN-ASL06" \
  --product "Ubuntu 24.04 LTS" \
  --name "Ubuntu 24.04 Updates" \
  --label "ubuntu_2404_updates" \
  --content-type "deb" \
  --url "http://archive.ubuntu.com/ubuntu" \
  --deb-releases "noble-updates" \
  --deb-components "main,universe,restricted,multiverse" \
  --deb-architectures "amd64" \
  --download-policy "on_demand" \
  --gpg-key "Ubuntu Archive Key"

# Repository Base
hammer repository create \
  --organization "PSN-ASL06" \
  --product "Ubuntu 24.04 LTS" \
  --name "Ubuntu 24.04 Base" \
  --label "ubuntu_2404_base" \
  --content-type "deb" \
  --url "http://archive.ubuntu.com/ubuntu" \
  --deb-releases "noble" \
  --deb-components "main,universe,restricted,multiverse" \
  --deb-architectures "amd64" \
  --download-policy "on_demand" \
  --gpg-key "Ubuntu Archive Key"
```

---

## FASE 12: Sincronizzazione Repository

```bash
hammer product synchronize \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --async

# Monitora
hammer task list --search "state=running"
```

---

## FASE 13: Lifecycle Environments

```bash
hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Development" \
  --label "development" \
  --prior "Library" \
  --description "Ambiente di sviluppo e test"

hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Test" \
  --label "test" \
  --prior "Development" \
  --description "Ambiente di test pre-produzione"

hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Production" \
  --label "production" \
  --prior "Test" \
  --description "Ambiente di produzione"

# Verifica
hammer lifecycle-environment paths --organization "PSN-ASL06"
```

---

## FASE 14: Content View

```bash
# Crea Content View
hammer content-view create \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --label "cv_ubuntu_2404" \
  --description "Content View per Ubuntu 24.04 LTS"

# Aggiungi Repository
hammer content-view add-repository \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --product "Ubuntu 24.04 LTS" \
  --repository "Ubuntu 24.04 Security"

hammer content-view add-repository \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --product "Ubuntu 24.04 LTS" \
  --repository "Ubuntu 24.04 Updates"

hammer content-view add-repository \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --product "Ubuntu 24.04 LTS" \
  --repository "Ubuntu 24.04 Base"

# Pubblica
hammer content-view publish \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --description "Initial publish"

# Promuovi a tutti gli ambienti
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Development"

hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Test"

hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Production"
```

---

## FASE 15: Operating System

```bash
hammer os create \
  --name "Ubuntu" \
  --major "24" \
  --minor "04" \
  --family "Debian" \
  --release-name "noble" \
  --description "Ubuntu 24.04 LTS Noble Numbat"

hammer os add-architecture \
  --title "Ubuntu 24.04" \
  --architecture "x86_64"
```

---

## FASE 16: Host Group

```bash
hammer hostgroup create \
  --organization "PSN-ASL06" \
  --location "Italy-North" \
  --name "Ubuntu-2404-Servers" \
  --description "Server Ubuntu 24.04 LTS" \
  --lifecycle-environment "Production" \
  --content-view "CV-Ubuntu-2404" \
  --content-source "foreman-katello-test.localdomain" \
  --operatingsystem "Ubuntu 24.04"

# Parametri SSH
hammer hostgroup set-parameter \
  --hostgroup "Ubuntu-2404-Servers" \
  --name "remote_execution_ssh_user" \
  --parameter-type "string" \
  --value "root"

hammer hostgroup set-parameter \
  --hostgroup "Ubuntu-2404-Servers" \
  --name "remote_execution_connect_by_ip" \
  --parameter-type "boolean" \
  --value "true"
```

---

## FASE 17: Activation Key

```bash
hammer activation-key create \
  --organization "PSN-ASL06" \
  --name "ak-ubuntu-2404-prod" \
  --description "Activation Key per Ubuntu 24.04 Production" \
  --lifecycle-environment "Production" \
  --content-view "CV-Ubuntu-2404" \
  --unlimited-hosts
```

---

# PARTE 2: PREPARAZIONE VM UBUNTU (10.172.2.5)

> **OBIETTIVO**: Configurare la VM con il **minimo** necessario, poi gestire tutto da Foreman.

---

## FASE 18: Preparazione Iniziale VM Ubuntu

### 18.1 Connessione alla VM

```bash
# Dal tuo PC o dal server Foreman
ssh azureuser@10.172.2.5
sudo su -
```

### 18.2 Aggiungi Foreman in /etc/hosts

```bash
echo "10.172.2.15 foreman-katello-test.localdomain foreman-katello-test" >> /etc/hosts
ping -c 2 foreman-katello-test.localdomain
```

### 18.3 ==DISABILITA AGGIORNAMENTI AUTOMATICI==

> **CRITICO**: Questa è la configurazione più importante per avere controllo totale da Foreman.

```bash
# Ferma e disabilita apt-daily
systemctl stop apt-daily.timer
systemctl disable apt-daily.timer
systemctl stop apt-daily-upgrade.timer
systemctl disable apt-daily-upgrade.timer
systemctl stop apt-daily.service
systemctl disable apt-daily.service
systemctl stop apt-daily-upgrade.service
systemctl disable apt-daily-upgrade.service

# Disabilita unattended-upgrades
systemctl stop unattended-upgrades
systemctl disable unattended-upgrades

# Rimuovi unattended-upgrades (opzionale)
apt remove -y unattended-upgrades

# Verifica che siano disabilitati
systemctl status apt-daily.timer
systemctl status apt-daily-upgrade.timer
systemctl status unattended-upgrades
```

### 18.4 Configura APT per non aggiornare automaticamente

```bash
cat > /etc/apt/apt.conf.d/99-foreman-managed << 'EOF'
// Gestito da Foreman - Non aggiornare automaticamente
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Download-Upgradeable-Packages "0";
APT::Periodic::AutocleanInterval "0";
APT::Periodic::Unattended-Upgrade "0";
EOF
```

### 18.5 Configura SSH per Remote Execution

```bash
# Crea directory SSH per root
mkdir -p /root/.ssh
chmod 700 /root/.ssh
```

### 18.6 Copia chiave SSH di Foreman

Dal **Server Foreman** (10.172.2.15), esegui:

```bash
# Metodo semplice - copia la chiave
cat /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy.pub | \
  ssh azureuser@10.172.2.5 "sudo tee /root/.ssh/authorized_keys && \
  sudo chmod 600 /root/.ssh/authorized_keys && \
  sudo chown root:root /root/.ssh/authorized_keys"
```

### 18.7 Test Connessione SSH da Foreman

```bash
# Sul server Foreman
ssh -i /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy root@10.172.2.5 "hostname && uptime"
```

Se vedi hostname e uptime, la connessione funziona! ✅

---

## FASE 19: Installazione subscription-manager su Ubuntu

> **IMPORTANTE**: Usare il repository `oss.atix.de` (NON apt.atix.de che è obsoleto!)

### 19.1 Installa dipendenze

```bash
apt update
apt install -y curl ca-certificates gnupg
```

### 19.2 Aggiungi chiave GPG ATIX

```bash
curl --silent --show-error --output /etc/apt/trusted.gpg.d/atix.asc \
  https://oss.atix.de/atix_gpg.pub
```

### 19.3 Aggiungi repository ATIX per Ubuntu 24.04

```bash
# Formato DEB822 (Ubuntu 24.04+)
cat > /etc/apt/sources.list.d/atix-client.sources << 'EOF'
Types: deb
URIs: https://oss.atix.de/Ubuntu24LTS/
Suites: stable
Components: main
Signed-By: /etc/apt/trusted.gpg.d/atix.asc
EOF
```

### 19.4 Installa subscription-manager

```bash
apt update
apt install -y subscription-manager
```

### 19.5 Installa katello-host-tools (opzionale ma raccomandato)

```bash
apt install -y katello-host-tools
```

### 19.6 Verifica installazione

```bash
subscription-manager version
```

---

## FASE 20: Configurazione subscription-manager

### 20.1 Scarica certificato CA di Katello

```bash
mkdir -p /etc/rhsm/ca

curl -o /etc/rhsm/ca/katello-server-ca.pem \
  https://foreman-katello-test.localdomain/pub/katello-server-ca.crt \
  --insecure
```

### 20.2 Configura subscription-manager

```bash
subscription-manager config \
  --server.hostname=foreman-katello-test.localdomain \
  --server.port=443 \
  --server.prefix=/rhsm \
  --rhsm.repo_ca_cert=/etc/rhsm/ca/katello-server-ca.pem \
  --rhsm.baseurl=https://foreman-katello-test.localdomain/pulp/deb
```

### 20.3 Verifica configurazione

```bash
subscription-manager config
```

---

## FASE 21: Registrazione come Content Host

> **CRITICO**: Usare il **Label** dell'organizzazione (`myorg`), NON il Name (`PSN-ASL06`)!

### 21.1 Registra l'host

```bash
subscription-manager register \
  --org="myorg" \
  --activationkey="ak-ubuntu-2404-prod" \
  --name="test-lorenzo-1"
```

Output atteso:

```
The system has been registered with ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### 21.2 Verifica registrazione

```bash
subscription-manager identity
```

Output atteso:

```
system identity: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
name: test-lorenzo-1
org name: PSN-ASL06
org ID: myorg
```

### 21.3 Verifica repository disponibili

```bash
subscription-manager repos --list
```

### 21.4 Abilita i repository

```bash
subscription-manager repos --enable='*'
```

### 21.5 Aggiorna APT (da repository Katello)

```bash
apt update
```

---

## FASE 22: Assegnazione Organization/Location all'Host

L'host registrato potrebbe non avere Organization/Location assegnate. Verifica e correggi.

### 22.1 Sul Server Foreman - Verifica host

```bash
sudo hammer host list
```

Cerca `test-lorenzo-1` e nota l'**ID**.

### 22.2 Assegna Organization e Location via API

```bash
# Sostituisci <HOST_ID> con l'ID trovato
curl -k -u admin:Temporanea1234 \
  -X PUT \
  -H "Content-Type: application/json" \
  -d '{"host": {"organization_id": 3, "location_id": 4}}' \
  https://foreman-katello-test.localdomain/api/hosts/<HOST_ID>
```

> **NOTA**: Organization ID = 3 (PSN-ASL06), Location ID = 4 (Italy-North). Verifica con `hammer organization list` e `hammer location list`.

### 22.3 Assegna Host Group e IP

```bash
sudo hammer host update \
  --name "test-lorenzo-1" \
  --hostgroup "Ubuntu-2404-Servers" \
  --ip "10.172.2.5"
```

### 22.4 Verifica nella Web UI

1. Seleziona **PSN-ASL06** e **Italy-North** in alto a sinistra
2. Vai su **Hosts → All Hosts**
3. Dovresti vedere `test-lorenzo-1`
4. Vai su **Hosts → Content Hosts**
5. Dovresti vedere `test-lorenzo-1` con Content View assegnata

---

## FASE 23: Upload Profilo Pacchetti

### 23.1 Sulla VM Ubuntu - Forza upload profilo

```bash
subscription-manager refresh
katello-package-upload --force
```

### 23.2 Verifica nella Web UI

1. **Hosts → Content Hosts → test-lorenzo-1**
2. Tab **Packages** → dovrebbe mostrare i pacchetti installati

---

## FASE 24: Test Remote Execution

### 24.1 Via Web UI

1. Vai su **Hosts → All Hosts**
2. Seleziona ☑ `test-lorenzo-1`
3. Clicca **Select Action → Schedule Remote Job**
4. Compila:
    - **Job Category**: `Commands`
    - **Job Template**: `Run Command - Script Default`
    - **Command**: `hostname && uptime && df -h`
5. Clicca **Submit**

### 24.2 Via Hammer CLI

```bash
sudo hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=hostname && uptime" \
  --search-query "name = test-lorenzo-1"
```

### 24.3 Verifica output

```bash
sudo hammer job-invocation list
sudo hammer job-invocation output --id <JOB_ID> --host "test-lorenzo-1"
```

---

# PARTE 3: GESTIONE PATCH MANAGEMENT DA FOREMAN

> Da questo punto in poi, **tutte le operazioni** vengono eseguite da Foreman via Remote Execution. Non è più necessario accedere direttamente alla VM.

---

## FASE 25: Creazione Job Templates per Ubuntu

### 25.1 Template: Ubuntu - Check Updates

#### Via Web UI

1. Vai su **Hosts → Templates → Job Templates**
2. Clicca **Create Template**
3. Compila:
    - **Name**: `Ubuntu - Check Updates`
    - **Job Category**: `Packages`
    - **Provider Type**: `Script`

**Template content:**

```erb
<%#
name: Ubuntu - Check Updates
job_category: Packages
description_format: Check available updates on %{host}
provider_type: script
kind: job_template
%>

#!/bin/bash
echo "=== Aggiornamento cache APT ==="
apt update 2>/dev/null

echo ""
echo "=== RIEPILOGO AGGIORNAMENTI ==="
UPGRADABLE=$(apt list --upgradable 2>/dev/null | grep -v "Listing..." | wc -l)
echo "Totale pacchetti aggiornabili: $UPGRADABLE"

echo ""
echo "=== PACCHETTI AGGIORNABILI ==="
apt list --upgradable 2>/dev/null | grep -v "Listing..."

echo ""
echo "=== POTENZIALI SECURITY UPDATES ==="
apt list --upgradable 2>/dev/null | grep -i security || echo "Nessuno identificato esplicitamente"
```

4. Tab **Job**: **Effective User** = `root`
5. Tab **Locations**: seleziona ☑ `Italy-North`
6. Tab **Organizations**: seleziona ☑ `PSN-ASL06`
7. Clicca **Submit**

---

### 25.2 Template: Ubuntu - Apply All Updates

```erb
<%#
name: Ubuntu - Apply All Updates
job_category: Packages
description_format: Apply all updates on %{host}
provider_type: script
kind: job_template
%>

#!/bin/bash
set -e

echo "=== Aggiornamento cache APT ==="
apt update

echo ""
echo "=== Applicazione TUTTI gli aggiornamenti ==="
DEBIAN_FRONTEND=noninteractive apt upgrade -y

echo ""
echo "=== Pulizia pacchetti obsoleti ==="
apt autoremove -y

echo ""
echo "=== COMPLETATO ==="
echo "Verifica riavvio richiesto:"
if [ -f /var/run/reboot-required ]; then
    echo "*** RIAVVIO RICHIESTO ***"
    cat /var/run/reboot-required.pkgs 2>/dev/null || true
else
    echo "Nessun riavvio richiesto"
fi
```

---

### 25.3 Template: Ubuntu - Install Package

```erb
<%#
name: Ubuntu - Install Package
job_category: Packages
description_format: Install package %{package} on %{host}
provider_type: script
kind: job_template
%>

#!/bin/bash
set -e

PACKAGE="<%= input('package') %>"

if [ -z "$PACKAGE" ]; then
    echo "ERRORE: Nessun pacchetto specificato"
    exit 1
fi

echo "=== Installazione pacchetto: $PACKAGE ==="
apt update
DEBIAN_FRONTEND=noninteractive apt install -y $PACKAGE

echo ""
echo "=== Verifica installazione ==="
dpkg -l | grep -i $PACKAGE || echo "Pacchetto non trovato nella lista"
```

**Input da aggiungere:**

- Name: `package`
- Input Type: `User input`
- Required: ☑
- Description: `Nome del pacchetto da installare`

---

### 25.4 Template: Ubuntu - Remove Package

```erb
<%#
name: Ubuntu - Remove Package
job_category: Packages
description_format: Remove package %{package} from %{host}
provider_type: script
kind: job_template
%>

#!/bin/bash
set -e

PACKAGE="<%= input('package') %>"

if [ -z "$PACKAGE" ]; then
    echo "ERRORE: Nessun pacchetto specificato"
    exit 1
fi

echo "=== Rimozione pacchetto: $PACKAGE ==="
DEBIAN_FRONTEND=noninteractive apt remove -y $PACKAGE
apt autoremove -y

echo ""
echo "=== Completato ==="
```

---

### 25.5 Template: Ubuntu - Reboot Host

```erb
<%#
name: Ubuntu - Reboot Host
job_category: Power
description_format: Reboot %{host}
provider_type: script
kind: job_template
%>

#!/bin/bash
echo "=== Riavvio sistema in 10 secondi ==="
echo "Host: $(hostname)"
echo "Uptime prima del riavvio: $(uptime)"
sleep 10
reboot
```

---

## FASE 26: Workflow Operativo

### Diagramma Workflow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW PATCH MANAGEMENT UBUNTU                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   1. SYNC AUTOMATICO                                                     │
│      ├─ Katello sincronizza repository Ubuntu ogni notte                │
│      └─ Content View aggiornata                                          │
│                                                                          │
│   2. CHECK UPDATES (da Foreman)                                          │
│      └─ Job Template: "Ubuntu - Check Updates"                          │
│                                                                          │
│   3. REVIEW (Admin)                                                      │
│      └─ Analizza output e decide cosa aggiornare                        │
│                                                                          │
│   4. TEST (su VM Development)                                            │
│      └─ Job Template: "Ubuntu - Apply All Updates"                      │
│                                                                          │
│   5. APPLY (su VM Production)                                            │
│      └─ Job Template: "Ubuntu - Apply All Updates"                      │
│                                                                          │
│   6. REBOOT (se necessario)                                              │
│      └─ Job Template: "Ubuntu - Reboot Host"                            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### Operazioni Comuni da Foreman

|Operazione|Job Template|Comando Hammer|
|---|---|---|
|Verificare aggiornamenti|Ubuntu - Check Updates|`hammer job-invocation create --job-template "Ubuntu - Check Updates" --search-query "name = test-lorenzo-1"`|
|Applicare aggiornamenti|Ubuntu - Apply All Updates|`hammer job-invocation create --job-template "Ubuntu - Apply All Updates" --search-query "name = test-lorenzo-1"`|
|Installare pacchetto|Ubuntu - Install Package|`hammer job-invocation create --job-template "Ubuntu - Install Package" --inputs "package=nginx" --search-query "name = test-lorenzo-1"`|
|Riavviare host|Ubuntu - Reboot Host|`hammer job-invocation create --job-template "Ubuntu - Reboot Host" --search-query "name = test-lorenzo-1"`|

---

## FASE 27: Host Collections per Operazioni Bulk

### 27.1 Crea Host Collection

```bash
sudo hammer host-collection create \
  --organization "PSN-ASL06" \
  --name "Ubuntu-2404-Servers" \
  --description "Tutti i server Ubuntu 24.04" \
  --unlimited-hosts
```

### 27.2 Aggiungi Host

```bash
# Trova ID dell'host
sudo hammer host list --search "name = test-lorenzo-1"

# Aggiungi alla collection
sudo hammer host-collection add-host \
  --organization "PSN-ASL06" \
  --name "Ubuntu-2404-Servers" \
  --host "test-lorenzo-1"
```

### 27.3 Esegui Job su Collection

Via Web UI:

1. **Hosts → Host Collections → Ubuntu-2404-Servers**
2. **Select Action → Schedule Remote Job**
3. Seleziona il template desiderato

---

## Troubleshooting

### Problema: Host non appare in Content Hosts

**Soluzione**: Verifica Organization/Location

```bash
# Seleziona "Any Organization" / "Any Location" nella UI
# Se l'host appare, assegna org/location via API
curl -k -u admin:Temporanea1234 \
  -X PUT \
  -H "Content-Type: application/json" \
  -d '{"host": {"organization_id": 3, "location_id": 4}}' \
  https://foreman-katello-test.localdomain/api/hosts/<HOST_ID>
```

### Problema: Remote Execution fallisce

**Soluzione**: Verifica connessione SSH

```bash
# Dal server Foreman
ssh -i /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy root@10.172.2.5 "hostname"
```

### Problema: subscription-manager "Organization not found"

**Soluzione**: Usa il **Label** dell'organizzazione, non il Name!

```bash
# SBAGLIATO
subscription-manager register --org="PSN-ASL06" ...

# CORRETTO
subscription-manager register --org="myorg" ...
```

### Problema: Repository APT non funzionano

**Soluzione**: Verifica file generati

```bash
# Sulla VM Ubuntu
cat /etc/apt/sources.list.d/rhsm.sources
subscription-manager repos --list
```

---

## Manutenzione

### Sync Plan Automatico

```bash
sudo hammer sync-plan create \
  --organization "PSN-ASL06" \
  --name "Daily-Ubuntu-Sync" \
  --description "Sincronizzazione giornaliera repository Ubuntu" \
  --enabled true \
  --interval "daily" \
  --sync-date "2025-01-01 02:00:00"

sudo hammer product set-sync-plan \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --sync-plan "Daily-Ubuntu-Sync"
```

### Aggiornamento Content View

Dopo ogni sync, pubblica e promuovi:

```bash
sudo hammer content-view publish \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --description "Security updates $(date +%Y-%m-%d)"

sudo hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Development"

# Dopo test OK
sudo hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Production"
```

---

## Riferimenti

- [Documentazione ufficiale Foreman 3.15](https://docs.theforeman.org/3.15/)
- [Documentazione Katello](https://docs.theforeman.org/3.15/Quickstart/index-katello.html)
- [ATIX subscription-manager per Ubuntu](https://oss.atix.de/html/ubuntu.html)
- [Foreman Remote Execution](https://docs.theforeman.org/3.15/Managing_Hosts/index-katello.html)