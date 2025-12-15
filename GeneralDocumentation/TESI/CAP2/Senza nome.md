When we speak about cybersecurity, it involves the protection of assets from intentional 
actions that could harm them. These assets possess a value, which makes them important 
to safeguard.
Assets may be exposed to malicious activities due to vulnerabilities. Vulnerabilities are weaknesses within the system, and they can exist in the system managing the asset or even in systems designed to provide security protection, if they themselves have vulnerabilities.
These vulnerabilities can be exploited by attackers, who represent threats to the 
system. Threats contribute to what is known as security risk. This risk is determined 
not only by the existence of threats and vulnerabilities but also by the value of the asset 
in question.
An increase in the number or severity of threats will elevate the security risk. Additionally, the risk is influenced by the type of threat involved. To mitigate these risks, we introduce security control. Security controls are measures designed to protect the system by defending against threats (e.g., attackers acting as threats to the system). By implementing security controls, the security risk is reduced. Security controls enforce security requirements, which define the desired level of 
risk reduction based on the identified security risks. These requirements guide the implementation of controls to ensure effective protection.
A vulnerability refers to a specific weak point in a system, such as a software version 
with a known flaw. In contrast, a weakness is a broader term that describes a type of 
vulnerability, such as a buffer overflow, representing a general class of issues.
A vulnerability, being an instance of a weakness, can be exploited through an exploit, 
which is typically a script or program designed to take advantage of the vulnerability. 
An attacker uses the exploit to execute an attack. If an attack is successful, it can result in a failure or incident, signifying that a security policy has been violated. Security policies are established to protect the software and its associated assets. A violation of the security policy indicates that an asset has been damaged or compromised due to the incident, resulting in harm to the system or its stakeholders.
## Vulnerability and vulnerability life cycle
Una vulnerabilità software rappresenta una debolezza o un difetto presente nel codice, nella progettazione, nell'implementazione o nella configurazione di un sistema software che può essere sfruttata da un attaccante per compromettere la sicurezza del sistema stesso. Il National Institute of Standards and Technology (NIST) definisce formalmente una vulnerabilità come "una debolezza in un sistema informativo, nelle procedure di sicurezza del sistema, nei controlli interni o nell'implementazione che potrebbe essere sfruttata da una fonte di minaccia" (NIST. (2012). _Guide for Conducting Risk Assessments_. NIST Special Publication 800-30 Rev. 1).
A vulnerability can manifest as a bug or a flaw in various parts of a system. These vulnerabilities may occur in the design or specification phase, for example, when code is developed based on incorrect specifications or when the specifications themselves are not met. Vulnerabilities can also arise in the implementation phase, such as when a bug exists in the program code, or in the configuration phase, where configuration files of a system component are misconfigured in a way that compromises security. In some cases, the component containing the vulnerability could be a third-party library, introducing what is known as exposed logic. Since such libraries are outside of 
our direct control, any vulnerabilities they contain make our system vulnerable if they 
are integrated.
A weakness, on the other hand, is not necessarily a bug. For example, storing a 
password in plain text is not a bug because the program may function as expected, but 
it is still a vulnerability due to the flaw in security practices.
Bugs and flaws can exist across various parts of a system’s artifacts. A classical bug is 
typically found in the implementation, such as errors in the program’s code. However, 
issues may also arise in the design or specification phases. For instance, if a system is 
designed in a way that allows unintended access, the problem lies in the design, not the 
implementation.
Vulnerabilities can also emerge in configuration files, where misconfigurations might 
expose the system to threats. Additionally, vulnerabilities in third-party libraries can 
propagate to our system, creating security risks if such libraries are used.
Ultimately, vulnerabilities are dangerous because they can be exploited to compromise system security. Importantly, if a bug or a flaw cannot be exploited, it is not 
considered a vulnerability.

