# 🚀 QUICK REFERENCE - Deployment OVAL Fix

## 📦 ESECUZIONE SCRIPT

### Opzione 1: Automatico (Recupera DB URL da container esistente)

```bash
./deploy-oval-fix.sh
```

Lo script tenterà di recuperare il DATABASE_URL dal container esistente. Se non lo trova, te lo chiederà interattivamente.

---

### Opzione 2: Con DATABASE_URL Specificato

```bash
./deploy-oval-fix.sh "postgresql://errataadmin:ErrataSecure2024@pg-errata-test.postgres.database.azure.com:5432/uyuni_errata?sslmode=require"
```

Fornisci il DATABASE_URL come primo parametro.

---

### Opzione 3: Interattivo (Se non trovato)

Se il DATABASE_URL non è trovato e non è fornito, lo script chiederà:

```
[WARN] Could not retrieve DATABASE_URL from existing container
[INFO]
[INFO] Please provide DATABASE_URL manually.
[INFO] Format: postgresql://user:password@host:port/database?sslmode=require
[INFO]
DATABASE_URL: _
```

---

## ⏱️ TIMELINE

| Fase | Tempo | Cosa Succede |
|------|-------|--------------|
| **Build immagine** | 10-15 min | Build su Azure ACR |
| **Backup** | 30 sec | Export config container |
| **Delete old** | 30 sec | Rimozione container vecchio |
| **Deploy new** | 2-3 min | Deploy nuovo container |
| **Health check** | 1-2 min | Verifica funzionamento |
| **OVAL sync (opzionale)** | 30-50 min | Test sync completo |

**Totale minimo**: ~15-20 minuti (senza test OVAL)
**Totale completo**: ~45-70 minuti (con test OVAL)

---

## 📋 CHECKLIST PRE-DEPLOYMENT

- [ ] Sei nella directory corretta (`Initial-Setup`)
- [ ] Hai accesso ad Azure CLI (`az login`)
- [ ] File esistono: `Dockerfile.api-timeout-fix`, `app-v2.5-IMPROVED.py`
- [ ] Hai il DATABASE_URL (o sai dove trovarlo)
- [ ] Hai tempo (20-30 minuti minimo)

---

## 🎯 COSA ASPETTARSI

### Durante Build Immagine (10-15 min)

```
[INFO] Starting Azure Container Registry build...
[INFO] Image: acaborerrata.azurecr.io/errata-api:v2.5-oval-fixed
[WARN] This will take 10-15 minutes...

Step 1/10 : FROM python:3.11-slim-bookworm
Step 2/10 : RUN apt-get update...
...
[SUCCESS] Image built successfully!
```

### Durante Deploy (2-3 min)

```
[INFO] Deploying container with new image...
[INFO] Image: acaborerrata.azurecr.io/errata-api:v2.5-oval-fixed

[SUCCESS] Container deployed successfully!
[SUCCESS] Container started with IP: 4.232.X.X
```

### Durante Health Check (1-2 min)

```
[INFO] Health check attempt 1/12...
[SUCCESS] Container is healthy!
{
    "api": "ok",
    "database": "ok",
    "uyuni": "not configured",
    "version": "2.5"
}
```

### Durante OVAL Sync (30-50 min) - Opzionale

```
[WARN] Starting OVAL sync test...
[INFO] Starting OVAL sync for platform=all...
[INFO] Monitor in another terminal with:
[INFO]   az container logs --resource-group test_group --name aci-errata-api --follow

[SUCCESS] OVAL sync completed!
{
    "status": "success",
    "total_processed": 15234,
    "results": {
        "ubuntu-noble": 808,
        "ubuntu-jammy": 1902,
        "ubuntu-focal": 7123,
        "debian-bookworm": 2401,
        "debian-bullseye": 3000
    }
}
```

---

## 🆘 SE QUALCOSA VA STORTO

### Build Fallisce

```bash
# Verifica connessione Azure
az account show

# Verifica ACR esiste
az acr show --name acaborerrata

# Verifica file
ls -la Dockerfile.api-timeout-fix app-v2.5-IMPROVED.py
```

### Deploy Fallisce

```bash
# Verifica log dello script
# Lo script stampa tutto in output

# Verifica che il vecchio container sia stato eliminato
az container list --output table | grep errata
```

### Health Check Fallisce

```bash
# Verifica log container
az container logs --resource-group test_group --name aci-errata-api

# Verifica stato container
az container show \
  --resource-group test_group \
  --name aci-errata-api \
  --query "instanceView.state"
```

### OVAL Sync Fallisce Ancora

```bash
# Verifica timeout nel container
az container logs --resource-group test_group --name aci-errata-api | grep -i timeout

# Se ancora timeout, aumenta timeout a 3600 (1 ora)
# Modifica Dockerfile.api-timeout-fix: --timeout 3600
```

---

## ✅ DOPO IL DEPLOYMENT

### 1. Verifica Nuovo IP

```bash
NEW_IP=$(az container show \
  --resource-group test_group \
  --name aci-errata-api \
  --query "ipAddress.ip" \
  -o tsv)

echo "New IP: $NEW_IP"
```

### 2. Aggiorna Script

```bash
# Se IP è cambiato
sed -i "s|PUBLIC_API=.*|PUBLIC_API=\"http://$NEW_IP:5000\"|g" remote-sync.sh
sed -i "s|PUBLIC_API=.*|PUBLIC_API=\"http://$NEW_IP:5000\"|g" errata-sync-v2.5-IMPROVED.sh
```

### 3. Test Sync Completo

```bash
# Sync esterni (dal tuo PC)
./remote-sync.sh full

# Sync interni (dal server UYUNI)
ssh root@10.172.2.5 '/root/uyuni-server-sync.sh quick'
```

### 4. Verifica in UYUNI

- **Web UI**: `Patches → Patch List`
- **CVE Audit**: `Audit → CVE Audit`

---

## 📝 NOTE IMPORTANTI

1. **Backup Automatico**: Lo script crea backup in `aci-errata-api-backup-YYYYMMDD-HHMMSS.yaml`

2. **IP Dinamico**: L'IP può cambiare dopo redeploy (normale per ACI pubblici)

3. **Downtime**: 2-3 minuti durante redeploy (solo container pubblico)

4. **Container Interno**: NON viene toccato, continua a funzionare

5. **Rollback**: Se qualcosa va storto, usa il backup per ripristinare

---

## 🎯 COMANDI RAPIDI

```bash
# Avvia deployment
./deploy-oval-fix.sh

# Avvia con DATABASE_URL custom
./deploy-oval-fix.sh "postgresql://..."

# Monitora log in tempo reale
az container logs --resource-group test_group --name aci-errata-api --follow

# Verifica health
curl -s http://$(az container show --resource-group test_group --name aci-errata-api --query "ipAddress.ip" -o tsv):5000/api/health

# Test OVAL sync
curl -m 3600 -X POST "http://$(az container show --resource-group test_group --name aci-errata-api --query "ipAddress.ip" -o tsv):5000/api/sync/oval?platform=all"
```

---

**Ready to go!** 🚀

Esegui: `./deploy-oval-fix.sh`
