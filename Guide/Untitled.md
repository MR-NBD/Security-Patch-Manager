# Guida Patch Management Ubuntu - Parte 2 (dalla FASE 11)

## Stato Attuale Completato

|Fase|Descrizione|Stato|
|---|---|---|
|1-8|Installazione Foreman-Katello|✅|
|9|Associazione Smart Proxy a Org/Location|✅|
|10|Content Credentials (GPG Keys Ubuntu)|✅|

### Ambiente di Riferimento

| Componente       | Valore                           |
| ---------------- | -------------------------------- |
| Server Foreman   | foreman-katello-test.localdomain |
| Organization     | PSN-ASL06                        |
| Location         | Italy-North                      |
| VM Ubuntu Target | 10.172.2.5                       |
| OS Target        | Ubuntu 24.04 LTS                 |

---

## FASE 11: Creazione Product e Repository Ubuntu 24.04

### 11.1 Crea il Product

#### Via Web UI

1. Vai su **Content → Products**
2. Clicca **Create Product**
3. Compila:
    - **Name**: `Ubuntu 24.04 LTS`
    - **Label**: `ubuntu_2404_lts` (auto-generato)
    - **GPG Key**: lascia vuoto (lo assegniamo ai singoli repository)
    - **Description**: `Repository Ubuntu 24.04 Noble Numbat per patch management`
4. Clicca **Save**

#### Via Hammer CLI

```bash
hammer product create \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --label "ubuntu_2404_lts" \
  --description "Repository Ubuntu 24.04 Noble Numbat per patch management"
```

---

### 11.2 Crea Repository Security

#### Via Web UI

1. Vai su **Content → Products → Ubuntu 24.04 LTS**
2. Clicca tab **Repositories** → **New Repository**
3. Compila:
    - **Name**: `Ubuntu 24.04 Security`
    - **Label**: `ubuntu_2404_security`
    - **Description**: `TEST`
    - **Type**: `deb`
    - **URL**: `http://security.ubuntu.com/ubuntu`
    - **Releases**: `noble-security`
    - **Components**: `main universe restricted multiverse`
    - **Architectures**: `amd64`
    - **GPG Key**: `Ubuntu Archive Key` (creato in FASE 10)
    - **Download Policy**: `On Demand`
4. Clicca **Save**

#### Via Hammer CLI

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

---

### 11.3 Crea Repository Updates

#### Via Web UI

1. In **Content → Products → Ubuntu 24.04 LTS → Repositories**
2. Clicca **New Repository**
3. Compila:
    - **Name**: `Ubuntu 24.04 Updates`
    - **Label**: `ubuntu_2404_updates`
    - **Type**: `deb`
    - **URL**: `http://archive.ubuntu.com/ubuntu`
    - **Releases**: `noble-updates`
    - **Components**: `main universe restricted multiverse`
    - **Architectures**: `amd64`
    - **GPG Key**: `Ubuntu Archive Key`
    - **Download Policy**: `On Demand`
4. Clicca **Save**

#### Via Hammer CLI

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

---

### 11.4 Crea Repository Base

#### Via Web UI

1. In **Content → Products → Ubuntu 24.04 LTS → Repositories**
2. Clicca **New Repository**
3. Compila:
    - **Name**: `Ubuntu 24.04 Base`
    - **Label**: `ubuntu_2404_base`
    - **Type**: `deb`
    - **URL**: `http://archive.ubuntu.com/ubuntu`
    - **Releases**: `noble`
    - **Components**: `main universe restricted multiverse`
    - **Architectures**: `amd64`
    - **GPG Key**: `Ubuntu Archive Key`
    - **Download Policy**: `On Demand`
4. Clicca **Save**

#### Via Hammer CLI

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

---

### 11.5 Verifica Repository Creati

#### Via Web UI

1. Vai su **Content → Products → Ubuntu 24.04 LTS → Repositories**
2. Dovresti vedere 3 repository elencati

#### Via Hammer CLI

