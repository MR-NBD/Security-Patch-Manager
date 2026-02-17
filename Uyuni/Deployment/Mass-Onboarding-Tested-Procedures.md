### Bootstrap Repository per RHEL9
Il bootstrap repository deve esistere per l'OS target. Di default era presente solo per Ubuntu.

```bash
# Verificare i repo disponibili
mgrctl exec -- mgr-create-bootstrap-repo --list

# Output atteso:
# 1. RHEL9-x86_64-uyuni
# 2. ubuntu-24.04-amd64-uyuni

# Generare il repo per RHEL9 (se mancante)
mgrctl exec -- mgr-create-bootstrap-repo --create=RHEL9-x86_64-uyuni

# Verificare la creazione
mgrctl exec -- ls /srv/www/htdocs/pub/repositories/
# Output atteso: res  ubuntu
```

### Compatibilita versione venv-salt-minion (HA CREATO PROBLEMI)

> **PROBLEMA RISCONTRATO**: il bootstrap repository puo contenere piu versioni del pacchetto `venv-salt-minion`. La versione piu recente (3006.0-58.1) richiede **OpenSSL >= 3.3.0**, ma RHEL 9.4 con repo EUS ha solo OpenSSL 3.0.7. Il risultato e che `venv-salt-minion` crasha all'avvio con:
> ```
> ImportError: /lib64/libcrypto.so.3: version `OPENSSL_3.3.0' not found
> ```

**Verificare le versioni nel bootstrap repo:**
```bash
mgrctl exec -- ls -la /srv/www/htdocs/pub/repositories/res/9/bootstrap/x86_64/
# Se sono presenti piu versioni (es. 47.36 e 58.1):
# venv-salt-minion-3006.0-47.36.uyuni.x86_64.rpm  <-- compatibile con OpenSSL 3.0.x
# venv-salt-minion-3006.0-58.1.uyuni.x86_64.rpm   <-- richiede OpenSSL >= 3.3.0
```

**Soluzione - Rimuovere la versione incompatibile e rigenerare i metadati del repo:**
```bash
# Rimuovere la versione che richiede OpenSSL 3.3.0
mgrctl exec -- rm /srv/www/htdocs/pub/repositories/res/9/bootstrap/x86_64/venv-salt-minion-3006.0-58.1.uyuni.x86_64.rpm

# Rigenerare i metadati del repo
mgrctl exec -- createrepo_c /srv/www/htdocs/pub/repositories/res/9/bootstrap/
```

> Dopo la registrazione su UYUNI, il client ricevera OpenSSL aggiornato tramite i canali CLM, e successivamente potra aggiornare anche `venv-salt-minion` alla versione piu recente senza problemi.
### Script Bootstrap specifico per RHEL9 via Proxy
Lo script bootstrap generico (`bootstrap.sh`) punta al server diretto. Per l'onboarding via proxy serve uno script dedicato.

```bash
mgrctl exec -- mgr-bootstrap \
  --hostname=uyuni-proxy-test.uyuni.internal \
  --activation-keys=1-rhel9 \
  --script=bootstrap-rhel9-proxy.sh
