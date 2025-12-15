## 2.1 Introduzione al Security Patch Management

La gestione delle patch di sicurezza software rappresenta una delle pratiche più critiche e al contempo più complesse nell'ambito della cybersecurity aziendale. Nonostante il rilascio tempestivo di patch di sicurezza da parte dei vendor per correggere vulnerabilità appena scoperte, la maggior parte degli attacchi informatici nel mondo reale è il risultato dello sfruttamento di vulnerabilità note per le quali esisteva già una patch disponibile (Dissanayake et al., 2021a). Casi emblematici come la violazione di Equifax nel 2017, che ha esposto i dati personali di 143 milioni di cittadini americani, o il più recente attacco ransomware a un ospedale tedesco nel 2020 che ha causato la morte di una paziente, dimostrano le conseguenze potenzialmente catastrofiche di un ritardo nell'applicazione delle patch di sicurezza (Eddy & Perlroth, 2020; Mathews, 2017).

Il Security Patch Management può essere definito come:

> _"Un processo multidimensionale di identificazione, acquisizione, test, installazione e verifica delle patch di sicurezza per prodotti e sistemi software"_ (Dissanayake et al., 2021a; Souppaya & Scarfone, 2013).

Questa pratica di sicurezza è progettata per prevenire proattivamente lo sfruttamento delle vulnerabilità presenti nei prodotti software e nei sistemi distribuiti all'interno dell'ambiente IT di un'organizzazione (Mell et al., 2005). Le patch di sicurezza software sono definite come "porzioni di codice sviluppate per affrontare problemi di sicurezza identificati nel software" e sono sempre prioritizzate rispetto alle patch non legate alla sicurezza, poiché mirano a mitigare vulnerabilità che presentano opportunità sfruttabili da entità malevole per ottenere accesso ai sistemi (Mell et al., 2005; Brykczynski & Small, 2003).

Un processo di Security Patch Management efficace è quindi essenziale e critico per sostenere la confidenzialità, l'integrità e la disponibilità dei sistemi IT (Mell et al., 2005). Tuttavia, secondo recenti report industriali, oltre il 50% delle organizzazioni non riesce a patchare le vulnerabilità critiche entro le 72 ore raccomandate dal loro rilascio, e circa il 15% rimane senza patch anche dopo 30 giorni (Automox, 2020). Questi dati rivelano che le organizzazioni moderne stanno lottando per soddisfare i requisiti di "patch early and often", indicando una crescente necessità di maggiore attenzione al processo di patching nella pratica.

## 2.2 Il Ciclo di Vita delle Vulnerabilità Software

Per comprendere appieno il contesto del Security Patch Management, è fondamentale analizzare il ciclo di vita tipico di una vulnerabilità software (Figura 2.1). Questo ciclo inizia con la scoperta della vulnerabilità, che può avvenire attraverso ricercatori di sicurezza, team interni di sviluppo o, nel peggiore dei casi, da attori malevoli.

La sequenza temporale tipica comprende:

1. **Scoperta della vulnerabilità**: Il momento in cui viene identificata una debolezza nel software
2. **Sfruttamento della vulnerabilità**: Il periodo in cui la vulnerabilità può essere attivamente sfruttata (se scoperta da attori malevoli prima della disclosure)
3. **Divulgazione della vulnerabilità**: La comunicazione formale dell'esistenza della vulnerabilità
4. **Rilascio della patch di sicurezza**: Il momento in cui il vendor rende disponibile la correzione
5. **Applicazione della patch di sicurezza**: L'installazione effettiva della patch nei sistemi dell'organizzazione

Il Security Patch Management si focalizza specificamente sulla fase finale di questo ciclo, ovvero sul processo attraverso il quale un'organizzazione applica le patch di sicurezza ai propri software di terze parti dopo che queste sono state rilasciate dai rispettivi vendor (Dissanayake et al., 2021a).

## 2.3 Le Fasi del Processo di Security Patch Management

Il processo di Security Patch Management si articola in cinque fasi principali, ciascuna caratterizzata da specifiche attività, sfide e requisiti (Dissanayake et al., 2021a; Li et al., 2019; Tiefenau et al., 2020).

