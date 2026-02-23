"""
SPM Orchestrator - Deployment Manager

Gestisce il deployment delle patch approvate sui sistemi di produzione.

Flusso:
  approved → create_deployment() → [execute] → prod_applied | partial_failure
  prod_applied → rollback_deployment() → rolled_back

Applicazione parallela via Salt API su N sistemi di produzione.
Per ogni sistema: Salt pkg.install → traccia {pkg: {old, new}} per rollback.

system_results JSONB (per sistema):
  {
    "prod-ubuntu-01": {
      "status":           "success" | "failed" | "unreachable",
      "packages_applied": {"openssl": {"old": "3.0.2", "new": "3.0.2-1ubuntu1"}},
      "error":            null | "messaggio errore"
    }
  }

Rollback produzione: sempre package-based (reinstalla versioni 'old' da system_results).
Snapshot non garantito in produzione.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional

from app.config import Config
from app.services.db import get_db
from app.services.salt_client import SaltSession

logger = logging.getLogger(__name__)

# Worker paralleli per deployment multi-sistema
_DEPLOY_WORKERS = 5


# ─────────────────────────────────────────────
# Serializzazione
# ─────────────────────────────────────────────

def _serialize(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return obj


def _serialize_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


# ─────────────────────────────────────────────
# DB Helpers
# ─────────────────────────────────────────────

def _get_approved_item(queue_id: int) -> dict:
    """
    Ritorna l'elemento in coda se status='approved'.
    Raises ValueError se non trovato o stato errato.
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT q.id, q.errata_id, q.target_os, q.status,
                   pa.id AS approval_id
            FROM patch_test_queue q
            LEFT JOIN patch_approvals pa
                ON pa.queue_id = q.id AND pa.action = 'approved'
            WHERE q.id = %s
            ORDER BY pa.action_at DESC
            LIMIT 1
        """, (queue_id,))
        row = cur.fetchone()

    if not row:
        raise ValueError(f"Queue item {queue_id} not found")
    if row["status"] != "approved":
        raise ValueError(
            f"Queue item {queue_id} is '{row['status']}', expected 'approved'"
        )
    return dict(row)


def _create_deployment_record(
    approval_id: Optional[int],
    errata_id: str,
    target_system_ids: list,
    total_systems: int,
    created_by: str,
    notes: Optional[str],
) -> int:
    """Inserisce riga in patch_deployments. Ritorna id generato."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO patch_deployments (
                approval_id, errata_id,
                target_system_ids, total_systems,
                status, created_by, notes
            ) VALUES (%s, %s, %s, %s, 'pending', %s, %s)
            RETURNING id
        """, (
            approval_id, errata_id,
            target_system_ids, total_systems,
            created_by, notes,
        ))
        return cur.fetchone()["id"]


def _update_deployment(deployment_id: int, **fields) -> None:
    """Aggiorna campi arbitrari in patch_deployments."""
    if not fields:
        return
    set_parts, values = [], []
    for k, v in fields.items():
        if k == "system_results":
            set_parts.append(f"{k} = %s::jsonb")
            values.append(json.dumps(v))
        else:
            set_parts.append(f"{k} = %s")
            values.append(v)
    values.append(deployment_id)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE patch_deployments SET {', '.join(set_parts)} WHERE id = %s",
            values,
        )


def _set_queue_status(queue_id: int, status: str) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE patch_test_queue SET status = %s WHERE id = %s",
            (status, queue_id),
        )


def _get_packages(errata_id: str) -> list:
    """Legge pacchetti da errata_cache. Fallback on-demand da UYUNI."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT packages FROM errata_cache WHERE errata_id = %s",
                (errata_id,),
            )
            row = cur.fetchone()
            if row and row["packages"]:
                pkgs = row["packages"]
                if isinstance(pkgs, list) and pkgs:
                    return pkgs
    except Exception as e:
        logger.warning(f"DeployManager: DB read packages failed: {e}")

    from app.services.uyuni_client import get_errata_packages
    return get_errata_packages(errata_id)


# ─────────────────────────────────────────────
# Deployment execution
# ─────────────────────────────────────────────

