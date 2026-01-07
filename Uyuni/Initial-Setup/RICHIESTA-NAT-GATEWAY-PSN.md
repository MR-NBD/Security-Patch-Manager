# Richiesta Eccezione Policy Azure - NAT Gateway per Errata Manager

## Dati Richiesta

**Data**: 2026-01-07
**Richiedente**: [Tuo Nome/Team]
**Progetto**: Security Patch Management - UYUNI Errata Manager
**Subscription**: ASL0603-spoke10
**Resource Group**: ASL0603-spoke10-rg-spoke-italynorth

---

## 1. Oggetto della Richiesta

**Richiesta di eccezione alla policy PSN per creazione Azure NAT Gateway** nella subnet `errata-aci-subnet` (10.172.5.0/28) al fine di consentire accesso Internet in uscita per i container Azure Container Instance del servizio UYUNI Errata Manager.

---

## 2. Contesto e Motivazione

### 2.1 Problema Attuale

Il sistema UYUNI Errata Manager è un componente critico per la gestione automatizzata delle patch di sicurezza su sistemi Linux (Ubuntu/Debian) in ambiente Azure PSN.

Attualmente, l'architettura prevede **2 container separati** a causa del vincolo di rete PSN:

```
┌─────────────────────────────────────────────────────────────────┐
│ ARCHITETTURA ATTUALE (Non Ottimale)                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Container Pubblico (RG: test_group)                            │
│  IP: 4.232.4.142 (Public IP)                                    │
│  Funzione: Sync errata da Internet                              │
│  ├─ Ubuntu Security Notices (USN)                               │
│  ├─ Debian Security Advisories (DSA)                            │
│  ├─ National Vulnerability Database (NVD)                       │
│  └─ OVAL Definitions                                            │
│                  │                                               │
│                  ▼                                               │
│        PostgreSQL (Private Endpoint)                            │
│                  ▲                                               │
│                  │                                               │
│  Container Interno (VNet PSN)                                   │
│  IP: 10.172.5.4 (Private)                                       │
│  Funzione: Push a UYUNI                                         │
│  └─ Accesso UYUNI Server (10.172.2.5)                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Problemi di questa architettura**:
- ❌ Doppia infrastruttura (2 container + 2 ACR images)
- ❌ Sincronizzazione manuale tra container
- ❌ Complessità operativa e manutenzione
- ❌ Doppio punto di failure
- ❌ Costi aumentati (doppio container ACI)
- ❌ Difficoltà troubleshooting e monitoring

### 2.2 Soluzione Proposta

**Unificazione in un singolo container** nella VNet PSN con accesso Internet in uscita tramite Azure NAT Gateway:

```
┌─────────────────────────────────────────────────────────────────┐
│ ARCHITETTURA PROPOSTA (Ottimale)                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Container Unificato (VNet PSN + NAT Gateway)                   │
│  IP Privato: 10.172.5.4                                         │
│  IP Uscita: [NAT Gateway Public IP - statico]                  │
│                                                                  │
│  Funzioni:                                                       │
│  ├─ Sync da Internet (USN, DSA, NVD, OVAL)                     │
│  └─ Push a UYUNI Server (10.172.2.5)                           │
│                                                                  │
│         ┌──────────────┐              ┌──────────────┐          │
│         │  Internet    │              │ UYUNI Server │          │
│         │  (outbound)  │              │  (internal)  │          │
│         └──────┬───────┘              └───────▲──────┘          │
│                │                              │                  │
│         NAT Gateway                     VNet routing            │
│                │                              │                  │
│                └──────────┬───────────────────┘                 │
│                           │                                      │
│                  Errata Manager Container                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Benefici**:
- ✅ Singolo container, singola image
- ✅ Logica unificata e semplificata
- ✅ Riduzione costi (eliminazione container pubblico)
- ✅ Monitoring centralizzato
- ✅ Manutenzione semplificata
- ✅ Riduzione superficie di attacco (no public IP su container)

---

## 3. Dettagli Tecnici della Richiesta

### 3.1 Risorsa da Creare

| Parametro             | Valore                                |
| --------------------- | ------------------------------------- |
| **Risorsa**           | Azure NAT Gateway                     |
| **Nome**              | `natgw-errata-manager-spoke10`        |
| **Resource Group**    | `ASL0603-spoke10-rg-spoke-italynorth` |
| **Region**            | Italy North                           |
| **SKU**               | Standard                              |
| **Availability Zone** | Zone 1 (allineato con VM UYUNI)       |
| **Public IP**         | `pip-natgw-errata-spoke10` (statico)  |
| **Subnet associata**  | `errata-aci-subnet` (10.172.5.0/28)   |

