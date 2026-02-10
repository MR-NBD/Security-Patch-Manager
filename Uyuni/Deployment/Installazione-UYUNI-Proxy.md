# Installazione UYUNI Proxy Containerizzato

Installazione di **UYUNI Proxy 2025.10** su **openSUSE Leap 15.6** in ambiente **Azure** con deployment containerizzato tramite **Podman**.

### Accesso alla VM
L'accesso alla VM avviene **esclusivamente tramite Azure Bastion** (nessun IP pubblico).

> Il Proxy UYUNI funge da intermediario tra il Server UYUNI e i client Salt. Tutto il traffico Salt e i pacchetti transitano attraverso il Proxy, riducendo il carico sul Server e migliorando le performance nella rete locale.

> A partire da UYUNI 2024.10, il Proxy è disponibile **esclusivamente come container**. La versione classica RPM non è più supportata.

### Architettura Target

```
UYUNI Server (10.172.2.17)
        │
        │ Salt 4505/4506 + HTTPS 443
        │
UYUNI Proxy (10.172.1.10)          ◄── Questa guida
        │
        ├── Ubuntu Client #1
        ├── Ubuntu Client #2
        └── RHEL 9 Client
```

### Componenti Container (Proxy 2025.10)

| Container | Funzione |
|-----------|----------|
| **proxy-httpd** | HTTP/HTTPS - repository pacchetti e Web forwarding |
| **proxy-salt-broker** | Broker Salt events tra client e Server |
| **proxy-squid** | Cache proxy per pacchetti (riduce traffico verso Server) |
| **proxy-ssh** | SSH tunneling per push clients |
| **proxy-tftpd** | TFTP per PXE boot (provisioning automatico) |

### Requisiti Hardware

| Componente | Test | Production |
|------------|------|------------|
| CPU | 2+ core | 4+ core |
| RAM | 2 GB | 8 GB |
| Disco OS | 40 GB SSD | 64 GB SSD |
| Disco Cache | 64 GB Standard SSD | 128+ GB Premium SSD |

> **NOTA**: La dimensione del disco cache Squid determina quanti pacchetti vengono serviti localmente senza contattare il Server. Più grande è, meno traffico di rete tra Proxy e Server. Impostare Squid cache al massimo **60% dello spazio disponibile** sul disco cache.

---

## DEPLOYMENT

### Configurazione VM Azure - Ambiente TEST

| Parametro          | Valore                              |
| ------------------ | ----------------------------------- |
| **Subscription**   | ASL0603-spoke10                     |
| **Resource Group** | test_group                          |
| **VM Name**        | uyuni-proxy-test                    |
| **Region**         | Italy North                         |
| **Availability**   | Availability Zone 1                 |
| **Security Type**  | Trusted launch (Secure boot + vTPM) |
| **Image**          | openSUSE Leap 15.6 - Gen2           |
| **Architecture**   | x64                                 |
| **Size**           | Standard_B2s (2 vCPU, 4 GB RAM)     |
| **Username**       | azureuser                           |
| **Authentication** | Password                            |
| **OS Disk**        | 40 GB Standard SSD LRS              |
| **Data Disks**     | 1 disco (64 GB) per cache pacchetti |
| **VNet**           | ASL0603-spoke10-spoke-italynorth    |
| **Subnet**         | Subnet-Proxy (10.172.1.0/24)        |
| **Private IP**     | Statico: 10.172.1.10                |
| **Public IP**      | None                                |
| **NSG**            | uyuni-proxy-test-nsg                |

### Configurazione NSG

| Priority | Nome | Port | Protocol | Source | Destination | Action |
|----------|------|------|----------|--------|-------------|--------|
| 100 | AllowHTTPS_Clients | 443 | TCP | 10.172.2.0/24 | 10.172.1.10 | Allow |
| 110 | AllowSalt_Clients | 4505-4506 | TCP | 10.172.2.0/24 | 10.172.1.10 | Allow |
| 120 | AllowHTTPS_Server | 443 | TCP | 10.172.2.17 | 10.172.1.10 | Allow |
| 130 | AllowSalt_Server | 4505-4506 | TCP | 10.172.2.17 | 10.172.1.10 | Allow |
| 140 | AllowSSHPush | 8022 | TCP | 10.172.2.0/24 | 10.172.1.10 | Allow |

**Outbound** (dal Proxy):