```bash
hammer repository list --organization "PSN-ASL06" --product "Ubuntu 24.04 LTS"
```

---

## FASE 12: Sincronizzazione Repository

### 12.1 Sincronizza Tutti i Repository

#### Via Web UI

1. Vai su **Content → Products → Ubuntu 24.04 LTS**
2. Seleziona tutti i repository (checkbox)
3. Clicca **Sync Now**

Oppure:

1. Vai su **Content → Sync Status**
2. Espandi **Ubuntu 24.04 LTS**
3. Seleziona i repository da sincronizzare
4. Clicca **Synchronize Now**

#### Via Hammer CLI

```bash
# Sync di tutto il product
hammer product synchronize \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --async
```

Oppure singolarmente:

```bash
# Sync Security (priorità)
hammer repository synchronize \
  --organization "PSN-ASL06" \
  --product "Ubuntu 24.04 LTS" \
  --name "Ubuntu 24.04 Security" \
  --async

# Sync Updates
hammer repository synchronize \
  --organization "PSN-ASL06" \
  --product "Ubuntu 24.04 LTS" \
  --name "Ubuntu 24.04 Updates" \
  --async

# Sync Base
hammer repository synchronize \
  --organization "PSN-ASL06" \
  --product "Ubuntu 24.04 LTS" \
  --name "Ubuntu 24.04 Base" \
  --async
```

---

### 12.2 Monitora Sincronizzazione

#### Via Web UI

1. Vai su **Content → Sync Status**
2. Visualizza lo stato in tempo reale per ogni repository

Oppure:

1. Vai su **Monitor → Tasks**
2. Filtra per `state = running`

#### Via Hammer CLI

```bash
# Lista task in esecuzione
hammer task list --search "state=running"

# Dettaglio task specifico
hammer task progress --id <TASK_ID>
```

---

### 12.3 Crea Sync Plan (Sincronizzazione Automatica)

#### Via Web UI

1. Vai su **Content → Sync Plans**
2. Clicca **Create Sync Plan**
3. Compila:
    - **Name**: `Daily-Ubuntu-Sync`
    - **Description**: `Sincronizzazione giornaliera repository Ubuntu`
    - **Interval**: `daily`
    - **Start Date**: seleziona data
    - **Start Time**: `02:00` (orario notturno)
4. Clicca **Save**
5. Nella pagina del Sync Plan, vai tab **Products**
6. Clicca **Add** → seleziona **Ubuntu 24.04 LTS** → **Add Selected**

#### Via Hammer CLI

```bash
# Crea sync plan
hammer sync-plan create \
  --organization "PSN-ASL06" \
  --name "Daily-Ubuntu-Sync" \
  --description "Sincronizzazione giornaliera repository Ubuntu" \
  --enabled true \
  --interval "daily" \
  --sync-date "2025-01-01 02:00:00"

# Associa product al sync plan
hammer product set-sync-plan \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --sync-plan "Daily-Ubuntu-Sync"
```

---

## FASE 13: Lifecycle Environments

### 13.1 Crea Ambiente Development

#### Via Web UI

1. Vai su **Content → Lifecycle → Lifecycle Environments**
2. Clicca **Create Environment Path**
3. Compila:
    - **Name**: `Development`
    - **Label**: `development`
    - **Description**: `Ambiente di sviluppo e test`
4. Clicca **Save**

#### Via Hammer CLI

```bash
hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Development" \
  --label "development" \
  --prior "Library" \
  --description "Ambiente di sviluppo e test"
```

---

### 13.2 Crea Ambiente Staging

#### Via Web UI

1. In **Lifecycle Environments**, clicca su **Add New Environment** dopo "Development"
2. Compila:
    - **Name**: `Staging`
    - **Label**: `staging`
    - **Description**: `Ambiente di staging pre-produzione`
3. Clicca **Save**

#### Via Hammer CLI

```bash
hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Staging" \
  --label "staging" \
  --prior "Development" \
  --description "Ambiente di staging pre-produzione"
```

