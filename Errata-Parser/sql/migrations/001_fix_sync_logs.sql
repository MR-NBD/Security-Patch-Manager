-- ============================================================
-- Migration 001: Fix sync_logs — dsa_full → dsa + constraints
-- Data: 2026-03-11
-- Motivo: versioni precedenti dell'app usavano sync_type='dsa_full'.
--   Il constraint chk_log_type non era presente sulle installazioni
--   esistenti (CREATE TABLE IF NOT EXISTS non modifica tabelle già create).
--   Questa migration pulisce i dati storici e aggiunge i constraint mancanti.
-- Applicare con: psql "$DATABASE_URL" -f sql/migrations/001_fix_sync_logs.sql
-- ============================================================

BEGIN;

-- ============================================================
-- 1. Aggiorna record storici: dsa_full → dsa
-- ============================================================
DO $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE sync_logs SET sync_type = 'dsa' WHERE sync_type = 'dsa_full';
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    IF updated_count > 0 THEN
        RAISE NOTICE 'Migration 001: aggiornati % record dsa_full → dsa', updated_count;
    ELSE
        RAISE NOTICE 'Migration 001: nessun record dsa_full trovato';
    END IF;
END $$;

-- ============================================================
-- 2. Rimuove eventuali altri valori non riconosciuti
--    (imposta a 'usn' come fallback sicuro)
-- ============================================================
UPDATE sync_logs
SET sync_type = 'usn'
WHERE sync_type NOT IN ('usn', 'dsa', 'nvd', 'packages', 'push');

-- ============================================================
-- 3. Aggiunge constraint chk_log_type se non esiste
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_log_type'
          AND conrelid = 'sync_logs'::regclass
    ) THEN
        ALTER TABLE sync_logs
            ADD CONSTRAINT chk_log_type
            CHECK (sync_type IN ('usn', 'dsa', 'nvd', 'packages', 'push'));
        RAISE NOTICE 'Migration 001: constraint chk_log_type aggiunto';
    ELSE
        RAISE NOTICE 'Migration 001: constraint chk_log_type già presente';
    END IF;
END $$;

-- ============================================================
-- 4. Aggiunge constraint chk_log_status se non esiste
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_log_status'
          AND conrelid = 'sync_logs'::regclass
    ) THEN
        ALTER TABLE sync_logs
            ADD CONSTRAINT chk_log_status
            CHECK (status IN ('running', 'completed', 'error'));
        RAISE NOTICE 'Migration 001: constraint chk_log_status aggiunto';
    ELSE
        RAISE NOTICE 'Migration 001: constraint chk_log_status già presente';
    END IF;
END $$;

-- ============================================================
-- 5. Aggiunge constraint chk_errata_source su tabella errata
--    (stessa situazione: potrebbe mancare su installazioni esistenti)
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_errata_source'
          AND conrelid = 'errata'::regclass
    ) THEN
        ALTER TABLE errata
            ADD CONSTRAINT chk_errata_source
            CHECK (source IN ('usn', 'dsa'));
        RAISE NOTICE 'Migration 001: constraint chk_errata_source aggiunto';
    ELSE
        RAISE NOTICE 'Migration 001: constraint chk_errata_source già presente';
    END IF;
END $$;

-- ============================================================
-- 6. Aggiunge constraint chk_errata_severity se non esiste
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_errata_severity'
          AND conrelid = 'errata'::regclass
    ) THEN
        ALTER TABLE errata
            ADD CONSTRAINT chk_errata_severity
            CHECK (severity IS NULL OR severity IN ('critical', 'high', 'medium', 'low'));
        RAISE NOTICE 'Migration 001: constraint chk_errata_severity aggiunto';
    ELSE
        RAISE NOTICE 'Migration 001: constraint chk_errata_severity già presente';
    END IF;
END $$;

-- ============================================================
-- 7. Aggiunge constraint chk_errata_status se non esiste
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_errata_status'
          AND conrelid = 'errata'::regclass
    ) THEN
        ALTER TABLE errata
            ADD CONSTRAINT chk_errata_status
            CHECK (sync_status IN ('pending', 'synced'));
        RAISE NOTICE 'Migration 001: constraint chk_errata_status aggiunto';
    ELSE
        RAISE NOTICE 'Migration 001: constraint chk_errata_status già presente';
    END IF;
END $$;

-- ============================================================
-- Verifica finale
-- ============================================================
DO $$
DECLARE
    spurious INTEGER;
BEGIN
    SELECT COUNT(*) INTO spurious
    FROM sync_logs
    WHERE sync_type NOT IN ('usn', 'dsa', 'nvd', 'packages', 'push');

    IF spurious = 0 THEN
        RAISE NOTICE 'Migration 001: COMPLETATA — nessun sync_type non valido rimasto';
    ELSE
        RAISE WARNING 'Migration 001: rimasti % record con sync_type non valido', spurious;
    END IF;
END $$;

COMMIT;