The lifecycle of a vulnerability consists of several key events:
- Creation: A vulnerability is created during the design, implementation, or operation of a system.
- Discovery: Vulnerabilities are unintended and remain unknown until someone discovers them.
- Disclosure: After discovery, a vulnerability can be made public and disclosed (d).
- Exploit: An exploit is developed for a known vulnerability (e).
- Exploit disclosure: The exploit is disclosed and made public, often through public or private repositories (ed).
- Patch: A patch is created to address the vulnerability. Once applied, the vulnerability is mitigated or eliminated (p).
- Patch publication: The patch is made publicly available (pp).
- The lifecycle of the vulnerability ends when the patch has been widely applied across systems.
Vulnerability repositories provide information about vulnerabilities and can be
categorized as follows:
- Public repositories (accessible to everyone):
	- MITRE Common Vulnerabilities and Exposures (CVE)
	- NIST National Vulnerability Database (NVD), which includes entries corresponding to CVEs.
- Private repositories (accessible under subscription):
	- Exodus Intelligence 
	- Zerodium
In addition, MITRE maintains a repository called Common Weakness Enumeration 
(CWE) for categorizing software weaknesses. From the NVD repository, some important terms include:
- CVSS: Common Vulnerability Scoring System, a method for scoring vulnerabilities based on various factors, including a so-called vector.
- Access Vector (AV): Indicates the access required for an attacker to exploit the vulnerability (e.g., network access implies higher risk compared to local physical access).
- Access Complexity (AC): Represents the difficulty of exploiting the vulnerability.
The illustrates the vulnerability lifecycle. On the left, it shows the vulnerability 
progression: initially absent, then created but unknown, followed by discovery and private 
knowledge, and eventually public disclosure. The central section focuses on the exploit 
lifecycle, while the right section represents the patch lifecycle
![[image.png]]
The initial state is when the vulnerability is absent. Then, there is the creation of the vulnerability, but it remains unknown. Following this, the discovery phase occurs, which introduces several possible scenarios. At this stage, the vulnerability is known but only privately. The last crossed line in the figure signifies the point where the vulnerability becomes publicly known.
One possible scenario is that the vulnerability is discovered by developers. In this case, no exploit exists, and the process follows the left branch, where the vulnerability is disclosed, and a patch is published (d+pp). This is the best case because the patch is created before any exploit exists.
Alternatively, the discovery may be made by hackers, as shown in the middle branch. Here, the vulnerability becomes exploitable, resulting in a 0-day vulnerability. Developers are unaware of the vulnerability, but an exploit exists, giving them zero days to fix the issue. If developers subsequently discover the vulnerability, a patch can be created moving the process from the mid-branch to the left one.
Another scenario involves hackers disclosing both the vulnerability and the exploit full disclosure), represented as the d+ep event. This is the riskiest scenario, as the risk remains high until a patch is both created and installed. Even after the patch is created, the risk persists if it is not yet widely deployed.
In some cases, developers are informed about the vulnerability without the exploit being made public. This is the responsible disclosure scenario, represented on the right side, where developers have a certain amount of time to create a patch before the vulnerability is disclosed. 
![[image-1 1.png]]
The figure above illustrates a timeline example of responsible disclosure, which does not always guarantee low risk. In the first case, developers successfully fix the problem within the grace time, the period given by the vulnerability discoverer to address the issue. In the second case, developers fail to meet the deadline, causing the risk to grow immediately. The risk remains high until the patch is created, published, and installed.

La divulgazione è il processo attraverso cui l'esistenza di una vulnerabilità viene comunicata pubblicamente o al vendor interessato. Esistono diversi modelli di disclosure:

- **Responsible Disclosure**: Il ricercatore notifica privatamente il vendor e attende un periodo concordato prima della divulgazione pubblica, permettendo lo sviluppo di una patch
- **Full Disclosure**: La vulnerabilità viene immediatamente resa pubblica, con o senza una patch disponibile
- **Coordinated Vulnerability Disclosure (CVD)**: Un processo strutturato che coinvolge vendor, ricercatori e organizzazioni di coordinamento come CERT/CC

