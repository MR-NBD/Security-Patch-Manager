# Guida Registrazione Content Host Ubuntu 24.04

## Panoramica

Questa guida descrive i passaggi per **rimuovere** l'host esistente registrato in modo incompleto e **ri-registrarlo correttamente** come **Content Host** in Foreman/Katello.

L'obiettivo è avere una VM Ubuntu 24.04 che:

- Sia visibile in **Hosts → Content Hosts**
- Riceva i repository configurati nella Content View
- Possa ricevere aggiornamenti di sicurezza tramite Katello

### Ambiente di Riferimento

|Componente|Valore|
|---|---|
|Server Foreman|foreman-katello-test.localdomain (10.172.2.15)|
|Organization|PSN-ASL06|
|Location|Italy-North|
|VM Ubuntu Target|test-Lorenzo-1 (10.172.2.5)|
|OS Target|Ubuntu 24.04 LTS (Noble)|
|Content View|CV-Ubuntu-2404|
|Activation Key|ak-ubuntu-2404-prod|
|Lifecycle Environment|Production|

### Prerequisiti Completati

Prima di procedere, assicurati di aver completato:

- [x] FASE 1-9: Installazione Foreman/Katello
- [x] FASE 10: Content Credentials (GPG Keys)
- [x] FASE 11: Product e Repository Ubuntu 24.04
- [x] FASE 12: Sincronizzazione Repository
- [x] FASE 13: Lifecycle Environments
- [x] FASE 14: Content View (CV-Ubuntu-2404)
- [x] FASE 15: Operating System
- [x] FASE 16: Host Group
- [x] FASE 17: Activation Key
- [x] FASE 18: Configurazione SSH sulla VM Ubuntu

---

## FASE 21: Rimozione Host Esistente

> **NOTA**: Questo passaggio è necessario solo se hai già registrato l'host con `hammer host create --managed false`. Se l'host non esiste, salta alla FASE 22.

### 21.1 Verifica Host Esistente

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Cerca `test-Lorenzo-1`
3. Verifica se è presente

#### Via Hammer CLI

```bash
hammer host list --search "name = test-Lorenzo-1"
```

### 21.2 Rimuovi Host da Foreman

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Trova `test-Lorenzo-1`
3. Clicca sul menu **⋮** (tre puntini) a destra
4. Seleziona **Delete**
5. Nella finestra di conferma:
    - ☑ Seleziona tutte le opzioni di cleanup se presenti
6. Clicca **Delete**

#### Via Hammer CLI

```bash
hammer host delete --name "test-Lorenzo-1"
```

### 21.3 Verifica Rimozione

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Cerca `test-Lorenzo-1`
3. Non dovrebbe apparire nessun risultato

#### Via Hammer CLI

```bash
hammer host list --search "name = test-Lorenzo-1"
```

Output atteso: nessun host trovato.

### 21.4 Verifica Content Hosts (se presente)

#### Via Web UI

1. Vai su **Hosts → Content Hosts**
2. Cerca `test-Lorenzo-1`
3. Se presente, rimuovilo:
    - Seleziona ☑ l'host
    - Clicca **Select Action → Unregister Hosts**

#### Via Hammer CLI

```bash
# Verifica se esiste come content host
hammer content-host list --organization "PSN-ASL06" --search "name = test-Lorenzo-1"

# Se esiste, rimuovilo
hammer content-host delete --organization "PSN-ASL06" --name "test-Lorenzo-1"
```

---

## FASE 22: Preparazione VM Ubuntu per Content Host

Questi passaggi vanno eseguiti **sulla VM Ubuntu** (10.172.2.5).

### 22.1 Connessione alla VM

```bash
# Dal server Foreman o dalla tua workstation
ssh azureuser@10.172.2.5
```

### 22.2 Diventa Root

```bash
sudo su -
```

### 22.3 Verifica Connettività verso Foreman

```bash
# Test connessione HTTPS
curl -k https://foreman-katello-test.localdomain/
```

Se non funziona, verifica:

- Risoluzione DNS o aggiungi entry in `/etc/hosts`
- Firewall

