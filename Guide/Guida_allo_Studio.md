## 1. Introduzione
Foreman è una piattaforma open source per il provisioning e la gestione del ciclo di vita dei server fisici e virtuali. **Katello** è un plugin di Foreman che aggiunge funzionalità avanzate di content management, subscription management e lifecycle management. Insieme formano una soluzione enterprise completa per la gestione centralizzata di infrastrutture multi-OS.
## 2. GPG Key (Chiave GPG)
Una GPG Key (GNU Privacy Guard Key) è una chiave crittografica utilizzata per verificare l'autenticità e l'integrità dei pacchetti software. Ogni repository ufficiale di una distribuzione Linux pubblica una chiave GPG pubblica che viene usata per firmare digitalmente tutti i pacchetti distribuiti.
### 2.2 Perché serve?
- **Sicurezza:** Garantisce che i pacchetti provengano effettivamente dal fornitore ufficiale e non siano stati modificati da terzi malintenzionati
- **Integrità:** Verifica che il pacchetto non sia stato corrotto durante il download
- **Trust Chain:** Stabilisce una catena di fiducia tra il repository e i sistemi client
- **Compliance:** Requisito fondamentale per ambienti enterprise e normative di sicurezza
### 2.3 Come funziona in Katello?
In Katello, le GPG Key vengono importate e associate ai Product o ai singoli Repository. Il processo è:
1.     Scaricare la chiave GPG pubblica dal sito ufficiale della distribuzione
2.     Importare la chiave in Katello tramite Content → Content Credentials
3.     Associare la chiave al Product o Repository corrispondente
4.     Durante la sincronizzazione, Katello verifica automaticamente la firma di ogni pacchetto

> **💡** **Nota Pratica:** Per Ubuntu, la chiave GPG si trova tipicamente su keyserver.ubuntu.com o nel file /usr/share/keyrings/. Per sistemi RHEL-like, usa rpm --import per importare le chiavi GPG.

## 3. Product
### 3.1 Cos'è?
Un Product in Katello è un contenitore logico che raggruppa uno o più Repository correlati. Rappresenta tipicamente un software vendor o una distribuzione specifica (es. 'Ubuntu 24.04', 'RHEL 9', 'PostgreSQL').
### 3.2 Perché serve?
- **Organizzazione:** Raggruppa repository logicamente correlati per una gestione più semplice
- **Sincronizzazione:** Permette di sincronizzare tutti i repository di un product con un'unica operazione
- **GPG Key inheritance:** La chiave GPG associata al Product viene ereditata da tutti i suoi repository
- **Multi-tenancy:** Ogni Product appartiene a un'Organization specifica
### 3.3 Struttura gerarchica per Foreman
La gerarchia in Katello è: Organization → Product → Repository → Content

|**Product**|**Repository**|**Tipo Contenuto**|
|---|---|---|
|Ubuntu 24.04|ubuntu-noble-main|deb packages|
|Ubuntu 24.04|ubuntu-noble-security|deb packages|
|RHEL 9|rhel9-baseos|rpm packages|
## 4. Content (Contenuto)
### 4.1 Cos'è?
Content rappresenta i dati effettivi gestiti da Katello: pacchetti software (RPM, DEB), errata, moduli, container images, file ISO, e altri artefatti. Il contenuto viene scaricato (sincronizzato) dai repository esterni e memorizzato localmente nel Pulp content store.
### 4.2 Tipi di Content supportati

|**Tipo**|**Descrizione**|**Uso tipico**|
|---|---|---|
|**yum**|Repository RPM standard|RHEL, CentOS, Rocky, Alma|
|**deb**|Repository Debian/Ubuntu|Ubuntu, Debian|
|**docker**|Container images OCI|Kubernetes, Podman|
|**file**|File generici (ISO, script)|Installazione OS, tool custom|
### 4.3 Content Storage (Pulp)
Katello utilizza **Pulp** come backend per la gestione del contenuto. Pulp è un sistema di repository management che gestisce la sincronizzazione, lo storage e la distribuzione del contenuto. Ogni tipo di contenuto ha un plugin Pulp dedicato (pulp_rpm, pulp_deb, pulp_container, etc.).
## 5. Content View
### 5.1 Cos'è?
Una Content View è una selezione filtrata e versionata di contenuto proveniente da uno o più repository. Rappresenta uno 'snapshot' del contenuto in un momento specifico, permettendo di controllare esattamente quali pacchetti sono disponibili per i sistemi gestiti.
### 5.2 Perché serve?
•       **Controllo versioni:** Ogni pubblicazione crea una nuova versione immutabile del contenuto
•       **Consistenza:** Tutti i sistemi in un ambiente vedono lo stesso set di pacchetti
•       **Filtraggio:** Possibilità di includere/escludere pacchetti specifici tramite filtri
•       **Rollback:** In caso di problemi, si può tornare a una versione precedente
•       **Testing:** Permette di testare nuovi pacchetti prima del deploy in produzione
### 5.3 Come funziona?
Il workflow tipico di una Content View è:
1.  **Creazione:** Definire la Content View selezionando i repository da includere
2. **Filtri (opzionale):** Aggiungere filtri per includere/escludere pacchetti, errata o moduli specifici
3. **Pubblicazione:** Pubblicare per creare una nuova versione (es. Version 1.0, 2.0, etc.)
4. **Promozione:** Promuovere la versione attraverso i Lifecycle Environments (Dev → Test → Prod)
5. **Consumo:** I Content Host ricevono i pacchetti dalla versione promossa nel loro ambiente
### 5.4 Composite Content View - (Per ora non necessario)
Una **Composite Content View** combina più Content View in un'unica vista. Utile quando si vogliono gestire separatamente contenuti di base OS e applicazioni custom, ma distribuirli insieme ai sistemi.

