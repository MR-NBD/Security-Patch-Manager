## Prerequisiti
### Canali Software sincronizzati
Tutti i canali associati alle Activation Key devono essere completamente sincronizzati. Verificare con:
```bash
# Stato sincronizzazione (dentro il container UYUNI)
mgrctl exec -- spacewalk-repo-sync --channel <nome-canale> --type deb
```
### Bootstrap Repository generato
Il bootstrap repository contiene i pacchetti necessari per installare `salt-minion` o `venv-salt-minion` sul client durante il bootstrap. Deve essere generato **dopo** la sincronizzazione dei canali:
```bash
# Genera per tutte le distro sincronizzate
mgrctl exec -- mgr-create-bootstrap-repo --auto

# Oppure per distro specifica
mgrctl exec -- mgr-create-bootstrap-repo --create=ubuntu-24.04-amd64

# Verifica
ls /srv/www/htdocs/pub/repositories/
```

Il repo viene anche rigenerato automaticamente ogni notte dal server.

**Riferimento**: [Bootstrap Repository - Uyuni Docs](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/bootstrap-repository.html)
### Activation Keys configurate
Le Activation Key definiscono **cosa succede** quando un client si registra: canali assegnati, gruppi, configurazioni, metodo di contatto. Devono esistere **prima** del bootstrap.

Creazione: `Systems > Activation Keys > Create Key`
**Riferimento**: [Activation Keys - Uyuni Docs](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/activation-keys.html)
### Rete e DNS
- I client devono risolvere l'FQDN del server UYUNI (o entry in `/etc/hosts`)
- Le porte **4505/tcp** e **4506/tcp** devono essere raggiungibili dai client verso il server
- La porta **443/tcp** deve essere raggiungibile per il download del bootstrap script
- NTP deve essere sincronizzato (critico per certificati SSL)
### Accesso SSH ai target
La maggior parte dei metodi richiede accesso SSH (root o utente con sudo) ai sistemi target. Verificare in anticipo:
- Chiave SSH distribuita o password nota
- Porta SSH corretta (default 22)
- Firewall client che permette SSH in ingresso

## METODO UFFICIALE: Bootstrap Script + Distribuzione SSH Parallela

> **Questo è il metodo ufficialmente raccomandato da SUSE/Uyuni per l'onboarding massivo di sistemi esistenti.** Ha il miglior rapporto effort/risultato e la massima compatibilità con il workflow di registrazione UYUNI.
### Come funziona
Il flusso si compone di 3 fasi:

```
FASE 1: Generazione (una tantum sul server)
┌─────────────────────────────────────────────────┐
│ mgr-bootstrap --activation-keys=ak-ubuntu2404   │
│            --script=bootstrap-ubuntu.sh         │
│                                                 │
│  Output: /srv/www/htdocs/pub/bootstrap/         │
│          bootstrap-ubuntu.sh                    │
│                                                 │
│  Accessibile via:                               │
│  https://uyuni-server/pub/bootstrap/            │
│          bootstrap-ubuntu.sh                    │
└─────────────────────────────────────────────────┘
                        │
                        ▼
FASE 2: Distribuzione (parallela via SSH)
┌─────────────────────────────────────────────────┐
│ Per ogni host nel file inventory:               │
│                                                 │
│  ssh root@<host> "curl -Sks                     │
│    https://uyuni-server/pub/bootstrap/          │
│    bootstrap-ubuntu.sh | bash"                  │
│                                                 │
│  Lo script sul client:                          │
│  1. Importa certificato SSL del server          │
│  2. Configura i repository bootstrap            │
│  3. Installa venv-salt-minion (o salt-minion)   │
│  4. Configura il minion (master, activation key │
│  5. Avvia il servizio salt-minion               │
│  6. Il minion si connette al master (4505/4506) │
└─────────────────────────────────────────────────┘
                        │
                        ▼
FASE 3: Accettazione chiavi
┌─────────────────────────────────────────────────┐
│ Il bootstrap script con activation key gestisce │
│ automaticamente l'accettazione della chiave.    │
│                                                 │
│ Il sistema appare nella Web UI con:             │
│ - Canali assegnati (dalla activation key)       │
│ - System Groups assegnati                       │
│ - Configurazioni applicate                      │
└─────────────────────────────────────────────────┘
```
### Generazione dello script bootstrap
Esistono due modi per generare lo script:

**Via Web UI**:
1. `Admin > Manager Configuration > Bootstrap Script`
2. Configurare i parametri (hostname, activation key, GPG keys)
3. Cliccare `Update` per generare

**Via CLI**:
```bash
# Dentro il container UYUNI
mgrctl exec -- mgr-bootstrap \
  --activation-keys=ak-ubuntu2404-test \
  --script=bootstrap-ubuntu2404.sh

# Per RHEL
mgrctl exec -- mgr-bootstrap \
  --activation-keys=1-rhel9 \
  --script=bootstrap-rhel9.sh
```

Lo script generato viene pubblicato in `/srv/www/htdocs/pub/bootstrap/` e diventa accessibile via HTTPS a tutti i client.
**Parametri chiave dello script**:

| Parametro | Descrizione | Sovrascrivibile a runtime |
|---|---|---|
| `ACTIVATION_KEYS` | Chiave di attivazione | Si (variabile ambiente) |
| `MGR_SERVER_HOSTNAME` | FQDN del server | Si |
| `ORG_GPG_KEY` | Chiavi GPG per verifica pacchetti | Si |
| `REACTIVATION_KEY` | Per ri-registrare sistemi esistenti | Si |
### Distribuzione parallela
Il punto critico è **come distribuire l'esecuzione** dello script su centinaia di host contemporaneamente. Diverse opzioni, dalla più semplice alla più robusta:

**Opzione A - Bash loop semplice con `xargs`** (per 10-50 host):
```bash
# File hosts.txt: un IP/hostname per riga
cat hosts.txt | xargs -I {} -P 10 \
  ssh -o StrictHostKeyChecking=no root@{} \
  "curl -Sks https://uyuni-server/pub/bootstrap/bootstrap-ubuntu2404.sh | bash"
```

