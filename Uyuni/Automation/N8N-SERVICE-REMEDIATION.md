# N8N Service Remediation - Integrazione con UYUNI

## Panoramica

Sistema automatizzato per gestire disservizi VM 24/7:
- **Input**: Email/webhook con segnalazione disservizio
- **Processing**: Identificazione VM, analisi contesto, remediation via Salt
- **Output**: Email report con risultato operazione

---

## Architettura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WORKFLOW N8N                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────┐    ┌─────────────┐    ┌──────────────┐    ┌────────────────┐ │
│  │  EMAIL   │───►│  PARSER     │───►│ VM RESOLVER  │───►│ SALT EXECUTOR  │ │
│  │  TRIGGER │    │  (AI/Regex) │    │ (UYUNI API)  │    │ (SSH/API)      │ │
│  └──────────┘    └─────────────┘    └──────────────┘    └───────┬────────┘ │
│        │                                                          │          │
│        │         ┌─────────────────────────────────────────────────┘          │
│        │         │                                                            │
│        │         ▼                                                            │
│        │    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐        │
│        │    │ SERVICE      │───►│ REPORT       │───►│ EMAIL        │        │
│        │    │ RESTART      │    │ GENERATOR    │    │ SENDER       │        │
│        │    └──────────────┘    └──────────────┘    └──────────────┘        │
│        │                                                                      │
└────────┼──────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         UYUNI SERVER (10.172.2.17)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│  │ Salt Master │    │ UYUNI API   │    │ PostgreSQL  │                     │
│  │ (4505/4506) │    │ (XMLRPC)    │    │ (5432)      │                     │
│  └──────┬──────┘    └──────┬──────┘    └─────────────┘                     │
│         │                   │                                               │
│         │    ┌──────────────┴──────────────┐                               │
│         │    │      System Groups          │                               │
│         │    ├─────────────────────────────┤                               │
│         │    │ org-asl0603-prod           │                               │
│         │    │ org-asl0603-test           │                               │
│         │    │ org-cliente-x-webservers   │                               │
│         │    └─────────────────────────────┘                               │
└─────────┼───────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MANAGED VMs (Salt Minions)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────┐   ┌───────────────┐   ┌───────────────┐                 │
│  │ vm-web-01     │   │ vm-db-01      │   │ vm-app-01     │                 │
│  │ nginx/apache  │   │ postgresql    │   │ custom-app    │                 │
│  │ Ubuntu 24.04  │   │ Ubuntu 24.04  │   │ Ubuntu 24.04  │                 │
│  └───────────────┘   └───────────────┘   └───────────────┘                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisiti

### 1. Deployment n8n

n8n può essere deployato come container sullo stesso host UYUNI o su una VM dedicata.

```bash
# Su VM dedicata (consigliato) o sullo stesso host UYUNI
# Crea directory persistenza
sudo mkdir -p /opt/n8n/data
sudo chown 1000:1000 /opt/n8n/data

# Deploy n8n con Podman
podman run -d \
  --name n8n \
  --restart=always \
  -p 5678:5678 \
  -v /opt/n8n/data:/home/node/.n8n:Z \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER=admin \
  -e N8N_BASIC_AUTH_PASSWORD=SecureN8nPass2024 \
  -e GENERIC_TIMEZONE=Europe/Rome \
  -e N8N_HOST=n8n.spm.internal \
  -e N8N_PROTOCOL=https \
  -e WEBHOOK_URL=https://n8n.spm.internal \
  docker.n8n.io/n8nio/n8n:latest
```

### 2. Configurazione UYUNI API User

Crea un utente dedicato per n8n con permessi limitati:

```bash
# Accedi alla WebUI UYUNI
# Admin > Users > Create User

# Username: n8n-automation
# Password: N8nUyuniIntegration2024
# Roles:
#   - System Group Admin (per gestire i sistemi)
#   - Activation Key Admin (opzionale)
```

### 3. Servizio di Test (per esperimento)

Installiamo un servizio semplice su una VM Ubuntu che possiamo killare e far riavviare.

**Opzione A: Nginx (consigliato per test)**
```bash
# Sulla VM Ubuntu 24.04
sudo apt update && sudo apt install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

**Opzione B: Servizio Custom (più controllabile)**
```bash
# Crea un servizio "dummy" per test
sudo tee /opt/test-service.sh << 'EOF'
#!/bin/bash
# Servizio di test per remediation automatica
LOG_FILE="/var/log/test-service.log"

