-- ============================================================
-- SPM ORCHESTRATOR DATABASE SCHEMA
-- Version: 1.1
-- Date: 2026-02-20
-- ============================================================
-- Database separato da SPM-SYNC.
-- errata_cache replica localmente i dati da SPM-SYNC via polling.
-- ============================================================

BEGIN;

-- ============================================================
-- 0. ERRATA CACHE (replica locale da SPM-SYNC via polling)
-- ============================================================

CREATE TABLE IF NOT EXISTS errata_cache (
    errata_id VARCHAR(50) PRIMARY KEY,
    synopsis TEXT,
    description TEXT,
    severity VARCHAR(20),
    type VARCHAR(50),
    issued_date TIMESTAMP,
    target_os VARCHAR(20),              -- 'ubuntu', 'rhel'
    packages JSONB,                     -- [{name, version, size_kb}]
    cves TEXT[],                        -- ['CVE-2026-1234', ...]
    source_url TEXT,
    synced_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_errata_cache_severity ON errata_cache(severity);
CREATE INDEX IF NOT EXISTS idx_errata_cache_os ON errata_cache(target_os);
CREATE INDEX IF NOT EXISTS idx_errata_cache_issued ON errata_cache(issued_date DESC);
CREATE INDEX IF NOT EXISTS idx_errata_cache_synced ON errata_cache(synced_at DESC);

COMMENT ON TABLE errata_cache IS 'Cache locale errata copiati da SPM-SYNC via polling';

-- ============================================================
-- 1. PATCH RISK PROFILE (Success Score)
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_risk_profile (
    errata_id VARCHAR(50) PRIMARY KEY,

    affects_kernel BOOLEAN DEFAULT FALSE,
    requires_reboot BOOLEAN DEFAULT FALSE,
    modifies_config BOOLEAN DEFAULT FALSE,
    dependency_count INTEGER DEFAULT 0,
    package_count INTEGER DEFAULT 1,
    total_size_kb INTEGER DEFAULT 0,

    times_tested INTEGER DEFAULT 0,
    times_failed INTEGER DEFAULT 0,
    last_failure_reason TEXT,
    last_test_date TIMESTAMP,
    last_test_result VARCHAR(20),

    success_score INTEGER DEFAULT 50 CHECK (success_score >= 0 AND success_score <= 100),

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_profile_score ON patch_risk_profile(success_score DESC);
CREATE INDEX IF NOT EXISTS idx_risk_profile_kernel ON patch_risk_profile(affects_kernel);
CREATE INDEX IF NOT EXISTS idx_risk_profile_reboot ON patch_risk_profile(requires_reboot);

COMMENT ON TABLE patch_risk_profile IS 'Profilo di rischio e Success Score per ogni errata';

-- ============================================================
-- 2. PATCH TEST QUEUE
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_test_queue (
    id SERIAL PRIMARY KEY,
    errata_id VARCHAR(50) NOT NULL,
    errata_version VARCHAR(20),
    target_os VARCHAR(20) NOT NULL,

    success_score INTEGER DEFAULT 50,
    priority_override INTEGER DEFAULT 0,

    status VARCHAR(30) DEFAULT 'queued',

    queued_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    test_id INTEGER,
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
-- 3. PATCH TESTS
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_tests (
    id SERIAL PRIMARY KEY,
    queue_id INTEGER REFERENCES patch_test_queue(id) ON DELETE SET NULL,
    errata_id VARCHAR(50) NOT NULL,

    test_system_id INTEGER,
    test_system_name VARCHAR(100),
    test_system_ip VARCHAR(45),

    snapshot_id VARCHAR(100),
    snapshot_type VARCHAR(20),
    snapshot_size_mb INTEGER,

    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_seconds INTEGER,

    result VARCHAR(20),
    failure_reason TEXT,
    failure_phase VARCHAR(50),

    required_reboot BOOLEAN DEFAULT FALSE,
    reboot_performed BOOLEAN DEFAULT FALSE,
    reboot_successful BOOLEAN,

    baseline_metrics JSONB,
    post_patch_metrics JSONB,
    metrics_delta JSONB,
    metrics_evaluation JSONB,

    services_baseline JSONB,
    services_post_patch JSONB,
    failed_services TEXT[],

    test_config JSONB,

    rollback_performed BOOLEAN DEFAULT FALSE,
    rollback_type VARCHAR(20),
    rollback_at TIMESTAMP,

    CONSTRAINT chk_test_result CHECK (result IS NULL OR result IN ('passed', 'failed', 'error', 'aborted'))
);

CREATE INDEX IF NOT EXISTS idx_tests_errata ON patch_tests(errata_id);
CREATE INDEX IF NOT EXISTS idx_tests_queue ON patch_tests(queue_id);
CREATE INDEX IF NOT EXISTS idx_tests_result ON patch_tests(result);
CREATE INDEX IF NOT EXISTS idx_tests_started ON patch_tests(started_at);

COMMENT ON TABLE patch_tests IS 'Risultati dettagliati dei test patch';

ALTER TABLE patch_test_queue
    DROP CONSTRAINT IF EXISTS fk_queue_test;
ALTER TABLE patch_test_queue
    ADD CONSTRAINT fk_queue_test
    FOREIGN KEY (test_id) REFERENCES patch_tests(id) ON DELETE SET NULL;

-- ============================================================
-- 4. PATCH TEST PHASES
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_test_phases (
    id SERIAL PRIMARY KEY,
    test_id INTEGER NOT NULL REFERENCES patch_tests(id) ON DELETE CASCADE,
    phase_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    error_message TEXT,
    output JSONB,

    CONSTRAINT chk_phase_status CHECK (status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped'))
);

CREATE INDEX IF NOT EXISTS idx_phases_test ON patch_test_phases(test_id);

COMMENT ON TABLE patch_test_phases IS 'Tracking fasi individuali di ogni test';

-- ============================================================
-- 5. PATCH APPROVALS
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_approvals (
    id SERIAL PRIMARY KEY,
    queue_id INTEGER REFERENCES patch_test_queue(id) ON DELETE SET NULL,
    errata_id VARCHAR(50) NOT NULL,
    action VARCHAR(20) NOT NULL,
    action_by VARCHAR(100) NOT NULL,
    action_at TIMESTAMP DEFAULT NOW(),
    reason TEXT,
    snooze_until TIMESTAMP,
    ip_address VARCHAR(45),
    user_agent TEXT,

    CONSTRAINT chk_approval_action CHECK (action IN ('approved', 'rejected', 'snoozed'))
);

CREATE INDEX IF NOT EXISTS idx_approvals_errata ON patch_approvals(errata_id);
CREATE INDEX IF NOT EXISTS idx_approvals_queue ON patch_approvals(queue_id);
CREATE INDEX IF NOT EXISTS idx_approvals_action ON patch_approvals(action);

COMMENT ON TABLE patch_approvals IS 'Storico approvazioni/rifiuti patch';

-- ============================================================
-- 6. PATCH DEPLOYMENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_deployments (
    id SERIAL PRIMARY KEY,
    approval_id INTEGER REFERENCES patch_approvals(id) ON DELETE SET NULL,
    errata_id VARCHAR(50) NOT NULL,
    errata_ids TEXT[],
    target_system_ids INTEGER[],
    total_systems INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    scheduled_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    systems_succeeded INTEGER DEFAULT 0,
    systems_failed INTEGER DEFAULT 0,
    failed_system_ids INTEGER[],
    system_results JSONB,
    rollback_performed BOOLEAN DEFAULT FALSE,
    rollback_type VARCHAR(20),
    rollback_id INTEGER,
    rollback_at TIMESTAMP,
    created_by VARCHAR(100),
    notes TEXT,

    CONSTRAINT chk_deployment_status CHECK (status IN (
        'pending', 'scheduled', 'in_progress', 'completed', 'partial_failure', 'rolled_back'
    ))
);

CREATE INDEX IF NOT EXISTS idx_deployments_status ON patch_deployments(status);
CREATE INDEX IF NOT EXISTS idx_deployments_errata ON patch_deployments(errata_id);

COMMENT ON TABLE patch_deployments IS 'Deployment patch in produzione';

-- ============================================================
-- 7. PATCH ROLLBACKS
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_rollbacks (
    id SERIAL PRIMARY KEY,
    deployment_id INTEGER REFERENCES patch_deployments(id) ON DELETE SET NULL,
    errata_id VARCHAR(50) NOT NULL,
    rollback_type VARCHAR(20) NOT NULL,
    target_system_ids INTEGER[],
    total_systems INTEGER NOT NULL,
    initiated_by VARCHAR(100) NOT NULL,
    reason TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'in_progress',
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    systems_succeeded INTEGER DEFAULT 0,
    systems_failed INTEGER DEFAULT 0,
    failed_system_ids INTEGER[],
    system_results JSONB,
    error_details JSONB,

    CONSTRAINT chk_rollback_type CHECK (rollback_type IN ('package', 'system')),
    CONSTRAINT chk_rollback_status CHECK (status IN ('in_progress', 'completed', 'failed', 'partial'))
);

CREATE INDEX IF NOT EXISTS idx_rollbacks_deployment ON patch_rollbacks(deployment_id);
CREATE INDEX IF NOT EXISTS idx_rollbacks_errata ON patch_rollbacks(errata_id);
CREATE INDEX IF NOT EXISTS idx_rollbacks_status ON patch_rollbacks(status);

COMMENT ON TABLE patch_rollbacks IS 'Storico operazioni di rollback';

ALTER TABLE patch_deployments
    DROP CONSTRAINT IF EXISTS fk_deployment_rollback;
ALTER TABLE patch_deployments
    ADD CONSTRAINT fk_deployment_rollback
    FOREIGN KEY (rollback_id) REFERENCES patch_rollbacks(id) ON DELETE SET NULL;

-- ============================================================
-- 8. NOTIFICATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS orchestrator_notifications (
    id SERIAL PRIMARY KEY,
    notification_type VARCHAR(50) NOT NULL,
    errata_id VARCHAR(50),
    queue_id INTEGER,
    test_id INTEGER,
    deployment_id INTEGER,
    channel VARCHAR(20) NOT NULL,
    recipient VARCHAR(200) NOT NULL,
    subject VARCHAR(200),
    body TEXT,
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

COMMENT ON TABLE orchestrator_notifications IS 'Log notifiche inviate';

-- ============================================================
-- 9. CONFIGURATION
-- ============================================================

CREATE TABLE IF NOT EXISTS orchestrator_config (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(100)
);

COMMENT ON TABLE orchestrator_config IS 'Configurazione orchestrator';

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
    "verify_ssl": false
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
-- 10. VIEWS (usano errata_cache locale)
-- ============================================================

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
LEFT JOIN errata_cache e ON q.errata_id = e.errata_id
LEFT JOIN patch_risk_profile rp ON q.errata_id = rp.errata_id
LEFT JOIN patch_tests t ON q.test_id = t.id;

COMMENT ON VIEW v_queue_details IS 'Coda test con dettagli errata e profilo rischio';

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
LEFT JOIN errata_cache e ON q.errata_id = e.errata_id
LEFT JOIN patch_tests t ON q.test_id = t.id
WHERE q.status = 'pending_approval'
ORDER BY e.severity DESC, q.completed_at ASC;

COMMENT ON VIEW v_pending_approvals IS 'Patch in attesa di approvazione';

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
-- 11. FUNCTIONS & TRIGGERS
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_risk_profile_updated ON patch_risk_profile;
CREATE TRIGGER trg_risk_profile_updated
    BEFORE UPDATE ON patch_risk_profile
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_config_updated ON orchestrator_config;
CREATE TRIGGER trg_config_updated
    BEFORE UPDATE ON orchestrator_config
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_errata_cache_updated ON errata_cache;
CREATE TRIGGER trg_errata_cache_updated
    BEFORE UPDATE ON errata_cache
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

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
    FOR EACH ROW EXECUTE FUNCTION update_risk_profile_history();

COMMIT;

-- ============================================================
-- VERIFICA
-- ============================================================

DO $$
DECLARE
    table_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name IN (
        'errata_cache', 'patch_risk_profile', 'patch_test_queue', 'patch_tests',
        'patch_test_phases', 'patch_approvals', 'patch_deployments',
        'patch_rollbacks', 'orchestrator_notifications', 'orchestrator_config'
    );

    IF table_count = 10 THEN
        RAISE NOTICE 'SPM Orchestrator schema v1.1 installed successfully. Tables: %', table_count;
    ELSE
        RAISE WARNING 'Schema incomplete. Expected 10 tables, found %', table_count;
    END IF;
END $$;