La disclosure innesca una corsa contro il tempo: da un lato i vendor devono sviluppare e rilasciare una patch, dall'altro gli attaccanti iniziano a sviluppare exploit. Secondo Dissanayake et al. (2021b), questa dinamica crea una pressione enorme sulle organizzazioni che devono applicare le patch prima che gli exploit diventino ampiamente disponibili.

Rilascio della Patch di Sicurezza

Il rilascio della patch da parte del vendor rappresenta un momento cruciale nel ciclo di vita. Tuttavia, il semplice rilascio non elimina la vulnerabilità: la patch deve essere acquisita, testata e installata da ogni organizzazione che utilizza il software affetto.

I vendor adottano diverse strategie di rilascio:

- **Patch Tuesday**: Microsoft rilascia aggiornamenti di sicurezza il secondo martedì di ogni mese
- **Rilascio continuo**: Altri vendor rilasciano patch non appena sono pronte
- **Out-of-band patches**: Rilasci di emergenza per vulnerabilità critiche attivamente sfruttate

Questa variabilità nelle pratiche di rilascio complica ulteriormente la gestione per le organizzazioni che utilizzano software di molteplici vendor, ciascuno con il proprio ciclo di rilascio.
## Le Patch di Sicurezza
Le patch di sicurezza software sono definite come "porzioni di codice sviluppate per affrontare problemi di sicurezza identificati nel software" (Mell, P., Bergeron, T., & Henning, D. (2005). Creating a patch and vulnerability management program. _NIST Special Publication 800-40_.). A differenza delle patch funzionali che introducono nuove funzionalità o correggono bug non legati alla sicurezza, le patch di sicurezza hanno lo scopo specifico di eliminare o mitigare vulnerabilità che potrebbero essere sfruttate da attori malevoli per ottenere accesso non autorizzato ai sistemi.
Le patch di sicurezza sono sempre prioritizzate rispetto alle patch non legate alla sicurezza da parte di professionisti e ricercatori del settore, poiché mirano a mitigare vulnerabilità che presentano opportunità sfruttabili per entità malevole (Mell et al., 2005; Brykczynski, B., & Small, R. A. (2003). Reducing internet-based intrusions: Effective security patch management. _IEEE Software_, 20(1), 50-57.). Tuttavia, l'applicazione di una patch non è un'operazione banale: può richiedere riavvii del sistema, può introdurre incompatibilità con software esistente, può alterare il comportamento di applicazioni critiche e, in casi estremi, può essa stessa contenere difetti che causano malfunzionamenti.
Li e Paxson (2017), in uno studio empirico su larga scala, hanno analizzato le caratteristiche delle patch di sicurezza scoprendo che esse variano significativamente in termini di complessità, dimensione e tipo di modifiche apportate. Alcune patch consistono in semplici modifiche di poche righe di codice, mentre altre richiedono ristrutturazioni significative. Alcune necessitano solo dell'installazione del codice aggiornato, mentre altre richiedono modifiche ai registri di sistema, installazione di pacchetti preparatori o configurazioni specifiche prima che la patch possa prendere effetto.

Il Security Patch Management può essere definito come:

> _"Un processo multidimensionale di identificazione, acquisizione, test, installazione e verifica delle patch di sicurezza per prodotti e sistemi software"_ (Dissanayake et al., 2021a; Souppaya & Scarfone, 2013).

Questa pratica di sicurezza è progettata per prevenire proattivamente lo sfruttamento delle vulnerabilità presenti nei prodotti software e nei sistemi distribuiti all'interno dell'ambiente IT di un'organizzazione (Mell et al., 2005). Un processo di Security Patch Management efficace è essenziale per sostenere la triade CIA (Confidentiality, Integrity, Availability) dei sistemi IT.

