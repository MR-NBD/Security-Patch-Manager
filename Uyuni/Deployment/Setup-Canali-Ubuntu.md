# Setup Canali Ubuntu 24.04 LTS per UYUNI

Guida completa per configurare i canali Ubuntu 24.04 LTS (Noble Numbat) su UYUNI Server utilizzando i template pre-configurati di `spacewalk-common-channels`.

## Obiettivo

Configurare UYUNI per gestire sistemi Ubuntu 24.04 LTS con:
- Repository main, security, updates, universe
- UYUNI Client Tools (venv-salt-minion)
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
ubuntu-24.04-pool-amd64-uyuni (Parent - Base)           ← 0 pacchetti (contenitore)
├── ubuntu-2404-amd64-main-uyuni                        ← ~6,000 pacchetti
├── ubuntu-2404-amd64-main-security-uyuni               ← ~7,600 pacchetti + errata
├── ubuntu-2404-amd64-main-updates-uyuni                ← ~9,000 pacchetti
├── ubuntu-2404-amd64-universe-uyuni                    ← ~65,000 pacchetti
├── ubuntu-2404-amd64-universe-security-uyuni           ← errata sicurezza
├── ubuntu-2404-amd64-universe-updates-uyuni            ← ~7,400 pacchetti
└── ubuntu-2404-amd64-uyuni-client                      ← Client Tools (venv-salt-minion)
```

> **NOTA**: Il canale Pool/Base è un contenitore gerarchico e non contiene pacchetti. I pacchetti sono nei child channels.

---

## FASE 1: Verifica Template Disponibili

Entra nel container UYUNI e verifica i template disponibili:

```bash
sudo podman exec -it uyuni-server bash

# Lista tutti i template Ubuntu 24.04
spacewalk-common-channels -l | grep ubuntu-2404
```

Output atteso:
```
 ubuntu-2404-amd64-main-backports-uyuni: amd64-deb
 ubuntu-2404-amd64-main-security-uyuni: amd64-deb
 ubuntu-2404-amd64-main-updates-uyuni: amd64-deb
 ubuntu-2404-amd64-main-uyuni: amd64-deb
 ubuntu-2404-amd64-multiverse-backports-uyuni: amd64-deb
 ubuntu-2404-amd64-multiverse-security-uyuni: amd64-deb
 ubuntu-2404-amd64-multiverse-updates-uyuni: amd64-deb
 ubuntu-2404-amd64-multiverse-uyuni: amd64-deb
 ubuntu-2404-amd64-restricted-backports-uyuni: amd64-deb
 ubuntu-2404-amd64-restricted-security-uyuni: amd64-deb
 ubuntu-2404-amd64-restricted-updates-uyuni: amd64-deb
 ubuntu-2404-amd64-restricted-uyuni: amd64-deb
 ubuntu-2404-amd64-universe-backports-uyuni: amd64-deb
 ubuntu-2404-amd64-universe-security-uyuni: amd64-deb
 ubuntu-2404-amd64-universe-updates-uyuni: amd64-deb
 ubuntu-2404-amd64-universe-uyuni: amd64-deb
 ubuntu-2404-amd64-uyuni-client: amd64-deb
 ubuntu-2404-amd64-uyuni-client-devel: amd64-deb
 ubuntu-2404-pool-amd64-uyuni: amd64-deb
```

---

## FASE 2: Creazione Canali con spacewalk-common-channels

> **IMPORTANTE**: I canali devono essere creati in ordine gerarchico. Prima il Pool (base), poi i child channels.

### 2.1 Crea Pool Channel (Base)

```bash
# Il pool è il parent channel - DEVE essere creato per primo
spacewalk-common-channels -u admin -p <password> ubuntu-2404-pool-amd64-uyuni
```

### 2.2 Crea Main Channels

```bash
# Main (base packages)
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-main-uyuni

# Main Security (aggiornamenti sicurezza)
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-main-security-uyuni

# Main Updates (aggiornamenti generali)
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-main-updates-uyuni
```

### 2.3 Crea Universe Channels (Opzionale ma consigliato)

```bash
# Universe (pacchetti community - necessario per OpenSCAP)
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-universe-uyuni

# Universe Security
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-universe-security-uyuni

