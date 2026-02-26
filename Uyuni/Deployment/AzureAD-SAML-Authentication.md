## Integrazione Azure AD (Entra ID) con Uyuni — SAML 2.0 SSO

> **Contesto specifico**: Uyuni 2025.x containerizzato su Podman, openSUSE Leap 15.6, Azure.
> Azure AD (Entra ID) nativo **non espone LDAP/Kerberos**, quindi l'unica integrazione
> diretta supportata è **SAML 2.0**.

---

## Architettura

```
Browser utente
      │  HTTPS (redirect SAML)
      ▼
Azure AD (Entra ID)
      │  SAML Assertion (email, nome, gruppi)
      ▼
Uyuni Web UI — ACS endpoint
  /rhn/saml/acs
      │  JIT provisioning (primo login → utente creato in Uyuni)
      ▼
Uyuni DB (utenti locali con flag saml=true)
```

**User Sync**: Uyuni non ha un endpoint SCIM nativo. Gli utenti vengono creati
automaticamente al primo login SAML (**Just-In-Time provisioning**). I ruoli
vengono assegnati manualmente dall'admin dopo il primo accesso, oppure
automaticamente tramite mapping gruppi AD (vedi FASE 4).

---

## Prerequisiti

- Accesso a **Azure Portal** con ruolo `Application Administrator` o `Global Administrator`
- FQDN del server Uyuni risolvibile da browser degli utenti (es. `uyuni-server-test.uyuni.internal`)
- HTTPS attivo su Uyuni (il certificato self-signed va bene, ma gli utenti devono accettarlo)
- Accesso root al server Uyuni (via Azure Bastion)

---
## FASE 1 — Registra Uyuni come Enterprise Application in Azure AD

### 1.1 Crea la nuova applicazione

1. **Azure Portal** → **Microsoft Entra ID** → **Enterprise Applications**
2. **+ New application** → **+ Create your own application**
3. Nome: `Uyuni Server` (o `Uyuni-SPM-Test`)
4. Seleziona: **Integrate any other application you don't find in the gallery**
5. **Create**

### 1.2 Configura Single Sign-On SAML

1. Nella pagina dell'app → **Single sign-on** → **SAML**
2. **Basic SAML Configuration** → Edit

| Campo                      | Valore                                                       |
| -------------------------- | ------------------------------------------------------------ |
| **Identifier (Entity ID)** | `https://uyuni-server-test.uyuni.internal/rhn/saml/metadata` |
| **Reply URL (ACS URL)**    | `https://uyuni-server-test.uyuni.internal/rhn/saml/acs`      |
| **Sign on URL**            | `https://uyuni-server-test.uyuni.internal`                   |
| **Relay State**            | *(lascia vuoto)*                                             |
| **Logout URL**             | `https://uyuni-server-test.uyuni.internal/rhn/saml/logout`   |

> Sostituisci `uyuni-server-test.uyuni.internal` con il tuo FQDN reale.

### 1.3 Configura gli attributi SAML (Claims)

In **Attributes & Claims** → Edit, verifica che siano presenti questi claim:

| Claim Name                                                           | Sorgente  | Attributo Azure AD       |
| -------------------------------------------------------------------- | --------- | ------------------------ |
| `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress` | Attributo | `user.mail`              |
| `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname`    | Attributo | `user.givenname`         |
| `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname`      | Attributo | `user.surname`           |
| `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name`         | Attributo | `user.userprincipalname` |

**Aggiunta claim gruppi** (necessaria per il role mapping automatico):
1. **+ Add a group claim**
2. Seleziona: **Security groups** (o **All groups**)
3. Source attribute: **Group ID** (usa ObjectId) oppure **Cloud-only group display names**
4. Nome claim: `http://schemas.microsoft.com/ws/2008/06/identity/claims/groups`

### 1.4 Scarica il Metadata XML di Azure AD

In **SAML Certificates** → **Federation Metadata XML** → **Download**

Salva il file come `azure-ad-metadata.xml`. Lo userai nella FASE 3.

### 1.5 Annota i dati dell'IDP

Prendi nota di:

| Parametro | Dove trovarlo |
|---|---|
| **Login URL** | Set up Uyuni Server → Login URL |
| **Azure AD Identifier** | Set up Uyuni Server → Azure AD Identifier |
| **Logout URL** | Set up Uyuni Server → Logout URL |
| **Thumbprint certificato** | SAML Certificates → Thumbprint |

Questi URL hanno il formato:
```
Login URL:    https://login.microsoftonline.com/<tenant-id>/saml2
Identifier:   https://sts.windows.net/<tenant-id>/
Logout URL:   https://login.microsoftonline.com/<tenant-id>/saml2
```

### 1.6 Assegna utenti/gruppi all'applicazione

1. **Users and groups** → **+ Add user/group**
2. Aggiungi il gruppo AD o gli utenti che devono avere accesso a Uyuni
3. Gli utenti non in questa lista riceveranno un errore AADSTS al login

---

## FASE 2 — Copia il Metadata XML nel container Uyuni

```bash
# Copia il file dal tuo PC al server Uyuni tramite git o scp
# (data la policy no-SCP, usa git)

# Crea una directory nel repo per i file di configurazione
mkdir -p /opt/Security-Patch-Manager/Uyuni/Config/saml/
# Copia azure-ad-metadata.xml in questa directory e fai git push

# Sul server Uyuni (10.172.2.17):
cd /opt/Security-Patch-Manager && git pull origin main

# Copia il metadata dentro il container
podman cp /opt/Security-Patch-Manager/Uyuni/Config/saml/azure-ad-metadata.xml \
  uyuni-server:/etc/rhn/azure-ad-metadata.xml
```

---

## FASE 3 — Configura SAML in Uyuni (dentro il container)

### 3.1 Ottieni il certificato SP di Uyuni

Uyuni genera automaticamente un certificato SP per firmare le richieste SAML:

```bash
# Verifica se il certificato SP esiste già
mgrctl exec -- ls -la /etc/rhn/saml/

# Se non esiste, genera la coppia chiave/certificato SP
mgrctl exec -- openssl req -x509 -nodes -days 3650 \
  -newkey rsa:2048 \
  -keyout /etc/rhn/saml/sp-key.pem \
  -out /etc/rhn/saml/sp-cert.pem \
  -subj "/CN=uyuni-server-test.uyuni.internal/O=LEONARDO/C=IT"

mgrctl exec -- chmod 600 /etc/rhn/saml/sp-key.pem
mgrctl exec -- chmod 644 /etc/rhn/saml/sp-cert.pem
```

### 3.2 Configura rhn.conf per SAML

```bash
mgrctl exec -- bash -c "cat >> /etc/rhn/rhn.conf << 'EOF'

# ===== SAML SSO - Azure AD (Entra ID) =====
java.saml_enabled = true
java.saml_entityid = https://uyuni-server-test.uyuni.internal/rhn/saml/metadata
java.saml_acs_url = https://uyuni-server-test.uyuni.internal/rhn/saml/acs
java.saml_slo_url = https://uyuni-server-test.uyuni.internal/rhn/saml/logout

# IDP metadata (file locale o URL diretto Azure AD)
java.saml_idp_metadata = /etc/rhn/azure-ad-metadata.xml

# Certificato SP (per firmare AuthnRequest)
java.saml_sp_cert = /etc/rhn/saml/sp-cert.pem
java.saml_sp_key  = /etc/rhn/saml/sp-key.pem

# Mapping attributi SAML → campi Uyuni
java.saml_attr_email     = http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress
java.saml_attr_firstname = http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname
java.saml_attr_lastname  = http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname

# Comportamento
java.saml_create_user_on_first_login = true   # JIT provisioning
java.saml_default_role = satellite_admin       # Ruolo assegnato al primo login
                                               # Opzioni: satellite_admin, org_admin, channel_admin, etc.
EOF"
```

> **Nota**: I nomi esatti dei parametri `java.saml_*` possono variare tra versioni.
> Verifica con `mgrctl exec -- grep -i saml /etc/rhn/rhn.conf.d/*.conf` se esistono
> file di configurazione separati da UYUNI 2025.x.

