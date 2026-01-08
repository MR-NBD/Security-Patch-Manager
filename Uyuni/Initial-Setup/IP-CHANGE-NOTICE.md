# ⚠️ IP CONTAINER CAMBIATO - 08/01/2026

## 🔄 Cambio IP Rilevato

Durante il riavvio dei container, l'IP del **container interno è cambiato**:

| Container | IP Vecchio | IP Nuovo | Stato |
|-----------|------------|----------|-------|
| **Container Interno** | ~~10.172.5.4~~ | **10.172.5.5** | ✅ Running |
| **Container Pubblico** | 4.232.3.251 | 4.232.3.251 | ✅ Running |

---

## ✅ Script Aggiornati

Tutti gli script sono stati aggiornati con il nuovo IP:

- ✅ `test-and-sync.sh`
- ✅ `errata-sync-v2.5-IMPROVED.sh`
- ✅ `GUIDA-OPERATIVA-FIX.md`
- ✅ `README-FIX-08-01-2026.md`
- ✅ `DEPLOYMENT-GUIDE-v2.5.md`

---

## 🚀 Cosa Fare Ora

### 1. Verifica IP Correnti (Opzionale)

```bash
# Esegui lo script di verifica
./check-containers.sh
```

Questo script:
- ✅ Verifica stato container in Azure
- ✅ Mostra IP correnti
- ✅ Controlla se gli script sono aggiornati
- ✅ Offre di aggiornarli automaticamente se necessario

### 2. Copia Script Aggiornati sul Server UYUNI

```bash
cd /mnt/c/Users/alber/Documents/GitHub/Security-Patch-Manager/Uyuni/Initial-Setup

# Copia gli script con IP corretti
scp test-and-sync.sh root@10.172.2.5:/root/
scp errata-sync-v2.5-IMPROVED.sh root@10.172.2.5:/root/errata-sync.sh
scp QUICK-START.sh root@10.172.2.5:/root/
scp GUIDA-OPERATIVA-FIX.md root@10.172.2.5:/root/
```

### 3. Test Connettività dal Server UYUNI

```bash
# SSH nel server UYUNI
ssh root@10.172.2.5

# Test connettività
chmod +x /root/test-and-sync.sh
/root/test-and-sync.sh test
```

**Output atteso**:
```
[SUCCESS] Public Container is reachable and healthy
[SUCCESS] Internal Container is reachable and healthy
[SUCCESS] Both containers are healthy!
```

### 4. Esegui Sync Completo

```bash
# Se il test passa, esegui sync completo
/root/test-and-sync.sh full
```

---

## 🔍 Perché l'IP È Cambiato?

**Causa**: Azure Container Instances nella VNET privata ottengono IP dinamici.

Quando un container viene riavviato/ricreato, Azure può assegnare un nuovo IP dalla subnet.

---

## 💡 Soluzione Permanente

### Opzione 1: IP Statico (Limitato)
Azure ACI non supporta IP statici nella VNET, ma puoi:
- Usare Azure Private DNS per hostname fisso
- Implementare service discovery

### Opzione 2: Migrare ad AKS
Per IP stabili e produzione:
- Azure Kubernetes Service con LoadBalancer interno
- IP fissi gestiti da Kubernetes

### Opzione 3: Riservare IP (Non supportato per ACI in VNET)
Attualmente non disponibile per ACI in VNET private.

---

## 📝 Note Importanti

1. **Verifica IP prima di ogni operazione critica**
   ```bash
   ./check-containers.sh
   ```

2. **Se i container crashano**, potrebbero ottenere nuovo IP al riavvio

3. **Gli script ora sono variabili d'ambiente**:
   ```bash
   PUBLIC_API="http://4.232.3.251:5000" INTERNAL_API="http://10.172.5.5:5000" /root/test-and-sync.sh test
   ```

4. **Monitorare restart dei container**:
   ```bash
   az container show --resource-group ASL0603-spoke10-rg-spoke-italynorth \
     --name aci-errata-api-internal \
     --query "instanceView.currentState.restartCount"
   ```

---

## ✅ Checklist Post-Update

- [x] IP aggiornati negli script
- [x] Script testati localmente
- [ ] Script copiati su server UYUNI (10.172.2.5)
- [ ] Test connettività dal server UYUNI
- [ ] Sync completo eseguito con successo
- [ ] Patch visibili in UYUNI Web UI

---

## 🆘 Se Hai Problemi

### Container non raggiungibili anche con IP corretto

```bash
# Verifica log del container
az container logs --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal

# Riavvia container
az container restart --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name aci-errata-api-internal

# Verifica nuovo IP dopo restart
./check-containers.sh
```

### Script hanno ancora IP vecchi

```bash
# Usa lo script automatico
./check-containers.sh

# Oppure aggiorna manualmente
sed -i 's|10.172.5.4|10.172.5.5|g' test-and-sync.sh
sed -i 's|10.172.5.4|10.172.5.5|g' errata-sync-v2.5-IMPROVED.sh
```

---

**Data**: 2026-01-08
**Status**: ✅ IP Aggiornati in Tutti gli Script
**Azione Richiesta**: Copia script aggiornati su server UYUNI ed esegui test
