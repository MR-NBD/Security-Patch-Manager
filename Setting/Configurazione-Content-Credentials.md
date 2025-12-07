## Configurazione Content Credentials (Chiavi GPG)
Le chiavi GPG sono necessarie per verificare l'autenticità dei pacchetti.
### 1 - Scarica le chiavi GPG di Ubuntu
#### Crea directory se non esiste
```bash
mkdir -p /etc/pki/rpm-gpg/import
```
#### Scarica Ubuntu Archive Keyring
```bash
curl -o /etc/pki/rpm-gpg/import/ubuntu-archive-keyring.gpg \
  "http://archive.ubuntu.com/ubuntu/project/ubuntu-archive-keyring.gpg"
```
#### Scarica Ubuntu Archive Signing Key (2018)
```bash
curl -o /etc/pki/rpm-gpg/import/ubuntu-archive-key-2018.asc \
  "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x871920D1991BC93C"
```
### 2 - Estrai le chiavi in formato ASCII
#### Converti il keyring in formato ASCII per l'import in Foreman
```bash
gpg --no-default-keyring \
  --keyring /etc/pki/rpm-gpg/import/ubuntu-archive-keyring.gpg \
  --export --armor > /etc/pki/rpm-gpg/import/ubuntu-keys-ascii.asc
```
### 3 - Crea Content Credential in Foreman
**Via Web UI (raccomandato):**
1. Vai su **Content → Content Credentials**
2. Clicca **Create Content Credential**
3. Compila:
    - **Name**: `Ubuntu Archive Key`
    - **Content Credential Type**: `GPG Key`
    - **Content Credential Contents**: Copia il contenuto del file:

```bash
cat /etc/pki/rpm-gpg/import/ubuntu-keys-ascii.asc
```
4. Clicca **Save**

**Via CLI:**
```bash
hammer content-credentials create \
  --organization "PSN-ASL06" \
  --name "Ubuntu Archive Key" \
  --content-type "gpg_key" \
  --path "/etc/pki/rpm-gpg/import/ubuntu-keys-ascii.asc"
```
