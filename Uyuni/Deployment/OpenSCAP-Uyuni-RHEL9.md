## Prerequisiti e canali software

Prima di installare i pacchetti, il sistema RHEL deve avere i canali software corretti assegnati su Uyuni.
### Verifica canali assegnati
**Web UI Uyuni:**

```
Systems → [seleziona sistema RHEL] → Software → Software Channels
```

Devono essere presenti almeno:

| Canale | Tipo | Contenuto |
|---|---|---|
| `rhel9-pool-x86_64` | Base channel | Pacchetti base RHEL 9 |
| `rhel9-appstream-x86_64` | Child channel | AppStream (include openscap) |
## Installare i pacchetti OpenSCAP tramite Uyuni
### Metodo A — Web UI (consigliato)

```
Systems → [sistema RHEL] → Software → Packages → Install
```
Cerca e installa i seguenti pacchetti:

| Pacchetto | Obbligatorio | Funzione |
|---|---|---|
| `openscap-scanner` | Si | Scanner SCAP core |
| `scap-security-guide` | Si | Profili CIS, STIG, PCI-DSS, HIPAA |
| `bzip2` | Si | Decompressione risultati (richiesto da Uyuni) |
| `openscap-utils` | No | Utility aggiuntive |

1. Cerca ogni pacchetto nella barra di ricerca
2. Seleziona la versione più recente
3. Clicca **Schedule Install**
4. Conferma → attendi il completamento (verificabile in **Schedule** → **Pending Actions**)
## Eseguire la prima scansione da Uyuni
### Via Web UI
```
Systems → [sistema RHEL] → Audit → Schedule
```
Compila il form:

| Campo | Valore |
|---|---|
| **Path to XCCDF document** | `/usr/share/xml/scap/ssg/content/ssg-rhel9-ds.xml` |
| **Command-line arguments** | `--profile xccdf_org.ssgproject.content_profile_cis` |
| **Date/Time** | Subito o pianificato |

Clicca **Schedule** e attendi il completamento (2-10 minuti).

> **Nota:** Usa sempre `ssg-rhel9-ds.xml` (DataStream) e non `ssg-rhel9-xccdf.xml` diretto,
> perché il DataStream include OVAL e CPE dictionary in un unico file.

### Test scansione locale (debug, bypass Uyuni)
Utile per verificare che i pacchetti funzionino prima di schedulare da Uyuni:

```bash
oscap xccdf eval \
  --profile xccdf_org.ssgproject.content_profile_cis \
  --results /tmp/scap-results.xml \
  --report /tmp/scap-report.html \
  /usr/share/xml/scap/ssg/content/ssg-rhel9-ds.xml

echo "Exit code: $?"
# 0 = tutte le regole pass
# 2 = alcune regole fail (normale)
# 1 = errore di esecuzione
```

Il report HTML in `/tmp/scap-report.html` può essere copiato e aperto in un browser.
## Leggere i risultati
### Via Web UI
```
Systems → [sistema RHEL] → Audit → List Scans
```

Clicca sulla scansione per il dettaglio:

```
Total rules:   250
Pass:          180  ████████████░░░  72%
Fail:           65  ██████░░░░░░░░░  26%
Not checked:    5                     2%
```

Per ogni regola vengono mostrati:
- **ID regola** (es. `xccdf_org.ssgproject.content_rule_no_empty_passwords`)
- **Risultato**: pass / fail / notchecked / informational / fixed
- **Severity**: high / medium / low / unknown
- **Descrizione** del controllo
- **Remediation** suggerita (script o procedura)

###  Scansioni aggregate (tutti i sistemi)
```
Audit → All Scans
```

Permette di confrontare i risultati tra sistemi diversi e monitorare il trend nel tempo.
## Troubleshooting

| Sintomo | Causa probabile | Soluzione |
|---|---|---|
| Scansione fallisce immediatamente | `openscap-scanner` non installato | Fase 2 |
| `No such file or directory` sul path XCCDF | `scap-security-guide` non installato | Fase 2 |
| Profilo non trovato | ID profilo errato o typo | `oscap info ssg-rhel9-ds.xml` per lista completa |
| Risultati non caricati su Uyuni | `bzip2` mancante | Installa `bzip2` (Fase 2) |
| Minion non risponde | Salt non attivo | `salt '10.172.2.19' test.ping` |
| Scansione molto lenta (>15 min) | Sistema sotto carico o OVAL lento | Normale su prima esecuzione, poi si velocizza |
| `oscap` non trovato in PATH | Installazione incompleta | `rpm -q openscap-scanner` + reinstalla |
| Scansione schedulata ma non parte | Minion offline al momento dello schedule | Verifica stato minion in Uyuni → Systems → Overview |

### Comandi diagnostici rapidi

```bash
# Sul server Uyuni (10.172.2.17)
salt '10.172.2.19' test.ping
salt '10.172.2.19' pkg.version openscap-scanner
salt '10.172.2.19' cmd.run 'oscap --version'
salt '10.172.2.19' cmd.run 'ls /usr/share/xml/scap/ssg/content/ | grep rhel9'

# Verifica azioni pendenti via API
# GET https://10.172.2.17/rpc/api → schedule.listAllActions
```

---

## Note finali

- Usa sempre il file **DataStream** (`ssg-rhel9-ds.xml`) e non i singoli file XCCDF/OVAL
- Il profilo **CIS Level 1** e' il punto di partenza consigliato: buon equilibrio tra sicurezza e impatto operativo
- Esegui sempre una scansione **prima** di applicare patch per avere una baseline di confronto
- I risultati sono conservati in Uyuni per audit trail storico