### 3.3 Alternativa: Configurazione da Web UI (se disponibile in 2025.x)

Alcune versioni di Uyuni espongono la configurazione SAML dalla Web UI:

```
Admin → Authentication Methods → SAML SSO
```

Se il menu è presente, preferisci questo metodo alla modifica manuale di `rhn.conf`.

### 3.4 Riavvia Tomcat per applicare la configurazione

```bash
mgrctl exec -- systemctl restart tomcat.service

# Verifica che Tomcat si sia riavviato senza errori
mgrctl exec -- systemctl status tomcat.service --no-pager

# Controlla i log per errori SAML
mgrctl exec -- tail -50 /var/log/rhn/rhn_web_ui.log | grep -i saml
```

---

## FASE 4 — Verifica Metadata SP di Uyuni

Dopo il riavvio, il metadata SP di Uyuni deve essere accessibile:

```bash
curl -k https://uyuni-server-test.uyuni.internal/rhn/saml/metadata
```

Output atteso (XML con EntityDescriptor):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
  entityID="https://uyuni-server-test.uyuni.internal/rhn/saml/metadata">
  ...
  <md:AssertionConsumerService
    Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
    Location="https://uyuni-server-test.uyuni.internal/rhn/saml/acs"/>
</md:EntityDescriptor>
```

Copia questo URL nell'**App Federation Metadata URL** su Azure AD (opzionale ma comodo
per aggiornamento automatico del metadata).

---

## FASE 5 — Role Mapping automatico via Gruppi AD

Per assegnare ruoli Uyuni automaticamente in base ai gruppi AD:

### 5.1 Gruppi AD consigliati

Crea questi gruppi in Azure AD (o usa gruppi esistenti):

| Gruppo AD | Ruolo Uyuni | Permessi |
|---|---|---|
| `uyuni-admins` | `satellite_admin` | Accesso completo |
| `uyuni-operators` | `org_admin` | Gestione organizzazione |
| `uyuni-sysadmins` | `system_group_admin` | Gestione sistemi |
| `uyuni-readonly` | *(nessun ruolo aggiuntivo)* | Sola lettura |

### 5.2 Configurazione mapping gruppi in rhn.conf

```bash
mgrctl exec -- bash -c "cat >> /etc/rhn/rhn.conf << 'EOF'

# Mapping gruppi AD (ObjectId del gruppo Azure AD) → ruolo Uyuni
java.saml_role_attr = http://schemas.microsoft.com/ws/2008/06/identity/claims/groups
java.saml_role_map.satellite_admin = <ObjectId-gruppo-uyuni-admins>
java.saml_role_map.org_admin = <ObjectId-gruppo-uyuni-operators>
java.saml_role_map.system_group_admin = <ObjectId-gruppo-uyuni-sysadmins>
EOF"
```

> Recupera gli ObjectId dei gruppi da Azure Portal:
> **Entra ID → Groups → [gruppo] → Object ID**

### 5.3 Riavvia dopo la modifica

```bash
mgrctl exec -- systemctl restart tomcat.service
```

---

## FASE 6 — Test End-to-End

### 6.1 Test SP-initiated SSO (da Uyuni)

1. Apri `https://uyuni-server-test.uyuni.internal`
2. La pagina di login mostra un pulsante **"Sign in with Azure AD"** (o redirect automatico)
3. Sei rediretto a `login.microsoftonline.com`
4. Inserisci credenziali aziendali
5. Autenticazione MFA (se configurata in Azure AD)
6. Redirect ad Uyuni → login effettuato

### 6.2 Test IDP-initiated SSO (da Azure AD)

1. **Azure Portal → Enterprise Applications → Uyuni Server**
2. **Single sign-on → Test** → **Test sign in**
3. Se la configurazione è corretta, vieni reindirizzato a Uyuni loggato

### 6.3 Verifica utente creato (JIT provisioning)

```
Uyuni Web UI → Admin → Users
```

L'utente deve essere apparso con:
- Username = UPN Azure AD (es. `mario.rossi@company.onmicrosoft.com`)
- Email = email aziendale
- Auth method = SAML

---

## FASE 7 — Gestione utenti post-login

