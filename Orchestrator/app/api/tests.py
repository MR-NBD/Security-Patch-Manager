"""
SPM Orchestrator - Tests API

Endpoint per il Test Engine:
  GET  /api/v1/tests/status      → stato corrente engine + ultimo risultato
  POST /api/v1/tests/run         → trigger manuale test (bloccante)
  GET  /api/v1/tests/<id>        → dettaglio test con fasi
"""

import json
import logging
from datetime import datetime, date
from decimal import Decimal

from flask import Blueprint, jsonify

from app.services.db import get_db
from app.services.test_engine import run_next_test, get_engine_status

logger = logging.getLogger(__name__)

tests_bp = Blueprint("tests", __name__, url_prefix="/api/v1/tests")


def _serialize(obj):
    """Serializzazione JSON per tipi PostgreSQL."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return obj


def _serialize_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


# ─────────────────────────────────────────────
# GET /api/v1/tests/status
# ─────────────────────────────────────────────

@tests_bp.route("/status", methods=["GET"])
def engine_status():
    """Stato corrente del Test Engine e statistiche ultime 24h."""
    status = get_engine_status()

    # Statistiche rapide DB
    stats = {}
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE result = 'passed')  AS passed_24h,
                    COUNT(*) FILTER (WHERE result = 'failed')  AS failed_24h,
                    COUNT(*) FILTER (WHERE result = 'error')   AS error_24h,
                    ROUND(AVG(duration_seconds))               AS avg_duration_s
                FROM patch_tests
                WHERE started_at > NOW() - INTERVAL '24 hours'
            """)
            row = cur.fetchone()
            if row:
                stats = dict(row)
    except Exception as e:
        logger.warning(f"Tests status DB query failed: {e}")

    return jsonify({
        "engine_running": status["testing"],
        "last_result":    status["last_result"],
        "stats_24h":      stats,
    })


# ─────────────────────────────────────────────
# POST /api/v1/tests/run
# ─────────────────────────────────────────────

@tests_bp.route("/run", methods=["POST"])
def trigger_test():
    """
    Trigger manuale del Test Engine.
    Bloccante: ritorna quando il test è completato (o skipped se coda vuota).
    """
    logger.info("Manual test run triggered via API")
    result = run_next_test()
    status_code = 200

    if result.get("status") == "error":
        status_code = 500
    elif result.get("status") == "skipped":
        status_code = 202  # Accepted — nessun lavoro da fare

    return jsonify(result), status_code


# ─────────────────────────────────────────────
# GET /api/v1/tests/<int:test_id>
# ─────────────────────────────────────────────

@tests_bp.route("/<int:test_id>", methods=["GET"])
def get_test(test_id: int):
    """Dettaglio completo di un test con tutte le fasi."""
    try:
        with get_db() as conn:
            cur = conn.cursor()

            # Test record
            cur.execute("""
                SELECT
                    t.*,
                    q.priority_override,
                    q.created_by,
                    e.synopsis,
                    e.severity,
                    e.type AS errata_type
                FROM patch_tests t
                LEFT JOIN patch_test_queue q ON t.queue_id = q.id
                LEFT JOIN errata_cache e     ON t.errata_id = e.errata_id
                WHERE t.id = %s
            """, (test_id,))
            row = cur.fetchone()

            if not row:
                return jsonify({"error": f"Test {test_id} not found"}), 404

            test = _serialize_row(dict(row))

            # Fasi
            cur.execute("""
                SELECT id, phase_name, status,
                       started_at, completed_at, duration_seconds,
                       error_message, output
                FROM patch_test_phases
                WHERE test_id = %s
                ORDER BY started_at ASC
            """, (test_id,))
            test["phases"] = [_serialize_row(dict(p)) for p in cur.fetchall()]

        return jsonify(test)

    except Exception as e:
        logger.error(f"GET /tests/{test_id} failed: {e}")
        return jsonify({"error": "Internal server error"}), 500
