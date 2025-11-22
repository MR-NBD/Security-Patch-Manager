# Automated Patch Management for B2B IaaS Environments
## 📌 Overview

Questo progetto propone un modello preliminare di **Security Patch Management (SPM)** pensato per ambienti **B2B multi-tenant** in ambito **Infrastructure-as-a-Service (IaaS)**.  
L’obiettivo è definire un processo centralizzato, automatizzato e sicuro per la gestione delle patch, ponendo le basi per una futura architettura completa.

La soluzione è progettata con riferimento al contesto del **Polo Strategico Nazionale (PSN)** e integra standard internazionali come **IEC/ISO 62443**, **ISO/IEC 27002**, **NIST SP 800-40**, e **NERC CIP-007**.

---
## 🎯 Project Goals
![img](./img/PSN_work_flow_v2.png)
- Creare una **visione unificata e aggiornata** di tutte le risorse gestite (VM, sistemi operativi, patch installate o mancanti).
- Definire un sistema che identifichi automaticamente patch di sicurezza, le classifichi e ne valuti l’impatto.
- Minimizzare gli effetti sui sistemi di produzione, rispettando il principio di **zero downtime** e le esigenze dei tenant.
- Strutturare un processo scalabile e automatizzabile, per supportare ambienti **eterogenei e multi-cloud**.

---
## 🏗️ High-Level Architecture

Il modello introduce due componenti principali:
![img](./img/HLD_SPM_v2.png)
### **Master Server**

- Repository centrale per inventario, vulnerabilità, politiche e monitoraggio.
- Responsabile del download e aggiornamento della **National Vulnerability Database (NVD)**.
- Gestisce la comunicazione sicura con i Proxy e la segregazione dei tenant.

### **Proxy Server (Smart Proxy)**

- Installato nei tenant, esegue discovery, analisi, test e deployment in locale.
- Coordina l’intero ciclo di patching senza esporre sistemi di produzione al Master Server.
- Garantisce isolamento, sicurezza e coerenza.

---
## 🔄 Patch Management Workflow

### **P1 — [Active Environment Discovery](./workflow/Active_Environment_Discovery-SPM.drawio)**
### **P2 — [Security Discovery & Prioritization](./workflow/Security_Patch_Discovery_&_Prioritization.drawio)**

Due modalità operative:
- **Security Mode** — priorità basate esclusivamente sul rischio.
- **Smart Mode** — valutazione combinata di rischio, dipendenze, stabilità e impatto operativo.
### **P3 — [Patch Testing](./workflow/PATCHTESTING_VALIDATION.drawio)**
### **P4 — [Patch Deployment](./workflow/PATCH_INSTALLATION_ENGINE.drawio)**

### **(Opzionale) P5 — Post-Deployment Assessment**

---
## 🔐 Utenze

- 🔑 [ASL0603](./Utenze/ASL0603.md)

---
## 🔬 LAB
In questo momento il laboratorio si concentrando sull'utilizzo di Foreman+Katello+Puppet
[DOC](https://theforeman.org/)
![img](./img/2025-11-22-15_54_42-.png)
- SETUP [CREATE VM](./Setting/CreateVM.md) [INSTALLATION](./Setting/Installation.md)
- GUIDE 
- CONFIGURAZIONI

---
## 📝Documetazione prodotta
- [Automated Patch Management for B2B IaaS Environments](./Documentation/Automated_Patch_Management_for_B2B_IaaS_Environments_v1.1.pdf)
## 📝Relevant documents
- [RED HAT SATELLITE CRON-BASED PATCHING A ZERO-TOUCH APPROACH](./Documentation/Ext_Doc/RED_HAT_SATELLITE_CRON-BASED_PATCHING_A_ZERO-TOUCH_APPROACH.pdf)
- [Smart Patching with Cron Jobs An Ops-Centric](./Documentation/Ext_Doc/Smart_Patching_with_Cron_Jobs_An_Ops-Centric.pdf)
- [The Recent AutomatingSystem Patching Via Satellite](./Documentation/Ext_Doc/The_Recent_AutomatingSystem_Patching_Via_Satellite.pdf)

---
## 👤 Author

**Alberto Ameglio**  