```

**Problemi durante il test:**

| Problema riscontrato                                   | Soluzione                                                              |
| ------------------------------------------------------ | ---------------------------------------------------------------------- |
| `--force` disponibile come fallback                    | Usare solo se il FQDN non e risolvibile ma e corretto                  |

**Opzioni disponibili** (`mgr-bootstrap --help`):

| Opzione | Descrizione |
|---|---|
| `--hostname=FQDN` | FQDN del proxy (o server) a cui si connetteranno i client |
| `--activation-keys=KEY` | Activation key (una sola supportata con Salt) |
| `--script=FILENAME` | Nome del file script generato |
| `--ssl-cert=PATH` | Certificato SSL pubblico (default: auto) |
| `--gpg-key=KEY` | Chiave GPG per verifica pacchetti |
| `--no-bundle` | Evita venv-salt-minion, installa salt-minion classico |
| `--force-bundle` | Forza venv-salt-minion |
| `--no-gpg` | Disabilita verifica GPG (sconsigliato) |
| `--force` | Forza generazione ignorando warning |

### Activation Key con permessi corretti

Nella Web UI (`Systems > Activation Keys > 1-rhel9 > Details`) devono essere abilitati:

-  **Configuration File Deployment** - permette push di file di configurazione
-  **Remote Commands** - permette esecuzione comandi remoti
-  **Monitoring** (Add-On System Types) - abilita "Monitor this Host"

Verifica via CLI:
```bash
mgrctl exec -- spacecmd -u admin -p '<ADMIN_PASS>' -- activationkey_details 1-rhel9
```

> Le opzioni `Config actions`, `Remote commands` e `Monitoring` si configurano **esclusivamente** nella Activation Key, non nello script bootstrap. Ogni client registrato con questa AK eredita automaticamente questi permessi.

#### Connettivita di Rete

Verificata dal client RHEL:
```bash
# Il client deve raggiungere il proxy sulla porta 443
curl -Sks https://uyuni-proxy-test.uyuni.internal/pub/bootstrap/bootstrap-rhel9-proxy.sh | head -5

# Output atteso:
# #!/bin/bash
# ...
# echo "Uyuni Server Client bootstrap script v2025.10"
```

### Entropia (ambiente Azure virtualizzato)

```bash
mgrctl exec -- cat /proc/sys/kernel/random/entropy_avail
# Output: 256 (OK, deve essere > 200)
# Se < 200: installare haveged o rng-tools
```

### Utente SSH in Azure

**Probleimi durante il test**: su Azure l'accesso SSH avviene con utente `azureuser` (non `root`). Lo script bootstrap richiede privilegi root per:
- Installare pacchetti (`venv-salt-minion`)
- Scrivere in `/etc/yum.repos.d/`
- Importare certificati SSL in `/usr/share/rhn/`

**Soluzione**: usare `| sudo bash` in tutti i metodi di distribuzione via SSH.
### SSH Known Hosts
Se un host target e stato ricreato (nuova VM sullo stesso IP), la chiave SSH cambia e il bootstrap fallisce con `REMOTE HOST IDENTIFICATION HAS CHANGED`.

**Soluzioni:**
```bash
# Rimuovere la vecchia chiave dal known_hosts del server
ssh-keygen -R <IP> -f /root/.ssh/known_hosts

# Rimuovere la vecchia chiave dal known_hosts di Salt
mgrctl exec -- ssh-keygen -R <IP> -f /var/lib/salt/.ssh/known_hosts

# Per il mass onboarding: usare -o StrictHostKeyChecking=no
ssh -o StrictHostKeyChecking=no azureuser@<host> "..."
```

---

## Procedura di Deregistrazione Client

```bash
# 1. Sul client RHEL: fermare e rimuovere salt-minion
ssh azureuser@10.172.2.21 "sudo systemctl stop venv-salt-minion; sudo dnf remove -y venv-salt-minion; sudo rm -rf /etc/venv-salt-minion /etc/salt"

# 2. Sul server: rimuovere la chiave Salt
mgrctl exec -- salt-key -d 'onbording-test-VM-RHEL9' -y

# 3. Sul server: rimuovere il sistema dalla Web UI
#    Systems > System List > selezionare il sistema > Delete System
#    Oppure via spacecmd:
mgrctl exec -- spacecmd -u admin -p '<ADMIN_PASS>' -- system_delete 'onbording-test-VM-RHEL9'
```

---

## Verifica Post-Onboarding (comune a tutti i metodi)

```bash
# 1. Chiave Salt accettata
mgrctl exec -- salt-key -l accepted
# Il minion-id del client deve essere presente

# 2. Ping Salt funzionante
mgrctl exec -- salt 'onbording-test-VM-RHEL9' test.ping
# Output atteso: True

# 3. Grains leggibili (informazioni sistema)
mgrctl exec -- salt 'onbording-test-VM-RHEL9' grains.get os
# Output atteso: RedHat

