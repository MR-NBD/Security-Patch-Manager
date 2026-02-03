# Integrazione con UYUNI

## Panoramica

Sistema automatizzato per gestire disservizi tramite n8n e Salt/UYUNI.

- **Input**: Messaggio in chat n8n con segnalazione disservizio
- **Processing**: AI (Groq) interpreta il messaggio, Salt esegue diagnosi e remediation
- **Output**: Report formattato in chat con esito operazione

---

## Architettura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              VM n8n (10.172.x.x)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────┐    ┌─────────────┐    ┌──────────────┐    ┌────────────────┐ │
│  │  Chat    │───►│  Groq AI    │───►│    Code      │───►│ SSH Diagnosi   │ │
│  │  Trigger │    │  (Interpreta)│    │  (Parser)    │    │ (Salt)         │ │
│  └──────────┘    └─────────────┘    └──────────────┘    └───────┬────────┘ │
│                                                                   │          │
│                  ┌────────────────────────────────────────────────┘          │
│                  │                                                           │
│                  ▼                                                           │
│  ┌──────────┐    ┌─────────────┐    ┌──────────────┐                        │
│  │  Chat    │◄───│  Groq AI    │◄───│ SSH Restart  │                        │
│  │  Output  │    │  (Report)   │    │ (Salt)       │                        │
│  └──────────┘    └─────────────┘    └──────────────┘                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │ SSH (porta 22)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         UYUNI SERVER (10.172.2.17)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Container Podman: uyuni-server                    │   │
│  │  ┌─────────────┐                                                     │   │
│  │  │ Salt Master │ ◄──── salt "minion-id" service.restart <service>   │   │
│  │  │ (4505/4506) │                                                     │   │
│  │  └──────┬──────┘                                                     │   │
│  └─────────┼───────────────────────────────────────────────────────────┘   │
│            │                                                                 │
└────────────┼─────────────────────────────────────────────────────────────────┘
             │
             │ Salt (porta 4505/4506)
             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MANAGED VMs (Salt Minions)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────┐   ┌───────────────┐                                     │
│  │ 10.172.2.15   │   │ 10.172.2.18   │                                     │
│  │ Salt Minion   │   │ Salt Minion   │                                     │
│  │ Ubuntu 24.04  │   │ Ubuntu 24.04  │                                     │
│  └───────────────┘   └───────────────┘                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```
## Prerequisiti

- VM Linux (Ubuntu 24.04) nella stessa VNET di UYUNI
- Accesso SSH al server UYUNI (10.172.2.17)
- Account Groq (gratuito) per AI
- Salt Minions configurati e connessi al Salt Master

## INSTALLAZIONE N8n
### Step 3: Installa Docker

```bash
# Aggiorna il sistema
sudo apt-get update && sudo apt-get upgrade -y

# Installa Docker
curl -fsSL https://get.docker.com | sudo sh

# Aggiungi utente al gruppo docker
sudo usermod -aG docker azureuser

# Esci e rientra per applicare i permessi
exit
```
### Step 4: Avvia n8n
```bash
# Crea directory per n8n
mkdir -p ~/.n8n

# Avvia n8n con Docker
docker run -d \
  --name n8n \
  --restart always \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER=admin \
  -e N8N_BASIC_AUTH_PASSWORD=N8nSecure2024 \
  -e N8N_SECURE_COOKIE=false \
  -e GENERIC_TIMEZONE=Europe/Rome \
  n8nio/n8n:latest
```
### Step 5: Verifica installazione
```bash
# Verifica che il container sia running
docker ps

# Trova l'IP della VM
hostname -I
```
### Step 6: Accedi a n8n
Dalla macchina Windows nella VNET, apri il browser:

```
http://<IP_VM_N8N>:5678
```

Credenziali:
- **User**: `admin`
- **Password**: `N8nSecure2024`

---
## Configurazione Credenziali

### Credenziali Groq (AI)

1. Vai su https://console.groq.com/
2. Crea account (gratuito)
3. Vai su **API Keys** → **Create API Key**
4. Copia la chiave

In n8n:
1. **Credentials** → **Add Credential**
2. Cerca **"Groq"**
3. Inserisci l'API Key
4. Salva

### Credenziali SSH (UYUNI)
In n8n:
1. **Credentials** → **Add Credential**
2. Cerca **"SSH"**
3. Configura:
   - **Host**: `10.172.2.17`
   - **Port**: `22`
   - **Username**: `azureuser`
   - **Password**: (la tua password)
1. Salva
## Creazione Workflow

### Struttura del Workflow

![[img2187te87r13.png]]
### Step 1: Crea nuovo workflow

1. **Workflows** → **Add Workflow**
2. Rinomina: `Service Remediation AI`
### Step 2: Aggiungi Chat Trigger
1. Clicca **"+"**
2. Cerca **"Chat Trigger"**
3. Configura:
   - **Make Available in n8n Chat**: selezionato
### Step 3: Aggiungi nodo Interpreta Messaggio (Groq)
1. Clicca **"+"** a destra del Chat Trigger
2. Cerca **"Basic LLM Chain"**
3. Aggiungi modello **"Groq Chat Model"**:
   - Credential: le tue credenziali Groq
   - Model: `llama-3.3-70b-versatile`
4. Nel campo **Prompt**:

```
Sei un assistente IT che analizza ticket di disservizio.

Analizza questo messaggio: {{ $json.chatInput }}

Estrai:
- vmName: nome della VM (se presente)
- vmIP: indirizzo IP della VM (se presente)
- service: nome del servizio in errore (se menzionato, altrimenti null)
- organization: nome dell'organizzazione (se menzionata, altrimenti null)
- severity: critical/high/medium/low basato sul tono

