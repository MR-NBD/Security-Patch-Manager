# Vault e PKI Uyuni/Salt — Spiegazione Concettuale

---

## Cos'è HashiCorp Vault

Vault è un **cassaforte digitale**. Punto.

Non è specifico per i certificati — nasce per custodire qualsiasi cosa segreta: password, chiavi API, token, credenziali database. Il modulo PKI è una delle sue funzionalità, non il suo scopo principale.

```
VAULT — cosa può custodire
├── Certificati TLS
├── Password database
├── Chiavi API
├── Token applicativi
├── Credenziali cloud
└── Qualsiasi segreto strutturato
```

La caratteristica principale è che **non si accede mai direttamente ai segreti**. Le applicazioni o le persone chiedono a Vault, Vault verifica chi sei e cosa ti è permesso fare, e solo allora ti consegna il segreto — con una scadenza. Non esiste un file da copiare o una cartella da aprire.

### Perché è rilevante qui

Nella tua infrastruttura Vault servirebbe come **CA operativa automatizzata**. Invece di generare manualmente certificati con OpenSSL e spostarli a mano, Vault li emette su richiesta, li traccia, e sa quando scadono.

---

## Le due PKI che esistono già in Uyuni

Quando installi Uyuni con `mgradm install podman`, il sistema crea **due sistemi di certificati completamente separati** che servono scopi diversi.

---

### PKI numero 1 — La CA Uyuni (per il Web e i repository)

```
CA Uyuni (RHN-ORG-TRUSTED-SSL-CERT)
        │
        ├── Certificato HTTPS del Server Uyuni
        │   → usato dalla Web UI
        │   → usato dai client per scaricare pacchetti
        │
        └── Certificato HTTPS del Proxy Uyuni
            → usato dai client collegati al proxy
```

Questa CA viene creata da Uyuni durante il primo avvio. Vive dentro il container server in `/root/ssl-build/`. È una CA self-signed — nessuna autorità esterna la conosce o la valida.

**Il problema**: il browser mostra "Connessione non sicura" perché non riconosce questa CA. I client gestiti da Uyuni devono ricevere il file della CA e importarla manualmente come trusted per far sparire il warning. Non è un problema tecnico grave, ma non è enterprise.

---

### PKI numero 2 — Il PKI di Salt (per la comunicazione interna)

Questo è completamente diverso e **non ha nulla a che fare con i certificati TLS del browser**.

Salt usa un sistema a chiavi asimmetriche per rispondere alla domanda fondamentale: **"come fa il Server a sapere che il client che si connette è davvero lui e non qualcuno che si spaccia per lui?"**

```
Come funziona Salt:

Salt Minion (client) genera una coppia di chiavi propria
        │
        │  al primo avvio invia la chiave pubblica al Master
        ▼
Salt Master (dentro Uyuni) riceve la chiave pubblica
        │
        │  un amministratore la "accetta" (salt-key -a)
        ▼
Da quel momento il Minion è riconosciuto e fidato
        │
        └── tutta la comunicazione è cifrata
            con queste chiavi, non con certificati TLS classici
```

Non esiste una CA che firma qualcosa in questo meccanismo. È un modello **TOFU** — Trust On First Use — simile a quello di SSH. La prima volta ti fidi, poi la chiave è registrata e qualsiasi cambiamento è un alert.

---

### Come i due sistemi si parlano

```
CLIENT GESTITO DA UYUNI
│
│ 1. Si connette al Proxy/Server via HTTPS
│    → usa la PKI numero 1 (certificato TLS)
│    → verifica il certificato del server
│
│ 2. Comunica con Salt Master via porta 4505/4506
│    → usa la PKI numero 2 (chiavi Salt)
│    → canale cifrato separato dall'HTTPS
│
│ Sono due canali paralleli e indipendenti
```

---

## Cosa significa tutto questo per la soluzione proposta

```
COSA RESTA INVARIATO          COSA MIGLIORIAMO
────────────────────          ────────────────
PKI Salt (chiavi minion)  →   rimane esattamente com'è
CA Uyuni per proxy Salt   →   rimane esattamente com'è

Certificato HTTPS Server  →   firmato da Vault (non più self-signed)
Certificato HTTPS Proxy   →   firmato da Vault (non più self-signed)
CA root di fiducia        →   Root CA privata nostra, distribuita ai client
```

In pratica interveniamo **solo sullo strato visibile** — quello che tocca il browser e la comunicazione HTTPS. Salt continua a lavorare esattamente come fa oggi, indisturbato.

---

## Schema complessivo semplificato

```
ROOT CA (nostra, offline)
    │ ha firmato
    ▼
VAULT PKI (nostra, online)
    │ emette
    ▼
Certificato HTTPS Uyuni ──→ Browser si fida, nessun warning
    │
    ▼
UYUNI SERVER
    │
    ├── CA Uyuni interna ──→ Proxy riceve cert, client si fidano
    │
    └── Salt Master ──→ chiavi Salt, sistema separato, non tocchiamo
            │
            ▼
        Salt Minion (client)
        coppia di chiavi propria
        accettata dall'admin
```

---

## Domanda di fondo

La vera domanda è: **hai bisogno di Vault ora?**

Vault aggiunge potenza (multi-tenant, audit, automazione rinnovi) ma aggiunge anche una componente infrastrutturale da gestire.

Un'alternativa più semplice per iniziare è usare **solo OpenSSL** per creare Root CA + Issuing CA manualmente, senza Vault, e gestire tutto a mano. È meno automatizzato ma è sufficiente se i tenant sono pochi e i rinnovi sono rari.

La domanda giusta è: **quanti ambienti/tenant devi gestire e quanto spesso prevedi di emettere o rinnovare certificati?**
