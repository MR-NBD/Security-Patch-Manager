"""
SPM Orchestrator - Queue Manager

Gestisce la coda di test patch:
- Aggiunta errata (con fetch on-demand pacchetti da UYUNI)
- Auto-soppressione errata più vecchie (stessa famiglia USN o package overlap)
- Analisi pacchetti per profilo di rischio
- Calcolo Success Score (0-100)
- CRUD su patch_test_queue e patch_risk_profile

Funzioni pubbliche:
  extract_advisory_base()            → USN-XXXX-N → USN-XXXX (None per non-USN)
  add_to_queue()                     → inserisce errata, sopprime vecchie, ritorna row con "superseded"
  get_queue() / get_queue_item()     → lettura coda con filtri e join
  update_queue_item()                → aggiorna priority_override / notes
  remove_from_queue()                → solo se status='queued'
  get_queue_stats()                  → aggregati per status e OS
"""

import json
import logging
import re
from typing import Optional

from app.services.db import get_db
from app.services import uyuni_client
from app.utils.serializers import serialize_row as _serialize_row

logger = logging.getLogger(__name__)

# Pattern che indicano aggiornamento kernel
KERNEL_PATTERNS = [
    "kernel", "linux-image", "linux-headers",
    "linux-modules", "linux-generic", "linux-kvm",
]

# Pattern che richiedono reboot (superset kernel)
REBOOT_PATTERNS = KERNEL_PATTERNS + [
    "glibc", "libc6", "libc-bin",
    "systemd", "udev", "dbus",
    "openssh-server", "openssh-client",
    "initramfs-tools", "grub",
]

# Pattern che modificano config di sistema
_CONFIG_PATTERNS = [
    "openssl", "libssl", "ca-certificates",
    "sudo", "pam", "libpam",
    "grub", "initramfs", "apparmor",
    "selinux", "nss",
]


# ─────────────────────────────────────────────
# Analisi pacchetti
# ─────────────────────────────────────────────

def _matches_any(name: str, patterns: list) -> bool:
    n = (name or "").lower()
    return any(p in n for p in patterns)


def _analyze_packages(packages: list) -> dict:
    """
    Analizza lista pacchetti per caratteristiche di rischio.
    packages: [{name, version, release, size_kb}, ...]
    """
    affects_kernel = False
    requires_reboot = False
    modifies_config = False
    total_size_kb = 0

    for pkg in packages:
        name = pkg.get("name", "")
        size = pkg.get("size_kb", 0) or 0
        total_size_kb += size

        if _matches_any(name, KERNEL_PATTERNS):
            affects_kernel = True
        if _matches_any(name, REBOOT_PATTERNS):
            requires_reboot = True
        if _matches_any(name, _CONFIG_PATTERNS):
            modifies_config = True

    # Se kernel → implica reboot
    if affects_kernel:
        requires_reboot = True

    return {
        "affects_kernel":   affects_kernel,
        "requires_reboot":  requires_reboot,
        "modifies_config":  modifies_config,
        "package_count":    len(packages),
        "dependency_count": max(0, len(packages) - 1),
        "total_size_kb":    total_size_kb,
    }


# ─────────────────────────────────────────────
# Success Score
# ─────────────────────────────────────────────

_DEFAULT_WEIGHTS = {
    "kernel_penalty":           30,
    "reboot_penalty":           15,
    "config_penalty":           10,
    "dependency_penalty_per":    3,
    "dependency_penalty_max":   15,
    "size_penalty_per_mb":       2,
    "size_penalty_max":         10,
    "history_penalty_max":      20,
    "min_tests_for_history":     3,
    "small_patch_bonus":         5,
    "small_patch_threshold_kb": 100,
}