```bash
# Se necessario, aggiungi entry hosts
echo "10.172.2.15 foreman-katello-test.localdomain" >> /etc/hosts
```

### 22.4 Installa Dipendenze Base

```bash
apt update
apt install -y curl ca-certificates gnupg
```

---

## FASE 23: Configurazione Repository ATIX per subscription-manager

ATIX fornisce i pacchetti `subscription-manager` per Ubuntu, necessari per registrare l'host come Content Host.

### 23.1 Aggiungi Chiave GPG ATIX

```bash
# Scarica e installa la chiave GPG
curl -fsSL https://apt.atix.de/atix.asc | gpg --dearmor -o /usr/share/keyrings/atix-archive-keyring.gpg
```

### 23.2 Aggiungi Repository ATIX

```bash
# Crea il file repository per Ubuntu 24.04
cat > /etc/apt/sources.list.d/atix.list << 'EOF'
deb [signed-by=/usr/share/keyrings/atix-archive-keyring.gpg] http://apt.atix.de/Ubuntu24LTS stable main
EOF
```

> **NOTA**: Per altre versioni Ubuntu usa:
> 
> - Ubuntu 22.04: `http://apt.atix.de/Ubuntu22LTS`
> - Ubuntu 20.04: `http://apt.atix.de/Ubuntu20LTS`

### 23.3 Aggiorna Cache APT

```bash
apt update
```

### 23.4 Verifica Disponibilità Pacchetti

```bash
apt-cache search subscription-manager
```

Output atteso:

```
python3-subscription-manager - RHSM subscription-manager (Python 3)
subscription-manager - RHSM subscription-manager
...
```

---

## FASE 24: Installazione subscription-manager

### 24.1 Installa subscription-manager e Tools

```bash
apt install -y subscription-manager
```

### 24.2 Installa Katello Host Tools (opzionale ma raccomandato)

```bash
apt install -y katello-host-tools
```

> **NOTA**: `katello-host-tools` permette di:
> 
> - Inviare il profilo pacchetti a Katello
> - Visualizzare i pacchetti installati nella Web UI

### 24.3 Verifica Installazione

```bash
subscription-manager version
```

Output atteso:

```
server type: This system is currently not registered.
subscription management server: Unknown
subscription management rules: Unknown
subscription-manager: 1.29.x
```

---

## FASE 25: Configurazione Certificato CA Katello

### 25.1 Scarica il Certificato CA dal Server Foreman

```bash
# Crea directory se non esiste
mkdir -p /etc/rhsm/ca

# Scarica il certificato CA
curl -o /etc/rhsm/ca/katello-server-ca.pem \
  https://foreman-katello-test.localdomain/pub/katello-server-ca.crt \
  --insecure
```

### 25.2 Verifica il Certificato

```bash
ls -la /etc/rhsm/ca/katello-server-ca.pem
```

```bash
# Visualizza info certificato
openssl x509 -in /etc/rhsm/ca/katello-server-ca.pem -text -noout | head -20
```

---

## FASE 26: Configurazione subscription-manager

### 26.1 Configura Server Katello

```bash
subscription-manager config \
  --server.hostname=foreman-katello-test.localdomain \
  --server.port=443 \
  --server.prefix=/rhsm \
  --rhsm.repo_ca_cert=/etc/rhsm/ca/katello-server-ca.pem \
  --rhsm.baseurl=https://foreman-katello-test.localdomain/pulp/deb
```

### 26.2 Verifica Configurazione

```bash
subscription-manager config
```

Output atteso (sezioni rilevanti):

```
[server]
   hostname = foreman-katello-test.localdomain
   port = 443
   prefix = /rhsm
   ...

[rhsm]
   baseurl = https://foreman-katello-test.localdomain/pulp/deb
   repo_ca_cert = /etc/rhsm/ca/katello-server-ca.pem
   ...
```

### 26.3 Verifica File di Configurazione (alternativa)

```bash
cat /etc/rhsm/rhsm.conf
```

---

## FASE 27: Registrazione Content Host

### 27.1 Registra l'Host con Activation Key

```bash
subscription-manager register \
  --org="PSN-ASL06" \
  --activationkey="ak-ubuntu-2404-prod" \
  --name="test-Lorenzo-1"
```