# 4. Web UI - Systems > System List > All
# Il client deve apparire con:
#   - Canali RHEL assegnati (dalla activation key 1-rhel9)
#   - System Group corretto (se configurato nella AK)
#   - Properties: Monitoring abilitato
#   - Configuration management abilitato
#   - Remote commands abilitato
```

---
## METODO 1: Bootstrap Script + SSH Remoto

### Test su singolo host

Eseguito **dal server UYUNI** (o da qualsiasi macchina con accesso SSH ai target):

```bash
ssh azureuser@10.172.2.21 "curl -Sks https://uyuni-proxy-test.uyuni.internal/pub/bootstrap/bootstrap-rhel9-proxy.sh | sudo bash"
```

**Risultato**: Registrazione completata con successo.

Dopo il bootstrap, il minion appare in `Unaccepted Keys`. Accettare la chiave:
```bash
mgrctl exec -- salt-key -a 'onbording-test-VM-RHEL9' -y
```

Poi verificare:
```bash
mgrctl exec -- salt 'onbording-test-VM-RHEL9' test.ping
# Output: True
```

Il client appare nella Web UI con:
- Canali RHEL assegnati dalla activation key `1-rhel9`
- Properties: Monitoring abilitato
- Configuration management e remote commands abilitati

### Scalabilita: distribuzione parallela

#### Per 10-50 host: `xargs`

```bash
# File: hosts-rhel9.txt (un IP per riga)
# 10.172.2.21
# 10.172.2.22
# 10.172.2.23

cat hosts-rhel9.txt | xargs -I {} -P 10 \
  ssh -o StrictHostKeyChecking=no azureuser@{} \
  "curl -Sks https://uyuni-proxy-test.uyuni.internal/pub/bootstrap/bootstrap-rhel9-proxy.sh | sudo bash"
```

Parametri:
- `-P 10`: 10 connessioni SSH parallele
- `-o StrictHostKeyChecking=no`: evita prompt interattivo per host sconosciuti

**Prerequisito**: chiave SSH di `azureuser` distribuita su tutti i target (o autenticazione tramite Azure AD).

#### Per 50-500 host: `pssh` (parallel-ssh)

```bash
# Installare pssh sul server/jump host
# zypper install pssh  oppure  pip install parallel-ssh

pssh -h hosts-rhel9.txt \
  -l azureuser \
  -t 600 \
  -p 20 \
  -o /tmp/onboard-output \
  "curl -Sks https://uyuni-proxy-test.uyuni.internal/pub/bootstrap/bootstrap-rhel9-proxy.sh | sudo bash"
```

Parametri:
- `-h hosts-rhel9.txt`: file con lista IP/hostname
- `-l azureuser`: utente SSH
- `-t 600`: timeout 600 secondi per host
- `-p 20`: 20 connessioni parallele
- `-o /tmp/onboard-output`: directory con log per-host

#### Per 100-1000+ host: script strutturato con rate limiting

```bash
#!/bin/bash
# mass-onboard-rhel9.sh
# Onboarding massivo RHEL9 via proxy con rate limiting

PROXY_FQDN="uyuni-proxy-test.uyuni.internal"
BOOTSTRAP_SCRIPT="bootstrap-rhel9-proxy.sh"
SSH_USER="azureuser"
INVENTORY="hosts-rhel9.txt"
LOG_DIR="/tmp/onboard-logs/$(date +%Y%m%d-%H%M%S)"
PARALLEL_JOBS=10
DELAY_BETWEEN=15  # secondi tra ogni registrazione (regola dei 15 secondi)

mkdir -p "$LOG_DIR"

echo "=== Mass Onboarding RHEL9 via Proxy ==="
echo "Proxy:     $PROXY_FQDN"
echo "Script:    $BOOTSTRAP_SCRIPT"
echo "Inventory: $INVENTORY"
echo "Parallel:  $PARALLEL_JOBS"
echo "Delay:     ${DELAY_BETWEEN}s"
echo "Logs:      $LOG_DIR"
echo "========================================="