def _load_score_weights() -> dict:
    """Carica score_weights da orchestrator_config (fallback defaults)."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT value FROM orchestrator_config"
                " WHERE key = 'score_weights'"
            )
            row = cur.fetchone()
            if row and row["value"]:
                return {**_DEFAULT_WEIGHTS, **row["value"]}
    except Exception as e:
        logger.warning(f"Could not load score_weights: {e}")
    return dict(_DEFAULT_WEIGHTS)


def _calculate_score(analysis: dict, profile: Optional[dict] = None) -> int:
    """
    Calcola Success Score (0–100).

    Penalità applicate su base 100:
      - kernel:       -30
      - reboot:       -15
      - config:       -10
      - dipendenze:   -3/dep (max -15)
      - dimensione:   -2/MB  (max -10)
      - storico:      fino a -20 (solo se tested >= min_tests)
    Bonus:
      - patch piccola (<100 KB): +5
    """
    w = _load_score_weights()
    score = 100

    if analysis.get("affects_kernel"):
        score -= w["kernel_penalty"]
    if analysis.get("requires_reboot"):
        score -= w["reboot_penalty"]
    if analysis.get("modifies_config"):
        score -= w["config_penalty"]

    dep_penalty = min(
        analysis.get("dependency_count", 0) * w["dependency_penalty_per"],
        w["dependency_penalty_max"],
    )
    score -= dep_penalty

    size_mb = analysis.get("total_size_kb", 0) / 1024
    size_penalty = min(
        round(size_mb * w["size_penalty_per_mb"]),
        w["size_penalty_max"],
    )
    score -= size_penalty

    if analysis.get("total_size_kb", 0) < w["small_patch_threshold_kb"]:
        score += w["small_patch_bonus"]

    if profile:
        tested = profile.get("times_tested", 0) or 0
        failed = profile.get("times_failed", 0) or 0
        if tested >= w["min_tests_for_history"]:
            failure_rate = failed / tested
            score -= round(failure_rate * w["history_penalty_max"])

    return max(0, min(100, score))


# ─────────────────────────────────────────────
# Risk Profile
# ─────────────────────────────────────────────

_UPSERT_PROFILE_SQL = """
    INSERT INTO patch_risk_profile (
        errata_id,
        affects_kernel, requires_reboot, modifies_config,
        package_count, dependency_count, total_size_kb,
        success_score
    ) VALUES (
        %(errata_id)s,
        %(affects_kernel)s, %(requires_reboot)s, %(modifies_config)s,
        %(package_count)s, %(dependency_count)s, %(total_size_kb)s,
        %(success_score)s
    )
    ON CONFLICT (errata_id) DO UPDATE SET
        affects_kernel   = EXCLUDED.affects_kernel,
        requires_reboot  = EXCLUDED.requires_reboot,
        modifies_config  = EXCLUDED.modifies_config,
        package_count    = EXCLUDED.package_count,
        dependency_count = EXCLUDED.dependency_count,
        total_size_kb    = EXCLUDED.total_size_kb,
        success_score    = EXCLUDED.success_score
    RETURNING
        errata_id, affects_kernel, requires_reboot, modifies_config,
        package_count, dependency_count, total_size_kb, success_score,
        times_tested, times_failed
