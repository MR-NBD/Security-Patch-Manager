Guida per la gestione di client Red Hat Enterprise Linux 9 con UYUNI Server utilizzando il Content Delivery Network (CDN) di Red Hat.
**Riferimento**: https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/clients-rh-cdn.html

## Registrazione del sistema RHEL e ottenimento certificati
### Registra il sistema con subscription-manager
Sulla **VM RHEL**, esegui:
```bash
subscription-manager register --username=TUO_USER --password=TUA_PASS
```
### Verifica la registrazione
```bash
subscription-manager status
```
Output atteso (con Simple Content Access):
```
+-------------------------------------------+
   System Status Details
+-------------------------------------------+
Overall Status: Disabled
Content Access Mode is set to Simple Content Access.
```

```bash
subscription-manager identity
```

Output atteso:
```
system identity: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
name: nome-vm
org name: xxxxxx
```
### Verifica i certificati generati
```bash
ls -la /etc/pki/entitlement/
ls -la /etc/rhsm/ca/
```
## Certificati necessari per RHEL CDN

| Certificato             | Path sul sistema RHEL               | Tipo in UYUNI | Scopo                                          |
| ----------------------- | ----------------------------------- | ------------- | ---------------------------------------------- |
| Entitlement Certificate | `/etc/pki/entitlement/<ID>.pem`     | SSL           | Prova la validità della subscription           |
| Entitlement Key         | `/etc/pki/entitlement/<ID>-key.pem` | SSL           | Chiave privata associata al certificato        |
| Red Hat CA              | `/etc/rhsm/ca/redhat-uep.pem`       | SSL           | CA root per validare la connessione SSL al CDN |
## Trasferimento certificati al server UYUNI
### Copia i certificati dalla VM RHEL
Dalla **VM RHEL**:
```bash
# Copia nella home dell'utente sul server UYUNI
scp /etc/pki/entitlement/<ID>.pem azureuser@<IP-UYUNI>:/home/azureuser/
scp /etc/pki/entitlement/<ID>-key.pem azureuser@<IP-UYUNI>:/home/azureuser/
scp /etc/rhsm/ca/redhat-uep.pem azureuser@<IP-UYUNI>:/home/azureuser/
```
### Copia la chiave GPG Red Hat
```bash
scp /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release azureuser@<IP-UYUNI>:/home/azureuser/
```
### Sposta la chiave GPG nella posizione corretta (sul server UYUNI)
```bash
sudo mkdir -p /etc/pki/rpm-gpg/
sudo mv /home/azureuser/RPM-GPG-KEY-redhat-release /etc/pki/rpm-gpg/
```
## Caricamento certificati su UYUNI Web UI
**Systems → Autoinstallation → GPG and SSL Keys → Create Stored Key/Cert**
### Certificato 1: Red Hat CA

| Campo | Valore |
|-------|--------|
| Description | `RHEL9-CA-RedHat` |
| Type | `SSL` |
| File | `redhat-uep.pem` |
### Certificato 2: Entitlement Certificate

| Campo | Valore |
|-------|--------|
| Description | `RHEL9-Entitlement-Cert` |
| Type | `SSL` |
| File | `<ID>.pem` |
### Certificato 3: Entitlement Key

| Campo | Valore |
|-------|--------|
| Description | `RHEL9-Entitlement-Key` |
| Type | `SSL` |
| File | `<ID>-key.pem` |
## Creazione canali base con spacewalk-common-channels
Sul **server UYUNI**, esegui:
```bash
spacewalk-common-channels -a x86_64 rhel9-pool-uyuni rhel9-uyuni-client
```
Se usi container (mgrctl):
```bash
mgrctl exec -- spacewalk-common-channels -a x86_64 rhel9-pool-uyuni rhel9-uyuni-client
```
Verifica:
```bash
spacewalk-common-channels -l | grep rhel9
```
## Ottieni gli URL dei repository Red Hat
Sulla **VM RHEL**:
```bash
subscription-manager repos --list-enabled
```
Output atteso:
```
Repo ID:   rhel-9-for-x86_64-baseos-rpms
Repo URL:  https://cdn.redhat.com/content/dist/rhel9/$releasever/x86_64/baseos/os

Repo ID:   rhel-9-for-x86_64-appstream-rpms
Repo URL:  https://cdn.redhat.com/content/dist/rhel9/$releasever/x86_64/appstream/os
```

**Nota**: Sostituire `$releasever` con `9` negli URL.
## Creazione repository CUSTOM
**Software → Manage → Repositories → Create Repository**
### Repository 1: BaseOS

| Campo | Valore |
|-------|--------|
| Repository Label | `rhel9-baseos-cdn` |
| Repository URL | `https://cdn.redhat.com/content/dist/rhel9/9/x86_64/baseos/os` |
| Repository Type | `yum` |
| Has Signed Metadata? | **DESELEZIONATO** |
| SSL CA Certificate | `RHEL9-CA-RedHat` |
| SSL Client Certificate | `RHEL9-Entitlement-Cert` |
| SSL Client Key | `RHEL9-Entitlement-Key` |
### Repository 2: AppStream

