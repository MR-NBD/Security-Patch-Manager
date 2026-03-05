"""
SPM Orchestrator - Groups API

Endpoint per la vista dei gruppi UYUNI e delle patch applicabili.

GET /api/v1/groups
    Lista dei gruppi di test UYUNI con conteggio sistemi e patch.

GET /api/v1/groups/<group_name>/patches
    Patch applicabili a tutti i sistemi nel gruppo (merge + dedup).
"""

import logging
from flask import Blueprint, jsonify, request

from app.services.uyuni_client import UyuniSession, os_from_group
from app.services.db import get_db

# Pattern identici a queue_manager — usati per inferire requires_reboot
# quando il patch_risk_profile non esiste ancora (patch mai accodata)
_KERNEL_PATTERNS = ["kernel", "linux-image", "linux-headers", "linux-modules",
                    "linux-generic", "linux-kvm"]
_REBOOT_PATTERNS  = _KERNEL_PATTERNS + [
    "glibc", "libc6", "libc-bin", "systemd", "udev", "dbus",
    "openssh-server", "openssh-client", "initramfs-tools", "grub",
]

logger = logging.getLogger(__name__)

groups_bp = Blueprint("groups", __name__, url_prefix="/api/v1/groups")


def _uyuni_session_from_request() -> UyuniSession:
    """
    Crea UyuniSession con le credenziali dell'operatore se presenti negli header
    (X-UYUNI-Username / X-UYUNI-Password), altrimenti usa le credenziali admin
    da Config (fallback per compatibilità).
    """
    username = request.headers.get("X-UYUNI-Username")
    password = request.headers.get("X-UYUNI-Password")
    return UyuniSession(username=username or None, password=password or None)


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
        with _uyuni_session_from_request() as session:
            org = session.get_current_org()
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

        return jsonify({"org": org, "groups": result})

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
        with _uyuni_session_from_request() as session:
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
                            "synopsis":       e.get("advisory_synopsis") or e.get("synopsis", ""),
                            "date":           str(e.get("date", "") or ""),
                            "systems_affected": [],
                        }
                    patches_by_name[name]["systems_affected"].append(sid)

            # Arricchisce patches con requires_reboot / affects_kernel dal DB.
            # Fonte preferita: patch_risk_profile (se patch gia' accodata in passato).
            # Fallback: inferenza dai package names in errata_cache.packages.
            # Se nessuna info disponibile: None (mostrato come "sconosciuto").
            if patches_by_name:
                try:
                    advisory_names = list(patches_by_name.keys())
                    with get_db() as conn:
                        cur = conn.cursor()
                        cur.execute("""
                            SELECT
                                ec.errata_id,
                                rp.requires_reboot,
                                rp.affects_kernel,
                                ec.packages
                            FROM errata_cache ec
                            LEFT JOIN patch_risk_profile rp
                                   ON ec.errata_id = rp.errata_id
                            WHERE ec.errata_id = ANY(%s)
                        """, (advisory_names,))
                        for row in cur.fetchall():
                            name = row["errata_id"]
                            if name not in patches_by_name:
                                continue
                            requires_reboot = row["requires_reboot"]
                            affects_kernel  = row["affects_kernel"]
                            # Inferenza dai package se risk profile assente
                            if requires_reboot is None:
                                pkgs = row["packages"]
                                if isinstance(pkgs, list) and pkgs:
                                    n_lower = [p.get("name", "").lower() for p in pkgs]
                                    affects_kernel  = any(
                                        any(pat in n for pat in _KERNEL_PATTERNS)
                                        for n in n_lower
                                    )
                                    requires_reboot = any(
                                        any(pat in n for pat in _REBOOT_PATTERNS)
                                        for n in n_lower
                                    )
                            patches_by_name[name]["requires_reboot"] = requires_reboot
                            patches_by_name[name]["affects_kernel"]  = affects_kernel
                except Exception as e:
                    logger.warning(f"group_patches: DB enrich failed: {e}")

            # Ordinamento: no-reboot/sconosciuto prima, poi reboot; a pari categoria
            # le patch piu' recenti vengono prima.
            patches = sorted(
                patches_by_name.values(),
                key=lambda p: (
                    bool(p.get("requires_reboot")),  # False/None < True
                    p.get("date") or "",
                ),
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
