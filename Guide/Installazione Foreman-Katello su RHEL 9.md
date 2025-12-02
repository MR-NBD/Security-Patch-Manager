## Panoramica
Questa guida descrive l'installazione di **Foreman 3.15** con **Katello 4.17** e **Puppet 8** su **RHEL 9.x**. L'obiettivo finale è gestire il patch management di VM Linux (incluse Ubuntu) tramite SSH.

### Requisiti Hardware Minimi

|Componente|Minimo|Raccomandato|
|---|---|---|
|CPU|4 core|8 core|
|RAM|20 GB|32 GB|
|Disco OS|50 GB|100 GB|
|Disco Pulp (`/var/lib/pulp`)|100 GB|300+ GB|
|Disco PostgreSQL (`/var/lib/pgsql`)|20 GB|50 GB|

### Architettura Target

```
┌─────────────────────────────────────────────────────┐
│           FOREMAN + KATELLO SERVER                  │
│                  (RHEL 9.6)                         │
│  ┌───────────────────────────────────────────────┐  │
│  │ Componenti:                                   │  │
│  │ • Foreman 3.15                                │  │
│  │ • Katello 4.17                                │  │
│  │ • Puppet 8                                    │  │
│  │ • Pulp (Content Management)                   │  │
│  │ • PostgreSQL                                  │  │
│  │ • Candlepin                                   │  │
│  │                                               │  │
│  │ Plugin Attivi:                                │  │
│  │ • Remote Execution (SSH)                      │  │
│  │ • Ansible                                     │  │
│  │ • Discovery                                   │  │
│  └───────────────────────────────────────────────┘  │
│                        │                            │
│                        │ SSH (porta 22)             │
│                        ▼                            │
│              ┌─────────────────┐                    │
│              │   VM Ubuntu     │                    │
│              │  (stessa subnet)│                    │
│              └─────────────────┘                    │
└─────────────────────────────────────────────────────┘
```

---

## FASE 1: Verifica e Preparazione del Sistema

### 1.1 Verifica versione OS e SELinux
#### Verifica versione OS
```bash
cat /etc/os-release
```
![](../img/image4-v2.png)

#### Verifica versione SELinux policy
```bash
rpm -q selinux-policy
```

> **IMPORTANTE**: Foreman/Katello 4.17 richiede almeno `selinux-policy >= 38.1.45-3.el9_5`. Se la versione è inferiore (es. `38.1.35-2.el9_4`), è necessario aggiornare il sistema.

### 1.2 Registrazione RHEL e Aggiornamento Sistema
#### Diventa root
```bash
sudo su -
```
#### Registra la sottoscrizione RHEL
```bash
subscription-manager register
```
#### Abilita i repository necessari
```bash
subscription-manager repos --enable=rhel-9-for-x86_64-baseos-rpms
```
```bash
subscription-manager repos --enable=rhel-9-for-x86_64-appstream-rpms
```
#### Aggiorna il sistema a RHEL 9.6
```bash
dnf upgrade --releasever=9.6 -y
```
#### Riavvia per applicare gli aggiornamenti
```bash
reboot
```
### 1.3 Verifica Post-Aggiornamento
#### Verifica che SELinux policy sia aggiornata
```bash
rpm -q selinux-policy
```

Output atteso: `selinux-policy-38.1.53-5.el9_6` o superiore.

![](../img/image5-v2.png)

---

## FASE 2: Configurazione NTP con Chrony

La sincronizzazione temporale è **critica** per il corretto funzionamento di Katello e dei certificati SSL.

### 2.1 Installazione e Configurazione Chrony

```bash
# Installa chrony
dnf install -y chrony
```

```bash
# Abilita e avvia il servizio
systemctl enable --now chronyd
```

```bash
# Verifica le sorgenti NTP
chronyc sources
```

```bash
# Abilita NTP via timedatectl
timedatectl set-ntp true
```

```bash
# Verifica stato sincronizzazione
timedatectl status
```

Output atteso:

```
               Local time: ...
           Universal time: ...
                 RTC time: ...
                Time zone: ...
System clock synchronized: yes
              NTP service: active
          RTC in local TZ: no
```

---

## FASE 3: Configurazione Hostname e Networking

