# Guida Completa Foreman-Katello: Dalla FASE 7 al Patch Management

## Stato Prerequisiti Completati (FASI 1-6)

|Fase|Descrizione|Stato|
|---|---|---|
|1|Verifica Sistema + Aggiornamento SELinux|✅|
|2|Configurazione NTP (Chrony)|✅|
|3|Hostname e Networking|✅|
|4|Firewall|✅|
|5|Storage LVM per Pulp|✅|
|6|Repository (Foreman, Katello, Puppet)|✅|

### Ambiente di Riferimento

|Componente|Valore|
|---|---|
|Server Foreman|foreman-katello-test.localdomain|
|IP Server Foreman|10.172.2.17|
|Organization|PSN-ASL06|
|Location|Italy-North|
|VM Ubuntu Target|10.172.2.5|
|OS Target|Ubuntu 24.04 LTS (noble)|

---

## FASE 7: Installazione Foreman-Katello

### 7.1 Installa il pacchetto installer

```bash
dnf install -y foreman-installer-katello
```

### 7.2 Esegui l'installazione completa

> **IMPORTANTE**: Questo comando include tutte le opzioni necessarie, incluse Registration e Templates per il Smart Proxy.

```bash
foreman-installer --scenario katello \
  --foreman-initial-admin-username admin \
  --foreman-initial-admin-password 'SecurePassword123!' \
  --enable-foreman-plugin-remote-execution \
  --enable-foreman-proxy-plugin-remote-execution-script \
  --enable-foreman-plugin-ansible \
  --enable-foreman-proxy-plugin-ansible \
  --enable-foreman-plugin-templates \
  --enable-foreman-cli-katello \
  --foreman-proxy-registration true \
  --foreman-proxy-templates true
```

#### Spiegazione opzioni:

|Opzione|Descrizione|
|---|---|
|`--scenario katello`|Installa Foreman con Katello|
|`--foreman-initial-admin-username`|Username admin|
|`--foreman-initial-admin-password`|Password admin|
|`--enable-foreman-plugin-remote-execution`|Esecuzione comandi via SSH|
|`--enable-foreman-proxy-plugin-remote-execution-script`|Proxy per SSH|
|`--enable-foreman-plugin-ansible`|Integrazione Ansible|
|`--enable-foreman-proxy-plugin-ansible`|Proxy per Ansible|
|`--enable-foreman-plugin-templates`|Gestione template|
|`--enable-foreman-cli-katello`|CLI hammer per Katello|
|`--foreman-proxy-registration true`|**Feature Registration** (necessaria per Global Registration)|
|`--foreman-proxy-templates true`|**Feature Templates** (necessaria per Global Registration)|

> **NOTA**: L'installazione richiede 15-30 minuti.

### 7.3 Output atteso

```
Success!
  * Foreman is running at https://foreman-katello-test.localdomain
      Initial credentials are admin / SecurePassword123!
  * Foreman Proxy is running at https://foreman-katello-test.localdomain:9090
```

---

## FASE 8: Verifica dell'Installazione

### 8.1 Verifica stato servizi

```bash
foreman-maintain service status
```

### 8.2 Verifica accesso web

Apri browser: `https://foreman-katello-test.localdomain` (o IP: `https://10.172.2.17`)

- **Username**: `admin`
- **Password**: `SecurePassword123!`

### 8.3 Recupera credenziali (se necessario)

```bash
grep admin_password /etc/foreman-installer/scenarios.d/katello-answers.yaml
```

### 8.4 Verifica Smart Proxy features

```bash
hammer proxy info --name "foreman-katello-test.localdomain"
```

Dovresti vedere in Active features:

- Ansible
- Dynflow
- Logs
- Pulpcore
- Script
- **Registration** ✅
- **Templates** ✅

### 8.5 Refresh features (se necessario)

```bash
hammer proxy refresh-features --name "foreman-katello-test.localdomain"
```

---

## FASE 9: Configurazione Organization, Location e Smart Proxy

### 9.1 Crea Organization

#### Via Web UI

1. Vai su **Administer → Organizations**
2. Clicca **New Organization**
3. Compila:
    - **Name**: `PSN-ASL06`
    - **Label**: `myorg`
4. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer organization create --name "PSN-ASL06" --label "myorg"
```

### 9.2 Crea Location

#### Via Web UI

1. Vai su **Administer → Locations**
2. Clicca **New Location**
3. Compila:
    - **Name**: `Italy-North`
4. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer location create --name "Italy-North"
```

### 9.3 Associa Location all'Organization

#### Via Web UI

1. Vai su **Administer → Organizations → PSN-ASL06 → Edit**
2. Tab **Locations** → seleziona `Italy-North`
3. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer organization add-location --name "PSN-ASL06" --location "Italy-North"
```

### 9.4 Associa Smart Proxy all'Organization

> **IMPORTANTE**: Senza questo passaggio, il Smart Proxy non apparirà in "Register Host".

#### Via Web UI

1. Vai su **Administer → Organizations → PSN-ASL06 → Edit**
2. Tab **Smart Proxies** → seleziona `foreman-katello-test.localdomain`
3. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer organization add-smart-proxy \
  --name "PSN-ASL06" \
  --smart-proxy "foreman-katello-test.localdomain"
```

### 9.5 Associa Smart Proxy alla Location

#### Via Web UI

1. Vai su **Administer → Locations → Italy-North → Edit**
2. Tab **Smart Proxies** → seleziona `foreman-katello-test.localdomain`
3. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer location add-smart-proxy \
  --name "Italy-North" \
  --smart-proxy "foreman-katello-test.localdomain"
```

### 9.6 Verifica associazioni

```bash
hammer organization info --name "PSN-ASL06" | grep -i proxy
hammer location info --name "Italy-North" | grep -i proxy
```

---

## FASE 10: Content Credentials (Chiavi GPG Ubuntu)

### 10.1 Scarica chiavi GPG

```bash
mkdir -p /etc/pki/rpm-gpg/import

curl -o /etc/pki/rpm-gpg/import/ubuntu-archive-keyring.gpg \
  "http://archive.ubuntu.com/ubuntu/project/ubuntu-archive-keyring.gpg"
```

### 10.2 Converti in formato ASCII

```bash
gpg --no-default-keyring \
  --keyring /etc/pki/rpm-gpg/import/ubuntu-archive-keyring.gpg \
  --export --armor > /etc/pki/rpm-gpg/import/ubuntu-keys-ascii.asc
```

### 10.3 Crea Content Credential in Foreman

#### Via Web UI

1. Vai su **Content → Content Credentials**
2. Clicca **Create Content Credential**
3. Compila:
    - **Name**: `Ubuntu Archive Key`
    - **Content Credential Type**: `GPG Key`
    - **Content Credential Contents**: incolla output di `cat /etc/pki/rpm-gpg/import/ubuntu-keys-ascii.asc`
4. Clicca **Save**

#### Via Hammer CLI

```bash
hammer content-credentials create \
  --organization "PSN-ASL06" \
  --name "Ubuntu Archive Key" \
  --content-type "gpg_key" \
  --path "/etc/pki/rpm-gpg/import/ubuntu-keys-ascii.asc"
```

---

## FASE 11: Creazione Product e Repository Ubuntu 24.04

### 11.1 Crea Product

#### Via Web UI

1. Vai su **Content → Products**
2. Clicca **Create Product**
3. Compila:
    - **Name**: `Ubuntu 24.04 LTS`
    - **Label**: `ubuntu_2404_lts`
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

### 11.2 Crea Repository Security

#### Via Web UI

1. Vai su **Content → Products → Ubuntu 24.04 LTS → Repositories**
2. Clicca **New Repository**
3. Compila:
    - **Name**: `Ubuntu 24.04 Security`
    - **Type**: `deb`
    - **URL**: `http://security.ubuntu.com/ubuntu`
    - **Releases**: `noble-security`
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

### 11.3 Crea Repository Updates

#### Via Web UI

1. In **Content → Products → Ubuntu 24.04 LTS → Repositories**
2. Clicca **New Repository**
3. Compila:
    - **Name**: `Ubuntu 24.04 Updates`
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

### 11.4 Crea Repository Base

#### Via Web UI

