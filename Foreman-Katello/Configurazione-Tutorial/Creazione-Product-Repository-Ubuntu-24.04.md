## 1 - Creazione Product e Repository Ubuntu 24.04
### 1.1 - Crea il Product
#### Via Web UI

1. Vai su **Content → Products**
2. Clicca **Create Product**
3. Compila:
    - **Name**: `Ubuntu 24.04 LTS`
    - **Label**: `ubuntu_2404_lts` (auto-generato)
    - **GPG Key**: lascia vuoto (lo assegniamo ai singoli repository)
    - **Description**: `Repository Ubuntu 24.04 Noble Numbat per patch management - TEST`
4. Clicca **Save**

![Create Product](CreateProduct.png)
#### Via Hammer CLI

```bash
hammer product create \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --label "ubuntu_2404_lts" \
  --description "Repository Ubuntu 24.04 Noble Numbat per patch management"
```
### 1.2 - Crea Repository Security
#### Via Web UI

1. Vai su **Content → Products → Ubuntu 24.04 LTS**
2. Clicca tab **Repositories** → **New Repository**
3. Compila:
    - **Name**: `Ubuntu 24.04 Security`
    - **Label**: `ubuntu_24_04_security`
    - **Description**: `TEST`
    - **Type**: `deb`
    - **URL**: `http://security.ubuntu.com/ubuntu`
    - **Releases**: `noble-security`
    - **Components**: `main universe restricted multiverse`
    - **Architectures**: `amd64`
    - **GPG Key**: `Ubuntu Archive Key` (creato in FASE 10)
    - **Download Policy**: `On Demand`
4. Clicca **Save**

![Create Product](CreateProduct.png)

| Versione Ubuntu  | Codename            |
| ---------------- | ------------------- |
| Ubuntu 20.04 LTS | **Focal** Fossa     |
| Ubuntu 22.04 LTS | **Jammy** Jellyfish |
| Ubuntu 24.04 LTS | **Noble** Numbat    |
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
### 1.3 - Crea Repository Updates
#### Via Web UI

1. In **Content → Products → Ubuntu 24.04 LTS → Repositories**
2. Clicca **New Repository**
3. Compila: (Riporto unicamente i campi che subiscono una modifica)
    - **Name**: `Ubuntu 24.04 Updates`
    - **Label**: `ubuntu_2404_updates`
    - **URL**: `http://archive.ubuntu.com/ubuntu`
    - **Releases**: `noble-updates`
4. Clicca **Save**
### 1.4 - Crea Repository Base
#### Via Web UI

1. In **Content → Products → Ubuntu 24.04 LTS → Repositories**
2. Clicca **New Repository**
3. Compila:
    - **Name**: `Ubuntu 24.04 Base`
    - **Label**: `ubuntu_2404_base`
    - **URL**: `http://archive.ubuntu.com/ubuntu`
    - **Releases**: `noble`
    - **Components**: `main universe restricted multiverse`
4. Clicca **Save
### 1.5 - Verifica Repository Creati
#### Via Web UI

1. Vai su **Content → Products → Ubuntu 24.04 LTS → Repositories**
2. Dovresti vedere 3 repository elencati
#### Via Hammer CLI

```bash
hammer repository list --organization "PSN-ASL06" --product "Ubuntu 24.04 LTS"
```
---
## 2 - Sincronizzazione Repository
### 2.1 - Sincronizza Tutti i Repository
#### Via Web UI

1. Vai su **Content → Products → Ubuntu 24.04 LTS**
2. Seleziona tutti i repository (checkbox)
3. Clicca **Sync Now**

Oppure:

1. Vai su **Content → Sync Status**
2. Espandi **Ubuntu 24.04 LTS**
3. Seleziona i repository da sincronizzare
4. Clicca **Synchronize Now**

![Sync Status](SyncStatus.png)
#### Via Hammer CLI
##### Sync di tutto il product
```bash
hammer product synchronize \
  --organization "PSN-ASL06" \
  --name "Ubuntu 24.04 LTS" \
  --async
```

Oppure singolarmente:
##### e.g. Sync Security
```bash
hammer repository synchronize \
  --organization "PSN-ASL06" \
  --product "Ubuntu 24.04 LTS" \
  --name "Ubuntu 24.04 Security" \
  --async
```
### 2.2 Monitora Sincronizzazione
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
### 2.3 Crea Sync Plan (Sincronizzazione Automatica) - NON FATTO AL MOMENTO

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