### 3.1 Identifica l'interfaccia di rete e l'IP

```bash
# Visualizza interfacce di rete
ip addr show
```

Annota l'indirizzo IP della tua interfaccia principale (es. `eth0` o `ens192`).

### 3.2 Configura l'hostname

```bash
# Imposta hostname (sostituisci con il tuo FQDN)
hostnamectl set-hostname foreman-katello.localdomain
```

```bash
# Verifica hostname
hostname
hostname -f
```

### 3.3 Configura il file /etc/hosts

```bash
# Backup del file hosts originale
cp /etc/hosts /etc/hosts.bak
```

```bash
# Edita il file hosts
nano /etc/hosts
```

Aggiungi la seguente riga (sostituisci con i tuoi valori):

```
10.172.2.17    foreman-katello.localdomain    foreman-katello
```

Il file dovrebbe apparire così:

```
127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4
::1         localhost localhost.localdomain localhost6 localhost6.localdomain6
10.172.2.17 foreman-katello.localdomain foreman-katello
```

### 3.4 Verifica la configurazione

```bash
# Verifica risoluzione hostname
ping -c 2 $(hostname -f)
```

---

## FASE 4: Configurazione Firewall

### 4.1 Abilita le porte necessarie
#### Porte TCP per Foreman/Katello
```bash
firewall-cmd --add-port={53,80,443,5646,5647,8000,8140,9090}/tcp --permanent  
```
- 53/tcp   # DNS
- 80/tcp   # HTTP
- 443/tcp # HTTPS
- 5646/tcp # Qpid router
- 5647/tcp # Qpid router
- 8000/tcp # Anaconda
- 8140/tcp # Puppet
- 9090/tcp # Cockpit/Smart Proxy HTTPS
#### Porte UDP
```bash
firewall-cmd --add-port={53,67,68,69}/udp --permanent
```
- 53/udp # DNS
- 67/udp # DHCP
- 68/udp # DHCP
- 69/udp # TFTP
#### Servizi predefiniti
```bash
firewall-cmd --add-service={http,https,dns,dhcp,tftp,puppetmaster} --permanent
```
#### Applica le modifiche
```bash
firewall-cmd --reload
```

### 4.2 Verifica configurazione firewall

```bash
firewall-cmd --list-all
```

Output atteso:

```
public (active)
  target: default
  services: cockpit dhcp dns http https puppetmaster ssh tftp
  ports: 53/tcp 80/tcp 443/tcp 5646/tcp 5647/tcp 8000/tcp 8140/tcp 9090/tcp 53/udp 67/udp 68/udp 69/udp
  ...
```

---

## FASE 5: Configurazione Storage LVM per Pulp

Pulp richiede un volume dedicato montato su `/var/lib/pulp` per la gestione dei repository.

### 5.1 Identifica il disco dedicato

```bash
lsblk
```

Identifica il disco aggiuntivo (es. `/dev/sdb` o `/dev/sda` se non è il disco OS).

> **ATTENZIONE**: Assicurati di selezionare il disco corretto! Non formattare il disco del sistema operativo.

### 5.2 Crea la struttura LVM

```bash
# Crea tabella delle partizioni GPT (sostituisci /dev/sdb con il tuo disco)
parted /dev/sdb --script mklabel gpt
```

```bash
# Crea partizione primaria
parted /dev/sdb --script mkpart primary 0% 100%
```

```bash
# Crea Physical Volume
pvcreate /dev/sdb1
```

```bash
# Crea Volume Group
vgcreate vg_pulp /dev/sdb1
```

```bash
# Crea Logical Volume (usa tutto lo spazio disponibile)
lvcreate -l 100%FREE -n lv_pulp vg_pulp
```

### 5.3 Formatta e monta il volume

```bash
# Formatta con filesystem XFS (raccomandato per Pulp)
mkfs.xfs /dev/mapper/vg_pulp-lv_pulp
```

```bash
# Crea directory mount point
mkdir -p /var/lib/pulp
```

```bash
# Monta il volume
mount /dev/mapper/vg_pulp-lv_pulp /var/lib/pulp
```

### 5.4 Configura mount persistente