> **NOTA**: Il parametro `--name` è opzionale. Se omesso, usa l'hostname della macchina.

Output atteso:

```
The system has been registered with ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### 27.2 Troubleshooting Registrazione

Se ricevi errori, verifica:

#### Errore: "Organization not found"

```bash
# Verifica il nome esatto dell'organizzazione sul server Foreman
hammer organization list
```

#### Errore: "Unable to find activation key"

```bash
# Verifica il nome esatto della activation key
hammer activation-key list --organization "PSN-ASL06"
```

#### Errore: "Connection refused" o "SSL error"

```bash
# Verifica connettività
curl -k https://foreman-katello-test.localdomain/rhsm/status

# Verifica che il certificato CA sia corretto
curl --cacert /etc/rhsm/ca/katello-server-ca.pem \
  https://foreman-katello-test.localdomain/rhsm/status
```

### 27.3 Verifica Registrazione sulla VM

```bash
subscription-manager identity
```

Output atteso:

```
system identity: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
name: test-Lorenzo-1
org name: PSN-ASL06
org ID: PSN-ASL06
```

---

## FASE 28: Verifica Content Host in Foreman

### 28.1 Verifica via Web UI

1. Vai su **Hosts → Content Hosts**
2. Cerca `test-Lorenzo-1`
3. Dovresti vedere l'host con:
    - **Subscription Status**: verde (subscribed)
    - **Content View**: CV-Ubuntu-2404
    - **Lifecycle Environment**: Production

### 28.2 Verifica via Hammer CLI

```bash
hammer content-host info \
  --organization "PSN-ASL06" \
  --name "test-Lorenzo-1"
```

Output atteso (campi chiave):

```
ID:                   X
Name:                 test-Lorenzo-1
Organization:         PSN-ASL06
Content View:         CV-Ubuntu-2404
Lifecycle Environment: Production
...
```

### 28.3 Verifica in All Hosts

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Cerca `test-Lorenzo-1`
3. L'host dovrebbe apparire con:
    - **Content Source**: foreman-katello-test.localdomain
    - **Lifecycle Environment**: Production
    - **Content View**: CV-Ubuntu-2404

---

## FASE 29: Configurazione Repository sulla VM

Dopo la registrazione, devi configurare la VM per usare i repository di Katello.

### 29.1 Verifica Repository Disponibili

```bash
# Sulla VM Ubuntu
subscription-manager repos --list
```

Output atteso:

```
+----------------------------------------------------------+
    Available Repositories in /etc/apt/sources.list.d/
+----------------------------------------------------------+
Repo ID:   PSN-ASL06_Ubuntu_24_04_LTS_Ubuntu_24_04_Security
Repo Name: Ubuntu 24.04 Security
Repo URL:  https://foreman-katello-test.localdomain/pulp/deb/...
Enabled:   1

Repo ID:   PSN-ASL06_Ubuntu_24_04_LTS_Ubuntu_24_04_Updates
...
```

### 29.2 Abilita i Repository (se non abilitati)

```bash
# Abilita tutti i repository disponibili
subscription-manager repos --enable='*'
```

Oppure abilita singolarmente:

```bash
subscription-manager repos \
  --enable="PSN-ASL06_Ubuntu_24_04_LTS_Ubuntu_24_04_Security" \
  --enable="PSN-ASL06_Ubuntu_24_04_LTS_Ubuntu_24_04_Updates" \
  --enable="PSN-ASL06_Ubuntu_24_04_LTS_Ubuntu_24_04_Base"