1. In **Content → Products → Ubuntu 24.04 LTS → Repositories**
2. Clicca **New Repository**
3. Compila:
    - **Name**: `Ubuntu 24.04 Base`
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

### 11.5 Verifica Repository

```bash
hammer repository list --organization "PSN-ASL06" --product "Ubuntu 24.04 LTS"
```

---

## FASE 12: Sincronizzazione Repository

### 12.1 Sincronizza tutti i Repository

#### Via Web UI

1. Vai su **Content → Sync Status**
2. Espandi **Ubuntu 24.04 LTS**
3. Seleziona tutti i repository
4. Clicca **Synchronize Now**

#### Via Hammer CLI

```bash
hammer product synchronize \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --async
```

### 12.2 Monitora sincronizzazione

#### Via Web UI

**Content → Sync Status** oppure **Monitor → Tasks**

#### Via Hammer CLI

```bash
hammer task list --search "state=running"
```

### 12.3 Crea Sync Plan automatico

#### Via Web UI

1. Vai su **Content → Sync Plans**
2. Clicca **Create Sync Plan**
3. Compila:
    - **Name**: `Daily-Ubuntu-Sync`
    - **Interval**: `daily`
    - **Start Time**: `02:00`
4. Clicca **Save**
5. Tab **Products** → **Add** → seleziona `Ubuntu 24.04 LTS`

#### Via Hammer CLI

```bash
hammer sync-plan create \
  --organization "PSN-ASL06" \
  --name "Daily-Ubuntu-Sync" \
  --description "Sincronizzazione giornaliera repository Ubuntu" \
  --enabled true \
  --interval "daily" \
  --sync-date "2025-01-01 02:00:00"

hammer product set-sync-plan \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --sync-plan "Daily-Ubuntu-Sync"
```

---

## FASE 13: Lifecycle Environments

### 13.1 Crea Development

#### Via Web UI

1. Vai su **Content → Lifecycle → Lifecycle Environments**
2. Clicca **Create Environment Path**
3. **Name**: `Development`, **Prior**: `Library`
4. Clicca **Save**

#### Via Hammer CLI

```bash
hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Development" \
  --label "development" \
  --prior "Library"
```

### 13.2 Crea Staging

#### Via Web UI

1. Clicca **Add New Environment** dopo Development
2. **Name**: `Staging`
3. Clicca **Save**

#### Via Hammer CLI

```bash
hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Staging" \
  --label "staging" \
  --prior "Development"
```

### 13.3 Crea Production

#### Via Web UI

1. Clicca **Add New Environment** dopo Staging
2. **Name**: `Production`
3. Clicca **Save**

#### Via Hammer CLI

```bash
hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Production" \
  --label "production" \
  --prior "Staging"
```

### 13.4 Verifica Lifecycle Path

```bash
hammer lifecycle-environment paths --organization "PSN-ASL06"
```

Output: `Library >> Development >> Staging >> Production`

---

## FASE 14: Content View

### 14.1 Crea Content View

#### Via Web UI

1. Vai su **Content → Lifecycle → Content Views**
2. Clicca **Create Content View**
3. Compila:
    - **Name**: `CV-Ubuntu-2404`
    - **Type**: `Content View` (non Composite)
    - **Solve Dependencies**: ☐ (lascia disabilitato)
4. Clicca **Create Content View**

#### Via Hammer CLI

```bash
hammer content-view create \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --label "cv_ubuntu_2404" \
  --description "Content View per Ubuntu 24.04 LTS"
```

### 14.2 Aggiungi Repository

#### Via Web UI

1. In **CV-Ubuntu-2404 → Repositories**
2. Clicca **Add Repositories**
3. Seleziona tutti e 3 i repository
4. Clicca **Add Repositories**

#### Via Hammer CLI

```bash
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
```

### 14.3 Pubblica Content View

#### Via Web UI

1. In **CV-Ubuntu-2404** clicca **Publish New Version**
2. Description: `Initial publish`
3. Clicca **Publish**

#### Via Hammer CLI

```bash
hammer content-view publish \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --description "Initial publish"
```

### 14.4 Promuovi attraverso gli ambienti