"""


def _upsert_risk_profile(errata_id: str, analysis: dict) -> dict:
    """Crea o aggiorna profilo di rischio. Ritorna il profilo salvato."""
    existing = None
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT times_tested, times_failed"
                " FROM patch_risk_profile WHERE errata_id = %s",
                (errata_id,),
            )
            row = cur.fetchone()
            if row:
                existing = dict(row)
    except Exception:
        pass

    score = _calculate_score(analysis, existing)
    params = {"errata_id": errata_id, "success_score": score, **analysis}

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(_UPSERT_PROFILE_SQL, params)
        return dict(cur.fetchone())


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def extract_advisory_base(errata_id: str) -> Optional[str]:
    """
    Estrae il nome base di un advisory USN senza il numero di revisione.
    'USN-7412-2' → 'USN-7412'
    'USN-7412-1' → 'USN-7412'
    Non-USN (RHSA, CVE, ecc.): ritorna None (nessuna revisione).
    """
    m = re.match(r'^(USN-\d+)-\d+$', errata_id)
    return m.group(1) if m else None


def _suppress_older_queued_errata(
    new_errata_id: str,
    target_os: str,
    new_packages: list,
    new_issued_date: Optional[str],
) -> list:
    """
    Cerca nella coda errata più vecchie che la nuova patch sostituisce e le marca
    come 'superseded'. L'operatore ha già scelto la patch più recente — le versioni
    precedenti ancora in coda vengono automaticamente soppresse.

    Due criteri (OR):
      1. Stesso advisory base USN (es. USN-7412-1 viene soppressa da USN-7412-2)
      2. Sovrapposizione dei package names + issued_date precedente

    Ritorna lista degli errata_id soppressi.
    """
    suppressed = []
    advisory_base = extract_advisory_base(new_errata_id)
    new_pkg_names = {
        p.get("name", "").lower() for p in new_packages if p.get("name")
    }

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT q.id, q.errata_id, e.packages, e.issued_date
                FROM patch_test_queue q
                JOIN errata_cache e ON q.errata_id = e.errata_id
                WHERE q.target_os = %s
                  AND q.status IN ('queued', 'retry_pending')
                  AND q.errata_id != %s
                """,
                (target_os, new_errata_id),
            )
            candidates = cur.fetchall()

        to_suppress = []
        for row in candidates:
            old_id   = row["errata_id"]
            old_pkgs = row["packages"] or []
            old_date = str(row["issued_date"] or "")

            should_suppress = False

            # Criterio 1: stesso advisory base (USN-XXXX con revisione precedente)
            if advisory_base:
                old_base = extract_advisory_base(old_id)
                if old_base == advisory_base:
                    should_suppress = True

            # Criterio 2: package overlap + data precedente
            if not should_suppress and new_pkg_names and old_pkgs:
                old_pkg_names = {
                    p.get("name", "").lower() for p in old_pkgs if p.get("name")
                }
                if new_pkg_names & old_pkg_names:
                    if new_issued_date and old_date and old_date < str(new_issued_date):
                        should_suppress = True

            if should_suppress:
                to_suppress.append(old_id)
                suppressed.append(old_id)

        if to_suppress:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE patch_test_queue
                    SET status = 'superseded', superseded_by = %s
                    WHERE errata_id = ANY(%s) AND target_os = %s
                      AND status IN ('queued', 'retry_pending')
                    """,
                    (new_errata_id, to_suppress, target_os),
                )
            logger.info(
                f"Queue: suppressed {len(to_suppress)} older errata "
                f"→ {to_suppress} (superseded by {new_errata_id!r})"
            )

    except Exception as e:
        logger.warning(f"Queue: _suppress_older_queued_errata failed: {e}")

    return suppressed


def add_to_queue(
    errata_id: str,
    target_os: str,
    priority_override: int = 0,
    created_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Aggiunge un errata alla coda di test.

    Workflow:
      1. Verifica errata in errata_cache
      2. Controlla che non sia già in coda (stato attivo)
      3. Fetch pacchetti da UYUNI (on-demand via errata.listPackages)
      4. Aggiorna packages in errata_cache
      5. Analisi rischio + upsert patch_risk_profile
      6. Calcola Success Score e inserisce in patch_test_queue

    Raises:
      ValueError: errata non trovato o già in coda
    """
    # 1. Verifica errata in cache
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT errata_id, synopsis, severity, issued_date"
            " FROM errata_cache WHERE errata_id = %s",
            (errata_id,),
        )
        errata = cur.fetchone()

    if not errata:
        raise ValueError(f"Errata {errata_id!r} not found in errata_cache")

    issued_date = errata.get("issued_date")

    # 2. Controlla duplicato attivo
    # 'superseded' è escluso: un errata precedentemente soppresso può essere
    # re-aggiunto dall'operatore se necessario.
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, status FROM patch_test_queue
            WHERE errata_id = %s AND target_os = %s
              AND status NOT IN ('completed', 'rolled_back', 'rejected', 'superseded')
            """,
            (errata_id, target_os),
        )
        existing = cur.fetchone()

    if existing:
        raise ValueError(
            f"Errata {errata_id!r} already in queue "
            f"(id={existing['id']}, status={existing['status']})"
        )

    # 3. Fetch packages on-demand
    packages = uyuni_client.get_errata_packages(errata_id)
    logger.info(f"Queue: {errata_id} → {len(packages)} packages fetched")

    # 4. Aggiorna packages in errata_cache (best-effort)
    if packages:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE errata_cache SET packages = %s::jsonb"
                    " WHERE errata_id = %s",
                    (json.dumps(packages), errata_id),
                )
        except Exception as e:
            logger.warning(f"Could not update packages for {errata_id}: {e}")

    # 5. Analisi + risk profile
    analysis = _analyze_packages(packages)
    profile = _upsert_risk_profile(errata_id, analysis)
    score = profile["success_score"]

    # 6. Insert in queue
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO patch_test_queue (
                errata_id, target_os, success_score,
                priority_override, created_by, notes
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING
                id, errata_id, target_os, status,
                success_score, priority_override,
                queued_at, created_by, notes
            """,
            (errata_id, target_os, score,
             priority_override, created_by, notes),
        )
        row = _serialize_row(dict(cur.fetchone()))

    logger.info(
        f"Queue: added {errata_id} "
        f"(os={target_os}, score={score}, id={row['id']})"
    )

    # Sopprime errata più vecchie nella coda con stessa famiglia USN o package overlap
    suppressed = _suppress_older_queued_errata(
        new_errata_id=errata_id,
        target_os=target_os,
        new_packages=packages,
        new_issued_date=str(issued_date) if issued_date else None,
    )
    row["superseded"] = suppressed

    return row


