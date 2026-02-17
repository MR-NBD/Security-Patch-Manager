Questa guida descrive la configurazione completa di UYUNI per gestire client **Ubuntu 24.04 LTS (Noble Numbat)** in un ambiente enterprise con:

- Importazione chiavi GPG Ubuntu
- Creazione canali software
- Sincronizzazione repository
- Content Lifecycle Management (promozione Dev → Prod)
- System Groups per organizzare i client
- Activation Keys per registrazione automatizzata
- Registrazione client Ubuntu
- Preparazione al Patch Management
---
## 1. Prerequisiti e Problemi Noti
### 1.1 Prerequisiti

Prima di iniziare, assicurarsi che:
- Spazio disco sufficiente su `/manager_storage` (minimo 200GB consigliati per Ubuntu)
- Connettività verso archive.ubuntu.com e security.ubuntu.com

### 1.2 Problematiche Noti e Soluzioni
Problematiche riscontrate durante la procedura di configurazione:
#### Problematica 1: spacewalk-common-channels richiede TTY
- **Problema**: Eseguendo `mgrctl exec -- spacewalk-common-channels` senza credenziali, si ottiene errore "OSError: No such device or address: '/dev/tty'"
- **Causa**: Il comando cerca di chiedere la password interattivamente, ma dentro il container non c'è un terminale.
- **Soluzione**: Specificare **sempre** le credenziali con `-u` e `-p`:

```bash
mgrctl exec -- spacewalk-common-channels -u admin -p 'PASSWORD' <canali>
```

#### Problematica 2: Web UI mostra solo Repository Type "yum"
- **Problema**: Nella creazione manuale repository, il dropdown mostra solo "yum", non "deb".
- **Causa**: La Web UI ha limitazioni per i repository deb.
- **Soluzione**: Usare `spacewalk-common-channels` che crea automaticamente canali e repository con tipo corretto.

#### Problematica 3: Nome Bootstrap Repository diverso
- **Problema**: `mgr-create-bootstrap-repo --create ubuntu-2404-amd64` restituisce "'ubuntu-2404-amd64' not found"
- **Causa**: Il nome del bootstrap usa il punto nel numero versione.
- **Soluzione**: Usare il comando `--list` per trovare il nome esatto:

```bash
mgrctl exec -- mgr-create-bootstrap-repo --list
# Output: ubuntu-24.04-amd64-uyuni

mgrctl exec -- mgr-create-bootstrap-repo --create ubuntu-24.04-amd64-uyuni
```

---
## FASE 1: Importazione Chiavi GPG
### 1.1 Informazioni sulle Chiavi GPG Ubuntu
Ubuntu utilizza questa chiave principale per firmare i pacchetti:

| Chiave | Key ID | Fingerprint |
|--------|--------|-------------|
| Ubuntu Archive (2018) | `871920D1991BC93C` | `F6ECB3762474EDA9D21B7022871920D1991BC93C` |
### 1.2 Scarica e Importa la Chiave GPG

```bash
# Crea directory temporanea
mkdir -p /tmp/ubuntu-gpg-keys && cd /tmp/ubuntu-gpg-keys

# Scarica la chiave Ubuntu Archive
curl -sS "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C" -o ubuntu-archive.asc

# Importa nel keyring UYUNI
mgradm gpg add /tmp/ubuntu-gpg-keys/ubuntu-archive.asc
# Conferma con 'y' quando richiesto
```

**Output atteso**:
```
gpg: key 871920D1991BC93C: public key "Ubuntu Archive Automatic Signing Key (2018) <ftpmaster@ubuntu.com>" imported
gpg: Total number processed: 1
gpg:               imported: 1
```

---
## FASE 2: Creazione Canali Software
### 2.1 Struttura Canali Ubuntu
UYUNI organizza i canali in una struttura gerarchica:

```
ubuntu-2404-pool-amd64-uyuni              ← CANALE PADRE (Base)
├── ubuntu-2404-amd64-main-uyuni           ← Child: pacchetti main
├── ubuntu-2404-amd64-main-updates-uyuni   ← Child: aggiornamenti
├── ubuntu-2404-amd64-main-security-uyuni  ← Child: patch sicurezza
└── ubuntu-2404-amd64-uyuni-client         ← Child: tool UYUNI client
```

**Canale Padre**: Base del sistema operativo. Ogni client ha 1 solo canale padre.
**Canale Figlio**: Add-on (updates, security, tools). Un client può avere N canali figli.

### 2.2 Crea i Canali con spacewalk-common-channels

```bash
# Crea tutti i canali Ubuntu 24.04 in un unico comando
mgrctl exec -- spacewalk-common-channels \
  -u admin -p 'TUA_PASSWORD' \
  ubuntu-2404-pool-amd64-uyuni \
  ubuntu-2404-amd64-main-uyuni \
  ubuntu-2404-amd64-main-updates-uyuni \
  ubuntu-2404-amd64-main-security-uyuni \
  ubuntu-2404-amd64-uyuni-client
```

### 2.3 Verifica Creazione Canali
**Via CLI**:
```bash
mgrctl exec -- spacecmd -u admin -p 'password' softwarechannel_list | grep ubuntu
```

**Via Web UI**:
1. **Software** → **Manage** → **Channels**
2. Verifica presenza dei 5 canali Ubuntu

---
## FASE 3: Configurazione GPG nei Canali

Dopo l'importazione della chiave nel keyring, configurare i riferimenti GPG in ogni canale per la verifica sui client.
### 3.1 Configura GPG nel Canale Padre

1. **Software** → **Manage** → **Channels**
2. Clicca su **Ubuntu 24.04 LTS AMD64 Base for Uyuni**
3. Clicca **Modifica** (Edit Channel)
4. Sezione **Security: GPG**, compila:

| Campo | Valore |
|-------|--------|
| **URL della chiave GPG** | `https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C` |
| **ID della chiave GPG** | `871920D1991BC93C` |
| **GPG key Fingerprint** | `F6ECB3762474EDA9D21B7022871920D1991BC93C` |

5. Clicca **Aggiorna Canale**

### 3.2 Ripeti per i Canali Child

Applica la stessa configurazione GPG a:
- ubuntu-2404-amd64-main-uyuni
- ubuntu-2404-amd64-main-updates-uyuni
- ubuntu-2404-amd64-main-security-uyuni
- ubuntu-2404-amd64-uyuni-client

> Tutti i canali Ubuntu usano la stessa chiave GPG.

---
## FASE 4: Sincronizzazione Repository
### 4.1 Avvia Sincronizzazione
La sincronizzazione parte automaticamente alla creazione dei canali. Per avviarla manualmente:

**Via CLI** (tutti i child in parallelo):
```bash
mgrctl exec -- spacewalk-repo-sync -p ubuntu-2404-pool-amd64-uyuni
```

**Via Web UI**:
1. **Software** → **Manage** → **Channels**
2. Clicca sul canale child (es. ubuntu-2404-amd64-main-uyuni)
3. Tab **Repositories** → **Sync** → **Sync Now**
### 4.2 Monitora Progresso

```bash
# Verifica processi sync attivi
mgrctl exec -- ps aux | grep spacewalk-repo-sync

# Lista log disponibili
mgrctl exec -- ls -la /var/log/rhn/reposync/

# Monitora log in tempo reale (Ctrl+C per uscire)
mgrctl exec -ti -- tail -f /var/log/rhn/reposync/ubuntu-2404-amd64-main-uyuni.log

# Verifica ultime righe di un log
mgrctl exec -- tail -20 /var/log/rhn/reposync/ubuntu-2404-amd64-main-security-uyuni.log
```

### 4.3 Tempistiche Attese

