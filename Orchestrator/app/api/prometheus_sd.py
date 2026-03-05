"""
SPM Orchestrator - Prometheus HTTP Service Discovery

Endpoint GET /api/v1/prometheus/targets

Restituisce i sistemi nei gruppi UYUNI test-* nel formato
Prometheus HTTP Service Discovery:
  [
    {
      "targets": ["10.172.2.18:9100"],
      "labels": {"group": "test-ubuntu-2404", "os": "ubuntu"}
    },
    ...
  ]

Prometheus è configurato con http_sd_configs che punta a questo
endpoint e aggiorna i target automaticamente a ogni refresh.
Nessuna configurazione manuale dei target necessaria.
"""

import logging

from flask import Blueprint, jsonify

from app.services.uyuni_client import UyuniSession, os_from_group
from app.services.uyuni_patch_client import is_ip

logger = logging.getLogger(__name__)

prometheus_sd_bp = Blueprint("prometheus_sd", __name__)

_NODE_EXPORTER_PORT = 9100


@prometheus_sd_bp.route("/api/v1/prometheus/targets", methods=["GET"])
def prometheus_targets():
    """
    Prometheus HTTP Service Discovery endpoint.

    Interroga UYUNI per tutti i gruppi test-* e restituisce
    i sistemi con il loro IP nel formato HTTP SD di Prometheus.
    I sistemi senza IP noto vengono esclusi (node_exporter non raggiungibile).
    """
    sd_targets = []

    try:
        with UyuniSession() as session:
            groups = session.get_test_groups()
            for group in groups:
                group_name = group.get("name", "")
                target_os = os_from_group(group_name)
                systems = session.get_systems_in_group(group_name)

                for s in systems:
                    system_id = s.get("id")
                    system_name = (
                        s.get("name")
                        or s.get("profile_name")
                        or s.get("hostname")
                        or ""
                    )

                    # Risolvi IP: nome se è già un IP, altrimenti system.getNetwork
                    if is_ip(system_name):
                        system_ip = system_name
                    else:
                        system_ip = session.get_system_network_ip(system_id) or ""

                    if not system_ip:
                        logger.warning(
                            f"prometheus_sd: no IP for system {system_name!r} "
                            f"(id={system_id}) in group {group_name!r} — skipped"
                        )
                        continue

                    sd_targets.append({
                        "targets": [f"{system_ip}:{_NODE_EXPORTER_PORT}"],
                        "labels": {
                            "group": group_name,
                            "os":    target_os or "unknown",
                            "name":  system_name,
                        },
                    })

        logger.info(f"prometheus_sd: returning {len(sd_targets)} targets")

    except Exception as e:
        logger.error(f"prometheus_sd: UYUNI error — {e}")
        # Restituisce lista vuota (non errore HTTP) per non bloccare Prometheus
        return jsonify([])

    return jsonify(sd_targets)