### Assegnazione ruoli manuale (primo accesso)

Al primo login, l'utente viene creato con il ruolo di default (`java.saml_default_role`).
L'admin può modificare i ruoli da:

```
Admin → Users → [utente] → Roles
```

### Revoca accesso

Per revocare l'accesso a un utente:
1. **Azure AD**: rimuovilo dal gruppo/app → non potrà più autenticarsi via SAML
2. **Uyuni**: opzionalmente disabilita l'account in `Admin → Users → [utente] → Disable`

---

## Troubleshooting

| Sintomo | Causa | Soluzione |
|---|---|---|
| `AADSTS700016` — application not found | Entity ID non corrisponde | Verifica `Identifier (Entity ID)` in Azure AD |
| `AADSTS750054` — SAMLRequest not present | Redirect mal configurato | Verifica `Sign on URL` in Azure AD |
| Redirect loop alla login | ACS URL errato | Verifica `/rhn/saml/acs` sia raggiungibile |
| `Tomcat 500 error` dopo SAML response | Errore mapping attributi | Log: `mgrctl exec -- cat /var/log/rhn/rhn_web_ui.log` |
| Utente non creato dopo login | JIT provisioning disabilitato | Verifica `java.saml_create_user_on_first_login = true` |
| Certificato SP non trovato | Percorso chiave/cert errato in rhn.conf | `mgrctl exec -- ls /etc/rhn/saml/` |
| Errore `Signature validation failed` | Certificato IDP scaduto o metadata non aggiornato | Riscari metadata XML da Azure AD |
| Configurazione SAML persa dopo upgrade | Container ricreato da mgradm | Usa script post-upgrade (vedi sotto) |

### Script post-upgrade per persistenza configurazione

Dopo ogni `mgradm upgrade`, il container viene ricreato. Per mantenere la configurazione SAML:

```bash
cat > /usr/local/bin/uyuni-post-upgrade.sh << 'EOF'
#!/bin/bash
# Ripristina configurazione SAML dopo upgrade mgradm

# Ricopia il metadata Azure AD
podman cp /opt/Security-Patch-Manager/Uyuni/Config/saml/azure-ad-metadata.xml \
  uyuni-server:/etc/rhn/azure-ad-metadata.xml

# Ricopia i certificati SP
podman cp /path/to/sp-cert.pem uyuni-server:/etc/rhn/saml/sp-cert.pem
podman cp /path/to/sp-key.pem  uyuni-server:/etc/rhn/saml/sp-key.pem

# Applica configurazione rhn.conf SAML
podman exec uyuni-server bash -c "
cat >> /etc/rhn/rhn.conf << 'RHNCONF'
java.saml_enabled = true
# ... resto della configurazione ...
RHNCONF
systemctl restart tomcat.service
"
EOF
chmod +x /usr/local/bin/uyuni-post-upgrade.sh
```

> **Alternativa più robusta**: Usa un ConfigMap/volume mount per `/etc/rhn/rhn.conf.d/saml.conf`
> (se mgradm supporta volume mount di config aggiuntive).

---

## Note finali

- Il **certificato SP** (coppia chiave/cert) deve essere tenuto fuori dal container in modo permanente
  (es. in `/opt/Security-Patch-Manager/Uyuni/Config/saml/` nel repo o in un Azure Key Vault)
- Il **metadata Azure AD** si aggiorna quando i certificati IDP scadono (di solito ogni 3 anni):
  - Azure AD avvisa via email 60 giorni prima della scadenza
  - Aggiorna il file `azure-ad-metadata.xml` e riapplica
- Per **Azure AD MFA**: è trasparente, gestito interamente da Azure AD prima della SAML assertion

---

## Riferimenti

- [Uyuni Documentation — Authentication Methods](https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/auth-methods.html)
- [Microsoft — Azure AD SAML Integration Tutorial](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/add-application-portal-setup-sso)
- [SAML 2.0 Protocol Reference](https://docs.oasis-open.org/security/saml/v2.0/)
- [Uyuni GitHub — SAML Issues/PRs](https://github.com/uyuni-project/uyuni/labels/saml)
