-- ============================================================
-- SPM ORCHESTRATOR DATABASE SCHEMA
-- Version: 1.0
-- Date: 2026-02-05
-- ============================================================

-- Questo schema estende il database SPM esistente con le tabelle
-- necessarie per l'orchestrazione dei test e approvazioni.

BEGIN;

-- ============================================================
-- 1. PATCH RISK PROFILE (Success Score)
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_risk_profile (
    errata_id VARCHAR(50) PRIMARY KEY,

    -- Fattori di rischio (calcolati dall'analisi pacchetti)
    affects_kernel BOOLEAN DEFAULT FALSE,
    requires_reboot BOOLEAN DEFAULT FALSE,
    modifies_config BOOLEAN DEFAULT FALSE,
    dependency_count INTEGER DEFAULT 0,
    package_count INTEGER DEFAULT 1,
    total_size_kb INTEGER DEFAULT 0,

    -- Storico test (aggiornato dopo ogni test)
    times_tested INTEGER DEFAULT 0,
    times_failed INTEGER DEFAULT 0,
    last_failure_reason TEXT,
    last_test_date TIMESTAMP,
    last_test_result VARCHAR(20),

    -- Success Score (0-100, più alto = più sicuro)
    success_score INTEGER DEFAULT 50 CHECK (success_score >= 0 AND success_score <= 100),

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_profile_score ON patch_risk_profile(success_score DESC);
CREATE INDEX IF NOT EXISTS idx_risk_profile_kernel ON patch_risk_profile(affects_kernel);
CREATE INDEX IF NOT EXISTS idx_risk_profile_reboot ON patch_risk_profile(requires_reboot);

COMMENT ON TABLE patch_risk_profile IS 'Profilo di rischio e Success Score per ogni errata';
COMMENT ON COLUMN patch_risk_profile.success_score IS 'Score 0-100: più alto = patch più sicura da testare prima';

-- ============================================================
-- 2. PATCH TEST QUEUE (Coda ordinata per test)
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_test_queue (
    id SERIAL PRIMARY KEY,
    errata_id VARCHAR(50) NOT NULL,
    errata_version VARCHAR(20),          -- Per tracking nuove versioni
    target_os VARCHAR(20) NOT NULL,      -- 'ubuntu' o 'rhel'

    -- Priorità
    success_score INTEGER DEFAULT 50,    -- Cached from risk_profile
    priority_override INTEGER DEFAULT 0, -- Override manuale (0 = usa score)

    -- Stato workflow
    status VARCHAR(30) DEFAULT 'queued',
    -- Stati possibili:
    -- queued, testing, passed, failed, needs_reboot, rebooting,
    -- pending_approval, approved, rejected, snoozed,
    -- promoting, prod_pending, prod_applied, completed, rolled_back

    -- Timestamps
    queued_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Riferimento al test eseguito
    test_id INTEGER,

    -- Metadata
    created_by VARCHAR(100),
    notes TEXT,

    CONSTRAINT chk_queue_os CHECK (target_os IN ('ubuntu', 'rhel')),
    CONSTRAINT chk_queue_status CHECK (status IN (
        'queued', 'testing', 'passed', 'failed', 'needs_reboot', 'rebooting',
        'pending_approval', 'approved', 'rejected', 'snoozed',
        'promoting', 'prod_pending', 'prod_applied', 'completed', 'rolled_back'
    ))
);

CREATE INDEX IF NOT EXISTS idx_queue_status ON patch_test_queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_os ON patch_test_queue(target_os);
CREATE INDEX IF NOT EXISTS idx_queue_priority ON patch_test_queue(success_score DESC, priority_override DESC);
CREATE INDEX IF NOT EXISTS idx_queue_errata ON patch_test_queue(errata_id);
CREATE INDEX IF NOT EXISTS idx_queue_queued_at ON patch_test_queue(queued_at);

COMMENT ON TABLE patch_test_queue IS 'Coda test patch ordinata per Success Score';

-- ============================================================
-- 3. PATCH TESTS (Risultati test)
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_tests (
    id SERIAL PRIMARY KEY,
    queue_id INTEGER REFERENCES patch_test_queue(id) ON DELETE SET NULL,
    errata_id VARCHAR(50) NOT NULL,

    -- Sistema di test utilizzato
    test_system_id INTEGER,              -- UYUNI system ID
    test_system_name VARCHAR(100),
    test_system_ip VARCHAR(45),

    -- Snapshot
    snapshot_id VARCHAR(100),
    snapshot_type VARCHAR(20),           -- 'snapper', 'lvm', 'azure'
    snapshot_size_mb INTEGER,

    -- Timing
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_seconds INTEGER,

    -- Risultato
    result VARCHAR(20),                  -- 'passed', 'failed', 'error', 'aborted'
    failure_reason TEXT,
    failure_phase VARCHAR(50),           -- Fase in cui è fallito

    -- Reboot
    required_reboot BOOLEAN DEFAULT FALSE,
    reboot_performed BOOLEAN DEFAULT FALSE,
    reboot_successful BOOLEAN,

    -- Metriche (JSONB per flessibilità)
    baseline_metrics JSONB,
    post_patch_metrics JSONB,
    metrics_delta JSONB,
    metrics_evaluation JSONB,

    -- Servizi
    services_baseline JSONB,
    services_post_patch JSONB,
    failed_services TEXT[],

    -- Configurazione test usata
    test_config JSONB,

    -- Rollback (se eseguito durante test)
    rollback_performed BOOLEAN DEFAULT FALSE,
    rollback_type VARCHAR(20),
    rollback_at TIMESTAMP,

    CONSTRAINT chk_test_result CHECK (result IS NULL OR result IN ('passed', 'failed', 'error', 'aborted'))
);

CREATE INDEX IF NOT EXISTS idx_tests_errata ON patch_tests(errata_id);
CREATE INDEX IF NOT EXISTS idx_tests_queue ON patch_tests(queue_id);
CREATE INDEX IF NOT EXISTS idx_tests_result ON patch_tests(result);
CREATE INDEX IF NOT EXISTS idx_tests_started ON patch_tests(started_at);
CREATE INDEX IF NOT EXISTS idx_tests_system ON patch_tests(test_system_id);

COMMENT ON TABLE patch_tests IS 'Risultati dettagliati dei test patch';

-- Aggiorna foreign key in queue dopo creazione patch_tests
ALTER TABLE patch_test_queue
    DROP CONSTRAINT IF EXISTS fk_queue_test;
ALTER TABLE patch_test_queue
    ADD CONSTRAINT fk_queue_test
    FOREIGN KEY (test_id) REFERENCES patch_tests(id) ON DELETE SET NULL;

-- ============================================================
-- 4. PATCH TEST PHASES (Fasi del test per tracking)
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_test_phases (
    id SERIAL PRIMARY KEY,
    test_id INTEGER NOT NULL REFERENCES patch_tests(id) ON DELETE CASCADE,

    phase_name VARCHAR(50) NOT NULL,
    -- Fasi: snapshot_create, baseline_collect, patch_apply,
    --       stabilization_wait, reboot_wait, post_metrics_collect, evaluation

    status VARCHAR(20) DEFAULT 'pending',
    -- pending, in_progress, completed, failed, skipped

    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,

    error_message TEXT,
    output JSONB,

    CONSTRAINT chk_phase_status CHECK (status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped'))
);

CREATE INDEX IF NOT EXISTS idx_phases_test ON patch_test_phases(test_id);
CREATE INDEX IF NOT EXISTS idx_phases_status ON patch_test_phases(status);

COMMENT ON TABLE patch_test_phases IS 'Tracking fasi individuali di ogni test';

-- ============================================================
-- 5. PATCH APPROVALS (Workflow approvazione)
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_approvals (
    id SERIAL PRIMARY KEY,
    queue_id INTEGER REFERENCES patch_test_queue(id) ON DELETE SET NULL,
    errata_id VARCHAR(50) NOT NULL,

    -- Azione
    action VARCHAR(20) NOT NULL,         -- 'approved', 'rejected', 'snoozed'

    -- Chi e quando
    action_by VARCHAR(100) NOT NULL,
    action_at TIMESTAMP DEFAULT NOW(),

    -- Dettagli
    reason TEXT,
    snooze_until TIMESTAMP,              -- Se snoozed

    -- Audit
    ip_address VARCHAR(45),
    user_agent TEXT,

    CONSTRAINT chk_approval_action CHECK (action IN ('approved', 'rejected', 'snoozed'))
);

CREATE INDEX IF NOT EXISTS idx_approvals_errata ON patch_approvals(errata_id);
CREATE INDEX IF NOT EXISTS idx_approvals_queue ON patch_approvals(queue_id);
CREATE INDEX IF NOT EXISTS idx_approvals_action ON patch_approvals(action);
CREATE INDEX IF NOT EXISTS idx_approvals_date ON patch_approvals(action_at);

COMMENT ON TABLE patch_approvals IS 'Storico approvazioni/rifiuti patch';

-- ============================================================
-- 6. PATCH DEPLOYMENTS (Deployment in produzione)
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_deployments (
    id SERIAL PRIMARY KEY,
    approval_id INTEGER REFERENCES patch_approvals(id) ON DELETE SET NULL,
    errata_id VARCHAR(50) NOT NULL,
    errata_ids TEXT[],                   -- Se deployment batch

    -- Sistemi target
    target_system_ids INTEGER[],         -- UYUNI system IDs
    total_systems INTEGER NOT NULL,

    -- Stato
    status VARCHAR(20) DEFAULT 'pending',
    -- pending, scheduled, in_progress, completed, partial_failure, rolled_back

    -- Timing
    scheduled_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Risultati
    systems_succeeded INTEGER DEFAULT 0,
    systems_failed INTEGER DEFAULT 0,
    failed_system_ids INTEGER[],

    -- Dettagli per sistema (JSONB)
    system_results JSONB,

    -- Rollback
    rollback_performed BOOLEAN DEFAULT FALSE,
    rollback_type VARCHAR(20),
    rollback_id INTEGER,
    rollback_at TIMESTAMP,

    -- Metadata
    created_by VARCHAR(100),
    notes TEXT,

    CONSTRAINT chk_deployment_status CHECK (status IN (
        'pending', 'scheduled', 'in_progress', 'completed', 'partial_failure', 'rolled_back'
    ))
);

CREATE INDEX IF NOT EXISTS idx_deployments_status ON patch_deployments(status);
CREATE INDEX IF NOT EXISTS idx_deployments_errata ON patch_deployments(errata_id);
CREATE INDEX IF NOT EXISTS idx_deployments_scheduled ON patch_deployments(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_deployments_approval ON patch_deployments(approval_id);

COMMENT ON TABLE patch_deployments IS 'Deployment patch in produzione';

-- ============================================================
-- 7. PATCH ROLLBACKS (Storico rollback)
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_rollbacks (
    id SERIAL PRIMARY KEY,
    deployment_id INTEGER REFERENCES patch_deployments(id) ON DELETE SET NULL,
    errata_id VARCHAR(50) NOT NULL,

    -- Tipo rollback
    rollback_type VARCHAR(20) NOT NULL,  -- 'package', 'system'

    -- Target
    target_system_ids INTEGER[],
    total_systems INTEGER NOT NULL,

    -- Chi e perché
    initiated_by VARCHAR(100) NOT NULL,
    reason TEXT NOT NULL,

    -- Stato
    status VARCHAR(20) DEFAULT 'in_progress',
    -- in_progress, completed, failed, partial

    -- Timing
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_seconds INTEGER,

    -- Risultati
    systems_succeeded INTEGER DEFAULT 0,
    systems_failed INTEGER DEFAULT 0,
    failed_system_ids INTEGER[],

    -- Dettagli
    system_results JSONB,
    error_details JSONB,

    CONSTRAINT chk_rollback_type CHECK (rollback_type IN ('package', 'system')),
    CONSTRAINT chk_rollback_status CHECK (status IN ('in_progress', 'completed', 'failed', 'partial'))
);

CREATE INDEX IF NOT EXISTS idx_rollbacks_deployment ON patch_rollbacks(deployment_id);
CREATE INDEX IF NOT EXISTS idx_rollbacks_errata ON patch_rollbacks(errata_id);
CREATE INDEX IF NOT EXISTS idx_rollbacks_status ON patch_rollbacks(status);
CREATE INDEX IF NOT EXISTS idx_rollbacks_date ON patch_rollbacks(started_at);

COMMENT ON TABLE patch_rollbacks IS 'Storico operazioni di rollback';

-- Aggiorna riferimento in deployments
ALTER TABLE patch_deployments
    DROP CONSTRAINT IF EXISTS fk_deployment_rollback;
ALTER TABLE patch_deployments
    ADD CONSTRAINT fk_deployment_rollback
    FOREIGN KEY (rollback_id) REFERENCES patch_rollbacks(id) ON DELETE SET NULL;

-- ============================================================
-- 8. NOTIFICATIONS (Notifiche inviate)
-- ============================================================

CREATE TABLE IF NOT EXISTS orchestrator_notifications (
    id SERIAL PRIMARY KEY,

    -- Tipo notifica
    notification_type VARCHAR(50) NOT NULL,
    -- test_started, test_passed, test_failed, pending_approval,
    -- approval_reminder, deployment_started, deployment_completed,
    -- deployment_failed, rollback_initiated, daily_digest

    -- Riferimenti
    errata_id VARCHAR(50),
    queue_id INTEGER,
    test_id INTEGER,
    deployment_id INTEGER,

    -- Destinazione
    channel VARCHAR(20) NOT NULL,        -- 'email', 'webhook'
    recipient VARCHAR(200) NOT NULL,

    -- Contenuto
    subject VARCHAR(200),
    body TEXT,

    -- Stato
    sent_at TIMESTAMP DEFAULT NOW(),
    delivered BOOLEAN DEFAULT FALSE,
    delivered_at TIMESTAMP,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,

    CONSTRAINT chk_notification_channel CHECK (channel IN ('email', 'webhook'))
);

CREATE INDEX IF NOT EXISTS idx_notifications_type ON orchestrator_notifications(notification_type);
CREATE INDEX IF NOT EXISTS idx_notifications_sent ON orchestrator_notifications(sent_at);
CREATE INDEX IF NOT EXISTS idx_notifications_delivered ON orchestrator_notifications(delivered);
CREATE INDEX IF NOT EXISTS idx_notifications_errata ON orchestrator_notifications(errata_id);

COMMENT ON TABLE orchestrator_notifications IS 'Log notifiche inviate';

-- ============================================================
-- 9. ORCHESTRATOR CONFIGURATION
-- ============================================================

CREATE TABLE IF NOT EXISTS orchestrator_config (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(100)
);

COMMENT ON TABLE orchestrator_config IS 'Configurazione orchestrator';

-- Inserisci configurazione di default
INSERT INTO orchestrator_config (key, value, description) VALUES

('score_weights', '{
    "kernel_penalty": 30,
    "reboot_penalty": 15,
    "config_penalty": 10,
    "dependency_penalty_per": 3,
    "dependency_penalty_max": 15,
    "size_penalty_per_mb": 2,
    "size_penalty_max": 10,
    "history_penalty_max": 20,
    "min_tests_for_history": 3,
    "small_patch_bonus": 5,
    "small_patch_threshold_kb": 100
}', 'Pesi per calcolo Success Score'),

('test_thresholds', '{
    "cpu_delta_percent": 20,
    "memory_delta_percent": 15,
    "max_failed_services": 0,
    "wait_after_patch_seconds": 300,
    "wait_after_reboot_seconds": 180,
    "test_timeout_minutes": 30,
    "snapshot_timeout_seconds": 120
}', 'Soglie per validazione test'),

('critical_services', '{
    "ubuntu": ["ssh", "salt-minion"],
    "rhel": ["sshd", "salt-minion"]
}', 'Servizi critici da verificare per OS'),

('notification_config', '{
    "email_enabled": false,
    "smtp_server": "",
    "smtp_port": 587,
    "smtp_tls": true,
    "smtp_user": "",
    "smtp_password": "",
    "from_address": "spm@example.com",
    "recipients": [],
    "digest_enabled": true,
    "digest_time": "08:00",
    "alert_on_test_failure": true,
    "alert_on_pending_approval": true,
    "approval_reminder_days": 2,
    "webhook_enabled": false,
    "webhook_url": "",
    "webhook_auth_header": ""
}', 'Configurazione notifiche'),

('test_systems', '{
    "ubuntu": {
        "system_id": null,
        "system_name": "test-ubuntu-01",
        "snapshot_type": "snapper"
    },
    "rhel": {
        "system_id": null,
        "system_name": "test-rhel-01",
        "snapshot_type": "snapper"
    }
}', 'Sistemi di test per OS'),

('prometheus_config', '{
    "url": "http://localhost:9090",
    "scrape_interval_seconds": 15,
    "query_timeout_seconds": 30
}', 'Configurazione Prometheus'),

('uyuni_config', '{
    "url": "https://uyuni.example.com",
    "user": "",
    "verify_ssl": true
}', 'Configurazione connessione UYUNI'),

('workflow_config', '{
    "auto_queue_new_errata": true,
    "auto_queue_min_severity": "Medium",
    "auto_start_tests": false,
    "auto_approve_passed": false,
    "approval_required_severities": ["Critical", "High", "Medium", "Low"],
    "auto_retry_new_version": true,
    "max_test_retries": 2,
    "snooze_max_days": 30
}', 'Configurazione workflow')

ON CONFLICT (key) DO NOTHING;

-- ============================================================
-- 10. VIEWS UTILI
-- ============================================================

-- Vista: Coda test con dettagli errata
CREATE OR REPLACE VIEW v_queue_details AS
SELECT
    q.id AS queue_id,
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
    e.type AS errata_type,
    e.issued_date,
    rp.affects_kernel,
    rp.requires_reboot,
    rp.times_tested,
    rp.times_failed,
    t.result AS test_result,
    t.duration_seconds AS test_duration
FROM patch_test_queue q
LEFT JOIN errata e ON q.errata_id = e.errata_id
LEFT JOIN patch_risk_profile rp ON q.errata_id = rp.errata_id
LEFT JOIN patch_tests t ON q.test_id = t.id;

COMMENT ON VIEW v_queue_details IS 'Coda test con dettagli errata e profilo rischio';

-- Vista: Pending approvals
CREATE OR REPLACE VIEW v_pending_approvals AS
SELECT
    q.id AS queue_id,
    q.errata_id,
    q.target_os,
    q.success_score,
    q.completed_at AS tested_at,
    e.synopsis,
    e.severity,
    t.result AS test_result,
    t.duration_seconds,
    t.required_reboot,
    t.metrics_evaluation,
    EXTRACT(EPOCH FROM (NOW() - q.completed_at))/3600 AS hours_pending
FROM patch_test_queue q
JOIN errata e ON q.errata_id = e.errata_id
LEFT JOIN patch_tests t ON q.test_id = t.id
WHERE q.status = 'pending_approval'
ORDER BY e.severity DESC, q.completed_at ASC;

COMMENT ON VIEW v_pending_approvals IS 'Patch in attesa di approvazione';

-- Vista: Statistiche giornaliere
CREATE OR REPLACE VIEW v_daily_stats AS
SELECT
    DATE(queued_at) AS date,
    COUNT(*) AS total_queued,
    COUNT(*) FILTER (WHERE status = 'passed') AS passed,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
    COUNT(*) FILTER (WHERE status = 'pending_approval') AS pending_approval,
    COUNT(*) FILTER (WHERE status = 'approved') AS approved,
    COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
    COUNT(*) FILTER (WHERE status IN ('prod_applied', 'completed')) AS deployed
FROM patch_test_queue
WHERE queued_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE(queued_at)
ORDER BY date DESC;

COMMENT ON VIEW v_daily_stats IS 'Statistiche giornaliere ultimi 30 giorni';

-- ============================================================
-- 11. FUNCTIONS
-- ============================================================

-- Funzione: Aggiorna timestamp updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger per patch_risk_profile
DROP TRIGGER IF EXISTS trg_risk_profile_updated ON patch_risk_profile;
CREATE TRIGGER trg_risk_profile_updated
    BEFORE UPDATE ON patch_risk_profile
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Trigger per orchestrator_config
DROP TRIGGER IF EXISTS trg_config_updated ON orchestrator_config;
CREATE TRIGGER trg_config_updated
    BEFORE UPDATE ON orchestrator_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Funzione: Aggiorna storico in risk_profile dopo test
CREATE OR REPLACE FUNCTION update_risk_profile_history()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.result IS NOT NULL AND OLD.result IS NULL THEN
        UPDATE patch_risk_profile
        SET
            times_tested = times_tested + 1,
            times_failed = times_failed + CASE WHEN NEW.result = 'failed' THEN 1 ELSE 0 END,
            last_test_date = NEW.completed_at,
            last_test_result = NEW.result,
            last_failure_reason = CASE WHEN NEW.result = 'failed' THEN NEW.failure_reason ELSE last_failure_reason END
        WHERE errata_id = NEW.errata_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_risk_history ON patch_tests;
CREATE TRIGGER trg_update_risk_history
    AFTER UPDATE ON patch_tests
    FOR EACH ROW
    EXECUTE FUNCTION update_risk_profile_history();

-- Funzione: Calcola posizione in coda
CREATE OR REPLACE FUNCTION get_queue_position(p_queue_id INTEGER)
RETURNS INTEGER AS $$
DECLARE
    v_position INTEGER;
BEGIN
    SELECT position INTO v_position
    FROM (
        SELECT id, ROW_NUMBER() OVER (ORDER BY success_score DESC, priority_override DESC, queued_at ASC) AS position
        FROM patch_test_queue
        WHERE status = 'queued'
    ) ranked
    WHERE id = p_queue_id;

    RETURN v_position;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_queue_position IS 'Restituisce posizione in coda per un queue_id';

COMMIT;

-- ============================================================
-- VERIFICA INSTALLAZIONE
-- ============================================================

DO $$
DECLARE
    table_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name IN (
        'patch_risk_profile', 'patch_test_queue', 'patch_tests',
        'patch_test_phases', 'patch_approvals', 'patch_deployments',
        'patch_rollbacks', 'orchestrator_notifications', 'orchestrator_config'
    );

    IF table_count = 9 THEN
        RAISE NOTICE 'SPM Orchestrator schema installed successfully. Tables created: %', table_count;
    ELSE
        RAISE WARNING 'Schema installation may be incomplete. Expected 9 tables, found %', table_count;
    END IF;
END $$;
