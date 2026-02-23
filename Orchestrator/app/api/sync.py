"""
SPM Orchestrator - Sync API

Endpoints per monitorare e controllare il poller UYUNI.
"""

from flask import Blueprint, jsonify
from app.services import poller

sync_bp = Blueprint("sync", __name__, url_prefix="/api/v1")


@sync_bp.route("/sync/status")
def sync_status():
    """
    GET /api/v1/sync/status

    Ritorna stato corrente del poller UYUNI e statistiche
    dell'ultimo run.
    """
    return jsonify(poller.get_sync_status())


@sync_bp.route("/sync/trigger", methods=["POST"])
def sync_trigger():
    """
    POST /api/v1/sync/trigger

    Avvia manualmente un ciclo di sync UYUNI → errata_cache.
    Bloccante: ritorna quando il sync è completato.
    """
    result = poller.trigger_sync()
    code = 200 if result.get("status") == "success" else 500
    return jsonify(result), code


@sync_bp.route("/errata/cache/stats")
def errata_cache_stats():
    """
    GET /api/v1/errata/cache/stats

    Statistiche sulla tabella errata_cache locale.
    """
    from app.services.db import get_db
    import psycopg2

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    COUNT(*)                          AS total,
                    COUNT(*) FILTER (
                        WHERE severity = 'Critical'
                    )                                 AS critical,
                    COUNT(*) FILTER (
                        WHERE severity = 'High'
                    )                                 AS high,
                    COUNT(*) FILTER (
                        WHERE severity = 'Medium'
                    )                                 AS medium,
                    COUNT(*) FILTER (
                        WHERE target_os = 'ubuntu'
                    )                                 AS ubuntu,
                    COUNT(*) FILTER (
                        WHERE target_os = 'debian'
                    )                                 AS debian,
                    MAX(synced_at)                    AS last_synced,
                    MIN(issued_date)                  AS oldest_errata,
                    MAX(issued_date)                  AS newest_errata
                FROM errata_cache
            """)
            row = cur.fetchone()

        return jsonify({
            "total":         row["total"],
            "by_severity": {
                "critical": row["critical"],
                "high":     row["high"],
                "medium":   row["medium"],
            },
            "by_os": {
                "ubuntu": row["ubuntu"],
                "debian": row["debian"],
            },
            "last_synced":   (
                row["last_synced"].isoformat()
                if row["last_synced"] else None
            ),
            "oldest_errata": (
                row["oldest_errata"].isoformat()
                if row["oldest_errata"] else None
            ),
            "newest_errata": (
                row["newest_errata"].isoformat()
                if row["newest_errata"] else None
            ),
        })

    except psycopg2.ProgrammingError:
        return jsonify({
            "error": "errata_cache table not found"
        }), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