def _deploy_to_system(
    salt: SaltSession,
    system_name: str,
    pkg_names: list,
) -> dict:
    """
    Applica patch su un singolo sistema.
    Ritorna {"status", "packages_applied", "error"}.
    """
    if not salt.ping(system_name):
        return {
            "status":           "unreachable",
            "packages_applied": {},
            "error":            f"Minion {system_name!r} not reachable",
        }
    try:
        apply_result = salt.apply_packages(system_name, pkg_names)
        return {
            "status":           "success",
            "packages_applied": apply_result,
            "error":            None,
        }
    except Exception as e:
        return {
            "status":           "failed",
            "packages_applied": {},
            "error":            str(e),
        }


def create_and_execute(
    queue_id: int,
    target_systems: list,
    created_by: str,
    notes: Optional[str] = None,
) -> dict:
    """
    Crea il record di deployment ed esegue immediatamente.

    target_systems: [{"name": "prod-ubuntu-01"}, ...]
      "name" = Salt minion ID (hostname)
      "id"   = UYUNI system ID (opzionale, per audit)

    Ritorna dict con deployment_id e risultati per sistema.
    """
    if not target_systems:
        raise ValueError("target_systems must not be empty")

    # Verifica stato approved
    item = _get_approved_item(queue_id)
    errata_id   = item["errata_id"]
    approval_id = item.get("approval_id")

    system_names = [s["name"] for s in target_systems if s.get("name")]
    system_ids   = [s["id"]   for s in target_systems if s.get("id")]

    if not system_names:
        raise ValueError("Each target_system must have a 'name' (Salt minion ID)")

    packages  = _get_packages(errata_id)
    pkg_names = [p["name"] for p in packages if p.get("name")]

    if not pkg_names:
        logger.warning(f"DeployManager: no packages found for {errata_id!r}")

    # Crea record deployment
    deployment_id = _create_deployment_record(
        approval_id   = approval_id,
        errata_id     = errata_id,
        target_system_ids = system_ids or None,
        total_systems = len(system_names),
        created_by    = created_by,
        notes         = notes,
    )

    # Aggiorna stati
    _update_deployment(deployment_id, status="in_progress", started_at=datetime.now(timezone.utc))
    _set_queue_status(queue_id, "promoting")

    logger.info(
        f"DeployManager: START deployment {deployment_id} | "
        f"errata={errata_id!r} | systems={system_names} | "
        f"packages={len(pkg_names)}"
    )

    started_at    = datetime.now(timezone.utc)
    system_results: dict = {}
    succeeded     = 0
    failed        = 0
    failed_ids    = []

    # Applica in parallelo su tutti i sistemi
    try:
        with SaltSession() as salt:
            with ThreadPoolExecutor(max_workers=_DEPLOY_WORKERS) as ex:
                futs = {
                    ex.submit(_deploy_to_system, salt, name, pkg_names): name
                    for name in system_names
                }
                for fut in as_completed(futs):
                    name = futs[fut]
                    try:
                        result = fut.result()
                    except Exception as e:
                        result = {
                            "status":           "failed",
                            "packages_applied": {},
                            "error":            str(e),
                        }

                    system_results[name] = result

                    if result["status"] == "success":
                        succeeded += 1
                        logger.info(f"DeployManager: {name!r} → OK")
                    else:
                        failed += 1
                        failed_ids.append(name)
                        logger.warning(
                            f"DeployManager: {name!r} → {result['status']}: "
                            f"{result.get('error')}"
                        )

    except Exception as e:
        # Errore apertura sessione Salt
        logger.error(f"DeployManager: Salt session failed: {e}")
        _update_deployment(
            deployment_id,
            status       = "partial_failure",
            completed_at = datetime.now(timezone.utc),
            systems_succeeded = 0,
            systems_failed    = len(system_names),
            system_results    = {"_error": str(e)},
        )
        _set_queue_status(queue_id, "approved")   # riporta ad approved per ri-tentare
        raise

    # Determina status finale
    if failed == 0:
        final_status = "completed"
        queue_status = "prod_applied"
    else:
        final_status = "partial_failure"
        queue_status = "prod_applied"   # anche parziale è applicato

    completed_at = datetime.now(timezone.utc)
    duration_s   = int((completed_at - started_at).total_seconds())

    _update_deployment(
        deployment_id,
        status            = final_status,
        completed_at      = completed_at,
        systems_succeeded = succeeded,
        systems_failed    = failed,
        system_results    = system_results,
    )
    _set_queue_status(queue_id, queue_status)

    logger.info(
        f"DeployManager: END deployment {deployment_id} → {final_status.upper()} "
        f"({succeeded}/{len(system_names)} succeeded, {duration_s}s)"
    )

    return {
        "deployment_id":    deployment_id,
        "status":           final_status,
        "errata_id":        errata_id,
        "systems_total":    len(system_names),
        "systems_succeeded": succeeded,
        "systems_failed":   failed,
        "failed_systems":   failed_ids,
        "duration_s":       duration_s,
        "system_results":   system_results,
    }


