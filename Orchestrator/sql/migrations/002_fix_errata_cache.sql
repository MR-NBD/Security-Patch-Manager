-- ============================================================
-- SPM ORCHESTRATOR - Migration 002
-- Fix: aggiunge errata_cache e corregge le VIEW
-- Da applicare se 001 ha fallito con "relation errata does not exist"
-- ============================================================

BEGIN;

-- ============================================================
-- Tabella errata_cache (mancante in v1.0)
-- ============================================================
CREATE TABLE IF NOT EXISTS errata_cache (
    errata_id  VARCHAR(50) PRIMARY KEY,
    synopsis   TEXT,
    description TEXT,
    severity   VARCHAR(20),
    type       VARCHAR(50),
    issued_date TIMESTAMP,
    target_os  VARCHAR(20),
    packages   JSONB,
    cves       TEXT[],
    source_url TEXT,
    synced_at  TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_errata_cache_severity ON errata_cache(severity);
CREATE INDEX IF NOT EXISTS idx_errata_cache_os       ON errata_cache(target_os);
CREATE INDEX IF NOT EXISTS idx_errata_cache_issued   ON errata_cache(issued_date DESC);
CREATE INDEX IF NOT EXISTS idx_errata_cache_synced   ON errata_cache(synced_at DESC);

DROP TRIGGER IF EXISTS trg_errata_cache_updated ON errata_cache;
CREATE TRIGGER trg_errata_cache_updated
    BEFORE UPDATE ON errata_cache
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

COMMENT ON TABLE errata_cache IS 'Cache locale errata copiati da SPM-SYNC via polling';

-- ============================================================
-- Ricrea VIEW usando errata_cache locale (non la DB di SPM-SYNC)
-- ============================================================

CREATE OR REPLACE VIEW v_queue_details AS
SELECT
    q.id               AS queue_id,
    q.errata_id,
    q.errata_version,
    q.target_os,
    q.status,
    q.success_score,
    q.priority_override,
    q.queued_at,
    q.started_at,
    q.completed_at,
    q.test_id,
    e.synopsis,
    e.severity,
    e.type             AS errata_type,
    e.issued_date,
    rp.affects_kernel,
    rp.requires_reboot,
    rp.times_tested,
    rp.times_failed,
    t.result           AS test_result,
    t.duration_seconds AS test_duration
FROM patch_test_queue q
LEFT JOIN errata_cache      e  ON q.errata_id = e.errata_id
LEFT JOIN patch_risk_profile rp ON q.errata_id = rp.errata_id
LEFT JOIN patch_tests        t  ON q.test_id   = t.id;

COMMENT ON VIEW v_queue_details IS 'Coda test con dettagli errata e profilo rischio';

CREATE OR REPLACE VIEW v_pending_approvals AS
SELECT
    q.id              AS queue_id,
    q.errata_id,
    q.target_os,
    q.success_score,
    q.completed_at    AS tested_at,
    e.synopsis,
    e.severity,
    t.result          AS test_result,
    t.duration_seconds,
    t.required_reboot,
    t.metrics_evaluation,
    EXTRACT(EPOCH FROM (NOW() - q.completed_at))/3600 AS hours_pending
FROM patch_test_queue q
LEFT JOIN errata_cache e ON q.errata_id = e.errata_id
LEFT JOIN patch_tests  t ON q.test_id   = t.id
WHERE q.status = 'pending_approval'
ORDER BY e.severity DESC, q.completed_at ASC;

COMMENT ON VIEW v_pending_approvals IS 'Patch in attesa di approvazione';

COMMIT;

-- Verifica
DO $$
DECLARE cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO cnt
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name IN (
          'errata_cache','patch_risk_profile','patch_test_queue','patch_tests',
          'patch_test_phases','patch_approvals','patch_deployments',
          'patch_rollbacks','orchestrator_notifications','orchestrator_config'
      );
    RAISE NOTICE 'Tables present: % / 10', cnt;
END $$;
