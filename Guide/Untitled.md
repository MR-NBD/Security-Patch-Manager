# Guida Completa: Patch Management VM Ubuntu con Foreman-Katello

## Contesto

Questa guida continua dalla **FASE 9** dell'installazione Foreman-Katello e copre la configurazione completa per gestire il patch management di una VM Ubuntu.

### Ambiente

|Componente|Valore|
|---|---|
|Server Foreman|foreman-katello-test.localdomain|
|Organization|PSN-ASL06|
|Location|Italy-North|
|VM Ubuntu Target|10.172.2.5|
|OS Target|Ubuntu 24.04 LTS|

---

## FASE 9: Associazione Smart Proxy a Organization e Location

### 9.1 Problema: Smart Proxy non associato

Il problema che stai riscontrando è che lo Smart Proxy (il server Foreman stesso) non è associato all'Organization e Location create. Questo è necessario per il corretto funzionamento di Remote Execution e Content Management.

### 9.2 Verifica Smart Proxy esistente

```bash
# Lista gli Smart Proxy disponibili
hammer proxy list
```

Output atteso:

```
---|----------------------------------------|-------------------------------------------|----------|
ID | NAME                                   | URL                                       | FEATURES |
---|----------------------------------------|-------------------------------------------|----------|
1  | foreman-katello-test.localdomain       | https://foreman-katello-test.localdomain:9090 | Ansible, Dynflow, ...
---|----------------------------------------|-------------------------------------------|----------|
```

### 9.3 Associa Smart Proxy all'Organization

```bash
# Associa il proxy all'organizzazione PSN-ASL06
hammer organization add-smart-proxy \
  --name "PSN-ASL06" \
  --smart-proxy "foreman-katello-test.localdomain"
```

### 9.4 Associa Smart Proxy alla Location

```bash
# Associa il proxy alla location Italy-North
hammer location add-smart-proxy \
  --name "Italy-North" \
  --smart-proxy "foreman-katello-test.localdomain"
```

### 9.5 Verifica associazioni

```bash
# Verifica Organization
hammer organization info --name "PSN-ASL06" | grep -A5 "Smart Proxies"
```

```bash
# Verifica Location
hammer location info --name "Italy-North" | grep -A5 "Smart Proxies"
```

### 9.6 Verifica da Web UI

1. Vai su **Administer → Organizations → PSN-ASL06 → Smart Proxies**
2. Verifica che `foreman-katello-test.localdomain` sia presente
3. Ripeti per **Administer → Locations → Italy-North → Smart Proxies**

---

## FASE 10: Configurazione Content Credentials (Chiavi GPG)

Le chiavi GPG sono necessarie per verificare l'autenticità dei pacchetti Ubuntu.

### 10.1 Scarica le chiavi GPG di Ubuntu

```bash
# Crea directory se non esiste
mkdir -p /etc/pki/rpm-gpg/import
```

```bash
# Scarica Ubuntu Archive Keyring
curl -o /etc/pki/rpm-gpg/import/ubuntu-archive-keyring.gpg \
  "http://archive.ubuntu.com/ubuntu/project/ubuntu-archive-keyring.gpg"
```

```bash
# Scarica Ubuntu Archive Signing Key (2018)
curl -o /etc/pki/rpm-gpg/import/ubuntu-archive-key-2018.asc \
  "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C"
```

### 10.2 Estrai le chiavi in formato ASCII

```bash
# Converti il keyring in formato ASCII per l'import in Foreman
gpg --no-default-keyring \
  --keyring /etc/pki/rpm-gpg/import/ubuntu-archive-keyring.gpg \
  --export --armor > /etc/pki/rpm-gpg/import/ubuntu-keys-ascii.asc
```

### 10.3 Crea Content Credential in Foreman

**Via Web UI (raccomandato):**

1. Vai su **Content → Content Credentials**
2. Clicca **Create Content Credential**
3. Compila:
    - **Name**: `Ubuntu Archive Key`
    - **Content Credential Type**: `GPG Key`
    - **Content Credential Contents**: Copia il contenuto del file:

```bash
cat /etc/pki/rpm-gpg/import/ubuntu-keys-ascii.asc
```

4. Clicca **Save**

**Via CLI:**

