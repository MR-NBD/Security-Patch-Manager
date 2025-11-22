In questa guida mostrerò come installare Forman con Puppet, Katello e il plugin Discovery. Vedremop come installare e configurare i server DHCP e TFTP. Mostrerò anche come configurare Foreman e come utilizzare l'immagine di avvio di Foreman tramite PXE.
## Setup check
```bash
cat /etc/os-release
```
```bash
rpm -q selinux-policy
```
![[image.png]]
Si vede la versione `selinux-policy-38.1.35-2.el9_4.3 ← è troppo vecchia`. Per questo setup stiamo usando **RHEL 9.4** OS presente come ISO su azure, ma i pacchetti SELinux di Foreman/Katello che vogliamo installanlare richiedono almeno : 
- `selinux-policy >= 38.1.45-3.el9_5`
- `selinux-policy >= 38.1.53-5.el9_6`
Aggiorniamola: 
```bash
sudo su
```
```bash
sudo subscription-manager register
```
```bash
sudo subscription-manager attach --auto
```
E' necessario registrare una sottoscrizione RHEL, in quasteso caso sto usando la mia personale gratuita, _situazione da migliorare magari caricando su azure una ISO già compatibile è più aggionata_. 
```bash
sudo subscription-manager repos --enable=rhel-9-for-x86_64-baseos-rpms
```
```bash
sudo subscription-manager repos --enable=rhel-9-for-x86_64-appstream-rpms
```
```bash
sudo dnf upgrade --releasever=9.6 -y
```
```bash
sudo reboot
```
Dopo il riavvio controllare se la verione è stata aggiornata correttamente.
```bash
rpm -q selinux-policy
```
![[2025-11-22 13_56_50-.png]]
- assicuriamoci di avere un hostname statico
- Ricaviamoci il NIC a IP 
```bash
ifconfig
```
![[2025-11-22 14_28_19-.png]]
In questo caso il NIC eth0 e l'IP 10.172.2.17
- verifichiamo l'hostname se non se siamo sicuri
```bash
hostname 
```
Per una procedura standard in questo momento dovremmo cercare il dominio del DNS per una corretta configurazione del hest. 
in questo modo
```bash
nmcli device show enp2s0 | grep IP4.DNS
```
ci aspetta un Output simile `DNS-Server-IP: IP4.DNS[1]: 192.168.2.1`
```bash
nslookup 192.168.2.1
```
ci aspetta un Output simile `1.2.168.192.in-addr.arpa name = speedport.ip.`
Essendo noi in un laboratorio test ed unico interesse in questo momento che il servizio venga raggiunto solamente da un host all'interno della stessa subnet aggiriamo il problema.
## edit il file hosts
- edit `/etc/hosts`
```bash
sudo nano /etc/hosts
```
IL dominio per la mappatura di un nuov host dovrebbe essere: `<host name+routers domain> <host name>` nel nostro ambiente di test seguendo l'esempio di prima inseriremo l'IP 10.172.2.17 hostname della macchina e `.localdomain` seguendo la logical del file. Dovremmo ottenere un risultato simile.
![[2025-11-22 14_40_15-.png]]
nel caso di una nonn limitazione di laboratorio per il DNS il risultato sarebbe stato `10.172.2.17 foreman-katello-test2speedport.ip. foreman-katello-test2` o qualcosa di simile.
## Settiamo le regole del firewall
```bash
firewall-cmd --add-port="5646/tcp"
```
```bash
firewall-cmd \  
--add-port="5647/tcp" \  
--add-port="8000/tcp" \  
--add-port="9090/tcp"
```
```bash
firewall-cmd \  
--add-service=dns \  
--add-service=dhcp \  
--add-service=tftp \  
--add-service=http \  
--add-service=https \  
--add-service=puppetmaster
```
```bash
firewall-cmd --runtime-to-permanent
```
Verifichiamo che tutto sia venuto correttamente.
```bash
firewall-cmd --list-all
```
Ci aspettiamo un output simile
![[2025-11-22 14_49_23-.png]]
Ora possiamo iniziare con l'installazione dei Foreman-Katello. Seguima dunque quanto riporato dalla guida per instllare verione di Foreman 3.15 Katello 4.17 e Puppet 8 https://docs.theforeman.org/3.15/Quickstart/index-katello.html
## Configurazione dei repository
1. Cancelliamo tutti i metadati:
```bash
dnf clean all
```
2. Installare il pacchetto foreman-release.rpm:
```bash
dnf install https://yum.theforeman.org/releases/3.15/el9/x86_64/foreman-release.rpm
```
3. Installa il pacchetto katello-repos-latest.rpm:
```bash
dnf install https://yum.theforeman.org/katello/4.17/katello/el9/x86_64/katello-repos-latest.rpm
```
4. Installa il pacchetto puppet-release.
```bash
dnf install https://yum.puppet.com/puppet8-release-el-9.noarch.rpm
```
Verifichiamo che tutto sia vvenuto correttamente. 
```bash
dnf repolist enabled
```
Dovremmo ottenere un risultato simile.
![[2025-11-22 15_04_48-.png]]
## Installazione dei pacchetti del server Foreman
1. Aggiorniamo tutti i pacchetti:
```bash
dnf upgrade
```
1. Installiamo `foreman-installer-katello`:
```bash
dnf install foreman-installer-katello
```
## Lanciamo l'installer di Foreman per katello
L'installazione non è interattiva, ma la configurazione può essere personalizzata specificando una qualsiasi delle opzioni elencate in foreman-installer --help, oppure eseguendo foreman-installer -i per la modalità interattiva. Ulteriori esempi sono descritti nella sezione Opzioni di installazione. L'opzione -v disabilita la barra di avanzamento e visualizza tutte le modifiche.
```bash
foreman-installer --scenario katello
```

