## 2.1 Concetti Fondamentali
Una vulnerabilità software rappresenta una debolezza o un difetto presente nel codice, nella progettazione, nell'implementazione o nella configurazione di un sistema software che può essere sfruttata da un attaccante per compromettere la sicurezza del sistema stesso. Il National Institute of Standards and Technology (NIST) definisce formalmente una vulnerabilità come "una debolezza in un sistema informativo, nelle procedure di sicurezza del sistema, nei controlli interni o nell'implementazione che potrebbe essere sfruttata da una fonte di minaccia" (NIST, 2012).

Le vulnerabilità software possono manifestarsi in diverse forme:
- **Errori di programmazione**: Buffer overflow, injection flaws, race conditions
- **Difetti di progettazione**: Architetture insicure, autenticazione debole, gestione inadeguata delle sessioni
- **Errori di configurazione**: Impostazioni di default non sicure, permessi eccessivi, servizi non necessari esposti
- **Dipendenze vulnerabili**: Librerie di terze parti contenenti vulnerabilità note

La gravità di una vulnerabilità viene tipicamente valutata attraverso il Common Vulnerability Scoring System (CVSS), uno standard industriale sviluppato dal Forum of Incident Response and Security Teams (FIRST) che assegna un punteggio numerico da 0.0 a 10.0 basato su metriche quali il vettore di attacco, la complessità dell'attacco, i privilegi richiesti e l'impatto su confidenzialità, integrità e disponibilità (FIRST, 2019). Le vulnerabilità sono inoltre catalogate nel Common Vulnerabilities and Exposures (CVE), un dizionario pubblico che assegna identificatori univoci a ciascuna vulnerabilità nota, facilitando la comunicazione e il tracciamento tra organizzazioni, vendor e ricercatori di sicurezza.

### 2.1.2 Le Patch di Sicurezza: Natura e Scopo

Le patch di sicurezza software sono definite come "porzioni di codice sviluppate per affrontare problemi di sicurezza identificati nel software" (Mell et al., 2005). A differenza delle patch funzionali che introducono nuove funzionalità o correggono bug non legati alla sicurezza, le patch di sicurezza hanno lo scopo specifico di eliminare o mitigare vulnerabilità che potrebbero essere sfruttate da attori malevoli per ottenere accesso non autorizzato ai sistemi.

Le patch di sicurezza sono sempre prioritizzate rispetto alle patch non legate alla sicurezza da parte di professionisti e ricercatori del settore, poiché mirano a mitigare vulnerabilità che presentano opportunità sfruttabili per entità malevole (Mell et al., 2005; Brykczynski & Small, 2003). Tuttavia, l'applicazione di una patch non è un'operazione banale: può richiedere riavvii del sistema, può introdurre incompatibilità con software esistente, può alterare il comportamento di applicazioni critiche e, in casi estremi, può essa stessa contenere difetti che causano malfunzionamenti.

Li e Paxson (2017), in uno studio empirico su larga scala, hanno analizzato le caratteristiche delle patch di sicurezza scoprendo che esse variano significativamente in termini di complessità, dimensione e tipo di modifiche apportate. Alcune patch consistono in semplici modifiche di poche righe di codice, mentre altre richiedono ristrutturazioni significative. Alcune necessitano solo dell'installazione del codice aggiornato, mentre altre richiedono modifiche ai registri di sistema, installazione di pacchetti preparatori o configurazioni specifiche prima che la patch possa prendere effetto.

### 2.1.3 Il Security Patch Management: Una Definizione Operativa

Il Security Patch Management può essere definito come:

> _"Un processo multidimensionale di identificazione, acquisizione, test, installazione e verifica delle patch di sicurezza per prodotti e sistemi software"_ (Dissanayake et al., 2021a; Souppaya & Scarfone, 2013).

Questa pratica di sicurezza è progettata per prevenire proattivamente lo sfruttamento delle vulnerabilità presenti nei prodotti software e nei sistemi distribuiti all'interno dell'ambiente IT di un'organizzazione (Mell et al., 2005). Un processo di Security Patch Management efficace è essenziale per sostenere la triade CIA (Confidentiality, Integrity, Availability) dei sistemi IT.