| Campo | Valore |
|-------|--------|
| Repository Label | `rhel9-appstream-cdn` |
| Repository URL | `https://cdn.redhat.com/content/dist/rhel9/9/x86_64/appstream/os` |
| Repository Type | `yum` |
| Has Signed Metadata? | **DESELEZIONATO** |
| SSL CA Certificate | `RHEL9-CA-RedHat` |
| SSL Client Certificate | `RHEL9-Entitlement-Cert` |
| SSL Client Key | `RHEL9-Entitlement-Key` |

**Importante**: I repository Red Hat CDN non hanno metadati firmati, quindi "Has Signed Metadata?" deve essere deselezionato.
## NON TESTATO - Creazione canali CUSTOM
**Software → Manage → Channels → Create Channel**
### Canale 1: BaseOS

| Campo | Valore |
|-------|--------|
| Channel Name | `RHEL 9 BaseOS CDN` |
| Channel Label | `rhel9-baseos-cdn` |
| Parent Channel | `rhel9-pool-uyuni` |
| Architecture | `x86_64` |
| Channel Summary | `Red Hat Enterprise Linux 9 BaseOS from CDN` |
| Repository Checksum Type | `SHA-256` |
| GPG Key URL | `file:///etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release` |
| GPG Key ID | `FD431D51` |
| GPG Key Fingerprint | `567E 347A D004 4ADE 55BA 8A5F 199E 2F91 FD43 1D51` |
### Canale 2: AppStream

| Campo | Valore |
|-------|--------|
| Channel Name | `RHEL 9 AppStream CDN` |
| Channel Label | `rhel9-appstream-cdn` |
| Parent Channel | `rhel9-pool-uyuni` |
| Architecture | `x86_64` |
| Channel Summary | `Red Hat Enterprise Linux 9 AppStream from CDN` |
| Repository Checksum Type | `SHA-256` |
| GPG Key URL | `file:///etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release` |
| GPG Key ID | `FD431D51` |
| GPG Key Fingerprint | `567E 347A D004 4ADE 55BA 8A5F 199E 2F91 FD43 1D51` |
## Associazione repository ai canali
### Canale BaseOS
**Software → Manage → Channels → RHEL 9 BaseOS CDN → Repositories**
1. Spunta `rhel9-baseos-cdn`
2. Clicca **Update Repositories**
### Canale AppStream
**Software → Manage → Channels → RHEL 9 AppStream CDN → Repositories**
1. Spunta `rhel9-appstream-cdn`
2. Clicca **Update Repositories**
## Sincronizzazione dei canali
### Avvia la sincronizzazione
**Software → Manage → Channels → [canale] → Sync → Sync Now**
Esegui per entrambi i canali:
- RHEL 9 BaseOS CDN
- RHEL 9 AppStream CDN
### Monitoraggio
**Da Web UI**: Admin → Task Schedules
**Da CLI**:
```bash
tail -f /var/log/rhn/reposync/rhel9-baseos-cdn.log
tail -f /var/log/rhn/reposync/rhel9-appstream-cdn.log
```
**Nota**: La sincronizzazione può richiedere diverse ore. I canali RHEL 9 sono molto grandi (~50-60 GB totali).
#### Verifica spazio disco
```bash
df -h /var/spacewalk/
```
## Creazione Bootstrap Repository
Sul **server UYUNI**:
```bash
mgr-create-bootstrap-repo
```
Se usi container:
```bash
mgrctl exec -ti mgr-create-bootstrap-repo
```
Seleziona `rhel9-pool-uyuni` quando richiesto.
## Content Lifecycle Management (CLM)
### Crea il progetto
**Content Lifecycle → Projects → Create Project**

| Campo | Valore |
|-------|--------|
| Name | `RHEL 9 Lifecycle` |
| Label | `rhel9-lifecycle` |
| Description | `Content Lifecycle for RHEL 9` |
### Aggiungi Sources
Nella pagina del progetto, sezione **Sources** → **Attach/Detach Sources**
Seleziona:
- `RHEL 9 BaseOS CDN`
- `RHEL 9 AppStream CDN`
- `rhel9-uyuni-client`

Clicca **Save**
### Aggiungi Environment: test
**Environments → Add Environment**

| Campo | Valore |
|-------|--------|
| Name | `test` |
| Label | `test` |
| Description | `Test environment` |
### Build
Clicca **Build** per creare la prima versione dei canali CLM.
## Creazione Activation Key
**Systems → Activation Keys → Create Key**

| Campo        | Valore                  |
| ------------ | ----------------------- |
| Description  | `RHEL 9 Activation Key` |
| Key          | `1-rhel9`               |
| Base Channel | `rhel9-pool-uyuni-test` |
Dopo la creazione, vai su **Child Channels** e seleziona:
- `rhel9-lifecycle-rhel-9-baseos-cdn-test`
- `rhel9-lifecycle-rhel-9-appstream-cdn-test`
- `rhel9-lifecycle-rhel9-uyuni-client-test`
Clicca **Update Key**
## Bootstrap del client RHEL
**Systems → Bootstrapping**

| Campo | Valore |
|-------|--------|
| Host | `<IP del client RHEL>` |
| SSH Port | `22` |
| User | `root` o utente con sudo |
| Authentication | Password o SSH Key |
| Activation Key | `1-rhel9` |
Se usi un utente non-root, spunta **Use sudo**.
Clicca **Bootstrap**