È fondamentale distinguere il Security Patch Management dallo sviluppo delle patch. Mentre lo sviluppo delle patch è responsabilità del vendor del software (che identifica la vulnerabilità, sviluppa la correzione e la rilascia), il Security Patch Management riguarda il processo attraverso il quale un'organizzazione cliente applica tali patch ai propri sistemi dopo che queste sono state rese disponibili (Dissanayake et al., 2021a). Questa distinzione è cruciale per comprendere le sfide specifiche affrontate dai team IT aziendali.

L'applicazione della patch rappresenta il focus del Security Patch Management e la fase finale del ciclo di vita della vulnerabilità. Solo quando la patch è stata effettivamente installata e verificata su tutti i sistemi interessati, la vulnerabilità può considerarsi remediata per quell'organizzazione.

Questa fase comprende in realtà molteplici attività: recupero delle informazioni sulla patch, valutazione dell'applicabilità, testing in ambiente controllato, pianificazione del deployment, installazione effettiva e verifica post-deployment. Ciascuna di queste attività introduce potenziali ritardi e punti di fallimento.
Un concetto critico che emerge dal ciclo di vita è quello della "finestra di esposizione" (exposure window), ovvero il periodo durante il quale un sistema rimane vulnerabile a un attacco. Questa finestra si estende dal momento in cui la vulnerabilità diventa sfruttabile (potenzialmente dalla sua introduzione, se scoperta da attori malevoli) fino al momento in cui la patch viene effettivamente applicata.

Marconato et al. (2013) hanno proposto un modello di sicurezza basato sul ciclo di vita delle vulnerabilità che considera esplicitamente questa finestra di esposizione. Il loro lavoro dimostra come la riduzione di questa finestra sia l'obiettivo primario del Security Patch Management, e come ogni ritardo in qualsiasi fase del processo estenda proporzionalmente il periodo di rischio.

## La Dimensione del Problema
Nonostante il rilascio tempestivo di patch di sicurezza da parte dei vendor, la maggioranza degli attacchi informatici nel mondo reale è il risultato dello sfruttamento di vulnerabilità note per le quali esisteva già una patch disponibile (Dissanayake et al., 2021a; Accenture Security, 2020). Questa apparente contraddizione rivela la profondità del problema del Security Patch Management.
Secondo un report industriale del 2020, oltre il 50% delle organizzazioni non riesce ad applicare patch per vulnerabilità critiche entro le 72 ore raccomandate dal loro rilascio, e circa il 15% rimane senza patch anche dopo 30 giorni (Automox, 2020). Questi dati dimostrano che le organizzazioni moderne stanno lottando per soddisfare i requisiti di "patch early and often".

I ritardi nell'applicazione delle patch hanno conseguenze che vanno ben oltre il rischio teorico. Casi documentati illustrano la gravità del problema:

**Il caso Equifax (2017)**: Una delle più gravi violazioni di dati nella storia è stata causata dal mancato patching di una vulnerabilità nota (CVE-2017-5638) nel framework Apache Struts. La patch era disponibile da due mesi quando gli attaccanti hanno sfruttato la vulnerabilità, esponendo i dati personali di 143 milioni di cittadini americani (Mathews, 2017; Goodin, 2017). L'ex CEO di Equifax ha attribuito la violazione a "una singola persona che ha fallito nel deployare la patch", evidenziando come un singolo punto di fallimento nel processo possa avere conseguenze catastrofiche.

**Attacco ransomware a ospedale tedesco (2020)**: Un attacco informatico a un ospedale universitario in Germania ha causato la morte di una paziente che ha dovuto essere trasferita in un'altra struttura a causa dell'indisponibilità dei sistemi. L'attacco ha sfruttato una vulnerabilità per la quale esisteva una patch disponibile (Eddy & Perlroth, 2020). Questo caso dimostra come nel settore sanitario, i ritardi nel patching possano avere conseguenze letali.


Un aspetto fondamentale del problema risiede nel conflitto intrinseco tra sicurezza e disponibilità. L'applicazione di patch richiede frequentemente riavvii dei sistemi, che comportano interruzioni del servizio. In contesti mission-critical come ospedali, infrastrutture critiche o servizi finanziari, anche brevi interruzioni possono avere impatti significativi.

