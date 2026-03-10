-- ============================================================
-- UYUNI ERRATA MANAGER - DATABASE SCHEMA
-- Version: 3.3
-- Date: 2026-03-10
-- ============================================================
--
-- Schema per il database dell'Errata Manager.
-- Gestisce errata USN/DSA, CVE, pacchetti UYUNI e log di sync.
--
-- Prerequisiti: database PostgreSQL già creato.
-- Applicare con: psql "$DATABASE_URL" -f errata-schema.sql
-- ============================================================

BEGIN;

-- ============================================================
-- 1. ERRATA (avvisi di sicurezza importati da USN/DSA)
-- ============================================================

CREATE TABLE IF NOT EXISTS errata (
    id           SERIAL PRIMARY KEY,
    advisory_id  VARCHAR(100) NOT NULL UNIQUE,
    title        VARCHAR(500),
    description  TEXT,
    severity     VARCHAR(20),           -- critical, high, medium, low
    source       VARCHAR(10) NOT NULL,  -- 'usn' | 'dsa'
    distribution VARCHAR(50) NOT NULL,  -- 'ubuntu' | 'debian-bookworm' | ...
    issued_date  TIMESTAMP,
    sync_status  VARCHAR(20) DEFAULT 'pending',  -- 'pending' | 'synced'
    created_at   TIMESTAMP DEFAULT NOW(),

    CONSTRAINT chk_errata_source   CHECK (source IN ('usn', 'dsa')),
    CONSTRAINT chk_errata_severity CHECK (severity IS NULL OR severity IN ('critical', 'high', 'medium', 'low')),
    CONSTRAINT chk_errata_status   CHECK (sync_status IN ('pending', 'synced'))
);

CREATE INDEX IF NOT EXISTS idx_errata_advisory    ON errata(advisory_id);
CREATE INDEX IF NOT EXISTS idx_errata_source      ON errata(source);
CREATE INDEX IF NOT EXISTS idx_errata_distribution ON errata(distribution);
CREATE INDEX IF NOT EXISTS idx_errata_severity    ON errata(severity);
CREATE INDEX IF NOT EXISTS idx_errata_sync_status ON errata(sync_status);
CREATE INDEX IF NOT EXISTS idx_errata_issued      ON errata(issued_date DESC);

COMMENT ON TABLE errata IS 'Avvisi di sicurezza importati da Ubuntu USN e Debian DSA';

-- ============================================================
-- 2. ERRATA_PACKAGES (pacchetti associati agli errata)
-- ============================================================

CREATE TABLE IF NOT EXISTS errata_packages (
    id            SERIAL PRIMARY KEY,
    errata_id     INTEGER NOT NULL REFERENCES errata(id) ON DELETE CASCADE,
    package_name  VARCHAR(200) NOT NULL,
    fixed_version VARCHAR(100),
    release_name  VARCHAR(50),          -- es. 'noble', 'jammy', 'bookworm'

    CONSTRAINT uq_errata_pkg UNIQUE (errata_id, package_name, release_name)
);

CREATE INDEX IF NOT EXISTS idx_epkg_errata  ON errata_packages(errata_id);
CREATE INDEX IF NOT EXISTS idx_epkg_name    ON errata_packages(package_name);

COMMENT ON TABLE errata_packages IS 'Pacchetti con versione corretta associati a ogni errata';

-- ============================================================
-- 3. CVEs
-- ============================================================

CREATE TABLE IF NOT EXISTS cves (
    id     SERIAL PRIMARY KEY,
    cve_id VARCHAR(30) NOT NULL UNIQUE  -- es. 'CVE-2024-12345'
);

CREATE INDEX IF NOT EXISTS idx_cve_id ON cves(cve_id);

-- ============================================================
-- 4. ERRATA_CVES (relazione N:M errata ↔ CVE)
-- ============================================================

CREATE TABLE IF NOT EXISTS errata_cves (
    errata_id INTEGER NOT NULL REFERENCES errata(id) ON DELETE CASCADE,
    cve_id    INTEGER NOT NULL REFERENCES cves(id)   ON DELETE CASCADE,
    PRIMARY KEY (errata_id, cve_id)
);