def get_queue(
    status: Optional[str] = None,
    target_os: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """
    Restituisce la coda con filtri opzionali.
    Ordinamento: priority_override DESC, success_score DESC, queued_at ASC.
    """
    conditions = []
    base_params: list = []

    if status:
        conditions.append("q.status = %s")
        base_params.append(status)
    if target_os:
        conditions.append("q.target_os = %s")
        base_params.append(target_os)
    if severity:
        conditions.append("e.severity = %s")
        base_params.append(severity)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM patch_test_queue q
        LEFT JOIN errata_cache e ON q.errata_id = e.errata_id
        {where}
    """

    list_sql = f"""
        SELECT
            q.id            AS queue_id,
            q.errata_id,
            q.target_os,
            q.status,
            q.success_score,
            q.priority_override,
            q.queued_at,
            q.started_at,
            q.completed_at,
            q.test_id,
            q.created_by,
            q.notes,
            e.synopsis,
            e.severity,
            e.type          AS errata_type,
            e.issued_date,
            rp.affects_kernel,
            rp.requires_reboot,
            rp.times_tested,
            rp.times_failed,
            t.result        AS test_result,
            t.duration_seconds AS test_duration
        FROM patch_test_queue q
        LEFT JOIN errata_cache e  ON q.errata_id = e.errata_id
        LEFT JOIN patch_risk_profile rp ON q.errata_id = rp.errata_id
        LEFT JOIN patch_tests t   ON q.test_id  = t.id
        {where}
        ORDER BY
            q.priority_override              DESC,
            COALESCE(rp.requires_reboot, FALSE) ASC,
            q.success_score                  DESC,
            q.queued_at                      ASC
        LIMIT %s OFFSET %s
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(count_sql, base_params)
        total = cur.fetchone()["total"]

        cur.execute(list_sql, base_params + [limit, offset])
        items = [_serialize_row(dict(r)) for r in cur.fetchall()]

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "items":  items,
    }