Dissanayake et al. (2021b), nel loro studio sul settore sanitario, hanno documentato come i professionisti si trovino costantemente a bilanciare il rischio di lasciare vulnerabilità non patchate contro il rischio di causare downtime a sistemi critici. Un partecipante allo studio ha descritto situazioni in cui "A ha bisogno di B per funzionare, e viceversa, ma quando abbiamo accidentalmente messo B offline, A non funzionava. È stato allora che ci sono venuti i brividi" riferendosi a sistemi medicali critici.

Il Security Patch Management è intrinsecamente un'impresa socio-tecnica, dove le interazioni umane e tecnologiche sono strettamente accoppiate (Dissanayake et al., 2021b). L'analisi sistematica della letteratura ha identificato 14 sfide principali, classificabili in sfide comuni all'intero processo e sfide specifiche per ciascuna fase.
Il processo di Security Patch Management è uno sforzo collaborativo che coinvolge molteplici stakeholder: team interni (security manager, ingegneri, amministratori di sistema), vendor software di terze parti (Microsoft, Oracle, Adobe), e clienti/utenti finali. Gli interessi conflittuali e le interdipendenze tra queste parti rendono il Security Patch Management un'impresa intrinsecamente complessa (Dissanayake et al., 2021b; Nappa et al., 2015).

Le problematiche specifiche includono:

- **Overhead amministrativo**: Il coordinamento con diversi stakeholder con interessi conflittuali richiede significativo effort gestionale
- **Problemi di delega**: Mancanza di accountability e ruoli/responsabilità ben definiti porta a situazioni in cui nessuno si assume la responsabilità di specifiche attività
- **Conflitti di interesse**: I team di sicurezza spingono per patching immediato, mentre i team operativi resistono per evitare interruzioni del servizio
- **Mancanza di collaborazione**: Silos organizzativi impediscono la condivisione efficace di informazioni critiche

Dissanayake et al. (2021b) hanno osservato nel loro studio longitudinale come la mancanza di consapevolezza delle dipendenze, derivante dalla distribuzione localizzata del lavoro, creasse sfide aggiuntive nel coordinamento delle dipendenze inter-team, impedendo la misurazione accurata della progressione delle attività di patching.
La necessità di bilanciare la conformità alle policy organizzative con il mantenimento della sicurezza software è riconosciuta come una sfida significativa (Dissanayake et al., 2021a). Le policy stabilite dal management superiore, come quelle che richiedono minime interruzioni di servizio o approvazioni multiple prima di modifiche ai sistemi di produzione, talvolta contraddicono direttamente la necessità di applicare tempestivamente patch di sicurezza emergenziali.
Tiefenau et al. (2020), nel loro studio sugli amministratori di sistema, hanno documentato come i professionisti si trovino frequentemente intrappolati tra requisiti di compliance contrastanti: da un lato standard di sicurezza che richiedono patching tempestivo, dall'altro SLA (Service Level Agreement) che penalizzano il downtime non pianificato.
Il rapido aumento del numero e della diversità degli attacchi ha comportato un tasso accelerato di rilascio delle patch, creando una situazione sempre più difficile per i professionisti IT (Dissanayake et al., 2021a). I fattori che contribuiscono a questa complessità includono:

**Eterogeneità**: Le organizzazioni moderne operano ambienti estremamente eterogenei con molteplici sistemi operativi (Windows, Linux, macOS), diverse versioni di ciascuno, e centinaia o migliaia di applicazioni software. Come evidenziato da un partecipante allo studio di Dissanayake et al. (2021b): "Abbiamo circa 15-16 versioni di Windows 10. Quindi, prima del patching dobbiamo vedere quale versione sta girando su quale server? Qual è il numero di build? Stiamo usando l'ultima versione? È tantissimo!"

