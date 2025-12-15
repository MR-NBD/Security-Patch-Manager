L'obbiettivo della tesi sviluppare una metodologia per la gestione di tutto il ciclo del rilascio e installazione delle patch di sicurezza.
Il problema ben documento e riconosciuto nell'ambiente IT e anche osservato anche nel contesto PSN è maggiormente circoscritto in umbiente linux poichè per come funziona il sistema chiuso di WIndowsper le pathc di sicurezza  vengono rilasciate mediamente ad eccezione di partcolare urgenze avviene ogni secondo marted' nel mese il "Patch Tuesday"e nel mmento di rilascio vengono già testate eventuali problemi di incompatibilità o di prerequisitivi. Questa gestione centralizzate e coerente e meno gestiota in ambiente linux portando spesso agli amministratori di sistema a procedere manulamente ogni singola patch o addirittura a non installarle per non procurare un inopertività ai sistemi. 
L'obbiettivo della progetto di tesi è sviluppare una proposta per un ambiente multi tenat in infrastruttura B2B che gestisca tutto il ciclo di gestione delle patch di sicurezza al fine di incrementare la sicureza generale dell'infrastruttuta. Questo avviene tramite il raggiungimento di tre obbiettivo. 
1. Una migliore gestione dei dowload delle patch tramite controllo e virificha di certificati GPC e certificazioni SSL dei server provider. QUesto al fine di ridurre i rischi di attacchi legati alla suplly chain
2. Un manager che ti permetta di prioritizzare il deploy delle patch che ti permetta di gestire il monitoraggio di quest ultime su ambienti di test e di promuovere successivamente in ambienti di produzione al fine di ridurre disservizi ai clienti 
3. Un ambiente centralizzato per la visualizzazione che permetta una miglior reazione e gestione in caso di necessità di intervento nella gestione o reazione ad un rischio.
Come abbiamo definito e mostrato nel docuemnto "Automated Patch Management for B2B IaaS Environments v1.1" Il problema è molto comune nell'ambiente e per tanto abbiamo proposto un processo di gestione del problema che si allinea con gli standard  IEC/ISO 62443 , ISO / IEC 27002 e NIST SP 800-40 — Enterprise Patch Management. Nello specifico IEC/ISO 62443 sciolina i punti punti principali che siamo andati ad evidenziare nel workload ovvero Information Gatherin, Monitoring and Evaluation, Patch Testing, Patch Deployment e Verification and Reporing. 
A seguito di ciò abbiamo anche analizzato nel contesto psn provando anche ad approcciare un impotesi di definizione  che possa anche all'inearsi alle necessità contrattuali col PSN. Fornendo uan definzione degli obbiettvi in questo contesto.
“Security Patch Management for PSN consists in achieving comprehensive visibility into the health of all managed assets through a centralized system that enables automated identification, acquisition, testing, installation, and verification of third-party security patches, without compromising the operational stability of clients’ production environments.”
Come affrontato meglio nel documento sopra abbiao definto un primo esempio di PoC su come vorremmo gestire il patch di mangemt in costesto multi tenant in un architettura Master slayer 
![[HLD_SPM_v2.png]]

e con uno sviluppo di un processo opertivo che possa allinearsi agli standr cui sopra. 
![[General_Workflow_SPM_v2.png]]
![[PSN_work_flow_v2.png]]