```

### 29.3 Verifica File Sources List Generato

```bash
ls -la /etc/apt/sources.list.d/
cat /etc/apt/sources.list.d/redhat.list
```

> **NOTA**: Anche per Debian/Ubuntu, subscription-manager crea un file chiamato `redhat.list` per convenzione.

### 29.4 Aggiorna Cache APT

```bash
apt update
```

---

## FASE 30: Upload Profilo Pacchetti a Katello

Per vedere i pacchetti installati nella Web UI di Foreman, devi inviare il profilo.

### 30.1 Invia Profilo Pacchetti Manualmente

```bash
# Se hai installato katello-host-tools
katello-package-upload
```

Oppure:

```bash
# Alternativa
subscription-manager facts --update
```

### 30.2 Verifica Pacchetti in Web UI

#### Via Web UI

1. Vai su **Hosts → Content Hosts → test-Lorenzo-1**
2. Clicca tab **Packages**
3. Dovresti vedere la lista dei pacchetti installati

> **NOTA**: La prima volta potrebbe richiedere qualche minuto per popolarsi.

---

## FASE 31: Configurazione SSH per Remote Execution

Anche se l'host è ora un Content Host, dobbiamo assicurarci che Remote Execution funzioni.

### 31.1 Verifica Chiave SSH già Configurata

```bash
# Sulla VM Ubuntu - verifica che la chiave Foreman sia presente
cat /root/.ssh/authorized_keys
```

Se la chiave di Foreman non è presente, segui la FASE 18 della guida originale.

### 31.2 Associa Host al Host Group (se necessario)

#### Via Web UI

1. Vai su **Hosts → All Hosts → test-Lorenzo-1**
2. Clicca **Edit**
3. In **Host Group**: seleziona `Ubuntu-2404-Groups`
4. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer host update \
  --name "test-Lorenzo-1" \
  --hostgroup "Ubuntu-2404-Groups"
```

### 31.3 Test Remote Execution

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Seleziona ☑ `test-Lorenzo-1`
3. Clicca **Select Action → Schedule Remote Job**
4. Compila:
    - **Job Category**: `Commands`
    - **Job Template**: `Run Command - Script Default`
    - **Command**: `hostname && uptime`
5. Clicca **Submit**
6. Verifica output in **Monitor → Jobs**

---

## FASE 32: Verifica Aggiornamenti Disponibili

### 32.1 Metodo 1: Via Remote Execution (Raccomandato)

#### Via Web UI

1. Vai su **Hosts → All Hosts**
2. Seleziona ☑ `test-Lorenzo-1`
3. Clicca **Select Action → Schedule Remote Job**
4. Compila:
    - **Job Category**: `Commands`
    - **Job Template**: `Run Command - Script Default`
    - **Command**:
        
        ```
        apt update && apt list --upgradable
        ```
        
5. Clicca **Submit**

#### Via Hammer CLI

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt update && apt list --upgradable" \
  --search-query "name = test-Lorenzo-1"
```

### 32.2 Metodo 2: Direttamente sulla VM

```bash
# Sulla VM Ubuntu
apt update
apt list --upgradable
```

### 32.3 Filtra Solo Security Updates

```bash
# Mostra solo aggiornamenti di sicurezza
apt list --upgradable 2>/dev/null | grep -i security
```

Oppure:

```bash
# Usa unattended-upgrades per vedere cosa verrebbe aggiornato
apt install -y unattended-upgrades
unattended-upgrade --dry-run -v
```

---

## FASE 33: Applicazione Aggiornamenti

### 33.1 Applica Tutti gli Aggiornamenti

#### Via Remote Execution (Web UI)

1. **Hosts → All Hosts → ☑ test-Lorenzo-1**
2. **Select Action → Schedule Remote Job**
3. Compila:
    - **Job Template**: `Run Command - Script Default`
    - **Command**:
        
        ```
        apt update && apt upgrade -y
        ```
        
4. **Submit**

#### Via Hammer CLI

```bash
hammer job-invocation create \
  --job-template "Run Command - Script Default" \
  --inputs "command=apt update && apt upgrade -y" \
  --search-query "name = test-Lorenzo-1"
```

### 33.2 Applica Solo Security Updates

```bash
# Via Remote Execution
# Command:
apt update && apt upgrade -y -o Dir::Etc::sourcelist="/etc/apt/sources.list.d/security.list" -o Dir::Etc::sourceparts="-"
```

Oppure usando `unattended-upgrades`:

```bash
unattended-upgrade -v
```

### 33.3 Verifica Job Completato

#### Via Web UI

1. Vai su **Monitor → Jobs**
2. Trova il job appena eseguito
3. Clicca per vedere l'output dettagliato

#### Via Hammer CLI

```bash
# Lista ultimi job
hammer job-invocation list --per-page 5

