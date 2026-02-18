Problemi riscontrati
### 1. Bug volume mount systemid (UYUNI 2025.10)
Il servizio systemd generato da mgrpxy install non monta la directory /etc/sysconfig/rhn/ nel container proxy-httpd. Lo script uyuni-configure.py all'avvio del container deve scrivere il file systemid (credenziali di autenticazione del proxy verso il server) in quella directory, ma senza il mount il file viene creato solo dentro il container e perso al restart, oppure il container crasha con FileNotFoundError.

**Fix**: Creare la directory sull'host e aggiungere manualmente il volume mount -v /etc/sysconfig/rhn:/etc/sysconfig/rhn al service file di
  uyuni-proxy-httpd.

Attenzione critica: NON creare il file systemid vuoto con touch. Lo script uyuni-configure.py controlla if not os.path.exists() e se trova un file già esistente (anche vuoto) salta la scrittura. Creare solo la directory.

### 2. Checksum mismatch tra systemid e server (Invalid System Credentials)
Il proxy si autentica verso il server tramite un file XML (systemid) che contiene un checksum. Se si esegue il bootstrap Salt dell'host proxy separatamente dalla generazione del config, il bootstrap modifica il checksum nel database del server ma il config.tar.gz mantiene il checksum originale. Il risultato è che il proxy invia un checksum che il server non riconosce, causando errore Invalid System Credentials e HTTP 500 su tutte le richieste dei client.

Causa root: Il comando proxy_container_config_generate_cert crea una registrazione tradizionale (con un checksum). Il bootstrap Salt crea/modifica una registrazione separata, sovrascrivendo il checksum nel database. I due meccanismi di registrazione non sono sincronizzati.

**Fix**: L'ordine delle operazioni è critico (vedi procedura sotto). Il config va generato PRIMA di qualsiasi bootstrap Salt, e il bootstrap va fatto solo DOPO l'installazione dei container.

### 3. Permessi file systemid (unable to access systemid)
Il processo Apache nel container gira come utente wwwrun che non ha accesso a file/directory con permessi restrittivi. La directory deve essere 755 e il file 644. Operazioni come il bootstrap Salt possono modificare i permessi, rendendo il file illeggibile da Apache.

**Fix**: Dopo ogni operazione che tocca /etc/sysconfig/rhn/, verificare e correggere i permessi (chmod 755 sulla directory, chmod 644 sul
  file systemid).

### 4. DNS nel container Server
 Il container del Server UYUNI ha un proprio /etc/hosts gestito da Podman. Non è possibile modificarlo permanentemente con echo >> o sed perché Podman lo rigenera. Se il Server non riesce a risolvere l'FQDN del Proxy, operazioni come il bootstrap dei client via proxy falliscono.

Fix: Configurare una Azure Private DNS Zone con i record di Server e Proxy, oppure utilizzare il DNS aziendale.

  ---

Procedura corretta per il deployment in produzione

  Ordine delle macro-operazioni:

  1. Preparazione VM Proxy - OS, NTP, hostname, firewall, storage, pacchetti (mgrpxy)
  2. Configurazione DNS - Assicurarsi che Server, Proxy e tutti i Client possano risolvere gli FQDN reciproci (Azure Private DNS Zone o DNS aziendale). Includere la risoluzione anche dall'interno del container Server
  3. Generazione config.tar.gz dal Server - Eseguire proxy_container_config_generate_cert sul Server. Questo crea la registrazione tradizionale del proxy con un checksum valido e genera i certificati SSL. Trasferire il file al Proxy
  4. Installazione container sul Proxy - Eseguire mgrpxy install podman con il config.tar.gz
  5. Applicazione fix systemid - Creare SOLO la directory /etc/sysconfig/rhn (con permessi 755, SENZA creare il file), aggiungere il volume  mount al service file di uyuni-proxy-httpd, ricaricare systemd e avviare i servizi nell'ordine: pod prima, httpd dopo
  6. Verifica systemid e funzionamento proxy - Verificare che il file systemid sia popolato con XML valido, che tutti i 6 container siano running, e che non ci siano errori nei log di httpd
  7. Registrazione Salt del Proxy (opzionale) - Se si vuole gestire il proxy via Salt, configurare il salt-minion manualmente (file susemanager.conf con master: \<server-fqdn>) e accettare la key sul Server. Dopo il bootstrap verificare e correggere i permessi del file systemid (chmod 644) e riavviare httpd
  8. Configurazione DNS sui Client - Aggiungere l'FQDN del Proxy su ogni client
  9. Ri-puntamento Client al Proxy - Via Web UI (Details → Connection → Change proxy) oppure manualmente modificando il master nel salt minion config
  10. Verifica end-to-end - Testare che i client scarichino i pacchetti tramite il proxy (dnf repolist, dnf updateinfo list) e che le patch vengano applicate correttamente

 ---
  