# Universe Updates
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-universe-updates-uyuni
```

### 2.4 Crea UYUNI Client Channel (Obbligatorio per bootstrap)

```bash
# Client Tools - contiene venv-salt-minion per registrazione client
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-uyuni-client
```

> **IMPORTANTE**: Senza questo canale, il bootstrap dei client fallirà con errore: `ERROR: package 'venv-salt-minion' not found`

### 2.5 Verifica Canali Creati

```bash
spacecmd -u admin -p <password> softwarechannel_list
```

Output atteso:
```
ubuntu-24.04-pool-amd64-uyuni
ubuntu-2404-amd64-main-security-uyuni
ubuntu-2404-amd64-main-updates-uyuni
ubuntu-2404-amd64-main-uyuni
ubuntu-2404-amd64-universe-security-uyuni
ubuntu-2404-amd64-universe-updates-uyuni
ubuntu-2404-amd64-universe-uyuni
ubuntu-2404-amd64-uyuni-client
```

---

## FASE 3: Sincronizzazione Repository

### 3.1 Avvia Sync Manuale

```bash
# Sync tutti i canali in sequenza
spacewalk-repo-sync --channel ubuntu-2404-amd64-main-uyuni
spacewalk-repo-sync --channel ubuntu-2404-amd64-main-security-uyuni
spacewalk-repo-sync --channel ubuntu-2404-amd64-main-updates-uyuni
spacewalk-repo-sync --channel ubuntu-2404-amd64-universe-uyuni
spacewalk-repo-sync --channel ubuntu-2404-amd64-universe-security-uyuni
spacewalk-repo-sync --channel ubuntu-2404-amd64-universe-updates-uyuni
spacewalk-repo-sync --channel ubuntu-2404-amd64-uyuni-client
```

Oppure avvia in background:
```bash
spacewalk-repo-sync --channel ubuntu-2404-amd64-main-uyuni &
spacewalk-repo-sync --channel ubuntu-2404-amd64-main-security-uyuni &
spacewalk-repo-sync --channel ubuntu-2404-amd64-main-updates-uyuni &
```

### 3.2 Monitoraggio Sync

```bash
# Processi attivi
ps aux | grep spacewalk-repo-sync

# Log in tempo reale
tail -f /var/log/rhn/reposync/ubuntu-2404-amd64-main-uyuni.log

# Lista tutti i log
ls -la /var/log/rhn/reposync/

# Spazio disco (monitoraggio continuo)
watch -n 5 'df -h /var/spacewalk'

# Conteggio pacchetti sincronizzati
spacecmd -u admin -p <password> softwarechannel_listallpackages ubuntu-2404-amd64-main-uyuni | wc -l
```

### 3.3 Tempi e Dimensioni Stimate

| Canale | Pacchetti | Dimensione | Tempo Stimato |
|--------|-----------|------------|---------------|
| Pool (Base) | 0 | - | Immediato |
| Main | ~6,000 | ~8-10 GB | 30-60 min |
| Main Security | ~7,600 | ~2-3 GB | 15-30 min |
| Main Updates | ~9,000 | ~3-5 GB | 20-40 min |
| Universe | ~65,000 | ~80-100 GB | 4-8 ore |
| Universe Security | ~500 | ~500 MB | 5-10 min |
| Universe Updates | ~7,400 | ~2-3 GB | 15-30 min |
| UYUNI Client | ~50 | ~100 MB | 2-5 min |

**Totale stimato**: ~100-120 GB, 5-10 ore

### 3.4 Risultato Sync (Esempio Reale)

| Canale | Pacchetti | Errata |
|--------|-----------|--------|
| Pool (Base) | 0 | 0 |
| Main | 6,099 | 0 |
| Main Security | 7,638 | 318 |
| Main Updates | 9,067 | 0 |
| Universe | 64,755 | 0 |
| Universe Updates | 7,384 | 73 |

**Totale**: ~95,000 pacchetti, **391 errata** di sicurezza

---

## FASE 4: Creazione Activation Keys

### 4.1 Activation Key Test

**Systems** → **Activation Keys** → **Create Key**

| Campo | Valore |
|-------|--------|
| **Description** | Ubuntu 24.04 Test Systems |
| **Key** | `1-ak-ubuntu2404-test` |
| **Usage Limit** | (vuoto = illimitato) |
| **Base Channel** | `ubuntu-24.04-pool-amd64-uyuni` |

Dopo la creazione:
1. Tab **Child Channels** → seleziona tutti i child channels incluso `ubuntu-2404-amd64-uyuni-client`
2. Tab **Configuration** → Enable Configuration Management (opzionale)
3. **Update Key**

### 4.2 Activation Key Production

| Campo | Valore |
|-------|--------|
| **Description** | Ubuntu 24.04 Production Systems |
| **Key** | `1-ak-ubuntu2404-prod` |
| **Base Channel** | `ubuntu-24.04-pool-amd64-uyuni` |

---

## FASE 5: Registrazione Client

### 5.1 Pre-requisiti sul Client

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

### 5.2 Bootstrap Script (Consigliato)

```bash
# Scarica e esegui bootstrap
curl -Sks https://uyuni-server-test.uyuni.internal/pub/bootstrap/bootstrap.sh -o /tmp/bootstrap.sh
chmod +x /tmp/bootstrap.sh