| Priority | Nome | Port | Protocol | Source | Destination | Action |
|----------|------|------|----------|--------|-------------|--------|
| 100 | AllowHTTPS_ToServer | 443 | TCP | 10.172.1.10 | 10.172.2.17 | Allow |
| 110 | AllowSalt_ToServer | 4505-4506 | TCP | 10.172.1.10 | 10.172.2.17 | Allow |

---

## FASE 1: Preparazione del Sistema Base

### 1.1 Dalla VM

#### Diventa root
```bash
sudo su -
```

#### Verifica versione OS
```bash
cat /etc/os-release
```

Output atteso:
```
NAME="openSUSE Leap"
VERSION="15.6"
```

### 1.2 Aggiornamento Sistema
```bash
zypper refresh
```
```bash
zypper update -y
```

#### Riavvia per applicare aggiornamenti kernel
```bash
reboot
```

### 1.3 Installazione Pacchetti Prerequisiti
```bash
zypper install -y \
  chrony \
  podman \
  firewalld \
  nano \
  wget \
  curl \
  jq
```

---

## FASE 2: Configurazione NTP con Chrony

La sincronizzazione temporale è **CRITICA** per il corretto funzionamento di Salt e i certificati SSL.

### 2.1 Configurazione Chrony

#### Backup configurazione originale
```bash
cp /etc/chrony.conf /etc/chrony.conf.bak
```

#### Modifica configurazione
```bash
nano /etc/chrony.conf
```

Configurazione:
```
# Server NTP (sostituire con i propri server aziendali)
server ntp1.inrim.it iburst
server ntp2.inrim.it iburst
pool pool.ntp.org iburst

# Permetti sincronizzazione rapida all'avvio
makestep 1.0 3

# Registra le statistiche
logdir /var/log/chrony

# Drift file
driftfile /var/lib/chrony/drift
```

### 2.2 Abilita e Avvia il Servizio
```bash
systemctl enable --now chronyd
```

#### Abilita NTP via timedatectl
```bash
timedatectl set-ntp true
```

#### Verificare stato sincronizzazione
```bash
timedatectl status
```

Output atteso:
```
System clock synchronized: yes
NTP service: active
```

---

## FASE 3: Configurazione Hostname e DNS

### 3.1 Configurare l'Hostname

#### Impostare hostname
```bash
hostnamectl set-hostname uyuni-proxy-test.uyuni.internal
```

#### Verificare hostname
```bash
hostname -f
```

### 3.2 Configura il File /etc/hosts

#### Recuperare l'IP privato della VM
```bash
ip addr show eth0
```

#### Backup del file hosts originale
```bash
cp /etc/hosts /etc/hosts.bak
```

#### Editare il file hosts
```bash
nano /etc/hosts
```

Aggiungere:
```
10.172.1.10    uyuni-proxy-test.uyuni.internal    uyuni-proxy-test
10.172.2.17    uyuni-server-test.uyuni.internal    uyuni-server-test
```

> **IMPORTANTE**: Il Proxy DEVE risolvere l'FQDN del Server UYUNI. Aggiungere anche l'entry del Server nel file hosts se non si usa Azure Private DNS Zone.

### 3.3 Verificare la Configurazione DNS

#### Test risoluzione diretta
```bash
ping -c 2 $(hostname -f)
```

#### Test risoluzione Server
```bash
ping -c 2 uyuni-server-test.uyuni.internal
```

---

## FASE 4: Configurazione Firewall

### 4.1 Abilitare Firewalld
```bash
systemctl enable --now firewalld
```

### 4.2 Configurare Porte Proxy

#### HTTPS (Web UI e repository pacchetti)
```bash
firewall-cmd --permanent --add-port=443/tcp
```

#### HTTP (repository pacchetti)
```bash
firewall-cmd --permanent --add-port=80/tcp
```

#### Salt (comunicazione con client e Server)
```bash
firewall-cmd --permanent --add-port=4505/tcp
firewall-cmd --permanent --add-port=4506/tcp
```

#### SSH Push (per contact method ssh-push)
```bash
firewall-cmd --permanent --add-port=8022/tcp
```

### 4.3 Applicare le Modifiche
```bash
firewall-cmd --reload
```

### 4.4 Verifica Configurazione
```bash
firewall-cmd --list-all
```

Output atteso:
```
ports: 80/tcp 443/tcp 4505/tcp 4506/tcp 8022/tcp
```

---

## FASE 5: Configurazione Storage Cache

### 5.1 Identificare il Disco Dati
```bash
lsblk
```

### 5.2 Configurazione LVM per disco cache (es. /dev/sdb)

#### Creare partizione
```bash
parted /dev/sdb --script mklabel gpt
parted /dev/sdb --script mkpart primary 0% 100%
```

