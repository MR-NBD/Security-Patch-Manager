## Informazioni Ambiente di esempio

| Parametro          | Valore                             |
| ------------------ | ---------------------------------- |
| Server Foreman     | `foreman-katello-test.localdomain` |
| IP Server Foreman  | `10.172.2.17`                      |
| Organization Label | `psnasl06`                         |
| Activation Key     | `ak-ubuntu-2404-prod`              |
| Location           | `Italy-North`                      |
| Host Group         | Ubuntu-2404-Groups                 |

---
## FASE 1: Preparazione VM Ubuntu

Accedi alla VM Ubuntu come root.
### 1.1 Aggiungi Risoluzione DNS per Foreman

```bash
echo "10.172.2.17    foreman-katello-test.localdomain" >> /etc/hosts
```
### 1.2 Verifica Connettività

```bash
ping -c 2 foreman-katello-test.localdomain
```
---
## FASE 2: Disabilita Aggiornamenti Automatici

Questo garantisce che sia Il Server FOREMAN controllare quando aggiornare, non Ubuntu automaticamente.
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

## FASE 3: Installa subscription-manager
il 'subscription-manager' è l'agent che permette alla VM di interagire con Foreman/Katello
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
## FASE 4: Crea Directory PKI

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
## FASE 5: Scarica Certificato CA di Foreman

```bash
curl -o /etc/rhsm/ca/katello-server-ca.pem https://foreman-katello-test.localdomain/pub/katello-server-ca.crt --insecure
```
### Verifica che sia un certificato valido
```bash
openssl x509 -in /etc/rhsm/ca/katello-server-ca.pem -text -noout | head -10
```
**Output atteso**: Informazioni del certificato (Subject, Issuer, Validity).

---
## FASE 6: Configura subscription-manager
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
## FASE 7: Testa Connessione al Server

```bash
curl -k https://foreman-katello-test.localdomain/rhsm/status
```

**Output atteso**: JSON con `"result":true`.

---
## FASE 8: Registra l'Host
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
Se ricevi errore `Error loading certificate`:

```bash
# Pulisci registrazioni precedenti
subscription-manager clean

# Riprova la registrazione
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

![](../img/image-5.png)


---
## FASE 9: Abilita Repository e Aggiorna

```bash
# Abilita tutti i repository
subscription-manager repos --enable='*'

# Verifica repository abilitati
subscription-manager repos --list-enabled

# Aggiorna lista pacchetti
apt update
```

---
## FASE 10: Carica Profilo Pacchetti

```bash
subscription-manager refresh
katello-package-upload --force
```

Questo invia a Foreman l'elenco dei pacchetti installati sulla VM.
---
## FASE 11: Configura SSH per Remote Execution

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
## FASE 12: Aggiungi Host a /etc/hosts su Foreman
### Sul Server Foreman

```bash
echo "IP_VM    NOME-HOST" >> /etc/hosts
```

Sostituisci con i valori reali (es: `echo "10.172.2.15 ubuntu-server-01" >> /etc/hosts`).
### Verifica

```bash
ping -c 2 NOME-HOST
```

---
## FASE 13: Aggiorna Host in Foreman
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
## FASE 14: Verifica Finale

### 14.1 Dalla Web UI

1. Vai su **Hosts → Content Hosts**
2. Cerca il nome dell'host
3. Verifica che mostri:
    - Organization: PSN-ASL06
    - Location: Italy-North
    - Packages: Lista dei pacchetti installati

### 14.2 Testa Remote Execution

1. Vai su **Hosts → All Hosts**
2. Clicca sull'host
3. Clicca **Schedule Remote Job**
4. Job category: `Commands`
5. Job template: `Run Command - Script Default`
6. Command: `hostname && uptime`
7. Clicca **Submit**

**Output atteso**: Job completato con successo, mostra hostname e uptime della VM.
