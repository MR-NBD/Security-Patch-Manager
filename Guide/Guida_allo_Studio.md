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











