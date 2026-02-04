https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/clients-rh-cdn.html
### Certificati necessari per RHEL CDN

| Certificato             | Path sul sistema RHEL registrato    | Tipo in UYUNI | Scopo                                          |
| ----------------------- | ----------------------------------- | ------------- | ---------------------------------------------- |
| Entitlement Certificate | /etc/pki/entitlement/$<ID>$.pem     | SSL           | Prova la validità della  subscription          |
| Entitlement Key         | /etc/pki/entitlement/$<ID>$-key.pem | SSL           | Chiave privata associata al certificato        |
| Red Hat CA              | /etc/rhsm/ca/redhat-uep.pem         | SSL           | CA root per validare la connessione SSL al CDN |
Come ottenerli: 
### Su una VM RHEL registrata con subscription-manager
```bash
subscription-manager register --username=TUO_USER --password=TUA_PASS
```
```bash
subscription-manager attach --auto
```
### I certificati vengono salvati in:
```
ls /etc/pki/entitlement/
ls /etc/rhsm/ca/
```

#### Come caricarli su UYUNI

Web UI: **Systems** → **Autoinstallation** → **GPG and SSL Keys** → **Create Stored Key/Cert**
Per ogni file:
1. Description: es. `Entitlement-Cert-RHEL9`
2. Type: `SSL`
3. Upload file o incolla contenuto

#### Quando si crea un canale software in UYUNI per RHEL:
*  1. Vai su: **Software** → *Manage* → **Channels** → **Create Channel**
  1. Nella sezione **Repository/Sync**, quando si configura il repository CDN Red Hat, si dovrà specificare:
    - SSL CA Certificate: seleziona redhat-uep.pem (Red Hat CA)
    - SSL Client Certificate: seleziona <ID>.pem (Entitlement Certificate)
    - SSL Client Key: seleziona <ID>-key.pem (Entitlement Key)
  2. URL del repository: sarà qualcosa tipo:
  https://cdn.redhat.com/content/dist/rhel9/9/x86_64/baseos/os

  Quando carichi i tre file in GPG and SSL Keys, usa nomi descrittivi come:
  - RHEL9-CA-RedHat
  - RHEL9-Entitlement-Cert
  - RHEL9-Entitlement-Key