#### Via Web UI

1. In **Versions** → clicca **⋮** → **Promote**
2. Seleziona ambiente → **Promote**
3. Ripeti per ogni ambiente

#### Via Hammer CLI

```bash
# A Development
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Development"

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

## FASE 15: Operating System

### 15.1 Verifica OS esistenti

```bash
hammer os list
```

### 15.2 Crea Operating System (se non esiste)

> **NOTA**: Il nome Ubuntu deve essere **minuscolo** (`ubuntu`) per evitare errori.

#### Via Web UI

1. Vai su **Hosts → Provisioning Setup → Operating Systems**
2. Clicca **Create Operating System**
3. Compila:
    - **Name**: `ubuntu` (minuscolo!)
    - **Major Version**: `24`
    - **Minor Version**: `04`
    - **Family**: `Debian`
    - **Release Name**: `noble`
4. Tab **Architectures** → seleziona `x86_64`
5. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer os create \
  --name "ubuntu" \
  --major "24" \
  --minor "04" \
  --family "Debian" \
  --release-name "noble"

hammer os add-architecture \
  --title "ubuntu 24.04" \
  --architecture "x86_64"
```

### 15.3 Verifica Operating System

```bash
hammer os list
```

Output atteso: `ubuntu 24.04` (minuscolo)

---

## FASE 16: Host Group

### 16.1 Crea Host Group

> **NOTA**: Host Groups si trova in **Configure → Host Groups**, non in "Hosts → Host Collections".

#### Via Web UI

1. Vai su **Configure → Host Groups**
2. Clicca **Create Host Group**
3. Tab **Host Group**:
    - **Name**: `Ubuntu-2404-Groups`
    - **Lifecycle Environment**: `Production`
    - **Content View**: `CV-Ubuntu-2404`
    - **Content Source**: `foreman-katello-test.localdomain`
4. Tab **Operating System**:
    - **Operating System**: `ubuntu 24.04`
    - **Architecture**: `x86_64`
5. Tab **Locations** → seleziona `Italy-North`
6. Tab **Organizations** → seleziona `PSN-ASL06`
7. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer hostgroup create \
  --organization "PSN-ASL06" \
  --location "Italy-North" \
  --name "Ubuntu-2404-Groups" \
  --lifecycle-environment "Production" \
  --content-view "CV-Ubuntu-2404" \
  --content-source "foreman-katello-test.localdomain" \
  --operatingsystem "ubuntu 24.04"
```

### 16.2 Configura Parametri SSH

#### Via Web UI

1. In **Host Groups → Ubuntu-2404-Groups → Parameters**
2. Aggiungi parametri

#### Via Hammer CLI

```bash
hammer hostgroup set-parameter \
  --hostgroup "Ubuntu-2404-Groups" \
  --name "remote_execution_ssh_user" \
  --parameter-type "string" \
  --value "root"

hammer hostgroup set-parameter \
  --hostgroup "Ubuntu-2404-Groups" \
  --name "remote_execution_connect_by_ip" \
  --parameter-type "boolean" \
  --value "true"
```

### 16.3 Verifica Host Group

```bash
hammer hostgroup list
```

---

## FASE 17: Activation Key

### 17.1 Crea Activation Key

#### Via Web UI

1. Vai su **Content → Lifecycle → Activation Keys**
2. Clicca **Create Activation Key**
3. Compila:
    - **Name**: `ak-ubuntu-2404-prod`
    - **Environment**: `Production`
    - **Content View**: `CV-Ubuntu-2404`
    - **Unlimited Hosts**: ☑
4. Clicca **Save**

#### Via Hammer CLI

```bash
hammer activation-key create \
  --organization "PSN-ASL06" \
  --name "ak-ubuntu-2404-prod" \
  --lifecycle-environment "Production" \
  --content-view "CV-Ubuntu-2404" \
  --unlimited-hosts