```bash
hammer content-credentials create \
  --organization "PSN-ASL06" \
  --name "Ubuntu Archive Key" \
  --content-type "gpg_key" \
  --path "/etc/pki/rpm-gpg/import/ubuntu-keys-ascii.asc"
```

---

## FASE 11: Creazione Product e Repository Ubuntu 24.04

### 11.1 Crea il Product

```bash
hammer product create \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --label "ubuntu_2404_lts" \
  --description "Repository Ubuntu 24.04 Noble Numbat per patch management"
```

### 11.2 Crea i Repository

Ubuntu 24.04 usa i componenti: `main`, `universe`, `restricted`, `multiverse`

#### Repository Main (Security)

```bash
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
```

#### Repository Updates

```bash
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
```

#### Repository Base

```bash
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

### 11.3 Verifica i repository creati

```bash
hammer repository list --organization "PSN-ASL06" --product "Ubuntu 24.04 LTS"
```

---

## FASE 12: Sincronizzazione Repository

### 12.1 Sincronizza tutti i repository del Product

```bash
# Sync di tutto il product (tutti i repository insieme)
hammer product synchronize \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --async
```

### 12.2 Oppure sincronizza singolarmente

```bash
# Sync Security (priorità alta)
hammer repository synchronize \
  --organization "PSN-ASL06" \
  --product "Ubuntu 24.04 LTS" \
  --name "Ubuntu 24.04 Security" \
  --async
```

```bash
# Sync Updates
hammer repository synchronize \
  --organization "PSN-ASL06" \
  --product "Ubuntu 24.04 LTS" \
  --name "Ubuntu 24.04 Updates" \
  --async
```

```bash
# Sync Base
hammer repository synchronize \
  --organization "PSN-ASL06" \
  --product "Ubuntu 24.04 LTS" \
  --name "Ubuntu 24.04 Base" \
  --async
```

### 12.3 Monitora lo stato della sincronizzazione

```bash
# Lista task in esecuzione
hammer task list --search "state=running"
```

```bash
# Verifica progresso specifico
hammer task progress --id <TASK_ID>
```

**Via Web UI:**

- Vai su **Content → Sync Status** per vedere lo stato in tempo reale

### 12.4 Configura Sync Plan (Sincronizzazione automatica)

```bash
# Crea un sync plan giornaliero
hammer sync-plan create \
  --organization "PSN-ASL06" \
  --name "Daily-Ubuntu-Sync" \
  --description "Sincronizzazione giornaliera repository Ubuntu" \
  --enabled true \
  --interval "daily" \
  --sync-date "2024-01-01 02:00:00"
```

```bash
# Associa il product al sync plan
hammer product set-sync-plan \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --sync-plan "Daily-Ubuntu-Sync"
```

---

## FASE 13: Content View e Lifecycle Environment

### 13.1 Crea Lifecycle Environments

```bash
# Ambiente Development
hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Development" \
  --label "development" \
  --prior "Library" \
  --description "Ambiente di sviluppo e test"
```

```bash
# Ambiente Staging
hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Staging" \
  --label "staging" \
  --prior "Development" \
  --description "Ambiente di staging pre-produzione"
```

```bash
# Ambiente Production
hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Production" \
  --label "production" \
  --prior "Staging" \
  --description "Ambiente di produzione"
```

### 13.2 Verifica Lifecycle Path

```bash
hammer lifecycle-environment paths --organization "PSN-ASL06"
```

Output atteso:

```
Library >> Development >> Staging >> Production
```

### 13.3 Crea Content View

```bash
hammer content-view create \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --label "cv_ubuntu_2404" \
  --description "Content View per Ubuntu 24.04 LTS"
```

### 13.4 Aggiungi Repository alla Content View

```bash
# Aggiungi Security
hammer content-view add-repository \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --product "Ubuntu 24.04 LTS" \
  --repository "Ubuntu 24.04 Security"
```

```bash
# Aggiungi Updates
hammer content-view add-repository \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --product "Ubuntu 24.04 LTS" \
  --repository "Ubuntu 24.04 Updates"
```

```bash
# Aggiungi Base
hammer content-view add-repository \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --product "Ubuntu 24.04 LTS" \
  --repository "Ubuntu 24.04 Base"
