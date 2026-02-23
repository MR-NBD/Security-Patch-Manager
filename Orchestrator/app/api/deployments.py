"""
SPM Orchestrator - Deployments API

Endpoint per il deployment in produzione delle patch approvate:

  POST /api/v1/deployments                  → crea + esegui deployment
  GET  /api/v1/deployments                  → lista deployments
  GET  /api/v1/deployments/<id>             → dettaglio deployment
  POST /api/v1/deployments/<id>/rollback    → rollback deployment

Body POST /api/v1/deployments:
  {
    "queue_id":       123,
    "target_systems": [{"name": "prod-ubuntu-01"}, {"name": "prod-ubuntu-02"}],
    "created_by":     "operator",
    "notes":          "testo opzionale"
  }

Body POST /api/v1/deployments/<id>/rollback:
  {
    "initiated_by": "operator",
    "reason":       "motivazione obbligatoria"
  }
"""

import logging

from flask import Blueprint, jsonify, request

from app.services import deployment_manager

logger = logging.getLogger(__name__)

deployments_bp = Blueprint("deployments", __name__, url_prefix="/api/v1/deployments")


# ─────────────────────────────────────────────
# POST /api/v1/deployments
# ─────────────────────────────────────────────

@deployments_bp.route("", methods=["POST"])
def create_deployment():
    """
    Crea ed esegue immediatamente un deployment di produzione.
    Bloccante: ritorna quando il deployment è completato su tutti i sistemi.

    La patch deve essere in status='approved'.
    """
    body = request.get_json(silent=True) or {}

    queue_id       = body.get("queue_id")
    target_systems = body.get("target_systems", [])
    created_by     = (body.get("created_by") or "").strip()
    notes          = body.get("notes")

    # Validazione input
    if not queue_id:
        return jsonify({"error": "'queue_id' is required"}), 400
    if not isinstance(queue_id, int):
        return jsonify({"error": "'queue_id' must be an integer"}), 400
    if not target_systems:
        return jsonify({"error": "'target_systems' must not be empty"}), 400
    if not isinstance(target_systems, list):
        return jsonify({"error": "'target_systems' must be a list"}), 400
    if not created_by:
        return jsonify({"error": "'created_by' is required"}), 400

    # Verifica che ogni sistema abbia almeno 'name'
    for i, sys in enumerate(target_systems):
        if not isinstance(sys, dict) or not sys.get("name"):
            return jsonify({
                "error": f"target_systems[{i}] must have a 'name' (Salt minion ID)"
            }), 400

    try:
        result = deployment_manager.create_and_execute(
            queue_id       = queue_id,
            target_systems = target_systems,
            created_by     = created_by,
            notes          = notes,
        )
        # 200 se completato, 207 se parziale
        status_code = 200 if result["systems_failed"] == 0 else 207
        return jsonify(result), status_code

    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        logger.error(f"POST /deployments failed: {e}")
        return jsonify({"error": "Deployment failed", "detail": str(e)}), 500


# ─────────────────────────────────────────────
# GET /api/v1/deployments
# ─────────────────────────────────────────────

@deployments_bp.route("", methods=["GET"])
def list_deployments():
    """Lista deployments con filtro opzionale su status e paginazione."""
    status = request.args.get("status")
    try:
        limit  = min(int(request.args.get("limit",  50)), 200)
        offset = max(int(request.args.get("offset",  0)),   0)
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    result = deployment_manager.list_deployments(
        status=status, limit=limit, offset=offset,
    )
    return jsonify(result)


# ─────────────────────────────────────────────
# GET /api/v1/deployments/<id>
# ─────────────────────────────────────────────

@deployments_bp.route("/<int:deployment_id>", methods=["GET"])
def get_deployment(deployment_id: int):
    """Dettaglio completo deployment con system_results e info rollback."""
    dep = deployment_manager.get_deployment(deployment_id)
    if not dep:
        return jsonify({"error": f"Deployment {deployment_id} not found"}), 404
    return jsonify(dep)


# ─────────────────────────────────────────────
# POST /api/v1/deployments/<id>/rollback
# ─────────────────────────────────────────────

@deployments_bp.route("/<int:deployment_id>/rollback", methods=["POST"])
def rollback_deployment(deployment_id: int):
    """
    Esegue rollback package-based su tutti i sistemi del deployment.
    Solo per deployment in status 'completed' o 'partial_failure'.

    Body: { "initiated_by": "operator", "reason": "motivazione" }
    """
    body = request.get_json(silent=True) or {}

    initiated_by = (body.get("initiated_by") or "").strip()
    reason       = (body.get("reason") or "").strip()

    if not initiated_by:
        return jsonify({"error": "'initiated_by' is required"}), 400
    if not reason:
        return jsonify({"error": "'reason' is required"}), 400

    try:
        result = deployment_manager.rollback_deployment(
            deployment_id = deployment_id,
            initiated_by  = initiated_by,
            reason        = reason,
        )
        status_code = 200 if result["systems_failed"] == 0 else 207
        return jsonify(result), status_code

    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        logger.error(f"POST /deployments/{deployment_id}/rollback failed: {e}")
        return jsonify({"error": "Rollback failed", "detail": str(e)}), 500
