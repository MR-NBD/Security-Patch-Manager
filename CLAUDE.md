# Security Patch Manager - Note per Claude Code

## Deployment sul VM (REGOLA FISSA)

**Usare SEMPRE git per deployare modifiche sul VM. MAI base64.**

Il repo è clonato in `/opt/Security-Patch-Manager`. Procedura deploy:

```bash
cd /opt/Security-Patch-Manager && git pull origin main
cp -r /opt/Security-Patch-Manager/Orchestrator/app /opt/spm-orchestrator/
sudo systemctl restart spm-orchestrator
```

- Il VM (`10.172.2.22`) ha accesso a GitHub (repo pubblico: `https://github.com/MR-NBD/Security-Patch-Manager.git`)
- L'accesso al VM è via Azure Bastion (no SCP, no rsync diretto)
- Il repo è clonato in `/opt/Security-Patch-Manager`
- Il base64 copy-paste è **vietato**: stringhe lunghe → errori silenziosi

---

## Architettura

- **SPM-ORCHESTRATOR**: Flask 3.x API su `10.172.2.22:5001`
  - Path: `/opt/spm-orchestrator`
  - Service: `spm-orchestrator.service` (systemd)
  - DB: PostgreSQL locale, user `spm_orch`, db `spm_orchestrator`
  - `psql` richiede `-h localhost` (peer auth disabilitata su TCP)

- **UYUNI**: patch manager su `10.172.2.17` (XML-RPC `/rpc/api`)
  - Source of truth per le patch applicabili ai sistemi test-*
  - SSL verify disabilitato (`UYUNI_VERIFY_SSL=false`)
  - Il poller interroga i gruppi con prefisso `test-` (es. `test-rhel9`, `test-ubuntu-2404`)
  - Severity mappata da advisory_type: Security→Medium, Bug Fix→Low, Enhancement→Low

## Stack
- Python 3.x, Flask 3.x, psycopg2, APScheduler
- PostgreSQL (RealDictCursor, ThreadedConnectionPool)
- 10 tabelle: `errata_cache`, `patch_test_queue`, `patch_risk_profile`, `patch_tests`, `patch_test_phases`, `patch_approvals`, `patch_deployments`, `patch_rollbacks`, `orchestrator_notifications`, `orchestrator_config`
