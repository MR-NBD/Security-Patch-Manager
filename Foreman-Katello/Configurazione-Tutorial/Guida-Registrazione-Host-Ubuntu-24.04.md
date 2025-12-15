Scaricare il certificato CA di Foreman## Informazioni sull'ambiente di esempio

| Parametro          | Valore                             |
| ------------------ | ---------------------------------- |
| Server Foreman     | `foreman-katello-test.localdomain` |
| IP Server Foreman  | `10.172.2.17`                      |
| Organization Label | `psnasl06`                         |
| Activation Key     | `ak-ubuntu-2404-prod`              |
| Location           | `Italy-North`                      |
| Host Group         | Ubuntu-2404-Groups                 |

---
## Indice
- [1 Preparazione della VM Ubuntu](#1-preparazione-della-vm-ubuntu)
- [2 Disabilitare aggiornamenti Automatici](#2-configurazione-ntp-con-chrony)
- [3 Installa subscription-manager](#3-installa-subscription-manager)
- [4 Crea Directory PKI](#4-crea-directory-pki)
- [5 Scaricare il certificato CA di Foreman](#5-scaricare-il-certificato-ca-di-foreman)
- [6 Configura subscription-manager](#6-configura-subscription-manager)
- [7 Testa Connessione al Server](#7-testa-connessioneal-server)
- [8 Registra Host](#8-registra-host)
- [9 Abilita Repository e Aggiorna](#9-abilita-repository-e-aggiorna)
- [10 Carica Profilo pacchetti](#10-carica-profilo-pacchetti)
	- [10-bis Carica Profilo Pacchetti via API REST](#10-bis-carica-profilo-pacchetti-via-api-rest)
- [11 Automazione Upload Pacchetti](#11-automazione-upload-pacchetti)
	- [Troubleshooting](#troubleshooting)
- [12 Configura SSH per Remote Execution](#12-configura-ssh-per-remote-execution)
- [13 Aggiungi Host a /etc/hosts su Foreman](#13-aggiungi-host-a-/etc/hosts-su-foreman)
- [14 Aggiorna Host in Foreman](#14-aggiorna-host-in-foreman)
- [15 Verifica Finale](#15-verifica-finale)
	-  [Riepilogo Comandi Rapidi](#riepilogo-comandi-rapidi)
---
## 1 Preparazione della VM Ubuntu

Accedere alla VM Ubuntu come root.
### 1.1 Aggiungi Risoluzione DNS per Foreman

```bash
echo "10.172.2.17    foreman-katello-test.localdomain" >> /etc/hosts
```
### 1.2 Verifica Connettività

```bash
ping -c 2 foreman-katello-test.localdomain
```
---
## 2 Disabilitare aggiornamenti Automatici

Questo garantisce che sia Il Server FOREMAN possa controllare quando aggiornare, non Ubuntu automaticamente.
#### Ferma e disabilita apt-daily
```bash
systemctl stop apt-daily.timer
```
```bash
systemctl disable apt-daily.timer
```
```bash
systemctl stop apt-daily-upgrade.timer
```
```bash
systemctl disable apt-daily-upgrade.timer
```
```bash
systemctl stop apt-daily.service
```
```bash
systemctl disable apt-daily.service
```
```bash
systemctl stop apt-daily-upgrade.service
```
```bash
systemctl disable apt-daily-upgrade.service
```
#### Ferma e disabilita apt-daily
```bash
systemctl stop unattended-upgrades
```
```bash
systemctl disable unattended-upgrades
```
#### Rimuovi unattended-upgrades
```bash
apt remove -y unattended-upgrades
```
### Verifica

```bash
systemctl status apt-daily.timer
```
```bash
systemctl status apt-daily-upgrade.timer
```

**Output atteso**: "inactive (dead)" per entrambi.

---

## 3 Installa subscription-manager
Il `subscription-manager` è l'agent che permette alla VM di interagire con Foreman/Katello.
### 3.1 Aggiungi Repository ATIX
#### Scarica la chiave GPG
```bash
curl --silent --show-error --output /etc/apt/trusted.gpg.d/atix.asc https://oss.atix.de/atix_gpg.pub
```
#### Crea il file repository
```bash
cat > /etc/apt/sources.list.d/atix-client.sources << 'EOF'
Types: deb
URIs: https://oss.atix.de/Ubuntu24LTS/
Suites: stable
Components: main
Signed-By: /etc/apt/trusted.gpg.d/atix.asc
EOF
```
**IMPORTANTE**: L'URL corretto è `oss.atix.de`, NON `apt.atix.de`.
### 3.2 Installa i Pacchetti
```bash
apt update
```
```bash
apt install -y subscription-manager katello-host-tools
```
### 3.3 Verifica Installazione

```bash
subscription-manager version
```

**Output atteso**: Mostra la versione (es: `subscription-manager: 1.30.5-2`).

---
## 4 Crea Directory PKI

```bash
mkdir -p /etc/pki/consumer
```
```bash
mkdir -p /etc/pki/entitlement
```
```bash
mkdir -p /etc/pki/product
```
```bash
mkdir -p /etc/rhsm/ca
```

---
## 5 Scaricare il certificato CA di Foreman

```bash
curl -o /etc/rhsm/ca/katello-server-ca.pem https://foreman-katello-test.localdomain/pub/katello-server-ca.crt --insecure
```
### Verifica che sia un certificato valido
```bash
openssl x509 -in /etc/rhsm/ca/katello-server-ca.pem -text -noout | head -10
```
**Output atteso**: Informazioni del certificato (Subject, Issuer, Validity).

---
## 6 Configura subscription-manager

```bash
subscription-manager config \
  --server.hostname=foreman-katello-test.localdomain \
  --server.port=443 \
  --server.prefix=/rhsm \
  --rhsm.repo_ca_cert=/etc/rhsm/ca/katello-server-ca.pem \
  --rhsm.baseurl=https://foreman-katello-test.localdomain/pulp/deb
```
### Verifica Configurazione
```bash
subscription-manager config | grep -E "(hostname|baseurl)"
```
**Output atteso**:
```
   hostname = foreman-katello-test.localdomain
   baseurl = https://foreman-katello-test.localdomain/pulp/deb
```
---
## 7 Testa Connessione al Server

```bash
curl -k https://foreman-katello-test.localdomain/rhsm/status
```

**Output atteso**: JSON con `"result":true`.

---
## 8 Registra Host
```bash
subscription-manager register \
  --org="psnasl06" \
  --activationkey="ak-ubuntu-2404-prod" \
  --name="NOME-HOST"
```
**Output atteso**:
```
The system has been registered with ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
The registered system name is: NOME-HOST
```
### Troubleshooting Registrazione
In caso di errore `Error loading certificate`:
#### Pulisci registrazioni precedenti
```bash
subscription-manager clean
```
#### Riprova la registrazione
```bash
subscription-manager register \
  --org="psnasl06" \
  --activationkey="ak-ubuntu-2404-prod" \
  --name="NOME-HOST"
```
#### Via Web UI
1. Vai su **Hosts → Register Host**
2. Compila:
    - **Host Group**: `Ubuntu-2404-Groups`
    - **Operating System**: `Ubuntu 24.04`
    - **Activation Keys**: `ak-ubuntu-2404-prod`
    - **Insecure**: ☑ (se certificato self-signed)
3. Clicca **Generate**
4. Copia il comando `curl` generato

![](image-5.png)

---
## 9 Abilita Repository e Aggiorna
#### Abilita tutti i repository
```bash
subscription-manager repos --enable='*'
```
#### Verifica repository abilitati
```bash
subscription-manager repos --list-enabled
```
#### Aggiorna lista pacchetti
```bash
apt update
```

---
## 10 Carica Profilo Pacchetti
### IMPORTANTE - Problema Verifacato

Il comando standard `katello-package-upload --force` **potrebbe non funzionare** in ambienti Ubuntu 24.04 a causa di problemi con i pacchetti ATIX. Se il comando non produce alcun output e Foreman non mostra i pacchetti, usare il **metodo alternativo via API REST**.
### Metodo Standard (provare prima)

```bash
subscription-manager refresh
```
```bash
katello-package-upload --force
```
Questo invia a Foreman l'elenco dei pacchetti installati sulla VM.
### Verificare se ha funzionato
Dal server Foreman:
```bash
curl -k -u admin:PASSWORD "https://localhost/api/hosts/NOME-HOST/packages?per_page=5" | python3 -m json.tool
```

Se `total` è 0, il metodo standard non ha funzionato. Usare il metodo alternativo.
## 10-bis Carica Profilo Pacchetti via API REST
### Se il metodo standard trattato sopra fallisce
Questo metodo bypassa `katello-package-upload` e invia i pacchetti direttamente all'API Candlepin/RHSM.
#### 1: Genera lista pacchetti in formato JSON
```bash
dpkg-query -W -f='{"name":"${Package}","version":"${Version}","arch":"${Architecture}"},\n' | \
  sed '$ s/,$//' | \
  sed '1s/^/[/' | \
  sed '$s/$/]/' > /tmp/packages.json
```
#### 2: Ottieni l'UUID del consumer
```bash
UUID=$(cat /etc/pki/consumer/cert.pem | openssl x509 -subject -noout | grep -oP 'CN = \K[a-f0-9-]+')
echo "UUID: $UUID"
```
#### 3: Prepara il profilo nel formato corretto
```bash
cat /tmp/packages.json | python3 -c "
import json, sys
pkgs = json.load(sys.stdin)
profile = [{'name': p['name'], 'version': p['version'], 'arch': p['arch']} for p in pkgs]
print(json.dumps(profile))
" > /tmp/profile.json
```
#### 4: Invia a Foreman via API
```bash
curl -k --cert /etc/pki/consumer/cert.pem --key /etc/pki/consumer/key.pem \
  -X PUT \
  -H "Content-Type: application/json" \
  -d @/tmp/profile.json \
  "https://foreman-katello-test.localdomain/rhsm/consumers/$UUID/packages"
```
#### Verifica
Dal server Foreman:
```bash
curl -k -u admin:PASSWORD "https://localhost/api/hosts/NOME-HOST/packages?per_page=5" | python3 -m json.tool
```

**Output atteso**: `total` maggiore di 0 (es: 676 pacchetti).
### Spiegazione del metodo cui sopra

| Comando          | Cosa fa                                                                |
| ---------------- | ---------------------------------------------------------------------- |
| `dpkg-query`     | Estrae la lista di tutti i pacchetti installati dal database dpkg      |
| `UUID`           | Legge l'identificativo univoco dell'host dal certificato consumer      |
| `python3 -c ...` | Converte il JSON nel formato richiesto dall'API Candlepin              |
| `curl -X PUT`    | Invia i dati all'endpoint RHSM usando i certificati per autenticazione |

---
## 11 Automazione Upload Pacchetti
Poiché il metodo standard potrebbe non funzionare, è necessario automatizzare l'upload periodico.
### Metodo A: Cron Job Locale (su ogni VM)
#### Crea lo script di upload
```bash
cat > /usr/local/bin/katello-upload-packages.sh << 'EOF'
#!/bin/bash
# Script per upload pacchetti a Foreman/Katello
# Alternativa a katello-package-upload che non funziona su Ubuntu 24.04

FOREMAN_HOST="foreman-katello-test.localdomain"
CERT="/etc/pki/consumer/cert.pem"
KEY="/etc/pki/consumer/key.pem"

# Verifica che i certificati esistano
if [[ ! -f "$CERT" ]] || [[ ! -f "$KEY" ]]; then
    echo "Certificati consumer non trovati. Host non registrato?"
    exit 1
fi

# Ottieni UUID
UUID=$(openssl x509 -in "$CERT" -subject -noout | grep -oP 'CN = \K[a-f0-9-]+')

if [[ -z "$UUID" ]]; then
    echo "Impossibile ottenere UUID dal certificato"
    exit 1
fi

# Genera lista pacchetti
PACKAGES=$(dpkg-query -W -f='{"name":"%{Package}","version":"%{Version}","arch":"%{Architecture}"},' | sed 's/,$//' | sed 's/^/[/' | sed 's/$/]/')

# Converti in formato corretto
PROFILE=$(echo "$PACKAGES" | python3 -c "
import json, sys
data = sys.stdin.read()
# Fix formato dpkg-query
data = data.replace('%{Package}', '${Package}').replace('%{Version}', '${Version}').replace('%{Architecture}', '${Architecture}')
pkgs = json.loads(data)
profile = [{'name': p['name'], 'version': p['version'], 'arch': p['arch']} for p in pkgs]
print(json.dumps(profile))
" 2>/dev/null)

# Se la conversione fallisce, usa metodo alternativo
if [[ -z "$PROFILE" ]]; then
    dpkg-query -W -f='{"name":"${Package}","version":"${Version}","arch":"${Architecture}"},\n' | \
      sed '$ s/,$//' | sed '1s/^/[/' | sed '$s/$/]/' > /tmp/packages.json
    
    PROFILE=$(cat /tmp/packages.json | python3 -c "
import json, sys
pkgs = json.load(sys.stdin)
profile = [{'name': p['name'], 'version': p['version'], 'arch': p['arch']} for p in pkgs]
print(json.dumps(profile))
")
fi

# Invia a Foreman
curl -s -k --cert "$CERT" --key "$KEY" \
  -X PUT \
  -H "Content-Type: application/json" \
  -d "$PROFILE" \
  "https://$FOREMAN_HOST/rhsm/consumers/$UUID/packages" > /dev/null

if [[ $? -eq 0 ]]; then
    logger -t katello-upload "Package profile uploaded successfully"
else
    logger -t katello-upload "Package profile upload failed"
fi
EOF
```
#### Rendi eseguibile
```bash
chmod +x /usr/local/bin/katello-upload-packages.sh
```
#### Testa lo script
```bash
/usr/local/bin/katello-upload-packages.sh
```
#### Crea cron job (esegue ogni ora)
```bash
cat > /etc/cron.d/katello-package-upload << 'EOF'
# Upload package profile to Foreman/Katello every hour
0 * * * * root /usr/local/bin/katello-upload-packages.sh
EOF
```
#### Crea anche un hook apt (esegue dopo ogni install/upgrade)
```bash
cat > /etc/apt/apt.conf.d/99katello-upload << 'EOF'
DPkg::Post-Invoke { "/usr/local/bin/katello-upload-packages.sh" };
EOF
```
### Opzione B: Foreman Remote Execution (Consigliata per molti host)
Invece di configurare ogni VM, puoi schedulare un job da Foreman che esegue l'upload su tutti gli host.
#### 1. Crea Job Template in Foreman
Vai su **Hosts → Templates → Job Templates → New Job Template**
**Nome**: `Katello - Upload Package Profile (Ubuntu)`

**Template**:
```bash
#!/bin/bash
# Upload package profile per host Ubuntu

FOREMAN_HOST="<%= @host.content_source.hostname %>"
CERT="/etc/pki/consumer/cert.pem"
KEY="/etc/pki/consumer/key.pem"

UUID=$(openssl x509 -in "$CERT" -subject -noout | grep -oP 'CN = \K[a-f0-9-]+')

dpkg-query -W -f='{"name":"${Package}","version":"${Version}","arch":"${Architecture}"},\n' | \
  sed '$ s/,$//' | sed '1s/^/[/' | sed '$s/$/]/' > /tmp/packages.json

PROFILE=$(cat /tmp/packages.json | python3 -c "
import json, sys
pkgs = json.load(sys.stdin)
profile = [{'name': p['name'], 'version': p['version'], 'arch': p['arch']} for p in pkgs]
print(json.dumps(profile))
")

curl -s -k --cert "$CERT" --key "$KEY" \
  -X PUT \
  -H "Content-Type: application/json" \
  -d "$PROFILE" \
  "https://$FOREMAN_HOST/rhsm/consumers/$UUID/packages"

echo "Package profile uploaded for $(hostname)"
```

**Job category**: `Katello`
#### 2. Schedula il Job

1. Vai su **Hosts → All Hosts**
2. Seleziona gli host Ubuntu
3. Clicca **Schedule Remote Job**
4. Seleziona il template creato
5. Configura scheduling:
   - **Schedule**: Recurring
   - **Cronline**: `0 * * * *` (ogni ora)
1. Clicca **Submit**
## Troubleshooting

### Problema: `katello-package-upload --force` non produce output
### Problema: Pacchetti non visibili in Foreman dopo upload

**Verifica**:
```bash
curl -k -u admin:PASSWORD "https://localhost/api/hosts/NOME-HOST/packages" | python3 -m json.tool | head -20
```

Se `total: 0`:
1. Verifica che l'UUID sia corretto
2. Verifica che i certificati esistano in `/etc/pki/consumer/`
3. Riprova l'upload via API

### Problema: Errore "No such file or directory" per certificati
**Soluzione**: L'host non è registrato correttamente. Ripeti dalla FASE 8.
### Problema: Upload funziona ma poi i pacchetti "spariscono"
**Causa**: Possibile sovrascrittura da parte di `rhsmcertd`.
**Soluzione**: Implementare l'automazione (FASE 11) con cron job o Foreman Remote Execution.

---
## 12 Configura SSH per Remote Execution
### Sul Server Foreman

Copia la chiave SSH pubblica sulla VM Ubuntu:

```bash
cat /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy.pub | ssh UTENTE@IP_VM "sudo mkdir -p /root/.ssh && sudo tee /root/.ssh/authorized_keys && sudo chmod 600 /root/.ssh/authorized_keys && sudo chown root:root /root/.ssh/authorized_keys"
```
Sostituisci:

- `UTENTE` = utente con sudo sulla VM (es: `azureuser`)
- `IP_VM` = indirizzo IP della VM Ubuntu
### Verifica Connessione SSH

```bash
ssh -i /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy root@IP_VM "hostname"
```

**Output atteso**: Hostname della VM senza richiesta password.

---
## 13 Aggiungi Host a /etc/hosts su Foreman
### Dal Server Foreman
```bash
echo "IP_VM    NOME-HOST" >> /etc/hosts
```

Sostituisci con i valori reali (es: `echo "10.172.2.15 test-vm-production" >> /etc/hosts`).
### Verifica
```bash
ping -c 2 NOME-HOST
```
---
## 14 Aggiorna Host in Foreman
### Aggiorna IP
```bash
hammer host update --name "NOME-HOST" --ip "IP_VM"
```
### Aggiorna Location
```bash
hammer host update --name "NOME-HOST" --location "Italy-North"
```
### Verifica
```bash
hammer host info --name "NOME-HOST" | grep -E "(IP|Location)"
```
---
## 15 Verifica Finale
### 15.1 Dalla Web UI
1. Vai su **Hosts → Content Hosts**
2. Cerca il nome dell'host
3. Verifica che mostri:
    - Organization: PSN-ASL06
    - Location: Italy-North
    - Packages: Lista dei pacchetti installati
### 15.2 Via API
```bash
curl -k -u admin:PASSWORD "https://localhost/api/hosts/NOME-HOST/packages" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Totale pacchetti: {d[\"total\"]}')"
```
### 15.3 Testa Remote Execution
1. Vai su **Hosts → All Hosts**
2. Clicca sull'host
3. Clicca **Schedule Remote Job**
4. Job category: `Commands`
5. Job template: `Run Command - Script Default`
6. Command: `hostname && uptime`
7. Clicca **Submit**

**Output atteso**: Job completato con successo, mostra hostname e uptime della VM.

---
## Riepilogo Comandi Rapidi
### Upload manuale pacchetti (da eseguire sulla VM Ubuntu)

```bash
# Tutto in un comando
UUID=$(openssl x509 -in /etc/pki/consumer/cert.pem -subject -noout | grep -oP 'CN = \K[a-f0-9-]+') && \
dpkg-query -W -f='{"name":"${Package}","version":"${Version}","arch":"${Architecture}"},\n' | \
  sed '$ s/,$//' | sed '1s/^/[/' | sed '$s/$/]/' | \
  python3 -c "import json,sys; pkgs=json.load(sys.stdin); print(json.dumps([{'name':p['name'],'version':p['version'],'arch':p['arch']} for p in pkgs]))" | \
  curl -s -k --cert /etc/pki/consumer/cert.pem --key /etc/pki/consumer/key.pem \
    -X PUT -H "Content-Type: application/json" -d @- \
    "https://foreman-katello-test.localdomain/rhsm/consumers/$UUID/packages"
```
### Verifica pacchetti (da Foreman)
```bash
curl -k -u admin:PASSWORD "https://localhost/api/hosts/NOME-HOST/packages" | python3 -c "import json,sys; print(f'Pacchetti: {json.load(sys.stdin)[\"total\"]}')"
```