# Vedi output specifico
hammer job-invocation output --id <JOB_ID> --host "test-Lorenzo-1"
```

---

## FASE 34: Creazione Job Templates Personalizzati (Opzionale)

Per semplificare le operazioni future, crea dei Job Templates dedicati.

### 34.1 Template: Ubuntu - Check Updates

#### Via Web UI

1. Vai su **Hosts → Templates → Job Templates**
2. Clicca **Create Template**
3. Compila:
    - **Name**: `Ubuntu - Check Updates`
    - **Job Category**: `Packages`
    - **Provider Type**: `Script`
    - **Template**:

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
echo "=== AGGIORNAMENTI DISPONIBILI ==="
UPGRADABLE=$(apt list --upgradable 2>/dev/null | grep -v "Listing..." | wc -l)
echo "Totale pacchetti aggiornabili: $UPGRADABLE"

echo ""
echo "=== DETTAGLIO PACCHETTI ==="
apt list --upgradable 2>/dev/null | grep -v "Listing..."

echo ""
echo "=== SECURITY UPDATES ==="
apt list --upgradable 2>/dev/null | grep -i security || echo "Nessun security update specifico identificato"
```

4. Tab **Job**:
    - **Effective User**: `root`
5. Tab **Locations**: seleziona ☑ `Italy-North`
6. Tab **Organizations**: seleziona ☑ `PSN-ASL06`
7. Clicca **Submit**

### 34.2 Template: Ubuntu - Apply Updates

#### Via Web UI

1. **Hosts → Templates → Job Templates → Create Template**
2. Compila:
    - **Name**: `Ubuntu - Apply Updates`
    - **Job Category**: `Packages`
    - **Provider Type**: `Script`
    - **Template**:

```erb
<%#
name: Ubuntu - Apply Updates
job_category: Packages
description_format: Apply updates on %{host}
provider_type: script
kind: job_template
%>

#!/bin/bash
set -e

echo "=== Aggiornamento cache APT ==="
apt update

echo ""
echo "=== Applicazione aggiornamenti ==="
DEBIAN_FRONTEND=noninteractive apt upgrade -y

echo ""
echo "=== Pulizia pacchetti obsoleti ==="
apt autoremove -y

echo ""
echo "=== Aggiornamento completato ==="
echo "Verifica se è necessario un riavvio:"
if [ -f /var/run/reboot-required ]; then
    echo "*** RIAVVIO RICHIESTO ***"
    cat /var/run/reboot-required.pkgs 2>/dev/null || true
else
    echo "Nessun riavvio richiesto"
fi
```

3. Clicca **Submit**

### 34.3 Template: Ubuntu - Security Updates Only

```erb
<%#
name: Ubuntu - Security Updates Only
job_category: Packages
description_format: Apply security updates only on %{host}
provider_type: script
kind: job_template
%>

#!/bin/bash
set -e

echo "=== Applicazione SOLO Security Updates ==="

# Metodo 1: usando unattended-upgrades
if command -v unattended-upgrade &> /dev/null; then
    echo "Usando unattended-upgrade..."
    unattended-upgrade -v
else
    echo "Installazione unattended-upgrades..."
    apt update
    apt install -y unattended-upgrades
    unattended-upgrade -v
fi

echo ""
echo "=== Security Updates completati ==="
```

---

## FASE 35: Creazione Host Collection (Opzionale)

Le Host Collections permettono di raggruppare host per eseguire azioni bulk.

### 35.1 Crea Host Collection

#### Via Web UI

1. Vai su **Hosts → Host Collections**
2. Clicca **Create Host Collection**
3. Compila:
    - **Name**: `Ubuntu-2404-Servers`
    - **Unlimited Hosts**: ☑ abilitato
    - **Description**: `Server Ubuntu 24.04 per patch management`
4. Clicca **Save**

#### Via Hammer CLI

```bash
hammer host-collection create \
  --organization "PSN-ASL06" \
  --name "Ubuntu-2404-Servers" \
  --description "Server Ubuntu 24.04 per patch management" \
  --unlimited-hosts
```

### 35.2 Aggiungi Host alla Collection