---

### 13.3 Crea Ambiente Production

#### Via Web UI

1. In **Lifecycle Environments**, clicca su **Add New Environment** dopo "Staging"
2. Compila:
    - **Name**: `Production`
    - **Label**: `production`
    - **Description**: `Ambiente di produzione`
3. Clicca **Save**

#### Via Hammer CLI

```bash
hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Production" \
  --label "production" \
  --prior "Staging" \
  --description "Ambiente di produzione"
```

---

### 13.4 Verifica Lifecycle Path

#### Via Web UI

Vai su **Content → Lifecycle → Lifecycle Environments**

Dovresti vedere:

```
Library → Development → Staging → Production
```

#### Via Hammer CLI

```bash
hammer lifecycle-environment paths --organization "PSN-ASL06"
```

---

## FASE 14: Content View

### 14.1 Crea Content View

#### Via Web UI

1. Vai su **Content → Lifecycle → Content Views**
2. Clicca **Create Content View**
3. Compila:
    - **Name**: `CV-Ubuntu-2404`
    - **Label**: `cv_ubuntu_2404`
    - **Description**: `Content View per Ubuntu 24.04 LTS`
    - **Type**: `Content View` (non Composite)
4. Clicca **Create Content View**

#### Via Hammer CLI

```bash
hammer content-view create \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --label "cv_ubuntu_2404" \
  --description "Content View per Ubuntu 24.04 LTS"
```

---

### 14.2 Aggiungi Repository alla Content View

#### Via Web UI

1. In **Content Views → CV-Ubuntu-2404**
2. Vai tab **Repositories**
3. Clicca **Add Repositories**
4. Seleziona tutti e 3 i repository:
    - ☑ Ubuntu 24.04 Security
    - ☑ Ubuntu 24.04 Updates
    - ☑ Ubuntu 24.04 Base
5. Clicca **Add Repositories**

#### Via Hammer CLI

```bash
# Aggiungi Security
hammer content-view add-repository \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --product "Ubuntu 24.04 LTS" \
  --repository "Ubuntu 24.04 Security"

# Aggiungi Updates
hammer content-view add-repository \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --product "Ubuntu 24.04 LTS" \
  --repository "Ubuntu 24.04 Updates"

# Aggiungi Base
hammer content-view add-repository \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --product "Ubuntu 24.04 LTS" \
  --repository "Ubuntu 24.04 Base"
```

---

### 14.3 Pubblica Content View

#### Via Web UI

1. In **Content Views → CV-Ubuntu-2404**
2. Clicca **Publish New Version**
3. Compila:
    - **Description**: `Initial publish`
4. Clicca **Publish**
5. Attendi il completamento

#### Via Hammer CLI

```bash
hammer content-view publish \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --description "Initial publish"
```

---

### 14.4 Promuovi Content View a Development

#### Via Web UI

1. In **Content Views → CV-Ubuntu-2404 → Versions**
2. Trova la versione 1.0
3. Clicca sul menu **⋮** → **Promote**
4. Seleziona ☑ **Development**
5. Clicca **Promote**

#### Via Hammer CLI

```bash
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Development"
```

---

### 14.5 Promuovi a Staging e Production

#### Via Web UI

Ripeti il processo di promozione per ogni ambiente:

1. **Versions → ⋮ → Promote → Staging → Promote**
2. **Versions → ⋮ → Promote → Production → Promote**

#### Via Hammer CLI

```bash
# A Staging
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Staging"

# A Production
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Production"
```

---

### 14.6 Verifica Content View

#### Via Web UI

In **Content Views → CV-Ubuntu-2404 → Versions** dovresti vedere la versione presente in tutti gli ambienti.

#### Via Hammer CLI

```bash
hammer content-view info \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404"
```

---

## FASE 15: Operating System

### 15.1 Verifica OS Esistenti

#### Via Web UI