#### Configura LVM
```bash
pvcreate /dev/sdb1
vgcreate vg_proxy_cache /dev/sdb1
lvcreate -l 100%FREE -n lv_cache vg_proxy_cache
```

#### Formatta XFS
```bash
mkfs.xfs /dev/mapper/vg_proxy_cache-lv_cache
```

#### Crea mount point e monta
```bash
mkdir -p /proxy_storage
mount /dev/mapper/vg_proxy_cache-lv_cache /proxy_storage
```

#### Aggiungi a fstab
```bash
echo "/dev/mapper/vg_proxy_cache-lv_cache /proxy_storage xfs defaults,nofail 0 0" >> /etc/fstab
```

#### Reload systemd
```bash
systemctl daemon-reload
```

### 5.3 Spostare Container Storage su proxy_storage

```bash
# Crea directory per containers
mkdir -p /proxy_storage/containers

# Ferma eventuali container attivi
systemctl stop podman.socket

# Sposta dati esistenti (se presenti)
mv /var/lib/containers/* /proxy_storage/containers/ 2>/dev/null || true

# Rimuovi directory originale
rm -rf /var/lib/containers

# Crea symlink
ln -s /proxy_storage/containers /var/lib/containers

# Riavvia Podman
systemctl start podman.socket
```

> **NOTA**: Eseguire questa operazione PRIMA di installare il Proxy.

### 5.4 Verificare Configurazione Storage
```bash
df -hP /proxy_storage
lvs
```

---

## FASE 6: Installazione Repository e Pacchetti Proxy

### 6.1 Aggiungere Repository UYUNI Proxy

```bash
zypper ar https://download.opensuse.org/repositories/systemsmanagement:/Uyuni:/Stable/images/repo/Uyuni-Proxy-POOL-$(arch)-Media1/ uyuni-proxy-stable
```

### 6.2 Refresh e Installazione

#### Accettare chiave GPG e refresh
```bash
zypper --gpg-auto-import-keys refresh
```

#### Installare tool di gestione Proxy
```bash
zypper install -y mgrpxy mgrpxy-bash-completion uyuni-storage-setup-proxy
```

### 6.3 Verificare Versione Podman
```bash
podman --version
```

UYUNI richiede Podman >= 4.5.0

### 6.4 Abilitare Podman Socket
```bash
systemctl enable --now podman.socket
```

---

## FASE 7: Registrare l'Host Proxy come Salt Minion

> **PREREQUISITO CRITICO**: L'host del Proxy DEVE essere registrato come Salt minion sul Server UYUNI **PRIMA** di generare la configurazione Proxy. Senza questo passaggio, la generazione del certificato SSL fallirà.

### 7.1 Sul Server UYUNI: Creare Activation Key per il Proxy

Dalla **Web UI** del Server UYUNI (`https://uyuni-server-test.uyuni.internal`):

1. **Systems → Activation Keys → Create Key**
2. Configurare:

| Campo | Valore |
|-------|--------|
| **Key** | `1-proxy-opensuse156` |
| **Description** | Activation key per Uyuni Proxy - openSUSE Leap 15.6 |
| **Base Channel** | openSUSE Leap 15.6 (x86_64) |
| **Add-On Entitlements** | Container Build Host |
| **Contact Method** | Default |

3. **Create Activation Key**

### 7.2 Sull'Host Proxy: Bootstrap via Script

```bash
curl -Sks https://uyuni-server-test.uyuni.internal/pub/bootstrap/bootstrap.sh | /bin/bash
```

> Se il certificato SSL del Server non è attendibile, aggiungere `--insecure` o scaricare prima il CA certificate:
> ```bash
> curl -Sks https://uyuni-server-test.uyuni.internal/pub/RHN-ORG-TRUSTED-SSL-CERT -o /etc/pki/trust/anchors/uyuni-ca.crt
> update-ca-certificates
> ```

### 7.3 Sul Server UYUNI: Accettare il Salt Key

Dalla Web UI:
1. **Salt → Keys**
2. Trovare `uyuni-proxy-test.uyuni.internal` nella lista "Pending"
3. Cliccare **Accept**

Oppure da CLI sul Server:
```bash
mgrctl exec -- salt-key -a uyuni-proxy-test.uyuni.internal
```

### 7.4 Verificare Registrazione

Dalla Web UI:
1. **Systems → System List**
2. Verificare che `uyuni-proxy-test` appaia nella lista
3. Cliccare sul sistema e verificare lo stato "Active"

