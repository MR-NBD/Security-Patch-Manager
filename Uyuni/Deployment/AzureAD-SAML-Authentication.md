## Integrazione Azure AD (Entra ID) con Uyuni — SAML 2.0 SSO

> **Contesto specifico**: Uyuni 2025.x containerizzato su Podman, openSUSE Leap 15.6, Azure.
> Azure AD (Entra ID) nativo **non espone LDAP/Kerberos**, quindi l'unica integrazione
> diretta supportata è **SAML 2.0**.

---

## Architettura

```
Browser utente
      │  HTTPS → redirect a login.microsoftonline.com
      ▼
Azure AD (Entra ID)
      │  SAML Assertion (uid, email, nome)
      ▼
Uyuni Web UI — ACS endpoint
  /rhn/manager/sso/acs
      │  Lookup utente per claim "uid"
      ▼
Uyuni DB (utente pre-creato con login = UPN Azure AD)
```

**Nessun JIT provisioning**: Uyuni **non crea** utenti automaticamente al primo login.
Ogni utente deve essere creato manualmente in Uyuni prima del primo accesso SSO.
Il login Uyuni deve corrispondere **esattamente** (case-sensitive) al valore del claim `uid`
inviato da Azure AD — Azure invia l'UPN in **minuscolo**.

**SSO è esclusivo**: con `java.sso = true` attivo, tutti i login web vengono reindirizzati
ad Azure AD. Il form di login locale non funziona più via browser.
Le API XML-RPC continuano a usare le credenziali locali.

---

## Prerequisiti

- Accesso a **Azure Portal** con ruolo `Application Administrator` o `Global Administrator`
- FQDN del server Uyuni risolvibile da browser degli utenti (es. `uyuni-server-test.uyuni.internal`)
- Il browser degli utenti deve raggiungere Uyuni tramite **FQDN** (non IP) — il redirect SAML usa il FQDN
- HTTPS attivo su Uyuni (il certificato self-signed va bene)
- Accesso SSH al server Uyuni host (via Azure Bastion)
- Tenant ID di Azure AD
- Federation Metadata XML scaricato dall'Enterprise App Azure AD

---

## FASE 1 — Registra Uyuni come Enterprise Application in Azure AD

### 1.1 Crea la nuova applicazione

1. **Azure Portal** → **Microsoft Entra ID** → **Enterprise Applications**
2. **+ New application** → **+ Create your own application**
3. Nome: `Uyuni Server`
4. Seleziona: **Integrate any other application you don't find in the gallery**
5. **Create**

