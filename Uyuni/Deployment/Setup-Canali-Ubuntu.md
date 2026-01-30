# Setup Canali Ubuntu 24.04 LTS per UYUNI

Guida completa per configurare i canali Ubuntu 24.04 LTS (Noble Numbat) su UYUNI Server, inclusa la gestione GPG, sincronizzazione repository, e registrazione client.
## Obiettivo

Configurare UYUNI per gestire sistemi Ubuntu 24.04 LTS con:
- Repository main, security, updates, universe
- GPG key verification
- Activation keys per ambienti test/production
- Integrazione con OpenSCAP per compliance

---

## Pre-requisiti

| Requisito | Dettaglio |
|-----------|-----------|
| UYUNI Server | Installato e funzionante |
| Spazio disco | Minimo **256GB** per repository (universe = ~65k pacchetti) |
| Connettività | Accesso a archive.ubuntu.com e security.ubuntu.com |
| Client | VM Ubuntu 24.04 LTS da registrare |

---

## Architettura Canali

```
Ubuntu 24.04 LTS AMD64 Base for Uyuni (Parent)
├── Ubuntu 24.04 LTS AMD64 Main
├── Ubuntu 24.04 LTS AMD64 Main Security
├── Ubuntu 24.04 LTS AMD64 Main Updates
├── Ubuntu 24.04 LTS AMD64 Universe            ← Necessario per OpenSCAP
├── Ubuntu 24.04 LTS AMD64 Universe Updates
└── Uyuni Client Tools for Ubuntu 24.04 AMD64
```

> **NOTA IMPORTANTE**: Il canale Universe contiene ~65.000 pacchetti e richiede ~50GB di spazio. Pianificare lo storage di conseguenza.

---

## FASE 1: Import GPG Keys

Ubuntu usa diverse GPG keys per firmare i pacchetti. Importarle prima di creare i canali.

### 1.1 Scarica GPG Key Ubuntu (da container UYUNI)

```bash
sudo podman exec -it uyuni-server bash
```

```bash
# Scarica la chiave Ubuntu Archive 2018
curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C" -o /tmp/ubuntu-archive-2018.asc

# Visualizza per verifica
cat /tmp/ubuntu-archive-2018.asc
```

### 1.2 Import via Web UI

1. **Systems** → **Autoinstallation** → **GPG and SSL Keys**
2. **Create Stored Key** / **Cert**

| Campo           | Valore                                                                                                                |
| --------------- | --------------------------------------------------------------------------------------------------------------------- |
| **Description** | Ubuntu Archive Automatic Signing Key (2018)                                                                           |
| **Type**        | GPG                                                                                                                   |
| **Key Content** | Incolla il contenuto del file .asc (da `-----BEGIN PGP PUBLIC KEY BLOCK-----` a `-----END PGP PUBLIC KEY BLOCK-----`) |

3. **Create Key**

### 1.3 Informazioni GPG per i Canali

Questi valori serviranno nella creazione dei canali:

| Campo | Valore |
|-------|--------|
| GPG key URL | `https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C` |
| GPG key ID | `991BC93C` |
| GPG key Fingerprint | `F6EC B376 2474 EDA9 D21B 7022 8719 20D1 991B C93C` |

---

## FASE 2: Creazione Base Channel

### 2.1 Crea Parent Channel

**Software** → **Manage** → **Channels** → **Create Channel**

| Campo                   | Valore                                                                     |
| ----------------------- | -------------------------------------------------------------------------- |
| **Channel Name**        | `Ubuntu 24.04 LTS AMD64 Base for Uyuni`                                    |
| **Channel Label**       | `ubuntu-2404-amd64-base-uyuni`                                             |
| **Parent Channel**      | `-- None --`                                                               |
| **Architecture**        | `AMD64 Debian`                                                             |
| **Checksum Type**       | `SHA256`                                                                   |
| **Channel Summary**     | `Ubuntu 24.04 LTS (Noble Numbat) base channel`                             |
| **GPG key URL**         | `https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C` |
| **GPG key ID**          | `991BC93C`                                                                 |
| **GPG key Fingerprint** | `F6EC B376 2474 EDA9 D21B 7022 8719 20D1 991B C93C`                        |
| **Enable GPG Check**    | ✅ Checked (per production)                                                 |

