-- P3 Patch Testing Schema
-- Run after main schema

-- Tabella principale test patch
CREATE TABLE IF NOT EXISTS patch_tests (
    id SERIAL PRIMARY KEY,
    errata_id INTEGER REFERENCES errata(id),
    source_system_id INTEGER NOT NULL,
    source_vm_name VARCHAR(255) NOT NULL,
    test_vm_name VARCHAR(255),
    snapshot_id VARCHAR(255),

    -- Status tracking
    status VARCHAR(50) NOT NULL DEFAULT 'pending',

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Configuration
    test_config JSONB DEFAULT '{}',

    -- Results
    result VARCHAR(20),
    result_reason TEXT,
    test_report JSONB,

    -- Error handling
    error_message TEXT,
    retry_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_patch_tests_status ON patch_tests(status);
CREATE INDEX IF NOT EXISTS idx_patch_tests_errata ON patch_tests(errata_id);
CREATE INDEX IF NOT EXISTS idx_patch_tests_source ON patch_tests(source_system_id);

-- Metriche raccolte durante i test
CREATE TABLE IF NOT EXISTS patch_test_metrics (
    id SERIAL PRIMARY KEY,
    test_id INTEGER REFERENCES patch_tests(id) ON DELETE CASCADE,
    phase VARCHAR(20) NOT NULL,
    collected_at TIMESTAMP DEFAULT NOW(),

    -- System metrics
    cpu_usage_avg DECIMAL(5,2),
    cpu_usage_max DECIMAL(5,2),
    memory_usage_percent DECIMAL(5,2),
    memory_used_mb INTEGER,
    disk_io_read_mbps DECIMAL(10,2),
    disk_io_write_mbps DECIMAL(10,2),

    -- Network metrics
    network_connections INTEGER,
    network_bytes_in BIGINT,
    network_bytes_out BIGINT,

    -- Service metrics
    services_running INTEGER,
    services_failed INTEGER,
    services_list JSONB,

    -- Process metrics
    critical_processes_ok BOOLEAN,
    processes_list JSONB,

    -- Custom checks
    custom_checks JSONB
);

CREATE INDEX IF NOT EXISTS idx_test_metrics_test ON patch_test_metrics(test_id);
CREATE INDEX IF NOT EXISTS idx_test_metrics_phase ON patch_test_metrics(phase);

-- Log eventi del test
CREATE TABLE IF NOT EXISTS patch_test_events (
    id SERIAL PRIMARY KEY,
    test_id INTEGER REFERENCES patch_tests(id) ON DELETE CASCADE,
    event_time TIMESTAMP DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    event_message TEXT,
    event_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_test_events_test ON patch_test_events(test_id);

-- Aggiorna errata table con colonna per test status
ALTER TABLE errata ADD COLUMN IF NOT EXISTS test_status VARCHAR(20) DEFAULT 'not_tested';
-- not_tested, testing, passed, failed, approved, rejected