CREATE INDEX IF NOT EXISTS idx_ecve_errata ON errata_cves(errata_id);
CREATE INDEX IF NOT EXISTS idx_ecve_cve    ON errata_cves(cve_id);

-- ============================================================
-- 5. CVE_DETAILS (dettagli NVD: CVSS, severity, descrizione)
-- ============================================================

CREATE TABLE IF NOT EXISTS cve_details (
    cve_id           VARCHAR(30) PRIMARY KEY REFERENCES cves(cve_id) ON DELETE CASCADE,
    cvss_v3_score    NUMERIC(4,1),
    cvss_v3_vector   VARCHAR(100),
    cvss_v3_severity VARCHAR(20),     -- CRITICAL, HIGH, MEDIUM, LOW
    cvss_v2_score    NUMERIC(4,1),
    severity         VARCHAR(20),     -- severity normalizzata finale
    description      TEXT,
    published_date   TIMESTAMP,
    last_modified    TIMESTAMP,
    cwe_ids          TEXT[],          -- es. ['CWE-79', 'CWE-89']
    nvd_last_sync    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cvd_severity ON cve_details(severity);
CREATE INDEX IF NOT EXISTS idx_cvd_score    ON cve_details(cvss_v3_score DESC);

COMMENT ON TABLE cve_details IS 'Dettagli CVSS e severity NVD per ogni CVE';

-- ============================================================
-- 6. UYUNI_PACKAGE_CACHE (cache pacchetti dai canali UYUNI)
-- ============================================================

CREATE TABLE IF NOT EXISTS uyuni_package_cache (
    id              SERIAL PRIMARY KEY,
    channel_label   VARCHAR(200) NOT NULL,
    package_id      INTEGER      NOT NULL,
    package_name    VARCHAR(200) NOT NULL,
    package_version VARCHAR(100),
    package_release VARCHAR(100),
    package_arch    VARCHAR(50),
    last_sync       TIMESTAMP DEFAULT NOW(),

    CONSTRAINT uq_cache_channel_pkg UNIQUE (channel_label, package_id)
);

CREATE INDEX IF NOT EXISTS idx_upc_channel ON uyuni_package_cache(channel_label);
CREATE INDEX IF NOT EXISTS idx_upc_name    ON uyuni_package_cache(package_name);
CREATE INDEX IF NOT EXISTS idx_upc_sync    ON uyuni_package_cache(last_sync);

COMMENT ON TABLE uyuni_package_cache IS 'Cache locale dei pacchetti presenti nei canali UYUNI';

-- ============================================================
-- 7. SYNC_LOGS (log delle operazioni di sincronizzazione)
-- ============================================================

CREATE TABLE IF NOT EXISTS sync_logs (
    id              SERIAL PRIMARY KEY,
    sync_type       VARCHAR(20) NOT NULL,    -- 'usn' | 'dsa' | 'nvd' | 'packages' | 'push'
    status          VARCHAR(20) DEFAULT 'running',  -- 'running' | 'completed' | 'error'
    started_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP,
    items_processed INTEGER,
    error_message   TEXT,

    CONSTRAINT chk_log_type   CHECK (sync_type IN ('usn', 'dsa', 'nvd', 'packages', 'push')),
    CONSTRAINT chk_log_status CHECK (status IN ('running', 'completed', 'error'))
);

CREATE INDEX IF NOT EXISTS idx_slog_type    ON sync_logs(sync_type);
CREATE INDEX IF NOT EXISTS idx_slog_status  ON sync_logs(status);
CREATE INDEX IF NOT EXISTS idx_slog_started ON sync_logs(started_at DESC);

COMMENT ON TABLE sync_logs IS 'Log delle operazioni di sincronizzazione USN/DSA/NVD';

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
        'errata', 'errata_packages', 'cves', 'errata_cves',
        'cve_details', 'uyuni_package_cache', 'sync_logs'
    );

    IF table_count = 7 THEN
        RAISE NOTICE 'Errata Manager schema installed successfully (% tables)', table_count;
    ELSE
        RAISE WARNING 'Schema may be incomplete: expected 7 tables, found %', table_count;
    END IF;
END $$;

COMMIT;