> **Per test rapidi**: Disabilita GPG Check e lascia vuoti i campi GPG.

Clicca **Create Channel**.

---

## FASE 3: Creazione Child Channels

Per ogni child channel, vai su **Software** → **Manage** → **Channels** → **Create Channel**

### 3.1 Main Channel

| Campo              | Valore                                  |
| ------------------ | --------------------------------------- |
| **Channel Name**   | `Ubuntu 24.04 LTS AMD64 Main`           |
| **Channel Label**  | `ubuntu-2404-amd64-main-uyuni`          |
| **Parent Channel** | `Ubuntu 24.04 LTS AMD64 Base for Uyuni` |
| **Architecture**   | `AMD64 Debian`                          |
| **Checksum Type**  | `SHA256`                                |
| **Summary**        | `Ubuntu 24.04 main packages`            |

### 3.2 Main Security Channel

| Campo              | Valore                                  |
| ------------------ | --------------------------------------- |
| **Channel Name**   | `Ubuntu 24.04 LTS AMD64 Main Security`  |
| **Channel Label**  | `ubuntu-2404-amd64-main-security-uyuni` |
| **Parent Channel** | `Ubuntu 24.04 LTS AMD64 Base for Uyuni` |
| **Architecture**   | `AMD64 Debian`                          |
| **Summary**        | `Ubuntu 24.04 main security updates`    |

### 3.3 Main Updates Channel

| Campo              | Valore                                  |
| ------------------ | --------------------------------------- |
| **Channel Name**   | `Ubuntu 24.04 LTS AMD64 Main Updates`   |
| **Channel Label**  | `ubuntu-2404-amd64-main-updates-uyuni`  |
| **Parent Channel** | `Ubuntu 24.04 LTS AMD64 Base for Uyuni` |
| **Architecture**   | `AMD64 Debian`                          |
| **Summary**        | `Ubuntu 24.04 main updates`             |

### 3.4 Universe Channel

| Campo              | Valore                                       |
| ------------------ | -------------------------------------------- |
| **Channel Name**   | `Ubuntu 24.04 LTS AMD64 Universe`            |
| **Channel Label**  | `ubuntu-2404-amd64-universe-uyuni`           |
| **Parent Channel** | `Ubuntu 24.04 LTS AMD64 Base for Uyuni`      |
| **Architecture**   | `AMD64 Debian`                               |
| **Summary**        | `Ubuntu 24.04 universe packages (community)` |

> Questo canale è necessario per installare OpenSCAP (`openscap-scanner`, `ssg-base`).

### 3.5 Universe Updates Channel

| Campo              | Valore                                     |
| ------------------ | ------------------------------------------ |
| **Channel Name**   | `Ubuntu 24.04 LTS AMD64 Universe Updates`  |
| **Channel Label**  | `ubuntu-2404-amd64-universe-updates-uyuni` |
| **Parent Channel** | `Ubuntu 24.04 LTS AMD64 Base for Uyuni`    |
| **Architecture**   | `AMD64 Debian`                             |
| **Summary**        | `Ubuntu 24.04 universe updates`            |

---

## FASE 4: Creazione Repository

**Software** → **Manage** → **Repositories** → **Create Repository**

### 4.1 Repository Main

| Campo                   | Valore                                                            |
| ----------------------- | ----------------------------------------------------------------- |
| **Repository Label**    | `repo-ubuntu-2404-main`                                           |
| **Repository URL**      | `http://archive.ubuntu.com/ubuntu/dists/noble/main/binary-amd64/` |
| **Type**                | `deb`                                                             |
| **Has Signed Metadata** | `No` (per test) o `Yes` (per production con GPG)                  |