```

### 13.5 Pubblica la Content View

```bash
hammer content-view publish \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --description "Initial publish"
```

### 13.6 Promuovi la Content View negli ambienti

```bash
# Promuovi a Development
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Development"
```

```bash
# Promuovi a Staging (quando pronto)
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Staging"
```

```bash
# Promuovi a Production (quando validato)
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Production"
```

### 13.7 Verifica Content View

```bash
hammer content-view info \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404"
```

---

## FASE 14: Creazione Operating System

### 14.1 Verifica se Ubuntu 24.04 esiste già

```bash
hammer os list | grep -i ubuntu
```

### 14.2 Crea Operating System (se non esiste)

```bash
hammer os create \
  --name "Ubuntu" \
  --major "24" \
  --minor "04" \
  --family "Debian" \
  --release-name "noble" \
  --description "Ubuntu 24.04 LTS Noble Numbat"
```

### 14.3 Associa l'OS all'Architecture

```bash
# Verifica architecture disponibili
hammer architecture list
```

```bash
# Associa x86_64
hammer os add-architecture \
  --title "Ubuntu 24.04" \
  --architecture "x86_64"
```

### 14.4 Verifica Operating System

```bash
hammer os info --title "Ubuntu 24.04"
```

---

## FASE 15: Creazione Host Group

Gli Host Group permettono di raggruppare gli host con configurazioni comuni.

### 15.1 Crea Host Group

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
```

### 15.2 Configura parametri per Remote Execution

```bash
# Imposta utente SSH per il gruppo
hammer hostgroup set-parameter \
  --hostgroup "Ubuntu-2404-Servers" \
  --name "remote_execution_ssh_user" \
  --parameter-type "string" \
  --value "root"
```

```bash
# Imposta connessione via IP (utile in assenza di DNS)
hammer hostgroup set-parameter \
  --hostgroup "Ubuntu-2404-Servers" \
  --name "remote_execution_connect_by_ip" \
  --parameter-type "boolean" \
  --value "true"
```

### 15.3 Verifica Host Group

```bash
hammer hostgroup info --name "Ubuntu-2404-Servers"
```

---

## FASE 16: Creazione Activation Key

### 16.1 Crea Activation Key

```bash
hammer activation-key create \
  --organization "PSN-ASL06" \
  --name "ak-ubuntu-2404-prod" \
  --description "Activation Key per Ubuntu 24.04 Production" \
  --lifecycle-environment "Production" \
  --content-view "CV-Ubuntu-2404" \
  --unlimited-hosts
```

### 16.2 Verifica Activation Key

```bash
hammer activation-key info \
  --organization "PSN-ASL06" \
  --name "ak-ubuntu-2404-prod"
```

---

## FASE 17: Preparazione VM Ubuntu per la Registrazione

### 17.1 Copia la chiave SSH di Foreman sulla VM Ubuntu

**Sul server Foreman**, visualizza la chiave pubblica:

```bash
cat /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy.pub
```

**Sulla VM Ubuntu (10.172.2.5)**, esegui:

```bash
# Connettiti alla VM Ubuntu
ssh <tuo_utente>@10.172.2.5
```

```bash
# Crea directory .ssh per root se non esiste
sudo mkdir -p /root/.ssh
sudo chmod 700 /root/.ssh
```

```bash
# Aggiungi la chiave pubblica di Foreman
sudo nano /root/.ssh/authorized_keys
```

Incolla la chiave pubblica e salva.

```bash
# Imposta permessi corretti
sudo chmod 600 /root/.ssh/authorized_keys
sudo chown root:root /root/.ssh/authorized_keys
```

### 17.2 Configura SSH sulla VM Ubuntu

```bash
# Assicurati che PermitRootLogin sia abilitato (per Remote Execution)
sudo nano /etc/ssh/sshd_config
```

Modifica/aggiungi:

```
PermitRootLogin prohibit-password
PubkeyAuthentication yes
```

```bash
# Riavvia SSH
sudo systemctl restart sshd
```

### 17.3 Verifica connessione SSH dal server Foreman

```bash
# Sul server Foreman, testa la connessione SSH
ssh -i /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy root@10.172.2.5 "hostname"
```

Se vedi l'hostname della VM Ubuntu, la connessione SSH funziona!

---

## FASE 18: Registrazione Host in Foreman

### 18.1 Metodo 1: Registrazione Manuale via UI

1. Vai su **Hosts → Create Host**
    
