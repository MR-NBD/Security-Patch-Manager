# Guida Pratica: Setup Completo Ubuntu 22.04 su UYUNI

## Obiettivo

Replicare su UYUNI lo stesso setup che avevi con Foreman/Katello:
- ✅ Repository Ubuntu 22.04 LTS (= Product + Repositories)
- ✅ GPG Keys configurate
- ✅ Content Lifecycle Management (= Content Views)
- ✅ Environments: DEV → PROD (= Lifecycle Environments)
- ✅ 2 client Ubuntu registrati (uno test, uno production)

---

## Mappatura Concetti

| Foreman/Katello | UYUNI | Cosa farai |
|-----------------|-------|------------|
| Product | Parent Channel | `ubuntu-2204-lts-amd64` |
| Repository | Child Channel | `main`, `security`, `updates` |
| GPG Key | GPG Key (Channel) | Ubuntu Archive Key |
| Content View | CLM Project | `ubuntu-2204-clm` |
| Lifecycle Environment | CLM Environment | `dev`, `prod` |
| Activation Key | Activation Key | `ak-ubuntu2204-dev`, `ak-ubuntu2204-prod` |
| Host Collection | System Group | `ubuntu-dev`, `ubuntu-prod` |

---

## Pre-requisiti

- UYUNI Server installato e funzionante
- Accesso Web UI come admin
- Accesso SSH al server UYUNI (via Bastion)
- 2 VM Ubuntu 22.04 pronte (test e production)
- Connettività di rete tra UYUNI e le VM

---

## FASE 1: Accesso e Verifica Server UYUNI

### 1.1 Connessione al Server

```bash
# Via Azure Bastion, connettiti al server UYUNI
# Poi diventa root
sudo su -
```

### 1.2 Verifica Stato UYUNI

```bash
mgradm status
```

Tutti i servizi devono essere "running".

### 1.3 Accesso Web UI

Apri browser e vai a: `https://<UYUNI-SERVER-FQDN>`

- **Username**: admin
- **Password**: quella impostata durante l'installazione

---

## FASE 2: Creazione Canali Software Ubuntu 22.04

### 2.1 Metodo Rapido: spacewalk-common-channels

UYUNI include uno strumento che crea automaticamente i canali per distribuzioni comuni.

```bash
# Entra nel container UYUNI
mgrctl term
```

```bash
# Lista canali disponibili per Ubuntu
spacewalk-common-channels -l | grep -i ubuntu
```

Output (esempio):
```
ubuntu-2004-amd64-main
ubuntu-2004-amd64-security
ubuntu-2004-amd64-updates
ubuntu-2204-amd64-main
ubuntu-2204-amd64-security
ubuntu-2204-amd64-updates
ubuntu-2404-amd64-main
...
```

```bash
# Crea tutti i canali Ubuntu 22.04
spacewalk-common-channels -u admin -p '<TUA_PASSWORD>' -a amd64 \
  ubuntu-2204-amd64-main \
  ubuntu-2204-amd64-security \
  ubuntu-2204-amd64-updates
```

> **NOTA**: Sostituisci `<TUA_PASSWORD>` con la password admin.

### 2.2 Verifica Canali Creati

Nella Web UI:
1. Vai a **Software** → **Manage** → **Channels**
2. Dovresti vedere:

```
ubuntu-2204-amd64-main (Parent)
├── ubuntu-2204-amd64-security (Child)
└── ubuntu-2204-amd64-updates (Child)
```

### 2.3 Alternativa: Creazione Manuale Canali

Se preferisci creare manualmente (come facevi con Products in Katello):

#### 2.3.1 Crea Parent Channel (= Product)

Web UI → **Software** → **Manage** → **Channels** → **Create Channel**

| Campo | Valore |
|-------|--------|
| **Channel Name** | Ubuntu 22.04 LTS amd64 |
| **Channel Label** | ubuntu-2204-lts-amd64 |
| **Parent Channel** | None (questo È il parent) |
| **Architecture** | AMD64 Debian |
| **Channel Summary** | Ubuntu 22.04 LTS base channel |
| **GPG Key URL** | https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C |
| **GPG Key ID** | 871920D1991BC93C |
| **GPG Key Fingerprint** | F6EC... (opzionale) |

