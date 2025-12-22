# Guida Completa: Modalità di Gestione Client in UYUNI

UYUNI supporta tre modalità principali per gestire i sistemi client. Questa guida copre configurazione, casi d'uso e best practice per ciascuna.

---

## Panoramica delle Modalità

| Modalità | Agent | Comunicazione | Casi d'uso |
|----------|-------|---------------|------------|
| **Salt Minion** | Sì (salt-minion) | Persistente (ZeroMQ) | Produzione, alta reattività |
| **Salt-SSH** | No (agentless) | On-demand (SSH) | DMZ, sistemi sensibili, bootstrap |
| **Traditional Client** | Sì (rhnsd/osad) | Polling/Push | Legacy (deprecato) |

---

## 1. Salt Minion (Agent-Based)

### Come Funziona

Il salt-minion è un servizio che gira sul client e mantiene una connessione persistente con il Salt Master (UYUNI server) tramite ZeroMQ sulla porta 4505/4506.

```
┌─────────────┐                    ┌─────────────┐
│   UYUNI     │◄──── ZeroMQ ──────►│  Salt Minion│
│   Server    │     (4505/4506)    │   (Client)  │
└─────────────┘                    └─────────────┘
```

### Vantaggi

- **Reattività immediata**: comandi eseguiti in tempo reale
- **Event-driven**: il minion può notificare eventi al master
- **Grains e Beacons**: raccolta automatica di informazioni sul sistema
- **Scalabilità**: gestisce migliaia di sistemi efficientemente
- **Stato persistente**: il minion mantiene la connessione attiva

### Svantaggi

- Richiede installazione e manutenzione dell'agent
- Porte firewall da aprire (4505/4506 TCP)
- Consumo risorse (minimo, ~20-50MB RAM)

### Configurazione in UYUNI

#### Prerequisiti sul Server UYUNI

```bash
# Verifica che il Salt Master sia attivo
systemctl status salt-master

# Verifica le porte aperte
firewall-cmd --list-ports | grep -E "4505|4506"
```

#### Metodo 1: Bootstrap dalla Web UI

1. **Systems → Bootstrapping**
2. Inserisci:
   - **Host**: IP o FQDN del client
   - **SSH Port**: 22
   - **User**: root (o utente con sudo)
   - **Authentication**: Password o chiave SSH
   - **Activation Key**: seleziona la chiave appropriata
3. **Lascia DESELEZIONATO** "Manage system completely via SSH"
4. Clicca **Bootstrap**

#### Metodo 2: Bootstrap via CLI

```bash
# Dal server UYUNI, usa mgr-bootstrap o spacecmd
spacecmd system_bootstrap -H <hostname> -u root -p <password> -a <activation-key>
```

#### Metodo 3: Installazione Manuale sul Client

```bash
# Su Ubuntu/Debian - Aggiungi il repository UYUNI tools
curl -o /usr/share/keyrings/uyuni-tools.gpg \
  https://<uyuni-server>/pub/uyuni-tools.gpg

echo "deb [signed-by=/usr/share/keyrings/uyuni-tools.gpg] \
  https://<uyuni-server>/pub/repositories/ubuntu/24/04/bootstrap/ /" \
  > /etc/apt/sources.list.d/uyuni-tools.list

apt update
apt install salt-minion

# Configura il minion
cat > /etc/salt/minion.d/uyuni.conf << EOF
master: <uyuni-server-fqdn>
server_id_use_crc: adler32
enable_legacy_startup_events: false
enable_fqdns_grains: false
EOF

# Avvia il servizio
systemctl enable --now salt-minion
```

#### Accettazione Chiave sul Server

```bash
# Visualizza chiavi in attesa
salt-key -L

# Accetta una chiave specifica
salt-key -a <minion-id>

# Accetta tutte le chiavi in attesa
salt-key -A
```

#### Verifica Connessione

```bash
# Test di connettività
salt '<minion-id>' test.ping

# Informazioni sul sistema
salt '<minion-id>' grains.items
```

---

## 2. Salt-SSH (Agentless)

### Come Funziona

Salt-SSH esegue comandi via SSH senza richiedere un agent permanente sul client. UYUNI si connette, esegue il comando, e chiude la connessione.

```
┌─────────────┐                    ┌─────────────┐
│   UYUNI     │────── SSH ────────►│   Client    │
│   Server    │     (porta 22)     │  (no agent) │
└─────────────┘                    └─────────────┘
```

### Vantaggi

