# Configurazione Virtual Host Manager (VHM) per Azure

Guida per configurare il **Virtual Host Manager** di UYUNI per il discovery automatico delle VM nella subscription Azure. Il VHM interroga le API di Azure Resource Manager per elencare tutte le VM come sistemi "foreign" (visibili ma non gestiti) all'interno di UYUNI.

**Riferimento ufficiale**: https://www.uyuni-project.org/uyuni-docs/en/uyuni/client-configuration/vhm-azure.html

---

## Come funziona

```
UYUNI Server (10.172.2.17)
        │
        │  HTTPS → management.azure.com (API Azure)
        │
        ▼
Azure Resource Manager
        │
        ├── VM #1 (qualsiasi subnet/rete)
        ├── VM #2
        ├── VM #3
        └── ...
```

**Importante**: Il VHM NON comunica direttamente con le VM. Interroga le API Azure tramite Service Principal, quindi:
- Non serve che le VM abbiano DNS verso il server UYUNI
- Non serve che le VM abbiano route di rete verso il server
- Non serve che le VM siano accese
- Trova **tutte le VM** nella subscription, indipendentemente dalla configurazione di rete

---

## Prerequisiti

| Requisito | Dettaglio |
|-----------|-----------|
| **UYUNI Server** | Funzionante con accesso internet verso `management.azure.com` |
| **Pacchetto** | `virtual-host-gatherer-libcloud` installato sul server |
| **Account Azure** | Con permessi per creare App Registration e assegnare ruoli |

### Verifica pacchetto sul server UYUNI

```bash
mgrctl exec -- rpm -qa | grep virtual-host-gatherer-libcloud
```

Output atteso:
```
virtual-host-gatherer-libcloud-1.0.29-241000.1.2.uyuni5.noarch
```

Se non installato:
```bash
mgrctl exec -- zypper install virtual-host-gatherer-libcloud
```

---

## Fase 1: Creazione Service Principal su Azure Portal

### 1.1 Registra l'applicazione

1. Nel portale Azure, cerca **"Microsoft Entra ID"** nella barra di ricerca
2. Vai su **App registrations** → **New registration**
3. Compila:

| Campo | Valore |
|-------|--------|
| **Name** | `uyuni-vhm-reader` |
| **Supported account types** | Accounts in this organizational directory only |
| **Redirect URI** | *(lascia vuoto)* |

4. Clicca **Register**

### 1.2 Annota Application ID e Tenant ID

Dalla pagina **Overview** dell'app appena creata, copia:

| Dato | Campo nel portale | Esempio |
|------|-------------------|---------|
| **Application (Client) ID** | Application (client) ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| **Directory (Tenant) ID** | Directory (tenant) ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |

### 1.3 Crea il Client Secret

1. Nella pagina dell'app, vai su **Certificates & secrets**
2. **Client secrets** → **New client secret**
3. Compila:

| Campo | Valore |
|-------|--------|
| **Description** | `uyuni-vhm-key` |
| **Expires** | Scegli la durata (es. 24 months) |

4. Clicca **Add**
5. **COPIA SUBITO il campo "Value"** — il secret non sarà più visibile dopo aver lasciato la pagina!

### 1.4 Trova il Subscription ID

1. Nella barra di ricerca del portale Azure, cerca **"Subscriptions"**
2. Clicca sulla subscription desiderata
3. Nella pagina **Overview**, copia il **Subscription ID**

### 1.5 Assegna il ruolo Reader

1. Vai su **Subscriptions** → seleziona la tua subscription
2. **Access control (IAM)** → **Add** → **Add role assignment**
3. **Role**: cerca e seleziona **Reader**
4. **Members** → **Select members** → cerca `uyuni-vhm-reader` → selezionalo
5. Clicca **Review + assign**

> **Nota**: Il ruolo Reader è sufficiente per il discovery. Non serve alcun permesso di scrittura.

---

## Fase 2: Riepilogo dati raccolti

Prima di procedere, verifica di avere tutti i dati necessari:

| Dato | Dove trovarlo |
|------|---------------|
| **Subscription ID** | Subscriptions → Overview |
| **Application (Client) ID** | Entra ID → App registrations → Overview |
| **Directory (Tenant) ID** | Entra ID → App registrations → Overview |
| **Client Secret (Value)** | Entra ID → App registrations → Certificates & secrets |
| **Zona Azure** | La zona del datacenter (es. `italynorth`) |

---

## Fase 3: Configurazione VHM in UYUNI Web UI

1. Accedi alla Web UI di UYUNI
2. Vai su **Systems** → **Virtual Host Managers** → **Create** → **Azure**
3. Compila i campi:

| Campo UYUNI | Valore da inserire |
|-------------|-------------------|
| **Label** | `azure-spoke10-discovery` (o un nome a scelta) |
| **Subscription ID** | Il Subscription ID copiato |
| **Application ID** | Il Client ID dell'app registrata |
| **Tenant ID** | Il Directory (Tenant) ID |
| **Secret Key** | Il Client Secret (Value) |
| **Zone** | `italynorth` |

4. Clicca **Create**

---

## Fase 4: Primo gathering delle VM

1. Vai su **Systems** → **Virtual Host Managers**
2. Seleziona `azure-spoke10-discovery`
3. Clicca **Refresh Data**
4. Attendi qualche minuto

### Verifica

Dopo il refresh, vai su **Systems** → **Systems** e controlla che le VM Azure siano visibili come sistemi "foreign" / "unregistered".

Le informazioni disponibili per ogni VM includono:
- Nome della VM
- Indirizzo IP
- Stato (Running/Stopped)
- Sistema operativo
- Dimensione (es. Standard_B2s)

---

## Schedulazione automatica

Il gathering può essere schedulato per eseguirsi automaticamente:

1. **Systems** → **Virtual Host Managers** → `azure-spoke10-discovery`
2. Nella sezione **Schedule**, configura la frequenza desiderata (es. ogni ora)

---

## Troubleshooting

### Il gathering non trova VM

1. Verifica che il Service Principal abbia il ruolo **Reader** sulla subscription corretta
2. Verifica che la **zona** sia corretta (es. `italynorth`)
3. Controlla i log:
```bash
mgrctl exec -- cat /var/log/rhn/rhn_taskomatic_daemon.log | grep -i "virtual-host"
```

### Errore di autenticazione

1. Verifica che il Client Secret non sia scaduto
2. Rigenera il secret in **Entra ID → App registrations → Certificates & secrets**
3. Aggiorna il secret in **Systems → Virtual Host Managers → Edit**

### Il server non raggiunge le API Azure

```bash
mgrctl exec -- curl -s -o /dev/null -w "%{http_code}" https://management.azure.com
```

Output atteso: `401` (raggiungibile ma non autenticato, che è corretto).

Se `000` o timeout, verificare che il server abbia connettività internet verso `management.azure.com`.

---

## Sicurezza

- Il Client Secret è memorizzato nel database UYUNI
- Usare sempre il **ruolo Reader** (minimo privilegio) — mai Contributor o Owner
- Impostare una scadenza sul Client Secret e calendarizzare il rinnovo
- Se il secret viene esposto, rigenerarlo immediatamente da **Entra ID → App registrations → Certificates & secrets**
