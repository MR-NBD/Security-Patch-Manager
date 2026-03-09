-- Migration 003: Semplificazione sistema notifiche
--
-- Rimuove il canale email/webhook: le notifiche sono ora solo interne (dashboard).
-- L'audit esteso è delegato alle note UYUNI (add_note in test_engine.py).
--
-- Bug fix: il constraint originale CHECK (channel IN ('email', 'webhook')) bloccava
-- silenziosamente tutti gli INSERT con channel='dashboard', rendendo le notifiche
-- non operative. Questo script corregge il constraint e allinea i dati.
--
-- Applicare UNA SOLA VOLTA sul VM:
--   psql -h localhost -U spm_orch -d spm_orchestrator -f 003_simplify_notifications.sql

BEGIN;

-- 1. Rimuovi constraint canale obsoleto
ALTER TABLE orchestrator_notifications
    DROP CONSTRAINT IF EXISTS chk_notification_channel;

-- 2. Aggiorna eventuali righe storiche (se presenti nonostante il bug)
UPDATE orchestrator_notifications
    SET channel = 'dashboard'
    WHERE channel IN ('email', 'webhook');

-- 3. Aggiorna recipient generico se era un indirizzo email
UPDATE orchestrator_notifications
    SET recipient = 'operator'
    WHERE recipient LIKE '%@%';

-- 4. Aggiungi nuovo constraint: solo 'dashboard' ammesso
ALTER TABLE orchestrator_notifications
    ADD CONSTRAINT chk_notification_channel CHECK (channel = 'dashboard');

-- 5. Rimuovi notification_config da orchestrator_config (non più usato)
DELETE FROM orchestrator_config WHERE key = 'notification_config';

-- 6. Pulizia colonne obsolete non più popolate
--    retry_count e delivered_at non vengono più aggiornati.
--    Le colonne rimangono per compatibilità DDL ma con valori di default.
ALTER TABLE orchestrator_notifications
    ALTER COLUMN retry_count SET DEFAULT 0;

COMMIT;

-- Verifica
SELECT
    COUNT(*) AS total_notifications,
    COUNT(*) FILTER (WHERE delivered = FALSE) AS unread,
    COUNT(*) FILTER (WHERE channel != 'dashboard') AS wrong_channel
FROM orchestrator_notifications;

SELECT key FROM orchestrator_config ORDER BY key;
