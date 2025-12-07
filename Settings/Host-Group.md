## 1 - Host Group

> NOTA : **Differenza TRA** Host Groups e Host Collections

|Concetto|Posizione|Scopo|
|---|---|---|
|**Host Groups**|**Configure → Host Groups**|Configurazioni comuni (OS, Content View, Lifecycle, parametri)|
|**Host Collections**|Hosts → Host Collections|Raggruppamento per azioni bulk (errata, pacchetti)|
#### Quando usare Host Collections?
Le Host Collections sono utili **dopo** aver registrato gli host, per:

- Applicare errata a gruppi di host
- Installare/rimuovere pacchetti in bulk
- Azioni di content management
### 1.2 - Crea Host Group
#### Via Web UI

1. Vai su **Configure → Host Groups**
2. Clicca **Create Host Group**
3. Tab **Host Group**:
    - **Name**: `Ubuntu-2404-Groups`
    - **Description**: `Groups Ubuntu 24.04 LTS`
    - **Lifecycle Environment**: `Production`
    - **Content View**: `CV-Ubuntu-2404`
    - **Content Source**: `foreman-katello-test.localdomain`
4. Tab **Operating System**:
    - **Operating System**: `Ubuntu 24.04`
    - **Architecture**: `x86_64`
5. Tab **Locations**: seleziona ☑ `Italy-North`
6. Tab **Organizations**: seleziona ☑ `PSN-ASL06`
7. Clicca **Submit**

![Create Host Groups](../img/CreateHostGroup.png)
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
### 1.2 - Configura Parametri SSH per Host Group
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