1. Vai su **Hosts → Provisioning Setup → Operating Systems**
2. Cerca se esiste già "Ubuntu 24.04"

#### Via Hammer CLI

```bash
hammer os list | grep -i ubuntu
```

---

### 15.2 Crea Operating System (se non esiste)

#### Via Web UI

1. Vai su **Hosts → Provisioning Setup → Operating Systems**
2. Clicca **Create Operating System**
3. Compila:
    - **Name**: `Ubuntu`
    - **Major Version**: `24`
    - **Minor Version**: `04`
    - **Family**: `Debian`
    - **Release Name**: `noble`
    - **Description**: `Ubuntu 24.04 LTS Noble Numbat`
4. Tab **Architectures**: seleziona ☑ `x86_64`
5. Clicca **Submit**

#### Via Hammer CLI

```bash
# Crea OS
hammer os create \
  --name "Ubuntu" \
  --major "24" \
  --minor "04" \
  --family "Debian" \
  --release-name "noble" \
  --description "Ubuntu 24.04 LTS Noble Numbat"

# Associa architecture
hammer os add-architecture \
  --title "Ubuntu 24.04" \
  --architecture "x86_64"
```

---

### 15.3 Verifica Operating System

#### Via Web UI

In **Operating Systems** dovresti vedere `Ubuntu 24.04`

#### Via Hammer CLI

```bash
hammer os info --title "Ubuntu 24.04"
```

---

## FASE 16: Host Group

### 16.1 Crea Host Group

#### Via Web UI

1. Vai su **Configure → Host Groups**
2. Clicca **Create Host Group**
3. Tab **Host Group**:
    - **Name**: `Ubuntu-2404-Servers`
    - **Description**: `Server Ubuntu 24.04 LTS`
    - **Lifecycle Environment**: `Production`
    - **Content View**: `CV-Ubuntu-2404`
    - **Content Source**: `foreman-katello-test.localdomain`
4. Tab **Operating System**:
    - **Operating System**: `Ubuntu 24.04`
    - **Architecture**: `x86_64`
5. Tab **Locations**: seleziona ☑ `Italy-North`
6. Tab **Organizations**: seleziona ☑ `PSN-ASL06`
7. Clicca **Submit**

#### Via Hammer CLI

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

---

### 16.2 Configura Parametri SSH per Host Group

#### Via Web UI

1. In **Host Groups → Ubuntu-2404-Servers**
2. Vai tab **Parameters**
3. Clicca **Add Parameter**:
    - **Name**: `remote_execution_ssh_user`
    - **Type**: `string`
    - **Value**: `root`
4. Clicca **Add Parameter**:
    - **Name**: `remote_execution_connect_by_ip`
    - **Type**: `boolean`
    - **Value**: `true`
5. Clicca **Submit**

#### Via Hammer CLI

```bash
# Utente SSH
hammer hostgroup set-parameter \
  --hostgroup "Ubuntu-2404-Servers" \
  --name "remote_execution_ssh_user" \
  --parameter-type "string" \
  --value "root"

# Connessione via IP
hammer hostgroup set-parameter \
  --hostgroup "Ubuntu-2404-Servers" \
  --name "remote_execution_connect_by_ip" \
  --parameter-type "boolean" \
  --value "true"
```

---

## FASE 17: Activation Key

### 17.1 Crea Activation Key

#### Via Web UI

1. Vai su **Content → Lifecycle → Activation Keys**
2. Clicca **Create Activation Key**
3. Compila:
    - **Name**: `ak-ubuntu-2404-prod`
    - **Description**: `Activation Key per Ubuntu 24.04 Production`
    - **Environment**: `Production`
    - **Content View**: `CV-Ubuntu-2404`
    - **Unlimited Hosts**: ☑ abilitato
4. Clicca **Save**

#### Via Hammer CLI

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

### 17.2 Verifica Activation Key

#### Via Web UI

In **Activation Keys** dovresti vedere `ak-ubuntu-2404-prod`

#### Via Hammer CLI