Clicca **Create Channel**.

#### 2.3.2 Crea Child Channels (= Repositories)

Ripeti per ogni child channel:

**Security Channel:**

| Campo | Valore |
|-------|--------|
| **Channel Name** | Ubuntu 22.04 LTS Security |
| **Channel Label** | ubuntu-2204-lts-amd64-security |
| **Parent Channel** | Ubuntu 22.04 LTS amd64 |
| **Architecture** | AMD64 Debian |

**Updates Channel:**

| Campo | Valore |
|-------|--------|
| **Channel Name** | Ubuntu 22.04 LTS Updates |
| **Channel Label** | ubuntu-2204-lts-amd64-updates |
| **Parent Channel** | Ubuntu 22.04 LTS amd64 |
| **Architecture** | AMD64 Debian |

---

## FASE 3: Configurazione Repository URLs

### 3.1 Associa Repository ai Canali

Per ogni child channel, devi associare l'URL del repository Ubuntu.

Web UI → **Software** → **Manage** → **Channels** → clicca su `ubuntu-2204-amd64-main`

Tab **Repositories** → **Add/Remove**

Se non esistono repository, creali:

### 3.2 Crea Repository

Web UI → **Software** → **Manage** → **Repositories** → **Create Repository**

#### Repository Main:

| Campo | Valore |
|-------|--------|
| **Repository Label** | ubuntu-2204-main-repo |
| **Repository URL** | http://archive.ubuntu.com/ubuntu/dists/jammy/main/binary-amd64/ |
| **Type** | deb |

#### Repository Security:

| Campo | Valore |
|-------|--------|
| **Repository Label** | ubuntu-2204-security-repo |
| **Repository URL** | http://security.ubuntu.com/ubuntu/dists/jammy-security/main/binary-amd64/ |
| **Type** | deb |

#### Repository Updates:

| Campo | Valore |
|-------|--------|
| **Repository Label** | ubuntu-2204-updates-repo |
| **Repository URL** | http://archive.ubuntu.com/ubuntu/dists/jammy-updates/main/binary-amd64/ |
| **Type** | deb |

### 3.3 Associa Repository ai Canali

Per ogni canale:
1. Vai al canale → **Repositories** tab
2. Seleziona il repository corrispondente
3. **Update Repositories**

---

## FASE 4: Import GPG Keys

### 4.1 Scarica GPG Key Ubuntu

```bash
# Nel container UYUNI
mgrctl term

# Scarica la chiave Ubuntu Archive
curl -fsSL https://keyserver.ubuntu.com/pks/lookup?op=get\&search=0x871920D1991BC93C -o /tmp/ubuntu-archive-key.asc

# Oppure dalla keyserver
gpg --keyserver keyserver.ubuntu.com --recv-keys 871920D1991BC93C
gpg --export --armor 871920D1991BC93C > /tmp/ubuntu-archive-key.asc
```

### 4.2 Import via Web UI

Web UI → **Software** → **Manage** → **GPG Keys** → **Create Stored Key**

| Campo | Valore |
|-------|--------|
| **Description** | Ubuntu Archive Automatic Signing Key (2018) |
| **Type** | GPG |
| **Content** | (incolla il contenuto di ubuntu-archive-key.asc) |

### 4.3 Associa GPG Key ai Canali

Per ogni canale Ubuntu:
1. Vai a **Software** → **Manage** → **Channels** → seleziona canale
2. Tab **Details** → **Edit**
3. Sezione GPG: seleziona la key importata
4. **Update Channel**

---

## FASE 5: Sincronizzazione Repository

### 5.1 Sync Manuale (Prima Volta)

Web UI → **Software** → **Manage** → **Channels** → seleziona `ubuntu-2204-amd64-main`

Tab **Repositories** → **Sync**

Seleziona tutti i repository → **Sync Now**

> ⏱️ **TEMPO**: La prima sync può richiedere 30-60 minuti per canale.

### 5.2 Verifica Sync Status

Tab **Repositories** → **Sync** → **Sync Status**

