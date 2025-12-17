**Guida per (Ubuntu 22.04/24.04)** per gestire il **patch management** con Foreman + Katello.

> ⚠️ **Nota**  
> Katello gestisce nativamente repository _yum/dnf_ (RHEL-based).  
> Per **Ubuntu/Debian** serve usare:
> 
> - **apt repositories** tramite la funzione _Debian/Ubuntu repo sync_ (supportata da Foreman ≥ 3.6 / Katello ≥ 4.8)
> - Oppure usare **Pulp Deb plugin**, incluso nelle versioni moderne di Katello.
> 
> La guida sottostante usa **Pulp Deb**, attualmente lo standard per Ubuntu.

---

# **PATCH MANAGEMENT CON FOREMAN/KATELLO SU UBUNTU 24.04**
---
# **1. Creare il Product per Ubuntu-24.04**

Accedi alla Web UI:
**Content → Products → Create Product**

![Create Product](CreateProduct.png)

Compila:

- **Name**: `Ubuntu-24.04`
- **Label**: automatico
- **Description**: opzionale

 **Save**

---
# **2. Creare i Repository APT**

Vai su:
**Content → Products → Ubuntu-24.04 → New Repository**

![Create Product](CreateProduct.png)
Compila:

|Campo|Valore|
|---|---|
|**Name**|`Ubuntu-24.04-Main`|
|**Type**|`deb`|
|**Upstream URL**|`http://archive.ubuntu.com/ubuntu/`|
|**Distribution**|`noble`|
|**Components**|`main restricted universe multiverse`|
|**Architectures**|`amd64`|
**Save**.

Ripeti per gli altri repository:
### Repository Updates
- **Name**: `Ubuntu-24.04-Updates`
- URL: `http://archive.ubuntu.com/ubuntu/`
- Distribution: `noble-updates`
- Components: `main restricted universe multiverse`
### Repository Security
- **Name**: `Ubuntu-24.04-Security`
- URL: `http://security.ubuntu.com/ubuntu/`
- Distribution: `noble-security`
- Components: `main restricted universe multiverse`
---
# **3. Sincronizzare i Repository**
Vai su:
**Content → Sync Status**
Seleziona i repo → **Sync Now**

![Sync Status](SyncStatus.png)

---
# **4. Creare una Content View**

Vai su:
**Content → Lifecycle → Content Views → Create New View**

![Create Content View](CreateContentView.png)
Compila:
- Name: `Ubuntu-24.04-CV`
- Type: `Normal`

**Save**

# **Aggiungi i repository**
![img](img14.png)

**Repositories → Add**

Aggiungi:

- Ubuntu-24.04-Main
- Ubuntu-24.04-Updates
- Ubuntu-24.04-Security

# Pubblica la Content View

Vai su **Versions → Publish New Version**

![Publish New Version](PublishNewVersion.png)

Commento: “Initial Ubuntu 24.04 version”

---

# **5. Lifecycle Environment**

Se non ci sono già environment:

**Content → Lifecycle Environments → Create Environment Path**

![Create Environment Path][../img/CreateEnvironmentPath.png]
Crea ad esempio:

- Development
- Testing
- Production

### Promuovere la Content View

Vai su:  
**Content Views → Ubuntu-24.04-CV → Versions**

![](img5.png)
![](img15.png)

Seleziona → **Promote**

![](img16.png)
Promuovi in ordine:  
Development → Testing → Production

---
# **Aggiungere un nuovo OS**
Vai su:  
**Hosts → Provisioning Setup → Operating Systems**
Seleziona → **Create Operating System**

![](img17.png)

- Name : Ubuntu
- Major Version : 24
- Minor Version : 04
- Description : ubuntu 24.04
- Family : Debian
- Release Name : noble-security
- Root Password Hash : SHA512
 - Architectures : x86_64

![](img18.png)


---
![[png2.png]]