**Opzione B - `pssh` (parallel-ssh)** (per 50-500 host):
```bash
# Installa pssh
apt install pssh   # o pip install parallel-ssh

# Esegui in parallelo su tutti gli host
pssh -h hosts.txt -l root -t 600 -p 20 -o /tmp/onboard-output \
  "curl -Sks https://uyuni-server/pub/bootstrap/bootstrap-ubuntu2404.sh -o /tmp/bootstrap.sh && bash /tmp/bootstrap.sh"
```

Parametri `pssh`:
- `-h hosts.txt` - file con lista host
- `-l root` - utente SSH
- `-t 600` - timeout 600 secondi per host
- `-p 20` - 20 connessioni parallele
- `-o /tmp/output` - directory per output per-host

**Opzione C - `pdsh`** (per ambienti HPC/datacenter):
```bash
# Con lista host
pdsh -w ^hosts.txt -l root \
  "curl -Sks https://uyuni-server/pub/bootstrap/bootstrap-ubuntu2404.sh | bash"
```

**Opzione D - Script Bash strutturato** (per 100-1000+ host, con logging e gestione errori):

Uno script personalizzato che gestisce:
- Lettura da file inventory CSV (host, activation_key, ssh_user, ssh_port)
- Parallelismo controllato (es. 10-20 job contemporanei)
- Pre-check connettività SSH prima del bootstrap
- Logging per-host in file separati
- Report finale con successi/fallimenti
- Rate limiting per non sovraccaricare il server
### Rate limiting: la regola dei 15 secondi
La documentazione ufficiale UYUNI per i large deployment stabilisce un guideline fondamentale:

> **Safe starting point: 1 client ogni 15 secondi** (4 al minuto, ~240 all'ora)

Questo perché ogni registrazione comporta:
1. Handshake PKI (generazione chiavi RSA 4096-bit, scambio, accettazione)
2. Sync iniziale dei grains
3. Registrazione nel database PostgreSQL
4. Assegnazione canali e gruppi
5. Eventuale highstate iniziale

Con 20 job SSH paralleli e rate limiting, 1000 host richiedono circa **4-5 ore** di onboarding. Questo è il compromesso tra velocità e stabilità del server.

**Nota sull'entropia**: La crittografia asimmetrica di Salt richiede entropia di sistema sufficiente. In ambienti virtualizzati (come Azure), verificare:
```bash
cat /proc/sys/kernel/random/entropy_avail
# Deve essere > 200. Se basso, installare haveged o rng-tools
```
### Gestione di ambienti misti (Ubuntu + RHEL)
Per onboarding misto, servono **script bootstrap separati** per ogni OS, ma il processo è identico. L'inventory deve specificare quale activation key (e quindi quale bootstrap script) usare per ogni host:

```csv
# inventory.csv
# host,activation_key,os_type,ssh_user,ssh_port
10.172.3.10,ak-ubuntu2404-test,ubuntu,root,22
10.172.3.11,ak-ubuntu2404-test,ubuntu,root,22
10.172.3.50,1-rhel9,rhel,azureuser,22
10.172.3.51,1-rhel9,rhel,azureuser,22
```

Il loop di distribuzione seleziona lo script corretto in base all'`os_type`:
```bash
# Pseudocodice
if os_type == "ubuntu":
    script = "bootstrap-ubuntu2404.sh"
elif os_type == "rhel":
    script = "bootstrap-rhel9.sh"
```
### Verifica post-onboarding
Dopo il bootstrap, verificare che tutti i sistemi siano registrati correttamente:

```bash
# Lista chiavi accettate
mgrctl exec -- salt-key -l accepted

# Ping di tutti i minion
mgrctl exec -- salt '*' test.ping

# Verifica nella Web UI
# Systems > System List > All - devono apparire tutti i client registrati
```
### Perché questo è il metodo migliore

| Aspetto                 | Valutazione                                                 |
| ----------------------- | ----------------------------------------------------------- |
| **Supporto ufficiale**  | Metodo raccomandato da SUSE per mass onboarding             |
| **Compatibilità UYUNI** | Registrazione completa: DB, Web UI, canali, gruppi, CLM     |
| **Effort di setup**     | Basso - lo script bootstrap è già generabile con un comando |
| **Dipendenze esterne**  | Nessuna - solo SSH e curl (presenti ovunque)                |
| **Sicurezza**           | Alta - usa il workflow PKI standard di Salt                 |
| **Flessibilità**        | Funziona con qualsiasi OS supportato, con o senza proxy     |
| **Debugging**           | Semplice - ogni host ha il suo output/log                   |

**Riferimenti ufficiali**:
- [Register Clients With a Bootstrap Script](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/registration-bootstrap.html)
- [Bootstrap Script Reference](https://www.uyuni-project.org/uyuni-docs/en/uyuni/reference/admin/bootstrap-script.html)
- [Bootstrapping CLI Tools (mgr-bootstrap)](https://www.uyuni-project.org/uyuni-docs/en/uyuni/reference/cli-bootstrap.html)
- [Client Onboarding Workflow](https://www.uyuni-project.org/uyuni-docs/en/uyuni/common-workflows/workflow-client-onboarding.html)
## METODO COMPLEMENTARE: Terraform per Onboarding su Azure

> **Terraform può gestire sia nuove VM che VM già esistenti.** Per le nuove, cloud-init esegue il bootstrap al primo boot. Per le esistenti, Azure VM Run Command e Custom Script Extension permettono di eseguire il bootstrap senza nemmeno accesso SSH diretto.

### Scenario A: Nuove VM (Cloud-Init)
Cloud-init è un servizio standard presente nelle immagini cloud (Ubuntu, RHEL, SUSE) che esegue comandi personalizzati al primo avvio della VM. Inserendo il comando di bootstrap nel `user_data` della VM, la registrazione su UYUNI avviene automaticamente.

```
Terraform / ARM Template
         │
         │  user_data = "#!/bin/bash\n curl ... | bash"
         │
         ▼
   Azure crea la VM
         │
         ▼
   VM si avvia per la prima volta
         │
         ▼
   cloud-init esegue il bootstrap script
         │
         ▼
   salt-minion si connette a UYUNI Server
         │
         ▼
   Sistema registrato automaticamente
```
### Implementazione con Terraform
```hcl
resource "azurerm_linux_virtual_machine" "client" {
  count               = 100  # Numero di VM da creare
  name                = "client-${count.index + 1}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  size                = "Standard_B2s"

  # ... configurazione network, disco, immagine ...

  custom_data = base64encode(<<-EOF
    #!/bin/bash
    # Onboarding automatico su UYUNI
    curl -Sks https://uyuni-server-test.uyuni.internal/pub/bootstrap/bootstrap-ubuntu2404.sh -o /tmp/bootstrap.sh
    chmod +x /tmp/bootstrap.sh
    /tmp/bootstrap.sh
  EOF
  )
}
```
### Implementazione con Azure CLI
```bash
az vm create \
  --resource-group myRG \
  --name client-01 \
  --image Canonical:ubuntu-24_04-lts:server:latest \
  --custom-data cloud-init-bootstrap.yaml \
  --size Standard_B2s
```
Dove `cloud-init-bootstrap.yaml`:
```yaml
#cloud-config
runcmd:
  - curl -Sks https://uyuni-server-test.uyuni.internal/pub/bootstrap/bootstrap-ubuntu2404.sh -o /tmp/bootstrap.sh
  - chmod +x /tmp/bootstrap.sh
  - /tmp/bootstrap.sh
```
### Vantaggi e limiti

| Vantaggi | Limiti |
|---|---|
| Zero intervento post-creazione VM | Cloud-init esegue **solo al primo boot** |
| Scala a qualsiasi numero di VM | Modificare `user_data` in Terraform **distrugge e ricrea** la VM |
| Nessun accesso SSH necessario dal workstation | Richiede che UYUNI Server sia raggiungibile al boot |
| Integrazione nativa con IaC pipeline | Non applicabile a sistemi già esistenti |
| Ogni VM si registra indipendentemente | |

### Quando usare questo metodo
- **Nuove VM Azure** create tramite Terraform, ARM templates, o Azure CLI
- **Scale-out automatico** (es. VMSS - Virtual Machine Scale Sets)
- **Pipeline IaC** dove l'infrastruttura è definita come codice

Per sistemi già esistenti e in esecuzione, vedere lo Scenario B qui sotto.

### Scenario B: VM Già Esistenti su Azure (Terraform)
Questo è lo scenario più rilevante per chi ha già centinaia di VM in esecuzione e vuole registrarle su UYUNI senza ricrearle. Esistono **3 risorse Terraform** per eseguire script su VM Azure esistenti, tutte funzionanti tramite il **control plane Azure** (non richiedono accesso SSH diretto dalla workstation).

#### B1. `azurerm_virtual_machine_run_command` (Metodo consigliato)
Risorsa Terraform più recente e flessibile. Esegue comandi su VM esistenti tramite l'Azure Guest Agent, senza bisogno di SSH.

```hcl
# Definizione delle VM esistenti da onboardare
locals {
  existing_vms = {
    "web-01"  = { name = "server-web-01",  rg = "prod-rg" }
    "web-02"  = { name = "server-web-02",  rg = "prod-rg" }
    "db-01"   = { name = "server-db-01",   rg = "prod-rg" }
    "app-01"  = { name = "server-app-01",  rg = "staging-rg" }
    # ... 
  }
}

# Riferimento alle VM esistenti (data source, non crea nulla)
data "azurerm_virtual_machine" "targets" {
  for_each            = local.existing_vms
  name                = each.value.name
  resource_group_name = each.value.rg
}

# Esecuzione del bootstrap su tutte le VM
resource "azurerm_virtual_machine_run_command" "uyuni_bootstrap" {
  for_each           = data.azurerm_virtual_machine.targets
  name               = "uyuni-bootstrap"
  location           = each.value.location
  virtual_machine_id = each.value.id

  source {
    script = <<-EOT
      #!/bin/bash
      curl -Sks https://uyuni-server-test.uyuni.internal/pub/bootstrap/bootstrap-ubuntu2404.sh -o /tmp/bootstrap.sh
      chmod +x /tmp/bootstrap.sh
      /tmp/bootstrap.sh
    EOT
  }

  # Opzionale: cattura output in Azure Blob Storage
  # output_blob_uri = azurerm_storage_blob.output.url
  # error_blob_uri  = azurerm_storage_blob.errors.url
}
```

**Caratteristiche**:
- Usa il **control plane Azure** (non SSH) - funziona anche senza accesso SSH dalla workstation
- Richiede solo che l'**Azure VM Guest Agent** sia attivo sulla VM 
- Supporta `script` inline, `script_uri` remoto, o `command_id` predefinito
- Output catturabile in Azure Blob Storage per debugging
- Con `for_each` si possono onboardare centinaia di VM in un singolo `terraform apply`

**Riferimento**: [azurerm_virtual_machine_run_command](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/virtual_machine_run_command)

####  `azurerm_virtual_machine_extension` (Custom Script Extension)
Approccio consolidato, usa la Custom Script Extension di Azure:

```hcl
data "azurerm_virtual_machine" "existing" {
  name                = "server-web-01"
  resource_group_name = "prod-rg"
}

resource "azurerm_virtual_machine_extension" "uyuni_bootstrap" {
  name                 = "uyuni-bootstrap"
  virtual_machine_id   = data.azurerm_virtual_machine.existing.id
  publisher            = "Microsoft.Azure.Extensions"
  type                 = "CustomScript"
  type_handler_version = "2.1"

  protected_settings = jsonencode({
    commandToExecute = "curl -Sks https://uyuni-server-test.uyuni.internal/pub/bootstrap/bootstrap-ubuntu2404.sh -o /tmp/bootstrap.sh && chmod +x /tmp/bootstrap.sh && /tmp/bootstrap.sh && exit 0"
  })
}
```

**Note**:
- **Una sola extension** di tipo `CustomScript` per VM (se ne esiste già una, va rimossa prima)
- Il comando deve terminare con `exit 0` per evitare che Azure lo consideri fallito

**Riferimento**: [azurerm_virtual_machine_extension](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/virtual_machine_extension)

#### B3. `null_resource` + `remote-exec` (via SSH)

Per esecuzione via SSH diretto (quando si preferisce non usare l'Azure control plane):

```hcl
resource "null_resource" "uyuni_bootstrap" {
  for_each = toset(["10.172.3.10", "10.172.3.11", "10.172.3.12"])

  triggers = {
    run_once = "bootstrap-v1"
  }

  connection {
    type        = "ssh"
    host        = each.value
    user        = "root"
    private_key = file("~/.ssh/id_rsa")
  }

  provisioner "remote-exec" {
    inline = [
      "curl -Sks https://uyuni-server-test.uyuni.internal/pub/bootstrap/bootstrap-ubuntu2404.sh -o /tmp/bootstrap.sh",
      "chmod +x /tmp/bootstrap.sh",
      "/tmp/bootstrap.sh"
    ]
  }
}
```

**Note**: Richiede accesso SSH diretto. Supporta bastion host nel blocco `connection`. I provisioner sono considerati "last resort" da HashiCorp.
#### B4. Azure CLI senza Terraform (`az vm run-command invoke`)
Per un one-shot rapido senza infrastruttura Terraform:

```bash
# Singola VM
az vm run-command invoke \
  --resource-group prod-rg \
  --name server-web-01 \
  --command-id RunShellScript \
  --scripts "curl -Sks https://uyuni-server/pub/bootstrap/bootstrap-ubuntu2404.sh | bash"

# Tutte le VM di un resource group (PowerShell 7, parallelo)
$vms = Get-AzVM -ResourceGroupName "prod-rg"
$vms | ForEach-Object -Parallel {
    Invoke-AzVMRunCommand -ResourceGroupName $_.ResourceGroupName `
        -VMName $_.Name `
        -CommandId 'RunShellScript' `
        -ScriptString "curl -Sks https://uyuni-server/pub/bootstrap/bootstrap-ubuntu2404.sh | bash"
} -ThrottleLimit 10
```

**Riferimento**: [Run Command Overview - Microsoft Learn](https://learn.microsoft.com/en-us/azure/virtual-machines/run-command-overview)
### sumaform: il tool Terraform ufficiale di UYUNI
[sumaform](https://github.com/uyuni-project/sumaform) è il set di moduli Terraform mantenuto dal progetto UYUNI. Scoperta dalla ricerca: **sumaform supporta VM già esistenti** tramite il backend SSH.
#### Architettura sumaform
sumaform separa 3 livelli:

1. **Backend modules** (`backend_modules/`) - infrastruttura provider-specifica
2. **Frontend modules** (`modules/`) - componenti logici (server, minion, client, proxy) - 23 moduli
3. **Salt states** - configurazione software applicata via Salt dopo il provisioning

Il backend si seleziona con un symlink:
```bash
ln -sfn ../backend_modules/ssh modules/backend   # Per macchine esistenti
ln -sfn ../backend_modules/azure modules/backend  # Per Azure
```
#### I 6 backend disponibili

| Backend | Scopo | VM esistenti? | Stato |
|---|---|---|---|
| **Libvirt** | KVM locale/remoto | No (crea VM) | Raccomandato |
| **SSH** | **Macchine già esistenti** | **Si** | Supportato |
| **Azure** | Microsoft Azure | No (crea VM) | In manutenzione |
| **AWS** | Amazon Web Services | No (crea VM) | In manutenzione |
| **Feilong** | IBM z/VM mainframe | No (crea VM) | Supportato |
| **Null** | Solo test configurazione | N/A | Supportato |
#### Backend SSH per macchine esistenti
Il backend SSH è **esplicitamente progettato per macchine pre-esistenti**. Dalla documentazione: *"assumes hosts already exist and can be accessed via SSH, thus configuring them for desired roles."*

```hcl
# main.tf con backend SSH

module "base" {
  source      = "./modules/base"
  private_key = file("~/.ssh/id_rsa")
}

module "server" {
  source             = "./modules/server"
  base_configuration = module.base.configuration
  name               = "uyuni-server"
  product_version    = "5.0-released"
  create_sample_activation_key    = true
  create_sample_bootstrap_script  = true
  auto_accept                     = true
  provider_settings = {
    host = "10.172.2.17"
    user = "root"
  }
}

module "ubuntu_clients" {
  source             = "./modules/minion"
  base_configuration = module.base.configuration
  name               = "ubuntu-client"
  image              = "ubuntu2404"
  server_configuration    = module.server.configuration
  auto_connect_to_master  = true
  provider_settings = {
    host = "10.172.3.10"
    user = "root"
  }
}
```
#### Variabili chiave

| Variabile | Modulo | Scopo |
|---|---|---|
| `auto_connect_to_master` | minion | Connette il salt-minion al master |
| `auto_register` | client, proxy | Auto-registra il sistema (default: `true`) |
| `auto_accept` | server | Accetta automaticamente le chiavi Salt |
| `create_sample_activation_key` | server | Genera activation key |
| `create_sample_bootstrap_script` | server | Genera bootstrap script |
| `quantity` | minion, client | Numero di istanze |
#### Limitazioni di sumaform per produzione

| Limitazione | Impatto | Mitigazione |
|---|---|---|
| **Salt deve essere pre-installato** | Il backend SSH non installa Salt | Installare prima o usare bootstrap script |
| **Nessun inventario dinamico** | Ogni macchina va elencata in `provider_settings` | Generare `main.tf` da CSV/CMDB |
| **Design orientato al test** | Password default, sicurezza non prioritaria | Personalizzare credenziali |
| **Un host per blocco** | Scalabilità limitata | Creare moduli separati per gruppi |
#### Verdetto su sumaform

Sumaform è potente per **test e sviluppo**, ma per onboarding **produttivo di 100-1000 macchine** presenta friction: inventario statico, modello "1 blocco per host", design orientato ai test.

**Raccomandazione**: Usare sumaform come **riferimento architetturale**, ma per la produzione preferire `azurerm_virtual_machine_run_command` o Bootstrap Script + SSH parallelo.

**Riferimenti**:
- [sumaform su GitHub](https://github.com/uyuni-project/sumaform)
- [sumaform SSH Backend](https://github.com/uyuni-project/sumaform/blob/master/backend_modules/ssh/README.md)
- [sumaform DESIGN.md](https://github.com/uyuni-project/sumaform/blob/master/DESIGN.md)
- [Automatic Client Registration](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/automatic-client-registration.html)
- [Clients on Public Cloud](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/clients-pubcloud.html)
### Nota: Non esiste un Terraform Provider per UYUNI

Non esiste un provider Terraform dedicato che wrappa l'API XML-RPC di UYUNI. La registrazione deve sempre passare attraverso il bootstrap script o la connessione Salt minion. L'unico provider SUSE-related (`SUSE/susepubliccloud`) serve solo a trovare immagini SUSE nei cloud.
## METODO: spacecmd / API XML-RPC

> **Utile quando non si ha accesso SSH diretto ai client dal proprio workstation, ma si ha accesso al server UYUNI.** Il server stesso si connette via SSH ai target.

### spacecmd (CLI)
`spacecmd` è un tool CLI Python installato di default sul server UYUNI. Wrappa l'API XML-RPC in comandi leggibili.

**Bootstrap singolo host**:
```bash
mgrctl exec -- spacecmd -- system_bootstrap \
  --hostname 10.172.3.10 \
  --ssh-password 'PASSWORD' \
  --activation-key ak-ubuntu2404-test
```

**Bootstrap in loop da file**:
```bash
while IFS=',' read -r host ak; do
  echo "Bootstrap: ${host} con chiave ${ak}..."
  mgrctl exec -- spacecmd -u admin -p 'ADMIN_PASS' -- system_bootstrap \
    --hostname "${host}" \
    --ssh-password "${SSH_PASS}" \
    --activation-key "${ak}"
  sleep 15  # Rate limiting
done < hosts.csv
```
### API XML-RPC (Python)
Per maggiore controllo, si può usare direttamente l'API XML-RPC con Python:

```python
import xmlrpc.client
import time

UYUNI_URL = "https://uyuni-server-test.uyuni.internal/rpc/api"
client = xmlrpc.client.ServerProxy(UYUNI_URL, context=ssl._create_unverified_context())

# Login
session = client.auth.login("admin", "password")

# Lista host da onboardare
hosts = [
    {"host": "10.172.3.10", "key": "ak-ubuntu2404-test"},
    {"host": "10.172.3.11", "key": "ak-ubuntu2404-test"},
    {"host": "10.172.3.50", "key": "1-rhel9"},
]

for h in hosts:
    try:
        result = client.system.bootstrap(
            session,
            h["host"],    # hostname/IP
            22,           # SSH port
            "root",       # SSH user
            "password",   # SSH password
            h["key"],     # activation key
            False         # saltSSH (False = minion standard)
        )
        print(f"OK: {h['host']} -> {result}")
    except Exception as e:
        print(f"ERRORE: {h['host']} -> {e}")
    time.sleep(15)  # Rate limiting

client.auth.logout(session)
```

**Variante con chiave SSH** (più sicura):
```python
# Leggi la chiave privata
with open("/root/.ssh/id_rsa", "r") as f:
    private_key = f.read()

result = client.system.bootstrapWithPrivateSshKey(
    session,
    "10.172.3.10",       # host
    22,                   # port
    "root",               # user
    private_key,          # chiave privata PEM
    "",                   # passphrase (vuota se senza)
    "ak-ubuntu2404-test", # activation key
    False                 # saltSSH
)
```
### API Bootstrap con Proxy
Se i client passano attraverso un UYUNI Proxy, usare l'overload con `proxyId`:

```python
# Ottenere l'ID del proxy
proxies = client.system.listSystems(session)
proxy_id = [s['id'] for s in proxies if 'proxy' in s['name'].lower()][0]

# Bootstrap attraverso il proxy
result = client.system.bootstrap(
    session,
    "10.172.3.10",
    22,
    "root",
    "password",
    "ak-ubuntu2404-test",
    proxy_id,             # instrada attraverso il proxy
    False
)
```
### Confronto: SSH diretto vs API Bootstrap

| Aspetto             | Bootstrap Script via SSH        | API system.bootstrap                   |
| ------------------- | ------------------------------- | -------------------------------------- |
| **Chi fa l'SSH**    | Il tuo workstation/jump host    | Il server UYUNI                        |
| **Parallelismo**    | Controllato da te (xargs, pssh) | Sequenziale (1 alla volta dal server)  |
| **Scalabilità**     | Eccellente (parallelo)          | Moderata (server è collo di bottiglia) |
| **Requisiti rete**  | SSH dal workstation ai target   | SSH dal server ai target               |
| **Effort**          | Basso                           | Medio (scripting Python/Bash)          |
| **Uso consigliato** | Scenario principale             | Quando non hai SSH diretto ai target   |
### Issue nota
C'è un bug storico ([#4737](https://github.com/uyuni-project/uyuni/issues/4737)) con il tipo del parametro `saltSSH`: alcune versioni richiedono `0`/`1` (int) invece di `True`/`False` (boolean). Se il bootstrap via API fallisce, provare a passare `0` invece di `False`.

**Riferimenti**:
- [Uyuni API - system namespace](https://www.uyuni-project.org/uyuni-docs-api/uyuni/api/system.html)
- [spacecmd Reference](https://www.uyuni-project.org/uyuni-docs/en/uyuni/reference/spacecmd-intro.html)
- [API Sample Scripts](https://documentation.suse.com/suma/4.3/api/suse-manager/api/scripts.html)
## Meccanismi Salt per Auto-Accept delle Chiavi

Quando un salt-minion si connette al master per la prima volta, genera una coppia di chiavi RSA 4096-bit e invia la chiave pubblica al master. L'amministratore deve **accettare** la chiave affinché la comunicazione cifrata venga stabilita.

Con il Metodo Primario (bootstrap script + activation key), **l'accettazione è automatica** perché l'activation key autorizza il processo. Tuttavia, esistono meccanismi Salt aggiuntivi per gestire l'accettazione a livello di Salt master. Questi possono essere utili in scenari specifici ma hanno **importanti limitazioni nell'integrazione con UYUNI**.
### Autosign Grains (Shared Secret)
Questo è l'unico meccanismo di auto-accept **ufficialmente documentato da UYUNI** (nel contesto Retail/terminali).

**Come funziona**: Il master accetta automaticamente i minion che presentano un grain con un valore segreto concordato.

**Configurazione master** (dentro il container: `mgrctl term`):
```yaml
# /etc/salt/master.d/autosign_grains.conf
autosign_grains_dir: /etc/salt/autosign_grains
```

```
# /etc/salt/autosign_grains/autosign_key
mio-segreto-onboarding-2024
```

**Configurazione minion** (pre-installazione o in golden image):
```yaml
# /etc/salt/minion.d/autosign.conf
autosign_grains:
  - autosign_key

grains:
  autosign_key: mio-segreto-onboarding-2024
```

**Single-use grains**: UYUNI Retail supporta grains monouso che vengono cancellati dopo il primo utilizzo, migliorando significativamente la sicurezza.

**Quando usare**: Se si preparano golden image (AMI, template VM) con salt-minion pre-installato e si vuole che l'accettazione sia istantanea senza passare dal bootstrap script.

**Limitazione**: Richiede che il client abbia già `salt-minion` installato e configurato. Non sostituisce il bootstrap, ma complementa l'accettazione chiavi.

**Riferimento**: [Deploy Terminals and Auto-Accept Keys](https://www.uyuni-project.org/uyuni-docs/en/uyuni/retail/retail-deploy-terminals-auto.html)
### Salt Reactor (Event-Driven)
**Come funziona**: Il Reactor intercetta gli eventi `salt/auth` sul bus eventi e accetta condizionalmente le chiavi.

**Configurazione**:

```yaml
# /etc/salt/master.d/reactor.conf
reactor:
  - 'salt/auth':
    - /srv/reactor/auto-accept.sls
```

```yaml
# /srv/reactor/auto-accept.sls
# Accetta solo minion il cui ID inizia con "prod-"
{% if 'act' in data and data['act'] == 'pend' and data['id'].startswith('prod-') %}
accept_key:
  wheel.key.accept:
    - args:
      - match: {{ data['id'] }}
{% endif %}
```

**Problema critico con UYUNI**: Accettare una chiave Salt tramite reactor **non completa la registrazione nel database UYUNI**. Il minion viene accettato da Salt, ma potrebbe **non apparire nella Web UI** né avere canali e gruppi assegnati. Per una registrazione completa, è necessario che il client passi attraverso il bootstrap script con activation key.

**Quando usare**: Solo come strato aggiuntivo in scenari dove il bootstrap è già stato eseguito ma l'accettazione chiavi deve essere automatizzata per qualche motivo.

**Riferimento**: [Salt Reactor System](https://docs.saltproject.io/en/latest/topics/reactor/index.html)

### `auto_accept: True` (Non Sicuro diciamo)

```yaml
# /etc/salt/master.d/auth.conf
auto_accept: True
```

**Sicurezza**: La documentazione Salt stessa avverte: *"Automatically accepting keys is very dangerous. It is generally not advised unless operating in a safe test environment."*

Ogni macchina che raggiunge le porte 4505/4506 viene accettata senza filtri. Inoltre:
- Bypassa il workflow di registrazione UYUNI
- Quando `auto_accept: True` è attivo, gli eventi `salt/auth` **NON vengono emessi**, rendendo impossibile l'uso contemporaneo del Reactor
- Utilizzare **solo** in ambienti di test completamente isolati
### Preseed Keys (Pre-generazione)
**Come funziona**: Si generano le chiavi del minion **sul master** prima che il client si connetta, poi si distribuiscono le chiavi private al client.

```bash
# Sul master: genera coppia chiavi per un host
salt-key --gen-keys=client-web-01

# Copia la pubblica tra le chiavi accettate
cp client-web-01.pub /etc/salt/pki/master/minions/client-web-01

# Distribuisci la privata al client (via provisioning, cloud-init, ecc.)
# /etc/salt/pki/minion/minion.pem e minion.pub
```

**Quando usare**: In pipeline di provisioning dove si ha controllo completo sulla creazione della VM e si può iniettare la chiave durante il setup.

**Riferimento**: [Preseed Minion with Accepted Key](https://docs.saltproject.io/en/latest/topics/tutorials/preseed_key.html)
### Nota importante: Bootstrap Script gestisce già l'accettazione
Con il **Metodo Primario** (bootstrap script + activation key), **non è necessario nessuno di questi meccanismi aggiuntivi**. Il bootstrap script, quando usato con un'activation key valida, gestisce automaticamente:
1. Installazione salt-minion
2. Configurazione del master
3. Generazione chiavi
4. Registrazione e accettazione nel database UYUNI

I meccanismi di questa sezione sono utili solo per scenari non standard (golden image, provisioning custom, ambienti retail).
## Integrazioni con Tool Esterni

### Ansible + Bootstrap Script
Se l'organizzazione utilizza già Ansible, è possibile orchestrare il bootstrap tramite playbook.

**Ansible Collection community**: [stdevel.uyuni](https://github.com/stdevel/ansible-collection-uyuni) su Ansible Galaxy
- Include un role `client` per la registrazione
- Dynamic Inventory Plugin che legge i client da UYUNI
- Community-driven (non ufficiale SUSE), ma maturo e mantenuto

**Esempio playbook semplice** (senza collection):

```yaml
- hosts: uyuni_clients
  become: yes
  vars:
    uyuni_server: "uyuni-server-test.uyuni.internal"
    bootstrap_script: "bootstrap-ubuntu2404.sh"
  tasks:
    - name: Download bootstrap script
      get_url:
        url: "https://{{ uyuni_server }}/pub/bootstrap/{{ bootstrap_script }}"
        dest: /tmp/bootstrap.sh
        mode: '0755'
        validate_certs: no

    - name: Execute bootstrap
      command: /tmp/bootstrap.sh
      register: bootstrap_result
      changed_when: bootstrap_result.rc == 0

    - name: Verify salt-minion is running
      service:
        name: venv-salt-minion
        state: started
        enabled: yes
```

**Vantaggi**:
- Parallelismo nativo (configurabile con `forks` in `ansible.cfg`)
- Gestione avanzata degli errori e retry
- Inventario dinamico e grouping
- Idempotenza

**Svantaggi**:
- Richiede infrastruttura Ansible funzionante
- La collection è community, non ufficiale SUSE
- Layer aggiuntivo di complessità

**Quando usare**: Se Ansible è già in uso nell'organizzazione. Non ha senso introdurlo solo per l'onboarding UYUNI.

**Riferimenti**:
- [Uyuni Ansible Integration](https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/ansible-integration.html)
- [Uyuni Ansible Collection Blog](https://cstan.io/en/post/2023/10/uyuni-ansible-collection/)

### Cobbler / AutoYaST / Kickstart (PXE Provisioning)
Per il provisioning bare-metal di nuovi server tramite PXE boot.

**Come funziona**:
1. Si creano profili di autoinstallazione (AutoYaST per SUSE, Kickstart per RHEL)
2. Si inserisce lo snippet `$SNIPPET('spacewalk/minion_script')` nel profilo
3. I server fanno PXE boot, installano l'OS, e si registrano automaticamente su UYUNI

**Effort**: Alto (Cobbler, DHCP, TFTP, profili). Giustificato solo per rollout data center bare-metal.

**Nota**: Cobbler è tecnologia legacy. Nelle nuove versioni di UYUNI l'enfasi è ridotta.

**Riferimento**: [Autoinstallation Profiles](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/autoinst-profiles.html)

## Metodi Standard
### Web UI Bootstrap (Systems > Bootstrapping)
**Non scala**. Un host alla volta, inserimento manuale. Utile solo per test o host singoli.
### Salt SSH Push come metodo primario

La documentazione ufficiale è esplicita: *"The Push SSH method is not at all supported with large setups (1000 clients and more)."* Ogni operazione richiede una sessione SSH completa e il deploy del pacchetto Salt thin. Issue nota di starvation: [#3182](https://github.com/uyuni-project/uyuni/issues/3182).

**Uso legittimo**: DMZ, sistemi in ambienti con firewall restrittivo dove le porte 4505/4506 non possono essere aperte. In questo caso, usarlo solo per quel sottoinsieme di host.

### Hub Architecture (Multi-Server)

Architettura per **10.000+ client** con Hub che coordina più server UYUNI periferici. Eccessivo per 100-1000 client. Da considerare solo se la crescita prevista supera i 5000 sistemi.

**Riferimento**: [Hub XMLRPC API Deployment](https://documentation.suse.com/suma/5.0/en/suse-manager/specialized-guides/large-deployments/hub-install.html)
### Salt Cloud
Modulo Salt per provisioning cloud. **Non integrato con UYUNI**. UYUNI non include salt-cloud e non ha un modulo di provisioning. Il progetto UYUNI usa Terraform (sumaform), non Salt Cloud.
## Tuning del Server per Onboarding su Larga Scala

Prima di onboardare centinaia di client, è fondamentale tuning il server UYUNI. I valori di default sono dimensionati per deployment piccoli.

**Riferimento principale**: [Tuning Large Scale Deployments](https://www.uyuni-project.org/uyuni-docs/en/uyuni/specialized-guides/large-deployments/tuning.html)

### Salt Master

File: `/etc/salt/master.d/tuning.conf` (dentro il container)

| Parametro | Default | 100-500 client | 500-1000 client | 1000+ client |
|---|---|---|---|---|
| `worker_threads` | 8 | 8 | 16 | 16-32 |
| `pub_hwm` | 1000 | 10.000 | 50.000 | 100.000 |
| `zmq_backlog` | 1000 | 1.000 | 3.000 | 5.000 |
| `auth_events` | True | True | False | **False** |
| `minion_data_cache_events` | True | True | False | **False** |

> **Nota**: Ogni `worker_thread` consuma ~70 MB di RAM. Con 32 thread = ~2.2 GB solo per i worker.
### PostgreSQL

File: `postgresql.conf` (dentro il container database)

| Parametro | Raccomandazione |
|---|---|
| `shared_buffers` | 25-40% della RAM totale |
| `effective_cache_size` | ~75% della RAM totale |
| `work_mem` | 2-20 MB |
| `max_connections` | 400 (default, sufficiente) |
### Java / Tomcat

| Parametro | Default | Large Scale |
|---|---|---|
| Tomcat `-Xmx` | 1 GiB | 4-8 GiB |
| `maxThreads` | 150 | >= MaxRequestWorkers Apache |

### 10.4 Taskomatic

File: `/etc/rhn/rhn.conf`

| Parametro | Default | Large Scale |
|---|---|---|
| `java.message_queue_thread_pool_size` | 5 | 50-150 |
| `java.salt_batch_size` | 200 | 200-500 |
| `java.salt_event_thread_pool_size` | 8 | 20-100 |
| `taskomatic.java.maxmemory` | 4096 MiB | 8.192-16.384 MiB |
| `org.quartz.threadPool.threadCount` | 20 | 20-200 |
### Apache httpd

| Parametro | Default | Large Scale |
|---|---|---|
| `MaxRequestWorkers` | 150 | 150-500 |
| `ServerLimit` | - | = MaxRequestWorkers |
### Sistema operativo

| Parametro | Raccomandazione |
|---|---|
| `vm.swappiness` | 10 (per server con 64+ GB RAM) |
| Entropy | Installare `haveged` o `rng-tools` in ambienti virtualizzati |
| Filesystem | XFS per `/var/spacewalk` e `/var/lib/pgsql` |
| I/O Scheduler | `none` (noop) per VM su SSD |
### Segnali di allarme (quando tuning è necessario)

| Sintomo | Causa probabile | Parametro da aumentare |
|---|---|---|
| Errori `AH00161` nei log Apache | MaxRequestWorkers esaurito | `MaxRequestWorkers` |
| `OutOfMemoryException` in Tomcat | Heap insufficiente | Tomcat `-Xmx` |
| Timeout Salt durante picchi | Worker insufficienti | `worker_threads`, `pub_hwm` |
| Rigenerazione metadati canali lenta | Thread Taskomatic insufficienti | `threadPool.threadCount` |
| Onboarding lento/fallimentare | Rate troppo alto | Aumentare intervallo tra registrazioni |
### Hardware consigliato

| Risorsa | 100 client | 500 client | 1000+ client |
|---|---|---|---|
| CPU | 4 core | 8 core | 8-16 core |
| RAM | 16 GB | 32 GB | 64+ GB |
| Disco OS | 64 GB SSD | 64 GB SSD | 100 GB SSD |
| Disco Repository | 256 GB | 500 GB | 1+ TB |
| Disco PostgreSQL | 64 GB | 100 GB | 200+ GB |
## Tabella Comparativa Finale

| # | Metodo | 100 host | 1000 host | Effort | Sicurezza | Supporto SUSE | Caso d'uso |
|---|--------|----------|-----------|--------|-----------|---------------|------------|
| **1** | **Bootstrap Script + SSH** | ★★★★★ | ★★★★★ | **Basso** | Alta | **Ufficiale** | **Scenario principale** |
| **2** | **Terraform + Cloud-Init** | ★★★★★ | ★★★★★ | Medio | Alta | **Ufficiale** | **Nuove VM Azure** |
| 3 | spacecmd / API XML-RPC | ★★★★ | ★★★ | Medio | Alta | Ufficiale | No SSH diretto ai target |
| 4 | Ansible + Bootstrap | ★★★★★ | ★★★★★ | Medio | Alta | Community | Se Ansible è già in uso |
| 5 | Autosign Grains | ★★★★ | ★★★★★ | Medio | Media-Alta | Ufficiale (Retail) | Golden image, PXE |
| 6 | CLI minion config | ★★★ | ★★★★ | Alto | Alta | Ufficiale | Golden image |
| 7 | Salt Reactor | ★★★★ | ★★★★ | Medio | Media | Non documentato | Scenari avanzati |
| 8 | Preseed Keys | ★★★ | ★★★★ | Alto | Alta | Salt standard | Pipeline provisioning |
| 9 | Cobbler/AutoYaST | ★★★★★ | ★★★★★ | **Alto** | Alta | Ufficiale (legacy) | Bare-metal datacenter |
| 10 | Salt SSH Push | ★★★ | ★ | Basso | Alta | Ufficiale | Solo DMZ/firewall |
| 11 | `auto_accept: True` | ★★★★★ | ★★★★★ | Minimo | **Bassa** | Sconsigliato | Solo test isolati |
| 12 | Hub Multi-Server | ★★★★★ | ★★★★★ | **Molto alto** | Alta | Ufficiale | 10.000+ client |

## Raccomandazione Finale
### Per sistemi già esistenti (la maggior parte dei casi)
**Metodo Primario: Bootstrap Script + Distribuzione SSH parallela**

1. Generare gli script bootstrap con `mgr-bootstrap` (uno per ogni OS/activation key)
2. Preparare un file inventory con tutti gli host
3. Distribuire ed eseguire gli script via `pssh`, `xargs -P`, o script bash custom
4. Rispettare il rate limiting (~15 secondi tra registrazioni)
5. Verificare con `salt-key -l accepted` e nella Web UI

### Per nuove VM Azure
**Metodo Complementare: Terraform + Cloud-Init** (Sezione 5)

Inserire il bootstrap nel `user_data`/`custom_data` della VM. Auto-registrazione al primo boot.
### Prima di iniziare

1. Verificare tutti i prerequisiti (Sezione 2)
2. Applicare il tuning appropriato al server (Sezione 10)
3. Testare con 5-10 host prima di scalare a centinaia
## Fonti e Riferimenti

### Documentazione Ufficiale UYUNI

| Documento | URL |
|---|---|
| Client Onboarding Workflow | https://www.uyuni-project.org/uyuni-docs/en/uyuni/common-workflows/workflow-client-onboarding.html |
| Registration Methods | https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/registration-methods.html |
| Register With Bootstrap Script | https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/registration-bootstrap.html |
| Register on Command Line | https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/registration-cli.html |
| Bootstrap Script Reference | https://www.uyuni-project.org/uyuni-docs/en/uyuni/reference/admin/bootstrap-script.html |
| Bootstrap Repository | https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/bootstrap-repository.html |
| Bootstrap CLI Tools | https://www.uyuni-project.org/uyuni-docs/en/uyuni/reference/cli-bootstrap.html |
| Activation Keys | https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/activation-keys.html |
| Automatic Client Registration (Terraform) | https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/automatic-client-registration.html |
| Salt SSH Contact Method | https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/contact-methods-saltssh.html |
| Auto-Accept Keys (Retail) | https://www.uyuni-project.org/uyuni-docs/en/uyuni/retail/retail-deploy-terminals-auto.html |
| Autoinstallation Profiles | https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/autoinst-profiles.html |
| Ansible Integration | https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/ansible-integration.html |
| Clients on Public Cloud | https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/clients-pubcloud.html |
| Salt Keys Reference | https://www.uyuni-project.org/uyuni-docs/en/uyuni/reference/salt/salt-keys.html |
| API system namespace | https://www.uyuni-project.org/uyuni-docs-api/uyuni/api/system.html |
| spacecmd Reference | https://www.uyuni-project.org/uyuni-docs/en/uyuni/reference/spacecmd-intro.html |

### Documentazione SUSE Manager (Large Scale)

| Documento | URL |
|---|---|
| Large Deployments Overview | https://documentation.suse.com/suma/5.0/en/suse-manager/specialized-guides/large-deployments/overview.html |
| Tuning Large Scale Deployments | https://documentation.suse.com/suma/5.0/en/suse-manager/specialized-guides/large-deployments/tuning.html |
| Operation Recommendations | https://www.uyuni-project.org/uyuni-docs/en/uyuni/specialized-guides/large-deployments/operation-reqs.html |
| Hardware Requirements | https://www.uyuni-project.org/uyuni-docs/en/uyuni/specialized-guides/large-deployments/hardware-reqs.html |
| Hub XMLRPC API | https://documentation.suse.com/suma/5.0/en/suse-manager/specialized-guides/large-deployments/hub-install.html |
| Scaling Minions | https://www.uyuni-project.org/uyuni-docs/en/uyuni/specialized-guides/salt/salt-scaling-minions.html |

### Documentazione Salt Project

| Documento | URL |
|---|---|
| Salt Reactor System | https://docs.saltproject.io/en/latest/topics/reactor/index.html |
| Autoaccept Grains | https://docs.saltproject.io/en/latest/topics/tutorials/autoaccept_grains.html |
| Preseed Minion Keys | https://docs.saltproject.io/en/latest/topics/tutorials/preseed_key.html |
| Salt Master Configuration | https://docs.saltproject.io/en/latest/ref/configuration/master.html |
| Orchestrate Runner | https://docs.saltproject.io/en/latest/topics/orchestrate/orchestrate_runner.html |

### Community e Tool

| Risorsa | URL |
|---|---|
| sumaform (Terraform modules) | https://github.com/uyuni-project/sumaform |
| Ansible Collection (stdevel) | https://github.com/stdevel/ansible-collection-uyuni |
| Hub XMLRPC API source | https://github.com/uyuni-project/hub-xmlrpc-api |
| Salt SSH Integration Wiki | https://github.com/uyuni-project/uyuni/wiki/Salt-SSH-integration |
| Uyuni Ansible Collection Blog | https://cstan.io/en/post/2023/10/uyuni-ansible-collection/ |
| system.bootstrap API issue | https://github.com/uyuni-project/uyuni/issues/4737 |
| SSH-push starvation issue | https://github.com/uyuni-project/uyuni/issues/3182 |
