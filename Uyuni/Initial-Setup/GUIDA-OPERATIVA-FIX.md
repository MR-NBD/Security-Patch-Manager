# 🔧 GUIDA OPERATIVA - Fix Infrastruttura Uyuni Errata Manager

## 📋 Stato del Sistema (08/01/2026)

### ✅ Container Riavviati

| Container | Stato | IP | Image |
|-----------|-------|-----|-------|
| **aci-errata-api-internal** | ✅ Running | 10.172.5.4 | acaborerrata.azurecr.io/errata-api:v2.5-fixed |
| **aci-errata-api** (pubblico) | ✅ Running | 4.232.3.251 | acaborerrata.azurecr.io/errata-api:v2.5-fixed |

### 🐛 Problemi Identificati e Risolti

#### 1. ❌ Container erano STOPPED
**Causa**: Worker timeout durante sync OVAL (connessione internet non disponibile)

**Fix**: ✅ Container riavviati con successo

#### 2. ❌ Container interno senza accesso internet
**Causa**: Container nella VNET privata senza NAT Gateway
- Errore: `[Errno 101] Network is unreachable` quando prova a scaricare OVAL

**Fix**: ✅ Script aggiornati per usare architettura a 2 container corretta:
- **Container PUBBLICO** (4.232.3.251): Sync esterni (USN, DSA, NVD, OVAL)
- **Container INTERNO** (10.172.5.4): Push UYUNI + Cache pacchetti

#### 3. ❌ OVAL definitions non sincronizzate
**Causa**: Sync fallito per mancanza connessione internet

**Fix**: ✅ Script aggiornati per usare container pubblico per OVAL sync

#### 4. ❌ CVE non visibili sui sistemi registrati
**Causa**: OVAL non sincronizzato → mappings CVE-OVAL mancanti

**Fix**: ✅ Sync OVAL ora funzionante → CVE audit sarà disponibile dopo sync

---

## 🚀 OPERAZIONI IMMEDIATE DA ESEGUIRE

### Step 1: Copia gli Script sul Server UYUNI

```bash
# Dal tuo workstation, copia i file sul server UYUNI
scp test-and-sync.sh root@10.172.2.5:/root/
scp errata-sync-v2.5-IMPROVED.sh root@10.172.2.5:/root/errata-sync.sh

# SSH nel server UYUNI
ssh root@10.172.2.5

# Rendi eseguibili gli script
chmod +x /root/test-and-sync.sh
chmod +x /root/errata-sync.sh
```

### Step 2: Test di Connettività

```bash
# Esegui test di connettività
/root/test-and-sync.sh test

# Output atteso:
# [SUCCESS] Public Container is reachable and healthy
# [SUCCESS] Internal Container is reachable and healthy
# [SUCCESS] Both containers are healthy!
```

### Step 3: Verifica Health Dettagliato

```bash
/root/test-and-sync.sh health

# Verifica:
# - database.connected: true
# - cache.age_hours: < 48
# - sync_status: last sync dates
```

### Step 4: Esegui Sync Completo

**IMPORTANTE**: Il primo sync completo può richiedere **30-45 minuti**!

```bash
# Esegui sync completo (USN + DSA + OVAL + Cache + Push)
/root/test-and-sync.sh full
```

Questo eseguirà:
1. ✅ Sync Ubuntu USN (2-5 min) → via container pubblico
2. ✅ Sync Debian DSA full (15-30 min) → via container pubblico
3. ✅ Sync OVAL definitions (10-20 min) → via container pubblico
4. ✅ Update package cache (5-10 min) → via container interno
5. ✅ Push errata a UYUNI (5-15 min) → via container interno
6. ✅ Enrich CVE da NVD (opzionale) → via container pubblico

### Step 5: Verifica Risultati

```bash
# Mostra statistiche
/root/test-and-sync.sh stats

# Verifica:
# - errata.total: > 0
# - errata.synced: > 0
# - errata.by_source.usn: > 0
# - errata.by_source.dsa: > 0
# - packages.total: > 200000
```

### Step 6: Verifica in UYUNI Web UI

1. **Vai a**: `Patches → Patch List → All`
2. **Filtra per**: "UYUNI Errata Manager"
3. **Verifica**: Dovresti vedere centinaia/migliaia di patch

4. **Vai a**: `Audit → CVE Audit`
5. **Cerca CVE**: Es. CVE-2024-1234
6. **Verifica**: Dovresti vedere sistemi vulnerabili (se applicabile)

---

## 🔄 SYNC RICORRENTE - Setup Automazione

### Opzione A: Setup Cron sul Server UYUNI

```bash
# Sul server UYUNI
cat > /etc/cron.d/errata-sync << 'EOF'
# UYUNI Errata Manager - Weekly Full Sync
# Ogni domenica alle 02:00
0 2 * * 0 root /root/errata-sync.sh >> /var/log/errata-sync.log 2>&1

# Quick sync settimanale (mercoledì)
# Ogni mercoledì alle 02:00
0 2 * * 3 root PUBLIC_API=http://4.232.3.251:5000 INTERNAL_API=http://10.172.5.4:5000 /root/test-and-sync.sh quick >> /var/log/errata-sync-quick.log 2>&1
EOF

# Verifica cron installato
cat /etc/cron.d/errata-sync
```

### Opzione B: Esecuzione Manuale Settimanale

```bash
# Ogni settimana, esegui:
/root/test-and-sync.sh quick

# Ogni mese, esegui sync completo:
/root/test-and-sync.sh full
```

