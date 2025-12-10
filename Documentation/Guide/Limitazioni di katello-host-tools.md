## Architettura del Reporting in Katello
Per i sistemi RHEL, Katello utilizza un meccanismo di reporting basato sui seguenti componenti:

1. **subscription-manager**: gestisce la registrazione dell'host al server Katello
2. **katello-host-tools**: raccoglie informazioni sui pacchetti installati e li confronta con gli errata disponibili
3. **yum/dnf plugin katello**: intercetta le operazioni sui pacchetti e invia report al server

Questi componenti comunicano con il server Katello tramite API REST, inviando periodicamente:
- L'inventario dei pacchetti installati
- Lo stato degli errata applicabili
- Le modifiche ai pacchetti (installazioni, aggiornamenti, rimozioni)

### Incompatibilità con Sistemi Debian/Ubuntu
Il pacchetto `katello-host-tools` presenta le seguenti limitazioni su sistemi Debian/Ubuntu:

**1. Dipendenza da subscription-manager**

`subscription-manager` è uno strumento sviluppato da Red Hat specificamente per la gestione delle sottoscrizioni RHEL. Sebbene esista un porting per Debian, questo non supporta tutte le funzionalità richieste da Katello, in particolare:

- La generazione del consumer certificate nel formato atteso
- L'integrazione con il sistema di content delivery di Katello
- La comunicazione con l'API Candlepin (il backend di gestione sottoscrizioni)

**2. Assenza di plugin APT equivalenti**

Non esiste un equivalente del plugin yum/dnf per APT che possa:
- Intercettare le operazioni sui pacchetti
- Mappare i pacchetti agli errata (che non esistono)
- Inviare report strutturati al server Katello

**3. Differenze nel formato dei metadati**

Il formato dei metadati dei pacchetti DEB differisce significativamente da quello RPM:

|Aspetto|RPM (RHEL)|DEB (Ubuntu)|
|---|---|---|
|Database pacchetti|`/var/lib/rpm`|`/var/lib/dpkg`|
|Formato metadati|XML strutturato|File di testo semplice|
|Informazioni CVE|Incluse in updateinfo.xml|Non presenti|
|Classificazione update|Security/Bugfix/Enhancement|Non classificati|

---

## Conseguenze Pratiche

### Funzionalità Non Disponibili per Ubuntu

A causa delle limitazioni descritte, le seguenti funzionalità di Katello **non sono disponibili** per host Ubuntu/Debian:

|Funzionalità|Disponibilità|
|---|---|
|Visualizzazione pacchetti installati nella UI|Non disponibile|
|Conteggio errata applicabili|Non disponibile|
|Classificazione severity (Critical, High, etc.)|Non disponibile|
|Associazione CVE ai pacchetti|Non disponibile|
|Report di compliance|Non disponibile|
|Installazione pacchetti da UI|Non disponibile|
|Errata management|Non disponibile|

### Funzionalità Disponibili per Ubuntu

Alcune funzionalità rimangono operative grazie a meccanismi che non dipendono dal sistema di reporting:

|Funzionalità|Disponibilità|Meccanismo|
|---|---|---|
|Sincronizzazione repository DEB|Disponibile|Pulp supporta repository APT|
|Distribuzione repository agli host|Disponibile|Configurazione APT manuale|
|Content View con repository DEB|Disponibile|Gestione standard Katello|
|Lifecycle Environment|Disponibile|Gestione standard Katello|
|Remote Execution via SSH|Disponibile|Plugin REX indipendente|
|Esecuzione `apt-get upgrade`|Disponibile|Tramite Remote Execution|
