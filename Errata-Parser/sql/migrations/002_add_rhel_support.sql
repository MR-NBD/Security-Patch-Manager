-- ============================================================
-- Migration 002: Supporto RHEL — estende constraint per nuova sorgente
-- Data: 2026-03-11
-- Motivo: aggiunta NVD enrichment per errata RHEL nativi UYUNI.
--   - chk_errata_source esteso: aggiunge 'rhel'
--   - chk_log_type esteso: aggiunge 'rhel', 'rhel_push'
-- Applicare con: psql "$DATABASE_URL" -f sql/migrations/002_add_rhel_support.sql
-- ============================================================

BEGIN;

-- ============================================================
-- 1. Estende chk_errata_source: aggiunge 'rhel'
-- ============================================================
DO $$
BEGIN
    -- Rimuove il constraint esistente se presente
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_errata_source'
          AND conrelid = 'errata'::regclass
    ) THEN
        ALTER TABLE errata DROP CONSTRAINT chk_errata_source;
        RAISE NOTICE 'Migration 002: chk_errata_source rimosso';
    END IF;

    -- Ricrea con 'rhel' aggiunto
    ALTER TABLE errata
        ADD CONSTRAINT chk_errata_source
        CHECK (source IN ('usn', 'dsa', 'rhel'));
    RAISE NOTICE 'Migration 002: chk_errata_source ricreato con rhel';
END $$;

-- ============================================================
-- 2. Estende chk_log_type: aggiunge 'rhel', 'rhel_push'
-- ============================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_log_type'
          AND conrelid = 'sync_logs'::regclass
    ) THEN
        ALTER TABLE sync_logs DROP CONSTRAINT chk_log_type;
        RAISE NOTICE 'Migration 002: chk_log_type rimosso';
    END IF;

    ALTER TABLE sync_logs
        ADD CONSTRAINT chk_log_type
        CHECK (sync_type IN ('usn', 'dsa', 'nvd', 'packages', 'push', 'rhel', 'rhel_push'));
    RAISE NOTICE 'Migration 002: chk_log_type ricreato con rhel, rhel_push';
END $$;

-- ============================================================
-- Verifica finale
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE 'Migration 002: COMPLETATA';
END $$;

COMMIT;