**Volume crescente**: Il numero di vulnerabilità scoperte e di patch rilasciate cresce anno dopo anno. I professionisti descrivono la situazione come impossibile da gestire: "C'è semplicemente troppo da controllare! Stiamo gestendo 1500 server, non abbiamo tempo di guardare ogni patch per ogni server" (Dissanayake et al., 2021b).

**Superficie di attacco estesa**: Le strutture organizzative grandi e distribuite, con molteplici sedi, ambienti cloud ibridi e forza lavoro remota, amplificano la complessità della gestione delle patch.

Le limitazioni degli strumenti disponibili rappresentano un ostacolo maggiore al raggiungimento degli obiettivi del Security Patch Management (Dissanayake et al., 2021a). Le carenze principali includono:

**Mancanza di standardizzazione**: Non esiste una piattaforma standard per integrare gli strumenti eterogenei utilizzati nelle diverse fasi del processo. Organizzazioni utilizzano strumenti diversi per vulnerability scanning, patch deployment, configuration management, senza integrazione efficace tra di essi.

**Problemi di accuratezza**: Gli strumenti attuali spesso falliscono nel considerare il contesto organizzativo dinamico, producendo falsi positivi o mancando vulnerabilità reali. Come osservato da Holm e Sommestad (2011), esistono differenze significative nell'accuratezza delle scansioni tra diversi tool e diversi sistemi operativi.

**Carenze di scalabilità**: Molti strumenti non sono progettati per gestire ambienti enterprise su larga scala con migliaia di endpoint e centinaia di applicazioni diverse.

**Limitazioni nella gestione delle dipendenze**: Gli strumenti esistenti spesso si focalizzano sul patching a livello di funzione singola, assumendo che il codice vulnerabile risieda all'interno di una sola funzione, senza considerare le interdipendenze complesse tra componenti (Li & Paxson, 2017).

A causa della complessità crescente e della natura dinamica del Security Patch Management, e delle limitazioni delle tecnologie attuali, l'intervento umano rimane inevitabile in tutto il processo (Dissanayake et al., 2021a). Come osservato da Maurer e Brumley (2012): "Nel tentativo di automatizzare il più possibile il test delle patch, è stato notato che l'intervento umano è inevitabile. Poiché le patch possono cambiare la semantica di un programma, un umano dovrà probabilmente sempre essere nel loop per determinare se i cambiamenti semantici sono significativi." Tuttavia, il coinvolgimento umano introduce inevitabilmente latenza nel processo. Le decisioni richiedono tempo, la comunicazione tra team richiede tempo, le approvazioni richiedono tempo. Ogni passaggio umano nel processo rappresenta un potenziale punto di ritardo che estende la finestra di esposizione.

Il rischio di ritardi è ulteriormente amplificato dalla mancanza di risorse dedicate al Security Patch Management (Dissanayake et al., 2021a):

**Carenza di competenze**: Il Security Patch Management richiede competenze specializzate che sono scarse sul mercato. I professionisti devono comprendere non solo la sicurezza informatica, ma anche le specificità delle diverse piattaforme, le interdipendenze applicative, e il contesto di business dell'organizzazione.

**Mancanza di linee guida**: Molte organizzazioni non dispongono di processi documentati e linee guida chiare per il Security Patch Management, portando ad approcci ad-hoc e inconsistenti.

**Insufficiente automazione**: Nonostante la disponibilità di alcuni strumenti di automazione, molte organizzazioni continuano a fare affidamento su processi manuali per mancanza di investimenti o competenze per implementare soluzioni automatizzate.

## Le Dipendenze Tecniche come Ostacolo

Le interdipendenze tra software, hardware e firmware creano complessità aggiuntive che complicano significativamente il processo di patching (Dissanayake et al., 2021b).

**Dipendenze tra sistemi operativi e applicazioni**: Le patch del sistema operativo possono influenzare il funzionamento delle applicazioni installate. Le patch delle applicazioni possono richiedere versioni specifiche del sistema operativo. Questa rete di dipendenze deve essere attentamente mappata e gestita.