```bash
hammer activation-key info \
  --organization "PSN-ASL06" \
  --name "ak-ubuntu-2404-prod"
```

---

## FASE 18: Preparazione VM Ubuntu (10.172.2.5)

Questa fase richiede accesso alla VM Ubuntu target.

### 18.1 Ottieni la Chiave SSH di Foreman

#### Sul Server Foreman

```bash
cat /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy.pub
```

Copia l'output (inizia con `ssh-rsa ...`)

---

### ==18.2 Configura SSH sulla VM Ubuntu==

#### Sulla VM Ubuntu (10.172.2.5)

```bash
# Connettiti alla VM con le tue credenziali attuali
ssh tuo_utente@10.172.2.5
```

```bash
# Diventa root
sudo su -
```

```bash
# Crea directory .ssh se non esiste
mkdir -p /root/.ssh
chmod 700 /root/.ssh
```

```bash
# Aggiungi la chiave pubblica di Foreman
nano /root/.ssh/authorized_keys
```

Incolla la chiave pubblica copiata prima e salva.

```bash
# Imposta permessi corretti
chmod 600 /root/.ssh/authorized_keys
chown root:root /root/.ssh/authorized_keys
```

---

### ==18.3 Configura SSHD==

```bash
# Edita configurazione SSH
nano /etc/ssh/sshd_config
```

Verifica/modifica queste righe:

```
PermitRootLogin prohibit-password
PubkeyAuthentication yes
```

```bash
# Riavvia SSH
systemctl restart sshd
```

---

### ==18.4 Test Connessione SSH==

#### Sul Server Foreman

```bash
ssh -i /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy root@10.172.2.5 "hostname && uptime"
```

Se vedi hostname e uptime della VM, la connessione funziona! ✅

---

## FASE 19: Registrazione Host in Foreman

### 19.1 Metodo Consigliato: Global Registration

#### Via Web UI

1. Vai su **Hosts → Register Host**
2. Compila:
    - **Host Group**: `Ubuntu-2404-Servers`
    - **Operating System**: `Ubuntu 24.04`
    - **Activation Keys**: `ak-ubuntu-2404-prod`
    - **Insecure**: ☑ (se certificato self-signed)
    - **Advanced → Remote Execution Interface**: seleziona l'interfaccia
3. Clicca **Generate**
4. Copia il comando `curl` generato

#### Sulla VM Ubuntu (10.172.2.5)

Esegui il comando curl copiato:

```bash
curl -sS --insecure 'https://foreman-katello-test.localdomain/register?...' | bash
```

---

### 19.2 Metodo Alternativo: Creazione Manuale Host

#### Via Web UI

1. Vai su **Hosts → Create Host**
2. Tab **Host**:
    - **Name**: `ubuntu-24-04-lts`
    - **Organization**: `PSN-ASL06`
    - **Location**: `Italy-North`
    - **Host Group**: `Ubuntu-2404-Servers`
3. Tab **Operating System**:
    - **Operating System**: `Ubuntu 24.04`
    - **Architecture**: `x86_64`
4. Tab **Interfaces**:
    - Clicca **Edit** sull'interfaccia
    - **IPv4 Address**: `10.172.2.5`
    - **Primary**: ☑
    - **Managed**: ☐ (per host esistenti)
5. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer host create \
  --organization "PSN-ASL06" \
  --location "Italy-North" \
  --name "ubuntu-24-04-lts" \
  --hostgroup "Ubuntu-2404-Servers" \
  --operatingsystem "Ubuntu 24.04" \
  --architecture "x86_64" \
  --ip "10.172.2.5" \
  --interface "primary=true,managed=false,ip=10.172.2.5" \
  --build false \
  --managed false
```

---

### 19.3 Verifica Host Registrato

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Dovresti vedere `ubuntu-24-04-lts`

#### Via Hammer CLI

```bash
hammer host info --name "ubuntu-24-04-lts"
```

---

## FASE 20: Configurazione Client sulla VM Ubuntu

### 20.1 Installa Subscription Manager

#### Sulla VM Ubuntu (10.172.2.5)

```bash
# Aggiorna apt
apt-get update