cleanup() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Service stopped" >> "$LOG_FILE"
    exit 0
}

trap cleanup SIGTERM SIGINT

echo "$(date '+%Y-%m-%d %H:%M:%S') - Service started with PID $$" >> "$LOG_FILE"

while true; do
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Heartbeat" >> "$LOG_FILE"
    sleep 30
done
EOF

sudo chmod +x /opt/test-service.sh

# Crea systemd unit
sudo tee /etc/systemd/system/test-service.service << 'EOF'
[Unit]
Description=Test Service for N8N Remediation Demo
After=network.target

[Service]
Type=simple
ExecStart=/opt/test-service.sh
Restart=no
# Restart=no così possiamo testare il remediation manuale
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable test-service
sudo systemctl start test-service
```

---

## Workflow n8n Dettagliato

### Step 1: Email Trigger Node

```json
{
  "nodes": [
    {
      "name": "Email Trigger",
      "type": "n8n-nodes-base.emailReadImap",
      "parameters": {
        "mailbox": "INBOX",
        "options": {
          "customHeaders": true
        }
      },
      "credentials": {
        "imap": {
          "id": "1",
          "name": "Support Email"
        }
      }
    }
  ]
}
```

**Configurazione IMAP** (esempio con Gmail/O365):
- Host: `imap.gmail.com` / `outlook.office365.com`
- Port: 993
- SSL: true
- User: `support-alerts@tuodominio.it`

### Step 2: Parser Node (Estrazione Informazioni)

Questo node analizza l'email per estrarre:
- Nome/IP della VM
- Organizzazione
- Servizio interessato
- Severità

```javascript
// Code Node: parseAlertEmail
const emailBody = $input.first().json.text || $input.first().json.html;
const emailSubject = $input.first().json.subject;
const emailFrom = $input.first().json.from;

// Pattern per identificare VM e servizi
const patterns = {
  // Pattern comuni per alert di monitoraggio
  vmName: /(?:server|host|vm|machine)[:\s]+([a-zA-Z0-9\-_.]+)/i,
  vmIP: /(?:ip|address)[:\s]+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})/i,
  service: /(?:service|servizio|processo)[:\s]+([a-zA-Z0-9\-_]+)/i,
  organization: /(?:org|organizzazione|tenant|cliente)[:\s]+([a-zA-Z0-9\-_]+)/i,

  // Pattern per alert Zabbix/Nagios/Prometheus
  zabbixHost: /Host[:\s]+([^\n\r]+)/i,
  nagiosService: /Service[:\s]+([^\n\r]+)/i,

  // Pattern generici per "down" alerts
  downAlert: /(down|offline|unreachable|failed|crashed|stopped)/i
};

// Estrai informazioni
let vmName = null;
let vmIP = null;
let serviceName = null;
let organization = null;
let alertType = 'unknown';

// Cerca nei pattern
for (const [key, pattern] of Object.entries(patterns)) {
  const match = emailBody.match(pattern);
  if (match) {
    switch(key) {
      case 'vmName':
      case 'zabbixHost':
        vmName = match[1].trim();
        break;
      case 'vmIP':
        vmIP = match[1].trim();
        break;
      case 'service':
      case 'nagiosService':
        serviceName = match[1].trim();
        break;
      case 'organization':
        organization = match[1].trim();
        break;
      case 'downAlert':
        alertType = 'service_down';
        break;
    }
  }
}

// Fallback: cerca nell'oggetto
if (!vmName && emailSubject) {
  const subjectMatch = emailSubject.match(/(?:alert|down|critical)[:\s-]+([a-zA-Z0-9\-_.]+)/i);
  if (subjectMatch) vmName = subjectMatch[1];
}

// Determina severità
let severity = 'medium';
if (/critical|critico|urgente|emergency/i.test(emailBody + emailSubject)) {
  severity = 'critical';
} else if (/warning|attenzione|avviso/i.test(emailBody + emailSubject)) {
  severity = 'warning';
}