# ─────────────────────────────────────────────
# Rollback deployment
# ─────────────────────────────────────────────

def _rollback_system(
    salt: SaltSession,
    system_name: str,
    packages_before: dict,
) -> dict:
    """
    Rollback package-based su un singolo sistema.
    packages_before: {pkg_name: {old: "version", new: "version"}} da system_results.
    """
    if not salt.ping(system_name):
        return {
            "status": "unreachable",
            "error":  f"Minion {system_name!r} not reachable",
        }
    try:
        pkgs_to_restore = [
            {name: versions.get("old")}
            for name, versions in packages_before.items()
            if isinstance(versions, dict) and versions.get("old")
        ]
        if pkgs_to_restore:
            salt._run(
                system_name,
                "pkg.install",
                kwarg={"pkgs": pkgs_to_restore},
            )
        return {"status": "success", "error": None}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def rollback_deployment(
    deployment_id: int,
    initiated_by: str,
    reason: str,
) -> dict:
    """
    Esegue rollback di un deployment completato (completed | partial_failure).
    Reinstalla le versioni precedenti dei pacchetti per ogni sistema.
    Crea record in patch_rollbacks.
    Aggiorna patch_deployments.status → 'rolled_back'.
    """
    # Leggi deployment
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM patch_deployments WHERE id = %s",
            (deployment_id,),
        )
        dep = cur.fetchone()

    if not dep:
        raise ValueError(f"Deployment {deployment_id} not found")

    dep = dict(dep)
    if dep["status"] not in ("completed", "partial_failure"):
        raise ValueError(
            f"Deployment {deployment_id} status is '{dep['status']}', "
            f"expected 'completed' or 'partial_failure'"
        )

    system_results = dep.get("system_results") or {}
    errata_id      = dep["errata_id"]

    # Sistemi da cui fare rollback (solo quelli con status=success)
    systems_to_rollback = {
        name: data
        for name, data in system_results.items()
        if isinstance(data, dict) and data.get("status") == "success"
    }

    if not systems_to_rollback:
        raise ValueError(
            "No successfully-deployed systems to rollback "
            "(no 'success' entries in system_results)"
        )

    # Crea record rollback
    started_at = datetime.now(timezone.utc)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO patch_rollbacks (
                deployment_id, errata_id, rollback_type,
                total_systems, initiated_by, reason,
                status, started_at
            ) VALUES (%s, %s, 'package', %s, %s, %s, 'in_progress', NOW())
            RETURNING id
        """, (
            deployment_id, errata_id,
            len(systems_to_rollback), initiated_by, reason,
        ))
        rollback_id = cur.fetchone()["id"]

    logger.info(
        f"DeployManager: ROLLBACK {rollback_id} | "
        f"deployment={deployment_id} | systems={list(systems_to_rollback)}"
    )

    rb_results  = {}
    succeeded   = 0
    failed      = 0
    failed_names = []

    try:
        with SaltSession() as salt:
            with ThreadPoolExecutor(max_workers=_DEPLOY_WORKERS) as ex:
                futs = {
                    ex.submit(
                        _rollback_system,
                        salt,
                        name,
                        data.get("packages_applied", {}),
                    ): name
                    for name, data in systems_to_rollback.items()
                }
                for fut in as_completed(futs):
                    name = futs[fut]
                    try:
                        result = fut.result()
                    except Exception as e:
                        result = {"status": "failed", "error": str(e)}

                    rb_results[name] = result

                    if result["status"] == "success":
                        succeeded += 1
                    else:
                        failed += 1
                        failed_names.append(name)
                        logger.warning(
                            f"DeployManager: rollback {name!r} FAILED: "
                            f"{result.get('error')}"
                        )

    except Exception as e:
        logger.error(f"DeployManager: Salt session error during rollback: {e}")
        failed = len(systems_to_rollback)
        succeeded = 0
        rb_results = {"_error": str(e)}

    # Status rollback
    if failed == 0:
        rb_status = "completed"
    elif succeeded == 0:
        rb_status = "failed"
    else:
        rb_status = "partial"

    completed_at = datetime.now(timezone.utc)
    duration_s   = int((completed_at - started_at).total_seconds())

    # Aggiorna patch_rollbacks
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE patch_rollbacks SET
                status            = %s,
                completed_at      = NOW(),
                duration_seconds  = %s,
                systems_succeeded = %s,
                systems_failed    = %s,
                system_results    = %s::jsonb
            WHERE id = %s
        """, (
            rb_status, duration_s,
            succeeded, failed,
            json.dumps(rb_results),
            rollback_id,
        ))

        # Aggiorna patch_deployments
        cur.execute("""
            UPDATE patch_deployments SET
                status             = 'rolled_back',
                rollback_performed = TRUE,
                rollback_type      = 'package',
                rollback_id        = %s,
                rollback_at        = NOW()
            WHERE id = %s
        """, (rollback_id, deployment_id))

    # Aggiorna status coda (se collegata)
    if dep.get("approval_id"):
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE patch_test_queue SET status = 'rolled_back'
                WHERE id = (
                    SELECT queue_id FROM patch_approvals WHERE id = %s
                )
            """, (dep["approval_id"],))

    logger.info(
        f"DeployManager: ROLLBACK {rollback_id} → {rb_status.upper()} "
        f"({succeeded}/{len(systems_to_rollback)} OK, {duration_s}s)"
    )

    return {
        "rollback_id":      rollback_id,
        "status":           rb_status,
        "systems_total":    len(systems_to_rollback),
        "systems_succeeded": succeeded,
        "systems_failed":   failed,
        "failed_systems":   failed_names,
        "duration_s":       duration_s,
    }


# ─────────────────────────────────────────────
# Query
# ─────────────────────────────────────────────

def get_deployment(deployment_id: int) -> Optional[dict]:
    """Dettaglio deployment con info errata e rollback."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                d.*,
                e.synopsis,
                e.severity,
                e.type    AS errata_type,
                r.status  AS rollback_status,
                r.systems_succeeded AS rollback_succeeded,
                r.systems_failed    AS rollback_failed
            FROM patch_deployments d
            LEFT JOIN errata_cache   e ON d.errata_id   = e.errata_id
            LEFT JOIN patch_rollbacks r ON d.rollback_id = r.id
            WHERE d.id = %s
        """, (deployment_id,))
        row = cur.fetchone()
    return _serialize_row(dict(row)) if row else None


def list_deployments(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Lista deployment con filtro opzionale su status."""
    conditions = []
    params: list = []

    if status:
        conditions.append("d.status = %s")
        params.append(status)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) AS total FROM patch_deployments d {where}",
            params,
        )
        total = cur.fetchone()["total"]

        cur.execute(f"""
            SELECT
                d.id, d.errata_id, d.status,
                d.total_systems, d.systems_succeeded, d.systems_failed,
                d.started_at, d.completed_at, d.created_by,
                d.rollback_performed, d.rollback_at,
                e.synopsis, e.severity
            FROM patch_deployments d
            LEFT JOIN errata_cache e ON d.errata_id = e.errata_id
            {where}
            ORDER BY d.started_at DESC NULLS LAST
            LIMIT %s OFFSET %s
        """, params + [limit, offset])

        items = [_serialize_row(dict(r)) for r in cur.fetchall()]

    return {"total": total, "limit": limit, "offset": offset, "items": items}