### 2.3.1 Fase 1: Recupero delle Informazioni sulle Patch (Patch Information Retrieval)

La prima fase del processo riguarda l'acquisizione delle informazioni relative alle nuove patch disponibili. I professionisti IT devono apprendere l'esistenza di nuove patch e acquisirle dai vendor di software di terze parti come Microsoft, Oracle, Adobe e altri.

Secondo Li et al. (2019), le moderne fonti di informazione sulle patch includono:

- Advisory di sicurezza (78%)
- Notifiche ufficiali dei vendor (71%)
- Mailing list (53%)
- Forum online (52%)
- Notizie (39%)
- Blog (38%)
- Social media (18%)

La mancanza di una piattaforma centralizzata per il recupero e il filtraggio delle informazioni costringe i professionisti a dedicare ore al monitoraggio di molteplici fonti informative (Trabelsi et al., 2015; Rahman et al., 2013). Inoltre, la carenza di validazione automatica, filtraggio e classificazione delle informazioni sulle patch secondo le esigenze organizzative comporta ritardi nell'applicazione delle patch e aumenta il rischio di attacchi zero-day (Trabelsi et al., 2015).

### 2.3.2 Fase 2: Scansione delle Vulnerabilità, Valutazione e Prioritizzazione

In questa fase, i professionisti eseguono la scansione dei sistemi software gestiti per identificare le vulnerabilità appena divulgate, valutare l'applicabilità delle patch nel loro contesto organizzativo, stimare il rischio e conseguentemente prioritizzare le decisioni di patching.

Un aspetto critico riguarda la **mancanza di una soluzione di scansione completa**, che impedisce ai professionisti di ottenere una chiara comprensione del sistema, portando a mancate rilevazioni di vulnerabilità software e configurazioni errate (Dissanayake et al., 2021a). Le sfide principali includono:

- **Mancanza di comprensione del sistema**: Difficoltà nel mappare tutti gli asset e le loro interdipendenze
- **Carenza di supporto per la gestione della configurazione**: Problemi nella rilevazione di misconfigurazioni
- **Conoscenza incompleta degli inventari di sistema**: Asset non documentati o obsoleti

Per quanto riguarda la valutazione e prioritizzazione delle vulnerabilità, il Common Vulnerability Scoring System (CVSS) rappresenta lo standard industriale principale (FIRST, 2019). Tuttavia, diversi studi hanno evidenziato la necessità di approcci personalizzati che tengano conto del contesto dinamico dell'organizzazione (Fruhwirth & Männistö, 2009; Kamongi et al., 2013; Jiang et al., 2012).

Le sfide specifiche di questa fase includono:

- **Mancanza di supporto per contesti ambientali dinamici**: Gli approcci esistenti sono generalmente "one size fits all" e creano difficoltà nell'incorporare le esigenze del contesto organizzativo specifico
- **Gap di conoscenza tra contesto tecnico e di business**: Conflitti di prioritizzazione tra team diversi derivanti dalla mancanza di conoscenza della postura di rischio aziendale e del rischio tecnico

### 2.3.3 Fase 3: Test delle Patch (Patch Testing)

La fase di test delle patch rappresenta un passaggio cruciale per garantire l'accuratezza e la stabilità delle patch prima dell'installazione. Questa fase include la preparazione all'installazione attraverso la modifica delle configurazioni delle macchine, la risoluzione delle dipendenze delle patch e l'esecuzione di backup.

Le sfide principali in questa fase sono:

**Mancanza di una strategia di test automatizzata appropriata**: La necessità di test automatizzati delle patch è riconosciuta come una delle sfide più pressanti (Hosek & Cadar, 2013; Maurer & Brumley, 2012). Tuttavia, l'automazione completa rimane difficile da raggiungere a causa di:

- Complessità nella gestione delle dipendenze tra patch
- Sforzo umano significativo richiesto per configurare un ambiente di test che simuli fedelmente l'ambiente di produzione