2. Compila il tab **Host**:
    
    - **Name**: `ubuntu-24-04-lts`
    - **Organization**: `PSN-ASL06`
    - **Location**: `Italy-North`
    - **Host Group**: `Ubuntu-2404-Servers`
3. Compila il tab **Operating System**:
    
    - **Operating System**: `Ubuntu 24.04`
    - **Architecture**: `x86_64`
4. Compila il tab **Interfaces**:
    
    - Clicca su **Edit** sull'interfaccia
    - **IPv4 Address**: `10.172.2.5`
    - **Primary**: ✅
    - **Managed**: ❌ (per host esistenti)
5. Clicca **Submit**
    

### 18.2 Metodo 2: Registrazione via CLI

```bash
hammer host create \
  --organization "PSN-ASL06" \
  --location "Italy-North" \
  --name "ubuntu-24-04-lts" \
  --hostgroup "Ubuntu-2404-Servers" \
  --operatingsystem "Ubuntu 24.04" \
  --architecture "x86_64" \
  --ip "10.172.2.5" \
  --build false \
  --managed false
```

### 18.3 Metodo 3: Global Registration (Raccomandato per host esistenti)

**Via Web UI:**

1. Vai su **Hosts → Register Host**
    
2. Seleziona:
    
    - **Host Group**: `Ubuntu-2404-Servers`
    - **Operating System**: `Ubuntu 24.04`
    - **Activation Keys**: `ak-ubuntu-2404-prod`
    - **Insecure**: ✅ (se usi certificati self-signed)
    - **Remote Execution Interface**: seleziona l'interfaccia con IP 10.172.2.5
3. Clicca **Generate** per ottenere il comando curl
    
4. **Sulla VM Ubuntu**, esegui il comando generato:
    

```bash
curl -sS --insecure 'https://foreman-katello-test.localdomain/register?...' | bash
```

### 18.4 Verifica registrazione host

```bash
hammer host info --name "ubuntu-24-04-lts"
```

---

## FASE 19: Configurazione Repository sulla VM Ubuntu

Dopo la registrazione, la VM deve essere configurata per usare i repository Katello.

### 19.1 Sulla VM Ubuntu - Installa Subscription Manager

```bash
# Installa subscription-manager per Ubuntu
sudo apt-get update
sudo apt-get install -y subscription-manager
```

### 19.2 Installa Katello CA Certificate

```bash
# Scarica e installa il certificato CA di Katello
curl --insecure --output /tmp/katello-ca-consumer-latest.noarch.deb \
  https://foreman-katello-test.localdomain/pub/katello-ca-consumer-latest.noarch.deb

sudo dpkg -i /tmp/katello-ca-consumer-latest.noarch.deb
```

### 19.3 Registra con Activation Key

```bash
sudo subscription-manager register \
  --org="PSN-ASL06" \
  --activationkey="ak-ubuntu-2404-prod" \
  --force
```

### 19.4 Installa Katello Host Tools

```bash
sudo apt-get update
sudo apt-get install -y katello-host-tools
```

---

## FASE 20: Verifica Remote Execution

### 20.1 Testa un comando remoto dalla UI

1. Vai su **Hosts → All Hosts**
2. Seleziona `ubuntu-24-04-lts`
3. Clicca **Schedule Remote Job**
4. Seleziona **Job Category**: `Commands`
5. Seleziona **Job Template**: `Run Command - Script Default`
6. In **Command**, inserisci: `hostname && uptime`
7. Clicca **Submit**

### 20.2 Testa via CLI

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=hostname && uptime" \
  --search-query "name = ubuntu-24-04-lts"
```

### 20.3 Verifica output

```bash
# Lista job recenti
hammer job-invocation list
```

```bash
# Visualizza output di un job specifico
hammer job-invocation output --id <JOB_ID> --host "ubuntu-24-04-lts"
```

---

## FASE 21: Patch Management - Visualizzazione Aggiornamenti

### 21.1 Verifica pacchetti installabili (Via UI)

1. Vai su **Hosts → Content Hosts**
2. Seleziona `ubuntu-24-04-lts`
3. Vai nel tab **Packages** per vedere i pacchetti installati
4. Vai nel tab **Errata** per vedere gli aggiornamenti di sicurezza disponibili

### 21.2 Lista pacchetti aggiornabili (Via CLI)

```bash
# Elenca pacchetti aggiornabili
hammer host package list \
  --host "ubuntu-24-04-lts" \
  --status "upgradable"