È fondamentale distinguere il Security Patch Management dallo sviluppo delle patch. Mentre lo sviluppo delle patch è responsabilità del vendor del software (che identifica la vulnerabilità, sviluppa la correzione e la rilascia), il Security Patch Management riguarda il processo attraverso il quale un'organizzazione cliente applica tali patch ai propri sistemi dopo che queste sono state rese disponibili (Dissanayake et al., 2021a). Questa distinzione è cruciale per comprendere le sfide specifiche affrontate dai team IT aziendali.

## 2.2 Il Ciclo di Vita delle Vulnerabilità Software

La comprensione del ciclo di vita di una vulnerabilità software è fondamentale per contestualizzare le sfide del Security Patch Management. Questo ciclo rappresenta la sequenza temporale che intercorre dalla nascita di una vulnerabilità fino alla sua completa remediation, e ogni fase presenta rischi e implicazioni specifiche.

### 2.2.1 Fase 1: Introduzione della Vulnerabilità

Una vulnerabilità viene introdotta nel software durante il processo di sviluppo o attraverso l'integrazione di componenti di terze parti. Questa introduzione può avvenire in diversi momenti: durante la scrittura del codice originale, durante l'aggiunta di nuove funzionalità, durante la correzione di altri bug, o attraverso l'inclusione di librerie e dipendenze esterne che contengono vulnerabilità preesistenti.

Secondo Nappa et al. (2015), un fenomeno particolarmente problematico è quello delle vulnerabilità condivise: quando porzioni di codice vulnerabile vengono riutilizzate in molteplici prodotti software, una singola vulnerabilità può propagarsi attraverso l'intero ecosistema software, moltiplicando l'impatto e complicando enormemente gli sforzi di remediation. Il loro studio ha analizzato 1593 vulnerabilità client-side dimostrando come il codice condiviso tra applicazioni amplifichi significativamente la finestra di esposizione.

### 2.2.2 Fase 2: Scoperta della Vulnerabilità

La scoperta di una vulnerabilità può avvenire attraverso molteplici canali:

- **Ricercatori di sicurezza indipendenti**: Ethical hacker che identificano vulnerabilità e le segnalano responsabilmente ai vendor
- **Team di sicurezza interni ai vendor**: Attraverso audit di codice, penetration testing e programmi di bug bounty
- **Attori malevoli**: Cybercriminali, gruppi APT (Advanced Persistent Threat) o state-sponsored actors che scoprono vulnerabilità per sfruttarle

Il momento della scoperta è critico poiché determina chi detiene la conoscenza della vulnerabilità e come questa conoscenza verrà utilizzata. Nel caso peggiore, quando una vulnerabilità viene scoperta prima da attori malevoli che dai difensori, si crea una "vulnerabilità zero-day" che può essere sfruttata prima che qualsiasi difesa sia disponibile.

### 2.2.3 Fase 3: Sfruttamento della Vulnerabilità

Lo sfruttamento rappresenta il momento in cui un attaccante utilizza attivamente la vulnerabilità per compromettere sistemi. Questo può avvenire:

- **Prima della disclosure** (zero-day exploit): L'attaccante sfrutta una vulnerabilità sconosciuta al vendor e alla comunità di sicurezza
- **Dopo la disclosure ma prima della patch**: L'attaccante sfrutta la finestra temporale tra l'annuncio della vulnerabilità e il rilascio della correzione
- **Dopo il rilascio della patch**: L'attaccante sfrutta sistemi non ancora aggiornati

Xiao et al. (2018) hanno condotto uno studio approfondito sui profili di rischio delle vulnerabilità, analizzando i ritardi nel patching e i sintomi di infezione. I loro risultati dimostrano che esiste una correlazione significativa tra i ritardi nell'applicazione delle patch e la probabilità di sfruttamento: le vulnerabilità che rimangono non patchate più a lungo hanno maggiori probabilità di essere attivamente sfruttate.

### 2.2.4 Fase 4: Divulgazione della Vulnerabilità (Disclosure)

La divulgazione è il processo attraverso cui l'esistenza di una vulnerabilità viene comunicata pubblicamente o al vendor interessato. Esistono diversi modelli di disclosure:

- **Responsible Disclosure**: Il ricercatore notifica privatamente il vendor e attende un periodo concordato prima della divulgazione pubblica, permettendo lo sviluppo di una patch
- **Full Disclosure**: La vulnerabilità viene immediatamente resa pubblica, con o senza una patch disponibile
- **Coordinated Vulnerability Disclosure (CVD)**: Un processo strutturato che coinvolge vendor, ricercatori e organizzazioni di coordinamento come CERT/CC

La disclosure innesca una corsa contro il tempo: da un lato i vendor devono sviluppare e rilasciare una patch, dall'altro gli attaccanti iniziano a sviluppare exploit. Secondo Dissanayake et al. (2021b), questa dinamica crea una pressione enorme sulle organizzazioni che devono applicare le patch prima che gli exploit diventino ampiamente disponibili.

### 2.2.5 Fase 5: Rilascio della Patch di Sicurezza

Il rilascio della patch da parte del vendor rappresenta un momento cruciale nel ciclo di vita. Tuttavia, il semplice rilascio non elimina la vulnerabilità: la patch deve essere acquisita, testata e installata da ogni organizzazione che utilizza il software affetto.

I vendor adottano diverse strategie di rilascio:

- **Patch Tuesday**: Microsoft rilascia aggiornamenti di sicurezza il secondo martedì di ogni mese
- **Rilascio continuo**: Altri vendor rilasciano patch non appena sono pronte
- **Out-of-band patches**: Rilasci di emergenza per vulnerabilità critiche attivamente sfruttate

Questa variabilità nelle pratiche di rilascio complica ulteriormente la gestione per le organizzazioni che utilizzano software di molteplici vendor, ciascuno con il proprio ciclo di rilascio.

### 2.2.6 Fase 6: Applicazione della Patch

L'applicazione della patch rappresenta il focus del Security Patch Management e la fase finale del ciclo di vita della vulnerabilità. Solo quando la patch è stata effettivamente installata e verificata su tutti i sistemi interessati, la vulnerabilità può considerarsi remediata per quell'organizzazione.

Questa fase comprende in realtà molteplici attività: recupero delle informazioni sulla patch, valutazione dell'applicabilità, testing in ambiente controllato, pianificazione del deployment, installazione effettiva e verifica post-deployment. Ciascuna di queste attività introduce potenziali ritardi e punti di fallimento.

### 2.2.7 La Finestra di Esposizione

Un concetto critico che emerge dal ciclo di vita è quello della "finestra di esposizione" (exposure window), ovvero il periodo durante il quale un sistema rimane vulnerabile a un attacco. Questa finestra si estende dal momento in cui la vulnerabilità diventa sfruttabile (potenzialmente dalla sua introduzione, se scoperta da attori malevoli) fino al momento in cui la patch viene effettivamente applicata.

Marconato et al. (2013) hanno proposto un modello di sicurezza basato sul ciclo di vita delle vulnerabilità che considera esplicitamente questa finestra di esposizione. Il loro lavoro dimostra come la riduzione di questa finestra sia l'obiettivo primario del Security Patch Management, e come ogni ritardo in qualsiasi fase del processo estenda proporzionalmente il periodo di rischio.

## 2.3 Anatomia del Processo di Security Patch Management

Il processo di Security Patch Management si articola in cinque fasi principali, ciascuna caratterizzata da attività specifiche, requisiti e potenziali punti di fallimento (Dissanayake et al., 2021a; Li et al., 2019; Tiefenau et al., 2020).

### 2.3.1 Recupero delle Informazioni sulle Patch

La prima fase riguarda l'acquisizione delle informazioni relative alle nuove patch disponibili. I professionisti IT devono venire a conoscenza dell'esistenza di nuove patch e acquisirle dai vendor software. Secondo Li et al. (2019), le fonti moderne di informazione sulle patch sono estremamente frammentate e includono: advisory di sicurezza (utilizzate dal 78% dei professionisti), notifiche ufficiali dei vendor (71%), mailing list (53%), forum online (52%), notizie (39%), blog (38%) e social media (18%).

### 2.3.2 Scansione delle Vulnerabilità, Valutazione e Prioritizzazione

In questa fase, i professionisti eseguono la scansione dei sistemi per identificare le vulnerabilità presenti, valutare l'applicabilità delle patch nel loro contesto organizzativo, stimare il rischio e prioritizzare le decisioni di patching. La valutazione deve considerare sia il rischio tecnico (gravità della vulnerabilità, esposizione del sistema) sia il rischio di business (criticità del sistema per le operazioni aziendali).