```bash
# Aggiungi entry in fstab per mount automatico al boot
echo "/dev/mapper/vg_pulp-lv_pulp /var/lib/pulp xfs defaults 0 0" >> /etc/fstab
```

```bash
# Verifica la entry aggiunta
tail -n1 /etc/fstab
```

### 5.5 Ripristina contesto SELinux

```bash
# Ripristina il contesto SELinux corretto per la directory
restorecon -Rv /var/lib/pulp/
```

### 5.6 Verifica il mount

```bash
df -hP /var/lib/pulp/
```

Output atteso:

```
Filesystem                    Size  Used Avail Use% Mounted on
/dev/mapper/vg_pulp-lv_pulp   200G   33M  200G   1% /var/lib/pulp
```

```bash
# Reload systemd per riconoscere le nuove configurazioni
systemctl daemon-reload
```

---

## FASE 6: Installazione Repository

### 6.1 Abilita CodeReady Builder e EPEL

```bash
# Abilita CodeReady Linux Builder
subscription-manager repos --enable codeready-builder-for-rhel-9-$(arch)-rpms
```

```bash
# Installa EPEL per RHEL 9
dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
```

```bash
# Abilita EPEL
dnf config-manager --set-enabled epel
```

### 6.2 Pulisci e aggiorna cache

```bash
# Pulisci tutti i metadati
dnf clean all
```

```bash
# Aggiorna cache repository
dnf makecache
```

### 6.3 Installa repository Foreman, Katello e Puppet

```bash
# Repository Foreman 3.15
dnf install -y https://yum.theforeman.org/releases/3.15/el9/x86_64/foreman-release.rpm
```

```bash
# Repository Katello 4.17
dnf install -y https://yum.theforeman.org/katello/4.17/katello/el9/x86_64/katello-repos-latest.rpm
```

```bash
# Repository Puppet 8
dnf install -y https://yum.puppet.com/puppet8-release-el-9.noarch.rpm
```

### 6.4 Verifica i repository abilitati

```bash
dnf repolist enabled
```

Output atteso (dovrai vedere):

```
repo id                              repo name
epel                                 Extra Packages for Enterprise Linux 9 - x86_64
foreman                              Foreman 3.15
foreman-plugins                      Foreman plugins 3.15
katello                              Katello 4.17
puppet8                              Puppet 8 Repository el 9 - x86_64
pulpcore                             Pulpcore
rhel-9-for-x86_64-appstream-rpms     Red Hat Enterprise Linux 9 for x86_64 - AppStream (RPMs)
rhel-9-for-x86_64-baseos-rpms        Red Hat Enterprise Linux 9 for x86_64 - BaseOS (RPMs)
...
```

---

## FASE 7: Installazione Foreman-Katello

### 7.1 Aggiorna il sistema

```bash
# Aggiorna tutti i pacchetti prima dell'installazione
dnf upgrade -y
```

### 7.2 Installa il pacchetto installer

```bash
# Installa foreman-installer per scenario Katello
dnf install -y foreman-installer-katello
```

### 7.3 Esegui l'installazione con plugin

Questa è l'installazione completa con tutti i plugin necessari per gestire VM Ubuntu via SSH:

```bash
foreman-installer --scenario katello \
  --foreman-initial-admin-username admin \
  --foreman-initial-admin-password 'Temporanea1234' \
  --enable-foreman-plugin-remote-execution \
  --enable-foreman-proxy-plugin-remote-execution-script \
  --enable-foreman-plugin-ansible \
  --enable-foreman-proxy-plugin-ansible \
  --enable-foreman-plugin-templates \
  --enable-foreman-cli-katello
```

> **NOTA**: L'installazione richiede 15-30 minuti. Non interrompere il processo.

#### Opzioni installer spiegate:

|Opzione|Descrizione|
|---|---|
|`--scenario katello`|Installa Foreman con Katello per content management|
|`--foreman-initial-admin-username`|Username admin iniziale|
|`--foreman-initial-admin-password`|Password admin iniziale|
|`--enable-foreman-plugin-remote-execution`|Abilita esecuzione comandi remoti via SSH|
|`--enable-foreman-proxy-plugin-remote-execution-script`|Proxy per remote execution|
|`--enable-foreman-plugin-ansible`|Integrazione Ansible|
|`--enable-foreman-proxy-plugin-ansible`|Proxy per Ansible|
|`--enable-foreman-plugin-discovery`|Auto-discovery di nuovi host|
|`--enable-foreman-plugin-templates`|Gestione template|
|`--enable-foreman-cli-katello`|CLI hammer per Katello|