> **ATTENZIONE**: La prima sincronizzazione richiede **diverse ore** e spazio disco significativo (~150-200GB). Monitorare `/manager_storage` per evitare esaurimento spazio.

### 4.4 Verifica Completamento

```bash
# Conta pacchetti in un canale (dopo sync completa)
mgrctl exec -- spacecmd -u admin -p 'password' -- softwarechannel_listallpackages ubuntu-2404-amd64-main-uyuni | wc -l
```

---
## FASE 5: Bootstrap Repository

Il Bootstrap Repository contiene i pacchetti minimi necessari per la prima registrazione di un client (salt-minion, uyuni-client-tools).

### 5.1 Genera Bootstrap Repository

```bash
# Verifica nome corretto
mgrctl exec -- mgr-create-bootstrap-repo --list
# Output: ubuntu-24.04-amd64-uyuni

# Crea bootstrap repository
mgrctl exec -- mgr-create-bootstrap-repo --create ubuntu-24.04-amd64-uyuni
```

### 5.2 Verifica Bootstrap Repository

```bash
mgrctl exec -- ls -la /srv/www/htdocs/pub/repositories/
```

**Output atteso**:
```
drwxr-xr-x 3 root root 16 Dec 17 17:29 ubuntu
```

---

## FASE 6: Content Lifecycle Management (CLM)

Il Content Lifecycle Management permette di gestire la promozione dei contenuti attraverso ambienti (Dev → Test → Prod).
### 6.1 Concetti Chiave

| Termine | Descrizione |
|---------|-------------|
| **Project** | Contenitore che definisce i canali sorgente e gli ambienti |
| **Environment** | Stadio nel ciclo di vita (es. dev, test, prod) |
| **Filter** | Regole per includere/escludere pacchetti o patch |
| **Build** | Snapshot dei contenuti in un momento specifico |

### 6.2 Crea un Progetto CLM
**Via Web UI**:

1. **Content Lifecycle** → **Projects** → **Create Project**
2. Compila:

| Campo           | Valore                                  |
| --------------- | --------------------------------------- |
| **Name**        | Ubuntu-24.04-Lifecycle                  |
| **Label**       | ubuntu-2404-lifecycle                   |
| **Description** | Gestione ciclo di vita Ubuntu 24.04 LTS |

3. Clicca **Create**

### 6.3 Aggiungi Canali Sorgente
1. Nel progetto appena creato, sezione **Sources**
2. Clicca **Attach/Detach Sources**
3. Seleziona:
   -  ubuntu-2404-pool-amd64-uyuni
   -  ubuntu-2404-amd64-main-uyuni
   -  ubuntu-2404-amd64-main-updates-uyuni
   -  ubuntu-2404-amd64-main-security-uyuni
   -  ubuntu-2404-amd64-uyuni-client
1. Clicca **Save**

### 6.4 Crea gli Ambienti
Crea gli ambienti in ordine di promozione:

**Ambiente 1: TEST**
1. Sezione **Environments** → **Add Environment**
2. Compila:

| Campo           | Valore                          |
| --------------- | ------------------------------- |
| **Name**        | test                            |
| **Label**       | test                            |
| **Description** | Ambiente sviluppo/test iniziale |

3. Clicca **Save**

**Ambiente 2: PROD**
1. **Add Environment**
2. Compila:

| Campo             | Valore                  |
| ----------------- | ----------------------- |
| **Name**          | prod                    |
| **Label**         | prod                    |
| **Description**   | Ambiente produzione     |
| **Insert before** | (vuoto - sarà l'ultimo) |

3. Clicca **Save**

### 6.5 Crea Filtri (Opzionale)
I filtri permettono di controllare quali pacchetti vengono promossi.

**Esempio: Filtro per escludere pacchetti specifici**

1. **Content Lifecycle** → **Filters** → **Create Filter**
2. Compila:

| Campo | Valore |
|-------|--------|
| **Filter Name** | exclude-debug-packages |
| **Filter Type** | Package (Name) |
| **Matcher** | contains |
| **Package Name** | -dbg |
| **Rule** | Deny |

3. Clicca **Save**
4. Associa il filtro al progetto: **Projects** → **Ubuntu-24.04-Lifecycle** → **Filters** → **Attach Filter**

### 6.6 Costruisci la Prima Versione

1. **Content Lifecycle** → **Projects** → **Ubuntu-24.04-Lifecycle**
2. Clicca **Build** (in alto a destra)
3. Inserisci un **Version Message** (es. "Initial build 2024-12")
4. Clicca **Build**

Questo crea canali clonati per ogni ambiente:
```
ubuntu-2404-pool-amd64-uyuni-dev-ubuntu-2404-lifecycle
ubuntu-2404-pool-amd64-uyuni-prod-ubuntu-2404-lifecycle
```

### 6.7 Promozione tra Ambienti
Per promuovere contenuti da DEV a PROD:

1. **Content Lifecycle** → **Projects** → **Ubuntu-24.04-Lifecycle**
2. Nella riga dell'ambiente **prod**, clicca **Promote**
3. Seleziona la versione da promuovere
4. Clicca **Promote**

---
## FASE 7: System Groups

I System Groups permettono di organizzare i client per ambiente, funzione o location.

### 7.1 Struttura Consigliata
Per un ambiente con macchine Test e Produzione:

```
System Groups
├── Ubuntu-24.04-Test
│   └── vm-ubuntu-test01
└── Ubuntu-24.04-Prod
    └── vm-ubuntu-prod01
```

### 7.2 Crea System Groups
**Via Web UI**:

1. **Systems** → **System Groups** → **Create Group**
2. Crea gruppo TEST:

| Campo           | Valore                            |
| --------------- | --------------------------------- |
| **Name**        | Ubuntu-24.04-Test                 |
| **Description** | Client Ubuntu 24.04 ambiente Test |

3. Clicca **Create Group**
4. Ripeti per PROD:

| Campo           | Valore                                  |
| --------------- | --------------------------------------- |
| **Name**        | Ubuntu-24.04-Prod                       |
| **Description** | Client Ubuntu 24.04 ambiente Produzione |

### 7.3 Associa System Group a Canali CLM
Dopo aver creato i gruppi, puoi configurare l'associazione automatica:

1. **Systems** → **System Groups** → **Ubuntu-24.04-Test**
2. Tab **Target Systems** (dopo registrazione client)
3. Seleziona i sistemi da aggiungere al gruppo

> **Nota**: L'associazione può anche essere fatta automaticamente tramite Activation Key.

---
## FASE 8: Activation Keys

Le Activation Keys automatizzano la configurazione dei client durante la registrazione.
### 8.1 Crea Activation Key per TEST
1. **Systems** → **Activation Keys** → **Create Key**
2. Compila:

| Campo                   | Valore                                                 |
| ----------------------- | ------------------------------------------------------ |
| **Description**         | Ubuntu 24.04 - Ambiente Test                           |
| **Key**                 | ubuntu-2404-test                                       |
| **Usage Limit**         | (vuoto per illimitato)                                 |
| **Base Channel**        | ubuntu-2404-pool-amd64-uyuni-dev-ubuntu-2404-lifecycle |
| **Add-on Entitlements** | ☑ Monitoring (opzionale)                               |
| **Contact Method**      | Default                                                |
| **Universal Default**   | ☐ No                                                   |

3. Clicca **Create Activation Key**

4. Tab **Child Channels**, seleziona tutti i child dell'ambiente dev:
   - ubuntu-2404-amd64-main-uyuni-dev-ubuntu-2404-lifecycle
   - ubuntu-2404-amd64-main-updates-uyuni-dev-ubuntu-2404-lifecycle
   - ubuntu-2404-amd64-main-security-uyuni-dev-ubuntu-2404-lifecycle
   - ubuntu-2404-amd64-uyuni-client-dev-ubuntu-2404-lifecycle

3. Tab **Groups** → seleziona **Ubuntu-24.04-Test**
4. Clicca **Update Key**

### 8.2 Crea Activation Key per PROD
Ripeti il processo con:

| Campo            | Valore                                                  |
| ---------------- | ------------------------------------------------------- |
| **Description**  | Ubuntu 24.04 - Ambiente Produzione                      |
| **Key**          | ubuntu-2404-prod                                        |
| **Base Channel** | ubuntu-2404-pool-amd64-uyuni-prod-ubuntu-2404-lifecycle |

E associa al gruppo **Ubuntu-24.04-Prod**.
### 8.3 Riepilogo Activation Keys

| Key | Ambiente CLM | System Group | Uso |
|-----|--------------|--------------|-----|
| ubuntu-2404-test | dev | Ubuntu-24.04-Test | Macchine test |
| ubuntu-2404-prod | prod | Ubuntu-24.04-Prod | Macchine produzione |

---
## FASE 9: Registrazione Client Ubuntu
### 9.1 Prerequisiti sul Client

Sul client Ubuntu 24.04, verificare:

```bash
# Verifica connettività verso UYUNI server
ping uyuni-server-test.uyuni.internal

# Se DNS non risolve, aggiungere entry in /etc/hosts
echo "10.172.2.5 uyuni-server-test.uyuni.internal" | sudo tee -a /etc/hosts

# Verifica porte aperte (dal client)
nc -zv uyuni-server-test.uyuni.internal 443
nc -zv uyuni-server-test.uyuni.internal 4505
nc -zv uyuni-server-test.uyuni.internal 4506
```

### 9.2 Metodo 1: Bootstrap Script (Consigliato)
**Sul server UYUNI**, genera lo script di bootstrap:

1. **Systems** → **Bootstrapping**
2. Compila:

| Campo | Valore |
|-------|--------|
| **Host** | FQDN o IP del client (es. ubuntu-test01.domain.local) |
| **SSH Port** | 22 |
| **User** | root (o utente con sudo) |
| **Authentication** | Password o SSH Key |
| **Activation Key** | ubuntu-2404-test |

3. Clicca **Bootstrap**

**Oppure, sul client Ubuntu**:

```bash
# Scarica ed esegui bootstrap script
curl -Sks https://uyuni-server-test.uyuni.internal/pub/bootstrap/bootstrap.sh | sudo bash
```

Dopo il bootstrap, configurare l'activation key:
- Sul server UYUNI, accettare il minion e assegna activation key
- Via Web UI: **Salt** → **Keys** → **Accept**

### 9.3 Metodo 2: Registrazione Manuale

**Sul client Ubuntu**:

```bash
# 1. Aggiungi repository UYUNI client tools
echo "deb [trusted=yes] https://uyuni-server-test.uyuni.internal/pub/repositories/ubuntu/24/04/0/bootstrap main" | sudo tee /etc/apt/sources.list.d/uyuni.list

# 2. Importa certificato CA del server UYUNI
sudo curl -Sks https://uyuni-server-test.uyuni.internal/pub/RHN-ORG-TRUSTED-SSL-CERT -o /usr/local/share/ca-certificates/uyuni-ca.crt
sudo update-ca-certificates

# 3. Aggiorna e installa salt-minion
sudo apt update
sudo apt install -y venv-salt-minion

# 4. Configura salt-minion
sudo tee /etc/venv-salt-minion/minion.d/uyuni.conf << 'EOF'
master: uyuni-server-test.uyuni.internal
grains:
  susemanager:
    activation_key: ubuntu-2404-test
EOF

# 5. Abilita e avvia salt-minion
sudo systemctl enable --now venv-salt-minion

# 6. Verifica connessione
sudo systemctl status venv-salt-minion
```

### 9.4 Accetta il Client sul Server

**Via Web UI**:
1. **Salt** → **Keys** (o **Systems** → **Activation Keys**)
2. Trova il client nella lista "Pending"
3. Clicca **Accept**

**Via CLI**:
```bash
# Lista minion in attesa
mgrctl exec -- salt-key -L

# Accetta un minion specifico
mgrctl exec -- salt-key -a ubuntu-test01.domain.local

# Accetta tutti i minion in attesa
mgrctl exec -- salt-key -A
```

### 9.5 Verifica Registrazione

**Via Web UI**:
1. **Systems** → **Systems List** → **All**
2. Verifica che il client sia presente e nello stato corretto

**Via CLI**:
```bash
# Verifica comunicazione Salt
mgrctl exec -- salt 'ubuntu-test01*' test.ping

# Verifica info sistema
mgrctl exec -- salt 'ubuntu-test01*' grains.items
```

---

## FASE 10: Preparazione Patch Management

### 10.1 Workflow Patch Management

Il flusso di patch management con CLM:

```
1. Sync repository (automatica o schedulata)
         ↓
2. Nuovo contenuto appare nei canali sorgente
         ↓
3. Build nuovo snapshot CLM
         ↓
4. Test in ambiente DEV
         ↓
5. Promozione a PROD
         ↓
6. Applicazione patch ai client
```

### 10.2 Configura Sync Schedulata

1. **Admin** → **Task Schedules**
2. Trova **channel-repodata-default**
3. Configura frequenza (es. giornaliera alle 02:00)

### 10.3 Verifica Errata/Advisory

> UYUNI/SUSE Manager non hanno supporto nativo per Ubuntu Security Notices (USN) come per RHEL/SUSE. I pacchetti vengono sincronizzati, ma gli errata devono essere gestiti diversamente.

Per visualizzare pacchetti con aggiornamenti disponibili:

1. **Systems** → clicca sul client
2. Tab **Software** → **Packages** → **Upgrade**

### 10.4 Applicare Aggiornamenti

**Singolo Sistema**:
1. **Systems** → seleziona sistema
2. **Software** → **Packages** → **Upgrade**
3. Seleziona pacchetti → **Upgrade Packages**

**System Group**:
1. **Systems** → **System Groups** → **Ubuntu-24.04-Test**
2. Tab **Target Systems** → seleziona tutti
3. **System Set Manager** → **Packages** → **Upgrade**

**Via Salt (CLI)**:
```bash
# Verifica aggiornamenti disponibili
mgrctl exec -- salt 'ubuntu-test01*' pkg.list_upgrades

# Applica tutti gli aggiornamenti
mgrctl exec -- salt 'ubuntu-test01*' pkg.upgrade

# Applica pacchetto specifico
mgrctl exec -- salt 'ubuntu-test01*' pkg.install 'nome-pacchetto'
```

### 10.5 Reboot Schedulato (se necessario)

```bash
# Via Salt - reboot immediato
mgrctl exec -- salt 'ubuntu-test01*' system.reboot

# Via Salt - reboot schedulato (in 5 minuti)
mgrctl exec -- salt 'ubuntu-test01*' cmd.run 'shutdown -r +5'
```

---
## Troubleshooting
### Sync fallisce o si blocca

```bash
# Verifica spazio disco
df -h /manager_storage

# Verifica processi sync
mgrctl exec -- ps aux | grep spacewalk-repo-sync

# Kill processo bloccato
mgrctl exec -- pkill -f spacewalk-repo-sync

# Riavvia sync
mgrctl exec -- spacewalk-repo-sync -c ubuntu-2404-amd64-main-uyuni
```

### Client non si registra

```bash
# Sul client, verifica log salt-minion
sudo journalctl -u venv-salt-minion -f

# Verifica che il server sia raggiungibile
nc -zv uyuni-server.domain 4505
nc -zv uyuni-server.domain 4506

# Sul server, verifica chiavi pending
mgrctl exec -- salt-key -L
```

---
## Quick Reference

### Comandi Creazione Canali

```bash
# Crea tutti i canali Ubuntu 24.04
mgrctl exec -- spacewalk-common-channels \
  -u admin -p 'password' \
  ubuntu-2404-pool-amd64-uyuni \
  ubuntu-2404-amd64-main-uyuni \
  ubuntu-2404-amd64-main-updates-uyuni \
  ubuntu-2404-amd64-main-security-uyuni \
  ubuntu-2404-amd64-uyuni-client
```

### Comandi Sincronizzazione

```bash
# Sync tutti i child
mgrctl exec -- spacewalk-repo-sync -p ubuntu-2404-pool-amd64-uyuni

# Sync singolo canale
mgrctl exec -- spacewalk-repo-sync -c ubuntu-2404-amd64-main-uyuni

# Monitora sync
mgrctl exec -ti -- tail -f /var/log/rhn/reposync/ubuntu-2404-amd64-main-uyuni.log
```

### Comandi Bootstrap

```bash
# Lista nomi disponibili
mgrctl exec -- mgr-create-bootstrap-repo --list

# Crea bootstrap repo
mgrctl exec -- mgr-create-bootstrap-repo --create ubuntu-24.04-amd64-uyuni
```

### Comandi Client Management

```bash
# Lista minion
mgrctl exec -- salt-key -L

# Accetta minion
mgrctl exec -- salt-key -a <hostname>

# Test connessione
mgrctl exec -- salt '<hostname>*' test.ping

# Lista aggiornamenti
mgrctl exec -- salt '<hostname>*' pkg.list_upgrades

# Applica aggiornamenti
mgrctl exec -- salt '<hostname>*' pkg.upgrade
```

### Comandi Verifica Sistema

```bash
# Status container
mgradm status

# Spazio disco
df -h /manager_storage /pgsql_storage

# Verifica canali
mgrctl exec -- spacecmd -u admin -p 'PASSWORD' softwarechannel_list

# Verifica repository
mgrctl exec -- spacecmd -u admin -p 'PASSWORD' repo_list
```

---

## Struttura Finale

Dopo la configurazione completa avrai:

### Canali Sorgente
```
ubuntu-2404-pool-amd64-uyuni (Parent)
├── ubuntu-2404-amd64-main-uyuni
├── ubuntu-2404-amd64-main-updates-uyuni
├── ubuntu-2404-amd64-main-security-uyuni
└── ubuntu-2404-amd64-uyuni-client
```

### Canali CLM (dopo build)
```
DEV Environment:
├── ubuntu-2404-pool-amd64-uyuni-dev-ubuntu-2404-lifecycle
├── ubuntu-2404-amd64-main-uyuni-dev-ubuntu-2404-lifecycle
└── ...

PROD Environment:
├── ubuntu-2404-pool-amd64-uyuni-prod-ubuntu-2404-lifecycle
├── ubuntu-2404-amd64-main-uyuni-prod-ubuntu-2404-lifecycle
└── ...
```

### System Groups
```
Ubuntu-24.04-Test → client test (canali DEV)
Ubuntu-24.04-Prod → client prod (canali PROD)
```

### Activation Keys
```
ubuntu-2404-test → ambiente DEV + gruppo Test
ubuntu-2404-prod → ambiente PROD + gruppo Prod
```

---

## Riferimenti

- [UYUNI Documentation - Client Configuration](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/clients-ubuntu.html)
- [UYUNI Documentation - Content Lifecycle Management](https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/content-lifecycle.html)
- [UYUNI Documentation - Activation Keys](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/activation-keys.html)
- [UYUNI Documentation - System Groups](https://www.uyuni-project.org/uyuni-docs/en/uyuni/reference/systems/system-groups.html)
- [Ubuntu GPG Keys](https://keyserver.ubuntu.com/)