# Installa subscription-manager
apt-get install -y subscription-manager
```

---

### 20.2 Installa Katello CA Certificate

```bash
# Scarica il certificato CA
curl --insecure --output /tmp/katello-ca-consumer-latest.noarch.deb \
  https://foreman-katello-test.localdomain/pub/katello-ca-consumer-latest.noarch.deb

# Installa
dpkg -i /tmp/katello-ca-consumer-latest.noarch.deb
```

---

### 20.3 Registra con Activation Key

```bash
subscription-manager register \
  --org="PSN-ASL06" \
  --activationkey="ak-ubuntu-2404-prod" \
  --force
```

---

### 20.4 Installa Katello Host Tools

```bash
apt-get update
apt-get install -y katello-host-tools
```

---

## FASE 21: Verifica Remote Execution

### 21.1 Test Comando Remoto

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Seleziona ☑ `ubuntu-24-04-lts`
3. Clicca **Select Action → Schedule Remote Job**
4. Compila:
    - **Job Category**: `Commands`
    - **Job Template**: `Run Command - Script Default`
    - **Command**: `hostname && uptime && df -h`
5. Clicca **Submit**
6. Attendi completamento e verifica output

#### Via Hammer CLI

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=hostname && uptime && df -h" \
  --search-query "name = ubuntu-24-04-lts"
```

---

### 21.2 Verifica Output Job

#### Via Web UI

1. Vai su **Monitor → Jobs**
2. Clicca sul job eseguito
3. Visualizza output

#### Via Hammer CLI

```bash
# Lista job recenti
hammer job-invocation list

# Output specifico
hammer job-invocation output --id <JOB_ID> --host "ubuntu-24-04-lts"
```

---

## FASE 22: Patch Management - Visualizzazione

### 22.1 Verifica Pacchetti Installati

#### Via Web UI

1. Vai su **Hosts → Content Hosts**
2. Clicca su `ubuntu-24-04-lts`
3. Tab **Packages**: visualizza pacchetti installati
4. Tab **Errata**: visualizza aggiornamenti disponibili

#### Via Hammer CLI

```bash
# Lista pacchetti aggiornabili
hammer host package list \
  --host "ubuntu-24-04-lts" \
  --status "upgradable"
```

---

## FASE 23: Esecuzione Patch

### 23.1 Aggiorna Tutti i Pacchetti

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Seleziona ☑ `ubuntu-24-04-lts`
3. **Select Action → Schedule Remote Job**
4. Compila:
    - **Job Category**: `Commands`
    - **Job Template**: `Run Command - Script Default`
    - **Command**: `apt-get update && apt-get upgrade -y`
5. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get upgrade -y" \
  --search-query "name = ubuntu-24-04-lts"
```

---

### 23.2 Aggiorna Solo Security

#### Via Web UI

Usa il comando:

```
apt-get update && unattended-upgrade -v
```

#### Via Hammer CLI

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get install -y unattended-upgrades && unattended-upgrade -v" \
  --search-query "name = ubuntu-24-04-lts"
```

---

### 23.3 Dist-Upgrade

#### Via Hammer CLI

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get dist-upgrade -y" \
  --search-query "name = ubuntu-24-04-lts"
```

---

### 23.4 Patch su Tutto l'Host Group

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Filtra per Host Group: `Ubuntu-2404-Servers`
3. Seleziona tutti gli host
4. **Select Action → Schedule Remote Job**

#### Via Hammer CLI

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get upgrade -y" \
  --search-query "hostgroup = Ubuntu-2404-Servers"
```

---

## FASE 24: Scheduling Patch Automatici