return {
  json: {
    parsed: true,
    vmName: vmName,
    vmIP: vmIP,
    serviceName: serviceName || 'unknown',
    organization: organization || 'default',
    severity: severity,
    alertType: alertType,
    originalSubject: emailSubject,
    originalFrom: emailFrom,
    timestamp: new Date().toISOString(),
    rawBody: emailBody.substring(0, 500) // Primi 500 caratteri per debug
  }
};
```

### Step 3: VM Resolver (Query UYUNI API)

```javascript
// HTTP Request Node: Query UYUNI per trovare la VM
// Questo node usa l'API XMLRPC di UYUNI

// Prima dobbiamo fare login per ottenere il session key
const loginResponse = await this.helpers.httpRequest({
  method: 'POST',
  url: 'https://10.172.2.17/rpc/api',
  headers: {
    'Content-Type': 'text/xml'
  },
  body: `<?xml version="1.0"?>
<methodCall>
  <methodName>auth.login</methodName>
  <params>
    <param><value><string>n8n-automation</string></value></param>
    <param><value><string>N8nUyuniIntegration2024</string></value></param>
  </params>
</methodCall>`
});

// Poi cerca il sistema
const vmName = $input.first().json.vmName;
const searchResponse = await this.helpers.httpRequest({
  method: 'POST',
  url: 'https://10.172.2.17/rpc/api',
  headers: {
    'Content-Type': 'text/xml'
  },
  body: `<?xml version="1.0"?>
<methodCall>
  <methodName>system.searchByName</methodName>
  <params>
    <param><value><string>${sessionKey}</string></value></param>
    <param><value><string>${vmName}</string></value></param>
  </params>
</methodCall>`
});

return {
  json: {
    ...$input.first().json,
    uyuniSystemId: extractedSystemId,
    uyuniSystemDetails: systemDetails
  }
};
```

**Alternativa più semplice: Script Shell via SSH**

```javascript
// Execute Command Node (SSH)
// Questo approccio è più semplice e affidabile

const vmName = $input.first().json.vmName;
const vmIP = $input.first().json.vmIP;

// Query Salt per trovare il minion
const command = `
# Cerca il minion per nome o IP
if [ -n "${vmName}" ]; then
  salt-key -L | grep -i "${vmName}" || echo "NOT_FOUND_BY_NAME"
fi

if [ -n "${vmIP}" ]; then
  salt '*' grains.get ip4_interfaces --out=json 2>/dev/null | jq -r 'to_entries[] | select(.value[][].[] == "${vmIP}") | .key'
fi
`;

return { json: { command: command } };
```

### Step 4: Salt Service Restart

```javascript
// Code Node: Genera comando Salt per restart servizio

const systemId = $input.first().json.vmName;  // Salt minion ID
const serviceName = $input.first().json.serviceName;

// Mappa servizi comuni
const serviceMap = {
  'nginx': 'nginx',
  'apache': 'apache2',
  'httpd': 'apache2',
  'web': 'nginx',  // default per "web"
  'database': 'postgresql',
  'postgres': 'postgresql',
  'mysql': 'mysql',
  'ssh': 'ssh',
  'test-service': 'test-service',
  'unknown': null  // Richiede diagnosi
};

const actualService = serviceMap[serviceName.toLowerCase()] || serviceName;

let saltCommand;
let diagnosticCommand;

if (actualService) {
  // Comando per restart specifico
  saltCommand = `salt '${systemId}' service.restart ${actualService}`;
  diagnosticCommand = `salt '${systemId}' service.status ${actualService}`;
} else {
  // Se servizio sconosciuto, fai diagnosi
  saltCommand = null;
  diagnosticCommand = `salt '${systemId}' cmd.run 'systemctl list-units --state=failed --no-pager'`;
}

return {
  json: {
    ...$input.first().json,
    saltCommand: saltCommand,
    diagnosticCommand: diagnosticCommand,
    actualService: actualService
  }
};
```

### Step 5: Execute Salt Command

```javascript
// SSH Node: Esegue comando Salt sul server UYUNI

// Configurazione SSH
// Host: 10.172.2.17 (UYUNI Server)
// User: root (o user con accesso al container)
// Auth: SSH Key (consigliato) o Password

const saltCommand = $input.first().json.saltCommand;
const diagnosticCommand = $input.first().json.diagnosticCommand;

// Se container Podman
const containerExec = `podman exec uyuni-server`;

let commands = [];

// 1. Prima verifica stato attuale
commands.push(`${containerExec} ${diagnosticCommand}`);

// 2. Se abbiamo un comando di restart, eseguilo
if (saltCommand) {
  commands.push(`${containerExec} ${saltCommand}`);
}

