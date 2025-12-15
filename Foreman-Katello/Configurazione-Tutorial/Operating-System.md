## 1 - Operating System
### 1.1 - Verifica OS Esistenti
#### Via Web UI

1. Vai su **Hosts → Provisioning Setup → Operating Systems**
2. Cerca se esiste già "Ubuntu 24.04"

#### Via Hammer CLI

```bash
hammer os list | grep -i ubuntu
```
### 1.2 - Crea Operating System (se non esiste)
#### Via Web UI

1. Vai su **Hosts → Provisioning Setup → Operating Systems**
2. Clicca **Create Operating System**
3. Compila:
    - **Name**: `Ubuntu`
    - **Major Version**: `24`
    - **Minor Version**: `04`
    - **Family**: `Debian`
    - **Release Name**: `noble`
4. Tab **Architectures**: seleziona ☑ `x86_64`
5. Clicca **Submit**

![](img17.png)
![](img18.png)

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
### 1.3 - Verifica Operating System
#### Via Web UI

In **Operating Systems** dovresti vedere `Ubuntu 24.04`

#### Via Hammer CLI

```bash
hammer os info --title "Ubuntu 24.04"
```