Oppure da CLI:

```bash
# Nel container
tail -f /var/log/rhn/reposync/*.log
```

### 5.3 Configura Sync Automatico (Opzionale)

Web UI → **Admin** → **Task Schedules** → **repo-sync-default**

Configura frequenza (es. daily alle 02:00).

### 5.4 Sync via CLI (Alternativa)

```bash
# Nel container UYUNI
spacewalk-repo-sync -c ubuntu-2204-amd64-main
spacewalk-repo-sync -c ubuntu-2204-amd64-security
spacewalk-repo-sync -c ubuntu-2204-amd64-updates
```

---

## FASE 6: Content Lifecycle Management (CLM)

**Questo è l'equivalente di Content Views + Lifecycle Environments in Katello!**

### 6.1 Crea CLM Project (= Content View)

Web UI → **Content Lifecycle** → **Projects** → **Create Project**

| Campo | Valore |
|-------|--------|
| **Name** | Ubuntu 22.04 LTS Managed |
| **Label** | ubuntu-2204-clm |
| **Description** | Content View equivalente per Ubuntu 22.04 |

Clicca **Create**.

### 6.2 Aggiungi Sources (Canali Sorgente)

Nella pagina del progetto appena creato:

**Sources** → **Attach/Detach Sources**

Seleziona:
- ☑️ ubuntu-2204-amd64-main
- ☑️ ubuntu-2204-amd64-security  
- ☑️ ubuntu-2204-amd64-updates

**Save**.

### 6.3 Crea Environments (= Lifecycle Environments)

Nella pagina del progetto:

**Environments** → **Add Environment**

Aggiungi in ordine:

| # | Environment Label | Description |
|---|-------------------|-------------|
| 1 | dev | Development/Test environment |
| 2 | prod | Production environment |

Il risultato sarà:

```
Sources → [dev] → [prod]
```

### 6.4 Crea Filtri (Opzionale ma Raccomandato)

I filtri ti permettono di controllare cosa passa in ogni environment.

**Filters** → **Create Filter**

#### Filtro 1: Escludi pacchetti sperimentali

| Campo | Valore |
|-------|--------|
| **Filter Name** | exclude-experimental |
| **Filter Type** | Package (Name) |
| **Matcher** | contains |
| **Rule** | DENY |
| **Package Name** | -experimental |

#### Filtro 2: Solo pacchetti entro una data (Point-in-Time)

| Campo | Valore |
|-------|--------|
| **Filter Name** | freeze-date |
| **Filter Type** | Package (Build Date) |
| **Matcher** | before or equal |
| **Rule** | ALLOW |
| **Date** | [data del tuo ultimo test] |

> **NOTA**: Per Ubuntu/Debian NON puoi filtrare per "Errata Type" perché non ci sono errata nativi. Usa filtri per data o nome pacchetto.

### 6.5 Prima Build (= Publish in Katello)

**Build** → **Build Project**

| Campo | Valore |
|-------|--------|
| **Version Message** | Initial build - Ubuntu 22.04 base |

Clicca **Build**.

> ⏱️ **TEMPO**: Il build può richiedere 10-30 minuti.

### 6.6 Verifica Build

Dopo il completamento, nella sezione **Environments** vedrai:

```
Sources → [dev: Version 1] → [prod: -]
```

Il contenuto è ora disponibile in DEV.

### 6.7 Promote a Production (quando pronto)

Dopo aver testato in DEV:

**Environments** → su `dev` clicca **Promote**

Seleziona `prod` → **Promote**

```
Sources → [dev: Version 1] → [prod: Version 1]
```

---

## FASE 7: Creazione Activation Keys

### 7.1 Activation Key per DEV

Web UI → **Systems** → **Activation Keys** → **Create Key**

| Campo | Valore |
|-------|--------|
| **Description** | Ubuntu 22.04 Development |
| **Key** | ak-ubuntu2204-dev |
| **Usage Limit** | (vuoto = illimitato) |
| **Base Channel** | ubuntu-2204-amd64-main-dev-ubuntu-2204-clm-1 |

