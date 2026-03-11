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
    Ogni patch include:
      requires_reboot  bool|None  — da patch_risk_profile o inferenza package names
      affects_kernel   bool|None  — da patch_risk_profile
      is_latest        bool       — True se è la versione più recente nella sua famiglia
      superseded_by    str|None   — advisory_name della patch più recente (se is_latest=False)
    Ordinamento: latest first → no-reboot first → data discendente.
"""

import logging
import re
from flask import Blueprint, jsonify, request

from app.services.uyuni_client import UyuniSession, os_from_group
from app.services.db import get_db
from app.services.queue_manager import KERNEL_PATTERNS, REBOOT_PATTERNS, extract_advisory_base

logger = logging.getLogger(__name__)

groups_bp = Blueprint("groups", __name__, url_prefix="/api/v1")


def _uyuni_session_from_request() -> UyuniSession:
    """Crea UyuniSession con le credenziali admin da Config."""
    return UyuniSession()


def _normalize_advisory_name(name: str) -> str:
    """
    Normalizza il nome advisory restituito da UYUNI.
    UYUNI a volte omette il prefisso 'USN-' per gli advisory Ubuntu:
    '7955-1' → 'USN-7955-1'
    """
    if re.match(r'^\d+-\d+$', name):
        return "USN-" + name
    return name


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
                        name = _normalize_advisory_name(
                            e.get("advisory_name") or e.get("errata_id", "")
                        )
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
# DB helper: latest info enrichment
# ─────────────────────────────────────────────

def _enrich_latest_info(patches_by_name: dict) -> None:
    """
    Arricchisce in-place le patch con is_latest e superseded_by.

    Due criteri per identificare le patch più recenti:
      1. Famiglia USN (USN-XXXX-N): la revisione più alta è latest, le altre no.
      2. Package overlap: tra patch attive che condividono pacchetti, la più recente
         per issued_date è latest (le altre hanno superseded_by impostato).

    Questi campi sono informativi: l'operatore vede le patch recenti in evidenza
    e può scegliere di partire da quelle. Le più vecchie vengono soppresse
    automaticamente al momento dell'aggiunta in coda.
    """
    # Inizializza tutte come latest (default ottimistico)
    for p in patches_by_name.values():
        p["is_latest"] = True
        p["superseded_by"] = None

    # ── 1. Raggruppamento per famiglia USN ───────────────────────────────────
    families: dict = {}  # advisory_base → [(revision_int, advisory_name), ...]
    for name in patches_by_name:
        base = extract_advisory_base(name)
        if base:
            try:
                rev = int(name.rsplit("-", 1)[-1])
            except (ValueError, IndexError):
                rev = 0
            families.setdefault(base, []).append((rev, name))

    for base, members in families.items():
        if len(members) < 2:
            continue
        _, max_name = max(members, key=lambda x: x[0])
        for _, name in members:
            if name != max_name:
                patches_by_name[name]["is_latest"] = False
                patches_by_name[name]["superseded_by"] = max_name

    # ── 2. Package overlap tra patch non ancora marcate come superate ─────────
    active_names = [
        name for name, p in patches_by_name.items()
        if p.get("is_latest") is True
    ]
    if len(active_names) < 2:
        return

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT errata_id, packages, issued_date"
                " FROM errata_cache WHERE errata_id = ANY(%s)",
                (active_names,),
            )
            pkg_data = {row["errata_id"]: row for row in cur.fetchall()}
    except Exception as e:
        logger.warning(f"_enrich_latest_info: DB query failed: {e}")
        return

    # Mappa pkg_name → [advisory_name] per trovare patch che condividono pacchetti
    pkg_to_advisories: dict = {}
    for name, row in pkg_data.items():
        pkgs = row.get("packages") or []
        if isinstance(pkgs, list):
            for p in pkgs:
                pkg_name = (p.get("name") or "").lower()
                if pkg_name:
                    pkg_to_advisories.setdefault(pkg_name, []).append(name)

    processed_pairs: set = set()
    for pkg_name, advisories in pkg_to_advisories.items():
        if len(advisories) < 2:
            continue
        # Trova la più recente tra quelle che condividono questo pacchetto
        dated = []
        for adv_name in advisories:
            date_str = str(pkg_data.get(adv_name, {}).get("issued_date") or "")
            dated.append((date_str, adv_name))
        dated.sort(reverse=True)  # più recente prima
        newest_date, newest_name = dated[0]

        for date_str, adv_name in dated[1:]:
            if adv_name == newest_name:
                continue
            pair = frozenset([adv_name, newest_name])
            if pair in processed_pairs:
                continue
            # Sopprimi solo se la data è effettivamente precedente
            if date_str < newest_date:
                processed_pairs.add(pair)
                patches_by_name[adv_name]["is_latest"] = False
                if not patches_by_name[adv_name].get("superseded_by"):
                    patches_by_name[adv_name]["superseded_by"] = newest_name


# ─────────────────────────────────────────────
# DB helper: severity enrichment
# ─────────────────────────────────────────────

def _enrich_severity_info(patches_by_name: dict) -> None:
    """
    Arricchisce in-place le patch con il campo 'severity' da errata_cache.
    Il valore è quello NVD-enriched scritto dal poller (Critical/High/Medium/Low).
    Se la patch non è in cache, il campo rimane None (non ancora sincronizzata).
    """
    try:
        advisory_names = list(patches_by_name.keys())
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT errata_id, severity FROM errata_cache WHERE errata_id = ANY(%s)",
                (advisory_names,),
            )
            for row in cur.fetchall():
                name = row["errata_id"]
                if name in patches_by_name:
                    patches_by_name[name]["severity"] = row["severity"]
    except Exception as e:
        logger.warning(f"_enrich_severity_info: DB query failed: {e}")


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
                    name = _normalize_advisory_name(e.get("advisory_name") or "")
                    if not name:
                        continue
                    if name not in patches_by_name:
                        patches_by_name[name] = {
                            "advisory_name":  name,
                            "advisory_type":  e.get("advisory_type", ""),
                            "synopsis":       e.get("advisory_synopsis") or e.get("synopsis", ""),
                            "date":           str(e.get("date", "") or ""),
                            "severity":       None,
                            "systems_affected": [],
                        }
                    patches_by_name[name]["systems_affected"].append(sid)

            if patches_by_name:
                _enrich_reboot_info(patches_by_name)
                _enrich_latest_info(patches_by_name)
                _enrich_severity_info(patches_by_name)

            # Ordinamento: patch più recenti (is_latest=True) prima,
            # poi no-reboot prima di reboot, poi data discendente.
            patches = sorted(
                patches_by_name.values(),
                key=lambda p: (
                    p.get("is_latest", True),          # True > False → latest first
                    not bool(p.get("requires_reboot")), # True (no-reboot) first
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