Rispondi SOLO con JSON valido, esempio:
{"vmName": "test-VM-Test", "vmIP": "10.172.2.18", "service": "nginx", "organization": "ASL0603", "severity": "high"}

Se un'informazione manca, usa null. Rispondi SOLO con il JSON, nient'altro.
```

5. Rinomina il nodo: `Interpreta Messaggio`
### Step 4: Aggiungi nodo Code
1. Clicca **"+"** a destra di "Interpreta Messaggio"
2. Cerca **"Code"**
3. Language: **JavaScript**
4. Codice:

```javascript
// Parsa la risposta del nodo precedente (Interpreta Messaggio)
const response = $input.first().json.text;

let parsed;
try {
  const jsonMatch = response.match(/\{[\s\S]*\}/);
  if (jsonMatch) {
    parsed = JSON.parse(jsonMatch[0]);
  } else {
    throw new Error("No JSON found");
  }
} catch (e) {
  parsed = {
    vmName: null,
    vmIP: null,
    service: null,
    organization: null,
    severity: "medium"
  };
}

return {
  json: {
    vmName: parsed.vmName,
    vmIP: parsed.vmIP,
    service: parsed.service,
    organization: parsed.organization,
    severity: parsed.severity,
    timestamp: new Date().toISOString()
  }
};
```

5. Rinomina il nodo: `Code`
### Step 5: Aggiungi nodo Diagnosi Servizi (SSH)
1. Clicca **"+"** a destra di "Code"
2. Cerca **"SSH"**
3. Configura:
   - **Credential**: le tue credenziali SSH UYUNI
   - **Command**:

```
sudo podman exec uyuni-server salt "{{ $json.vmIP }}" cmd.run "systemctl list-units --state=failed --no-pager"
```

4. Rinomina il nodo: `Diagnosi Servizi`
### Step 6: Aggiungi nodo Restart Servizio (SSH)
1. Clicca **"+"** a destra di "Diagnosi Servizi"
2. Cerca **"SSH"**
3. Configura:
   - **Credential**: le tue credenziali SSH UYUNI
   - **Command**:

```
sudo podman exec uyuni-server salt "{{ $('Code').first().json.vmIP }}" service.restart {{ $('Code').first().json.service }}
```

4. Rinomina il nodo: `Restart Servizio`
### Step 7: Aggiungi nodo Format Output (Groq)
1. Clicca **"+"** a destra di "Restart Servizio"
2. Cerca **"Basic LLM Chain"**
3. Aggiungi modello **"Groq Chat Model"**:
   - Credential: le tue credenziali Groq
   - Model: `llama-3.3-70b-versatile`
4. Nel campo **Prompt**:

```
Genera un report di remediation.

Output del comando:
{{ $input.first().json.stdout }}

Crea un report con:
✅ Stato: operazione completata con successo
📍 VM interessata: (estrai da VM_IP nell'output)
🔧 Servizio riavviato: (estrai da SERVICE nell'output)
🕐 Timestamp: {{ new Date().toLocaleString('it-IT', {timeZone: 'Europe/Rome'}) }}
📝 Riepilogo: Il servizio è stato riavviato correttamente

Formatta il report in modo chiaro e leggibile.
```

5. Rinomina il nodo: `Format Output`
### Step 8: Pubblica il workflow
1. Clicca **"Publish"** in alto a destra
2. Il workflow è ora attivo
## Test del Workflow

### Test 1: Verifica connettività Salt
Prima verifica che Salt funzioni:

```bash
# Sul server UYUNI (10.172.2.17)
sudo podman exec uyuni-server salt-key -L
sudo podman exec uyuni-server salt '*' test.ping
```
### Test 2: Simula disservizio
1. Connettiti alla VM target (es. 10.172.2.18) via Bastion

2. Stoppa nginx:
```bash
sudo systemctl stop nginx
```

3. Verifica che sia fermo:
```bash
sudo systemctl status nginx
```

### Test 3: Invia messaggio alla chat n8n
1. In n8n, apri la chat (icona fumetto)
2. Scrivi:
```
Disservizio sulla VM 10.172.2.18, il servizio nginx non risponde
```

3. Attendi la risposta
### Test 4: Verifica remediation

Sulla VM target:
```bash
sudo systemctl status nginx
```

Nginx dovrebbe essere di nuovo `active (running)`.
## Troubleshooting

| Problema | Causa | Soluzione |
|----------|-------|-----------|
| n8n non raggiunge UYUNI | VM in subnet diversa | Verifica VNET e subnet |
| Salt non trova minion | Minion ID errato | Usa `salt-key -L` per vedere i nomi esatti |
| Groq timeout | Rate limiting | Attendi qualche secondo e riprova |
| Chat non risponde | Workflow non pubblicato | Clicca "Publish" |
| Errore "Referenced node doesn't exist" | Nome nodo errato | Verifica nomi esatti dei nodi |
## Video DImostrazione

![[2026-02-02 15-25-49.mp4]]
## Sicurezza

- n8n è accessibile solo dalla VNET interna (no IP pubblico)
- Autenticazione Basic Auth abilitata
- Credenziali SSH salvate in modo sicuro in n8n
- Comunicazione Salt cifrata
## Riferimenti

- [n8n Documentation](https://docs.n8n.io/)
- [Groq Console](https://console.groq.com/)
- [Salt Documentation](https://docs.saltproject.io/)
- Infrastruttura UYUNI: `/Uyuni/README.md`