> **NOTA**: Il nome del canale CLM sarà qualcosa come `[channel]-[env]-[project]-[version]`

Tab **Child Channels**: seleziona tutti i child channels DEV corrispondenti.

Clicca **Create Activation Key**.

### 7.2 Activation Key per PROD

Ripeti con:

| Campo | Valore |
|-------|--------|
| **Description** | Ubuntu 22.04 Production |
| **Key** | ak-ubuntu2204-prod |
| **Base Channel** | ubuntu-2204-amd64-main-prod-ubuntu-2204-clm-1 |

Seleziona child channels PROD.

### 7.3 Verifica Activation Keys

```bash
# Nel container
spacecmd activationkey_list
spacecmd activationkey_details ak-ubuntu2204-dev
spacecmd activationkey_details ak-ubuntu2204-prod
```

---

## FASE 8: Creazione System Groups

### 8.1 System Group per DEV

Web UI → **Systems** → **System Groups** → **Create Group**

| Campo | Valore |
|-------|--------|
| **Name** | ubuntu-dev |
| **Description** | Ubuntu development/test systems |

### 8.2 System Group per PROD

| Campo | Valore |
|-------|--------|
| **Name** | ubuntu-prod |
| **Description** | Ubuntu production systems |

### 8.3 Associa Groups alle Activation Keys

Per ogni Activation Key:

1. Vai a **Systems** → **Activation Keys** → seleziona la key
2. Tab **Groups** → **Join**
3. Seleziona il gruppo corrispondente (dev o prod)
4. **Join Selected Groups**

---

## FASE 9: Preparazione Client Ubuntu

Prima di registrare i client, devi preparare il bootstrap.

### 9.1 Genera Bootstrap Script

Web UI → **Admin** → **Manager Configuration** → **Bootstrap Script**

Oppure da CLI:

```bash
# Nel container
mgr-bootstrap
```

### 9.2 Verifica Bootstrap Repository

Il bootstrap repository per Ubuntu dovrebbe essere già stato creato automaticamente.

Verifica:

```bash
# Nel container
ls -la /srv/www/htdocs/pub/repositories/
```

Se manca, rigenera:

```bash
mgr-create-bootstrap-repo -c ubuntu-2204-amd64-main
```

---

## FASE 10: Registrazione Client Ubuntu - VM TEST (DEV)

### 10.1 Connetti alla VM Ubuntu Test

```bash
ssh user@ubuntu-test-vm
sudo su -
```

### 10.2 Verifica Prerequisiti

```bash
# Verifica hostname
hostname -f

# Deve risolvere UYUNI server
ping uyuni-server-test.yourcompany.local

# Verifica DNS
nslookup uyuni-server-test.yourcompany.local
```

### 10.3 Installa Salt Minion e Bootstrap

```bash
# Scarica ed esegui bootstrap script
curl -Sks https://uyuni-server-test.yourcompany.local/pub/bootstrap/bootstrap.sh | bash

# Oppure passo-passo:
# 1. Scarica script
curl -Sks https://uyuni-server-test.yourcompany.local/pub/bootstrap/bootstrap.sh -o /tmp/bootstrap.sh
chmod +x /tmp/bootstrap.sh

# 2. Esegui con activation key
/tmp/bootstrap.sh -a ak-ubuntu2204-dev
```

### 10.4 Alternativa: Registrazione Manuale con Salt

```bash
# Installa salt-minion
apt-get update
apt-get install -y salt-minion

# Configura master
cat > /etc/salt/minion.d/susemanager.conf << EOF
master: uyuni-server-test.yourcompany.local
EOF

# Riavvia
systemctl restart salt-minion
systemctl enable salt-minion
```

### 10.5 Accetta Salt Key sul Server

Web UI → **Salt** → **Keys**

Troverai la key del nuovo minion in "Pending". Clicca **Accept**.

Oppure da CLI nel container UYUNI:

```bash
salt-key -L
salt-key -A  # Accetta tutte le pending
```

### 10.6 Completa Registrazione con Activation Key

Dopo l'accept della key, se non hai usato il bootstrap con activation key:

Web UI → **Systems** → **Bootstrapping**

