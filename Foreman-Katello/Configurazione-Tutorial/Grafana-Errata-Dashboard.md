## Informazioni Accesso

| Parametro | Valore |
|-----------|--------|
| URL Grafana | `http://10.172.5.4:3000` |
| Username | `admin` |
| Password | `GrafanaAdmin2024!` |
| Datasource | PostgreSQL |

---
## 1 Configurazione Datasource

### 1.1 Aggiungi Datasource PostgreSQL

1. Accedi a Grafana
2. Vai su **Connections** → **Data sources**
3. Clicca **Add data source**
4. Cerca e seleziona **PostgreSQL**
5. Configura:

| Campo | Valore |
|-------|--------|
| Name | `Errata-PostgreSQL` |
| Host | `10.172.2.196:5432` |
| Database | `errata_db` |
| User | `errata_admin` |
| Password | `ErrataDB2024!` |
| TLS/SSL Mode | `require` |

6. Clicca **Save & test**
7. Verifica che appaia "Database Connection OK"

---
## 2 Creazione Dashboard
### 2.1 Nuova Dashboard
1. Vai su **Dashboards**
2. Clicca **New** → **New Dashboard**
3. **IMPORTANTE**: Clicca subito **Save** (in alto a destra)
4. Nome: `Errata Management`
5. Clicca **Save**

---
## 3 Configurazione Variabile Organization
Prima di creare i panel, configura il filtro per Organization.
### 3.1 Aggiungi Variabile
1. Clicca **Dashboard settings**
2. Nel menu a sinistra, clicca **Variables**
3. Clicca **Add variable**
4. Configura:

| Campo              | Valore                                                          |
| ------------------ | --------------------------------------------------------------- |
| Name               | `organization`                                                  |
| Type               | Query                                                           |
| Data source        | Errata-PostgreSQL                                               |
| Query              | `SELECT DISTINCT organization FROM hosts ORDER BY organization` |
| Include All option | On                                                              |
| Custom all value   | `%%`                                                            |

5. Clicca **Apply**
6. Clicca **Save dashboard**

Ora vedrai un dropdown "organization" in alto nella dashboard.

---
## 4 Panel: Errata per Severity (Pie Chart)
### 4.1 Creazione

1. Clicca **Add** → **Visualization**
2. Seleziona datasource **Errata-PostgreSQL**
3. In basso, clicca su **Code**
4. Incolla la query:

```sql
SELECT 
  e.severity as "Severity",
  COUNT(*)::float as "Count"
FROM host_errata he
INNER JOIN errata e ON e.id = he.errata_id
INNER JOIN hosts h ON h.id = he.host_id
WHERE h.organization LIKE '${organization:raw}'
GROUP BY e.severity
ORDER BY "Count" DESC
```
### 4.2 Configurazione
1. **Format**: `Table`
2. Nel pannello a destra, cambia tipo visualizzazione: cerca **Pie chart**
3. **Title**: `Errata per Severity`
### 4.3 Opzioni Pie Chart
Nel pannello a destra:
- **Legend** → **Visibility**: On
- **Legend** → **Placement**: Right
- **Legend** → **Values**: spunta `Value`

4. Clicca **Apply**
5. Clicca **Save**

![](/img/ErrataPerSecurity.png)

---
## 5 Panel: Errata per Host (Bar Chart)
### 5.1 Creazione

1. Clicca **Add** → **Visualization**
2. Datasource: **Errata-PostgreSQL**
3. Modalità **Code**, incolla:

```sql
SELECT 
  h.hostname as "Host",
  COUNT(*)::float as "Errata"
FROM host_errata he
INNER JOIN hosts h ON h.id = he.host_id
WHERE h.organization LIKE '${organization:raw}'
GROUP BY h.hostname
ORDER BY "Errata" DESC
```
### 5.2 Configurazione

1. **Format**: `Table`
2. Tipo visualizzazione: **Bar chart**
3. **Title**: `Errata per Host`
4. Clicca **Apply**
5. Clicca **Save**
![](/img/ErrataPerHost.png)
---
## 6 Panel: Errata Critical - Dettaglio (Table)
### 6.1 Creazione
1. Clicca **Add** → **Visualization**
2. Datasource: **Errata-PostgreSQL**
3. Modalità **Code**, incolla:

```sql
SELECT 
  h.hostname as "Host",
  e.errata_id as "Errata ID",
  e.title as "Titolo",
  array_to_string(e.cves, ', ') as "CVE",
  he.package_name as "Pacchetto",
  he.fixed_version as "Versione Fix",
  e.issued_date as "Data"
FROM host_errata he
INNER JOIN hosts h ON h.id = he.host_id
INNER JOIN errata e ON e.id = he.errata_id
WHERE e.severity = 'critical'
  AND h.organization LIKE '${organization:raw}'
ORDER BY e.issued_date DESC
```

### 6.2 Configurazione
1. **Format**: `Table`
2. Tipo visualizzazione: **Table**
3. **Title**: `Errata Critical - Dettaglio`