```

---

## FASE 18: Preparazione VM Ubuntu per SSH

### 18.1 Aggiungi entry hosts sulla VM Ubuntu

Sulla **VM Ubuntu** (10.172.2.5), aggiungi il server Foreman al file hosts:

```bash
echo "10.172.2.17 foreman-katello-test.localdomain foreman-katello-test" | sudo tee -a /etc/hosts
```

### 18.2 Configura SSH per root

Sulla **VM Ubuntu**:

```bash
# Abilita SSH per root
sudo nano /etc/ssh/sshd_config
```

Decommenta/modifica:

```
PermitRootLogin prohibit-password
PubkeyAuthentication yes
```

```bash
sudo systemctl restart ssh
```

### 18.3 Copia chiave SSH di Foreman sulla VM Ubuntu

> **METODO CONSIGLIATO**: Esegui questo comando dal **server Foreman** come root.

```bash
cat /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy.pub | ssh azureuser@10.172.2.5 "
  sudo mkdir -p /root/.ssh &&
  sudo chmod 700 /root/.ssh &&
  sudo tee /root/.ssh/authorized_keys > /dev/null &&
  sudo chmod 600 /root/.ssh/authorized_keys &&
  sudo chown -R root:root /root/.ssh
"
```

> **NOTA**: Sostituisci `azureuser` con il tuo utente SSH sulla VM Ubuntu.

### 18.4 Test connessione SSH

Dal **server Foreman** come root:

```bash
ssh -i /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy root@10.172.2.5 "hostname && uptime"
```

Output atteso:

```
test-Lorenzo-1
 10:26:43 up 6 min,  2 users,  load average: 0.09, 0.19, 0.12
```

✅ Se vedi hostname e uptime, la connessione funziona!

---

## FASE 19: Registrazione Host in Foreman

> **IMPORTANTE**: Per host Ubuntu esistenti, usare il metodo **Hammer CLI** è più affidabile della UI.

### 19.1 Registra host via Hammer CLI (Metodo Consigliato)

```bash
hammer host create \
  --organization "PSN-ASL06" \
  --location "Italy-North" \
  --name "test-Lorenzo-1" \
  --hostgroup "Ubuntu-2404-Groups" \
  --operatingsystem "ubuntu 24.04" \
  --architecture "x86_64" \
  --ip "10.172.2.5" \
  --managed false \
  --build false
```

> **NOTA**: Assicurati di usare:
> 
> - `--operatingsystem "ubuntu 24.04"` (minuscolo!)
> - `--hostgroup "Ubuntu-2404-Groups"` (nome esatto)

### 19.2 Verifica host registrato

#### Via Web UI

Vai su **Hosts → All Hosts** → dovresti vedere `test-Lorenzo-1`

#### Via Hammer CLI

```bash
hammer host info --name "test-Lorenzo-1"
```

### 19.3 Metodo alternativo: Via Web UI

Se preferisci la UI, ricorda:

1. **Hosts → Create Host**
2. Tab **Host**: Name, Organization, Location, Host Group
3. Tab **Operating System**:
    - **Build Mode**: ☐ **DISABILITATO**
    - Operating System: `ubuntu 24.04`
4. Tab **Interfaces** → Edit:
    - **IPv4 Address**: `10.172.2.5`
    - **Primary**: ☑
    - **Managed**: ☐
    - **Provision**: ☐
    - **Remote Execution**: ☑
5. Clicca **OK** → **Submit**

---

## FASE 20: Verifica Remote Execution

### 20.1 Test comando remoto

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Seleziona ☑ `test-Lorenzo-1`
3. Clicca **Select Action → Schedule Remote Job**
4. Compila:
    - **Job Category**: `Commands`
    - **Job Template**: `Run Command - Script Default`
    - **Command**: `hostname && uptime && df -h`
5. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=hostname && uptime && df -h" \
  --search-query "name = test-Lorenzo-1"
```

### 20.2 Verifica output job

#### Via Web UI

**Monitor → Jobs** → clicca sul job → visualizza output

#### Via Hammer CLI

```bash
hammer job-invocation list
hammer job-invocation output --id <JOB_ID> --host "test-Lorenzo-1"
```

---

## FASE 21: Patch Management - Visualizzazione

### 21.1 Verifica pacchetti installati

#### Via Web UI

1. Vai su **Hosts → Content Hosts**
2. Clicca su `test-Lorenzo-1`
3. Tab **Packages**: pacchetti installati
4. Tab **Errata**: aggiornamenti disponibili