```

### 21.3 Lista Errata applicabili

```bash
hammer host errata list --host "ubuntu-24-04-lts"
```

---

## FASE 22: Esecuzione Patch - Aggiornamenti Manuali

### 22.1 Aggiorna un singolo pacchetto

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get install -y <nome_pacchetto>" \
  --search-query "name = ubuntu-24-04-lts"
```

### 22.2 Aggiorna tutti i pacchetti

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get upgrade -y" \
  --search-query "name = ubuntu-24-04-lts"
```

### 22.3 Aggiorna solo pacchetti di sicurezza

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get upgrade -y -o Dir::Etc::SourceList=/etc/apt/sources.list.d/security.sources.list" \
  --search-query "name = ubuntu-24-04-lts"
```

### 22.4 Esegui dist-upgrade

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get dist-upgrade -y" \
  --search-query "name = ubuntu-24-04-lts"
```

---

## FASE 23: Creazione Job Template Personalizzati

### 23.1 Job Template per Patch Ubuntu (Security Only)

**Via UI:**

1. Vai su **Hosts → Templates → Job Templates**
2. Clicca **Create Job Template**
3. Compila:
    - **Name**: `Ubuntu Security Patch`
    - **Job Category**: `Packages`
    - **Provider Type**: `Script`
4. Nel tab **Template**:

```bash
#!/bin/bash
# Ubuntu Security Patch Template

echo "=== Starting Security Patch on $(hostname) ==="
echo "Date: $(date)"

# Update package lists
apt-get update

# Install unattended-upgrades if not present
apt-get install -y unattended-upgrades

# Run only security updates
unattended-upgrade --dry-run -d 2>&1 | head -50

echo ""
read -p "Proceed with security updates? (auto-yes in 10s) " -t 10 response
response=${response:-yes}

if [[ "$response" =~ ^[Yy] ]]; then
    unattended-upgrade -v
    echo "=== Security Patch Completed ==="
else
    echo "=== Security Patch Cancelled ==="
fi

# Report status
echo ""
echo "=== Current Kernel: $(uname -r) ==="
echo "=== Reboot Required: $([ -f /var/run/reboot-required ] && echo 'YES' || echo 'NO') ==="
```

5. Nel tab **Job**, seleziona:
    - **Effective User**: `root`
6. Nel tab **Locations**, aggiungi: `Italy-North`
7. Nel tab **Organizations**, aggiungi: `PSN-ASL06`
8. Clicca **Submit**

### 23.2 Job Template per Full System Update

**Via CLI (crea file template):**

```bash
cat << 'EOF' > /tmp/ubuntu-full-update.erb
#!/bin/bash
# Full System Update Template for Ubuntu

echo "=== Starting Full System Update on $(hostname) ==="
echo "Date: $(date)"

# Update package lists
apt-get update

# Show upgradable packages
echo ""
echo "=== Packages to be upgraded ==="
apt list --upgradable 2>/dev/null

# Perform upgrade
echo ""
echo "=== Performing upgrade ==="
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# Perform dist-upgrade if requested
<% if input("dist_upgrade") == "true" %>
echo ""
echo "=== Performing dist-upgrade ==="
DEBIAN_FRONTEND=noninteractive apt-get dist-upgrade -y
<% end %>

# Autoremove unused packages
echo ""
echo "=== Removing unused packages ==="
apt-get autoremove -y

# Clean apt cache
apt-get clean

# Report status
echo ""
echo "=== Update Summary ==="
echo "Kernel: $(uname -r)"
echo "Reboot Required: $([ -f /var/run/reboot-required ] && echo 'YES' || echo 'NO')"

