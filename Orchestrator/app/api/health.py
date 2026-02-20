"""
SPM Orchestrator - Health Endpoints

GET /api/v1/health         → stato base (risposta rapida)
GET /api/v1/health/detail  → stato dettagliato con check componenti
"""

import logging
import time
import xmlrpc.client
import requests
from flask import Blueprint, jsonify

from app.config import Config
from app.services.db import check_db_health

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__)

# Timestamp avvio applicazione
_start_time = time.time()


@health_bp.route("/api/v1/health", methods=["GET"])
def health():
    """
    Health check base - risposta rapida senza check componenti.
    Usato da load balancer / systemd watchdog.
    """
    return jsonify({
        "status": "healthy",
        "version": Config.APP_VERSION,
        "app": Config.APP_NAME,
    }), 200


@health_bp.route("/api/v1/health/detail", methods=["GET"])
def health_detail():
    """
    Health check dettagliato con verifica di ogni componente.
    Più lento, usato per monitoraggio.
    """
    uptime = int(time.time() - _start_time)
    components = {}
    overall = "healthy"

    # --- Database ---
    db_status = check_db_health()
    components["database"] = db_status
    if db_status["status"] == "error":
        overall = "degraded"

    # --- SPM-SYNC ---
    components["spm_sync"] = _check_spm_sync()
    if components["spm_sync"]["status"] == "error":
        overall = "degraded"

    # --- UYUNI ---
    components["uyuni"] = _check_uyuni()
    if components["uyuni"]["status"] == "error":
        overall = "degraded"

    # --- Prometheus ---
    components["prometheus"] = _check_prometheus()
    # Prometheus non critico: degraded ma non unhealthy

    status_code = 200 if overall == "healthy" else 207

    return jsonify({
        "status": overall,
        "version": Config.APP_VERSION,
        "app": Config.APP_NAME,
        "uptime_seconds": uptime,
        "components": components,
    }), status_code


# ----------------------------------------------------------
# Check singoli componenti
# ----------------------------------------------------------

def _check_spm_sync() -> dict:
    """Verifica raggiungibilità SPM-SYNC"""
    try:
        response = requests.get(
            f"{Config.SPM_SYNC_URL}/api/health",
            timeout=5,
        )
        if response.status_code == 200:
            return {"status": "connected", "url": Config.SPM_SYNC_URL}
        return {
            "status": "error",
            "message": f"HTTP {response.status_code}",
            "url": Config.SPM_SYNC_URL,
        }
    except requests.ConnectionError:
        return {
            "status": "error",
            "message": "Connection refused",
            "url": Config.SPM_SYNC_URL,
        }
    except requests.Timeout:
        return {
            "status": "error",
            "message": "Timeout",
            "url": Config.SPM_SYNC_URL,
        }


def _check_uyuni() -> dict:
    """Verifica raggiungibilità UYUNI XML-RPC"""
    try:
        client = xmlrpc.client.ServerProxy(
            f"{Config.UYUNI_URL}/rpc/api",
            context=_ssl_context(),
        )
        api_version = client.api.getVersion()
        return {
            "status": "connected",
            "url": Config.UYUNI_URL,
            "api_version": api_version,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)[:100],
            "url": Config.UYUNI_URL,
        }


def _check_prometheus() -> dict:
    """Verifica raggiungibilità Prometheus"""
    try:
        response = requests.get(
            f"{Config.PROMETHEUS_URL}/-/healthy",
            timeout=5,
        )
        if response.status_code == 200:
            return {"status": "connected", "url": Config.PROMETHEUS_URL}
        return {
            "status": "error",
            "message": f"HTTP {response.status_code}",
            "url": Config.PROMETHEUS_URL,
        }
    except requests.ConnectionError:
        return {
            "status": "unavailable",
            "message": "Not reachable (not critical for basic operation)",
            "url": Config.PROMETHEUS_URL,
        }
    except requests.Timeout:
        return {
            "status": "error",
            "message": "Timeout",
            "url": Config.PROMETHEUS_URL,
        }


def _ssl_context():
    """SSL context per UYUNI (gestisce verify_ssl=false)"""
    import ssl
    if not Config.UYUNI_VERIFY_SSL:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None