---

## FASE 8: Generare Configurazione Proxy

### Opzione A: Via Web UI (Consigliata)

1. Sul Server UYUNI, andare su **Systems → Proxy Configuration**
2. Compilare:

| Campo | Valore |
|-------|--------|
| **Proxy FQDN** | `uyuni-proxy-test.uyuni.internal` |
| **Parent FQDN** | `uyuni-server-test.uyuni.internal` |
| **Proxy SSH Port** | `8022` |
| **Max Squid Cache [MB]** | `38000` (60% di 64 GB) |
| **SSL Certificate** | Generate (certificato self-signed) |

3. Cliccare **Generate**
4. Scaricare il file `config.tar.gz` generato

### Opzione B: Via spacecmd (CLI)

Dal Server UYUNI:

```bash
mgrctl exec -ti 'spacecmd proxy_container_config_generate_cert -- \
  uyuni-proxy-test.uyuni.internal \
  uyuni-server-test.uyuni.internal \
  38000 \
  admin@example.com \
  -o /tmp/config.tar.gz \
  -p 8022'
```

#### Copiare il file config dal container Server all'host
```bash
podman cp uyuni-server:/tmp/config.tar.gz /root/config.tar.gz
```

#### Trasferire sull'host Proxy
```bash
scp /root/config.tar.gz azureuser@10.172.1.10:/tmp/config.tar.gz
```

> **PER PRODUZIONE**: Utilizzare certificati firmati dalla CA aziendale. Vedere sezione "Certificati Custom per Production" in fondo.

---

## FASE 9: Installazione Container Proxy

### 9.1 Sull'Host Proxy: Installare i Container

```bash
sudo su -
mgrpxy install podman /tmp/config.tar.gz
```

L'installazione:
- Scarica le 5 immagini container dal registry
- Configura il pod `uyuni-proxy-pod`
- Crea il servizio systemd
- Abilita IPv4/IPv6 forwarding

### 9.2 Verificare Container Attivi

```bash
podman ps
```

Output atteso (5 container):
```
CONTAINER ID  IMAGE                                          STATUS         NAMES
xxxx          registry.opensuse.org/uyuni/proxy-httpd        Up (healthy)   proxy-httpd
xxxx          registry.opensuse.org/uyuni/proxy-salt-broker  Up (healthy)   proxy-salt-broker
xxxx          registry.opensuse.org/uyuni/proxy-squid        Up (healthy)   proxy-squid
xxxx          registry.opensuse.org/uyuni/proxy-ssh          Up (healthy)   proxy-ssh
xxxx          registry.opensuse.org/uyuni/proxy-tftpd        Up (healthy)   proxy-tftpd
```

### 9.3 Verificare Pod
```bash
podman pod ps
```

### 9.4 Abilitare Avvio Automatico
```bash
systemctl enable uyuni-proxy-pod
```

### 9.5 Verificare dal Server UYUNI

Dalla Web UI:
1. **Systems → System List** → selezionare `uyuni-proxy-test`
2. Tab **Details → Proxy**
3. Verificare status: **Active**

---

## FASE 10: Ri-puntare i Client Esistenti al Proxy

Ora i 3 client (2 Ubuntu + 1 RHEL) devono essere reindirizzati dal Server diretto al Proxy.

### Opzione A: Via Web UI (Consigliata)

Per **ogni client**:

1. **Systems → System List** → cliccare sul sistema
2. Tab **Details → Connection**
3. Cliccare **Change proxy**
4. Selezionare `uyuni-proxy-test.uyuni.internal` dal menu dropdown
5. Cliccare **Confirm**

Uyuni modificherà automaticamente la configurazione Salt del client (`/etc/salt/minion.d/susemanager.conf`) e riavvierà il Salt minion.

### Opzione B: Via CLI (su ogni client manualmente)

#### Modificare configurazione Salt minion
```bash
nano /etc/salt/minion.d/susemanager.conf
```

Cambiare:
```yaml
# PRIMA (connessione diretta al Server)
master: uyuni-server-test.uyuni.internal

# DOPO (connessione tramite Proxy)
master: uyuni-proxy-test.uyuni.internal
```

#### Riavviare Salt minion
```bash
systemctl restart salt-minion
```

#### Verificare connessione
```bash
salt-call test.ping
```

Output atteso:
```
local:
    True
```

### 10.1 Verificare che i Client siano Connessi via Proxy

