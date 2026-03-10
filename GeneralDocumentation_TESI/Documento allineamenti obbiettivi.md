L’obiettivo della tesi è sviluppare una metodologia strutturata per la gestione dell’intero ciclo di rilascio, distribuzione, installazione e verifica delle patch di sicurezza.
Il problema del patch management è ampiamente documentato e riconosciuto nell’ambiente IT (https://www.computerworld.com/article/2583657/gartner--most-it-security-problems-self-inflicted.html) ed è osservabile anche nel contesto PSN. Tale problematica risulta maggiormente circoscritta in ambiente Linux, mentre negli ecosistemi Windows la gestione delle patch di sicurezza è fortemente centralizzata: salvo casi di urgenza, i rilasci avvengono con cadenza regolare (il cosiddetto “Patch Tuesday”, il secondo martedì di ogni mese) e le patch vengono distribuite dopo una fase di test preliminare che considera compatibilità e prerequisiti.
In ambiente Linux, al contrario, la gestione risulta meno uniforme e maggiormente frammentata. Questo porta frequentemente gli amministratori di sistema a dover applicare manualmente le singole patch o, in alcuni casi, a rinviarne l’installazione per evitare possibili interruzioni di servizio, con un conseguente aumento della superficie di attacco.
L’obiettivo del progetto di tesi è quindi proporre una soluzione per un ambiente multi-tenant in infrastruttura B2B, in grado di gestire l’intero ciclo di vita delle patch di sicurezza, incrementando il livello di sicurezza complessivo dell’infrastruttura. Tale obiettivo viene perseguito attraverso il raggiungimento di tre risultati principali:
1. Miglioramento della gestione del download delle patch tramite controllo e verifica dei certificati GPG e delle certificazioni SSL dei server provider, al fine di ridurre i rischi legati ad attacchi di supply chain. Questo rischio di sicurezza in continua crescita è anche ben documetato dal nuvo OWASP Top 10:2025(https://owasp.org/Top10/2025/A03_2025-Software_Supply_Chain_Failures/)
2. Introduzione di un manager per la prioritizzazione del deploy delle patch, che consenta il monitoraggio delle stesse in ambienti di test e la successiva promozione in ambienti di produzione, riducendo i disservizi per i clienti.
3. Realizzazione di un ambiente centralizzato di visualizzazione e controllo, che permetta una reazione più rapida ed efficace in caso di necessità di intervento o di risposta a un rischio.

Come definito e illustrato nel documento “Automated Patch Management for B2B IaaS Environments v1.1”, il problema del patch management è estremamente diffuso. Per questo motivo è stato proposto un processo di gestione allineato agli standard IEC/ISO 62443, ISO/IEC 27002 e NIST SP 800-40 (Enterprise Patch Management). In particolare, lo standard IEC/ISO 62443 definisce i principali punti del processo, che sono stati evidenziati nel workload proposto: Information Gathering, Monitoring and Evaluation, Patch Testing, Patch Deployment, Verification and Reporting.
È stato inoltre sviluppato un processo operativo allineato agli standard sopra menzionati.
![[PSN_work_flow_v2.png]]
![[General_Workflow_SPM_v2.png]]

Come descritto nel documento sopra, è stato definito un primo esempio di Proof of Concept (PoC) per la gestione del patch management in un contesto multi-tenant, basato su un’architettura Master–Slave.
![[HLD_SPM_v2.png]]
A seguito della definizione di un workflow iniziale, si è proceduto a sperimentarne l’applicabilità in un contesto operativo reale, apportando modifiche e miglioramenti. Ad esempio, è stata rimossa la fase di Active Environment Discovery, in quanto non allineata a un ecosistema operativo controllato e non in grado di incrementare la sicurezza, introducendo invece complessità aggiuntiva.
Con l’obiettivo di affinare ulteriormente la struttura della soluzione e raggiungere i tre obiettivi prefissati, sono state sperimentate diverse soluzioni tecnologiche, analizzandone l’integrazione con l’architettura proposta e i relativi limiti. È stato, ad esempio, ritenuto opportuno mantenere un database locale delle risorse gestite, al fine di evitare dipendenze eccessive da tool di terze parti.
Il primo approccio sperimentato è stato Foreman/Katello, un configuration manager open source mantenuto dalla community e supportato da Red Hat, in quanto progetto downstream di Red Hat Satellite. I test condotti hanno mostrato che lo strumento consente di gestire e definire le repository da sincronizzare (ad esempio “http://security.ubuntu.com/ubuntu”), includendo la registrazione e la verifica dei certificati GPG e SSL.
Sono stati inoltre analizzati i concetti di Lifecycle Environment e Content Management. Una volta definite le repository e sincronizzati i pacchetti installati sulle macchine, viene definito un “content”, ossia uno stato logico che rappresenta l’insieme dei pacchetti installati e disponibili per una determinata macchina o gruppo di macchine. Tali content possono essere associati a diversi ambienti (sviluppo, test, produzione) e promossi progressivamente, allineandosi perfettamente alla logica del workflow proposto, che prevede il testing delle patch in ambienti controllati prima del rilascio in produzione.
Foreman/Katello offre inoltre funzionalità avanzate di gestione delle identità tramite LDAP e la possibilità di suddividere logicamente l’infrastruttura in Organization e Location. Un ulteriore elemento chiave è la gestione dell’architettura Master–Slave tramite l’utilizzo di proxy, che permettono l’esecuzione locale delle operazioni e una migliore segmentazione dell’infrastruttura, incrementandone la sicurezza.
Un requisito fondamentale per il raggiungimento del terzo obiettivo è la correlazione tra patch di sicurezza e database NVD(https://nvd.nist.gov/), al fine di effettuare ricerche basate su CVE e valutare la gravità delle vulnerabilità nel contesto specifico delle macchine. In Foreman/Katello tale correlazione è gestita tramite gli Errata, che rappresentano una relazione logica tra CVE e pacchetti rilasciati da Red Hat. Questo ha evidenziato un limite significativo dello strumento: gli Errata sono disponibili esclusivamente per distribuzioni derivate da Fedora (Red Hat, CentOS, ecc.) e non per distribuzioni come Ubuntu o Debian, che utilizzano strutture differenti (USN per Ubuntu e DSA per Debian). Sebbene siano state ipotizzate soluzioni di integrazione, questo aspetto mette in luce una forte dipendenza dello strumento da specifiche famiglie di distribuzioni Linux.
**Per completare il processo di patch management, risulta ancora necessaria la definizione di una logica di prioritizzazione, testing e monitoraggio delle patch pienamente allineata al workflow proposto, attività attualmente in fase di sperimentazione.**
Per quanto riguarda la stesura della tesi, è stata definita la seguente struttura dei capitoli:
1. Introduction
    - Context and motivation
    - Problem statement and objectives
    - Scope and structure of the thesis
2. Background on Patch Management
    - Definition, process, and lifecycle
    - Common challenges and best practices
3. Risk Assessment and Security Trade-off (opzionale)
    - Security trade-off, compliance and governance aspects
    - Vulnerability classification and prioritization
    - Risk-based patching approaches    
4. Security in Cloud Environments
    - Functional and non-functional requirements
    - Multi-tenant B2B architectural constraints
    - Application in Microsoft Azure
5. Design and Implementation of the Solution
    - High-level architecture and components
    - Multi-tenant patch management workflow
    - Implementation details and automation
    - Performance evaluation and security validation
6. Conclusion and Future Work
    - Summary of results and contributions
    - Limitations of the current solution
    - Future extensions and scalability
A seguito di un colloquio col Prof.Valenza, è emerso anche l’interesse nell’introdurre e definire delle metriche per un KPI per il risk assessment. In ambito patch management sono riconosciute diverse metriche standard(https://ijtmh.com/index.php/ijtmh/article/view/194), tra cui:
- Patch Success Rate : Percentuale di patch distribuite con successo sul totale delle patch tentate
- Mean Time to Deploy : Tempo medio impiegato dal rilascio della patch alla sua distribuzione corretta.
- Rollback Frequency : Numero di patch ripristinate a causa di errori o guasti.
- System Downtime : Total downtime caused by patching activities.
- Vulnerability Remediation Coverage : Copertura di ripristino delle vulnerabilità

La metrica, ritenuta più significativa da me in questa prima fase di studio, per valutare il contributo alla sicurezza di una soluzione di patch management è il Mean Time to Deploy, in quanto una riduzione del tempo di distribuzione delle patch, senza impatti sull’operatività, consente di diminuire la window of exposure.
Stiamo inoltre definendo una metrica nuova che potrebbe allinearsi con la VRC che però non è stata ancora ben delianta ma ho affrontato una prima ipotesi esperimentale su excel. 