### 4.2 Repository Main Security

| Campo                | Valore                                                                      |
| -------------------- | --------------------------------------------------------------------------- |
| **Repository Label** | `repo-ubuntu-2404-main-security`                                            |
| **Repository URL**   | `http://security.ubuntu.com/ubuntu/dists/noble-security/main/binary-amd64/` |
| **Type**             | `deb`                                                                       |

### 4.3 Repository Main Updates

| Campo                | Valore                                                                    |
| -------------------- | ------------------------------------------------------------------------- |
| **Repository Label** | `repo-ubuntu-2404-main-updates`                                           |
| **Repository URL**   | `http://archive.ubuntu.com/ubuntu/dists/noble-updates/main/binary-amd64/` |
| **Type**             | `deb`                                                                     |

### 4.4 Repository Universe

| Campo                | Valore                                                                |
| -------------------- | --------------------------------------------------------------------- |
| **Repository Label** | `repo-ubuntu-2404-universe`                                           |
| **Repository URL**   | `http://archive.ubuntu.com/ubuntu/dists/noble/universe/binary-amd64/` |
| **Type**             | `deb`                                                                 |

### 4.5 Repository Universe Updates

| Campo                | Valore                                                                        |
| -------------------- | ----------------------------------------------------------------------------- |
| **Repository Label** | `repo-ubuntu-2404-universe-updates`                                           |
| **Repository URL**   | `http://archive.ubuntu.com/ubuntu/dists/noble-updates/universe/binary-amd64/` |
| **Type**             | `deb`                                                                         |

---

## FASE 5: Associazione Repository ai Canali

Per ogni canale child:

1. **Software** → **Manage** → **Channels** → clicca sul canale
2. Tab **Repositories** → **Link Repositories**
3. Seleziona il repository corrispondente
4. **Update Repositories**

| Canale | Repository |
|--------|------------|
| Ubuntu 24.04 LTS AMD64 Main | repo-ubuntu-2404-main |
| Ubuntu 24.04 LTS AMD64 Main Security | repo-ubuntu-2404-main-security |
| Ubuntu 24.04 LTS AMD64 Main Updates | repo-ubuntu-2404-main-updates |
| Ubuntu 24.04 LTS AMD64 Universe | repo-ubuntu-2404-universe |
| Ubuntu 24.04 LTS AMD64 Universe Updates | repo-ubuntu-2404-universe-updates |

---

## FASE 6: Sincronizzazione

### 6.1 Avvia Sync Manuale

Per ogni canale child:

1. **Software** → **Manage** → **Channels** → seleziona canale
2. Tab **Repositories** → **Sync**
3. **Sync Now**

### 6.2 Tempi Stimati di Sync

| Canale | Pacchetti | Tempo Stimato |
|--------|-----------|---------------|
| Main | ~6.000 | 5-10 min |
| Main Security | ~7.500 | 5-10 min |
| Main Updates | ~9.000 | 10-15 min |
| Universe | ~65.000 | 30-60 min |
| Universe Updates | ~7.500 | 10-15 min |

### 6.3 Monitoraggio Sync

Da container UYUNI:

```bash
sudo podman exec -it uyuni-server bash
tail -f /var/log/rhn/reposync/*.log
```

O da Web UI: **Admin** → **Task Schedules** → guarda task **Running**

### 6.4 Sync Automatico (Production)

1. **Software** → **Manage** → **Channels** → seleziona canale
2. Tab **Repositories** → **Sync**
3. Configura **Schedule**:
   - Daily alle 02:00 per security
   - Weekly per universe

---

## FASE 7: Creazione Activation Keys

### 7.1 Activation Key Test

**Systems** → **Activation Keys** → **Create Key**

| Campo | Valore |
|-------|--------|
| **Description** | Ubuntu 24.04 Test Systems |
| **Key** | `1-ak-ubuntu2404-test` |
| **Usage Limit** | (vuoto = illimitato) |
| **Base Channel** | `Ubuntu 24.04 LTS AMD64 Base for Uyuni` |
| **Add-On Entitlements** | (opzionale) |
| **Universal Default** | No |