# Esegui con activation key (senza il prefisso "1-")
/tmp/bootstrap.sh -a ak-ubuntu2404-test
```

### 5.3 Accetta Salt Key

Da container UYUNI:

```bash
sudo podman exec -it uyuni-server bash
salt-key -L          # Lista keys
salt-key -a <minion-id>  # Accetta specifica
salt-key -A          # Accetta tutte
```

---

## FASE 6: Verifica e Test

### 6.1 Verifica Sistema Registrato

**Systems** → **All** → clicca sul sistema

Verifica:
- Status verde
- Base Channel: `ubuntu-24.04-pool-amd64-uyuni`
- Child Channels assegnati (incluso uyuni-client)

### 6.2 Test Connettività Salt

```bash
salt '<minion-id>' test.ping
salt '<minion-id>' grains.item os osrelease
```

### 6.3 Installazione OpenSCAP

```bash
# Da client o via UYUNI
apt-get install -y openscap-scanner ssg-base
```

---

## Canali Opzionali

### Multiverse (software non-free)

```bash
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-multiverse-uyuni
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-multiverse-security-uyuni
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-multiverse-updates-uyuni
```

### Restricted (driver proprietari)

```bash
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-restricted-uyuni
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-restricted-security-uyuni
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-restricted-updates-uyuni
```

### Backports

```bash
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-main-backports-uyuni
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-universe-backports-uyuni
```

---

## Troubleshooting

### "No channels matching your selection"

Il canale Pool deve essere creato **prima** degli altri canali:
```bash
# PRIMA il pool
spacewalk-common-channels -u admin -p <password> ubuntu-2404-pool-amd64-uyuni

# POI i child
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-main-uyuni
```

### "package 'venv-salt-minion' not found"

Manca il canale UYUNI Client Tools:
```bash
spacewalk-common-channels -u admin -p <password> ubuntu-2404-amd64-uyuni-client
spacewalk-repo-sync --channel ubuntu-2404-amd64-uyuni-client
```

### "No space left on device"

```bash
# Verifica spazio
df -h /manager_storage

# Se pieno, espandi disco da Azure Portal, poi:
sudo growpart /dev/sdc 1
sudo pvresize /dev/sdc1
sudo lvextend -l +100%FREE /dev/vg_uyuni_repo/lv_repo
sudo xfs_growfs /manager_storage
```

### Pulizia canali per ricominciare

```bash
# Lista canali
spacecmd -u admin -p <password> softwarechannel_list

# Elimina un canale (prima i child, poi il parent)
spacecmd -u admin -p <password> softwarechannel_delete ubuntu-2404-amd64-main-uyuni

# Pulisci packages scaricati
rm -rf /var/spacewalk/packages/*
rm -rf /var/cache/rhn/reposync/*
```

### Container UYUNI non risponde

```bash
# Fuori dal container
sudo systemctl restart uyuni-server-pod
sudo podman ps
```

### Verifica sync in corso

```bash
# Processi attivi
ps aux | grep spacewalk-repo-sync

# Log in tempo reale
tail -f /var/log/rhn/reposync/*.log

# Dalla Web UI
Admin → Task Schedules → vedi job Running
```

---

## Metodo Alternativo: Creazione Manuale (Web UI)

Se preferisci creare i canali manualmente via Web UI invece di usare `spacewalk-common-channels`, consulta la sezione "Creazione Canali Manuale" nell'Appendice.

### Appendice: Import GPG Keys

Ubuntu usa diverse GPG keys per firmare i pacchetti. Se necessario importarle manualmente:

```bash
# Scarica la chiave Ubuntu Archive 2018
curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C" -o /tmp/ubuntu-archive-2018.asc
```

| Campo | Valore |
|-------|--------|
| GPG key URL | `https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C` |
| GPG key ID | `991BC93C` |
| GPG key Fingerprint | `F6EC B376 2474 EDA9 D21B 7022 8719 20D1 991B C93C` |

> **NOTA**: Con `spacewalk-common-channels` le GPG keys sono gestite automaticamente.

---

## Riferimenti

- [UYUNI - Registering Ubuntu Clients](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/clients-ubuntu.html)
- [UYUNI - spacewalk-common-channels](https://www.uyuni-project.org/uyuni-docs/en/uyuni/reference/spacecmd/softwarechannels.html)
- [Ubuntu Releases](https://releases.ubuntu.com/)
- [Ubuntu Archive Mirror](http://archive.ubuntu.com/ubuntu/)