// 3. Verifica stato dopo restart
commands.push(`${containerExec} ${diagnosticCommand}`);

return {
  json: {
    commands: commands.join(' && '),
    ...$input.first().json
  }
};
```

### Step 6: Report Generator

```javascript
// Code Node: Genera report HTML per email

const input = $input.first().json;

const statusEmoji = input.restartSuccess ? '✅' : '❌';
const statusText = input.restartSuccess ? 'RISOLTO' : 'RICHIEDE INTERVENTO MANUALE';

const report = `
<!DOCTYPE html>
<html>
<head>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; }
    .header { background: #1a365d; color: white; padding: 15px; border-radius: 5px; }
    .status-ok { background: #48bb78; color: white; padding: 10px; border-radius: 5px; }
    .status-fail { background: #f56565; color: white; padding: 10px; border-radius: 5px; }
    .details { background: #f7fafc; padding: 15px; margin: 10px 0; border-radius: 5px; }
    .code { background: #2d3748; color: #e2e8f0; padding: 10px; border-radius: 5px; font-family: monospace; }
    table { width: 100%; border-collapse: collapse; }
    td, th { padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: left; }
  </style>
</head>
<body>
  <div class="header">
    <h1>${statusEmoji} Service Remediation Report</h1>
    <p>Timestamp: ${input.timestamp}</p>
  </div>

  <div class="${input.restartSuccess ? 'status-ok' : 'status-fail'}">
    <h2>Status: ${statusText}</h2>
  </div>

  <div class="details">
    <h3>Dettagli Incidente</h3>
    <table>
      <tr><td><strong>VM/Host</strong></td><td>${input.vmName || 'N/A'}</td></tr>
      <tr><td><strong>IP</strong></td><td>${input.vmIP || 'N/A'}</td></tr>
      <tr><td><strong>Servizio</strong></td><td>${input.serviceName}</td></tr>
      <tr><td><strong>Organizzazione</strong></td><td>${input.organization}</td></tr>
      <tr><td><strong>Severità</strong></td><td>${input.severity}</td></tr>
      <tr><td><strong>Alert Originale</strong></td><td>${input.originalSubject}</td></tr>
    </table>
  </div>

  <div class="details">
    <h3>Azione Eseguita</h3>
    <div class="code">
      <pre>${input.saltCommand || 'Diagnosi automatica'}</pre>
    </div>
  </div>

  <div class="details">
    <h3>Output Comando</h3>
    <div class="code">
      <pre>${input.commandOutput || 'N/A'}</pre>
    </div>
  </div>

  ${!input.restartSuccess ? `
  <div class="details" style="background: #fff5f5;">
    <h3>⚠️ Azione Richiesta</h3>
    <p>Il riavvio automatico non è riuscito. Verificare manualmente:</p>
    <ol>
      <li>Connettersi alla VM: <code>ssh root@${input.vmIP || input.vmName}</code></li>
      <li>Verificare i log: <code>journalctl -u ${input.serviceName} -n 50</code></li>
      <li>Controllare risorse: <code>df -h && free -m</code></li>
    </ol>
  </div>
  ` : ''}

  <div class="details">
    <p><small>Report generato automaticamente da SPM N8N Automation</small></p>
    <p><small>UYUNI Server: ${input.uyuniServer || '10.172.2.17'}</small></p>
  </div>
</body>
</html>
`;

