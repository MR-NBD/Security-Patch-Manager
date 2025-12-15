# Guida Upload Incrementale Pacchetti

**Versione:** 1.0  
**Data:** Dicembre 2024  
**Stato:** Testato e Funzionante

---

## Panoramica

Questo sistema permette alle VM Ubuntu/Debian di inviare l'elenco pacchetti al backend errata in modo **incrementale**: se nulla è cambiato, non viene inviato nulla (0 byte di traffico).

### Vantaggi

| Metodo | Prima Esecuzione | Esecuzioni Successive |
|--------|------------------|----------------------|
| Tradizionale (sempre tutti) | ~50KB | ~50KB |
| **Incrementale (questo)** | ~50KB | **0 byte** (se nulla è cambiato) |

### Come Funziona

1. Lo script calcola l'hash SHA256 della lista pacchetti
2. Confronta con l'hash dell'ultima esecuzione (salvato localmente)
3. Se uguale → non invia nulla
4. Se diverso → invia i pacchetti al backend
5. Il backend correla gli errata e crea uno snapshot automatico

---

## 1. Installazione Manuale su Singola VM

### 1.1 Creare lo Script

```bash
cat > /usr/local/bin/katello-smart-upload.sh << 'ENDOFFILE'
#!/bin/bash
# Smart Package Upload - Upload incrementale pacchetti
# Versione: 1.0

BACKEND_URL="${BACKEND_URL:-http://10.172.5.4:5000}"
STATE_FILE="/var/lib/katello-smart-upload/state"
HOSTNAME=$(hostname | tr '[:upper:]' '[:lower:]')

# Crea directory stato
mkdir -p /var/lib/katello-smart-upload

# Genera lista pacchetti JSON
PACKAGES_JSON=$(dpkg-query -W -f='{"name":"${Package}","version":"${Version}","arch":"${Architecture}"},\n' | \
    sed '$ s/,$//' | sed '1s/^/[/' | sed '$s/$/]/')

# Calcola hash
CURRENT_HASH=$(echo "$PACKAGES_JSON" | sha256sum | cut -d' ' -f1)

# Leggi hash precedente
PREVIOUS_HASH=""
if [[ -f "$STATE_FILE" ]]; then
    PREVIOUS_HASH=$(head -1 "$STATE_FILE")
fi

# Se hash uguale, niente da fare
if [[ "$CURRENT_HASH" == "$PREVIOUS_HASH" ]]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - No changes (hash: ${CURRENT_HASH:0:16}...)"
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - Changes detected, uploading to host: $HOSTNAME"

# Prepara payload
PAYLOAD="{\"hash\": \"$CURRENT_HASH\", \"mode\": \"full\", \"packages\": $PACKAGES_JSON}"

# Invia al backend
RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/hosts/$HOSTNAME/packages" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    --connect-timeout 10 \
    --max-time 60)

# Verifica risposta
if echo "$RESPONSE" | grep -q '"status"'; then
    STATUS=$(echo "$RESPONSE" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    
    if [[ "$STATUS" == "updated" ]] || [[ "$STATUS" == "unchanged" ]]; then
        # Salva hash per prossima esecuzione
        echo "$CURRENT_HASH" > "$STATE_FILE"
        
        # Log risultato
        ERRATA=$(echo "$RESPONSE" | grep -o '"errata_correlated":[0-9]*' | cut -d: -f2)
        TOTAL=$(echo "$RESPONSE" | grep -o '"total_errata":[0-9]*' | cut -d: -f2)
        
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Success: $STATUS, errata applicabili: $TOTAL"
        logger -t katello-smart-upload "Upload successful: status=$STATUS, errata=$TOTAL"
        exit 0
    fi
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - Error: $RESPONSE"
logger -t katello-smart-upload "Upload failed: $RESPONSE"
exit 1
ENDOFFILE

chmod +x /usr/local/bin/katello-smart-upload.sh
```

### 1.2 Test Manuale

```bash
sudo /usr/local/bin/katello-smart-upload.sh
```

Output atteso (prima esecuzione):
```
2024-12-11 15:30:00 - Changes detected, uploading to host: test-vm-production
2024-12-11 15:30:02 - Success: updated, errata applicabili: 512
```

Output atteso (esecuzioni successive senza modifiche):
```
2024-12-11 16:00:00 - No changes (hash: a1b2c3d4e5f6...)
```

### 1.3 Schedulare con Cron (Opzione Locale)

```bash
# Esegui ogni 6 ore
echo "0 */6 * * * root /usr/local/bin/katello-smart-upload.sh >> /var/log/katello-smart-upload.log 2>&1" | \
    sudo tee /etc/cron.d/katello-smart-upload

# Oppure ogni giorno alle 6:00
echo "0 6 * * * root /usr/local/bin/katello-smart-upload.sh >> /var/log/katello-smart-upload.log 2>&1" | \
    sudo tee /etc/cron.d/katello-smart-upload
```

---

## 2. Deployment via Foreman Remote Execution (Raccomandato)

