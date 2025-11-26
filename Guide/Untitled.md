Ecco **la guida completa e aggiornata (Ubuntu 22.04/24.04)** per gestire il **patch management** con Foreman + Katello.

> ⚠️ **Nota importante**  
> Katello gestisce nativamente repository _yum/dnf_ (RHEL-based).  
> Per **Ubuntu/Debian** serve usare:
> 
> - **apt repositories** tramite la funzione _Debian/Ubuntu repo sync_ (supportata da Foreman ≥ 3.6 / Katello ≥ 4.8)
>     
> - Oppure usare **Pulp Deb plugin**, incluso nelle versioni moderne di Katello.
>     
> 
> La guida sottostante usa **Pulp Deb**, attualmente lo standard per Ubuntu.

---

# ✅ **PATCH MANAGEMENT CON FOREMAN/KATELLO SU UBUNTU 24.04 (GUIDA COMPLETA)**

---

# **1. Creare il Product per Ubuntu**

Accedi alla Web UI:

**Content → Products → Create Product**

Compila:

- **Name**: `Ubuntu-24.04`
- **Label**: automatico
- **Description**: opzionale

 **Save**

---

# **2. Creare i Repository APT**

Vai su:

**Content → Products → Ubuntu-24.04 → New Repository**

Compila:

|Campo|Valore|
|---|---|
|**Name**|`Ubuntu-24.04-Main`|
|**Type**|`deb`|
|**Upstream URL**|`http://archive.ubuntu.com/ubuntu/`|
|**Distribution**|`noble`|
|**Components**|`main restricted universe multiverse`|
|**Architectures**|`amd64`|

Clicca **Save**.

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

# **3. Sincronizzare i Repository Ubuntu**

Vai su:

**Content → Sync Status**

Seleziona i repo → **Sync Now**

Oppure CLI:

```bash
hammer repository synchronize --product "Ubuntu-24.04" --name "Ubuntu-24.04-Main"
```

---

# **4. Creare una Content View**

Vai su:

**Content → Content Views → Create New View**

Compila:

- Name: `Ubuntu-24.04-CV`
    
- Type: `Normal`
    

**Save**

### Aggiungi i repository

Tab **Repositories → Add**

Aggiungi:

- Ubuntu-24.04-Main
    
- Ubuntu-24.04-Updates
    
- Ubuntu-24.04-Security
    

### Pubblica la Content View

Vai su **Versions → Publish New Version**

Commento: “Initial Ubuntu 24.04 version”

---

# **5. Lifecycle Environment**

Se non ci sono già environment:

**Content → Lifecycle Environments → Create**

Crea ad esempio:

- Development
    
- Testing
    
- Production
    

### Promuovere la Content View

Vai su:  
**Content Views → Ubuntu-24.04-CV → Versions**

Seleziona → **Promote**

Promuovi in ordine:  
Development → Testing → Production

---

# **6. Creare l’Activation Key per Ubuntu**

Vai su:

**Content → Activation Keys → Create Activation Key**

Compila:

- Name: `ubuntu24-ak`
    
- Lifecycle Environment: `Development`
    
- Content View: `Ubuntu-24.04-CV`
    

**Save**

### Abilita i repository

Vai su tab:  
**Content → Repository Sets**

Abilita:

- Main
    
- Updates
    
- Security
    

---

# **7. Registrare il client Ubuntu 24.04 a Foreman/Katello**

Sul client Ubuntu:

## (A) Installare le chiavi CA

```bash
sudo apt install ca-certificates curl -y
curl -O http://<foreman.example.com>/pub/katello-ca-consumer-latest.deb
sudo apt install ./katello-ca-consumer-latest.deb
```

## (B) Installare il Foreman/Katello client per Debian/Ubuntu

```bash
sudo apt update
sudo apt install -y subscription-manager
```

## (C) Registrare il sistema

```bash
sudo subscription-manager register \
  --org="<YOUR_ORG>" \
  --activationkey="ubuntu24-ak"
```

## (D) Verificare i repository

```bash
apt-cache policy
```

Dovresti vedere repo come:

```
https://<foreman>/pulp/deb/<org>/<env>/ubuntu-24.04-main noble
```

---

# **8. Gestione Patch da Foreman**

Apri:

**Hosts → All Hosts → → Content**

Puoi gestire:

### ✔ Lista pacchetti

**Packages → List Installed**

### ✔ Aggiornare tutti i pacchetti

**Packages → Update All**

### ✔ Filtrare patch di sicurezza

**Errata → Security**

### ✔ Applicare patch

Seleziona → **Apply**

---

# **9. Automazione job di update**

Vai su:

**Hosts → Jobs → Run Job**

Scegli template:

- `Debian Package Update`
    
- `Debian Security Patch Install`
    
- `Apt Update + Apt Upgrade`
    

Puoi anche programmarlo:

**Schedule Recurring**

---

# **10. Flusso operativo completo (riassunto)**

1. Crea un **Product Ubuntu**
    
2. Aggiungi i **repository APT**
    
3. Sincronizza i repository
    
4. Crea una **Content View**
    
5. Pubblica e promuovi negli **environment**
    
6. Crea un **Activation Key**
    
7. Registra il client Ubuntu
    
8. Gestisci patch tramite Foreman
    

---

# Se vuoi, posso prepararti anche:

✅ Script di registrazione automatica per Ubuntu  
✅ Diagramma del flusso Katello → Ubuntu  
✅ Template per gestire patch solo di sicurezza  
✅ Guida per fare **Airgap patching** (sync offline)

Vuoi che ti generi anche lo **script di bootstrap** completo pronto all’uso?