**Scarsa qualità dei test manuali**: Nonostante le difficoltà, la maggior parte dei test delle patch viene ancora eseguita manualmente per evitare i rischi di interruzioni di sistema impreviste causate da patch difettose o malevole (Li et al., 2019). Tuttavia, questa pratica presenta problemi significativi:

- Ritarda il successivo deployment delle patch
- È soggetta a errori a causa della difficoltà di replicare esattamente lo stato di produzione
- Aumenta l'esposizione del sistema alle vulnerabilità

### 2.3.4 Fase 4: Deployment delle Patch (Patch Deployment)

La fase di deployment riguarda l'installazione effettiva delle patch sui sistemi target. Questa fase presenta alcune delle sfide più critiche dell'intero processo.

**Fallimenti ed effetti collaterali dovuti al deployment delle patch**: Questa sfida emerge come conseguenza di:

- Test delle patch insufficienti che portano al deployment di patch difettose
- Prerequisiti mancanti per il deployment (configurazioni, modifiche delle dipendenze) che causano errori di deployment
- Tali errori conducono a downtime aggiuntivo del servizio, portando molti professionisti a ritardare o rifiutare l'installazione delle patch, continuando a utilizzare software obsoleto e lasciando vulnerabilità note prontamente sfruttabili

**Gestione dei vincoli organizzativi sul downtime di sistema**: La mancanza di una strategia di deployment delle patch a runtime adeguata, combinata con le policy organizzative per evitare il downtime di sistema, presenta una sfida seria per l'installazione tempestiva delle patch (Dissanayake et al., 2021a). Questo è particolarmente critico nei contesti di infrastrutture critiche come il settore sanitario, dove il downtime può creare un impatto avverso significativo.

### 2.3.5 Fase 5: Verifica Post-Deployment (Post-Deployment Patch Verification)

L'ultima fase del processo riguarda la verifica dei deployment delle patch attraverso il monitoraggio (per interruzioni di servizio inaspettate) e la gestione dei problemi post-deployment.

Le sfide principali includono:

**Mancanza di una strategia automatizzata efficiente per la verifica post-deployment**: La maggior parte delle soluzioni esistenti non offre una panoramica dello stato delle patch del sistema, risultando in difficoltà nel rilevare la posizione del problema quando si verifica un'issue a seguito del deployment (Dissanayake et al., 2021a).

**Metodi di audit manuali**: La maggior parte dei metodi attuali di audit delle patch richiede ai professionisti di ispezionare manualmente l'applicazione per segni di attacco e riparare i danni se viene trovato un attacco. Questo è un compito frustrante, difficile e time-consuming senza garanzia di trovare ogni intrusione e revertere tutti i cambiamenti sfruttati da un attaccante (Chen et al., 2014; Kim et al., 2012).

## 2.4 Sfide Socio-Tecniche nel Security Patch Management

L'analisi della letteratura ha identificato 14 sfide socio-tecniche principali nel Security Patch Management, che possono essere classificate in sfide comuni a tutte le fasi del processo e sfide specifiche per ciascuna fase (Dissanayake et al., 2021a).

### 2.4.1 Sfide Comuni

**Sfide di collaborazione, coordinazione e comunicazione (Ch1)**: Il processo di Security Patch Management è uno sforzo collaborativo che coinvolge molteplici stakeholder quali team interni (security manager, ingegneri, amministratori), vendor software di terze parti e clienti/utenti finali. Gli interessi conflittuali e le interdipendenze tra queste parti rendono il Security Patch Management un'impresa complessa (Dissanayake et al., 2021b). Le principali problematiche includono:

- Overhead amministrativo nel coordinamento con diversi stakeholder con interessi conflittuali
- Problemi di delega dovuti alla mancanza di accountability e ruoli/responsabilità ben definiti
- Sfide comunicative con molteplici stakeholder con conflitti di interesse
- Mancanza di collaborazione tra i diversi stakeholder