- **Nessun agent** da installare o mantenere
- **Solo porta 22**: ideale per DMZ e ambienti restrittivi
- **Meno superficie di attacco**: nessun servizio in ascolto
- **Gestione sistemi "chiusi"**: dove non puoi installare software

### Svantaggi

- **Più lento**: ogni operazione apre una nuova connessione SSH
- **Non event-driven**: nessuna notifica proattiva dal client
- **Overhead di connessione**: meno efficiente per operazioni frequenti
- **Richiede Python** sul client (solitamente già presente)

### Configurazione in UYUNI

#### Prerequisiti

Sul client deve essere presente:
- Server SSH attivo (porta 22)
- Python 3 installato
- Utente con accesso root (diretto o via sudo)

#### Chiavi SSH di UYUNI

```bash
# Chiave privata generata automaticamente
/srv/susemanager/salt/salt_ssh/mgr_ssh_id

# Chiave pubblica (da distribuire ai client)
/srv/susemanager/salt/salt_ssh/mgr_ssh_id.pub
```

#### Metodo 1: Bootstrap dalla Web UI (Raccomandato)

1. **Systems → Bootstrapping**
2. Inserisci i dati del sistema
3. **SELEZIONA** ✅ "Manage system completely via SSH (Salt SSH)"
4. Clicca **Bootstrap**

UYUNI automaticamente:
- Si connette via SSH
- Copia la sua chiave pubblica in `~/.ssh/authorized_keys`
- Registra il sistema come Salt-SSH managed

#### Metodo 2: Configurazione Manuale

**Sul Server UYUNI:**

```bash
# Copia la chiave pubblica sul client
ssh-copy-id -i /srv/susemanager/salt/salt_ssh/mgr_ssh_id.pub root@<client-ip>

# Aggiungi il sistema al roster Salt-SSH
cat >> /etc/salt/roster << EOF
<minion-id>:
  host: <client-ip>
  user: root
  sudo: false
  priv: /srv/susemanager/salt/salt_ssh/mgr_ssh_id
EOF
```

**Test della connessione:**

```bash
# Test con salt-ssh
salt-ssh '<minion-id>' test.ping

# Esegui un comando
salt-ssh '<minion-id>' cmd.run 'hostname'
```

#### Metodo 3: Usando spacecmd

```bash
# Bootstrap con Salt-SSH
spacecmd system_bootstrap_ssh -H <hostname> -u root -k /path/to/key -a <activation-key>
```

### Configurazione Avanzata Salt-SSH

**File roster personalizzato** (`/etc/salt/roster`):

```yaml
# Sistema con sudo
ubuntu-web01:
  host: 192.168.1.100
  user: admin
  sudo: true
  priv: /srv/susemanager/salt/salt_ssh/mgr_ssh_id
  tty: true  # Necessario per sudo con password

# Sistema con porta SSH non standard
secure-server:
  host: 10.0.0.50
  port: 2222
  user: root
  priv: /srv/susemanager/salt/salt_ssh/mgr_ssh_id

# Sistema con timeout personalizzato
slow-system:
  host: remote.example.com
  user: root
  priv: /srv/susemanager/salt/salt_ssh/mgr_ssh_id
  timeout: 60
```

**Opzioni globali** (`/etc/salt/master`):

```yaml
# Configurazione Salt-SSH
ssh_user: root
ssh_priv: /srv/susemanager/salt/salt_ssh/mgr_ssh_id
ssh_timeout: 30
ssh_scan_timeout: 5
```

---

## 3. Traditional Client (Legacy - Deprecato)

### ⚠️ Nota Importante

Il Traditional Client è **deprecato** in UYUNI/SUSE Manager. È supportato solo per compatibilità con sistemi legacy. Per nuove installazioni, usa sempre Salt Minion o Salt-SSH.

### Come Funziona

Usa i tool originali di Spacewalk/Red Hat Satellite:
- **rhnsd**: daemon che fa polling periodico al server
- **osad**: daemon per push immediato (richiede osa-dispatcher sul server)

```
┌─────────────┐                    ┌─────────────┐
│   UYUNI     │◄──── XMLRPC ──────►│   rhnsd     │
│   Server    │      (443)         │   (Client)  │
└─────────────┘                    └─────────────┘
```

### Quando si Usa

- Migrazione da Spacewalk/Satellite legacy
- Sistemi molto vecchi incompatibili con Salt
- Requisiti di compatibilità specifici

### Configurazione (Solo per Riferimento)

```bash
# Sul client - NON RACCOMANDATO per nuove installazioni
apt install rhn-setup rhnsd  # Se disponibile

# Registrazione
rhnreg_ks --serverUrl=https://<uyuni-server>/XMLRPC \
          --activationkey=<key>

# Avvio daemon
systemctl enable --now rhnsd
```