A seguito della definzione di un primo workflow ipotetico abbiamo iniziato a sperimentarne il suo funzionamento andando a contestualiizarlo in ambiente opertivo selezionando e migliorando cosa sia corretto fare. Es è stato scendo di rimuovere Active Environment Discovery in quanto non si alinea ad un ecosistema opertivo e non incrementa in alcun modo la sicurezza ma aumenta la complessità che potrebbe generale l'effetto opposto.
Con l'obbiettivo di migliorare e definire sempre meglio la struttura che permetta di raggiungere i tre obbiettivi elencati sopra. Abbiamo iniziato sperimentare alcune soluzione per ricercare quelle che meglio si integra col la nostra soluzione proposta andando anche ad evidenziare dei limiti di applicare una suluzione terza e come intervenire su tali problematiche. (es. si è scelto che è comunque opprtuno mantenre un db locale delle risorse gestite in modo da essere comunque non intrappolati da un tool).
Il primo approccio esperimentato è stato foreman/katello che configuration manager mantenuto e finanziato dalla sua comunity e da Red Hat in quanto progetto downstream di Red Hat Satellite. 
Quanto provato e testato fino ad esso permette di gestire e definire le repository a cui ci si vuole sincronizzare es: "http://security.ubuntu.com/ubuntu" gestendendo e registrando i certificati GPG e SSL. Inoltre ho testato quello che in cotesto foreman/katello viene definitto come Lifecycle nvironment e Content Management. Ovvero una volta definite le repository che vogliamo gestire su una vm e sincronizzati con in pacchetti attuamente installati sulle macchine creiamo un content ovvero uno stato logico in cui i pacchettu su quella specifica stato della macchine è posizionato. Es. Vm1 HA attualmete pacchetto A, B, C, D, ... inoltre in relazione con le repository caricati sono disponibili per l'installazione i pacchetti F, Z, X. questa è versione di un content. Ovvero uno stato logico. che possiamo memorizzare in relazione con una macchine o un gruppo di macchine. Il life cycle environemts permtte di associare un flusso logico tra le macchine es: abbiamo tre macchine che rappresentato lo steso lusso una macchina per lo sviluppo una per il test e una per la produzione. Il life cycle permette di dire okay "promuovimi il content di una macchina" aggiungendo i pacchetti A, B ma solo sulla macchina di Sviluppo. Successivamente potremo promuovere le altre macchine Allo stesso stato o ad uno stato differente. Qeesto si allinea permettamente con la logica del nostro workflow in quanto noi vogliamo patchare singolamente ogni pacchetto in un ambinete di test e successivamente aggiornare i pacchetti che abbiamo riscontrato corretti passandoli in produzione. Un altro vantaggio di Foreman/katello è che permtte di configurare e gestire le utenze tramite LDAP e creare delle suddivisioni logiche tra Organization o location. Altro tassello fondamentale e la gestione dela struttura Master slayer. Foreman gestisce e configura ogni ogni connessione tramite dei proxy che meremttano la esecuzione negli ambienti locali e una migliore segmentazione dell'infratruttura che ne garantisce la sciurezza. Un altro processo fondamentale per raggiungere il terzo obbiettio è quello di avere una correlazione con le patch di sicurezza i il relativo NVD databse. Questo permette di effettuare ricerche anche sulle base CVE e di valutare la gravità di tale patch nel contetso della macchina. Questo obbiettvio in foreman/katello è gestito tramite gli Errata che sono relazione logica cve pacchetto rilasciata da red hat. Questa ha rappresentato un rpimo problema fondamentale sull'utilizzo di questo strumento in quanto gli errata sono escusivi per ambienti che derivano da Fedora(Red HAt, CentOS, ...) non presenti in ambienti ese Ubuntu debian che utilizzano una logica identica ma con una struttura diversa ese Ubuntu utilizza USN (Ubuntu Security Notices) Debian utilizza DSA (Debian Security Advisories). Nel processo fin ora testato sono supposte soluzioni per integrare tale problema ma esso mostra il limite di questo strumento in quanto molto dipendente da determinate tipi di distribzioni linux. Questo difetto è stato presentato e esposto. Per "completare" il processo di Patch management prevede ancora la creazione di una logica su l'ordine e la metologia che si allineare con il workflow di cui sopra un sistema di testing e monitoraggio delle patch cui sto ancora testando. Per quanto riguarda la stestura della tesi abbiamo definito i Capitoli per la struttura : 
1. Introduction
    - Context and motivation 
    - Problem statement and objectives
    - Scope and structure of the thesis
2. Background on Patch Management
    - Definition, process, and lifecycle    
    - Security trade off (In alternativa a capitolo terza)
    - Common challenges and best practices
3. Risk Assessment and security trade off (In caso ci sia sufficientemente tempo per gestire al meglio anche questa sezione)
  - Security trade off, compliance and governance aspects
    - Vulnerability classification and prioritization
    - Risk-based patching approaches
4. Security in Cloud environment
  - Definition functional and non-functional requirements
    - Multi-tenant B2B architectural constraints
  - Application in Microsoft Azure
    - Tools, services, and frameworks employed
5. Design and Implementation of the Solution
    - High-level architecture and components
    - Multi-tenant patch management workflow
    - Implementation details, automation
    - Performance evaluation and security validation
6. Conclusion and Future Work
    - Summary of results and contributions
    - Limitations of the current solution
    - Possibilities for extension, scalability, and improvements
A seguito dell'colloquio anche con valenza è stato osservato anche di interesse come gestire e mostrare un KPI per un risk assesment. In ambito patch management sono riconscitu alcuni standrd di metriche come :
- Patch Success Rate : Percentuale di patch distribuite con successo sul totale delle patch tentate
- Mean Time to Deploy : Tempo medio impiegato dal rilascio della patch alla sua distribuzione corretta.
- Rollback Frequency : Numero di patch ripristinate a causa di errori o guasti.
- System Downtime : Total downtime caused by patching activities.
- Vulnerability Remediation Coverage : Copertura di ripristino delle vulnerabilità

Quello che evidenzio io come più interessante per valutare la sicurezza che aggiunge uno specifico strumento di patch managemet è il Mean Time to Deploy in quanto un minor tempo di deploy di una patch senza interruzione di operatività permette di ridurre la windows of exposure. 

Stiamo inoltre definendo una metrica nuova che potrebbe allinearsi con la VRC che però non è stata ancora ben delianta ma ho affrontato una prima ipotesi esperimentale su excel. 