def get_queue_item(queue_id: int) -> Optional[dict]:
    """Dettaglio di un singolo elemento in coda. Ritorna None se non trovato."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                q.id            AS queue_id,
                q.errata_id,
                q.target_os,
                q.status,
                q.success_score,
                q.priority_override,
                q.queued_at,
                q.started_at,
                q.completed_at,
                q.test_id,
                q.created_by,
                q.notes,
                e.synopsis,
                e.severity,
                e.description,
                e.type          AS errata_type,
                e.issued_date,
                e.cves,
                e.packages,
                rp.affects_kernel,
                rp.requires_reboot,
                rp.modifies_config,
                rp.package_count,
                rp.dependency_count,
                rp.total_size_kb,
                rp.times_tested,
                rp.times_failed,
                rp.last_failure_reason,
                t.result        AS test_result,
                t.duration_seconds AS test_duration,
                t.failure_reason,
                t.failure_phase,
                t.required_reboot,
                t.metrics_evaluation,
                t.failed_services
            FROM patch_test_queue q
            LEFT JOIN errata_cache e  ON q.errata_id = e.errata_id
            LEFT JOIN patch_risk_profile rp ON q.errata_id = rp.errata_id
            LEFT JOIN patch_tests t   ON q.test_id  = t.id
            WHERE q.id = %s
            """,
            (queue_id,),
        )
        row = cur.fetchone()

    return _serialize_row(dict(row)) if row else None


def update_queue_item(
    queue_id: int,
    priority_override: Optional[int] = None,
    notes: Optional[str] = None,
) -> Optional[dict]:
    """Aggiorna priority_override o notes. Ritorna il record aggiornato."""
    sets: list = []
    params: list = []

    if priority_override is not None:
        sets.append("priority_override = %s")
        params.append(priority_override)
    if notes is not None:
        sets.append("notes = %s")
        params.append(notes)

    if not sets:
        return get_queue_item(queue_id)

    params.append(queue_id)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE patch_test_queue SET {', '.join(sets)}"
            f" WHERE id = %s RETURNING id",
            params,
        )
        updated = cur.fetchone()

    return get_queue_item(queue_id) if updated else None


def remove_from_queue(queue_id: int) -> bool:
    """
    Rimuove dalla coda (solo se status='queued').
    Ritorna True se rimosso, False se non trovato o in stato non rimovibile.
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM patch_test_queue"
            " WHERE id = %s AND status = 'queued'"
            " RETURNING id",
            (queue_id,),
        )
        return cur.fetchone() is not None


def get_queue_stats() -> dict:
    """Statistiche aggregate della coda (esclude completed/rolled_back/rejected)."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*)                                              AS total,
                COUNT(*) FILTER (WHERE q.status = 'queued')            AS queued,
                COUNT(*) FILTER (WHERE q.status = 'retry_pending')     AS retry_pending,
                COUNT(*) FILTER (WHERE q.status = 'testing')           AS testing,
                COUNT(*) FILTER (WHERE q.status = 'passed')            AS passed,
                COUNT(*) FILTER (WHERE q.status = 'failed')            AS failed,
                COUNT(*) FILTER (WHERE q.status = 'pending_approval')  AS pending_approval,
                COUNT(*) FILTER (WHERE q.status = 'approved')          AS approved,
                COUNT(*) FILTER (WHERE q.status = 'superseded')        AS superseded,
                COUNT(*) FILTER (
                    WHERE q.status IN ('prod_applied', 'completed')
                )                                                        AS deployed,
                COUNT(*) FILTER (WHERE q.target_os = 'ubuntu')          AS ubuntu,
                COUNT(*) FILTER (WHERE q.target_os = 'rhel')            AS rhel,
                AVG(q.success_score)                                     AS avg_score,
                COUNT(*) FILTER (
                    WHERE rp.requires_reboot = TRUE
                    AND q.status NOT IN ('rolled_back', 'rejected', 'completed', 'superseded')
                )                                                        AS requires_reboot,
                COUNT(*) FILTER (
                    WHERE COALESCE(rp.requires_reboot, FALSE) = FALSE
                    AND q.status NOT IN ('rolled_back', 'rejected', 'completed', 'superseded')
                )                                                        AS no_reboot
            FROM patch_test_queue q
            LEFT JOIN patch_risk_profile rp ON q.errata_id = rp.errata_id
            WHERE q.status NOT IN ('rolled_back', 'rejected', 'completed', 'superseded')
        """)
        row = dict(cur.fetchone())

    avg = row.pop("avg_score", None)
    return {
        **row,
        "avg_success_score": round(float(avg), 1) if avg else None,
    }