| Campo | Valore |
|-------|--------|
| **Host** | ubuntu-test-vm.yourcompany.local |
| **Activation Key** | ak-ubuntu2204-dev |
| **SSH Port** | 22 |
| **User** | root (o user con sudo) |
| **Authentication** | Password o SSH Key |

**Bootstrap**.

### 10.7 Verifica Registrazione

Web UI → **Systems** → **All**

Dovresti vedere `ubuntu-test-vm` con:
- Status: ✅ verde
- Base Channel: ubuntu-2204-...-dev-...
- System Group: ubuntu-dev

---

## FASE 11: Registrazione Client Ubuntu - VM PROD

### 11.1 Ripeti gli stessi step sulla VM Production

```bash
ssh user@ubuntu-prod-vm
sudo su -

# Bootstrap con activation key PROD
curl -Sks https://uyuni-server-test.yourcompany.local/pub/bootstrap/bootstrap.sh -o /tmp/bootstrap.sh
chmod +x /tmp/bootstrap.sh
/tmp/bootstrap.sh -a ak-ubuntu2204-prod
```

### 11.2 Accetta Key e Verifica

1. Web UI → **Salt** → **Keys** → Accept
2. Web UI → **Systems** → **All** → verifica `ubuntu-prod-vm`
   - Base Channel: ...-prod-...
   - System Group: ubuntu-prod

---

## FASE 12: Verifica Setup Completo

### 12.1 Checklist Web UI

- [ ] **Software** → **Channels**: 3+ canali Ubuntu visibili
- [ ] **Content Lifecycle** → **Projects**: `ubuntu-2204-clm` con 2 environments
- [ ] **Systems** → **Activation Keys**: 2 keys (dev, prod)
- [ ] **Systems** → **System Groups**: 2 gruppi con sistemi assegnati
- [ ] **Systems** → **All**: 2 sistemi Ubuntu registrati

### 12.2 Verifica da CLI

```bash
# Nel container UYUNI
mgrctl term

# Lista canali
spacecmd softwarechannel_list

# Lista sistemi
spacecmd system_list

# Dettagli sistema
spacecmd system_details ubuntu-test-vm.yourcompany.local

# Lista pacchetti installabili
spacecmd system_listupgrades ubuntu-test-vm.yourcompany.local
```

### 12.3 Test Connettività Salt

```bash
# Nel container UYUNI
salt '*ubuntu*' test.ping
salt '*ubuntu*' grains.item os osrelease

# Output atteso:
# ubuntu-test-vm.yourcompany.local:
#     True
# ubuntu-prod-vm.yourcompany.local:
#     True
```

### 12.4 Verifica Canali sui Client

Sul client Ubuntu:

```bash
# Verifica repo configurati
cat /etc/apt/sources.list.d/susemanager*.list

# Test update
apt-get update
```

---

## FASE 13: Primo Test di Patch (Preview)

Prima di passare alla guida completa sul patch management, facciamo un test veloce.

### 13.1 Visualizza Pacchetti Aggiornabili

Web UI → **Systems** → seleziona `ubuntu-test-vm` → **Software** → **Packages** → **Upgrade**

Vedrai lista di pacchetti con aggiornamenti disponibili.

### 13.2 Visualizza CVE (se disponibili)

Web UI → **Audit** → **CVE Audit**

Cerca per sistema o CVE ID.

### 13.3 Test Aggiornamento Singolo Pacchetto

1. Seleziona un pacchetto non critico (es. `vim`)
2. Clicca **Upgrade Packages**
3. Schedule: **As soon as possible**
4. Confirm

### 13.4 Verifica Esecuzione

Web UI → **Schedule** → **Pending Actions** o **Completed Actions**

---

## Riepilogo Architettura Finale