**Impatto delle policy organizzative/compliance (Ch2)**: La necessità di bilanciare la conformità alle policy organizzative eterogenee con il mantenimento della sicurezza software è riconosciuta come una sfida chiave. Questo perché le policy stabilite dal management superiore (es. policy di minime interruzioni di servizio) talvolta contraddicono l'applicazione tempestiva di patch di sicurezza emergenziali.

**Complessità delle patch (Ch3)**: Il rapido aumento del numero e della diversità degli attacchi ha comportato un tasso accelerato di rilascio delle patch, creando una situazione difficile per i professionisti. I fattori contributivi includono:

- Diversità delle patch (eterogeneità)
- Tasso crescente di rilascio delle patch
- Ampia superficie di attacco (struttura organizzativa grande e distribuita)

**Limitazioni degli strumenti esistenti (Ch4)**: Questa rappresenta un ostacolo maggiore al raggiungimento degli obiettivi del Security Patch Management. Le limitazioni prominenti includono:

- Mancanza di una piattaforma standard per integrare strumenti eterogenei utilizzati per il patch management
- Mancanza di accuratezza (gli strumenti attuali non considerano il contesto organizzativo dinamico)
- Mancanza di sicurezza
- Mancanza di scalabilità nel design/architettura degli strumenti

**Necessità di competenza umana (Ch5)**: A causa della complessità crescente e della natura dinamica del Security Patch Management, e delle limitazioni delle tecnologie attuali, l'intervento umano rimane inevitabile in tutto il processo di patching. Tuttavia, come conseguenza del coinvolgimento umano, il tempo per il patching aumenta, lasciando diversi vettori di attacco aperti agli exploit.

**Mancanza di risorse (Ch6)**: Il rischio di ritardi è ulteriormente aumentato dalla mancanza di risorse in termini di:

- Competenze e expertise
- Linee guida di processo
- Supporto per l'automazione del processo

### 2.4.2 Distribuzione delle Sfide per Fase

La Tabella 2.1 riassume la distribuzione delle sfide specifiche per ciascuna fase del processo:

|Fase|Sfide Specifiche|
|---|---|
|Patch Information Retrieval|Mancanza di piattaforma centrale per recupero e filtraggio informazioni|
|Vulnerability Scanning, Assessment and Prioritisation|Mancanza di soluzione di scansione completa; Mancanza di supporto per contesto ambientale dinamico; Gap di conoscenza tecnico-business|
|Patch Testing|Mancanza di strategia di test automatizzata; Scarsa qualità nei test manuali|
|Patch Deployment|Fallimenti ed effetti collaterali dovuti al deployment|
|Post-Deployment Verification|Mancanza di strategia automatizzata efficiente per la verifica|

## 2.5 Il Ruolo della Coordinazione nel Security Patch Management

Uno degli aspetti meno esplorati ma criticamente importanti del Security Patch Management riguarda il ruolo della coordinazione. Dissanayake et al. (2021b) hanno sviluppato una teoria fondata che spiega come la coordinazione impatti il processo attraverso quattro dimensioni interrelate: cause, vincoli, breakdown e meccanismi.

### 2.5.1 Cause: Dipendenze Socio-Tecniche

Le interdipendenze socio-tecniche intrinseche al processo definiscono la necessità di coordinazione e possono essere classificate in:

**Dipendenze Tecniche**: Interdipendenze tra software e hardware/firmware associati, che emergono come risultato delle dipendenze nel codice software. Includono:

- _Dipendenze relative al software_: Dipendenze del sistema operativo, dipendenze tra applicazioni software, prerequisiti per l'installazione delle patch
- _Dipendenze hardware e firmware_: Alcune patch di sicurezza contengono dipendenze con hardware e firmware associati

**Dipendenze Sociali**: Derivano dalle interdipendenze tra stakeholder e includono:

- _Dipendenze interne degli stakeholder_: A livello di team e a livello organizzativo
- _Dipendenze esterne degli stakeholder_: Con clienti, utenti finali e vendor

### 2.5.2 Vincoli

I fattori che ostacolano la coordinazione includono:

- **Dipendenze relative ai sistemi legacy**: I sistemi legacy rappresentano una minaccia alla sicurezza delle infrastrutture ICT organizzative, poiché spesso non sono più supportati dai vendor
- **Mancanza di supporto per l'automazione**: L'incapacità di visualizzare le dipendenze tecniche attraverso tutti gli inventari di sistema
- **Carico di patch aumentato**: Con la crescita delle dimensioni dell'organizzazione, aumentano il numero e la diversità dei sistemi, risultando in maggiore complessità nel patching

### 2.5.3 Breakdown

I breakdown rappresentano scenari di fallimento nel processo risultanti da coordinazione inefficace:

- **Escalation improvvise nei programmi delle patch**: Cambiamenti imprevisti ai piani di installazione
- **Ritardi nelle approvazioni organizzative**: Cambiamenti bruschi ai piani di installazione dovuti a ritardi nelle approvazioni
- **Mancanza di consapevolezza delle dipendenze**: Dovuta a distribuzione localizzata del lavoro

### 2.5.4 Meccanismi

Le strategie emergenti per supportare una coordinazione efficace includono:

1. **Investigazione precoce delle interdipendenze**: Identificazione anticipata delle dipendenze per coordinare le dipendenze dei task tra team
2. **Decision-making collaborativo**: Utilizzo di riunioni come piattaforma per decidere collaborativamente sulla valutazione del rischio e prioritizzazione
3. **Misurazione continua del progresso**: Monitoraggio costante della progressione della remediation delle vulnerabilità
4. **Comunicazione frequente**: Essenziale per una coordinazione efficace delle dipendenze
5. **Bilanciamento del carico**: Strategia per bilanciare il carico delle patch sui server
6. **Valutazione centralizzata del rischio delle vulnerabilità**: Ruolo centralizzato responsabile della scansione e categorizzazione delle vulnerabilità

## 2.6 Soluzioni Proposte: Approcci, Strumenti e Pratiche

La letteratura ha identificato diverse categorie di soluzioni per affrontare le sfide del Security Patch Management (Dissanayake et al., 2021a).

### 2.6.1 Approcci e Strumenti

**Gestione delle Informazioni sulle Patch (S1)**: Piattaforme unificate che includono:

- Recupero delle informazioni sulle patch da molteplici fonti
- Filtraggio delle informazioni basato sulle esigenze di configurazione organizzativa
- Validazione delle informazioni sulle patch
- Download e distribuzione delle patch

**Scansione per vulnerabilità, attacchi potenziali e in corso (S2)**: Include:

- Piattaforma centrale che integra i risultati delle scansioni da molteplici fonti
- Analisi dettagliata basata sull'host per identificare gli asset residenti
- Rilevamento delle misconfigurazioni di sistema
- Identificazione di attacchi in corso
- Fornitura di analisi storiche delle scansioni

**Valutazione e Prioritizzazione (S3)**: Comprende:

- Analisi personalizzabile, dettagliata e completa dei rischi delle vulnerabilità
- Predizione della strategia di correzione ottimale
- Misurazione dell'efficacia della remediation organizzativa
- Cattura del contesto dinamico per valutazione e prioritizzazione accurate

**Rilevamento automatico e recovery da patch difettose e malevole (S4)**: Include approcci per:

- Rilevamento automatico di patch difettose
- Rilevamento automatico di patch malevole
- Recovery automatico dai crash causati da patch difettose

**Deployment automatizzato delle patch (S5)**: Caratteristiche:

- Considerazione del contesto dinamico nel deployment
- Riduzione del downtime di sistema nei riavvii

**Monitoraggio automatizzato e audit delle patch (S6)**:

- Rilevamento automatico degli exploit e verifica del deployment
- Riparazione automatica degli exploit passati

### 2.6.2 Pratiche Raccomandate

La Tabella 2.2 sintetizza le pratiche raccomandate per ciascuna fase del processo:

|Fase|Pratiche|
|---|---|
|Comuni|Pianificazione e documentazione; Stabilire policy e procedure formali; Definire ruoli e responsabilità; Ottenere coinvolgimento del management; Definire procedure per comunicazione efficiente|
|Patch Information Retrieval|Stabilire policy e responsabilità per recupero, notifica e disseminazione delle informazioni|
|Vulnerability Scanning|Monitorare regolarmente applicazioni attive e inattive; Mantenere inventari di sistema aggiornati; Eseguire valutazione basata sulle esigenze organizzative|
|Patch Testing|Migliorare le attività di test; Preparare e conservare l'ambiente di test|
|Patch Deployment|Installare patch tempestivamente bilanciando rischi di sicurezza, risorse e disponibilità|
|Post-Deployment|Tracciare lo stato di deployment di ogni patch|

## 2.7 Valutazione delle Soluzioni

Un aspetto critico emerso dalla letteratura riguarda la valutazione delle soluzioni proposte. L'analisi ha rivelato che solo il 20.8% delle soluzioni è stato rigorosamente valutato in contesti industriali utilizzando approcci di valutazione rappresentativi del mondo reale come field experiment e case study (Dissanayake et al., 2021a).

La distribuzione dei tipi di valutazione mostra:

- **Laboratory experiment with software subjects**: 30.36% (più frequente per approcci)
- **Simulation with artificial data**: 28.57%
- **Experience**: 56.25% (più frequente per pratiche)
- **Case study**: Raramente utilizzato (3.57%)
- **No Evaluation**: 4 studi

Questa carenza di valutazioni rigorose con rilevanza industriale è allarmante considerando che il dominio è fortemente centrato sull'industria, indicando una grande necessità di valutazioni robuste delle soluzioni che facilitino l'adozione industriale.

## 2.8 Gap e Direzioni Future

Sulla base dell'analisi della letteratura, emergono diverse aree che richiedono ulteriore attenzione:

1. **Fasi meno esplorate del processo**: Patch Information Retrieval, Patch Testing e Post-Deployment Verification hanno ricevuto la minore attenzione (solo 6.9% degli studi per ciascuna fase)
    
2. **Focus sugli aspetti socio-tecnici**: Il 50% delle sfide comuni non è direttamente associato a soluzioni, rivelando gap aperti per la ricerca futura
    
3. **Collaborazione Human-AI**: La necessità di un equilibrio tra intervento umano e automazione suggerisce opportunità per la ricerca emergente sulla "Human-AI Collaboration"
    
4. **Standardizzazione degli strumenti eterogenei**: Necessità di architetture orchestrate che supportino la standardizzazione di strumenti di patch management eterogenei
    
5. **Valutazioni rigorose nel mondo reale**: Grande necessità di lavorare con i professionisti per migliorare lo stato della pratica nella valutazione rigorosa dei risultati della ricerca
    

## 2.9 Sintesi del Capitolo

Questo capitolo ha fornito una panoramica completa del Security Patch Management, definendolo come un processo multidimensionale che va oltre la semplice installazione tecnica di aggiornamenti software. L'analisi ha evidenziato come il Security Patch Management sia intrinsecamente un endeavor socio-tecnico, dove le interazioni umane e tecnologiche sono strettamente accoppiate, e dove il successo dipende significativamente dalla collaborazione efficace degli esseri umani con i sistemi tecnici.

Le cinque fasi del processo—recupero delle informazioni, scansione e prioritizzazione, testing, deployment e verifica—presentano ciascuna sfide specifiche che richiedono approcci integrati. Le 14 sfide socio-tecniche identificate, insieme alla teoria sulla coordinazione, forniscono un framework per comprendere le complessità del processo e le interdipendenze che devono essere gestite.

Le soluzioni proposte nella letteratura, sotto forma di approcci, strumenti e pratiche, offrono diverse strategie per affrontare queste sfide. Tuttavia, la carenza di valutazioni rigorose in contesti industriali rappresenta una limitazione significativa che deve essere affrontata per facilitare il trasferimento dei risultati della ricerca alla pratica industriale.

---

## Riferimenti Bibliografici

Automox. (2020). _2020 Cyber Hygiene Report: What You Need to Know Now_. https://patch.automox.com/rs/923-VQX-349/images/Automox_2020_Cyber_Hygiene_Report.pdf

