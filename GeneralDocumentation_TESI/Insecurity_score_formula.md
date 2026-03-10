## Framework Teorico
### Modello di Rischio
Il rischio informatico è tradizionalmente definito come:

```
Rischio = Probabilità × Impatto
```

Nel contesto delle vulnerabilità software, questa definizione si articola in:

- **Probabilità**: quanto è probabile che una vulnerabilità venga sfruttata
- **Impatto**: quali conseguenze derivano dallo sfruttamento

### Dimensioni del Rischio

L'Insecurity Score considera quattro dimensioni fondamentali:

Insecurity SCORE = Severità(CVSS) x EXPLOITABILITY (EPSS) x CONTESTO AZIENDALE

#### CVSS (Common Vulnerability Scoring System)
Il CVSS rappresenta la **severità tecnica intrinseca** di una vulnerabilità:
- Scala: 0.0 - 10.0
- Misura: complessità dell'attacco, privilegi richiesti, impatto su confidenzialità/integrità/disponibilità
- Limite: è una misura **teorica**, non considera la probabilità reale di sfruttamento
#### EPSS (Exploit Prediction Scoring System)
L'EPSS rappresenta la **probabilità che una vulnerabilità venga sfruttata** nei prossimi 30 giorni:
- Scala: 0.0 - 1.0 (0% - 100%)
- Basato su: machine learning applicato a dati storici di exploit
- Vantaggio: considera il contesto reale (disponibilità di exploit, interesse degli attaccanti)

> **Nota teorica**: EPSS colma il gap tra severità teorica e rischio pratico. Una vulnerabilità con CVSS 9.8 ma EPSS 0.01 è meno urgente di una con CVSS 7.0 ed EPSS 0.85.
#### Contesto Aziendale
Il contesto determina l'**amplificazione o attenuazione** del rischio tecnico:

| Fattore | Domanda Chiave |
|---------|----------------|
| **Exposure** | Quanto è raggiungibile l'asset da un attaccante? |
| **Criticality** | Quanto è importante l'asset per il business? |
| **Data Classification** | Quanto sono sensibili i dati gestiti? |

## La Formula
### Struttura Generale

```
Insecurity_Score = min(100, Technical_Risk × Context_Multiplier × Volume_Multiplier)
```

La formula adotta un **approccio moltiplicativo** piuttosto che additivo.
L'approccio moltiplicativo riflette meglio la realtà: una vulnerabilità grave (CVSS alto) su un sistema esposto (external) con dati critici (restricted) rappresenta un rischio **esponenzialmente maggiore**, non semplicemente la somma dei fattori.

### Componente 1: Technical Risk

```
Technical_Risk = [Σᵢ (wᵢ × CVSSᵢ × (1 + EPSSᵢ))] / 20 × 100
```

#### 3.2.1 Logica della Combinazione CVSS × (1 + EPSS)

La moltiplicazione `CVSS × (1 + EPSS)` combina severità e probabilità:

- **CVSS** fornisce l'impatto potenziale (0-10)
- **(1 + EPSS)** fornisce un moltiplicatore di probabilità (1.0 - 2.0)

Il fattore `(1 + EPSS)` invece del semplice `EPSS` garantisce che:
- Una CVE con EPSS = 0 non annulli il rischio (rimane il CVSS base)
- Una CVE con EPSS = 1 raddoppia il peso del CVSS

```
Esempio:
- CVE con CVSS 8.0, EPSS 0.1 → 8.0 × 1.1 = 8.8
- CVE con CVSS 8.0, EPSS 0.9 → 8.0 × 1.9 = 15.2

La seconda è quasi il doppio più rischiosa nonostante lo stesso CVSS.
```

#### Ponderazione Esponenziale Decrescente

Quando una VM ha multiple CVE, non tutte contribuiscono equamente. La formula adotta pesi esponenziali:

```
wᵢ = 0.5^i / Σ(0.5^j)   dove i = 0, 1, 2, ... (ordinati per CVSS decrescente)
```