return {
  json: {
    ...input,
    reportHtml: report,
    reportSubject: `[SPM] ${statusText}: ${input.serviceName} su ${input.vmName}`
  }
};
```

### Step 7: Email Sender

```json
{
  "name": "Send Report Email",
  "type": "n8n-nodes-base.emailSend",
  "parameters": {
    "fromEmail": "spm-automation@tuodominio.it",
    "toEmail": "support-team@tuodominio.it",
    "subject": "={{ $json.reportSubject }}",
    "html": "={{ $json.reportHtml }}",
    "options": {
      "replyTo": "noreply@tuodominio.it"
    }
  }
}
```

---

## Workflow Completo (JSON Export)

```json
{
  "name": "SPM Service Remediation",
  "nodes": [
    {
      "parameters": {
        "mailbox": "INBOX",
        "options": {}
      },
      "id": "email-trigger",
      "name": "Email Alert Trigger",
      "type": "n8n-nodes-base.emailReadImap",
      "typeVersion": 2,
      "position": [240, 300],
      "credentials": {
        "imap": {
          "id": "1",
          "name": "Alert Mailbox"
        }
      }
    },
    {
      "parameters": {
        "jsCode": "// Parser code from Step 2"
      },
      "id": "parse-email",
      "name": "Parse Alert Email",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [460, 300]
    },
    {
      "parameters": {
        "conditions": {
          "boolean": [
            {
              "value1": "={{ $json.vmName !== null }}",
              "value2": true
            }
          ]
        }
      },
      "id": "check-parsed",
      "name": "VM Identified?",
      "type": "n8n-nodes-base.if",
      "typeVersion": 1,
      "position": [680, 300]
    },
    {
      "parameters": {
        "authentication": "privateKey",
        "host": "10.172.2.17",
        "port": 22,
        "username": "root",
        "command": "={{ $json.commands }}"
      },
      "id": "salt-execute",
      "name": "Execute Salt Command",
      "type": "n8n-nodes-base.ssh",
      "typeVersion": 1,
      "position": [900, 200],
      "credentials": {
        "sshPrivateKey": {
          "id": "2",
          "name": "UYUNI SSH Key"
        }
      }
    },
    {
      "parameters": {
        "jsCode": "// Report generator from Step 6"
      },
      "id": "generate-report",
      "name": "Generate Report",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [1120, 200]
    },
    {
      "parameters": {
        "fromEmail": "spm@tuodominio.it",
        "toEmail": "support@tuodominio.it",
        "subject": "={{ $json.reportSubject }}",
        "html": "={{ $json.reportHtml }}"
      },
      "id": "send-email",
      "name": "Send Report",
      "type": "n8n-nodes-base.emailSend",
      "typeVersion": 2,
      "position": [1340, 200],
      "credentials": {
        "smtp": {
          "id": "3",
          "name": "SMTP Credentials"
        }
      }
    }
  ],
  "connections": {
    "Email Alert Trigger": {
      "main": [[{ "node": "Parse Alert Email", "type": "main", "index": 0 }]]
    },
    "Parse Alert Email": {
      "main": [[{ "node": "VM Identified?", "type": "main", "index": 0 }]]
    },
    "VM Identified?": {
      "main": [
        [{ "node": "Execute Salt Command", "type": "main", "index": 0 }],
        [{ "node": "Manual Review Required", "type": "main", "index": 0 }]
      ]
    },
    "Execute Salt Command": {
      "main": [[{ "node": "Generate Report", "type": "main", "index": 0 }]]
    },
    "Generate Report": {
      "main": [[{ "node": "Send Report", "type": "main", "index": 0 }]]
    }
  }
}
```

---

## Script di Test End-to-End

### 1. Setup Ambiente di Test

```bash
#!/bin/bash
# File: /opt/spm/test-remediation-setup.sh

echo "=== SPM Remediation Test Setup ==="

# 1. Verifica connettività Salt
echo "[1/4] Verifica Salt Master..."
podman exec uyuni-server salt-key -L

# 2. Lista minion attivi
echo "[2/4] Minion attivi..."
podman exec uyuni-server salt '*' test.ping

# 3. Verifica servizio test su un minion
MINION_ID="vm-test-ubuntu"  # Cambia con il tuo minion
echo "[3/4] Stato servizio test su $MINION_ID..."
podman exec uyuni-server salt "$MINION_ID" service.status test-service

# 4. Test kill e restart
echo "[4/4] Test manuale kill/restart..."
podman exec uyuni-server salt "$MINION_ID" cmd.run 'systemctl stop test-service'
sleep 2
podman exec uyuni-server salt "$MINION_ID" service.status test-service
podman exec uyuni-server salt "$MINION_ID" service.restart test-service
podman exec uyuni-server salt "$MINION_ID" service.status test-service

echo "=== Setup completato ==="
```

### 2. Simula Alert Email

```bash
#!/bin/bash
# File: /opt/spm/simulate-alert.sh

# Invia email di test al sistema
ALERT_EMAIL="support-alerts@tuodominio.it"
FROM_EMAIL="monitoring@tuodominio.it"
SMTP_SERVER="smtp.tuodominio.it"

cat << EOF | sendmail -t
From: $FROM_EMAIL
To: $ALERT_EMAIL
Subject: [CRITICAL] Service Down: test-service on vm-test-ubuntu