### 2.3.3 Test delle Patch

La fase di test è cruciale per garantire che l'applicazione della patch non introduca problemi nei sistemi di produzione. Include la configurazione di ambienti di test, l'installazione della patch in ambiente controllato, la verifica della stabilità e funzionalità, la risoluzione delle dipendenze e la preparazione dei piani di rollback.

### 2.3.4 Deployment delle Patch

Il deployment riguarda l'installazione effettiva delle patch sui sistemi di produzione. Questa fase deve essere attentamente pianificata per minimizzare l'impatto sulle operazioni aziendali, gestire i riavvii necessari e garantire che tutti i sistemi target vengano aggiornati.

### 2.3.5 Verifica Post-Deployment

L'ultima fase comprende il monitoraggio dei sistemi dopo l'applicazione delle patch per rilevare eventuali problemi, la verifica che le patch siano state effettivamente applicate e la gestione di eventuali issues post-deployment.

## 2.4 La Dimensione del Problema

### 2.4.1 Evidenze Empiriche dei Fallimenti

Nonostante il rilascio tempestivo di patch di sicurezza da parte dei vendor, la maggioranza degli attacchi informatici nel mondo reale è il risultato dello sfruttamento di vulnerabilità note per le quali esisteva già una patch disponibile (Dissanayake et al., 2021a; Accenture Security, 2020). Questa apparente contraddizione rivela la profondità del problema del Security Patch Management.

Secondo un report industriale del 2020, oltre il 50% delle organizzazioni non riesce ad applicare patch per vulnerabilità critiche entro le 72 ore raccomandate dal loro rilascio, e circa il 15% rimane senza patch anche dopo 30 giorni (Automox, 2020). Questi dati dimostrano che le organizzazioni moderne stanno lottando per soddisfare i requisiti di "patch early and often".

### 2.4.2 Conseguenze dei Ritardi nel Patching

I ritardi nell'applicazione delle patch hanno conseguenze che vanno ben oltre il rischio teorico. Casi documentati illustrano la gravità del problema:

**Il caso Equifax (2017)**: Una delle più gravi violazioni di dati nella storia è stata causata dal mancato patching di una vulnerabilità nota (CVE-2017-5638) nel framework Apache Struts. La patch era disponibile da due mesi quando gli attaccanti hanno sfruttato la vulnerabilità, esponendo i dati personali di 143 milioni di cittadini americani (Mathews, 2017; Goodin, 2017). L'ex CEO di Equifax ha attribuito la violazione a "una singola persona che ha fallito nel deployare la patch", evidenziando come un singolo punto di fallimento nel processo possa avere conseguenze catastrofiche.

**Attacco ransomware a ospedale tedesco (2020)**: Un attacco informatico a un ospedale universitario in Germania ha causato la morte di una paziente che ha dovuto essere trasferita in un'altra struttura a causa dell'indisponibilità dei sistemi. L'attacco ha sfruttato una vulnerabilità per la quale esisteva una patch disponibile (Eddy & Perlroth, 2020). Questo caso dimostra come nel settore sanitario, i ritardi nel patching possano avere conseguenze letali.

### 2.4.3 Il Paradosso della Sicurezza vs. Disponibilità

Un aspetto fondamentale del problema risiede nel conflitto intrinseco tra sicurezza e disponibilità. L'applicazione di patch richiede frequentemente riavvii dei sistemi, che comportano interruzioni del servizio. In contesti mission-critical come ospedali, infrastrutture critiche o servizi finanziari, anche brevi interruzioni possono avere impatti significativi.

Dissanayake et al. (2021b), nel loro studio sul settore sanitario, hanno documentato come i professionisti si trovino costantemente a bilanciare il rischio di lasciare vulnerabilità non patchate contro il rischio di causare downtime a sistemi critici. Un partecipante allo studio ha descritto situazioni in cui "A ha bisogno di B per funzionare, e viceversa, ma quando abbiamo accidentalmente messo B offline, A non funzionava. È stato allora che ci sono venuti i brividi" riferendosi a sistemi medicali critici.

## 2.5 Le Sfide Socio-Tecniche del Security Patch Management