Usare Remote Execution è la scelta migliore per:
- Gestire molti host da un punto centrale
- Avere log centralizzati in Foreman
- Schedulare esecuzioni senza accedere a ogni VM
- Monitorare successi/fallimenti

### 2.1 Prerequisiti

- Host registrati in Foreman come Content Host
- Remote Execution configurato (katello-agent o SSH)
- Host raggiungibili da Foreman

### 2.2 Creare Job Template

1. In Foreman, vai su **Hosts** → **Templates** → **Job templates**
2. Clicca **Create Template**
3. Configura:

| Campo | Valore |
|-------|--------|
| Name | `Smart Package Upload - Errata` |
| Job category | `Packages` |
| Provider Type | `Script` |
| Description | `Upload incrementale pacchetti al backend errata con snapshot automatico` |

4. Nel tab **Template**, incolla:

```bash
#!/bin/bash
# Smart Package Upload per Errata Backend
# Job Template per Foreman Remote Execution

BACKEND_URL="http://10.172.5.4:5000"
STATE_FILE="/var/lib/katello-smart-upload/state"
HOSTNAME=$(hostname | tr '[:upper:]' '[:lower:]')

# Crea directory stato
mkdir -p /var/lib/katello-smart-upload

# Genera lista pacchetti JSON
PACKAGES_JSON=$(dpkg-query -W -f='{"name":"${Package}","version":"${Version}","arch":"${Architecture}"},\n' | \
    sed '$ s/,$//' | sed '1s/^/[/' | sed '$s/$/]/')

# Calcola hash
CURRENT_HASH=$(echo "$PACKAGES_JSON" | sha256sum | cut -d' ' -f1)

# Leggi hash precedente
PREVIOUS_HASH=""
if [[ -f "$STATE_FILE" ]]; then
    PREVIOUS_HASH=$(head -1 "$STATE_FILE")
fi

# Se hash uguale, niente da fare
if [[ "$CURRENT_HASH" == "$PREVIOUS_HASH" ]]; then
    echo "INFO: No changes detected (hash: ${CURRENT_HASH:0:16}...)"
    exit 0
fi

echo "INFO: Changes detected, uploading packages..."

# Prepara payload
PAYLOAD="{\"hash\": \"$CURRENT_HASH\", \"mode\": \"full\", \"packages\": $PACKAGES_JSON}"

# Invia al backend
RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/hosts/$HOSTNAME/packages" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    --connect-timeout 10 \
    --max-time 60)

# Verifica risposta
if echo "$RESPONSE" | grep -q '"status"'; then
    STATUS=$(echo "$RESPONSE" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    
    if [[ "$STATUS" == "updated" ]] || [[ "$STATUS" == "unchanged" ]]; then
        echo "$CURRENT_HASH" > "$STATE_FILE"
        
        ERRATA=$(echo "$RESPONSE" | grep -o '"total_errata":[0-9]*' | cut -d: -f2)
        echo "SUCCESS: Packages uploaded, applicable errata: $ERRATA"
        exit 0
    fi
fi

echo "ERROR: Upload failed - $RESPONSE"
exit 1
```

5. Nel tab **Inputs**, non servono input aggiuntivi

6. Nel tab **Job**, configura:
   - **Effective user**: `root`

7. Clicca **Submit**

### 2.3 Esecuzione Manuale su Host Singolo

1. Vai su **Hosts** → **All Hosts**
2. Seleziona un host Ubuntu/Debian
3. Clicca **Schedule Remote Job**
4. Seleziona **Job category**: `Packages`
5. Seleziona **Job template**: `Smart Package Upload - Errata`
6. Clicca **Submit**
7. Monitora l'esecuzione nel tab **Jobs**

### 2.4 Esecuzione su Multipli Host

1. Vai su **Hosts** → **All Hosts**
2. Filtra: `os ~ Ubuntu` o `os ~ Debian`
3. Seleziona gli host desiderati (checkbox)
4. Clicca **Select Action** → **Schedule Remote Job**
5. Seleziona il template `Smart Package Upload - Errata`
6. Clicca **Submit**

### 2.5 Schedulare Esecuzione Periodica

1. Vai su **Hosts** → **Templates** → **Job templates**
2. Trova `Smart Package Upload - Errata`
3. Clicca sul nome → **Schedule Recurring**
4. Configura:

| Campo | Valore |
|-------|--------|
| Target | Search query: `os ~ Ubuntu or os ~ Debian` |
| Schedule | `Hourly`, `Daily`, o `Custom cron` |
| Cron pattern (se custom) | `0 */6 * * *` (ogni 6 ore) |
| Start time | (scegli) |
| Ends | `Never` |

5. Clicca **Submit**

### 2.6 Monitoraggio Jobs

- **Monitor** → **Jobs**: Lista tutti i job eseguiti
- Filtra per `Smart Package Upload` per vedere solo questi job
- Clicca su un job per vedere dettagli e output per ogni host

---

## 3. Verifica Funzionamento

