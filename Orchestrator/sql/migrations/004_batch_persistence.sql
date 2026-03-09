-- Migration 004: Persistenza batch su DB
--
-- Aggiunge tabella patch_test_batches per rendere i batch sopravvivere
-- al restart di Flask. Prima i batch erano solo in memoria (_batches dict):
-- un restart durante un batch rendeva il polling dalla dashboard → 404.
--
-- Il codice usa la memoria come cache veloce per batch attivi,
-- e il DB come fallback per batch completati o dopo restart.
--
-- Supporta cancellazione: status='cancelled' quando l'operatore
-- interrompe il batch prima del completamento.
--
-- Applicare UNA SOLA VOLTA sul VM:
--   psql -h localhost -U spm_orch -d spm_orchestrator -f 004_batch_persistence.sql

BEGIN;

CREATE TABLE IF NOT EXISTS patch_test_batches (
    batch_id     VARCHAR(12) PRIMARY KEY,
    status       VARCHAR(20) NOT NULL DEFAULT 'running',
    group_name   VARCHAR(100),
    operator     VARCHAR(200),
    total        INTEGER NOT NULL DEFAULT 0,
    completed    INTEGER NOT NULL DEFAULT 0,
    passed       INTEGER NOT NULL DEFAULT 0,
    failed       INTEGER NOT NULL DEFAULT 0,
    results      JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,

    CONSTRAINT chk_batch_status CHECK (
        status IN ('running', 'completed', 'cancelled', 'error')
    )
);

CREATE INDEX IF NOT EXISTS idx_batches_status     ON patch_test_batches(status);
CREATE INDEX IF NOT EXISTS idx_batches_operator   ON patch_test_batches(operator);
CREATE INDEX IF NOT EXISTS idx_batches_started_at ON patch_test_batches(started_at);

COMMENT ON TABLE patch_test_batches IS
    'Batch di test patch: persistenza su DB per sopravvivere al restart Flask';

COMMIT;

-- Verifica
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'patch_test_batches';