> "Create your own application" è il metodo corretto per qualsiasi app non presente
> nella Microsoft gallery (Uyuni non è un'app certificata Microsoft).

### 1.2 Configura Single Sign-On SAML

1. Nella pagina dell'app → **Single sign-on** → **SAML**
2. **Basic SAML Configuration** → Edit

| Campo | Valore |
|---|---|
| **Identifier (Entity ID)** | `https://uyuni-server-test.uyuni.internal/rhn/manager/sso/metadata` |
| **Reply URL (ACS URL)** | `https://uyuni-server-test.uyuni.internal/rhn/manager/sso/acs` |
| **Sign on URL** | `https://uyuni-server-test.uyuni.internal` |
| **Relay State** | *(lascia vuoto)* |
| **Logout URL** | `https://uyuni-server-test.uyuni.internal/rhn/manager/sso/sls` |

> Sostituisci `uyuni-server-test.uyuni.internal` con il tuo FQDN reale.
> Gli endpoint SSO in Uyuni 2025.x sono `/rhn/manager/sso/*` (non `/rhn/saml/*`).

### 1.3 Configura gli attributi SAML (Claims)

In **Attributes & Claims** → Edit, aggiungi il claim `uid` (obbligatorio per il login):

| Claim Name | Namespace | Source | Source attribute |
|---|---|---|---|
| `uid` | *(vuoto)* | `Attribute` | `user.userprincipalname` |

> **CRITICO**: il campo "Source attribute" deve essere **selezionato dal menu a tendina**, non
> digitato manualmente. Se viene digitato a mano, Azure AD invia la stringa letterale
> `user.userprincipalname` invece dell'UPN reale dell'utente, causando il login fail.
>
> Il claim `uid` è quello che Uyuni usa per identificare l'utente nel proprio database.
> Azure AD invia il valore UPN in **minuscolo** — il login Uyuni deve corrispondere esattamente.

### 1.4 Scarica il Federation Metadata XML

In **SAML Certificates** → **Federation Metadata XML** → **Download**

Salva il file (es. `Uyuni Server.xml`). Servirà per estrarre il certificato IDP.

### 1.5 Annota il Tenant ID

Da **Azure Portal** → **Microsoft Entra ID** → **Overview** → copia il **Tenant ID**.

Gli URL IDP hanno il formato:
```
Login URL:   https://login.microsoftonline.com/<tenant-id>/saml2
Identifier:  https://sts.windows.net/<tenant-id>/
Logout URL:  https://login.microsoftonline.com/<tenant-id>/saml2
```

### 1.6 Assegna utenti/gruppi all'applicazione

1. **Users and groups** → **+ Add user/group**
2. Aggiungi gli utenti o gruppi AD che devono accedere a Uyuni
3. Gli utenti non assegnati riceveranno un errore AADSTS al login

---

## FASE 2 — Carica il Federation Metadata XML sul server Uyuni

Il file XML viene usato per estrarre il certificato IDP (via script Python).
Caricalo nel container tramite copia da terminale:

```bash
# Sul server Uyuni host (10.172.2.17), crea il file con cat+heredoc:
cat > /tmp/azure-ad-metadata.xml << 'EOF'
[incolla qui il contenuto del file XML scaricato da Azure AD]
EOF

# Copia nel container
podman cp /tmp/azure-ad-metadata.xml uyuni-server:/etc/rhn/azure-ad-metadata.xml

# Verifica
mgrctl exec -- head -3 /etc/rhn/azure-ad-metadata.xml
```

> **Attenzione**: il file XML è tipicamente 5-10KB. Con copy-paste via Azure Bastion
> verifica che il file non sia troncato dopo il copia-incolla.

---

## FASE 3 — Pre-crea gli utenti in Uyuni

**Prima** di abilitare SSO, crea in Uyuni tutti gli utenti che accederanno via Azure AD.

1. Uyuni Web UI → **Admin → Users → User List → Create User**
2. **Login**: inserisci l'UPN Azure AD in **minuscolo** (es. `mario.rossi@domain.onmicrosoft.com`)
3. **Password**: imposta una password qualsiasi (non verrà usata con SSO attivo)
4. Dopo la creazione, assegna il ruolo appropriato dalla sezione **Roles**

> Il login deve corrispondere **esattamente** al valore che Azure AD invierà nel claim `uid`.
> Azure AD invia sempre il valore in minuscolo, indipendentemente da come è salvato nel portale.

---

## FASE 4 — Configura SSO in rhn.conf

Tutti i parametri SSO vanno in `/etc/rhn/rhn.conf` con il prefisso `java.sso.onelogin.saml2.*`.
Usa uno script Python per evitare problemi con stringhe lunghe (il certificato è ~1000 caratteri).

### 4.1 Scrivi lo script di configurazione sul server host

```bash
cat > /tmp/add_sso_full.py << 'PYEOF'
import xml.etree.ElementTree as ET

# Estrai il certificato IDP dal metadata XML
tree = ET.parse('/etc/rhn/azure-ad-metadata.xml')
ns = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}
cert = tree.getroot().find('.//ds:X509Certificate', ns).text.replace('\n','').replace(' ','').strip()

tenant = "IL-TUO-TENANT-ID"
fqdn = "uyuni-server-test.uyuni.internal"

config = f"""
# ===== SAML SSO Azure AD =====
java.sso = true
java.sso.onelogin.saml2.strict = true
java.sso.onelogin.saml2.debug = true
java.sso.onelogin.saml2.sp.entityid = https://{fqdn}/rhn/manager/sso/metadata
java.sso.onelogin.saml2.sp.assertion_consumer_service.url = https://{fqdn}/rhn/manager/sso/acs
java.sso.onelogin.saml2.sp.single_logout_service.url = https://{fqdn}/rhn/manager/sso/sls
java.sso.onelogin.saml2.idp.entityid = https://sts.windows.net/{tenant}/
java.sso.onelogin.saml2.idp.single_sign_on_service.url = https://login.microsoftonline.com/{tenant}/saml2
java.sso.onelogin.saml2.idp.single_logout_service.url = https://login.microsoftonline.com/{tenant}/saml2
java.sso.onelogin.saml2.idp.x509cert = {cert}
"""

# Rimuovi eventuali blocchi SSO precedenti
lines = open('/etc/rhn/rhn.conf').readlines()
lines = [l for l in lines if 'java.sso' not in l and 'onelogin' not in l and 'SAML SSO' not in l]
lines.append(config)
open('/etc/rhn/rhn.conf', 'w').writelines(lines)
print("Done, cert length:", len(cert))
PYEOF
```

> Sostituisci `IL-TUO-TENANT-ID` con il Tenant ID Azure AD.

### 4.2 Esegui lo script nel container e riavvia

```bash
# Copia lo script nel container ed eseguilo
podman cp /tmp/add_sso_full.py uyuni-server:/tmp/add_sso_full.py
mgrctl exec -- python3 /tmp/add_sso_full.py

# Riavvia Uyuni (non solo Tomcat — serve mgradm restart)
mgradm restart
```

> **Importante**: usare `mgradm restart` e non `systemctl restart tomcat`.
> Solo `mgradm restart` ricarica correttamente tutta la stack containerizzata.

---

## FASE 5 — Test

Dopo il riavvio (attendere 60-90 secondi):

```bash
# Verifica che la route SSO sia attiva (deve rispondere, non 404)
curl -k -o /dev/null -w "%{http_code}\n" https://uyuni-server-test.uyuni.internal/rhn/manager/sso
```

Apri il browser su `https://uyuni-server-test.uyuni.internal` — il login deve redirigere automaticamente ad Azure AD.

### Errori comuni al primo test

| Errore | Causa | Soluzione |
|---|---|---|
| Pagina login Uyuni classica (nessun redirect) | `java.sso` non letto o route non registrate | Verifica che tutti i parametri `java.sso.onelogin.saml2.*` siano in `rhn.conf`; esegui `mgradm restart` |
| `AADSTS700016` — application not found | Entity ID non corrisponde | Verifica `Identifier` in Azure AD: deve essere `/rhn/manager/sso/metadata` |
| "Internal error... Have you created the user?" — log: `Could not find user user.userprincipalname` | Claim `uid` configurato con valore digitato a mano: Azure AD invia la stringa letterale invece dell'UPN | In Azure AD → Attributes & Claims: elimina il claim `uid` e ricrealo selezionando `user.userprincipalname` dal **menu a tendina** (non digitarlo) |
| "Internal error... Have you created the user?" — log: `Could not find user alberto.rossi@...` | Login utente in Uyuni non corrisponde all'UPN | Il login in Uyuni deve essere in **minuscolo** e identico all'UPN Azure AD |
| `AADSTS750054` — SAMLRequest not present | Sign on URL errato | Verifica `Sign on URL` in Azure AD |
| Metadata restituisce HTML invece di XML | Bug noto Uyuni 2025.10 (fix in release post-Feb 2026) | Il login SSO funziona comunque — ignorare |

---

## FASE 6 — Assegna il ruolo SUSE Manager Administrator all'utente SSO

Con SSO attivo, l'utente `admin` non può fare login via browser, quindi il ruolo non può essere
assegnato dalla Web UI. Usa le **API XML-RPC** (che continuano a usare credenziali locali):

```bash
cat > /tmp/grant_admin.py << 'PYEOF'
import xmlrpc.client, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

client = xmlrpc.client.ServerProxy(
    "https://10.172.2.17/rpc/api",
    context=ctx
)

session = client.auth.login("admin", "LA-TUA-PASSWORD-ADMIN")
client.user.addRole(session, "utente@domain.onmicrosoft.com", "satellite_admin")
print("Ruolo assegnato con successo")
roles = client.user.listRoles(session, "utente@domain.onmicrosoft.com")
print("Ruoli attuali:", roles)
client.auth.logout(session)
PYEOF

python3 /tmp/grant_admin.py
rm /tmp/grant_admin.py
```

> Sostituisci `LA-TUA-PASSWORD-ADMIN` e `utente@domain.onmicrosoft.com` con i valori reali.
> Lo script va eseguito **sull'host Uyuni** (non via `mgrctl exec`) — l'API è esposta
> sull'IP della VM (`10.172.2.17`), non su `localhost`.
> `satellite_admin` è il nome interno del ruolo "SUSE Manager Administrator".

**Nota**: l'utente `admin` locale **non va eliminato** — viene usato dall'SPM Orchestrator
per le chiamate XML-RPC (`UYUNI_USER=admin` nel `.env`). Con SSO attivo è comunque
inaccessibile via browser.

---

## Procedura di emergenza — Disabilita SSO

Se rimani bloccato fuori da Uyuni con SSO attivo:

```bash
cat > /tmp/disable_sso.py << 'PYEOF'
lines = open('/etc/rhn/rhn.conf').readlines()
lines = [l for l in lines if 'java.sso' not in l and 'onelogin' not in l and 'SAML SSO' not in l]
open('/etc/rhn/rhn.conf', 'w').writelines(lines)
print("SSO disabilitato")
PYEOF
podman cp /tmp/disable_sso.py uyuni-server:/tmp/disable_sso.py
mgrctl exec -- python3 /tmp/disable_sso.py
mgradm restart
```

Dopo il riavvio il login locale torna attivo.

---

## Note tecniche Uyuni 2025.x

- Gli endpoint SSO sono registrati da `SSOController` via **Spark Java** (non in `web.xml` o `struts-config.xml`)
- La configurazione SSO va **solo in `/etc/rhn/rhn.conf`** con prefisso `java.sso.onelogin.saml2.*`
- Il file `/usr/share/rhn/config-defaults/rhn_java_sso.conf` contiene solo valori di default — non modificarlo
- I file in `/tmp` dentro il container vengono persi ad ogni `mgradm restart` — tenere gli script in `/tmp` sull'**host**
- `/etc/rhn/` è un volume montato persistente — sopravvive ai restart del container
- Il backup automatico di `rhn.conf` si trova in `/etc/rhn/rhn.conf.YYYY-MM-DD_HH:MM:SS`

---

## Riferimenti

- [Uyuni Documentation — Authentication with SSO](https://www.uyuni-project.org/uyuni-docs/en/uyuni/administration/auth-methods-sso.html)
- [SUSE Manager — SSO Configuration Example](https://documentation.suse.com/suma/5.0/en/suse-manager/administration/auth-methods-sso-example.html)
- [Microsoft — Azure AD SAML Integration](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/add-application-portal-setup-sso)
- [Uyuni GitHub Issue #6793 — SSO metadata returns HTML](https://github.com/uyuni-project/uyuni/issues/6793)


Login URL : https://login.microsoftonline.com/fae8df93-7cf5-40da-b480-f272e15b6242/saml2
Microsoft Entra Identifier : https://sts.windows.net/fae8df93-7cf5-40da-b480-f272e15b6242/
Logout URL : https://login.microsoftonline.com/fae8df93-7cf5-40da-b480-f272e15b6242/saml2


Tenant ID : fae8df93-7cf5-40da-b480-f272e15b6242