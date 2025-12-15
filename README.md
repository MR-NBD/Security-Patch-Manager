# Automated Patch Management for B2B IaaS Environments
## Overview

Questo progetto propone un modello preliminare di **Security Patch Management (SPM)** pensato per ambienti **B2B multi-tenant** in ambito **Infrastructure-as-a-Service (IaaS)**.  
L’obiettivo è definire un processo centralizzato, automatizzato e sicuro per la gestione delle patch, ponendo le basi per una futura architettura completa.

La soluzione è progettata con riferimento al contesto del **Polo Strategico Nazionale (PSN)** e integra standard internazionali come **IEC/ISO 62443**, **ISO/IEC 27002**, **NIST SP 800-40**, e **NERC CIP-007**.

---
## Project Goals
![img](./img/PSN_work_flow_v2.png)
- Creare una **visione unificata e aggiornata** di tutte le risorse gestite (VM, sistemi operativi, patch installate o mancanti).
- Definire un sistema che identifichi automaticamente patch di sicurezza, le classifichi e ne valuti l’impatto.
- Minimizzare gli effetti sui sistemi di produzione, rispettando il principio di **zero downtime** e le esigenze dei tenant.
- Strutturare un processo scalabile e automatizzabile, per supportare ambienti **eterogenei e multi-cloud**.

---
## High-Level Architecture

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
## Patch Management Workflow

### **P1 → [Active Environment Discovery](./workflow/Active_Environment_Discovery-SPM.drawio)**
### **P2 → [Security Discovery & Prioritization](./workflow/Security_Patch_Discovery_&_Prioritization.drawio)**

Due modalità operative:
- **Security Mode** — priorità basate esclusivamente sul rischio.
- **Smart Mode** — valutazione combinata di rischio, dipendenze, stabilità e impatto operativo.
### **P3 → [Patch Testing](./workflow/PATCH_TESTING_VALIDATION.drawio)**
### **P4 →[Patch Deployment](./workflow/PATCH_INSTALLATION_ENGINE.drawio)**

### **(Opzionale) P5 → Post-Deployment Assessment**

---
## Utenze

- [ASL0603](./Utenze/ASL0603.md)

---
## LAB
Ecco una prima analisi riassuntiva degli strumenti inizialmente proposti nel [documento](./GeneralDocumentation/Automated_Patch_Management_for_B2B_IaaS_Environments_v1.1.pdf). → [TABELLA](./GeneralDocumentation/Tabella_Comparativa.md)
In questo primo momento di test il laboratorio si concentra sull'utilizzo di Foreman+Katello
[DOC](https://theforeman.org/)
![img](./img/ForemanLOGO.png)
- INSTALLAZIONE E CONFIGURAZIONE con HOST UBUNTU -  [GUIDA](./Foreman-Katello/Initial-Setup/Installazione.md)
- GUIDE 
	- [Configurazione Organization e Location](./Foreman-Katello/Configurazione-Tutorial/Configurazione-Organization-e-Location.md)
	- [Configurazione Content Credentials (Chiavi GPG)](./Foreman-Katello/Configurazione-Tutorial/Configurazione-Content-Credentials.md)
	- [Creazione Product e Repository Ubuntu 24.04](./Foreman-Katello/Configurazione-Tutorial/Creazione-Product-Repository-Ubuntu-24.04.md)
	- [Lifecycle Environments](./Foreman-Katello/Configurazione-Tutorial/Lifecycle-Environments.md)
	- [Content View](./Foreman-Katello/Configurazione-Tutorial/Content-View.md)
	- [Operating System](./Foreman-Katello/Configurazione-Tutorial/Operating-System.md)
	- [Host Group](./Foreman-Katello/Configurazione-Tutorial/Host-Group.md)
	- [Activation Key](./Foreman-Katello/Configurazione-Tutorial/Activation-Key.md)
	- [Guida Registrazione Host Ubuntu 24.04](./Foreman-Katello/Configurazione-Tutorial/Guida-Registrazione-Host-Ubuntu-24.04.md)
	- [Errata-Management-Ubuntu-Debian](./Foreman-Katello/Configurazione-Tutorial/Errata-Management-Ubuntu-Debian.md)
	- [Guida-Upload-Incrementale-Pacchetti](./Foreman-Katello/Configurazione-Tutorial/Guida-Upload-Incrementale-Pacchetti.md)

---
## Documetazione prodotta
- [Automated Patch Management for B2B IaaS Environments](Automated_Patch_Management_for_B2B_IaaS_Environments_v1.1.pdf)
- [Capitoli Tesi Provvisori](CAPITOLI_TESI.md)
- [Tabella Comparativa tool](Tabella_Comparativa.md)
## Relevant documents
- [RED HAT SATELLITE CRON-BASED PATCHING A ZERO-TOUCH APPROACH](RED_HAT_SATELLITE_CRON-BASED_PATCHING_A_ZERO-TOUCH_APPROACH.pdf)
- [Smart Patching with Cron Jobs An Ops-Centric](Smart_Patching_with_Cron_Jobs_An_Ops-Centric.pdf)
- [The Recent AutomatingSystem Patching Via Satellite](The_Recent_AutomatingSystem_Patching_Via_Satellite.pdf)

---
## Author

**Alberto Ameglio**  
