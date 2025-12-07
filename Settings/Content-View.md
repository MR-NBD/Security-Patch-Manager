## 1 - Content View
### 1.1 - Crea Content View
#### Via Web UI

1. Vai su **Content → Lifecycle → Content Views**
2. Clicca **Create Content View**
3. Compila:
    - **Name**: `CV-Ubuntu-2404`
    - **Label**: `cv_ubuntu_2404`
    - **Description**: `Content View per Ubuntu 24.04 LTS`
    - **Type**: `Content View` (non Composite)
4. Clicca **Create Content View**

> NOTA SUL FLAG : Solve Dependencies
### ==Solve Dependencies==
Il flag **"Solve dependencies"** serve a risolvere automaticamente le dipendenze dei pacchetti quando pubblichi la Content View.
#### Cosa fa

| Stato              | Comportamento                                                            |
| ------------------ | ------------------------------------------------------------------------ |
| ☐ **Disabilitato** | Include solo i pacchetti esplicitamente presenti nei repository aggiunti |
| ☑ **Abilitato**    | Include automaticamente anche tutti i pacchetti dipendenza necessari     |
#### Esempio pratico
Se vuoi installare `nginx` che dipende da `libssl`, `libpcre`, ecc:
- **Senza Solve Dependencies**: potresti avere `nginx` ma non le sue dipendenze → installazione fallisce
- **Con Solve Dependencies**: Katello include automaticamente tutte le dipendenze → installazione OK
#### Quando usarlo

| Scenario | Raccomandazione |
|----------|-----------------|
| Repository completi (mirror full) | ☐ Non necessario |
| Repository filtrati (solo alcuni pacchetti) | ☑ **Raccomandato** |
| Content View con filtri specifici | ☑ **Raccomandato** |
In Questa fase di TEST verrà lasciata vuota **in futuro con l'applicazione di filtri sarà necessaria**.

#### Crea Content View via Hammer CLI
```bash
hammer content-view create \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --label "cv_ubuntu_2404" \
  --description "Content View per Ubuntu 24.04 LTS"
```
### 1.2 - Aggiungi Repository alla Content View
#### Via Web UI

1. In **Content Views → CV-Ubuntu-2404**
2. Vai tab **Repositories**
3. Clicca **Add Repositories** or **Show repositories**
4. Seleziona tutti e 3 i repository:
    - ☑ Ubuntu 24.04 Security
    - ☑ Ubuntu 24.04 Updates
    - ☑ Ubuntu 24.04 Base
5. Clicca **Add Repositories**

![](../img/img14.png)
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
### 1.3 - Pubblica Content View
#### Via Web UI

1. In **Content Views → CV-Ubuntu-2404**
2. Clicca **Publish New Version**
3. Compila:
    - **Description**: `Initial publish`
4. Clicca **Publish**
5. Attendi il completamento

![Publish New Version](../img/PublishNewVersion.png)
#### Via Hammer CLI

```bash
hammer content-view publish \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404" \
  --description "Initial publish"
```
### 1.4 - Promuovi Content View a Development
#### Via Web UI

1. In **Content Views → CV-Ubuntu-2404 → Versions**
2. Trova la versione 1.0
3. Clicca sul menu **⋮** → **Promote**
4. Seleziona ☑ **Development**
5. Clicca **Promote**

Ripeti il processo di promozione per ogni ambiente:

6. **Versions → ⋮ → Promote → Staging → Promote**
7. **Versions → ⋮ → Promote → Production → Promote**

![](../img/img5.png)
![](../img/img15.png)
![](../img/img16.png)

#### Via Hammer CLI

```bash
hammer content-view version promote \
  --organization "PSN-ASL06" \
  --content-view "CV-Ubuntu-2404" \
  --to-lifecycle-environment "Development"
```
### 1.5 - Verifica Content View
#### Via Web UI
In **Content Views → CV-Ubuntu-2404 → Versions** dovresti vedere la versione presente in tutti gli ambienti.

#### Via Hammer CLI

```bash
hammer content-view info \
  --organization "PSN-ASL06" \
  --name "CV-Ubuntu-2404"
```