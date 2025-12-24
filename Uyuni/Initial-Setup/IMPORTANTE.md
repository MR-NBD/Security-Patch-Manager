Verificare o stato attuale:

```bash
# Stato sync in corso
curl -s "http://10.172.5.4:5000/api/stats/overview" | jq '.errata'
```
### Risposta alla Tua Domanda sui Canali
**Quando crei nuovi canali/activation key:**

1. **Canali child/lifecycle** (clonati da un canale base) → Gli errata sono **già presenti** automaticamente
2. **Nuovi canali base** → Devi eseguire:
    
```bash
# Aggiorna cache (rileva nuovi canali)
curl -s -X POST "http://10.172.5.4:5000/api/uyuni/sync-packages"
```
    
I nuovi errata verranno poi associati automaticamente dal cron settimanale.
### Verifica Stato Sync

```bash
curl -s "http://10.172.5.4:5000/api/stats/overview" | jq '.errata'
```
