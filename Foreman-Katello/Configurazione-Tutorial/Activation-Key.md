## 1 - Activation Key
### 1.1 - Crea Activation Key
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

![Activation Keys](ActivationKeys.png)

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
### 1.2 - Verifica Activation Key
#### Via Web UI

In **Activation Keys** dovresti vedere `ak-ubuntu-2404-prod`

#### Via Hammer CLI

```bash
hammer activation-key info \
  --organization "PSN-ASL06" \
  --name "ak-ubuntu-2404-prod"
```