### 3.2 Traffico in Uscita Richiesto

| Destinazione | Protocollo | Porte | Frequenza | Giustificazione |
|--------------|------------|-------|-----------|-----------------|
| `ubuntu.com` | HTTPS | 443 | Settimanale | Download Ubuntu Security Notices (USN) |
| `security.ubuntu.com` | HTTPS | 443 | Settimanale | Download aggiornamenti sicurezza Ubuntu |
| `security-tracker.debian.org` | HTTPS | 443 | Settimanale | Download Debian Security Advisories (DSA) |
| `services.nvd.nist.gov` | HTTPS | 443 | Giornaliero | Enrichment CVSS scores da NVD |
| `security-metadata.canonical.com` | HTTPS | 443 | Settimanale | Download OVAL definitions Ubuntu |
| `www.debian.org` | HTTPS | 443 | Settimanale | Download OVAL definitions Debian |

**Nota**: Tutto il traffico è **outbound HTTPS (443) only**, nessuna connessione inbound richiesta.

### 3.3 Whitelist IP Consigliata (Opzionale)

Se richiesta granularità aggiuntiva per controllo policy:

```
# Ubuntu/Canonical (AS2635)
91.189.88.0/21
91.189.89.0/24
91.189.91.0/24

# Debian
debian.org (DNS-based, IP dinamici)

# NVD NIST
services.nvd.nist.gov (DNS-based)
```

**Raccomandazione**: Utilizzo di Azure Firewall Application Rules con FQDN filtering per controllo granulare.

---

## 4. Analisi Rischi e Mitigazioni

### 4.1 Rischi Identificati

| Rischio | Probabilità | Impatto | Mitigazione |
|---------|-------------|---------|-------------|
| Accesso non autorizzato verso Internet | Bassa | Medio | - NSG restrittivo (allow only 443 outbound)<br>- Container con least privilege<br>- No shell access dal container |
| Exfiltrazione dati | Molto Bassa | Alto | - Traffico limitato a domini whitelisted<br>- Azure Firewall con FQDN rules<br>- Monitoring traffico con Network Watcher |
| Compromissione container | Bassa | Medio | - Image scanning con ACR<br>- Read-only filesystem<br>- No secret in environment variables (use Azure Key Vault) |

### 4.2 Mitigazioni Implementate

1. **Network Security Group (NSG)** restrittivo:
   ```
   Priority 100: Allow HTTPS (443) outbound to Internet
   Priority 200: Allow 5432 to PostgreSQL Private Endpoint (10.172.2.6)
   Priority 300: Allow 443,4505,4506 to UYUNI (10.172.2.5)
   Priority 4096: Deny all other outbound
   ```

2. **Container Hardening**:
   - Non-root user (UID 1000)
   - Read-only root filesystem
   - No capabilities (CAP_DROP all)
   - Secrets via Azure Key Vault integration

3. **Monitoring**:
   - NSG Flow Logs abilitati
   - Azure Monitor Container Insights
   - Alert su connessioni anomale

4. **Principio Least Privilege**:
   - Managed Identity per accesso PostgreSQL (no password)
   - RBAC su Key Vault per secret retrieval

---

## 5. Impatto su Compliance e Security

### 5.1 Allineamento con Standard PSN

La soluzione proposta **migliora** il posture di sicurezza rispetto all'architettura attuale:

| Aspetto | Situazione Attuale | Con NAT Gateway | Impatto |
|---------|-------------------|-----------------|---------|
| **Public IP exposure** | Container pubblico con IP esposto | Nessun public IP su container | ✅ Migliorato |
| **Attack surface** | 2 container, 2 endpoint HTTP pubblici | 1 container privato | ✅ Ridotto |
| **Network segmentation** | Container pubblico fuori VNet | Tutto in VNet con routing controllato | ✅ Migliorato |
| **Auditability** | Log dispersi su 2 container | Log centralizzati | ✅ Migliorato |
| **Secret management** | Environment variables | Azure Key Vault | ✅ Migliorato |

### 5.2 Controlli di Sicurezza Aggiuntivi