### 24.1 Crea Job Schedulato

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Seleziona host o host group
3. **Select Action → Schedule Remote Job**
4. Compila job come sopra
5. Tab **Schedule**:
    - **Schedule**: `Future execution`
    - **Starts**: seleziona data/ora (es. domenica 03:00)
    - **Repeats**: `Weekly`
6. Clicca **Submit**

#### Via Hammer CLI

```bash
# Patch settimanale ogni domenica alle 03:00
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get upgrade -y" \
  --search-query "hostgroup = Ubuntu-2404-Servers" \
  --start-at "2025-01-05 03:00:00" \
  --cron-line "0 3 * * 0"
```

---

### 24.2 Verifica Job Schedulati

#### Via Web UI

Vai su **Monitor → Recurring Logics**

#### Via Hammer CLI

```bash
hammer recurring-logic list
```

---

## FASE 25: Ansible Integration

### 25.1 Test Ansible su Host

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Seleziona ☑ `ubuntu-24-04-lts`
3. **Select Action → Schedule Remote Job**
4. Compila:
    - **Job Category**: `Ansible Playbook`
    - **Job Template**: `Ansible Roles - Ansible Default`
5. Clicca **Submit**

---

## FASE 26: Workflow Patch Management

### 26.1 Processo Consigliato

```
1. SYNC REPOSITORY (automatico via Sync Plan)
         │
         ▼
2. PUBBLICA NUOVA VERSIONE CONTENT VIEW
         │
         ▼
3. PROMUOVI A DEVELOPMENT → Test
         │
         ▼
4. PROMUOVI A STAGING → Validazione
         │
         ▼
5. PROMUOVI A PRODUCTION
         │
         ▼
6. SCHEDULE PATCH (maintenance window)
```

---

### 26.2 Pubblica Nuova Versione CV

#### Via Web UI

1. **Content → Content Views → CV-Ubuntu-2404**
2. Clicca **Publish New Version**
3. Descrizione: `Security updates YYYY-MM-DD`
4. Clicca **Publish**

#### Via Hammer CLI

```bash
hammer content-view publish \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --description "Security updates $(date +%Y-%m-%d)"
```

---

### 26.3 Promuovi Versione

#### Via Hammer CLI

```bash
# A Development
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

---

## FASE 27: Manutenzione

### 27.1 Cleanup Content View Versions

#### Via Web UI

1. **Content Views → CV-Ubuntu-2404**
2. Tab **Versions**
3. Elimina versioni vecchie non più usate

#### Via Hammer CLI

```bash
hammer content-view purge \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --count 3
```

---

### 27.2 Verifica Spazio Disco

```bash
df -h /var/lib/pulp
```

---

### 27.3 Pulizia Contenuti Orfani

```bash
foreman-rake katello:delete_orphaned_content RAILS_ENV=production
```

---

## Comandi Rapidi - Cheat Sheet

```bash
# === HOST ===
hammer host list --organization "PSN-ASL06"
hammer host info --name "ubuntu-24-04-lts"

# === CONTENT ===
hammer repository synchronize --organization "PSN-ASL06" --product "Ubuntu 24.04 LTS" --name "Ubuntu 24.04 Security"
hammer content-view publish --organization "PSN-ASL06" --name "CV-Ubuntu-2404"

# === REMOTE EXECUTION ===
hammer job-invocation create --job-template "Run Command - Script Default" --inputs "command=uptime" --search-query "name = ubuntu-24-04-lts"

# === TASK ===
hammer task list --search "state=running"

# === SYNC ===
hammer sync-plan list --organization "PSN-ASL06"
```

---

## Troubleshooting

### Remote Execution Fallisce

```bash
# Test SSH manuale
ssh -i /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy root@10.172.2.5

# Verifica logs
tail -f /var/log/foreman-proxy/proxy.log
```

### Host Non Riceve Aggiornamenti

```bash
# Sulla VM Ubuntu
subscription-manager identity
subscription-manager refresh
apt-get update
```

### Sincronizzazione Fallisce

```bash
hammer task list --search "result=error"
df -h /var/lib/pulp
```