> **⚠️ Best Practice:** Creare Content View separate per OS base, security updates e applicazioni. Combinare poi con Composite Content View per deployment flessibili.
## 6. Activation Key
### 6.1 Cos'è?
Un'Activation Key è un token che automatizza la registrazione dei sistemi a Foreman/Katello. Contiene tutte le configurazioni necessarie per associare un nuovo host all'organizzazione corretta, ai repository appropriati e alle funzionalità di gestione.
### 6.2 Perché serve?
•       **Automazione:** Registrazione con un singolo comando senza intervento manuale
•       **Consistenza:** Tutti i sistemi registrati con la stessa key avranno configurazione identica
•       **Sicurezza:** Non richiede credenziali utente nel processo di registrazione
•       **Scalabilità:** Ideale per provisioning automatizzato e Infrastructure as Code
### 6.3 Cosa configura?
Un'Activation Key definisce:

| **Parametro**             | **Descrizione**                                               |
| ------------------------- | ------------------------------------------------------------- |
| **Content View**          | Quale Content View il sistema utilizzerà per i pacchetti      |
| **Lifecycle Environment** | In quale ambiente (Dev/Test/Prod) sarà posizionato il sistema |
| **Host Collection**       | Gruppo logico di host per operazioni batch (opzionale)        |
| **Release Version**       | Versione specifica della Content View (opzionale)             |
| **Service Level**         | Livello di supporto associato (per sistemi RHEL)              |
## 7. Lifecycle Environment
### 7.1 Cos'è?
Un Lifecycle Environment rappresenta una fase nel percorso di promozione del contenuto, dalla creazione alla produzione. Definisce dove si trova logicamente un sistema nel ciclo di vita dell'infrastruttura e quale versione del contenuto può ricevere.
### 7.2 Perché serve?
•       **Staging controllato:** Permette di testare gli aggiornamenti prima del deploy in produzione
•       **Isolamento:** Sistemi in ambienti diversi sono isolati e ricevono contenuto diverso
•       **Governance:** Workflow approvativo per la promozione tra ambienti
•       **Compliance:** Tracciabilità di quale contenuto è disponibile in ogni ambiente
### 7.3 Struttura tipica - (Nel Nostro caso Development non risulta necessario)
Una Lifecycle Environment Path tipica include:
**Library** → **Development** → **Testing** → **Production**

|**Ambiente**|**Descrizione e Uso**|
|---|---|
|**Library**|Ambiente speciale che contiene TUTTO il contenuto sincronizzato. Non assegnabile direttamente ai sistemi. È il punto di partenza per tutte le promozioni.|
|**Development**|Primo ambiente dove il contenuto viene promosso. Usato per test iniziali e sviluppo. Riceve per primo le nuove versioni delle Content View.|
|**Testing/QA**|Ambiente per test di integrazione e quality assurance. Il contenuto viene promosso qui dopo validazione in Development.|
|**Production**|Ambiente finale per i sistemi di produzione. Solo contenuto completamente testato e approvato viene promosso qui.|
## 8. Errata
### 8.1 Cos'è?
Gli Errata sono advisory ufficiali pubblicati dai vendor per comunicare correzioni di bug, patch di sicurezza e miglioramenti ai pacchetti software. Ogni erratum include metadati strutturati come: CVE associati, severità, descrizione del problema, pacchetti coinvolti e istruzioni di remediation.
### 8.2 Perché serve?
- **Vulnerability Management:** Identifica rapidamente quali sistemi sono vulnerabili a specifici CVE
- **Prioritizzazione:** Classifica gli aggiornamenti per severità (Critical, Important, Moderate, Low)
- **Compliance:** Documentazione per audit e certificazioni di sicurezza
- **Selective Patching:** Possibilità di applicare solo specifici errata invece di tutti gli aggiornamenti
- **Reporting:** Dashboard e report sullo stato di applicazione degli errata nell'infrastruttura
### 8.3 Tipi di Errata

|**Tipo**|**Identificatore**|**Descrizione**|
|---|---|---|
|**Security**|RHSA-xxxx:xxxx|Patch di sicurezza con CVE associati. Priorità massima.|
|**Bugfix**|RHBA-xxxx:xxxx|Correzioni di bug non legati alla sicurezza.|
|**Enhancement**|RHEA-xxxx:xxxx|Nuove funzionalità o miglioramenti.|
### 8.4 Limitazioni degli Errata su Ubuntu/Debian
**⚠️ IMPORTANTE:** A differenza dei sistemi RPM (RHEL, CentOS), l'ecosistema Debian/Ubuntu **NON utilizza nativamente il concetto di Errata**. I repository DEB non includono metadati errata strutturati. Questo significa che Katello non può fornire:
•       Classificazione automatica Security/Bugfix/Enhancement
•       Correlazione diretta pacchetto-CVE dai repository standard
•       Report nativi sullo stato di vulnerabilità per host Ubuntu
•       Filtraggio Content View basato su tipo erratum

> **🔧** **Soluzione:** Per ottenere funzionalità errata-like su Ubuntu, è necessario utilizzare il plugin ATIX (vedi sezione 10) che genera errata sintetici dal repository ubuntu-security, mappando i pacchetti ai relativi CVE tramite Ubuntu Security Notices (USN).