### 3.1 Dalla VM

```bash
# Verifica stato locale
cat /var/lib/katello-smart-upload/state | head -1

# Log (se usando cron)
tail -f /var/log/katello-smart-upload.log
```

### 3.2 Dal Backend

```bash
# Verifica hash salvato
curl http://10.172.5.4:5000/api/hosts/test-vm-production/hash

# Output atteso:
# {"hash":"a1b2c3d4...","last_update":"2024-12-11 15:30:00"}
```

### 3.3 Verifica Snapshot

```bash
curl "http://10.172.5.4:5000/api/history?days=1" | python3 -m json.tool
```

### 3.4 In Grafana

Il panel "Trend Errata nel Tempo" mostrerà un nuovo punto per ogni giorno in cui viene eseguito lo script.

---

## 4. Simulare un Cambiamento

Per testare che l'incrementale funzioni, installa un pacchetto:

```bash
# Installa un pacchetto di test
sudo apt install -y cowsay

# Esegui upload - dovrebbe rilevare cambiamento
sudo /usr/local/bin/katello-smart-upload.sh

# Output: Changes detected, uploading...

# Esegui di nuovo - dovrebbe dire "No changes"
sudo /usr/local/bin/katello-smart-upload.sh

# Output: No changes (hash: ...)

# Rimuovi il pacchetto di test
sudo apt remove -y cowsay
```

---

## 5. Troubleshooting

### 5.1 "Host not found"

**Causa**: L'hostname della VM non corrisponde a quello in Foreman.

**Verifica**:
```bash
# Sulla VM
hostname | tr '[:upper:]' '[:lower:]'

# Confronta con Foreman
curl -s -u admin:password -k https://foreman.example.com/api/hosts | \
    python3 -c "import json,sys; [print(h['name']) for h in json.load(sys.stdin)['results']]"
```

**Soluzione**: L'host deve essere prima registrato in Foreman.

### 5.2 "Connection refused"

**Causa**: Backend non raggiungibile.

**Verifica**:
```bash
curl http://10.172.5.4:5000/api/health
```

**Soluzione**: Verificare che il container ACI sia in esecuzione e la rete sia corretta.

### 5.3 Snapshot non creato

**Verifica**:
```bash
curl "http://10.172.5.4:5000/api/history?hostname=test-vm-production"
```

**Causa possibile**: L'host non ha errata correlati (nessun pacchetto matcha).

### 5.4 Forzare Re-upload Completo

```bash
# Rimuovi stato locale
sudo rm /var/lib/katello-smart-upload/state

# Riesegui
sudo /usr/local/bin/katello-smart-upload.sh
```

---

## 6. API Reference

### 6.1 GET /api/hosts/{hostname}/hash

Restituisce l'ultimo hash conosciuto per un host.

**Request:**
```bash
curl http://10.172.5.4:5000/api/hosts/test-vm-production/hash
```

**Response:**
```json
{
    "hash": "a1b2c3d4e5f6...",
    "last_update": "2024-12-11 15:30:00"
}
```

### 6.2 POST /api/hosts/{hostname}/packages

Aggiorna i pacchetti per un host.

**Request:**
```bash
curl -X POST http://10.172.5.4:5000/api/hosts/test-vm-production/packages \
    -H "Content-Type: application/json" \
    -d '{
        "hash": "sha256...",
        "mode": "full",
        "packages": [
            {"name": "bash", "version": "5.1-6", "arch": "amd64"},
            ...
        ]
    }'
```

**Response (successo):**
```json
{
    "status": "updated",
    "mode": "full",
    "packages_updated": 676,
    "packages_removed": 0,
    "errata_correlated": 4408,
    "snapshot": {
        "host": "test-vm-production",
        "snapshot_date": "2024-12-11",
        "total_errata": 512
    }
}
```

**Response (nessun cambiamento):**
```json
{
    "status": "unchanged",
    "message": "Package list unchanged",
    "packages_updated": 0
}
```

---

## 7. Confronto Metodi di Esecuzione

| Metodo | Pro | Contro | Quando Usare |
|--------|-----|--------|--------------|
| **Cron locale** | Semplice, autonomo | Difficile da monitorare, config su ogni VM | Pochi host, testing |
| **Foreman Remote Execution** | Centralizzato, monitorabile, schedulabile | Richiede Foreman configurato | **Produzione** |
| **Ansible** | Flessibile, idempotente | Richiede infrastruttura Ansible | Se già usi Ansible |

**Raccomandazione**: Usa **Foreman Remote Execution** per ambienti con più di 5 host.

---

## 8. Checklist Implementazione

- [ ] Script creato su ogni VM Ubuntu/Debian
- [ ] Test manuale eseguito con successo
- [ ] Job Template creato in Foreman
- [ ] Test Remote Execution su singolo host
- [ ] Test Remote Execution su multipli host
- [ ] Schedule ricorrente configurato
- [ ] Verifica snapshot in Grafana

---

*Documento generato: Dicembre 2024 - Versione 1.0*
