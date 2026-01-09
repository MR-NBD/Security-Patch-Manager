# ✅ WORKFLOW CORRETTO - Architettura 2 Container

## 🏗️ Architettura

```
┌─────────────────────────────────────────────────────────┐
│                  INTERNET                               │
│                                                         │
│  ┌──────────────────────────────────────┐              │
│  │  Container PUBBLICO                  │              │
│  │  IP: 4.232.4.32 (pubblico)         │              │
│  │                                      │              │
│  │  - Sync USN (Ubuntu)                │              │
│  │  - Sync DSA (Debian)                │              │
│  │  - Sync OVAL (CVE mapping)          │              │
│  │  - Sync NVD (CVE enrichment)        │              │
│  └──────────────────────────────────────┘              │
│            ↓ (DB condiviso)                            │
└─────────────────────────────────────────────────────────┘
            │
            │ Database Azure PostgreSQL
            │ (accessibile da entrambi)
            │
┌─────────────────────────────────────────────────────────┐
│          VNET PRIVATA (10.172.0.0/16)                   │
│                                                         │
│  ┌──────────────────────────────────────┐              │
│  │  Container INTERNO                   │              │
│  │  IP: 10.172.5.5 (privato)           │              │
│  │                                      │              │
│  │  - Update package cache              │              │
│  │  - Push errata a UYUNI               │              │
│  └──────────────────────────────────────┘              │
│            ↑                                            │
│  ┌──────────────────────────────────────┐              │
│  │  Server UYUNI                        │              │
│  │  IP: 10.172.2.5                     │              │
│  └──────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────┘
```

---

## 🔄 Workflow Operativo

### FASE 1: Sync Esterni (Da Azure Cloud Shell o PC)

**Script**: `remote-sync.sh`
**Container**: Pubblico (4.232.4.32)
**Dove**: Azure Cloud Shell, tuo PC, CI/CD pipeline

```bash
# Da Azure Cloud Shell o il tuo PC
cd /path/to/scripts
./remote-sync.sh full
```

**Operazioni**:
1. ✅ Sync Ubuntu USN (2-5 min)
2. ✅ Sync Debian DSA (15-30 min)
3. ✅ Sync OVAL definitions (10-20 min) ← **CRITICO per CVE visibility**
4. ✅ Sync NVD CVE enrichment (5-10 min)

**Risultato**: Database popolato con errata e CVE

---

### FASE 2: Sync Interni (Dal Server UYUNI)

**Script**: `uyuni-server-sync.sh`
**Container**: Interno (10.172.5.5)
**Dove**: Server UYUNI (10.172.2.5)

```bash
# Dal server UYUNI
ssh root@10.172.2.5
/root/uyuni-server-sync.sh quick
```

**Operazioni**:
1. ✅ Update package cache da UYUNI (5-10 min)
2. ✅ Push errata a UYUNI (5-15 min)

**Risultato**: Patch visibili in UYUNI, CVE mappate ai sistemi

---

## 📋 SETUP INIZIALE

### 1. Copia Script sul Server UYUNI

```bash
# Dal tuo workstation/Azure Cloud Shell
cd /mnt/c/Users/alber/Documents/GitHub/Security-Patch-Manager/Uyuni/Initial-Setup

scp uyuni-server-sync.sh root@10.172.2.5:/root/
scp WORKFLOW-CORRETTO.md root@10.172.2.5:/root/
```

### 2. Tieni Script Remoto sul Tuo PC/Cloud Shell

```bash
# Questo rimane sul tuo PC o in Azure Cloud Shell
# NON copiarlo sul server UYUNI (non funzionerebbe)
chmod +x remote-sync.sh
```

---

## 🚀 PRIMO SYNC COMPLETO

### Step 1: Sync Esterni (Da PC/Cloud Shell)

```bash
# Da Azure Cloud Shell o tuo PC
./remote-sync.sh full
```

Tempo: ~30-45 minuti

### Step 2: Sync Interni (Da Server UYUNI)

```bash
# SSH nel server UYUNI
ssh root@10.172.2.5

# Rendi eseguibile
chmod +x /root/uyuni-server-sync.sh

# Esegui sync interno
/root/uyuni-server-sync.sh quick
```

Tempo: ~10-20 minuti

### Step 3: Verifica in UYUNI

1. **Web UI**: `Patches → Patch List`
   - Dovresti vedere migliaia di patch

2. **CVE Audit**: `Audit → CVE Audit`
   - Cerca un CVE, dovresti vedere sistemi vulnerabili

---

## 🔁 SYNC RICORRENTE

### Opzione A: Manuale Settimanale

**Domenica mattina** (30-60 min totali):

```bash
# 1. Da PC/Cloud Shell
./remote-sync.sh full

# 2. Dal server UYUNI
ssh root@10.172.2.5
/root/uyuni-server-sync.sh quick
```