ALERT: Service Down Detected

Host: vm-test-ubuntu
IP: 10.172.2.50
Organization: ASL0603
Service: test-service
Status: STOPPED
Time: $(date '+%Y-%m-%d %H:%M:%S')

The service test-service on host vm-test-ubuntu has stopped responding.
Automatic remediation requested.

--
Monitoring System
EOF

echo "Alert email inviata!"
```

### 3. Script di Verifica

```bash
#!/bin/bash
# File: /opt/spm/verify-remediation.sh

MINION_ID="${1:-vm-test-ubuntu}"
SERVICE="${2:-test-service}"

echo "=== Verifica Remediation ==="
echo "Minion: $MINION_ID"
echo "Service: $SERVICE"
echo ""

# Controlla stato attuale
echo "[Stato Attuale]"
podman exec uyuni-server salt "$MINION_ID" service.status "$SERVICE"

# Controlla log recenti
echo ""
echo "[Log Recenti]"
podman exec uyuni-server salt "$MINION_ID" cmd.run "journalctl -u $SERVICE -n 10 --no-pager"

# Uptime servizio
echo ""
echo "[Uptime]"
podman exec uyuni-server salt "$MINION_ID" cmd.run "systemctl show $SERVICE --property=ActiveEnterTimestamp"
```

---

## Integrazione Avanzata con UYUNI API

### Script Python per API XMLRPC

```python
#!/usr/bin/env python3
"""
UYUNI API Client per N8N Integration
File: /opt/spm/uyuni_api_client.py
"""

import xmlrpc.client
import ssl
import json
import sys

class UyuniClient:
    def __init__(self, url, username, password):
        # Disabilita verifica SSL per test (abilita in prod!)
        context = ssl._create_unverified_context()
        self.client = xmlrpc.client.ServerProxy(
            f"{url}/rpc/api",
            context=context
        )
        self.session = self.client.auth.login(username, password)

    def search_system_by_name(self, name):
        """Cerca sistema per nome"""
        results = self.client.system.searchByName(self.session, name)
        return results

    def get_system_details(self, system_id):
        """Ottieni dettagli sistema"""
        return self.client.system.getDetails(self.session, system_id)

    def schedule_script(self, system_id, script, timeout=300):
        """Schedula esecuzione script"""
        import datetime
        run_time = datetime.datetime.now()
        action_id = self.client.system.scheduleScriptRun(
            self.session,
            system_id,
            "root",  # username
            "root",  # groupname
            timeout,
            script,
            run_time
        )
        return action_id

    def get_action_result(self, action_id):
        """Ottieni risultato azione"""
        return self.client.schedule.listCompletedActions(self.session)

    def restart_service_via_salt(self, minion_id, service_name):
        """
        Restart servizio via Salt (metodo diretto)
        Nota: Richiede accesso SSH al container UYUNI
        """
        import subprocess
        cmd = f"podman exec uyuni-server salt '{minion_id}' service.restart {service_name}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr
        }

    def logout(self):
        """Chiudi sessione"""
        self.client.auth.logout(self.session)

def main():
    """CLI interface"""
    if len(sys.argv) < 4:
        print("Usage: python uyuni_api_client.py <action> <minion_id> <service>")
        print("Actions: search, restart, status")
        sys.exit(1)

    action = sys.argv[1]
    minion_id = sys.argv[2]
    service = sys.argv[3] if len(sys.argv) > 3 else None

    client = UyuniClient(
        url="https://10.172.2.17",
        username="n8n-automation",
        password="N8nUyuniIntegration2024"
    )

    try:
        if action == "search":
            results = client.search_system_by_name(minion_id)
            print(json.dumps(results, indent=2))

        elif action == "restart":
            result = client.restart_service_via_salt(minion_id, service)
            print(json.dumps(result, indent=2))

        elif action == "status":
            import subprocess
            cmd = f"podman exec uyuni-server salt '{minion_id}' service.status {service}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            print(result.stdout)

    finally:
        client.logout()

if __name__ == "__main__":
    main()
```

---

## Configurazione Salt States per Remediation

Crea stati Salt riutilizzabili per remediation comuni:

```yaml
# File: /srv/salt/remediation/service_restart.sls
# Da deployare nel container UYUNI: /srv/salt/

