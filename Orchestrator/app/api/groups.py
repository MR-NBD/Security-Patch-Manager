"""
SPM Orchestrator - Groups API

Endpoint per la vista dei gruppi UYUNI e delle patch applicabili.

GET /api/v1/orgs
    Lista organizzazioni UYUNI visibili all'account admin.

GET /api/v1/groups[?org_id=N]
    Lista dei gruppi di test UYUNI con conteggio sistemi e patch.
    Parametro opzionale org_id per filtrare per organizzazione.

GET /api/v1/groups/<group_name>/patches
    Patch applicabili a tutti i sistemi nel gruppo (merge + dedup).
"""

import logging
from flask import Blueprint, jsonify, request

from app.services.uyuni_client import UyuniSession, os_from_group
from app.services.db import get_db
from app.services.queue_manager import KERNEL_PATTERNS, REBOOT_PATTERNS

logger = logging.getLogger(__name__)

groups_bp = Blueprint("groups", __name__, url_prefix="/api/v1")


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
# GET /api/v1/orgs
# ─────────────────────────────────────────────

@groups_bp.route("/orgs", methods=["GET"])
def list_orgs():
    """
    Lista tutte le organizzazioni UYUNI visibili all'account admin.
    Ritorna [{org_id, org_name}, ...].
    """
    try:
        with _uyuni_session_from_request() as session:
            orgs = session.list_orgs()
        return jsonify({"orgs": orgs})
    except Exception as e:
        logger.error(f"GET /orgs failed: {e}")
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# GET /api/v1/groups
# ─────────────────────────────────────────────

@groups_bp.route("/groups", methods=["GET"])
def list_groups():
    """
    Lista gruppi test UYUNI con sistemi e conteggio patch applicabili.
    Parametro opzionale: org_id (int) — filtra per organizzazione.

    Risposta:
    {
      "org": {"org_id": 1, "org_name": "ASL06"},
      "groups": [
        {
          "name": "test-ubuntu-2404",
          "org_id": 1,
          "os": "ubuntu",
          "systems": [{"id": 1000010000, "name": "10.172.2.18"}],
          "system_count": 1,
          "patch_count": 15
        }
      ]
    }
    """
    # Filtro org opzionale
    org_id_filter = None
    raw = request.args.get("org_id")
    if raw:
        try:
            org_id_filter = int(raw)
        except ValueError:
            return jsonify({"error": "org_id must be an integer"}), 400

    try:
        with _uyuni_session_from_request() as session:
            org = session.get_current_org()
            groups = session.get_test_groups()
            result = []
            for group in groups:
                # Filtra per org_id se specificato
                group_org_id = group.get("org_id")
                if org_id_filter is not None and group_org_id != org_id_filter:
                    continue
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
                    "org_id":       group_org_id,
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
# DB helper: reboot enrichment
# ─────────────────────────────────────────────

def _enrich_reboot_info(patches_by_name: dict) -> None:
    """
    Arricchisce in-place le patch con requires_reboot / affects_kernel dal DB.
    Fonte preferita: patch_risk_profile (se patch gia' accodata in passato).
    Fallback: inferenza dai package names in errata_cache.packages.
    Se nessuna info disponibile: campo assente (UI mostra "sconosciuto").
    """
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
                LEFT JOIN patch_risk_profile rp ON ec.errata_id = rp.errata_id
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
                        affects_kernel  = any(any(pat in n for pat in KERNEL_PATTERNS) for n in n_lower)
                        requires_reboot = any(any(pat in n for pat in REBOOT_PATTERNS) for n in n_lower)
                patches_by_name[name]["requires_reboot"] = requires_reboot
                patches_by_name[name]["affects_kernel"]  = affects_kernel
    except Exception as e:
        logger.warning(f"_enrich_reboot_info: DB query failed: {e}")


# ─────────────────────────────────────────────
# GET /api/v1/groups/<group_name>/patches
# ─────────────────────────────────────────────

@groups_bp.route("/groups/<path:group_name>/patches", methods=["GET"])
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

            if patches_by_name:
                _enrich_reboot_info(patches_by_name)

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