#### Via Hammer CLI

```bash
hammer host package list --host "test-Lorenzo-1"
```

---

## FASE 22: Esecuzione Patch

### 22.1 Aggiorna tutti i pacchetti

#### Via Web UI

1. **Hosts → All Hosts** → seleziona host
2. **Schedule Remote Job**
3. Command: `apt-get update && apt-get upgrade -y`

#### Via Hammer CLI

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get upgrade -y" \
  --search-query "name = test-Lorenzo-1"
```

### 22.2 Solo Security Updates

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get install -y unattended-upgrades && unattended-upgrade -v" \
  --search-query "name = test-Lorenzo-1"
```

### 22.3 Dist-Upgrade

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get dist-upgrade -y" \
  --search-query "name = test-Lorenzo-1"
```

### 22.4 Patch su tutto l'Host Group

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get upgrade -y" \
  --search-query "hostgroup = Ubuntu-2404-Groups"
```

---

## FASE 23: Scheduling Patch Automatici

### 23.1 Job schedulato settimanale

#### Via Web UI

1. **Schedule Remote Job**
2. Tab **Schedule**:
    - **Schedule**: `Future execution`
    - **Starts**: scegli data/ora
    - **Repeats**: `Weekly`
3. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt-get update && apt-get upgrade -y" \
  --search-query "hostgroup = Ubuntu-2404-Groups" \
  --start-at "2025-01-05 03:00:00" \
  --cron-line "0 3 * * 0"
```

### 23.2 Verifica job schedulati

```bash
hammer recurring-logic list
```

---

## FASE 24: Workflow Patch Management

### Processo Consigliato

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

### Pubblica nuova versione CV

```bash
hammer content-view publish \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --description "Security updates $(date +%Y-%m-%d)"
```

### Promuovi

```bash
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Production"
```

---

## FASE 25: Manutenzione

### Cleanup vecchie versioni CV

```bash
hammer content-view purge \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --count 3
```

### Verifica spazio disco

```bash
df -h /var/lib/pulp
```

### Pulizia contenuti orfani

```bash
foreman-rake katello:delete_orphaned_content RAILS_ENV=production
```

---

## Comandi Rapidi - Cheat Sheet

```bash
# === VERIFICA ===
hammer proxy info --name "foreman-katello-test.localdomain"
hammer host list --organization "PSN-ASL06"
hammer hostgroup list
hammer os list

# === SYNC ===
hammer product synchronize --organization "PSN-ASL06" --name "Ubuntu 24.04 LTS" --async

# === CONTENT VIEW ===
hammer content-view publish --organization "PSN-ASL06" --name "CV-Ubuntu-2404"
hammer content-view version promote --organization "PSN-ASL06" --content-view "CV-Ubuntu-2404" --to-lifecycle-environment "Production"

# === REMOTE EXECUTION ===
hammer job-invocation create --job-template "Run Command - Script Default" --inputs "command=uptime" --search-query "name = test-Lorenzo-1"

# === SSH TEST ===
ssh -i /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy root@10.172.2.5 "hostname"

# === TASK ===
hammer task list --search "state=running"
```

---

## Troubleshooting

### Smart Proxy non appare in Register Host

```bash
foreman-installer --foreman-proxy-registration true --foreman-proxy-templates true
hammer proxy refresh-features --name "foreman-katello-test.localdomain"
```

### Remote Execution fallisce

```bash
# Verifica SSH
ssh -i /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy root@<IP_HOST> "hostname"

# Verifica chiave sulla VM
cat /root/.ssh/authorized_keys

# Verifica logs
tail -f /var/log/foreman-proxy/proxy.log
```

### Errore "operatingsystem not found"

```bash
hammer os list  # Verifica nome esatto (es. "ubuntu 24.04" minuscolo)
```

### Errore "hostgroup not found"

```bash
hammer hostgroup list  # Verifica nome esatto
```

### VM non risolve hostname Foreman

```bash
# Sulla VM
echo "10.172.2.17 foreman-katello-test.localdomain" | sudo tee -a /etc/hosts
```