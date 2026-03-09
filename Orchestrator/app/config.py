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
    HOST = os.getenv("FLASK_HOST", "127.0.0.1")  # loopback by default — set 0.0.0.0 only if needed
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
    # Prometheus
    # ----------------------------------------------------------
    PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    PROMETHEUS_TIMEOUT = int(os.getenv("PROMETHEUS_TIMEOUT_SECONDS", 30))

    # ----------------------------------------------------------
    # Test Systems
    # ----------------------------------------------------------
    # Valori vuoti → auto-discovery da gruppi UYUNI test-*
    TEST_SYSTEMS = {
        "ubuntu": {
            "system_id":   _to_int(os.getenv("TEST_SYSTEM_UBUNTU_ID")),
            "system_name": os.getenv("TEST_SYSTEM_UBUNTU_NAME", ""),
            "system_ip":   os.getenv("TEST_SYSTEM_UBUNTU_IP", ""),
        },
        "rhel": {
            "system_id":   _to_int(os.getenv("TEST_SYSTEM_RHEL_ID")),
            "system_name": os.getenv("TEST_SYSTEM_RHEL_NAME", ""),
            "system_ip":   os.getenv("TEST_SYSTEM_RHEL_IP", ""),
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
    # Attesa prima che il minion UYUNI riceva e applichi il comando di reboot.
    # Su Salt, il check-in del minion puo' avvenire ogni 30-60s.
    # Aumentare se il sistema non risulta "in shutdown" durante wait_online.
    TEST_REBOOT_DELIVERY_WAIT = int(os.getenv("TEST_REBOOT_DELIVERY_WAIT_SECONDS", 60))
    # Attesa post-reboot dopo che il sistema e' tornato online, per lasciare
    # che i servizi si stabilizzino prima di Prometheus validate e service check.
    TEST_REBOOT_STABILIZATION = int(os.getenv("TEST_REBOOT_STABILIZATION_SECONDS", 30))
    TEST_TIMEOUT_MINUTES = int(os.getenv("TEST_TIMEOUT_MINUTES", 30))

    # ----------------------------------------------------------
    # Logging
    # ----------------------------------------------------------
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "/var/log/spm-orchestrator/app.log")

    # ----------------------------------------------------------
    # API Security
    # ----------------------------------------------------------
    # Chiave condivisa tra Streamlit e Flask API.
    # Se non vuota, tutte le richieste API devono includere X-SPM-Key: <key>.
    # Impostare in .env come SPM_API_KEY=<stringa-casuale-lunga>.
    API_KEY = os.getenv("SPM_API_KEY", "")

    # ----------------------------------------------------------
    # App metadata
    # ----------------------------------------------------------
    APP_NAME = "spm-orchestrator"
    APP_VERSION = "1.1.0"