### Opzione B: Automazione con Cron

#### Sul Server UYUNI (solo sync interni)

```bash
# Sul server UYUNI
cat > /etc/cron.d/uyuni-internal-sync << 'EOF'
# Sync interno ogni lunedì alle 03:00 (dopo sync esterno)
0 3 * * 1 root /root/uyuni-server-sync.sh quick >> /var/log/uyuni-sync.log 2>&1
EOF
```

#### Da Azure Automation/CI-CD (sync esterni)

Opzioni:
1. **Azure Automation Runbook** (consigliato)
2. **Azure Logic App**
3. **GitHub Actions** schedulato
4. **Cron su VM jumphost**

Esempio Azure Automation:
```powershell
# Runbook PowerShell
$uri = "http://4.232.4.32:5000/api/sync"

# Sync USN
Invoke-RestMethod -Method POST -Uri "$uri/usn"

# Sync DSA
Invoke-RestMethod -Method POST -Uri "$uri/dsa/full"

# Sync OVAL
Invoke-RestMethod -Method POST -Uri "$uri/oval?platform=all"

# Sync NVD
Invoke-RestMethod -Method POST -Uri "$uri/nvd?batch_size=100&prioritize=true"
```

---

## 📊 MONITORAGGIO

### Check Rapido

**Da PC/Cloud Shell** (container pubblico):
```bash
./remote-sync.sh test
curl -s http://4.232.4.32:5000/api/health
```

**Da Server UYUNI** (container interno):
```bash
/root/uyuni-server-sync.sh test
/root/uyuni-server-sync.sh stats
```

### Metriche Attese

Dopo primo sync completo:

| Metrica | Valore |
|---------|--------|
| Errata totali | > 5000 |
| Errata USN | > 3000 |
| Errata DSA | > 2000 |
| OVAL definitions | > 15000 |
| Pacchetti cache | > 250000 |

---

## 🆘 TROUBLESHOOTING

### Container pubblico non raggiungibile da server UYUNI

✅ **Normale!** Il server UYUNI è nella VNET privata, non può raggiungere IP pubblici.

**Soluzione**: Usa `remote-sync.sh` da PC/Cloud Shell

### Container interno non raggiungibile da PC

✅ **Normale!** Il container interno è nella VNET privata.

**Soluzione**: Usa `uyuni-server-sync.sh` dal server UYUNI

### Nessuna patch visibile dopo sync

**Checklist**:
1. Sync esterno completato? → Verifica con `remote-sync.sh test`
2. OVAL sincronizzato? → Critico per CVE visibility
3. Sync interno eseguito? → `uyuni-server-sync.sh quick`
4. Cache aggiornata? → Verifica log

---

## 💡 BEST PRACTICES

### 1. Ordine delle Operazioni

**SEMPRE**:
1. Prima: Sync esterni (`remote-sync.sh`)
2. Poi: Sync interni (`uyuni-server-sync.sh`)

**MAI** fare sync interni prima degli esterni!

### 2. Frequenza Sync

| Operazione | Frequenza Consigliata |
|------------|----------------------|
| Sync esterni (USN, DSA) | 1x settimana |
| Sync OVAL | 1x settimana |
| Sync NVD | 1x settimana (o on-demand) |
| Sync interni (cache + push) | Dopo ogni sync esterno |

### 3. Finestra di Manutenzione

**Consigliato**: Domenica 02:00-04:00
- 02:00-03:00: Sync esterni (automatico via Azure Automation)
- 03:00-03:30: Sync interni (automatico via cron su UYUNI)
- 03:30-04:00: Buffer per retry/errori

---

## 📁 RIEPILOGO SCRIPT

| Script | Dove Eseguire | Container | Operazioni |
|--------|---------------|-----------|------------|
| `remote-sync.sh` | PC/Cloud Shell | Pubblico | USN, DSA, OVAL, NVD |
| `uyuni-server-sync.sh` | Server UYUNI | Interno | Cache, Push |
| `check-containers.sh` | PC/Cloud Shell | Entrambi | Verifica stato/IP |

---

## ✅ CHECKLIST SETUP COMPLETO

- [ ] Script `remote-sync.sh` sul PC/Cloud Shell
- [ ] Script `uyuni-server-sync.sh` sul server UYUNI
- [ ] Test connettività entrambi gli script
- [ ] Primo sync esterno completato
- [ ] Primo sync interno completato
- [ ] Patch visibili in UYUNI Web UI
- [ ] CVE Audit funzionante
- [ ] Automazione configurata (opzionale)
- [ ] Documentazione letta e compresa

---

**Data**: 2026-01-08
**Versione**: v2.5-FIXED
**Status**: ✅ Architettura Corretta e Funzionante