Dalla Web UI del Server:
1. **Systems → System List** → cliccare su un client
2. Tab **Details → Connection**
3. Verificare che **Proxy** mostri `uyuni-proxy-test.uyuni.internal`

Oppure dalla lista sistemi, la colonna "Proxy" mostrerà il proxy di appartenenza.

---

## Troubleshooting

### I container Proxy non si avviano

```bash
# Verificare logs di ogni container
podman logs proxy-httpd
podman logs proxy-salt-broker
podman logs proxy-squid

# Verificare stato pod
podman pod ps

# Riavviare
mgrpxy stop
mgrpxy start

# Oppure via systemd
systemctl restart uyuni-proxy-pod
```

### Client non si connette al Proxy

```bash
# Dal client, verificare configurazione master
cat /etc/salt/minion.d/susemanager.conf

# Test connettività al Proxy
ping uyuni-proxy-test.uyuni.internal

# Verificare porte Salt aperte sul Proxy
nc -zv uyuni-proxy-test.uyuni.internal 4505
nc -zv uyuni-proxy-test.uyuni.internal 4506

# Riavviare Salt minion
systemctl restart salt-minion

# Verificare logs Salt minion
journalctl -u salt-minion -f
```

### Proxy non raggiunge il Server

```bash
# Dall'host Proxy, test connettività verso Server
ping uyuni-server-test.uyuni.internal
nc -zv uyuni-server-test.uyuni.internal 443
nc -zv uyuni-server-test.uyuni.internal 4505
nc -zv uyuni-server-test.uyuni.internal 4506

# Verificare DNS
host uyuni-server-test.uyuni.internal

# Verificare firewall
firewall-cmd --list-all
```

### Problemi Certificati SSL

```bash
# Verificare certificato Proxy
podman exec proxy-httpd openssl x509 -in /etc/pki/tls/certs/spacewalk.crt -text -noout

# Verificare CA del Server
openssl s_client -connect uyuni-server-test.uyuni.internal:443 </dev/null 2>/dev/null | openssl x509 -noout -dates
```

### Cache Squid piena

```bash
# Verificare spazio
df -h /proxy_storage

# Verificare cache Squid
podman exec proxy-squid du -sh /var/cache/squid/
```

---

## Certificati Custom per Production

Per ambienti production con CA aziendale:

### 1. Copiare certificati nel container Server
```bash
podman cp ca.crt uyuni-server:/tmp/
podman cp proxy.crt uyuni-server:/tmp/
podman cp proxy.key uyuni-server:/tmp/
```

### 2. Generare configurazione con certificati custom
```bash
mgrctl exec -ti 'spacecmd proxy_container_config -- \
  -p 8022 \
  uyuni-proxy-test.uyuni.internal \
  uyuni-server-test.uyuni.internal \
  38000 \
  admin@example.com \
  /tmp/ca.crt \
  /tmp/proxy.crt \
  /tmp/proxy.key \
  -o /tmp/config.tar.gz'
```

---

## Comandi Utili - Quick Reference

### Gestione Proxy
```bash
mgrpxy start               # Avvia il proxy
mgrpxy stop                # Ferma il proxy
mgrpxy status              # Stato proxy (se disponibile)
mgrpxy logs                # Visualizza logs
mgrpxy upgrade             # Aggiornamento container
mgrpxy uninstall           # Rimuovi proxy
```

### Container e Pod
```bash
podman ps                  # Lista container attivi
podman pod ps              # Stato pod
podman logs <container>    # Log specifico container
podman logs -f proxy-httpd # Log in tempo reale
```

### Systemd
```bash
systemctl status uyuni-proxy-pod    # Stato servizio
systemctl restart uyuni-proxy-pod   # Riavvia
systemctl enable uyuni-proxy-pod    # Abilita auto-start
journalctl -u uyuni-proxy-pod -f   # Log systemd
```

### Storage
```bash
df -h /proxy_storage                # Spazio disco cache
lvs                                 # Volumi logici
podman system df                    # Uso storage container
```

---

## Riferimenti

- [Proxy Deployment on openSUSE](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/container-deployment/uyuni/proxy-deployment-uyuni.html)
- [Proxy Container Setup](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/container-deployment/uyuni/proxy-container-setup-uyuni.html)
- [Proxy Container Installation](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/container-deployment/uyuni/proxy-container-installation-uyuni.html)
- [Network Requirements](https://www.uyuni-project.org/uyuni-docs/en/uyuni/installation-and-upgrade/network-requirements.html)
- [Client Registration to Proxy](https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/client-proxy.html)
- [SSL Certificates](https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/ssl-certs.html)