Il Security Patch Management è intrinsecamente un'impresa socio-tecnica, dove le interazioni umane e tecnologiche sono strettamente accoppiate (Dissanayake et al., 2021b). L'analisi sistematica della letteratura ha identificato 14 sfide principali, classificabili in sfide comuni all'intero processo e sfide specifiche per ciascuna fase.

### 2.5.1 Sfide di Collaborazione, Coordinazione e Comunicazione

Il processo di Security Patch Management è uno sforzo collaborativo che coinvolge molteplici stakeholder: team interni (security manager, ingegneri, amministratori di sistema), vendor software di terze parti (Microsoft, Oracle, Adobe), e clienti/utenti finali. Gli interessi conflittuali e le interdipendenze tra queste parti rendono il Security Patch Management un'impresa intrinsecamente complessa (Dissanayake et al., 2021b; Nappa et al., 2015).

Le problematiche specifiche includono:

- **Overhead amministrativo**: Il coordinamento con diversi stakeholder con interessi conflittuali richiede significativo effort gestionale
- **Problemi di delega**: Mancanza di accountability e ruoli/responsabilità ben definiti porta a situazioni in cui nessuno si assume la responsabilità di specifiche attività
- **Conflitti di interesse**: I team di sicurezza spingono per patching immediato, mentre i team operativi resistono per evitare interruzioni del servizio
- **Mancanza di collaborazione**: Silos organizzativi impediscono la condivisione efficace di informazioni critiche

Dissanayake et al. (2021b) hanno osservato nel loro studio longitudinale come la mancanza di consapevolezza delle dipendenze, derivante dalla distribuzione localizzata del lavoro, creasse sfide aggiuntive nel coordinamento delle dipendenze inter-team, impedendo la misurazione accurata della progressione delle attività di patching.

### 2.5.2 Impatto delle Policy Organizzative

La necessità di bilanciare la conformità alle policy organizzative con il mantenimento della sicurezza software è riconosciuta come una sfida significativa (Dissanayake et al., 2021a). Le policy stabilite dal management superiore, come quelle che richiedono minime interruzioni di servizio o approvazioni multiple prima di modifiche ai sistemi di produzione, talvolta contraddicono direttamente la necessità di applicare tempestivamente patch di sicurezza emergenziali.

Tiefenau et al. (2020), nel loro studio sugli amministratori di sistema, hanno documentato come i professionisti si trovino frequentemente intrappolati tra requisiti di compliance contrastanti: da un lato standard di sicurezza che richiedono patching tempestivo, dall'altro SLA (Service Level Agreement) che penalizzano il downtime non pianificato.

### 2.5.3 Complessità Crescente delle Patch

Il rapido aumento del numero e della diversità degli attacchi ha comportato un tasso accelerato di rilascio delle patch, creando una situazione sempre più difficile per i professionisti IT (Dissanayake et al., 2021a). I fattori che contribuiscono a questa complessità includono:

**Eterogeneità**: Le organizzazioni moderne operano ambienti estremamente eterogenei con molteplici sistemi operativi (Windows, Linux, macOS), diverse versioni di ciascuno, e centinaia o migliaia di applicazioni software. Come evidenziato da un partecipante allo studio di Dissanayake et al. (2021b): "Abbiamo circa 15-16 versioni di Windows 10. Quindi, prima del patching dobbiamo vedere quale versione sta girando su quale server? Qual è il numero di build? Stiamo usando l'ultima versione? È tantissimo!"

**Volume crescente**: Il numero di vulnerabilità scoperte e di patch rilasciate cresce anno dopo anno. I professionisti descrivono la situazione come impossibile da gestire: "C'è semplicemente troppo da controllare! Stiamo gestendo 1500 server, non abbiamo tempo di guardare ogni patch per ogni server" (Dissanayake et al., 2021b).

**Superficie di attacco estesa**: Le strutture organizzative grandi e distribuite, con molteplici sedi, ambienti cloud ibridi e forza lavoro remota, amplificano la complessità della gestione delle patch.

### 2.5.4 Limitazioni degli Strumenti Esistenti

Le limitazioni degli strumenti disponibili rappresentano un ostacolo maggiore al raggiungimento degli obiettivi del Security Patch Management (Dissanayake et al., 2021a). Le carenze principali includono:

**Mancanza di standardizzazione**: Non esiste una piattaforma standard per integrare gli strumenti eterogenei utilizzati nelle diverse fasi del processo. Organizzazioni utilizzano strumenti diversi per vulnerability scanning, patch deployment, configuration management, senza integrazione efficace tra di essi.

**Problemi di accuratezza**: Gli strumenti attuali spesso falliscono nel considerare il contesto organizzativo dinamico, producendo falsi positivi o mancando vulnerabilità reali. Come osservato da Holm e Sommestad (2011), esistono differenze significative nell'accuratezza delle scansioni tra diversi tool e diversi sistemi operativi.

**Carenze di scalabilità**: Molti strumenti non sono progettati per gestire ambienti enterprise su larga scala con migliaia di endpoint e centinaia di applicazioni diverse.

**Limitazioni nella gestione delle dipendenze**: Gli strumenti esistenti spesso si focalizzano sul patching a livello di funzione singola, assumendo che il codice vulnerabile risieda all'interno di una sola funzione, senza considerare le interdipendenze complesse tra componenti (Li & Paxson, 2017).

### 2.5.5 L'Inevitabilità dell'Intervento Umano

A causa della complessità crescente e della natura dinamica del Security Patch Management, e delle limitazioni delle tecnologie attuali, l'intervento umano rimane inevitabile in tutto il processo (Dissanayake et al., 2021a). Come osservato da Maurer e Brumley (2012): "Nel tentativo di automatizzare il più possibile il test delle patch, è stato notato che l'intervento umano è inevitabile. Poiché le patch possono cambiare la semantica di un programma, un umano dovrà probabilmente sempre essere nel loop per determinare se i cambiamenti semantici sono significativi."

Tuttavia, il coinvolgimento umano introduce inevitabilmente latenza nel processo. Le decisioni richiedono tempo, la comunicazione tra team richiede tempo, le approvazioni richiedono tempo. Ogni passaggio umano nel processo rappresenta un potenziale punto di ritardo che estende la finestra di esposizione.

### 2.5.6 Carenza di Risorse

Il rischio di ritardi è ulteriormente amplificato dalla mancanza di risorse dedicate al Security Patch Management (Dissanayake et al., 2021a):

**Carenza di competenze**: Il Security Patch Management richiede competenze specializzate che sono scarse sul mercato. I professionisti devono comprendere non solo la sicurezza informatica, ma anche le specificità delle diverse piattaforme, le interdipendenze applicative, e il contesto di business dell'organizzazione.

**Mancanza di linee guida**: Molte organizzazioni non dispongono di processi documentati e linee guida chiare per il Security Patch Management, portando ad approcci ad-hoc e inconsistenti.

**Insufficiente automazione**: Nonostante la disponibilità di alcuni strumenti di automazione, molte organizzazioni continuano a fare affidamento su processi manuali per mancanza di investimenti o competenze per implementare soluzioni automatizzate.

### 2.5.7 Le Dipendenze Tecniche come Ostacolo

Le interdipendenze tra software, hardware e firmware creano complessità aggiuntive che complicano significativamente il processo di patching (Dissanayake et al., 2021b).

**Dipendenze tra sistemi operativi e applicazioni**: Le patch del sistema operativo possono influenzare il funzionamento delle applicazioni installate. Le patch delle applicazioni possono richiedere versioni specifiche del sistema operativo. Questa rete di dipendenze deve essere attentamente mappata e gestita.

**Dipendenze circolari**: In casi particolarmente complessi, esistono dipendenze circolari dove il sistema A dipende dal sistema B, e B dipende da A. Come descritto da un partecipante: "Potrebbe esserci una situazione in cui A ha bisogno di B per funzionare, e viceversa, ma quando abbiamo accidentalmente messo B offline quel giorno, A non funzionava" (Dissanayake et al., 2021b).

**Prerequisiti per l'installazione**: Alcune patch richiedono che specifici prerequisiti siano stabiliti prima dell'installazione. Questi prerequisiti possono includere modifiche ai registri di sistema, installazione di pacchetti preparatori, o configurazioni specifiche. Il fallimento nell'identificare e configurare questi prerequisiti porta a errori di installazione.