Brykczynski, B., & Small, R. A. (2003). Reducing internet-based intrusions: Effective security patch management. _IEEE Software_, 20(1), 50-57.

Chen, H., Kim, T., Wang, X., Zeldovich, N., & Kaashoek, M. F. (2014). Identifying Information Disclosure in Web Applications with Retroactive Auditing. _USENIX Symposium on Operating Systems Design and Implementation_.

Dissanayake, N., Jayatilaka, A., Zahedi, M., & Babar, M. A. (2021a). Software Security Patch Management - A Systematic Literature Review of Challenges, Approaches, Tools and Practices. _arXiv preprint arXiv:2012.00544v3_.

Dissanayake, N., Zahedi, M., Jayatilaka, A., & Babar, M. A. (2021b). A Grounded Theory of the Role of Coordination in Software Security Patch Management. _Proceedings of the 29th ACM Joint European Software Engineering Conference and Symposium on the Foundations of Software Engineering (ESEC/FSE '21)_, 793-805.

Eddy, M., & Perlroth, N. (2020, September 18). Cyber Attack Suspected in German Woman's Death. _The New York Times_. https://www.nytimes.com/2020/09/18/world/europe/cyber-attack-germany-ransomeware-death.html

FIRST. (2019). _Common Vulnerability Scoring System_. https://www.first.org/cvss/

Fruhwirth, C., & Männistö, T. (2009). Improving CVSS-based vulnerability prioritization and response with context information. _International Symposium on Empirical Software Engineering and Measurement_.

Hosek, P., & Cadar, C. (2013). Safe software updates via multi-version execution. _International Conference on Software Engineering_.

Jiang, J., Ding, L., Zhai, E., & Yu, T. (2012). VRank: A Context-Aware Approach to Vulnerability Scoring and Ranking in SOA. _International Conference on Software Security and Reliability_.

Kamongi, P., Kotikela, S., Kavi, K., Gomathisankaran, M., & Singhal, A. (2013). VULCAN: Vulnerability Assessment Framework for Cloud Computing. _International Conference on Software Security and Reliability_.

Kim, T., Chandra, R., & Zeldovich, N. (2012). Efficient patch-based auditing for web application vulnerabilities. _USENIX Symposium on Operating Systems Design and Implementation_.

Li, F., Rogers, L., Mathur, A., Malkin, N., & Chetty, M. (2019). Keepers of the Machines: Examining How System Administrators Manage Software Updates. _Fifteenth Symposium on Usable Privacy and Security (SOUPS 2019)_, 273-288.

Mathews, L. (2017, September 7). Equifax Data Breach Impacts 143 Million Americans. _Forbes_. https://www.forbes.com/sites/leemathews/2017/09/07/equifax-data-breach-impacts-143-million-americans/

Maurer, M., & Brumley, D. (2012). Tachyon: Tandem execution for efficient live patch testing. _USENIX Security Symposium_.

Mell, P., Bergeron, T., & Henning, D. (2005). Creating a patch and vulnerability management program. _NIST Special Publication 800-40_.

Rahman, M. S., Yan, G., Madhyastha, H. V., Faloutsos, M., Eidenbenz, S., & Fisk, M. (2013). iDispatcher: A unified platform for secure planet-scale information dissemination. _Peer-to-Peer Networking and Applications_.

Souppaya, M., & Scarfone, K. (2013). Guide to Enterprise Patch Management Technologies. _NIST Special Publication 800-40r3_.

Tiefenau, C., Häring, M., Krombholz, K., & von Zezschwitz, E. (2020). Security, Availability, and Multiple Information Sources: Exploring Update Behavior of System Administrators. _Sixteenth Symposium on Usable Privacy and Security (SOUPS 2020)_, 239-258.

Trabelsi, S., Plate, H., Abida, A., Ben Aoun, M. M., Zouaoui, A., Missaoui, C., Gharbi, S., & Ayari, A. (2015). Mining social networks for software vulnerabilities monitoring. _International Conference on New Technologies, Mobility and Security_.