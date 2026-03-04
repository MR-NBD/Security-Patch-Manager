"""
SPM Orchestrator - Groups API

Endpoint per la vista dei gruppi UYUNI e delle patch applicabili.

GET /api/v1/groups
    Lista dei gruppi di test UYUNI con conteggio sistemi e patch.

GET /api/v1/groups/<group_name>/patches
    Patch applicabili a tutti i sistemi nel gruppo (merge + dedup).
"""

import logging
from flask import Blueprint, jsonify

from app.services.uyuni_client import UyuniSession, os_from_group

logger = logging.getLogger(__name__)

groups_bp = Blueprint("groups", __name__, url_prefix="/api/v1/groups")


# ─────────────────────────────────────────────
# GET /api/v1/groups
# ─────────────────────────────────────────────

@groups_bp.route("", methods=["GET"])
def list_groups():
    """
    Lista gruppi test UYUNI con sistemi e conteggio patch applicabili.

    Risposta:
    {
      "groups": [
        {
          "name": "test-ubuntu-2404",
          "os": "ubuntu",
          "systems": [{"id": 1000010000, "name": "10.172.2.18"}],
          "system_count": 1,
          "patch_count": 15     # patch uniche applicabili al gruppo
        }
      ]
    }
    """
    try:
        with UyuniSession() as session:
            groups = session.get_test_groups()
            result = []
            for group in groups:
                group_name = group.get("name", "")
                systems = session.get_systems_in_group(group_name)

                # Raccoglie errata uniche per tutti i sistemi del gruppo
                seen_errata = set()
                for sys in systems:
                    sid = sys.get("id")
                    if not sid:
                        continue
                    errata = session.get_relevant_errata(sid)
                    for e in errata:
                        name = e.get("advisory_name") or e.get("errata_id", "")
                        seen_errata.add(name)

                result.append({
                    "name":         group_name,
                    "os":           os_from_group(group_name),
                    "systems": [
                        {
                            "id":   s.get("id"),
                            "name": (
                                s.get("name")
                                or s.get("profile_name")
                                or s.get("hostname")
                                or str(s.get("id"))
                            ),
                        }
                        for s in systems
                    ],
                    "system_count": len(systems),
                    "patch_count":  len(seen_errata),
                })

        return jsonify({"groups": result})

    except Exception as e:
        logger.error(f"GET /groups failed: {e}")
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# GET /api/v1/groups/<group_name>/patches
# ─────────────────────────────────────────────

@groups_bp.route("/<path:group_name>/patches", methods=["GET"])
def group_patches(group_name: str):
    """
    Patch applicabili a tutti i sistemi nel gruppo (union, dedup per advisory_name).

    Risposta:
    {
      "group": "test-ubuntu-2404",
      "os": "ubuntu",
      "patch_count": 15,
      "patches": [
        {
          "advisory_name": "USN-7412-2",
          "advisory_type": "Security Advisory",
          "synopsis": "openssl vulnerabilities",
          "date": "2024-01-15",
          "systems_affected": [1000010000]
        }
      ]
    }
    """
    try:
        with UyuniSession() as session:
            # Verifica che il gruppo esista
            all_groups = session.get_test_groups()
            matching = [g for g in all_groups if g.get("name") == group_name]
            if not matching:
                return jsonify({"error": f"Group {group_name!r} not found"}), 404

            systems = session.get_systems_in_group(group_name)

            # Merge patch per tutti i sistemi
            patches_by_name: dict = {}
            for sys in systems:
                sid = sys.get("id")
                if not sid:
                    continue
                errata = session.get_relevant_errata(sid)
                for e in errata:
                    name = e.get("advisory_name") or ""
                    if not name:
                        continue
                    if name not in patches_by_name:
                        patches_by_name[name] = {
                            "advisory_name":  name,
                            "advisory_type":  e.get("advisory_type", ""),
                            "synopsis":       e.get("synopsis", ""),
                            "date":           str(e.get("date", "") or ""),
                            "systems_affected": [],
                        }
                    patches_by_name[name]["systems_affected"].append(sid)

            patches = sorted(
                patches_by_name.values(),
                key=lambda p: p["date"],
                reverse=True,
            )

        return jsonify({
            "group":       group_name,
            "os":          os_from_group(group_name),
            "patch_count": len(patches),
            "patches":     patches,
        })

    except Exception as e:
        logger.error(f"GET /groups/{group_name}/patches failed: {e}")
        return jsonify({"error": str(e)}), 500