**Dipendenze con sistemi legacy**: I sistemi legacy rappresentano una minaccia particolare. Molti sistemi critici operano su versioni di software non più supportate dai vendor, creando dipendenze che impediscono l'aggiornamento di altri componenti. Come osservato nello studio: "Ci sono ventisei server 2008 ancora in attesa di essere patchati questo mese. Ma ci sono alcuni server che dobbiamo esaminare per capire perché le patch non si applicano. Anche se abbiamo installato tutti i pacchetti preparatori richiesti, continuano a fare rollback" (Dissanayake et al., 2021b).

### 2.5.8 Le Dipendenze Sociali come Fattore di Complessità

Oltre alle dipendenze tecniche, le dipendenze tra stakeholder creano ulteriori sfide (Dissanayake et al., 2021b).

**Dipendenze interne**: I team interni hanno responsabilità assegnate e interdipendenze nelle loro attività. Le approvazioni, le comunicazioni, il coordinamento delle finestre di manutenzione richiedono tutti sincronizzazione tra team diversi. La mancanza di consapevolezza dei ruoli e delle responsabilità complica questa coordinazione.

**Dipendenze con i vendor**: Le organizzazioni dipendono dai vendor per il rilascio delle patch. Quando diverse applicazioni condividono vulnerabilità (come nel caso del codice condiviso), è necessario coordinare i cicli di rilascio di molteplici vendor. Inoltre, alcune applicazioni di terze parti sono gestite direttamente dai vendor esterni secondo accordi contrattuali, richiedendo sincronizzazione con i loro cicli di patching.

**Dipendenze con i clienti**: Nel caso di organizzazioni che forniscono servizi, le finestre di manutenzione devono essere negoziate con i clienti. Come osservato: "Molti clienti non capiscono sempre il valore del patching di sicurezza, vogliono solo usare il server, e continuano a chiedere: 'perché vuoi riavviarlo ogni tanto, o perché devi aggiornarlo? Funziona, lascialo stare!'" (Dissanayake et al., 2021b).

## 2.6 I Fattori Organizzativi che Amplificano il Problema

### 2.6.1 La Tensione tra Sicurezza e Operatività

Al cuore del problema del Security Patch Management risiede una tensione fondamentale tra l'imperativo di sicurezza e l'imperativo di operatività continuativa. I team di sicurezza sono incentivati a minimizzare il rischio di breach attraverso patching tempestivo; i team operativi sono incentivati a minimizzare le interruzioni del servizio e garantire la stabilità; il business è incentivato a massimizzare la disponibilità dei sistemi per supportare le operazioni commerciali.

Questa tensione non è risolvibile attraverso la sola tecnologia: richiede governance, processi decisionali strutturati, e una cultura organizzativa che bilanci appropriatamente i diversi imperativi.

### 2.6.2 L'Assenza di Visibilità End-to-End

Molte organizzazioni mancano di visibilità completa sul proprio ambiente IT. Asset non documentati, sistemi shadow IT, applicazioni installate senza approvazione, configurazioni non standard: tutti questi fattori creano punti ciechi che rendono impossibile determinare con certezza quali sistemi necessitino di quali patch.

### 2.6.3 La Frammentazione delle Responsabilità

In organizzazioni grandi e complesse, la responsabilità per il Security Patch Management è spesso frammentata tra molteplici team: il team di sicurezza identifica le vulnerabilità, il team di sistema gestisce i server, il team applicativo gestisce le applicazioni, il team di rete gestisce i dispositivi di rete. Questa frammentazione crea gap di responsabilità dove alcune patch possono cadere tra le crepe organizzative.

## 2.7 Sintesi: La Natura Multidimensionale del Problema

L'analisi presentata in questo capitolo rivela che il Security Patch Management non è semplicemente un problema tecnico risolvibile attraverso migliori strumenti o maggiore automazione. È un problema socio-tecnico complesso che coinvolge:

- **Dimensione tecnica**: Complessità delle patch, dipendenze tra componenti, eterogeneità degli ambienti
- **Dimensione organizzativa**: Processi, policy, strutture di governance, allocazione delle risorse
- **Dimensione umana**: Competenze, comunicazione, collaborazione, decision-making
- **Dimensione temporale**: La corsa contro il tempo tra disclosure e remediation

La comprensione di questa natura multidimensionale è prerequisito fondamentale per qualsiasi tentativo di migliorare l'efficacia del Security Patch Management nelle organizzazioni moderne. Le soluzioni parziali che affrontano solo una dimensione del problema sono destinate a produrre risultati limitati.