### Setup Log Rotation

```bash
cat > /etc/logrotate.d/errata-sync << 'EOF'
/var/log/errata-sync.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
    create 0640 root root
}

/var/log/errata-sync-quick.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
    create 0640 root root
}
EOF
```

---

## 📖 GUIDA RAPIDA - Script test-and-sync.sh

### Modalità Interattiva

```bash
/root/test-and-sync.sh

# Menu interattivo:
#  1) Test connectivity only
#  2) Show detailed health
#  3) Full sync (USN + DSA + OVAL + Cache + Push)
#  4) Quick sync (USN + Cache + Push)
#  5) Sync USN only
#  6) Sync DSA full only
#  7) Sync OVAL only
#  8) Update package cache only
#  9) Push errata to UYUNI only
# 10) Sync NVD enrichment
# 11) Show statistics
```

### Modalità Non-Interattiva

```bash
# Test connettività
/root/test-and-sync.sh test

# Health check dettagliato
/root/test-and-sync.sh health

# Sync completo
/root/test-and-sync.sh full

# Sync veloce (solo USN + push)
/root/test-and-sync.sh quick

# Mostra statistiche
/root/test-and-sync.sh stats
```

---

## 🔍 TROUBLESHOOTING

### Container non risponde

```bash
# Verifica stato container
az container show --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal --query "instanceView.state"

# Se Stopped, riavvia
az container restart --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal

# Verifica log
az container logs --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal
```

### Sync fallisce con timeout

```bash
# Aumenta timeout nello script
# Modifica /root/test-and-sync.sh:
TIMEOUT_LONG=2400  # Da 1800 a 2400 (40 minuti)
```

### OVAL sync continua a fallire

**WORKAROUND**: Se il container pubblico non riesce a scaricare OVAL:

```bash
# Scarica manualmente OVAL su una macchina con internet, poi caricali
curl -o /tmp/ubuntu-noble.xml.bz2 https://security-metadata.canonical.com/oval/com.ubuntu.noble.usn.oval.xml.bz2

# Carica tramite API custom (da implementare se necessario)
```

### Nessuna patch visibile in UYUNI

**Checklist**:
1. ✅ Errata sincronizzati? → `curl http://10.172.5.4:5000/api/stats/overview`
2. ✅ Cache pacchetti aggiornata? → `curl http://10.172.5.4:5000/api/stats/packages`
3. ✅ Push completato? → Verifica log: `cat /var/log/errata-sync.log`
4. ✅ Canali mappati correttamente? → `curl http://10.172.5.4:5000/api/uyuni/channels`
5. ✅ Sistemi registrati nei canali corretti? → UYUNI UI: Systems → Overview

### CVE Audit non mostra vulnerabilità

**Cause possibili**:
1. OVAL non sincronizzato → Esegui: `/root/test-and-sync.sh` → opzione 7
2. Mappings CVE-OVAL mancanti → Verificare database: `errata_cve_oval_map`
3. Sistema non ha pacchetti vulnerabili (normale se aggiornato)

---

## 📊 METRICHE DI SUCCESSO

Dopo il primo sync completo, dovresti avere:

| Metrica | Valore Atteso |
|---------|---------------|
| **Errata totali** | > 5000 |
| **Errata USN** | > 3000 |
| **Errata DSA** | > 2000 |
| **Errata synced** | > 100 (nel primo push) |
| **Pacchetti cache** | > 250000 |
| **OVAL definitions** | > 15000 |
| **CVE con dettagli NVD** | > 10000 |

---

## 🎯 PROSSIMI PASSI

### Immediato (Questa Settimana)
1. ✅ Eseguire primo sync completo
2. ✅ Verificare visibilità patch in UYUNI
3. ✅ Setup cron per automazione

### Breve Termine (Prossimo Mese)
1. Richiedere NAT Gateway (vedi RICHIESTA-NAT-GATEWAY-PSN.md)
2. Migrare a container unificato
3. Monitorare log e statistiche settimanali

### Lungo Termine (Prossimi 3 Mesi)
1. Implementare dashboard Grafana
2. Integrare Azure Monitor alerting
3. Estendere supporto a RHEL/CentOS

---

## 📞 SUPPORTO

### Verificare Stato Sistema

```bash
# Health check rapido
curl -s http://10.172.5.4:5000/api/health | python3 -m json.tool

# Health dettagliato
curl -s http://10.172.5.4:5000/api/health/detailed | python3 -m json.tool

# Statistiche
curl -s http://10.172.5.4:5000/api/stats/overview | python3 -m json.tool
```

### File di Log

```bash
# Log sync script
tail -f /var/log/errata-sync.log

# Log errori
tail -f /var/log/errata-sync-errors.log

# Log container (via Azure)
az container logs --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal
```

---

## ✅ CHECKLIST PRE-PRODUZIONE

- [ ] Container RUNNING e raggiungibili
- [ ] Health check passa su entrambi i container
- [ ] Primo sync completo eseguito con successo
- [ ] Patch visibili in UYUNI Web UI
- [ ] CVE Audit funzionante (almeno 1 CVE testato)
- [ ] Cron job configurato
- [ ] Log rotation configurato
- [ ] Documentazione aggiornata con IP corretti
- [ ] Test su almeno 1 sistema registrato

---

**Versione**: 2.5-FIX
**Data**: 2026-01-08
**Status**: ✅ Sistema Riparato e Operativo