### Limitazioni

- Nessuna esecuzione remota in tempo reale (senza osad)
- Funzionalità ridotte rispetto a Salt
- Non supporta tutti i moduli Salt
- In fase di dismissione

---

## 4. Confronto Dettagliato

### Tabella Comparativa Completa

| Caratteristica | Salt Minion | Salt-SSH | Traditional |
|----------------|-------------|----------|-------------|
| **Agent richiesto** | Sì | No | Sì |
| **Porte firewall** | 4505, 4506 | 22 | 443 |
| **Latenza comandi** | Millisecondi | Secondi | Minuti (polling) |
| **Scalabilità** | Eccellente | Buona | Limitata |
| **Risorse client** | ~50MB RAM | Solo durante exec | ~30MB RAM |
| **Event-driven** | Sì | No | Solo con osad |
| **Remote Execution** | ✅ Tempo reale | ✅ On-demand | ⚠️ Limitato |
| **Configuration Mgmt** | ✅ Completo | ✅ Completo | ⚠️ Parziale |
| **Package Management** | ✅ Completo | ✅ Completo | ✅ Completo |
| **Patch Management** | ✅ Completo | ✅ Completo | ✅ Completo |
| **Auditing/Compliance** | ✅ Completo | ✅ Completo | ⚠️ Limitato |
| **Futuro supporto** | ✅ Attivo | ✅ Attivo | ❌ Deprecato |

### Quando Usare Cosa

```
┌─────────────────────────────────────────────────────────────────┐
│                    ALBERO DECISIONALE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Puoi installare agent sul client?                              │
│       │                                                         │
│       ├── SÌ ──► Hai bisogno di reattività in tempo reale?     │
│       │              │                                          │
│       │              ├── SÌ ──► SALT MINION ★                  │
│       │              │                                          │
│       │              └── NO ──► Salt Minion (raccomandato)     │
│       │                         o Salt-SSH (accettabile)        │
│       │                                                         │
│       └── NO ──► Il client ha SSH e Python?                    │
│                      │                                          │
│                      ├── SÌ ──► SALT-SSH ★                     │
│                      │                                          │
│                      └── NO ──► Configura SSH/Python           │
│                                 poi usa Salt-SSH                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Raccomandazioni per il Tuo Ambiente

Per la gestione di centinaia di sistemi Ubuntu/Debian in un ambiente enterprise come il PSN:

**Scenario 1: Sistemi in rete interna**
→ Usa **Salt Minion** per massima reattività e controllo

**Scenario 2: Sistemi in DMZ o con firewall restrittivo**
→ Usa **Salt-SSH** (solo porta 22 outbound)

**Scenario 3: Ambiente misto**
→ Combinazione di entrambi, UYUNI li gestisce trasparentemente

---

## 5. Configurazione Ibrida (Best Practice)

Puoi avere sistemi Salt Minion e Salt-SSH nello stesso UYUNI. La Web UI li gestisce in modo uniforme.

### Identificare il Tipo di Gestione

**Dalla Web UI:**
- Systems → [sistema] → Details → Properties
- Cerca "Contact Method": `default` (minion) o `ssh-push` (Salt-SSH)

**Via API/CLI:**

```bash
# Elenca tutti i sistemi con il loro metodo di contatto
spacecmd system_list -v

# Oppure via Salt
salt-run manage.status  # Mostra solo i minion
salt-ssh '*' test.ping  # Testa solo i Salt-SSH
```

### Script per Identificare i Client

```bash
#!/bin/bash
# identify-client-types.sh

echo "=== Salt Minions (Agent) ==="
salt-key -L 2>/dev/null | grep -A 1000 "Accepted Keys:" | tail -n +2

echo ""
echo "=== Salt-SSH Clients (Agentless) ==="
cat /etc/salt/roster 2>/dev/null | grep -E "^[a-zA-Z]" | cut -d: -f1
```

---

## 6. Comandi Utili di Gestione

### Salt Minion

```bash
# Ping tutti i minion
salt '*' test.ping

# Esegui comando su tutti
salt '*' cmd.run 'uptime'

# Applica state
salt '*' state.apply

# Sync all modules
salt '*' saltutil.sync_all

# Visualizza grains (info sistema)
salt '<minion>' grains.items

# Aggiorna package list
salt '<minion>' pkg.refresh_db

# Installa pacchetto
salt '<minion>' pkg.install vim

