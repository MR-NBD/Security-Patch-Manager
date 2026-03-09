-- Migration 005: Critical services default config
--
-- Inserisce i valori di default per critical_services_ubuntu e critical_services_rhel
-- in orchestrator_config, in modo che siano configurabili a runtime via DB senza
-- modifiche al codice.
--
-- get_critical_services() in uyuni_patch_client.py interroga questi valori e usa
-- _DEFAULT_SERVICES come fallback se le chiavi non esistono.
-- ON CONFLICT DO NOTHING: non sovrascrive eventuali personalizzazioni esistenti.
--
-- Applicare con:
--   psql -h localhost -U spm_orch -d spm_orchestrator \
--       -f /opt/Security-Patch-Manager/Orchestrator/sql/migrations/005_critical_services_config.sql

BEGIN;

INSERT INTO orchestrator_config (key, value, description)
VALUES
    (
        'critical_services_ubuntu',
        '["ssh.socket", "cron", "rsyslog"]'::jsonb,
        'Servizi critici da verificare post-patch su VM Ubuntu 24.04. '
        'ssh.socket (socket activation), cron, rsyslog. '
        'Modificare qui per aggiungere/rimuovere servizi senza riavviare il servizio.'
    ),
    (
        'critical_services_rhel',
        '["sshd", "crond", "rsyslog"]'::jsonb,
        'Servizi critici da verificare post-patch su VM RHEL 9. '
        'sshd, crond, rsyslog. '
        'Modificare qui per aggiungere/rimuovere servizi senza riavviare il servizio.'
    )
ON CONFLICT (key) DO NOTHING;

-- Verifica risultato
SELECT key, value, description
FROM orchestrator_config
WHERE key IN ('critical_services_ubuntu', 'critical_services_rhel')
ORDER BY key;

COMMIT;