Dopo la creazione:
1. Tab **Child Channels** → seleziona tutti i child channels
2. Tab **Configuration** → Enable Configuration Management (opzionale)
3. **Update Key**

### 7.2 Activation Key Production

| Campo | Valore |
|-------|--------|
| **Description** | Ubuntu 24.04 Production Systems |
| **Key** | `1-ak-ubuntu2404-prod` |
| **Base Channel** | `Ubuntu 24.04 LTS AMD64 Base for Uyuni` |

### 7.3 System Groups (Opzionale ma Consigliato)

**Systems** → **System Groups** → **Create Group**

| Nome | Descrizione |
|------|-------------|
| `test-servers` | Ubuntu 24.04 test/development systems |
| `production-servers` | Ubuntu 24.04 production systems |

Associa i gruppi alle Activation Keys:
1. **Systems** → **Activation Keys** → seleziona key
2. Tab **Groups** → **Join** → seleziona gruppo

---

## FASE 8: Registrazione Client

### 8.1 Pre-requisiti sul Client

```bash
# Sul client Ubuntu 24.04
sudo su -

# Verifica hostname
hostname -f

# Verifica connettività a UYUNI
ping -c 2 uyuni-server-test.uyuni.internal

# Verifica porte Salt
nc -zv uyuni-server-test.uyuni.internal 4505
nc -zv uyuni-server-test.uyuni.internal 4506
```

### 8.2 Metodo 1: Bootstrap Script (Consigliato)

```bash
# Scarica e esegui bootstrap
curl -Sks https://uyuni-server-test.uyuni.internal/pub/bootstrap/bootstrap.sh -o /tmp/bootstrap.sh
chmod +x /tmp/bootstrap.sh

# Esegui con activation key (senza il prefisso "1-")
/tmp/bootstrap.sh -a ak-ubuntu2404-test
```

### 8.3 Metodo 2: Registrazione Manuale

```bash
# Installa salt-minion
apt-get update
apt-get install -y salt-minion

# Configura master
cat > /etc/salt/minion.d/susemanager.conf << 'EOF'
master: uyuni-server-test.uyuni.internal
EOF

# Riavvia e abilita
systemctl restart salt-minion
systemctl enable salt-minion
```

Poi su UYUNI:
1. **Salt** → **Keys** → trova la key pending → **Accept**
2. **Systems** → **Bootstrapping** → completa registrazione con Activation Key

### 8.4 Accetta Salt Key (se necessario)

Da container UYUNI:

```bash
sudo podman exec -it uyuni-server bash
salt-key -L          # Lista keys
salt-key -a <minion-id>  # Accetta specifica
salt-key -A          # Accetta tutte
```

---

## FASE 9: Verifica e Test

### 9.1 Verifica Sistema Registrato

**Systems** → **All** → clicca sul sistema

Verifica:
- ✅ Status verde
- ✅ Base Channel corretto
- ✅ Child Channels assegnati
- ✅ System Group (se configurato)

### 9.2 Test Connettività Salt

Da container UYUNI:

```bash
salt '<minion-id>' test.ping
salt '<minion-id>' grains.item os osrelease
```

### 9.3 Test Repository sul Client

Sul client Ubuntu:

```bash
apt-get update
apt-cache policy openscap-scanner
```

### 9.4 Installazione OpenSCAP (Test)

Da Web UI:
1. **Systems** → seleziona sistema
2. **Software** → **Packages** → **Install**
3. Cerca `openscap-scanner` e `ssg-base`
4. **Install Selected Packages**

O da client:

```bash
apt-get install -y openscap-scanner ssg-base
```

---

## Content Lifecycle Management (Opzionale)

> **ATTENZIONE**: In base ai test effettuati, CLM può avere problemi con canali molto grandi come Universe (~65k pacchetti). Si consiglia di:
> - Usare CLM solo per main, main-security, main-updates
> - Tenere Universe come canale diretto (non CLM)