# Riavvia servizio
salt '<minion>' service.restart apache2
```

### Salt-SSH

```bash
# Ping (nota: più lento)
salt-ssh '*' test.ping

# Esegui comando
salt-ssh '<host>' cmd.run 'df -h'

# Applica state
salt-ssh '<host>' state.apply

# Con sudo (se non root)
salt-ssh --sudo '<host>' cmd.run 'apt update'

# Specifica roster alternativo
salt-ssh --roster-file=/path/to/roster '<host>' test.ping

# Raw SSH (senza Salt thin)
salt-ssh --raw '<host>' 'cat /etc/os-release'
```

### Conversione tra Modalità

**Da Salt-SSH a Salt Minion:**

```bash
# Installa salt-minion via Salt-SSH
salt-ssh '<host>' pkg.install salt-minion

# Configura
salt-ssh '<host>' cmd.run 'echo "master: <uyuni-server>" > /etc/salt/minion.d/master.conf'

# Avvia
salt-ssh '<host>' service.start salt-minion
salt-ssh '<host>' service.enable salt-minion

# Accetta la nuova chiave sul server
salt-key -a <host>

# Rimuovi dal roster Salt-SSH (opzionale)
# Oppure ri-registra dalla UI
```

**Da Salt Minion a Salt-SSH:**

1. Ri-registra il sistema dalla UI con l'opzione Salt-SSH
2. Oppure rimuovi il minion e aggiungi al roster manualmente

---

## 7. Troubleshooting

### Salt Minion

```bash
# Stato del servizio
systemctl status salt-minion

# Log del minion
journalctl -u salt-minion -f

# Test connettività master
salt-call test.ping

# Verifica configurazione
salt-call --local grains.get master

# Rigenera chiavi (se corrotte)
systemctl stop salt-minion
rm -f /etc/salt/pki/minion/minion.*
systemctl start salt-minion
# Poi accetta la nuova chiave sul master
```

### Salt-SSH

```bash
# Test SSH diretto
ssh -i /srv/susemanager/salt/salt_ssh/mgr_ssh_id root@<host> 'echo OK'

# Verbosity aumentata
salt-ssh -v '<host>' test.ping
salt-ssh -vvv '<host>' test.ping  # Debug completo

# Verifica roster
cat /etc/salt/roster | grep -A5 '<host>'

# Test con timeout aumentato
salt-ssh --timeout=60 '<host>' test.ping

# Pulisci thin cache (se problemi con moduli)
salt-ssh '<host>' saltutil.clear_cache
```

### Problemi Comuni

| Problema | Salt Minion | Salt-SSH |
|----------|-------------|----------|
| Connessione fallita | Verifica porte 4505/4506 | Verifica SSH porta 22 |
| Timeout | Aumenta `timeout` in minion config | Usa `--timeout` |
| Auth failed | Rigenera chiavi | Verifica authorized_keys |
| Moduli mancanti | `saltutil.sync_all` | `saltutil.clear_cache` |

---

## 8. Sicurezza

### Salt Minion

```bash
# Autenticazione basata su chiavi PKI
/etc/salt/pki/minion/minion.pem    # Chiave privata minion
/etc/salt/pki/minion/minion.pub    # Chiave pubblica minion
/etc/salt/pki/minion/minion_master.pub  # Chiave pubblica master

# Hardening: accetta solo il master specifico
# /etc/salt/minion.d/security.conf
master_finger: 'aa:bb:cc:dd:...'  # Fingerprint del master
```

### Salt-SSH

```bash
# Protezione chiave privata
chmod 600 /srv/susemanager/salt/salt_ssh/mgr_ssh_id
chown root:root /srv/susemanager/salt/salt_ssh/mgr_ssh_id

# Limita accesso SSH solo da UYUNI (sui client)
# /etc/ssh/sshd_config.d/uyuni.conf
Match Address <uyuni-server-ip>
    PermitRootLogin prohibit-password
    PubkeyAuthentication yes
```

---

## Riepilogo Finale

Per il tuo ambiente PSN con centinaia di Ubuntu/Debian:

1. **Usa Salt Minion** come default per i sistemi interni
2. **Usa Salt-SSH** per DMZ e sistemi con restrizioni firewall
3. **Evita Traditional Client** - è deprecato
4. **Sfrutta la gestione ibrida** - UYUNI gestisce entrambi trasparentemente

La shell remota che cercavi si ottiene facilmente con Salt-SSH già configurato, usando:
```bash
ssh -i /srv/susemanager/salt/salt_ssh/mgr_ssh_id root@<qualsiasi-client>
```