<% if input("auto_reboot") == "true" && File.exist?("/var/run/reboot-required") %>
echo ""
echo "=== Auto-reboot requested, rebooting in 60 seconds ==="
shutdown -r +1 "System reboot scheduled by Foreman patch management"
<% end %>
EOF
```

---

## FASE 24: Scheduling Patch Automatici

### 24.1 Crea Recurring Logic per Patch Settimanali

**Via UI:**

1. Vai su **Monitor → Recurring Logics**
2. Clicca **Create Recurring Logic** (o crea durante la schedulazione di un job)

**Via Job Invocation con schedule:**

1. Vai su **Hosts → All Hosts** → seleziona `ubuntu-24-04-lts`
2. Clicca **Schedule Remote Job**
3. Configura:
    - **Job Template**: `Run Command - Script Default`
    - **Command**: `apt-get update && apt-get upgrade -y`
4. Nel tab **Schedule**:
    - **Execution Ordering**: `Alphabetical`
    - **Schedule**: seleziona **Future execution**
    - **Starts**: scegli data/ora
    - **Repeats**: `Weekly`
    - **Repeat on**: seleziona `Sunday`
5. Clicca **Submit**

### 24.2 Schedule via CLI

```bash
# Crea job schedulato per ogni domenica alle 03:00
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get upgrade -y" \
  --search-query "hostgroup = Ubuntu-2404-Servers" \
  --start-at "2024-01-07 03:00:00" \
  --cron-line "0 3 * * 0"
```

### 24.3 Verifica Job Schedulati

```bash
hammer recurring-logic list
```

```bash
# Visualizza dettagli
hammer recurring-logic info --id <ID>
```

---

## FASE 25: Ansible Integration per Patch Management

### 25.1 Importa Ansible Roles

```bash
# Sincronizza roles da Galaxy o da directory locale
hammer ansible roles sync
```

### 25.2 Crea Playbook per Patch Ubuntu

Crea il file sul server Foreman:

```bash
mkdir -p /etc/ansible/playbooks
cat << 'EOF' > /etc/ansible/playbooks/ubuntu_patch.yml
---
- name: Ubuntu Patch Management
  hosts: all
  become: yes
  
  vars:
    security_only: false
    auto_reboot: false
    
  tasks:
    - name: Update apt cache
      apt:
        update_cache: yes
        cache_valid_time: 3600
        
    - name: Get list of upgradable packages
      command: apt list --upgradable
      register: upgradable
      changed_when: false
      
    - name: Display upgradable packages
      debug:
        var: upgradable.stdout_lines
        
    - name: Upgrade all packages
      apt:
        upgrade: dist
        autoremove: yes
      when: not security_only
      
    - name: Install security updates only
      apt:
        upgrade: yes
        default_release: "{{ ansible_distribution_release }}-security"
      when: security_only
      
    - name: Check if reboot is required
      stat:
        path: /var/run/reboot-required
      register: reboot_required
      
    - name: Display reboot status
      debug:
        msg: "Reboot is {{ 'REQUIRED' if reboot_required.stat.exists else 'not required' }}"
        
    - name: Reboot if required and auto_reboot is true
      reboot:
        msg: "Rebooting due to kernel update"
        pre_reboot_delay: 30
        post_reboot_delay: 60
      when: 
        - reboot_required.stat.exists
        - auto_reboot
EOF
```

### 25.3 Esegui Ansible Job da Foreman

**Via UI:**

1. Vai su **Hosts → All Hosts** → seleziona `ubuntu-24-04-lts`
2. Clicca **Schedule Remote Job**
3. Seleziona:
    - **Job Category**: `Ansible Playbook`
    - **Job Template**: `Ansible Roles - Ansible Default`
4. Configura le variabili
5. Clicca **Submit**

---

## FASE 26: Reportistica e Monitoring

### 26.1 Report Patch Compliance

**Via UI:**

1. Vai su **Monitor → Report Templates**
2. Cerca `Host - Installed Products` o `Applicable Errata`
3. Clicca **Generate** per produrre il report

### 26.2 Crea Report Template Personalizzato

1. Vai su **Monitor → Report Templates → Create Report Template**
2. **Name**: `Ubuntu Patch Status Report`
3. **Template**:

```erb
<%#
name: Ubuntu Patch Status Report
description: Report dello stato patch per host Ubuntu
%>
<%= report_render do %>
Host,IP,OS,Last Checkin,Packages Upgradable,Security Errata,Reboot Required
<% load_hosts(search: "os ~ Ubuntu").each_record do |host| %>
<%= "#{host.name},#{host.ip},#{host.operatingsystem},#{host.last_report},#{host.content_facet&.upgradable_package_count || 'N/A'},#{host.content_facet&.applicable_errata_count || 'N/A'},#{host.content_facet&.reboot_required || 'N/A'}" %>
<% end %>
<% end %>
```

### 26.3 Genera Report via CLI

```bash
hammer report-template generate \
  --name "Host - Installed Products" \
  --organization "PSN-ASL06"
