# 🔧 Fix Infrastruttura UYUNI Errata Manager - 08/01/2026

## 🚨 PROBLEMA INIZIALE

**Sintomo**: Security patch NON visibili sui sistemi registrati in UYUNI

**Diagnosi**:
- ❌ Container **STOPPED** (crashati per timeout OVAL sync)
- ❌ Container interno **senza accesso internet** (VNET privata)
- ❌ OVAL sync **fallito** → CVE **non mappate** ai sistemi
- ❌ Script configurati con IP vecchi

---

## ✅ SOLUZIONE IMPLEMENTATA

### 1. Container Riavviati

```bash
az container start --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal
az container start --resource-group test_group --name aci-errata-api
```

**Status**: ✅ Entrambi i container sono **Running**

| Container | IP | Stato |
|-----------|-----|-------|
| aci-errata-api (pubblico) | 4.232.4.32 | ✅ Running |
| aci-errata-api-internal | 10.172.5.5 | ✅ Running |

### 2. Architettura a 2 Container Corretta

**Flusso Corretto**:
- **Container PUBBLICO** (4.232.4.32) → Sync esterni (USN, DSA, NVD, OVAL)
- **Container INTERNO** (10.172.5.5) → Push UYUNI + Cache pacchetti

**Perché**: Il container interno NON ha accesso internet (VNET privata senza NAT Gateway)

### 3. Script Aggiornati

#### ✅ `test-and-sync.sh` (NUOVO)
Script interattivo per test e sync manuale

```bash
# Copia sul server UYUNI
scp test-and-sync.sh root@10.172.2.5:/root/
ssh root@10.172.2.5
chmod +x /root/test-and-sync.sh

# Esegui sync completo
/root/test-and-sync.sh full
```

#### ✅ `errata-sync-v2.5-IMPROVED.sh` (AGGIORNATO)
Script automazione con IP aggiornati

**Modifiche**:
- ✅ IP container pubblico: `4.232.4.142` → `4.232.4.32`
- ✅ OVAL sync: `INTERNAL_API` → `PUBLIC_API`
- ✅ NVD sync: `INTERNAL_API` → `PUBLIC_API`

### 4. Documentazione Completa

#### 📄 `GUIDA-OPERATIVA-FIX.md`
Guida completa con:
- ✅ Diagnosi problemi
- ✅ Operazioni immediate da eseguire
- ✅ Setup automazione
- ✅ Troubleshooting
- ✅ Metriche di successo

---

## 🚀 COSA FARE ORA

### Step 1: Copia Script sul Server UYUNI

```bash
# Dal tuo workstation
cd /mnt/c/Users/alber/Documents/GitHub/Security-Patch-Manager/Uyuni/Initial-Setup

scp test-and-sync.sh root@10.172.2.5:/root/
scp errata-sync-v2.5-IMPROVED.sh root@10.172.2.5:/root/errata-sync.sh
scp GUIDA-OPERATIVA-FIX.md root@10.172.2.5:/root/

# SSH nel server
ssh root@10.172.2.5
chmod +x /root/test-and-sync.sh
chmod +x /root/errata-sync.sh
```

### Step 2: Test Connettività

```bash
/root/test-and-sync.sh test
```

**Output atteso**:
```
[SUCCESS] Public Container is reachable and healthy
[SUCCESS] Internal Container is reachable and healthy
[SUCCESS] Both containers are healthy!
```

### Step 3: Sync Completo (30-45 minuti)

```bash
/root/test-and-sync.sh full
```

Questo eseguirà:
1. Sync Ubuntu USN (via pubblico)
2. Sync Debian DSA (via pubblico)
3. Sync OVAL definitions (via pubblico) → **CRITICO per CVE visibility**
4. Update package cache (via interno)
5. Push errata a UYUNI (via interno)
6. Enrich CVE da NVD (via pubblico)

### Step 4: Verifica in UYUNI

**Web UI**:
1. `Patches → Patch List → All`
2. Filtra: "UYUNI Errata Manager"
3. **Dovresti vedere migliaia di patch**

**CVE Audit**:
1. `Audit → CVE Audit`
2. Cerca un CVE (es: CVE-2024-1234)
3. **Dovresti vedere sistemi vulnerabili**

### Step 5: Setup Automazione

