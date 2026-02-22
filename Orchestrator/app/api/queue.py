"""
SPM Orchestrator - Queue Management API

Endpoints per gestire la coda di test patch.

GET  /api/v1/queue              - lista coda (con filtri)
POST /api/v1/queue              - aggiungi errata
GET  /api/v1/queue/stats        - statistiche aggregate
GET  /api/v1/queue/<id>         - dettaglio elemento
PATCH /api/v1/queue/<id>        - aggiorna priorità/note
DELETE /api/v1/queue/<id>       - rimuovi dalla coda
"""

from flask import Blueprint, jsonify, request
from app.services import queue_manager as qm

queue_bp = Blueprint("queue", __name__, url_prefix="/api/v1")

_VALID_OS = {"ubuntu", "rhel"}
_VALID_STATUSES = {
    "queued", "testing", "passed", "failed", "needs_reboot", "rebooting",
    "pending_approval", "approved", "rejected", "snoozed",
    "promoting", "prod_pending", "prod_applied", "completed", "rolled_back",
}


@queue_bp.route("/queue", methods=["GET"])
def list_queue():
    """
    GET /api/v1/queue

    Query params:
      status    - filtra per stato (queued, testing, passed, ...)
      target_os - ubuntu / rhel
      severity  - Critical / High / Medium / Low
      limit     - default 50, max 200
      offset    - default 0
    """
    status = request.args.get("status")
    target_os = request.args.get("target_os")
    severity = request.args.get("severity")

    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "limit and offset must be integers"}), 400

    if status and status not in _VALID_STATUSES:
        return jsonify({"error": f"Invalid status: {status}"}), 400
    if target_os and target_os not in _VALID_OS:
        return jsonify({"error": f"Invalid target_os: {target_os}"}), 400

    try:
        result = qm.get_queue(
            status=status,
            target_os=target_os,
            severity=severity,
            limit=limit,
            offset=offset,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@queue_bp.route("/queue", methods=["POST"])
def add_to_queue():
    """
    POST /api/v1/queue

    Body JSON:
      errata_id         string   oppure errata_ids: [str, ...]
      target_os         string   required: ubuntu / rhel
      priority_override int      optional, default 0
      created_by        string   optional
      notes             string   optional

    Returns 201 se tutti aggiunti, 207 se parzialmente riuscito.
    """
    data = request.get_json(silent=True) or {}

    target_os = data.get("target_os", "").lower()
    if target_os not in _VALID_OS:
        return jsonify({
            "error": "target_os is required and must be 'ubuntu' or 'rhel'"
        }), 400

    errata_ids = data.get("errata_ids") or (
        [data["errata_id"]] if data.get("errata_id") else []
    )
    if not errata_ids:
        return jsonify({
            "error": "errata_id or errata_ids is required"
        }), 400

    try:
        priority_override = int(data.get("priority_override", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "priority_override must be an integer"}), 400

    created_by = data.get("created_by")
    notes = data.get("notes")

    queued = []
    errors = []

    for errata_id in errata_ids:
        try:
            row = qm.add_to_queue(
                errata_id=errata_id,
                target_os=target_os,
                priority_override=priority_override,
                created_by=created_by,
                notes=notes,
            )
            queued.append(row)
        except ValueError as e:
            errors.append({"errata_id": errata_id, "error": str(e)})
        except Exception as e:
            errors.append({
                "errata_id": errata_id,
                "error": f"Internal error: {e}",
            })

    if not queued and errors:
        return jsonify({"queued": [], "errors": errors}), 422

    status_code = 201 if not errors else 207
    return jsonify({"queued": queued, "errors": errors}), status_code


@queue_bp.route("/queue/stats", methods=["GET"])
def queue_stats():
    """
    GET /api/v1/queue/stats

    Statistiche aggregate della coda (escluse righe terminal).
    """
    try:
        return jsonify(qm.get_queue_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@queue_bp.route("/queue/<int:queue_id>", methods=["GET"])
def get_queue_item(queue_id):
    """
    GET /api/v1/queue/<id>

    Dettaglio completo: errata info, risk profile, ultimo test.
    """
    try:
        item = qm.get_queue_item(queue_id)
        if item is None:
            return jsonify({"error": "Queue item not found"}), 404
        return jsonify(item)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@queue_bp.route("/queue/<int:queue_id>", methods=["PATCH"])
def update_queue_item(queue_id):
    """
    PATCH /api/v1/queue/<id>

    Body JSON (almeno uno richiesto):
      priority_override  int
      notes              string
    """
    data = request.get_json(silent=True) or {}

    priority_override = data.get("priority_override")
    notes = data.get("notes")

    if priority_override is None and notes is None:
        return jsonify({
            "error": "At least one of priority_override or notes is required"
        }), 400

    if priority_override is not None:
        try:
            priority_override = int(priority_override)
        except (ValueError, TypeError):
            return jsonify({"error": "priority_override must be an integer"}), 400

    try:
        item = qm.update_queue_item(
            queue_id=queue_id,
            priority_override=priority_override,
            notes=notes,
        )
        if item is None:
            return jsonify({"error": "Queue item not found"}), 404
        return jsonify(item)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@queue_bp.route("/queue/<int:queue_id>", methods=["DELETE"])
def remove_from_queue(queue_id):
    """
    DELETE /api/v1/queue/<id>

    Rimuove dalla coda solo se status = 'queued'.
    Elementi in testing o oltre non possono essere rimossi.
    """
    try:
        removed = qm.remove_from_queue(queue_id)
        if not removed:
            return jsonify({
                "error": (
                    "Queue item not found or cannot be removed. "
                    "Only items with status 'queued' can be deleted."
                )
            }), 404
        return jsonify({"status": "removed", "queue_id": queue_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