```

---

## FASE 27: Best Practices e Manutenzione

### 27.1 Workflow Consigliato per Patch Management

```
1. SYNC REPOSITORY
   │
   ▼
2. PUBBLICA NUOVA VERSIONE CONTENT VIEW
   │
   ▼
3. PROMUOVI A DEVELOPMENT
   │
   ▼
4. TEST SU HOST DEVELOPMENT
   │
   ▼
5. PROMUOVI A STAGING
   │
   ▼
6. TEST SU HOST STAGING
   │
   ▼
7. PROMUOVI A PRODUCTION
   │
   ▼
8. SCHEDULE PATCH PRODUCTION (Maintenance Window)
```

### 27.2 Pubblica nuova versione Content View

```bash
# Dopo sincronizzazione repository, pubblica nuova versione
hammer content-view publish \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --description "Security updates $(date +%Y-%m-%d)"
```

### 27.3 Promuovi attraverso gli ambienti

```bash
# A Development (subito)
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Development"

# A Staging (dopo test)
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Staging"

# A Production (dopo validazione)
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Production"
```

### 27.4 Maintenance e Cleanup

```bash
# Rimuovi vecchie versioni Content View
hammer content-view purge \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --count 3  # Mantieni solo le ultime 3 versioni
```

```bash
# Pulisci contenuti orfani
foreman-rake katello:delete_orphaned_content RAILS_ENV=production
```

```bash
# Verifica spazio disco Pulp
df -h /var/lib/pulp
```

---

## Comandi Utili - Cheat Sheet

### Host Management

```bash
# Lista host
hammer host list --organization "PSN-ASL06"

# Info host specifico
hammer host info --name "ubuntu-24-04-lts"

# Aggiorna host group
hammer host update --name "ubuntu-24-04-lts" --hostgroup "Ubuntu-2404-Servers"
```

### Content Management

```bash
# Sync manuale repository
hammer repository synchronize --organization "PSN-ASL06" --product "Ubuntu 24.04 LTS" --name "Ubuntu 24.04 Security"

# Lista Content View versions
hammer content-view version list --organization "PSN-ASL06" --content-view "CV-Ubuntu-2404"
```

### Remote Execution

```bash
# Esegui comando su singolo host
hammer job-invocation create --job-template "Run Command - Script Default" --inputs "command=uptime" --search-query "name = ubuntu-24-04-lts"

# Esegui su tutto l'host group
hammer job-invocation create --job-template "Run Command - Script Default" --inputs "command=uptime" --search-query "hostgroup = Ubuntu-2404-Servers"

# Verifica status job
hammer job-invocation info --id <ID>
```

### Errata/Patch

```bash
# Lista errata per host
hammer host errata list --host "ubuntu-24-04-lts"

# Applica errata specifico (per sistemi RPM)
hammer host errata apply --host "ubuntu-24-04-lts" --errata-ids "RHSA-2024:xxxx"
```

---

## Troubleshooting

### Problema: Remote Execution fallisce

```bash
# Verifica connessione SSH
ssh -i /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy root@10.172.2.5

# Verifica chiave autorizzata su target
ssh root@10.172.2.5 "cat /root/.ssh/authorized_keys"

# Verifica logs
tail -f /var/log/foreman-proxy/proxy.log
```

### Problema: Host non riceve aggiornamenti

```bash
# Sulla VM Ubuntu, verifica configurazione repository
cat /etc/apt/sources.list.d/*.list

# Verifica registrazione
subscription-manager identity

# Refresh subscription
subscription-manager refresh
```

### Problema: Sincronizzazione repository fallisce

```bash
# Verifica task
hammer task list --search "result=error"

# Verifica logs Pulp
tail -f /var/log/messages | grep pulp

# Verifica spazio disco
df -h /var/lib/pulp
```

---

## Riferimenti

- [Foreman Documentation](https://docs.theforeman.org/3.15/)
- [Katello Content Management](https://docs.theforeman.org/3.15/Content_Management_Guide/index-katello.html)
- [Remote Execution Guide](https://docs.theforeman.org/3.15/Managing_Hosts/index-katello.html#Configuring_and_Setting_Up_Remote_Jobs_managing-hosts)
- [Ansible Integration](https://docs.theforeman.org/3.15/Managing_Configurations_Using_Ansible/index-katello.html)