| Posizione | Peso Grezzo | Peso Normalizzato (3 CVE) |
|-----------|-------------|---------------------------|
| 1ª (peggiore) | 1.0 | 57.1% |
| 2ª | 0.5 | 28.6% |
| 3ª | 0.25 | 14.3% |
**Giustificazione teorica**:
Un attaccante razionale sfrutterà la vulnerabilità più grave disponibile. Le vulnerabilità secondarie offrono vie alternative ma il rischio marginale decresce. Questo riflette il principio del **"weakest link"**: la sicurezza complessiva è dominata dalla debolezza principale.
#### Normalizzazione
Il divisore `20` rappresenta il massimo teorico:
- CVSS massimo: 10
- (1 + EPSS) massimo: 2 (quando EPSS = 1)
- Quindi: 10 × 2 = 20

Questo garantisce che Technical_Risk sia sempre in scala 0-100.
### Componente 2: Context Multiplier
```
Context_Multiplier = 0.5 + (Context_Raw - 0.125) / 5.875
```

Dove:
```
Context_Raw = Exposure_Factor × Criticality_Factor × Data_Classification_Factor
```
#### I tre Fattori
**Exposure Factor** - Raggiungibilità dell'asset:

| Valore | Fattore | Razionale |
|--------|---------|-----------|
| Internal | 0.5 | Richiede accesso alla rete interna |
| DMZ | 1.0 | Accessibile con controlli |
| External | 1.5 | Esposto a Internet |
**Criticality Factor** - Importanza per il business:

| Valore | Fattore | Razionale |
|--------|---------|-----------|
| Low | 0.5 | Ambiente di sviluppo/test |
| Medium | 1.0 | Workstation standard |
| High | 1.5 | Application server |
| Critical | 2.0 | Database, infrastruttura core |
**Data Classification Factor** - Sensibilità dei dati:

| Valore | Fattore | Razionale |
|--------|---------|-----------|
| Public | 0.5 | Dati pubblici |
| Internal | 1.0 | Dati interni |
| Confidential | 1.5 | Dati riservati |
| Restricted | 2.0 | Dati critici/regolamentati |
 Con i fattori definiti:
  - **Exposure**: 0.5 (internal), 1.0 (dmz), 1.5 (external)
  - **Criticality**: 0.5 (low), 1.0 (medium), 1.5 (high), 2.0 (critical)
  - **DataClass**: 0.5 (public), 1.0 (internal), 1.5 (confidential), 2.0 (restricted)

  Range di Context_Raw:
  **MINIMO** = 0.5 × 0.5 × 0.5 = 0.125   (internal, low, public)
  **MASSIMO** = 1.5 × 2.0 × 2.0 = 6.0    (external, critical, restricted)

  La Matematica

  La formula generale per normalizzare da [old_min, old_max] a [new_min, new_max] è:

  new_value = new_min + (value - old_min) / (old_max - old_min) × (new_max - new_min)

  Nel nostro caso:
  old_min = 0.125
  old_max = 6.0
  new_min = 0.5
  new_max = 1.5

  Quindi:
  Context_Mult = 0.5 + (Context_Raw - 0.125) / (6.0 - 0.125) × (1.5 - 0.5)
               = 0.5 + (Context_Raw - 0.125) / 5.875 × 1.0
               = 0.5 + (Context_Raw - 0.125) / 5.875
#### Calcolo del Range

- **Minimo teorico**: 0.5 × 0.5 × 0.5 = 0.125 → Context_Mult = 0.5
- **Massimo teorico**: 1.5 × 2.0 × 2.0 = 6.0 → Context_Mult = 1.5

Il Context_Multiplier trasforma il contesto in un **fattore di scala** che:
- **Dimezza** il rischio tecnico nel caso più favorevole (internal, low, public)
- **Aumenta del 50%** il rischio nel caso più sfavorevole (external, critical, restricted)

### Componente 3: Volume Multiplier

```
Volume_Multiplier = 1 + 0.1 × log₂(N_CVE)
```

| N CVE | Volume Multiplier | Incremento |
|-------|-------------------|------------|
| 1 | 1.00 | - |
| 2 | 1.10 | +10% |
| 3 | 1.16 | +16% |
| 5 | 1.23 | +23% |
| 10 | 1.33 | +33% |
| 20 | 1.43 | +43% |
**Giustificazione teorica**:

La funzione logaritmica modella i **rendimenti decrescenti** del volume:
- La seconda CVE aggiunge rischio significativo (nuova via d'attacco)
- La decima CVE aggiunge rischio marginale (l'attaccante ha già molte opzioni)

Questo evita che VM con molte CVE minori superino VM con poche CVE critiche.

### Saturazione a 100

```
Final_Score = min(100, calculated_score)
```

La saturazione garantisce che il punteggio rimanga nel range 0-100, anche in casi estremi. Un punteggio di 100 indica **rischio massimo**, non necessariamente "il peggiore possibile in assoluto".
## Proprietà Matematiche
### Monotonicità

La formula è **monotona crescente** rispetto a tutti i fattori di rischio:
- ↑ CVSS → ↑ Score
- ↑ EPSS → ↑ Score
- ↑ N CVE → ↑ Score
- ↑ Exposure → ↑ Score
- ↑ Criticality → ↑ Score
- ↑ Data Classification → ↑ Score
### Bounded
```
0 ≤ Insecurity_Score ≤ 100
```

- **Score = 0**: Nessuna CVE non patchata
- **Score = 100**: Massimo rischio (saturazione)
### Indipendenza
Il punteggio di una VM è **indipendente** dalle altre VM nel dataset. Questo significa che:
- Aggiungere una nuova VM non modifica i punteggi esistenti
- Rimuovere una VM non modifica i punteggi rimanenti
- I punteggi sono confrontabili nel tempo

---

## Interpretazione dei Risultati

### Scale di Rischio

| Range | Livello | Significato Operativo |
|-------|---------|----------------------|
| 80-100 | **CRITICAL** | Azione immediata richiesta. Rischio di compromissione imminente. |
| 60-79 | **HIGH** | Priorità alta. Pianificare remediation entro il prossimo ciclo. |
| 40-59 | **MEDIUM** | Rischio moderato. Includere nel piano di patching ordinario. |
| 20-39 | **LOW** | Rischio accettabile nel breve termine. Monitorare. |
| 0-19 | **MINIMAL** | Rischio trascurabile. Nessuna azione urgente. |

### Esempi Interpretativi

**Caso 1: Score 95 (CRITICAL)**
> Una VM external-facing con dati confidenziali presenta una CVE con CVSS 9.8 e EPSS 0.85. L'exploit è disponibile pubblicamente e la probabilità di attacco nei prossimi 30 giorni è molto alta.

**Caso 2: Score 35 (LOW)**
> Una VM interna di sviluppo presenta 3 CVE con CVSS medio-alto (7-8), ma EPSS basso (< 0.2) e gestisce solo dati interni. Il contesto mitiga significativamente il rischio tecnico.

**Caso 3: Score 55 (MEDIUM)**
> Una VM nel DMZ con criticality media presenta CVE moderate. Il bilanciamento tra esposizione e severità porta a un rischio intermedio.


L'Insecurity Score proposto offre una metrica **rigorosa, interpretabile e azionabile** per la prioritizzazione del rischio nelle infrastrutture IT.

La formula bilancia:
- **Rigore tecnico** (CVSS, EPSS)
- **Contesto aziendale** (exposure, criticality, data classification)
- **Pragmatismo operativo** (scala 0-100, interpretazione chiara)

Il modello moltiplicativo con ponderazione esponenziale riflette la natura non-lineare del rischio informatico, dove fattori multipli si amplificano reciprocamente anziché sommarsi linearmente.

---

## Appendice: Formula Completa

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         INSECURITY SCORE FORMULA                           │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  Score = min(100, Tech_Risk × Context_Mult × Volume_Mult)                  │
│                                                                            │
│  dove:                                                                     │
│                                                                            │
│  Tech_Risk = [Σᵢ (wᵢ × CVSSᵢ × (1 + EPSSᵢ))] / 20 × 100                   │
│              con wᵢ = 0.5^i / Σ(0.5^j), CVE ordinate per CVSS desc        │
│                                                                            │
│  Context_Mult = 0.5 + (Exposure_F × Criticality_F × DataClass_F - 0.125)  │
│                       ─────────────────────────────────────────────        │
│                                        5.875                               │
│                                                                            │
│  Volume_Mult = 1 + 0.1 × log₂(N_CVE)                                       │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```