sudo su 
nano /etc/hosts
<IP> <MY-HOSTNAME>.localdomain <MY-HOSTANME>
sudo dnf clean all
sudo dnf update -y
sudo reboot
cat /etc/os-release
rpm -q selinux-policy
Si vede versione del tipo:

`selinux-policy-38.1.53-5.el9_6`

Stai usando **RHEL 9.4**, ma i pacchetti SELinux di Foreman/Katello che stai installando richiedono:

- `selinux-policy >= 38.1.45-3.el9_5`
    
- `selinux-policy >= 38.1.53-5.el9_6`
    

La tua versione è:

`selinux-policy-38.1.35-2.el9_4.4  ← troppo vecchia`



## Firewall Settings

# firewall-cmd --add-port="5646/tcp"  
# firewall-cmd \  
--add-port="5647/tcp" \  
--add-port="8000/tcp" \  
--add-port="9090/tcp"  
  
# firewall-cmd \  
--add-service=dns \  
--add-service=dhcp \  
--add-service=tftp \  
--add-service=http \  
--add-service=https \  
--add-service=puppetmaster  
  
# firewall-cmd --runtime-to-permanent

>  **check if it works <<**

# firewall-cmd --list-all


https://docs.theforeman.org/3.15/Quickstart/index-katello.html

## Configuring repositories

Procedure

1. Clear any metadata:
    
    # dnf clean all
    
2. Install the `foreman-release.rpm` package:
    
    # dnf install https://yum.theforeman.org/releases/3.15/el9/x86_64/foreman-release.rpm
    
3. Install the `katello-repos-latest.rpm` package:
    
    # dnf install https://yum.theforeman.org/katello/4.17/katello/el9/x86_64/katello-repos-latest.rpm
    
4. Install the `puppet-release` package.
    
    - For Puppet 8:
        
        # dnf install https://yum.puppet.com/puppet8-release-el-9.noarch.rpm
    

Verification

- Verify that the required repositories are enabled:
    
    # dnf repolist enabled

## Installing Foreman server packages

Procedure

1. Update all packages:
    
    # dnf upgrade
    
2. Install `foreman-installer-katello`:
    
    # dnf install foreman-installer-katello


## Running the Foreman installer

The installation run is non-interactive, but the configuration can be customized by supplying any of the options listed in `foreman-installer --help`, or by running `foreman-installer -i` for interactive mode. More examples are described in the `Installation Options` section. The `-v` option disables the progress bar and displays all changes.

Procedure

- Run the Foreman installer:
    
    # foreman-installer --scenario katello
    

The script displays its progress and writes logs to `/var/log/foreman-installer/katello.log`.