### Setup CLM Base (senza Universe)

1. **Content Lifecycle** → **Projects** → **Create Project**
   - Name: `Ubuntu 24.04 Lifecycle`
   - Label: `ubuntu-2404-lifecycle`

2. **Sources** → **Attach/Detach**:
   - ☑️ ubuntu-2404-amd64-main-uyuni
   - ☑️ ubuntu-2404-amd64-main-security-uyuni
   - ☑️ ubuntu-2404-amd64-main-updates-uyuni
   - ☐ **NON** includere universe (troppo grande)

3. **Environments** → **Add**:
   - `test` - Ambiente di test
   - `production` - Ambiente di produzione

4. **Build** → crea Version 1

### Activation Keys con CLM

Per usare CLM, le Activation Keys devono puntare ai canali CLM:

| Key | Base Channel |
|-----|--------------|
| Test | `ubuntu-2404-lifecycle-test-ubuntu-2404-amd64-base-uyuni` |
| Prod | `ubuntu-2404-lifecycle-production-ubuntu-2404-amd64-base-uyuni` |

Poi aggiungere Universe come child channel diretto (non CLM).

---

## Troubleshooting

### Sync fallisce con "No space left on device"

```bash
# Verifica spazio
df -h /manager_storage

# Se pieno, espandi disco da Azure Portal, poi:
sudo pvresize /dev/sdb1
sudo lvextend -l +100%FREE /dev/vg_uyuni_repo/lv_repo
sudo xfs_growfs /manager_storage
```

### Repository URL 404

Verifica l'URL del repository:
```bash
curl -I http://archive.ubuntu.com/ubuntu/dists/noble/main/binary-amd64/Packages.gz
```

Se 404, l'URL potrebbe essere cambiato. Verifica su archive.ubuntu.com.

### GPG Key Error

Per test, disabilita GPG check:
1. **Software** → **Manage** → **Repositories** → seleziona repo
2. **Has Signed Metadata** = No

Per production, assicurati che la GPG key sia importata e associata al canale.

### Client non si registra

```bash
# Sul client
systemctl status salt-minion
journalctl -u salt-minion -f

# Verifica configurazione
cat /etc/salt/minion.d/susemanager.conf

# Verifica connettività
nc -zv <uyuni-server> 4505
nc -zv <uyuni-server> 4506
```

### Salt key non appare

```bash
# Sul client, forza registrazione
salt-call --local grains.items
systemctl restart salt-minion

# Sul server, verifica
sudo podman exec uyuni-server salt-key -L
```

### Canale "Waiting for repositories data to be generated"

Questo indica che i metadati non sono stati generati. Prova:

```bash
sudo podman exec -it uyuni-server bash
systemctl restart taskomatic
```

Poi rifai il **Sync** del canale.

---

## Riepilogo Canali e URL

| Canale | Repository URL |
|--------|----------------|
| Main | `http://archive.ubuntu.com/ubuntu/dists/noble/main/binary-amd64/` |
| Main Security | `http://security.ubuntu.com/ubuntu/dists/noble-security/main/binary-amd64/` |
| Main Updates | `http://archive.ubuntu.com/ubuntu/dists/noble-updates/main/binary-amd64/` |
| Universe | `http://archive.ubuntu.com/ubuntu/dists/noble/universe/binary-amd64/` |
| Universe Updates | `http://archive.ubuntu.com/ubuntu/dists/noble-updates/universe/binary-amd64/` |

---

## Riferimenti

- [UYUNI - Registering Ubuntu Clients](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/clients-ubuntu.html)
- [UYUNI - Content Lifecycle Management](https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/content-lifecycle-management.html)
- [UYUNI - Activation Keys](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/activation-keys.html)
- [Ubuntu Releases](https://releases.ubuntu.com/)
- [Ubuntu Archive Mirror](http://archive.ubuntu.com/ubuntu/)