#### Via Web UI

1. In **Host Collections → Ubuntu-2404-Servers**
2. Clicca tab **Hosts**
3. Clicca **Add**
4. Seleziona ☑ `test-Lorenzo-1`
5. Clicca **Add Selected**

#### Via Hammer CLI

```bash
hammer host-collection add-host \
  --organization "PSN-ASL06" \
  --name "Ubuntu-2404-Servers" \
  --host-ids $(hammer host info --name "test-Lorenzo-1" --fields Id | grep Id | awk '{print $2}')
```

### 35.3 Esegui Job su Host Collection

#### Via Web UI

1. Vai su **Hosts → Host Collections → Ubuntu-2404-Servers**
2. Clicca **Select Action → Schedule Remote Job**
3. Seleziona il Job Template desiderato

---

## FASE 36: Workflow Completo - Riepilogo

### Diagramma del Workflow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW PATCH MANAGEMENT UBUNTU                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │
│  │   KATELLO   │    │  CONTENT    │    │    HOST     │                  │
│  │   SERVER    │───▶│    VIEW     │───▶│  COLLECTION │                  │
│  └─────────────┘    └─────────────┘    └─────────────┘                  │
│        │                                      │                          │
│        │ Sync Plan                            │                          │
│        │ (Daily 02:00)                        │                          │
│        ▼                                      ▼                          │
│  ┌─────────────┐                      ┌─────────────┐                   │
│  │ REPOSITORY  │                      │    VM       │                   │
│  │  SECURITY   │                      │  UBUNTU     │                   │
│  │  UPDATES    │                      │             │                   │
│  └─────────────┘                      └─────────────┘                   │
│                                              │                           │
│  OPERAZIONI:                                 │                           │
│  1. Check Updates ────────────────────────▶ apt list --upgradable       │
│  2. Apply Updates ────────────────────────▶ apt upgrade -y              │
│  3. Security Only ────────────────────────▶ unattended-upgrade          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Checklist Operazioni Giornaliere

|Operazione|Frequenza|Metodo|
|---|---|---|
|Sync Repository|Automatico (Daily)|Sync Plan|
|Check Updates|Manuale/Schedulato|Remote Execution|
|Review Updates|Manuale|Web UI / CLI|
|Apply Updates (Test)|Manuale|Remote Execution|
|Apply Updates (Prod)|Manuale (dopo test)|Remote Execution|

---

## Troubleshooting

### Problema: Content Host non appare in Foreman

**Soluzione**:

```bash
# Sulla VM Ubuntu
subscription-manager unregister
subscription-manager clean
subscription-manager register --org="PSN-ASL06" --activationkey="ak-ubuntu-2404-prod"
```

### Problema: Repository non disponibili

**Soluzione**:

```bash
# Verifica subscription status
subscription-manager status

# Rigenera configurazione repository
subscription-manager refresh

# Riabilita repository
subscription-manager repos --enable='*'
```

### Problema: Errore SSL durante apt update

**Soluzione**:

```bash
# Verifica certificato CA
curl --cacert /etc/rhsm/ca/katello-server-ca.pem \
  https://foreman-katello-test.localdomain/pulp/deb/

# Se fallisce, riscarica il certificato
curl -o /etc/rhsm/ca/katello-server-ca.pem \
  https://foreman-katello-test.localdomain/pub/katello-server-ca.crt --insecure
```

### Problema: Remote Execution fallisce

**Soluzione**:

```bash
# Sul server Foreman - test connessione
ssh -i /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy root@10.172.2.5 "hostname"

# Se fallisce, verifica authorized_keys sulla VM
ssh azureuser@10.172.2.5 "sudo cat /root/.ssh/authorized_keys"
```

---

## Riferimenti

- [Katello Content Hosts Documentation](https://docs.theforeman.org/nightly/Managing_Content/index-katello.html)
- [ATIX subscription-manager for Ubuntu](https://oss.atix.de/html/ubuntu.html)
- [Foreman Remote Execution](https://docs.theforeman.org/nightly/Managing_Hosts/index-katello.html#Configuring_and_Setting_Up_Remote_Jobs_managing-hosts)