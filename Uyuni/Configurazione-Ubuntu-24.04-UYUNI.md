# Configurazione Ubuntu 24.04 LTS (Noble) su UYUNI

## Panoramica

Questa guida descrive la configurazione completa di UYUNI per gestire client **Ubuntu 24.04 LTS (Noble Numbat)**, inclusa:
- Importazione chiavi GPG Ubuntu
- Creazione canali software
- Configurazione repository
- Sincronizzazione contenuti

---

## Indice

- [FASE 1: Importazione Chiavi GPG Ubuntu](#fase-1-importazione-chiavi-gpg-ubuntu)
- [FASE 2: Creazione Canali Software](#fase-2-creazione-canali-software)
- [FASE 3: Configurazione Repository](#fase-3-configurazione-repository)
- [FASE 4: Sincronizzazione](#fase-4-sincronizzazione)
- [FASE 5: Verifica e Bootstrap Repository](#fase-5-verifica-e-bootstrap-repository)
- [Riferimenti](#riferimenti)

---

## FASE 1: Importazione Chiavi GPG Ubuntu

### 1.1 Informazioni sulle Chiavi GPG Ubuntu

Ubuntu utilizza diverse chiavi GPG per firmare i pacchetti:

| Chiave | Key ID | Descrizione |
|--------|--------|-------------|
| Ubuntu Archive | `871920D1991BC93C` | Chiave principale archivio Ubuntu |
| Ubuntu Archive (2018) | `F6ECB3762474EDA9D21B7022871920D1991BC93C` | Chiave archivio 2018 |
| Ubuntu Archive Automatic Signing Key | `3B4FE6ACC0B21F32` | Firma automatica |

### 1.2 Scarica le Chiavi GPG sul Server UYUNI

Connettiti al server UYUNI e scarica le chiavi:

```bash
# Entra come root
sudo su -

# Crea directory temporanea per le chiavi
mkdir -p /tmp/ubuntu-gpg-keys
cd /tmp/ubuntu-gpg-keys

# Scarica la chiave principale Ubuntu Archive (871920D1991BC93C)
curl -sS "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C" -o ubuntu-archive-keyring.asc

# Scarica la chiave Ubuntu Archive Automatic Signing Key (3B4FE6ACC0B21F32)
curl -sS "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x3B4FE6ACC0B21F32" -o ubuntu-archive-automatic.asc
```

### 1.3 Importa le Chiavi nel Keyring UYUNI

```bash
# Importa le chiavi nel keyring UYUNI (container)
mgradm gpg add /tmp/ubuntu-gpg-keys/ubuntu-archive-keyring.asc
mgradm gpg add /tmp/ubuntu-gpg-keys/ubuntu-archive-automatic.asc

# Verifica che le chiavi siano state importate
mgrctl exec -- gpg --homedir /var/lib/spacewalk/gpgdir --list-keys
```

Output atteso (dovrebbe mostrare le chiavi Ubuntu):
```
pub   rsa4096 2018-09-17 [SC]
      F6ECB3762474EDA9D21B7022871920D1991BC93C
uid           [unknown] Ubuntu Archive Automatic Signing Key (2018) <ftpmaster@ubuntu.com>
```
### 1.4 Alternativa: Importa Chiavi da un Client Ubuntu

Se hai già un client Ubuntu 24.04, puoi esportare le chiavi da lì:

```bash
# Sul client Ubuntu 24.04
apt-key export 871920D1991BC93C > ubuntu-archive.gpg
# Oppure (metodo moderno)
gpg --export --armor 871920D1991BC93C > ubuntu-archive.asc

# Trasferisci il file sul server UYUNI e importa
mgradm gpg add /path/to/ubuntu-archive.asc
```

---

## FASE 2: Creazione Canali Software

### 2.1 Metodo A: Usando spacewalk-common-channels (Consigliato)

UYUNI fornisce un comando per creare automaticamente i canali Ubuntu:

```bash
# Lista tutti i canali disponibili per Ubuntu
mgrctl exec -- spacewalk-common-channels -l | grep ubuntu-24

# Crea tutti i canali per Ubuntu 24.04
mgrctl exec -- spacewalk-common-channels \
  ubuntu-2404-pool-amd64-uyuni \
  ubuntu-2404-amd64-main-uyuni \
  ubuntu-2404-amd64-main-updates-uyuni \
  ubuntu-2404-amd64-main-security-uyuni \
  ubuntu-2404-amd64-uyuni-client
```

### 2.2 Metodo B: Creazione Manuale via Web UI

Se preferisci creare i canali manualmente:

#### Step 1: Crea il Canale Base (Parent)

1. **Web UI** → **Software** → **Manage** → **Channels**
2. Clicca **Create Channel**
3. Compila:

| Campo                   | Valore                                                                   |
| ----------------------- | ------------------------------------------------------------------------ |
| **Channel Name**        | Ubuntu 24.04 LTS Pool for amd64                                          |
| **Channel Label**       | ubuntu-2404-pool-amd64-uyuni                                             |
| **Parent Channel**      | None (è il canale base)                                                  |
| **Architecture**        | AMD64 Debian                                                             |
| **Checksum Type**       | SHA256                                                                   |
| **Channel Summary**     | Ubuntu 24.04 LTS base channel                                            |
| **GPG key URL**         | https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C |
| **GPG key ID**          | 871920D1991BC93C                                                         |
| **GPG key Fingerprint** | F6ECB3762474EDA9D21B7022871920D1991BC93C                                 |

4. Clicca **Create Channel**

#### Step 2: Crea i Canali Child

Ripeti il processo per ogni canale child (usa il canale base come **Parent Channel**):

| Channel Name | Channel Label | Repository (Step 3) |
|--------------|---------------|---------------------|
| Ubuntu 24.04 LTS Main amd64 | ubuntu-2404-amd64-main-uyuni | main |
| Ubuntu 24.04 LTS Main Updates amd64 | ubuntu-2404-amd64-main-updates-uyuni | main updates |
| Ubuntu 24.04 LTS Main Security amd64 | ubuntu-2404-amd64-main-security-uyuni | main security |
| Ubuntu 24.04 LTS UYUNI Client amd64 | ubuntu-2404-amd64-uyuni-client | client tools |

---

## FASE 3: Configurazione Repository

### 3.1 Repository Ubuntu 24.04 (Noble)

I repository ufficiali Ubuntu 24.04 sono:

| Repository | URL | Componente |
|------------|-----|------------|
| **Main** | `http://archive.ubuntu.com/ubuntu` | main |
| **Updates** | `http://archive.ubuntu.com/ubuntu` | main (noble-updates) |
| **Security** | `http://security.ubuntu.com/ubuntu` | main (noble-security) |

### 3.2 Crea Repository via Web UI

Per ogni repository:

1. **Web UI** → **Software** → **Manage** → **Repositories**
2. Clicca **Create Repository**

#### Repository 1: Ubuntu 24.04 Main

| Campo | Valore |
|-------|--------|
| **Repository Label** | ubuntu-2404-amd64-main-repo |
| **Repository URL** | `http://archive.ubuntu.com/ubuntu/` |
| **Has Signed Metadata?** | ☑ Yes |
| **Type** | deb |
| **In Release path** | dists/noble |
| **Components** | main |
| **Architectures** | amd64 |

Clicca **Create Repository**

#### Repository 2: Ubuntu 24.04 Main Updates

| Campo | Valore |
|-------|--------|
| **Repository Label** | ubuntu-2404-amd64-main-updates-repo |
| **Repository URL** | `http://archive.ubuntu.com/ubuntu/` |
| **Has Signed Metadata?** | ☑ Yes |
| **Type** | deb |
| **In Release path** | dists/noble-updates |
| **Components** | main |
| **Architectures** | amd64 |

Clicca **Create Repository**

#### Repository 3: Ubuntu 24.04 Main Security

| Campo | Valore |
|-------|--------|
| **Repository Label** | ubuntu-2404-amd64-main-security-repo |
| **Repository URL** | `http://security.ubuntu.com/ubuntu/` |
| **Has Signed Metadata?** | ☑ Yes |
| **Type** | deb |
| **In Release path** | dists/noble-security |
| **Components** | main |
| **Architectures** | amd64 |

Clicca **Create Repository**

### 3.3 Associa Repository ai Canali

Per ogni canale child:

1. **Web UI** → **Software** → **Manage** → **Channels**
2. Clicca sul canale (es. `ubuntu-2404-amd64-main-uyuni`)
3. Tab **Repositories** → **Add/Remove**
4. Seleziona il repository corrispondente
5. Clicca **Update Repositories**

| Canale | Repository da Associare |
|--------|-------------------------|
| ubuntu-2404-amd64-main-uyuni | ubuntu-2404-amd64-main-repo |
| ubuntu-2404-amd64-main-updates-uyuni | ubuntu-2404-amd64-main-updates-repo |
| ubuntu-2404-amd64-main-security-uyuni | ubuntu-2404-amd64-main-security-repo |

---

## FASE 4: Sincronizzazione

### 4.1 Avvia Sincronizzazione via Web UI

1. **Web UI** → **Software** → **Manage** → **Channels**
2. Clicca sul canale (es. `ubuntu-2404-amd64-main-uyuni`)
3. Tab **Repositories** → **Sync**
4. Clicca **Sync Now**

Ripeti per tutti i canali child.

### 4.2 Avvia Sincronizzazione via CLI

```bash
# Sincronizza tutti i canali figli del parent
mgrctl exec -- spacewalk-repo-sync -p ubuntu-2404-pool-amd64-uyuni

# Oppure sincronizza canale singolo
mgrctl exec -- spacewalk-repo-sync -c ubuntu-2404-amd64-main-uyuni
mgrctl exec -- spacewalk-repo-sync -c ubuntu-2404-amd64-main-updates-uyuni
mgrctl exec -- spacewalk-repo-sync -c ubuntu-2404-amd64-main-security-uyuni
```

### 4.3 Monitora Progresso Sincronizzazione

```bash
# Lista log disponibili
mgrctl exec ls /var/log/rhn/reposync/

# Monitora log in tempo reale
mgrctl exec -ti -- tail -f /var/log/rhn/reposync/ubuntu-2404-amd64-main-uyuni.log
```

> **⚠️ ATTENZIONE**: I repository Ubuntu sono molto grandi. La sincronizzazione può richiedere **diverse ore** (anche 6-12 ore per la prima sync completa).

### 4.4 Verifica Stato Sincronizzazione via Web UI

1. **Web UI** → **Software** → **Manage** → **Channels**
2. Clicca sul canale
3. Tab **Repositories** → **Sync** → **Sync Status**

---

## FASE 5: Verifica e Bootstrap Repository

### 5.1 Crea Repository UYUNI Client Tools

Per il bootstrap dei client Ubuntu, devi anche configurare il canale client tools:

```bash
# Aggiungi repository per UYUNI client tools
mgrctl exec -- spacewalk-common-channels ubuntu-2404-amd64-uyuni-client
```

### 5.2 Genera Bootstrap Repository

Dopo che la sincronizzazione è completa:

```bash
# Genera bootstrap repository per Ubuntu 24.04
mgrctl exec -ti mgr-create-bootstrap-repo --create ubuntu-2404-amd64
```

### 5.3 Verifica Bootstrap Repository

```bash
# Verifica che il bootstrap repo esista
mgrctl exec -- ls -la /srv/www/htdocs/pub/repositories/
```

### 5.4 Verifica Pacchetti Sincronizzati

Via Web UI:

1. **Web UI** → **Software** → **Channel List** → **All**
2. Clicca su `ubuntu-2404-amd64-main-uyuni`
3. Verifica il conteggio pacchetti (dovrebbero essere migliaia)

Via CLI:

```bash
# Conta pacchetti in un canale
mgrctl exec -- spacecmd -u admin -p <password> -- softwarechannel_listallpackages ubuntu-2404-amd64-main-uyuni | wc -l
```

---

## FASE 6: Configurazione Activation Key (Opzionale)

Per facilitare la registrazione dei client, crea un Activation Key:

### 6.1 Crea Activation Key via Web UI

1. **Web UI** → **Systems** → **Activation Keys**
2. Clicca **Create Key**
3. Compila:

| Campo | Valore |
|-------|--------|
| **Description** | Ubuntu 24.04 LTS Clients |
| **Key** | ubuntu-2404-key (o lascia vuoto per auto-generazione) |
| **Base Channel** | ubuntu-2404-pool-amd64-uyuni |
| **Add-on Entitlements** | Monitoring (opzionale) |
| **Contact Method** | Default |
| **Universal Default** | ☐ No |

4. Clicca **Create Activation Key**
5. Dopo la creazione, vai nella tab **Child Channels** e seleziona:
   - ☑ ubuntu-2404-amd64-main-uyuni
   - ☑ ubuntu-2404-amd64-main-updates-uyuni
   - ☑ ubuntu-2404-amd64-main-security-uyuni
   - ☑ ubuntu-2404-amd64-uyuni-client

6. Clicca **Update Key**

---

## Troubleshooting

### Errore: GPG Key non trovata

```bash
# Verifica chiavi importate
mgrctl exec -- gpg --homedir /var/lib/spacewalk/gpgdir --list-keys

# Re-importa chiave
mgradm gpg add /path/to/key.asc
```

### Errore: Repository sync fallita

```bash
# Verifica log errori
mgrctl exec -- cat /var/log/rhn/reposync/ubuntu-2404-amd64-main-uyuni.log | tail -50

# Verifica connettività
mgrctl exec -- curl -I http://archive.ubuntu.com/ubuntu/dists/noble/Release
```

### Errore: "Release file not found"

Verifica che il campo **In Release path** sia corretto:
- Per main: `dists/noble`
- Per updates: `dists/noble-updates`
- Per security: `dists/noble-security`

### Sincronizzazione lenta

I repository Ubuntu sono molto grandi. Per accelerare:
- Sincronizza solo i componenti necessari (main, non universe/multiverse)
- Usa mirror geograficamente vicini (es. `http://it.archive.ubuntu.com/ubuntu/`)

---

## Quick Reference - Comandi Utili

```bash
# Lista canali disponibili
mgrctl exec -- spacewalk-common-channels -l | grep ubuntu

# Crea canali Ubuntu 24.04
mgrctl exec -- spacewalk-common-channels \
  ubuntu-2404-pool-amd64-uyuni \
  ubuntu-2404-amd64-main-uyuni \
  ubuntu-2404-amd64-main-updates-uyuni \
  ubuntu-2404-amd64-main-security-uyuni \
  ubuntu-2404-amd64-uyuni-client

# Sincronizza tutti i child channels
mgrctl exec -- spacewalk-repo-sync -p ubuntu-2404-pool-amd64-uyuni

# Monitora sync
mgrctl exec -ti -- tail -f /var/log/rhn/reposync/ubuntu-2404-amd64-main-uyuni.log

# Genera bootstrap repo
mgrctl exec -ti mgr-create-bootstrap-repo --create ubuntu-2404-amd64

# Verifica chiavi GPG
mgrctl exec -- gpg --homedir /var/lib/spacewalk/gpgdir --list-keys
```

---

## Struttura Finale Canali

Dopo la configurazione completa avrai:

```
ubuntu-2404-pool-amd64-uyuni (Parent)
├── ubuntu-2404-amd64-main-uyuni
├── ubuntu-2404-amd64-main-updates-uyuni
├── ubuntu-2404-amd64-main-security-uyuni
└── ubuntu-2404-amd64-uyuni-client
```

---

## Riferimenti

- [UYUNI - Registering Ubuntu Clients](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/clients-ubuntu.html)
- [UYUNI - GPG Keys](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/gpg-keys.html)
- [UYUNI - Custom Channels](https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/custom-channels.html)
- [Ubuntu Releases](https://releases.ubuntu.com/)
- [Ubuntu Archive GPG Keys](https://keyserver.ubuntu.com/)