---

## Riferimenti Bibliografici

Accenture Security. (2020). _2020 Cyber Threatscape Report_. https://www.accenture.com/_acnmedia/PDF-136/Accenture-2020-Cyber-Threatscape-Full-Report.pdf

Automox. (2020). _2020 Cyber Hygiene Report: What You Need to Know Now_. https://patch.automox.com/rs/923-VQX-349/images/Automox_2020_Cyber_Hygiene_Report.pdf

Brykczynski, B., & Small, R. A. (2003). Reducing internet-based intrusions: Effective security patch management. _IEEE Software_, 20(1), 50-57.

Dissanayake, N., Jayatilaka, A., Zahedi, M., & Babar, M. A. (2021a). Software Security Patch Management - A Systematic Literature Review of Challenges, Approaches, Tools and Practices. _arXiv preprint arXiv:2012.00544v3_.

Dissanayake, N., Zahedi, M., Jayatilaka, A., & Babar, M. A. (2021b). A Grounded Theory of the Role of Coordination in Software Security Patch Management. _Proceedings of the 29th ACM Joint European Software Engineering Conference and Symposium on the Foundations of Software Engineering (ESEC/FSE '21)_, 793-805.

Eddy, M., & Perlroth, N. (2020, September 18). Cyber Attack Suspected in German Woman's Death. _The New York Times_. https://www.nytimes.com/2020/09/18/world/europe/cyber-attack-germany-ransomeware-death.html

FIRST. (2019). _Common Vulnerability Scoring System v3.1: Specification Document_. https://www.first.org/cvss/

Goodin, D. (2017, September 14). Failure to patch two-month-old bug led to massive Equifax breach. _Ars Technica_. https://arstechnica.com/information-technology/2017/09/massive-equifax-breach-caused-by-failure-to-patch-two-month-old-bug/

Holm, H., & Sommestad, T. (2011). A quantitative evaluation of vulnerability scanning. _Information Management & Computer Security_, 19(4), 231-247.

Li, F., & Paxson, V. (2017). A Large-Scale Empirical Study of Security Patches. _Proceedings of the 2017 ACM SIGSAC Conference on Computer and Communications Security (CCS)_, 2201-2215.

Li, F., Rogers, L., Mathur, A., Malkin, N., & Chetty, M. (2019). Keepers of the Machines: Examining How System Administrators Manage Software Updates. _Fifteenth Symposium on Usable Privacy and Security (SOUPS 2019)_, 273-288.

Marconato, G. V., Kaâniche, M., & Nicomette, V. (2013). A vulnerability life cycle-based security modeling and evaluation approach. _The Computer Journal_, 56(4), 422-439.

Mathews, L. (2017, September 7). Equifax Data Breach Impacts 143 Million Americans. _Forbes_. https://www.forbes.com/sites/leemathews/2017/09/07/equifax-data-breach-impacts-143-million-americans/

Maurer, M., & Brumley, D. (2012). Tachyon: Tandem execution for efficient live patch testing. _USENIX Security Symposium_.

Mell, P., Bergeron, T., & Henning, D. (2005). Creating a patch and vulnerability management program. _NIST Special Publication 800-40_.

Nappa, A., Johnson, R., Bilge, L., Caballero, J., & Dumitras, T. (2015). The Attack of the Clones: A Study of the Impact of Shared Code on Vulnerability Patching. _IEEE Symposium on Security and Privacy (S&P)_, 692-708.

NIST. (2012). _Guide for Conducting Risk Assessments_. NIST Special Publication 800-30 Rev. 1.

Souppaya, M., & Scarfone, K. (2013). Guide to Enterprise Patch Management Technologies. _NIST Special Publication 800-40r3_.

Tiefenau, C., Häring, M., Krombholz, K., & von Zezschwitz, E. (2020). Security, Availability, and Multiple Information Sources: Exploring Update Behavior of System Administrators. _Sixteenth Symposium on Usable Privacy and Security (SOUPS 2020)_, 239-258.

Xiao, C., Sarabi, A., Liu, Y., Li, B., Liu, M., & Dumitras, T. (2018). From patching delays to infection symptoms: Using risk profiles for an early discovery of vulnerabilities exploited in the wild. _USENIX Security Symposium_.