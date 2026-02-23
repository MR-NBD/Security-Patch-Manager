"""
SPM Orchestrator - Configuration

Carica configurazione da environment variables (.env).
Tutti i valori hanno defaults sicuri per development.
"""

import os
from dotenv import load_dotenv

# Carica .env se presente
load_dotenv()


def _to_int(value) -> int | None:
    """Converte stringa in int, None se vuota"""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


class Config:
    """Configurazione centralizzata dell'applicazione"""

    # ----------------------------------------------------------
    # Flask
    # ----------------------------------------------------------
    ENV = os.getenv("FLASK_ENV", "production")
    PORT = int(os.getenv("FLASK_PORT", 5001))
    HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-in-production")
    DEBUG = ENV == "development"

    # ----------------------------------------------------------
    # Database
    # ----------------------------------------------------------
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 5432))
    DB_NAME = os.getenv("DB_NAME", "spm_orchestrator")
    DB_USER = os.getenv("DB_USER", "spm_orch")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    @classmethod
    def db_dsn(cls) -> str:
        """Restituisce DSN PostgreSQL"""
        return (
            f"host={cls.DB_HOST} "
            f"port={cls.DB_PORT} "
            f"dbname={cls.DB_NAME} "
            f"user={cls.DB_USER} "
            f"password={cls.DB_PASSWORD}"
        )

    # ----------------------------------------------------------
    # UYUNI (fonte errata, polling gruppi test-*)
    # ----------------------------------------------------------
    UYUNI_URL = os.getenv("UYUNI_URL", "https://10.172.2.17")
    UYUNI_USER = os.getenv("UYUNI_USER", "admin")
    UYUNI_PASSWORD = os.getenv("UYUNI_PASSWORD", "")
    UYUNI_VERIFY_SSL = os.getenv("UYUNI_VERIFY_SSL", "false").lower() == "true"
    UYUNI_TIMEOUT = int(os.getenv("UYUNI_TIMEOUT_SECONDS", 30))
    UYUNI_POLL_INTERVAL = int(os.getenv("UYUNI_POLL_INTERVAL_MINUTES", 30))
    UYUNI_TEST_GROUP_PREFIX = os.getenv("UYUNI_TEST_GROUP_PREFIX", "test-")
    UYUNI_SYNC_WORKERS = int(os.getenv("UYUNI_SYNC_WORKERS", 10))

    # ----------------------------------------------------------
    # Salt API
    # ----------------------------------------------------------
    SALT_API_URL = os.getenv("SALT_API_URL", "https://10.172.2.17:9080")
    SALT_API_USER = os.getenv("SALT_API_USER", "saltapi")
    SALT_API_PASSWORD = os.getenv("SALT_API_PASSWORD", "")

    # ----------------------------------------------------------
    # Prometheus
    # ----------------------------------------------------------
    PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    PROMETHEUS_TIMEOUT = int(os.getenv("PROMETHEUS_TIMEOUT_SECONDS", 30))

    # ----------------------------------------------------------
    # Test Systems
    # ----------------------------------------------------------
    TEST_SYSTEMS = {
        "ubuntu": {
            "system_id": _to_int(os.getenv("TEST_SYSTEM_UBUNTU_ID")),
            "system_name": os.getenv("TEST_SYSTEM_UBUNTU_NAME", "test-ubuntu-01"),
        },
        "rhel": {
            "system_id": _to_int(os.getenv("TEST_SYSTEM_RHEL_ID")),
            "system_name": os.getenv("TEST_SYSTEM_RHEL_NAME", "test-rhel-01"),
        },
    }
    SNAPSHOT_TYPE = os.getenv("SNAPSHOT_TYPE", "snapper")

    # ----------------------------------------------------------
    # Test Thresholds
    # ----------------------------------------------------------
    TEST_CPU_DELTA = int(os.getenv("TEST_CPU_DELTA_THRESHOLD", 20))
    TEST_MEMORY_DELTA = int(os.getenv("TEST_MEMORY_DELTA_THRESHOLD", 15))
    TEST_MAX_FAILED_SERVICES = int(os.getenv("TEST_MAX_FAILED_SERVICES", 0))
    TEST_WAIT_AFTER_PATCH = int(os.getenv("TEST_WAIT_AFTER_PATCH_SECONDS", 300))
    TEST_WAIT_AFTER_REBOOT = int(os.getenv("TEST_WAIT_AFTER_REBOOT_SECONDS", 180))
    TEST_TIMEOUT_MINUTES = int(os.getenv("TEST_TIMEOUT_MINUTES", 30))

    # ----------------------------------------------------------
    # Logging
    # ----------------------------------------------------------
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "/var/log/spm-orchestrator/app.log")

    # ----------------------------------------------------------
    # App metadata
    # ----------------------------------------------------------
    APP_NAME = "spm-orchestrator"
    APP_VERSION = "1.0.0"


