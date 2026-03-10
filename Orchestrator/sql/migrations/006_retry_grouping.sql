-- Migration 006: Retry logic + supersession columns
--
-- Aggiunge a patch_test_queue:
--   retry_count   INT DEFAULT 0     → numero di tentativi effettuati
--   retry_after   TIMESTAMPTZ       → non riprovare prima di questo timestamp
--   superseded_by VARCHAR(255)      → errata_id della patch più recente che la sostituisce
--
-- Aggiunge due nuovi stati al constraint chk_queue_status:
--   retry_pending → in attesa del prossimo tentativo (INFRA/TRANSIENT error)
--   superseded    → sostituita da una patch più recente (stessa famiglia o stessi pacchetti)
--
-- Applicare con:
--   psql -h localhost -U spm_orch -d spm_orchestrator \
--       -f /opt/Security-Patch-Manager/Orchestrator/sql/migrations/006_retry_grouping.sql

BEGIN;

ALTER TABLE patch_test_queue
    ADD COLUMN IF NOT EXISTS retry_count   INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS retry_after   TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS superseded_by VARCHAR(255);

-- Aggiorna constraint status per includere i nuovi valori
ALTER TABLE patch_test_queue DROP CONSTRAINT IF EXISTS chk_queue_status;

ALTER TABLE patch_test_queue ADD CONSTRAINT chk_queue_status CHECK (status IN (
    'queued', 'testing', 'passed', 'failed', 'needs_reboot', 'rebooting',
    'pending_approval', 'approved', 'rejected', 'snoozed',
    'promoting', 'prod_pending', 'prod_applied', 'completed', 'rolled_back',
    'retry_pending', 'superseded'
));

-- Indice per il polling efficiente dei retry (scheduler controlla ogni 2 min)
CREATE INDEX IF NOT EXISTS idx_ptq_retry
    ON patch_test_queue (status, retry_after)
    WHERE status = 'retry_pending';

-- Indice per lookup delle patch che hanno soppresso questa
CREATE INDEX IF NOT EXISTS idx_ptq_superseded_by
    ON patch_test_queue (superseded_by)
    WHERE superseded_by IS NOT NULL;

-- Verifica risultato
SELECT
    column_name,
    data_type,
    column_default
FROM information_schema.columns
WHERE table_name = 'patch_test_queue'
  AND column_name IN ('retry_count', 'retry_after', 'superseded_by')
ORDER BY column_name;

COMMIT;