TOTAL=$(wc -l < "$INVENTORY")
COUNT=0
SUCCESS=0
FAIL=0

while IFS= read -r HOST; do
  # Ignora righe vuote e commenti
  [[ -z "$HOST" || "$HOST" =~ ^# ]] && continue

  COUNT=$((COUNT + 1))
  echo "[${COUNT}/${TOTAL}] Onboarding: ${HOST}..."

  # Pre-check: connettivita SSH
  if ! ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "${SSH_USER}@${HOST}" "echo OK" &>/dev/null; then
    echo "  ERRORE: SSH non raggiungibile"
    echo "${HOST},SSH_UNREACHABLE" >> "${LOG_DIR}/failures.csv"
    FAIL=$((FAIL + 1))
    continue
  fi

  # Bootstrap
  ssh -o StrictHostKeyChecking=no "${SSH_USER}@${HOST}" \
    "curl -Sks https://${PROXY_FQDN}/pub/bootstrap/${BOOTSTRAP_SCRIPT} | sudo bash" \
    > "${LOG_DIR}/${HOST}.log" 2>&1

  if [ $? -eq 0 ]; then
    echo "  OK"
    SUCCESS=$((SUCCESS + 1))
  else
    echo "  ERRORE (vedi ${LOG_DIR}/${HOST}.log)"
    echo "${HOST},BOOTSTRAP_FAILED" >> "${LOG_DIR}/failures.csv"
    FAIL=$((FAIL + 1))
  fi

  # Rate limiting
  sleep "$DELAY_BETWEEN"

done < "$INVENTORY"

echo ""
echo "=== REPORT ==="
echo "Totale:    $COUNT"
echo "Successo:  $SUCCESS"
echo "Falliti:   $FAIL"
echo "Logs:      $LOG_DIR"
echo "==============="
```

### Accettazione chiavi post-onboarding

Con l'Activation Key, le chiavi dovrebbero essere accettate automaticamente. Se restano in `Unaccepted Keys`:

```bash
# Accettare tutte le chiavi pendenti
mgrctl exec -- salt-key -A -y

# Oppure accettare solo quelle specifiche
mgrctl exec -- salt-key -a 'onbording-test-VM-*' -y
```

---
## METODO 2: spacecmd - Bootstrap dal Server

### Test su singolo host

Eseguire **dal server UYUNI**:

```bash
mgrctl exec -- spacecmd -u admin -p '<ADMIN_PASS>' -- system_bootstrap \
  --hostname 10.172.2.21 \
  --user azureuser \
  --ssh-password '<SSH_PASS>' \
  --activation-key 1-rhel9
```

**Nota**: verificare prima le opzioni disponibili:
```bash
mgrctl exec -- spacecmd -u admin -p '<ADMIN_PASS>' -- system_bootstrap --help
```

>`spacecmd system_bootstrap` usa il meccanismo salt-ssh del server (come la Web UI). E soggetto allo stesso problema di compatibilita `venv-salt-minion` / OpenSSL. Assicurarsi che il bootstrap repo contenga la versione compatibile (vedi Prerequisito 2).

### Scalabilita: loop con rate limiting

```bash
#!/bin/bash
# mass-onboard-spacecmd.sh
# Onboarding via spacecmd

ADMIN_USER="admin"
ADMIN_PASS="<ADMIN_PASS>"
SSH_USER="azureuser"
SSH_PASS="<SSH_PASS>"
AK="1-rhel9"
INVENTORY="hosts-rhel9.txt"

while IFS= read -r HOST; do
  [[ -z "$HOST" || "$HOST" =~ ^# ]] && continue

  echo "Bootstrap via spacecmd: ${HOST}..."
  mgrctl exec -- spacecmd -u "$ADMIN_USER" -p "$ADMIN_PASS" -- system_bootstrap \
    --hostname "${HOST}" \
    --user "${SSH_USER}" \
    --ssh-password "${SSH_PASS}" \
    --activation-key "${AK}"

  echo "  Attesa rate limiting (15s)..."
  sleep 15

done < "$INVENTORY"
```

### Differenze rispetto al Metodo 1

| Aspetto | Metodo 1 (SSH diretto) | Metodo 2 (spacecmd) |
|---|---|---|
| **Chi fa l'SSH** | Il tuo workstation/jump host | Il server UYUNI |
| **Parallelismo** | Controllato da te (xargs, pssh) | Sequenziale (1 alla volta) |
| **Accesso SSH necessario** | Dal workstation ai target | Dal server ai target |
| **Scalabilita** | Eccellente | Moderata |
| **Complessita** | Bassa | Media |

---

## METODO 3: API XML-RPC Python
### Test su singolo host

Creare ed eseguire lo script seguente (dal server o da qualsiasi macchina con accesso HTTPS al server UYUNI):

```python
#!/usr/bin/env python3
"""
test-xmlrpc-bootstrap.py
Test onboarding singolo host RHEL9 via API XML-RPC di UYUNI.
Il bootstrap viene eseguito dal server UYUNI via SSH verso il target.
"""

import xmlrpc.client
import ssl
import sys

# === CONFIGURAZIONE ===
UYUNI_URL = "https://uyuni-server-test.uyuni.internal/rpc/api"
ADMIN_USER = "admin"
ADMIN_PASS = "<ADMIN_PASS>"

TARGET_HOST = "10.172.2.21"
SSH_PORT = 22
SSH_USER = "azureuser"
SSH_PASS = "<SSH_PASS>"
ACTIVATION_KEY = "1-rhel9"
# === FINE CONFIGURAZIONE ===

# Connessione
ctx = ssl._create_unverified_context()
client = xmlrpc.client.ServerProxy(UYUNI_URL, context=ctx)

# Login
try:
    session = client.auth.login(ADMIN_USER, ADMIN_PASS)
    print(f"Login OK - sessione: {session[:20]}...")
except Exception as e:
    print(f"ERRORE login: {e}")
    sys.exit(1)

# Bootstrap
# NOTA: usare 0 invece di False per il parametro saltSSH (bug #4737)
try:
    result = client.system.bootstrap(
        session,
        TARGET_HOST,      # hostname/IP del target
        SSH_PORT,         # porta SSH
        SSH_USER,         # utente SSH
        SSH_PASS,         # password SSH
        ACTIVATION_KEY,   # activation key
        0                 # saltSSH: 0 = minion standard, 1 = salt-ssh
    )
    print(f"Bootstrap result: {result}")
except Exception as e:
    print(f"ERRORE bootstrap: {e}")
    print("Nota: se l'errore riguarda il tipo del parametro saltSSH,")
    print("      verificare che si stia passando 0 (int) invece di False (bool)")

# Logout
client.auth.logout(session)
print("Logout OK")
```

### Variante con chiave SSH (piu sicura, senza password)

```python
# Leggi la chiave privata
with open("/home/azureuser/.ssh/id_rsa", "r") as f:
    private_key = f.read()

result = client.system.bootstrapWithPrivateSshKey(
    session,
    "10.172.2.21",        # host
    22,                    # port
    "azureuser",           # user
    private_key,           # chiave privata PEM
    "",                    # passphrase (vuota se senza)
    "1-rhel9",             # activation key
    0                      # saltSSH
)
```

### Variante con Proxy
Se i client devono passare attraverso il proxy:

```python
# Ottenere l'ID del proxy
proxies = client.system.listSystems(session)
proxy_id = [s['id'] for s in proxies if 'proxy' in s['name'].lower()][0]
print(f"Proxy ID: {proxy_id}")

# Bootstrap attraverso il proxy
result = client.system.bootstrap(
    session,
    "10.172.2.21",
    22,
    "azureuser",
    "<SSH_PASS>",
    "1-rhel9",
    proxy_id,     # instrada attraverso il proxy
    0             # saltSSH
)
```

### Scalabilita: loop Python con rate limiting

```python
#!/usr/bin/env python3
"""
mass-onboard-xmlrpc.py
Onboarding massivo via API XML-RPC con rate limiting.
"""

import xmlrpc.client
import ssl
import time
import csv
import sys

# === CONFIGURAZIONE ===
UYUNI_URL = "https://uyuni-server-test.uyuni.internal/rpc/api"
ADMIN_USER = "admin"
ADMIN_PASS = "<ADMIN_PASS>"
SSH_PASS = "<SSH_PASS>"
DELAY = 15  # secondi tra ogni registrazione
INVENTORY_FILE = "hosts-rhel9.csv"
# === FINE CONFIGURAZIONE ===

ctx = ssl._create_unverified_context()
client = xmlrpc.client.ServerProxy(UYUNI_URL, context=ctx)
session = client.auth.login(ADMIN_USER, ADMIN_PASS)

# Formato CSV: host,activation_key,ssh_user,ssh_port
# 10.172.2.21,1-rhel9,azureuser,22
# 10.172.2.22,1-rhel9,azureuser,22

success = 0
fail = 0

with open(INVENTORY_FILE, "r") as f:
    reader = csv.reader(f)
    for row in reader:
        if not row or row[0].startswith("#"):
            continue
        host, ak, ssh_user, ssh_port = row[0], row[1], row[2], int(row[3])

        print(f"Bootstrap: {host} (AK: {ak})...", end=" ")
        try:
            result = client.system.bootstrap(
                session, host, ssh_port, ssh_user, SSH_PASS, ak, 0
            )
            print(f"OK - {result}")
            success += 1
        except Exception as e:
            print(f"ERRORE - {e}")
            fail += 1

        time.sleep(DELAY)

client.auth.logout(session)
print(f"\n=== REPORT: {success} OK, {fail} ERRORI ===")
```

---
## METODO 4: Azure VM Run Command
### Test su singolo host

#### Via Azure CLI

```bash
az vm run-command invoke \
  --resource-group <RG-NAME> \
  --name onbording-test-VM-RHEL9 \
  --command-id RunShellScript \
  --scripts "curl -Sks https://uyuni-proxy-test.uyuni.internal/pub/bootstrap/bootstrap-rhel9-proxy.sh -o /tmp/bootstrap.sh && chmod +x /tmp/bootstrap.sh && /tmp/bootstrap.sh"
```

**Nota**: Azure VM Run Command esegue come **root**, quindi non serve `sudo`.

#### Via Terraform (`azurerm_virtual_machine_run_command`)

```hcl
# Riferimento alla VM esistente
data "azurerm_virtual_machine" "rhel_test" {
  name                = "onbording-test-VM-RHEL9"
  resource_group_name = "<RG-NAME>"
}

# Esecuzione bootstrap
resource "azurerm_virtual_machine_run_command" "uyuni_bootstrap" {
  name               = "uyuni-bootstrap"
  location           = data.azurerm_virtual_machine.rhel_test.location
  virtual_machine_id = data.azurerm_virtual_machine.rhel_test.id

  source {
    script = <<-EOT
      #!/bin/bash
      curl -Sks https://uyuni-proxy-test.uyuni.internal/pub/bootstrap/bootstrap-rhel9-proxy.sh -o /tmp/bootstrap.sh
      chmod +x /tmp/bootstrap.sh
      /tmp/bootstrap.sh
    EOT
  }
}
```

### Scalabilita: tutte le VM di un Resource Group

#### Azure CLI + PowerShell (parallelo)

```powershell
# PowerShell 7
$vms = Get-AzVM -ResourceGroupName "<RG-NAME>" | Where-Object { $_.StorageProfile.OsDisk.OsType -eq "Linux" }

$vms | ForEach-Object -Parallel {
    Write-Host "Bootstrap: $($_.Name)..."
    Invoke-AzVMRunCommand -ResourceGroupName $_.ResourceGroupName `
        -VMName $_.Name `
        -CommandId 'RunShellScript' `
        -ScriptString "curl -Sks https://uyuni-proxy-test.uyuni.internal/pub/bootstrap/bootstrap-rhel9-proxy.sh -o /tmp/bootstrap.sh && chmod +x /tmp/bootstrap.sh && /tmp/bootstrap.sh"
} -ThrottleLimit 10
```

#### Azure CLI + Bash (sequenziale con rate limiting)

```bash
#!/bin/bash
# mass-onboard-azure-runcmd.sh

RG="<RG-NAME>"
PROXY_FQDN="uyuni-proxy-test.uyuni.internal"
SCRIPT="bootstrap-rhel9-proxy.sh"
DELAY=15

# Lista VM Linux nel resource group
VMS=$(az vm list -g "$RG" --query "[?storageProfile.osDisk.osType=='Linux'].name" -o tsv)

for VM in $VMS; do
  echo "Bootstrap via Azure Run Command: ${VM}..."

  az vm run-command invoke \
    --resource-group "$RG" \
    --name "$VM" \
    --command-id RunShellScript \
    --scripts "curl -Sks https://${PROXY_FQDN}/pub/bootstrap/${SCRIPT} -o /tmp/bootstrap.sh && chmod +x /tmp/bootstrap.sh && /tmp/bootstrap.sh" \
    --no-wait  # non-blocking, non aspetta il completamento

  echo "  Inviato. Attesa rate limiting (${DELAY}s)..."
  sleep "$DELAY"
done
```

#### Terraform per VM multiple esistenti

```hcl
locals {
  rhel9_vms = {
    "vm-01" = { name = "server-web-01", rg = "<RG-NAME>" }
    "vm-02" = { name = "server-web-02", rg = "<RG-NAME>" }
    "vm-03" = { name = "server-app-01", rg = "<RG-NAME>" }
    # ... aggiungere tutte le VM da onboardare
  }
}

data "azurerm_virtual_machine" "targets" {
  for_each            = local.rhel9_vms
  name                = each.value.name
  resource_group_name = each.value.rg
}

resource "azurerm_virtual_machine_run_command" "uyuni_bootstrap" {
  for_each           = data.azurerm_virtual_machine.targets
  name               = "uyuni-bootstrap"
  location           = each.value.location
  virtual_machine_id = each.value.id

  source {
    script = <<-EOT
      #!/bin/bash
      curl -Sks https://uyuni-proxy-test.uyuni.internal/pub/bootstrap/bootstrap-rhel9-proxy.sh -o /tmp/bootstrap.sh
      chmod +x /tmp/bootstrap.sh
      /tmp/bootstrap.sh
    EOT
  }
}
```

### Differenze rispetto agli altri metodi

| Aspetto | Metodo 4 (Azure Run Command) | Metodo 1 (SSH) |
|---|---|---|
| **Accesso SSH necessario** | No (usa Azure Guest Agent) | Si |
| **Funziona con Azure Bastion** | Si, nativamente | Richiede tunnel/jump host |
| **Esecuzione come** | root (default) | Dipende dall'utente SSH |
| **Logging** | Azure Activity Log + output comando | Log SSH locale |
| **Prerequisito** | Azure VM Guest Agent attivo | Chiave SSH distribuita |
| **Ideale per** | Ambienti Azure senza SSH diretto | Ambienti con SSH diretto |

---

## Tabella Comparativa Metodi

| #     | Metodo                | Via Proxy         | Richiede SSH diretto | Parallelismo      | Caso d'uso               |
| ----- | --------------------- | ----------------- | -------------------- | ----------------- | ------------------------ |
| **1** | **Bootstrap + SSH**   | Si                | Si (dal workstation) | Sì(xargs/pssh)    | **Scenario principale**  |
| **2** | **spacecmd**          | Si (nativo)       | No (dal server)      | Sequenziale       | No SSH diretto ai target |
| **3** | **API XML-RPC**       | Si (con proxy_id) | No (dal server)      | Sequenziale       | Automazione/integrazione |
| **4** | **Azure Run Command** | Si                | No (usa Guest Agent) | Buono (--no-wait) | Ambiente Azure nativo    |