### 6.3 Abilitare Filtri
Nel pannello a destra:
- Cerca **Table** → attiva **Column filter**

4. Clicca **Apply**
5. Clicca **Save**

---
## 7 Panel: Trend Errata nel Tempo (Time Series)
### 7.1 Creazione

1. Clicca **Add** → **Visualization**
2. Datasource: **Errata-PostgreSQL**
3. Modalità **Code**, incolla:

```sql
SELECT 
  snapshot_date::timestamp as "time",
  hostname,
  total_errata
FROM errata_history
WHERE organization LIKE '${organization:raw}'
ORDER BY snapshot_date ASC
```

### 7.2 Configurazione

1. **Format**: `Time series`
2. Tipo visualizzazione: **Time series**
3. **Title**: `Trend Errata nel Tempo`
### 7.3 Opzioni Time Series

Nel pannello a destra:
- **Legend** → **Visibility**: On
- **Legend** → **Mode**: List
- **Legend** → **Placement**: Bottom
### 7.4 Impostare Intervallo Temporale
In alto a destra nella dashboard, imposta l'intervallo temporale:
- Clicca sul selettore tempo (default "Last 6 hours")
- Seleziona **Last 7 days** o **Last 30 days**

4. Clicca **Apply**
5. Clicca **Save**

---
## 8 Query Alternative
### 8.1 Trend per Severity (alternativa per Panel Trend)

Se si vuoi vedere il trend separato per severity invece che per host:

```sql
SELECT 
  snapshot_date::timestamp as "time",
  SUM(critical_count) as "Critical",
  SUM(important_count) as "Important",
  SUM(moderate_count) as "Moderate",
  SUM(low_count) as "Low"
FROM errata_history
WHERE organization LIKE '${organization:raw}'
GROUP BY snapshot_date
ORDER BY snapshot_date ASC
```
### 8.2 Tutti gli Errata (non solo Critical)
Per vedere tutti gli errata, non solo i critical:

```sql
SELECT 
  h.hostname as "Host",
  e.errata_id as "Errata ID",
  e.severity as "Severity",
  e.title as "Titolo",
  array_to_string(e.cves, ', ') as "CVE",
  he.package_name as "Pacchetto",
  he.fixed_version as "Versione Fix",
  e.issued_date as "Data"
FROM host_errata he
INNER JOIN hosts h ON h.id = he.host_id
INNER JOIN errata e ON e.id = he.errata_id
WHERE h.organization LIKE '${organization:raw}'
ORDER BY 
  CASE e.severity 
    WHEN 'critical' THEN 1 
    WHEN 'important' THEN 2 
    WHEN 'moderate' THEN 3 
    ELSE 4 
  END,
  e.issued_date DESC
```

### 8.3 Conteggio per Host e Severity
```sql
SELECT 
  h.hostname as "Host",
  e.severity as "Severity",
  COUNT(*) as "Count"
FROM host_errata he
INNER JOIN hosts h ON h.id = he.host_id
INNER JOIN errata e ON e.id = he.errata_id
WHERE h.organization LIKE '${organization:raw}'
GROUP BY h.hostname, e.severity
ORDER BY h.hostname, e.severity
```
## 10 Troubleshooting

### 10.1 "No data" nel panel

**Cause possibili:**
- Intervallo temporale sbagliato (controlla il selettore in alto a destra)
- Variabile organization non selezionata
- Query con errore di sintassi

**Soluzione:**
1. Prova prima una query semplice: `SELECT * FROM hosts`
2. Verifica che il datasource sia connesso
3. Controlla i log di Grafana

### 10.2 Errore "syntax error at or near PSN"

**Causa:** Variabile non quotata correttamente.

**Soluzione:** Usa `'${organization:raw}'` con `:raw` e `%%` come Custom all value.
### 10.3 Dashboard persa dopo riavvio

**Causa:** Non hai salvato la dashboard.

**Soluzione:** Clicca sempre **Save** dopo ogni modifica. Grafana non salva automaticamente.
### 10.4 Pie chart mostra un solo colore

**Causa:** Il campo per le categorie non è riconosciuto.

**Soluzione:** 
- Assicurati che la query restituisca due colonne: una per le etichette, una per i valori
- Verifica che **Format** sia `Table`

---
## 11 Note

### 11.1 Snapshot e Storico

Il panel "Trend Errata nel Tempo" richiede dati nella tabella `errata_history`. Gli snapshot vengono creati:
- Automaticamente quando si esegue un sync completo
- Manualmente via API: `curl -X POST http://10.172.5.4:5000/api/snapshot`
### 11.2 Aggiornamento Dati

I dati vengono aggiornati quando:
1. Le VM inviano i pacchetti a Foreman
2. Si esegue il sync: `curl -X POST http://10.172.5.4:5000/api/sync -d '{"type":"all"}'`
### 11.3 Accesso Esterno

Grafana è accessibile solo dalla rete interna (IP privato 10.172.5.4). Per accesso esterno:
- Usa tunnel SSH
- Oppure configura un reverse proxy