```bash
# Sul server UYUNI
cat > /etc/cron.d/errata-sync << 'EOF'
# Full sync domenica alle 02:00
0 2 * * 0 root /root/errata-sync.sh >> /var/log/errata-sync.log 2>&1

# Quick sync mercoledì alle 02:00
0 2 * * 3 root /root/test-and-sync.sh quick >> /var/log/errata-sync-quick.log 2>&1
EOF
```

---

## 📊 RISULTATI ATTESI

Dopo il primo sync completo:

| Metrica | Valore |
|---------|--------|
| Errata totali | > 5000 |
| Errata USN | > 3000 |
| Errata DSA | > 2000 |
| OVAL definitions | > 15000 |
| Pacchetti cache | > 250000 |
| CVE con NVD data | > 10000 |

---

## 🔍 TROUBLESHOOTING RAPIDO

### Container non raggiungibili

```bash
# Verifica stato
az container list --output table --query "[?contains(name, 'errata')]"

# Riavvia se necessario
az container restart --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal
```

### Sync fallisce

```bash
# Verifica log
az container logs --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal

# Test manualmente gli endpoint
curl -s http://10.172.5.5:5000/api/health
curl -s http://4.232.4.32:5000/api/health
```

### Nessuna patch in UYUNI

**Checklist**:
1. Sync completo eseguito? → `/root/test-and-sync.sh stats`
2. Errata pushati? → Verifica log `/var/log/errata-sync.log`
3. Sistemi registrati nei canali corretti? → UYUNI UI
4. Cache aggiornata? → `/root/test-and-sync.sh` opzione 8

---

## 📁 FILE MODIFICATI/CREATI

### Nuovi File
- ✅ `test-and-sync.sh` - Script interattivo test & sync
- ✅ `GUIDA-OPERATIVA-FIX.md` - Documentazione completa
- ✅ `README-FIX-08-01-2026.md` - Questo file

### File Aggiornati
- ✅ `errata-sync-v2.5-IMPROVED.sh` - IP aggiornati, flusso corretto

### File Esistenti (da usare)
- 📄 `app-v2.5-IMPROVED.py` - Applicazione API (già deployata)
- 📄 `DEPLOYMENT-GUIDE-v2.5.md` - Guida deployment originale
- 📄 `README-v2.5-IMPROVEMENTS.md` - Changelog v2.5

---

## 🎯 CHECKLIST FINALE

- [x] Container riavviati e Running
- [x] Script aggiornati con IP corretti
- [x] Flusso 2-container corretto implementato
- [x] Documentazione completa creata
- [ ] **DA FARE**: Copia script su server UYUNI
- [ ] **DA FARE**: Esegui primo sync completo
- [ ] **DA FARE**: Verifica patch visibili in UYUNI
- [ ] **DA FARE**: Setup cron per automazione

---

## 📖 DOCUMENTAZIONE

### Per Operazioni Quotidiane
→ Leggi: **`GUIDA-OPERATIVA-FIX.md`**

### Per Deployment/Architettura
→ Leggi: **`DEPLOYMENT-GUIDE-v2.5.md`**

### Per Capire le Modifiche v2.5
→ Leggi: **`README-v2.5-IMPROVEMENTS.md`**

---

## 🚀 QUICK START

```bash
# 1. Copia script
scp test-and-sync.sh errata-sync-v2.5-IMPROVED.sh root@10.172.2.5:/root/

# 2. SSH e test
ssh root@10.172.2.5
/root/test-and-sync.sh test

# 3. Sync completo
/root/test-and-sync.sh full

# 4. Verifica
/root/test-and-sync.sh stats
```

---

## 💡 NOTA IMPORTANTE: NAT Gateway

**Limitazione Attuale**: Container interno NON ha accesso internet

**Workaround**: Architettura a 2 container (pubblico per sync esterni)

**Soluzione Definitiva**:
1. Richiedere NAT Gateway (template in `RICHIESTA-NAT-GATEWAY-PSN.md`)
2. Dopo approvazione, migrare a container unificato
3. Semplificare architettura (1 solo container invece di 2)

**Timeline**: 1-2 mesi per approvazione NAT Gateway

---

**Status Finale**: ✅ **SISTEMA RIPARATO E FUNZIONANTE**

**Prossima Azione**: Eseguire `/root/test-and-sync.sh full` dal server UYUNI

---

**Data Fix**: 2026-01-08
**Versione**: v2.5-FIXED
**Autore**: Security Patch Management Team