{% set service_name = salt['pillar.get']('service_name', 'unknown') %}

check_service_before:
  cmd.run:
    - name: systemctl status {{ service_name }} || true
    - stateful: False

restart_{{ service_name }}:
  service.running:
    - name: {{ service_name }}
    - enable: True
    - watch:
      - cmd: check_service_before

verify_service_after:
  cmd.run:
    - name: systemctl is-active {{ service_name }}
    - require:
      - service: restart_{{ service_name }}
```

```yaml
# File: /srv/salt/remediation/full_diagnostic.sls

system_status:
  cmd.run:
    - name: |
        echo "=== DISK USAGE ==="
        df -h
        echo ""
        echo "=== MEMORY ==="
        free -m
        echo ""
        echo "=== FAILED SERVICES ==="
        systemctl list-units --state=failed --no-pager
        echo ""
        echo "=== TOP PROCESSES ==="
        ps aux --sort=-%mem | head -10
```

**Applicazione via Salt:**
```bash
# Restart specifico servizio
podman exec uyuni-server salt 'vm-test-*' state.apply remediation.service_restart \
  pillar='{"service_name": "nginx"}'

# Diagnosi completa
podman exec uyuni-server salt 'vm-test-*' state.apply remediation.full_diagnostic
```

---

## Monitoraggio e Logging

### Webhook per Alert in Tempo Reale

```javascript
// N8N Webhook Node per ricevere alert da Zabbix/Prometheus/etc.

// URL: https://n8n.spm.internal/webhook/service-alert
// Method: POST
// Authentication: Header Auth (X-API-Key)

// Esempio payload Prometheus AlertManager:
{
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "ServiceDown",
        "instance": "vm-web-01:9100",
        "job": "node",
        "service": "nginx",
        "severity": "critical"
      },
      "annotations": {
        "description": "Service nginx is down on vm-web-01",
        "summary": "Service Down"
      }
    }
  ]
}
```

### Dashboard Metriche (opzionale)

```bash
# Aggiungi metriche a Prometheus/Grafana
# File: /opt/spm/n8n_metrics.py

from prometheus_client import Counter, Histogram, start_http_server

REMEDIATION_TOTAL = Counter(
    'spm_remediation_total',
    'Total remediation attempts',
    ['service', 'vm', 'status']
)

REMEDIATION_DURATION = Histogram(
    'spm_remediation_duration_seconds',
    'Time spent on remediation',
    ['service']
)
```

---

## Checklist Implementazione

### Fase 1: Setup Base
- [ ] Deploy n8n container
- [ ] Configura credenziali SMTP (invio email)
- [ ] Configura credenziali IMAP (ricezione email)
- [ ] Crea utente UYUNI per automazione
- [ ] Genera SSH key per n8n → UYUNI

### Fase 2: Test Environment
- [ ] Installa servizio test su VM Ubuntu
- [ ] Verifica connettività Salt minion
- [ ] Test manuale kill/restart via Salt
- [ ] Verifica invio email report

### Fase 3: Workflow N8N
- [ ] Importa workflow JSON
- [ ] Configura tutti i credential stores
- [ ] Test con email simulata
- [ ] Verifica parsing corretto
- [ ] Verifica esecuzione Salt
- [ ] Verifica report email

### Fase 4: Produzione
- [ ] Configura filtri email (evita loop)
- [ ] Aggiungi rate limiting
- [ ] Configura alerting su fallimenti
- [ ] Documenta runbook manuale
- [ ] Training team

---

## Troubleshooting

| Problema | Causa | Soluzione |
|----------|-------|-----------|
| Salt non raggiunge minion | Firewall/rete | Verifica porte 4505/4506 |
| Email non parsata | Pattern non match | Aggiungi regex specifico |
| SSH timeout | Container non raggiungibile | Verifica network n8n→UYUNI |
| Restart fallisce | Permessi insufficienti | Verifica sudoers sul minion |
| Report non inviato | SMTP blocked | Verifica credenziali/firewall |

---

## Riferimenti

- [N8N Documentation](https://docs.n8n.io/)
- [Salt States Reference](https://docs.saltproject.io/en/latest/ref/states/all/index.html)
- [UYUNI API Documentation](https://www.uyuni-project.org/uyuni-docs/en/uyuni/api/index.html)
- Infrastruttura SPM: `/Uyuni/README.md`