**Dipendenze circolari**: In casi particolarmente complessi, esistono dipendenze circolari dove il sistema A dipende dal sistema B, e B dipende da A. Come descritto da un partecipante: "Potrebbe esserci una situazione in cui A ha bisogno di B per funzionare, e viceversa, ma quando abbiamo accidentalmente messo B offline quel giorno, A non funzionava" (Dissanayake et al., 2021b).

**Prerequisiti per l'installazione**: Alcune patch richiedono che specifici prerequisiti siano stabiliti prima dell'installazione. Questi prerequisiti possono includere modifiche ai registri di sistema, installazione di pacchetti preparatori, o configurazioni specifiche. Il fallimento nell'identificare e configurare questi prerequisiti porta a errori di installazione.

**Dipendenze con sistemi legacy**: I sistemi legacy rappresentano una minaccia particolare. Molti sistemi critici operano su versioni di software non più supportate dai vendor, creando dipendenze che impediscono l'aggiornamento di altri componenti. Come osservato nello studio: "Ci sono ventisei server 2008 ancora in attesa di essere patchati questo mese. Ma ci sono alcuni server che dobbiamo esaminare per capire perché le patch non si applicano. Anche se abbiamo installato tutti i pacchetti preparatori richiesti, continuano a fare rollback" (Dissanayake et al., 2021b).

Oltre alle dipendenze tecniche, le dipendenze tra stakeholder creano ulteriori sfide (Dissanayake et al., 2021b).

**Dipendenze interne**: I team interni hanno responsabilità assegnate e interdipendenze nelle loro attività. Le approvazioni, le comunicazioni, il coordinamento delle finestre di manutenzione richiedono tutti sincronizzazione tra team diversi. La mancanza di consapevolezza dei ruoli e delle responsabilità complica questa coordinazione.

**Dipendenze con i vendor**: Le organizzazioni dipendono dai vendor per il rilascio delle patch. Quando diverse applicazioni condividono vulnerabilità (come nel caso del codice condiviso), è necessario coordinare i cicli di rilascio di molteplici vendor. Inoltre, alcune applicazioni di terze parti sono gestite direttamente dai vendor esterni secondo accordi contrattuali, richiedendo sincronizzazione con i loro cicli di patching.

**Dipendenze con i clienti**: Nel caso di organizzazioni che forniscono servizi, le finestre di manutenzione devono essere negoziate con i clienti. Come osservato: "Molti clienti non capiscono sempre il valore del patching di sicurezza, vogliono solo usare il server, e continuano a chiedere: 'perché vuoi riavviarlo ogni tanto, o perché devi aggiornarlo? Funziona, lascialo stare!'" (Dissanayake et al., 2021b).

Al cuore del problema del Security Patch Management risiede una tensione fondamentale tra l'imperativo di sicurezza e l'imperativo di operatività continuativa. I team di sicurezza sono incentivati a minimizzare il rischio di breach attraverso patching tempestivo; i team operativi sono incentivati a minimizzare le interruzioni del servizio e garantire la stabilità; il business è incentivato a massimizzare la disponibilità dei sistemi per supportare le operazioni commerciali.

Questa tensione non è risolvibile attraverso la sola tecnologia: richiede governance, processi decisionali strutturati, e una cultura organizzativa che bilanci appropriatamente i diversi imperativi.
Molte organizzazioni mancano di visibilità completa sul proprio ambiente IT. Asset non documentati, sistemi shadow IT, applicazioni installate senza approvazione, configurazioni non standard: tutti questi fattori creano punti ciechi che rendono impossibile determinare con certezza quali sistemi necessitino di quali patch.
In organizzazioni grandi e complesse, la responsabilità per il Security Patch Management è spesso frammentata tra molteplici team: il team di sicurezza identifica le vulnerabilità, il team di sistema gestisce i server, il team applicativo gestisce le applicazioni, il team di rete gestisce i dispositivi di rete. Questa frammentazione crea gap di responsabilità dove alcune patch possono cadere tra le crepe organizzative.
