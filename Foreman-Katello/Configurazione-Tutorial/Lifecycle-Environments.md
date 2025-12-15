## 1 - Lifecycle Environments
### 1.1 - Crea Ambiente Development
#### Via Web UI

1. Vai su **Content → Lifecycle → Lifecycle Environments**
2. Clicca **Create Environment Path**
3. Compila:
    - **Name**: `Development`
    - **Label**: `development`
    - **Description**: `Ambiente di sviluppo e test`
4. Clicca **Save**

![Create Environment Path](CreateEnvironmentPath.png)
#### Via Hammer CLI

```bash
hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Development" \
  --label "development" \
  --prior "Library" \
  --description "Ambiente di sviluppo e test"
```
### 1.2 - Aggiungi Ambiente Test
#### Via Web UI

1. In **Lifecycle Environments**, clicca su **Add New Environment** dopo "Test"
2. Compila:
    - **Name**: `Test`
    - **Label**: `test`
    - **Description**: `Ambiente di test pre-produzione`
3. Clicca **Save**

![](AddEnvironmentPath.png)
#### Via Hammer CLI

```bash
hammer lifecycle-environment create \
  --organization "PSN-ASL06" \
  --name "Test" \
  --label "test" \
  --prior "Development" \
  --description "Ambiente di staging pre-produzione"
```
### 1.3 - Aggiungi Ambiente Production
#### Via Web UI

1. In **Lifecycle Environments**, clicca su **Add New Environment** dopo "Staging"
2. Compila:
    - **Name**: `Production`
    - **Label**: `production`
    - **Description**: `Ambiente di produzione`
3. Clicca **Save**
### 1.4 - Verifica Lifecycle Path
#### Via Web UI

Vai su **Content → Lifecycle → Lifecycle Environments**
#### Via Hammer CLI

```bash
hammer lifecycle-environment paths --organization "PSN-ASL06"
```
Output atteso :

![](Image16-v2.png)