```
┌─────────────────────────────────────────────────────────────────┐
│                       UYUNI Server                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Software Channels                           │   │
│  │  ubuntu-2204-amd64-main (Parent)                        │   │
│  │    ├── ubuntu-2204-amd64-security                       │   │
│  │    └── ubuntu-2204-amd64-updates                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │          CLM Project: ubuntu-2204-clm                    │   │
│  │                                                          │   │
│  │  Sources ──► [DEV] ──► [PROD]                           │   │
│  │              │          │                                │   │
│  │              ▼          ▼                                │   │
│  │         Channels    Channels                             │   │
│  │         cloned      cloned                               │   │
│  │         for DEV     for PROD                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌────────────────────┐    ┌────────────────────┐              │
│  │ Activation Key     │    │ Activation Key     │              │
│  │ ak-ubuntu2204-dev  │    │ ak-ubuntu2204-prod │              │
│  │ → DEV channels     │    │ → PROD channels    │              │
│  │ → Group: ubuntu-dev│    │ → Group: ubuntu-prod│             │
│  └────────────────────┘    └────────────────────┘              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
           │                              │
           │ Salt (4505/4506)             │ Salt (4505/4506)
           ▼                              ▼
    ┌─────────────┐               ┌─────────────┐
    │ ubuntu-test │               │ ubuntu-prod │
    │ (DEV)       │               │ (PROD)      │
    │ Group:      │               │ Group:      │
    │ ubuntu-dev  │               │ ubuntu-prod │
    └─────────────┘               └─────────────┘
```

---

## Equivalenze Finali con Foreman/Katello

| Hai fatto in Katello | Hai fatto in UYUNI |
|----------------------|---------------------|
| Create Product "Ubuntu 22.04" | Create Parent Channel |
| Create Repository main/security/updates | Create Child Channels + Repositories |
| Import GPG Key | Import GPG Key (stored) |
| Sync Repository | Channel → Repositories → Sync |
| Create Content View | Create CLM Project |
| Add repos to CV | Attach Sources to Project |
| Create Filter | Create CLM Filter |
| Create Lifecycle Environment DEV | Add Environment "dev" |
| Create Lifecycle Environment PROD | Add Environment "prod" |
| Publish Content View | Build Project |
| Promote to DEV | (automatic on build) |
| Promote to PROD | Promote to "prod" |
| Create Activation Key DEV | Create Activation Key → DEV channels |
| Create Activation Key PROD | Create Activation Key → PROD channels |
| Create Host Collection | Create System Group |
| Register Host with AK | Bootstrap with Activation Key |

---

## Next Steps: Security Patch Management

Nella prossima guida tratteremo:

1. **Selezione manuale patch** - Come scegliere singole patch da applicare
2. **Prioritizzazione patch** - Workflow Security → Critical → Normal
3. **CVE Audit** - Identificare vulnerabilità specifiche
4. **Action Chains** - Sequenze di azioni (pre-check, patch, post-check, reboot)
5. **Scheduling** - Maintenance windows
6. **Verifica post-patch** - Monitoring e validazione
7. **Rollback** - Procedure di recovery

---

## Troubleshooting Comune

### Canale non sincronizza

```bash
# Nel container, verifica log
tail -f /var/log/rhn/reposync/ubuntu-2204*.log

# Riprova sync
spacewalk-repo-sync -c ubuntu-2204-amd64-main --fail
```

### Client non si registra

```bash
# Sul client
systemctl status salt-minion
journalctl -u salt-minion -f

# Verifica connettività
nc -zv uyuni-server 4505
nc -zv uyuni-server 4506
```

### GPG Key error

```bash
# Nel container
spacewalk-repo-sync -c ubuntu-2204-amd64-main --no-gpg-check
# (solo per debug, poi sistema la key)
```

### CLM Build fallisce

- Verifica che i canali sorgente abbiano pacchetti sincronizzati
- Controlla log: **Admin** → **Task Engine** → **History**

### Salt key non appare

```bash
# Sul client, verifica
cat /etc/salt/minion.d/susemanager.conf
systemctl restart salt-minion

# Sul server
salt-key -L
```

---

## Riferimenti

- [UYUNI - Registering Ubuntu Clients](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/clients-ubuntu.html)
- [UYUNI - Content Lifecycle Management](https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/content-lifecycle-management.html)
- [UYUNI - Activation Keys](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/activation-keys.html)

---

*Prossima guida: Security Patch Management - Selezione, Prioritizzazione e Monitoraggio*
