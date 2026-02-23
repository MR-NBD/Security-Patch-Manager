"""
SPM Orchestrator - Approvals API

Endpoint per il workflow di approvazione patch:

  GET  /api/v1/approvals/pending          → lista patch in attesa
  GET  /api/v1/approvals/pending/<id>     → dettaglio + test results
  POST /api/v1/approvals/<id>/approve     → approva
  POST /api/v1/approvals/<id>/reject      → rifiuta
  POST /api/v1/approvals/<id>/snooze      → rimanda
  GET  /api/v1/approvals/history          → storico azioni

Body approve/reject:
  { "action_by": "operator_name", "reason": "testo opzionale" }

Body snooze:
  { "action_by": "operator_name", "reason": "testo", "snooze_until": "2026-03-01T08:00:00Z" }
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app.services import approval_manager

logger = logging.getLogger(__name__)

approvals_bp = Blueprint("approvals", __name__, url_prefix="/api/v1/approvals")


def _client_ip() -> str:
    """Estrae IP del client dalla request (considera X-Forwarded-For)."""
    return (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
        or "unknown"
    )


# ─────────────────────────────────────────────
# GET /api/v1/approvals/pending
# ─────────────────────────────────────────────

@approvals_bp.route("/pending", methods=["GET"])
def list_pending():
    """Lista patch in attesa di approvazione con paginazione."""
    try:
        limit  = min(int(request.args.get("limit",  50)), 200)
        offset = max(int(request.args.get("offset",  0)),   0)
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    result = approval_manager.get_pending(limit=limit, offset=offset)
    return jsonify(result)


# ─────────────────────────────────────────────
# GET /api/v1/approvals/pending/<id>
# ─────────────────────────────────────────────

@approvals_bp.route("/pending/<int:queue_id>", methods=["GET"])
def pending_detail(queue_id: int):
    """Dettaglio completo di una patch in pending_approval per la revisione."""
    item = approval_manager.get_pending_detail(queue_id)
    if not item:
        return jsonify({
            "error": f"Queue item {queue_id} not found or not in pending_approval"
        }), 404
    return jsonify(item)


# ─────────────────────────────────────────────
# POST /api/v1/approvals/<id>/approve
# ─────────────────────────────────────────────

@approvals_bp.route("/<int:queue_id>/approve", methods=["POST"])
def approve(queue_id: int):
    """
    Approva patch: status → 'approved'.
    Body: { "action_by": "nome", "reason": "opzionale" }
    """
    body = request.get_json(silent=True) or {}
    action_by = body.get("action_by", "").strip()

    if not action_by:
        return jsonify({"error": "'action_by' is required"}), 400

    try:
        result = approval_manager.approve(
            queue_id   = queue_id,
            action_by  = action_by,
            reason     = body.get("reason"),
            ip_address = _client_ip(),
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        logger.error(f"approve({queue_id}) failed: {e}")
        return jsonify({"error": "Internal server error"}), 500


# ─────────────────────────────────────────────
# POST /api/v1/approvals/<id>/reject
# ─────────────────────────────────────────────

@approvals_bp.route("/<int:queue_id>/reject", methods=["POST"])
def reject(queue_id: int):
    """
    Rifiuta patch: status → 'rejected'.
    Body: { "action_by": "nome", "reason": "motivazione consigliata" }
    """
    body = request.get_json(silent=True) or {}
    action_by = body.get("action_by", "").strip()

    if not action_by:
        return jsonify({"error": "'action_by' is required"}), 400

    try:
        result = approval_manager.reject(
            queue_id   = queue_id,
            action_by  = action_by,
            reason     = body.get("reason"),
            ip_address = _client_ip(),
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        logger.error(f"reject({queue_id}) failed: {e}")
        return jsonify({"error": "Internal server error"}), 500


# ─────────────────────────────────────────────
# POST /api/v1/approvals/<id>/snooze
# ─────────────────────────────────────────────

@approvals_bp.route("/<int:queue_id>/snooze", methods=["POST"])
def snooze(queue_id: int):
    """
    Rimanda patch: status → 'snoozed'. Torna a pending_approval allo scadere.
    Body: { "action_by": "nome", "snooze_until": "2026-03-01T08:00:00Z", "reason": "..." }
    """
    body = request.get_json(silent=True) or {}
    action_by    = body.get("action_by", "").strip()
    snooze_until = body.get("snooze_until", "").strip()

    if not action_by:
        return jsonify({"error": "'action_by' is required"}), 400
    if not snooze_until:
        return jsonify({"error": "'snooze_until' is required (ISO 8601)"}), 400

    try:
        snooze_dt = datetime.fromisoformat(
            snooze_until.replace("Z", "+00:00")
        )
        if snooze_dt.tzinfo is None:
            snooze_dt = snooze_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return jsonify({
            "error": f"Invalid snooze_until format: {snooze_until!r}. Use ISO 8601."
        }), 400

    try:
        result = approval_manager.snooze(
            queue_id    = queue_id,
            action_by   = action_by,
            snooze_until = snooze_dt,
            reason      = body.get("reason"),
            ip_address  = _client_ip(),
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        logger.error(f"snooze({queue_id}) failed: {e}")
        return jsonify({"error": "Internal server error"}), 500


# ─────────────────────────────────────────────
# GET /api/v1/approvals/history
# ─────────────────────────────────────────────

@approvals_bp.route("/history", methods=["GET"])
def history():
    """Storico completo delle azioni di approvazione (audit trail)."""
    try:
        limit  = min(int(request.args.get("limit",  50)), 200)
        offset = max(int(request.args.get("offset",  0)),   0)
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    result = approval_manager.get_history(limit=limit, offset=offset)
    return jsonify(result)