- **Azure Firewall** (opzionale): Se richiesto, possiamo aggiungere Azure Firewall davanti al NAT Gateway per:
  - Application-level filtering (Layer 7)
  - Threat intelligence integration
  - Full packet inspection

- **Azure DDoS Protection Standard**: Protezione sul Public IP del NAT Gateway

---

## 6. Costi Stimati

### Confronto Costi Mensili

| Componente | Architettura Attuale | Architettura con NAT Gateway | Differenza |
|------------|---------------------|------------------------------|------------|
| ACI Container Pubblico | €35 | €0 | -€35 |
| ACI Container Interno | €35 | €35 | €0 |
| NAT Gateway (Standard) | €0 | €33 | +€33 |
| Public IP (statico) | €0 | €3 | +€3 |
| **TOTALE** | **€70** | **€71** | **+€1/mese** |

**Conclusione**: Costo equivalente con architettura significativamente migliore.

---

## 7. Piano di Implementazione

### Fase 1: Setup NAT Gateway (1 giorno)
```bash
# 1. Crea Public IP
az network public-ip create \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name pip-natgw-errata-spoke10 \
  --sku Standard \
  --allocation-method Static \
  --zone 1

# 2. Crea NAT Gateway
az network nat gateway create \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --name natgw-errata-manager-spoke10 \
  --public-ip-addresses pip-natgw-errata-spoke10 \
  --idle-timeout 10 \
  --zone 1

# 3. Associa alla subnet
az network vnet subnet update \
  --resource-group ASL0603-spoke10-rg-spoke-italynorth \
  --vnet-name ASL0603-spoke10-spoke-italynorth \
  --name errata-aci-subnet \
  --nat-gateway natgw-errata-manager-spoke10
```

### Fase 2: Refactoring Applicazione (2 giorni)
- Merge codice dei 2 container in uno
- Rimozione logiche di sincronizzazione inter-container
- Aggiornamento configurazione database
- Testing connettività Internet + UYUNI

### Fase 3: Deployment e Validazione (1 giorno)
- Build nuova immagine unificata
- Deploy container in VNet con NAT Gateway
- Smoke test sync USN/DSA/NVD
- Validazione push a UYUNI
- Monitoraggio 24h

### Fase 4: Dismissione Infrastruttura Vecchia (1 giorno)
- Backup configurazione
- Eliminazione container pubblico
- Pulizia Resource Group `test_group` (se non più necessario)

**Tempo totale stimato**: 5 giorni lavorativi

---

## 8. Rollback Plan

In caso di problemi durante la migrazione:

1. **Mantenimento architettura esistente** funzionante durante test
2. **Rollback immediato**: Eliminazione NAT Gateway, ritorno ai 2 container
3. **Tempo di rollback**: < 30 minuti
4. **Nessuna perdita dati**: PostgreSQL condiviso tra le architetture

---

## 9. Documentazione e Supporto

### Riferimenti Tecnici
- [Azure NAT Gateway Documentation](https://learn.microsoft.com/en-us/azure/nat-gateway/)
- [Azure Container Instances VNet Integration](https://learn.microsoft.com/en-us/azure/container-instances/container-instances-vnet)
- [UYUNI Errata Manager - Documentazione Progetto](../UYUNI-ERRATA-MANAGER-v2.4-GUIDA-COMPLETA.md)

### Contatti
- **Team**: Security Patch Management
- **Responsabile Tecnico**: [Nome]
- **Email**: [email]

---

## 10. Richiesta di Approvazione

Si richiede l'approvazione per:

1. ✅ **Creazione Azure NAT Gateway** nella subscription ASL0603-spoke10
2. ✅ **Eccezione policy** "Subnets must have PSN Route Table" per subnet `errata-aci-subnet` (o configurazione route table compatibile con NAT Gateway)
3. ✅ **Associazione NAT Gateway** alla subnet `errata-aci-subnet` (10.172.5.0/28)
4. ✅ **Whitelist traffico HTTPS (443) outbound** verso domini elencati nella sezione 3.2

### Firme di Approvazione

| Ruolo | Nome | Data | Firma |
|-------|------|------|-------|
| Richiedente | | | |
| Responsabile Infrastruttura | | | |
| Security Officer | | | |
| Cloud Architect PSN | | | |

---

**Nota**: Questa richiesta è motivata da esigenze di **security hardening**, **riduzione complessità operativa** e **allineamento best practices cloud-native**, mantenendo piena compliance con i requisiti PSN.
