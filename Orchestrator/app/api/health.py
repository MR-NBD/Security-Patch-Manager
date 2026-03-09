"""
SPM Orchestrator - Health Endpoints

GET /api/v1/health         → stato base (risposta rapida)
GET /api/v1/health/detail  → stato dettagliato con check componenti
"""

import logging
import time
import requests
from flask import Blueprint, jsonify, request
import xmlrpc.client

from app.config import Config
from app.services.db import check_db_health, get_db
from app.services.uyuni_client import make_uyuni_transport
from app.utils.serializers import serialize_row

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

def _check_uyuni() -> dict:
    """Verifica raggiungibilità UYUNI XML-RPC (con timeout da Config.UYUNI_TIMEOUT)."""
    try:
        client = xmlrpc.client.ServerProxy(
            f"{Config.UYUNI_URL}/rpc/api",
            transport=make_uyuni_transport(),
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


# ----------------------------------------------------------
# Notifiche non lette
# ----------------------------------------------------------

@health_bp.route("/api/v1/notifications", methods=["GET"])
def notifications():
    """
    GET /api/v1/notifications

    Ritorna le notifiche non lette (delivered=False) da orchestrator_notifications.
    La dashboard le mostra come banner di attenzione.

    Query params:
      limit  (default 20)
      mark_read  (default false) — se true marca le notifiche come delivered=True
    """
    try:
        limit     = min(int(request.args.get("limit", 20)), 100)
        mark_read = request.args.get("mark_read", "false").lower() == "true"
    except ValueError:
        return jsonify({"error": "Invalid query params"}), 400

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, notification_type, errata_id, queue_id, test_id,
                       channel, recipient, subject, body,
                       delivered, error_message, sent_at
                FROM orchestrator_notifications
                WHERE delivered = FALSE
                ORDER BY sent_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = [serialize_row(dict(row)) for row in cur.fetchall()]

            total_unread = 0
            cur.execute(
                "SELECT COUNT(*) AS n FROM orchestrator_notifications WHERE delivered = FALSE"
            )
            total_unread = cur.fetchone()["n"]

            if mark_read and rows:
                ids = [r["id"] for r in rows]
                cur.execute(
                    "UPDATE orchestrator_notifications SET delivered = TRUE WHERE id = ANY(%s)",
                    (ids,),
                )

        return jsonify({"total_unread": total_unread, "items": rows})

    except Exception as e:
        logger.error(f"GET /notifications failed: {e}")
        return jsonify({"error": str(e)}), 500


@health_bp.route("/api/v1/notifications/mark-read", methods=["POST"])
def mark_notifications_read():
    """
    POST /api/v1/notifications/mark-read

    Body: { "ids": [1, 2, 3] }  oppure {}  per marcare tutte come lette.
    """
    body = request.get_json(silent=True) or {}
    ids  = body.get("ids")

    # Validazione: ids deve essere una lista di interi
    if ids is not None:
        if not isinstance(ids, list) or not all(isinstance(i, int) and i > 0 for i in ids):
            return jsonify({"error": "ids must be a list of positive integers"}), 400
        if len(ids) > 1000:
            return jsonify({"error": "ids list exceeds maximum length (1000)"}), 400

    try:
        with get_db() as conn:
            cur = conn.cursor()
            if ids:
                cur.execute(
                    "UPDATE orchestrator_notifications SET delivered = TRUE WHERE id = ANY(%s)",
                    (ids,),
                )
            else:
                cur.execute(
                    "UPDATE orchestrator_notifications SET delivered = TRUE WHERE delivered = FALSE"
                )
            updated = cur.rowcount
        return jsonify({"marked_read": updated})
    except Exception as e:
        logger.error(f"POST /notifications/mark-read failed: {e}")
        return jsonify({"error": str(e)}), 500