### 7.4 Monitora l'installazione (opzionale)

In un altro terminale puoi monitorare il log:

```bash
tail -f /var/log/foreman-installer/katello.log
```

### 7.5 Output installazione completata

Al termine dell'installazione vedrai un output simile:

```
  Success!
  * Foreman is running at https://foreman-katello.localdomain
      Initial credentials are admin / Temporanea1234

  * To install an additional Foreman proxy on separate machine continue by running:

      foreman-proxy-certs-generate --foreman-proxy-fqdn "$FOREMAN_PROXY" --certs-tar "/root/$FOREMAN_PROXY-certs.tar"

  The full log is at /var/log/foreman-installer/katello.log
```

---

## FASE 8: Verifica dell'Installazione

### 8.1 Verifica stato servizi

```bash
# Verifica stato di tutti i servizi Katello
foreman-maintain service status
```

Oppure:

```bash
# Verifica servizi singoli
systemctl status foreman
systemctl status httpd
systemctl status postgresql
systemctl status pulpcore-api
systemctl status pulpcore-content
```

### 8.2 Verifica accesso web

Apri un browser e accedi a:

- **URL**: `https://foreman-katello.localdomain` (o l'IP del server: `https://10.172.2.17`)
- **Username**: `admin`
- **Password**: `Temporanea1234` (o quella specificata durante l'installazione)

> **NOTA**: Se il browser mostra un avviso certificato, è normale (certificato self-signed). Procedi accettando il rischio.

### 8.3 Recupera credenziali (se necessario)

Se hai dimenticato la password:

```bash
grep admin_password /etc/foreman-installer/scenarios.d/katello-answers.yaml
```

### 8.4 Test CLI Hammer

```bash
# Login con hammer
hammer auth login basic --username admin --password 'Temporanea1234'
```

```bash
# Verifica utenti
hammer user list
```

```bash
# Verifica organizzazioni
hammer organization list
```

```bash
# Verifica locations
hammer location list
```

---

## FASE 9: Configurazione Post-Installazione

### 9.1 Configura Organization e Location

```bash
# L'organizzazione di default è già creata, ma puoi crearne altre
hammer organization create --name "MyOrganization" --label "myorg"
```

```bash
# Crea location per il tuo ambiente Azure
hammer location create --name "Italy-North"
```

```bash
# Associa location all'organizzazione
hammer organization add-location --name "MyOrganization" --location "Italy-North"
```

### 9.2 Importa chiavi GPG per i repository

```bash
# Crea directory per le chiavi GPG
mkdir -p /etc/pki/rpm-gpg/import
```

```bash
# Scarica chiavi GPG Ubuntu (per gestire VM Ubuntu)
curl -o /etc/pki/rpm-gpg/import/ubuntu-archive-keyring.gpg \
  https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C
```

### 9.3 Verifica plugin Remote Execution

```bash
# Verifica che il plugin REX sia attivo
hammer settings list | grep remote_execution
```

```bash
# Verifica la chiave SSH di Foreman
cat /var/lib/foreman-proxy/ssh/id_rsa_foreman_proxy.pub
```

> **IMPORTANTE**: Questa chiave pubblica dovrà essere copiata sulle VM Ubuntu che vuoi gestire.

---

## FASE 10: Configurazione Repository per Ubuntu

Per gestire VM Ubuntu, devi configurare i repository DEB.

### 10.1 Crea Product per Ubuntu

```bash
# Crea il Product
hammer product create \
  --organization "MyOrganization" \
  --name "Ubuntu 22.04 LTS" \
  --description "Repository Ubuntu 22.04 Jammy"
```

### 10.2 Crea Repository Ubuntu

```bash
# Repository Main
hammer repository create \
  --organization "MyOrganization" \
  --product "Ubuntu 22.04 LTS" \
  --name "Ubuntu 22.04 Main" \
  --content-type "deb" \
  --url "http://archive.ubuntu.com/ubuntu" \
  --deb-releases "jammy,jammy-updates,jammy-security" \
  --deb-components "main,universe" \
  --deb-architectures "amd64" \
  --download-policy "on_demand"
```

### 10.3 Sincronizza il repository

```bash
# Avvia sincronizzazione (può richiedere tempo)
hammer repository synchronize \
  --organization "MyOrganization" \
  --product "Ubuntu 22.04 LTS" \
  --name "Ubuntu 22.04 Main" \
  --async
```

```bash
# Monitora lo stato della sincronizzazione
hammer task list --search "state=running"
```

---

## FASE 11: Configurazione Content View e Lifecycle

### 11.1 Crea Content View

```bash
hammer content-view create \
  --organization "MyOrganization" \
  --name "CV-Ubuntu-Base" \
  --description "Content View per Ubuntu 22.04"
```

### 11.2 Aggiungi repository alla Content View

```bash
hammer content-view add-repository \
  --organization "MyOrganization" \
  --name "CV-Ubuntu-Base" \
  --product "Ubuntu 22.04 LTS" \
  --repository "Ubuntu 22.04 Main"
```

### 11.3 Pubblica la Content View

```bash
hammer content-view publish \
  --organization "MyOrganization" \
  --name "CV-Ubuntu-Base" \
  --description "Initial publish"
```

### 11.4 Crea Lifecycle Environment

```bash
# Crea ambiente Development
hammer lifecycle-environment create \
  --organization "MyOrganization" \
  --name "Development" \
  --prior "Library"
```

```bash
# Crea ambiente Production
hammer lifecycle-environment create \
  --organization "MyOrganization" \
  --name "Production" \
  --prior "Development"
```

### 11.5 Promuovi Content View

```bash
# Promuovi a Development
hammer content-view version promote \
  --organization "MyOrganization" \
  --content-view "CV-Ubuntu-Base" \
  --to-lifecycle-environment "Development"
```

---

## FASE 12: Crea Activation Key

L'Activation Key serve per registrare automaticamente gli host.

```bash
hammer activation-key create \
  --organization "MyOrganization" \
  --name "ak-ubuntu-dev" \
  --lifecycle-environment "Development" \
  --content-view "CV-Ubuntu-Base" \
  --unlimited-hosts
```

---

## Troubleshooting

### Problema: Installazione fallita

```bash
# Visualizza log completo
cat /var/log/foreman-installer/katello.log

# Riesegui installer (è idempotente)
foreman-installer --scenario katello
```

### Problema: Servizi non partono

```bash
# Restart di tutti i servizi
foreman-maintain service restart
```

### Problema: Errori SELinux

```bash
# Verifica problemi SELinux
ausearch -m avc -ts recent

# Genera policy fix
audit2allow -a -M foreman_fix
semodule -i foreman_fix.pp
```

### Problema: Spazio disco insufficiente

```bash
# Verifica spazio
df -h

# Pulisci cache Pulp se necessario
foreman-rake katello:delete_orphaned_content RAILS_ENV=production
```

### Problema: Connessione firewall

```bash
# Test connettività porte
ss -tulpn | grep -E '(443|5647|9090)'
```

---

## Riepilogo Comandi Utili

```bash
# Stato servizi
foreman-maintain service status

# Restart servizi
foreman-maintain service restart

# Verifica salute sistema
foreman-maintain health check

# Backup
foreman-maintain backup offline /backup/foreman

# Aggiornamento Foreman
foreman-maintain upgrade check
foreman-maintain upgrade run
```

---

## Prossimi Passi

Una volta completata l'installazione, i prossimi passi saranno:

1. **Registrare la VM Ubuntu** al server Foreman
2. **Configurare Remote Execution** per la gestione via SSH
3. **Schedulare patch automatiche** tramite Foreman
4. **Configurare Errata Management** per le security patch

---

## Riferimenti

- [Documentazione ufficiale Foreman 3.15](https://docs.theforeman.org/3.15/)
- [Documentazione Katello](https://docs.theforeman.org/3.15/Quickstart/index-katello.html)
- [Foreman Remote Execution](https://docs.theforeman.org/3.15/Managing_Hosts/index-katello.html#Configuring_and_Setting_Up_Remote_Jobs_managing-hosts)