Regola fondamentale: MAI eseguire il bootstrap Salt dell'host proxy PRIMA della generazione del config e dell'installazione dei container. Il bootstrap modifica il checksum delle credenziali tradizionali e invalida il systemid nel config.tar.gz.


## Lezioni Apprese dai Test

### Problemi critici

1. **Incompatibilita venv-salt-minion / OpenSSL (CRITICO)**: la versione `venv-salt-minion-3006.0-58.1` richiede OpenSSL >= 3.3.0. Le macchine RHEL 9.4 con repo EUS hanno solo OpenSSL 3.0.7. **Soluzione**: rimuovere la versione 58.1 dal bootstrap repo e tenere la 47.36 compatibile. Dopo la registrazione, il client ricevera l'aggiornamento OpenSSL dai canali UYUNI CLM e potra poi aggiornare `venv-salt-minion`.

2. **Problema uovo-gallina OpenSSL/UYUNI**: per registrarsi su UYUNI serve `venv-salt-minion` (che richiede OpenSSL >= 3.3.0). Per avere OpenSSL >= 3.3.0 serve essere registrati su UYUNI (canali CLM). I repo Red Hat standard (anche non-EUS) arrivano solo fino a OpenSSL 3.0.7-28. La versione 3.5.1 e disponibile solo dai canali UYUNI.

### Problemi operativi

3. **`sudo bash` obbligatorio su Azure**: l'utente `azureuser` non ha privilegi root. Tutti i metodi SSH devono usare `| sudo bash` invece di `| bash`.

4. **FQDN obbligatorio**: `mgr-bootstrap` rifiuta hostname non FQDN. Usare sempre il FQDN completo (es. `uyuni-proxy-test.uyuni.internal`).

5. **Config actions, remote commands e monitoring**: si abilitano nella **Activation Key**, non nello script bootstrap. Lo script `mgr-bootstrap` non ha opzioni `--allow-config-actions` o `--allow-remote-commands`.

6. **Bootstrap repo va creato esplicitamente**: per RHEL9 non era presente di default, serve `mgr-create-bootstrap-repo --create=RHEL9-x86_64-uyuni`.

7. **SSH known_hosts stale**: se una VM viene ricreata, la vecchia chiave SSH nel known_hosts del server (sia `/root/.ssh/known_hosts` che `/var/lib/salt/.ssh/known_hosts`) blocca il bootstrap. Rimuovere con `ssh-keygen -R`.

8. **Una sola sync alla volta**: `spacewalk-repo-sync` non permette istanze multiple.

9. **Bug #4737 (API XML-RPC)**: il parametro `saltSSH` potrebbe richiedere `0` (int) invece di `False` (bool).

10. **Chiave Salt non auto-accettata**: con il bootstrap via script + SSH (Metodo 1), la chiave del minion arriva in `Unaccepted Keys`. Va accettata manualmente con `salt-key -a` o configurando auto-accept nella AK.