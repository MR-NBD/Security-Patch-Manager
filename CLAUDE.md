# Security Patch Manager - Note per Claude Code

## Deployment sul VM (REGOLA FISSA)

**Usare SEMPRE `git pull` per deployare modifiche sul VM. MAI base64.**

```bash
cd /opt/spm-orchestrator
git pull origin main
sudo systemctl restart spm-orchestrator
```

- Il VM (`10.172.2.22`) ha accesso a GitHub
- L'accesso al VM è via Azure Bastion (no SCP, no rsync diretto)
- `git pull` è l'unico metodo di deploy affidabile
- Il base64 copy-paste è **vietato**: stringhe lunghe → errori silenziosi

---

## Architettura

- **SPM-ORCHESTRATOR**: Flask 3.x API su `10.172.2.22:5001`
  - Path: `/opt/spm-orchestrator`
  - Service: `spm-orchestrator.service` (systemd)
  - DB: PostgreSQL locale, user `spm_orch`, db `spm_orchestrator`
  - `psql` richiede `-h localhost` (peer auth disabilitata su TCP)

- **SPM-SYNC**: API esterna su `10.172.5.4:5000`
  - `issued_date` è in formato **RFC 2822** (es. `"Fri, 20 Feb 2026 13:23:45 GMT"`)
  - NON è ISO 8601 — usare `email.utils.parsedate_to_datetime()` per parsarlo

- **UYUNI**: patch manager, host `10.172.x.x`

## Stack
- Python 3.x, Flask 3.x, psycopg2, APScheduler
- PostgreSQL (RealDictCursor, ThreadedConnectionPool)
- 10 tabelle: `errata_cache`, `patch_test_queue`, `patch_risk_profile`, `patch_tests`, `patch_test_phases`, `patch_approvals`, `patch_deployments`, `patch_rollbacks`, `orchestrator_notifications`, `orchestrator_config`
