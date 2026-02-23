"""
SPM Orchestrator - Approval Manager

Gestisce il workflow di approvazione patch dopo un test superato.

Flusso:
  pending_approval → [operatore] → approved   → (production deployment)
                                 → rejected   → fine
                                 → snoozed    → (re-queue dopo snooze_until)

Ogni azione viene registrata in patch_approvals (audit trail completo).
Le patch snoozed vengono automaticamente riportate a pending_approval
quando snooze_until è scaduto (via process_snoozed(), chiamato dallo scheduler).
"""

import json
import logging
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional

from app.services.db import get_db

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Serializzazione helper
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
# Query: pending approvals
# ─────────────────────────────────────────────

def get_pending(limit: int = 50, offset: int = 0) -> dict:
    """
    Lista patch in attesa di approvazione (status='pending_approval').
    Include dati errata, risk profile e test superato.
    Ordinamento: priority_override DESC, success_score DESC, completed_at ASC.
    """
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT COUNT(*) AS total FROM patch_test_queue WHERE status = 'pending_approval'"
        )
        total = cur.fetchone()["total"]

        cur.execute("""
            SELECT
                q.id            AS queue_id,
                q.errata_id,
                q.target_os,
                q.success_score,
                q.priority_override,
                q.queued_at,
                q.completed_at,
                q.test_id,
                q.created_by,
                q.notes,
                e.synopsis,
                e.severity,
                e.type          AS errata_type,
                e.issued_date,
                e.cves,
                rp.affects_kernel,
                rp.requires_reboot,
                rp.modifies_config,
                rp.package_count,
                rp.total_size_kb,
                rp.times_tested,
                rp.times_failed,
                t.result        AS test_result,
                t.duration_seconds  AS test_duration,
                t.reboot_performed,
                t.failed_services,
                t.metrics_evaluation,
                EXTRACT(EPOCH FROM (NOW() - q.completed_at)) / 3600 AS hours_pending
            FROM patch_test_queue q
            LEFT JOIN errata_cache       e  ON q.errata_id = e.errata_id
            LEFT JOIN patch_risk_profile rp ON q.errata_id = rp.errata_id
            LEFT JOIN patch_tests        t  ON q.test_id   = t.id
            WHERE q.status = 'pending_approval'
            ORDER BY q.priority_override DESC, q.success_score DESC, q.completed_at ASC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        items = [_serialize_row(dict(r)) for r in cur.fetchall()]

    return {"total": total, "limit": limit, "offset": offset, "items": items}


def get_pending_detail(queue_id: int) -> Optional[dict]:
    """
    Dettaglio completo di una patch in attesa di approvazione.
    Ritorna None se non trovata o non in stato pending_approval.
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                q.id            AS queue_id,
                q.errata_id,
                q.target_os,
                q.status,
                q.success_score,
                q.priority_override,
                q.queued_at,
                q.completed_at,
                q.test_id,
                q.created_by,
                q.notes,
                e.synopsis,
                e.description,
                e.severity,
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
                rp.success_score    AS risk_score,
                rp.times_tested,
                rp.times_failed,
                rp.last_failure_reason,
                t.result            AS test_result,
                t.duration_seconds  AS test_duration,
                t.started_at        AS test_started_at,
                t.completed_at      AS test_completed_at,
                t.reboot_performed,
                t.reboot_successful,
                t.failed_services,
                t.baseline_metrics,
                t.post_patch_metrics,
                t.metrics_delta,
                t.metrics_evaluation,
                t.rollback_performed,
                t.rollback_type
            FROM patch_test_queue q
            LEFT JOIN errata_cache       e  ON q.errata_id = e.errata_id
            LEFT JOIN patch_risk_profile rp ON q.errata_id = rp.errata_id
            LEFT JOIN patch_tests        t  ON q.test_id   = t.id
            WHERE q.id = %s AND q.status = 'pending_approval'
        """, (queue_id,))
        row = cur.fetchone()

    return _serialize_row(dict(row)) if row else None


# ─────────────────────────────────────────────
# Azioni di approvazione
# ─────────────────────────────────────────────

def _write_approval(
    queue_id: int,
    errata_id: str,
    action: str,
    action_by: str,
    reason: Optional[str],
    snooze_until: Optional[datetime],
    ip_address: Optional[str],
) -> int:
    """Inserisce riga in patch_approvals. Ritorna l'id generato."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO patch_approvals
                (queue_id, errata_id, action, action_by, reason, snooze_until, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (queue_id, errata_id, action, action_by, reason, snooze_until, ip_address),
        )
        return cur.fetchone()["id"]


def _require_pending(queue_id: int) -> dict:
    """
    Verifica che l'elemento esista e sia in status='pending_approval'.
    Ritorna il record. Solleva ValueError se non trovato o stato errato.
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, errata_id, status FROM patch_test_queue WHERE id = %s",
            (queue_id,),
        )
        row = cur.fetchone()

    if not row:
        raise ValueError(f"Queue item {queue_id} not found")
    if row["status"] != "pending_approval":
        raise ValueError(
            f"Queue item {queue_id} is in status '{row['status']}', "
            f"expected 'pending_approval'"
        )
    return dict(row)


def approve(
    queue_id: int,
    action_by: str,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> dict:
    """
    Approva una patch in pending_approval → status='approved'.
    Registra in patch_approvals.
    Ritorna dict con approval_id e queue_id.
    """
    item = _require_pending(queue_id)
    errata_id = item["errata_id"]

    approval_id = _write_approval(
        queue_id, errata_id, "approved", action_by, reason, None, ip_address,
    )

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE patch_test_queue SET status = 'approved' WHERE id = %s",
            (queue_id,),
        )

    logger.info(
        f"Approval: {errata_id!r} APPROVED by {action_by!r} "
        f"(queue_id={queue_id}, approval_id={approval_id})"
    )
    return {"approval_id": approval_id, "queue_id": queue_id, "action": "approved"}


def reject(
    queue_id: int,
    action_by: str,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> dict:
    """
    Rifiuta una patch in pending_approval → status='rejected'.
    Registra in patch_approvals.
    """
    item = _require_pending(queue_id)
    errata_id = item["errata_id"]

    approval_id = _write_approval(
        queue_id, errata_id, "rejected", action_by, reason, None, ip_address,
    )

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE patch_test_queue SET status = 'rejected' WHERE id = %s",
            (queue_id,),
        )

    logger.info(
        f"Approval: {errata_id!r} REJECTED by {action_by!r} "
        f"(queue_id={queue_id}, reason={reason!r})"
    )
    return {"approval_id": approval_id, "queue_id": queue_id, "action": "rejected"}


def snooze(
    queue_id: int,
    action_by: str,
    snooze_until: datetime,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> dict:
    """
    Rimanda una patch in pending_approval → status='snoozed'.
    La patch tornerà a pending_approval quando snooze_until è scaduto
    (via process_snoozed(), chiamato dallo scheduler).
    """
    item = _require_pending(queue_id)
    errata_id = item["errata_id"]

    if snooze_until <= datetime.now(timezone.utc):
        raise ValueError("snooze_until must be in the future")

    approval_id = _write_approval(
        queue_id, errata_id, "snoozed", action_by, reason, snooze_until, ip_address,
    )

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE patch_test_queue SET status = 'snoozed' WHERE id = %s",
            (queue_id,),
        )

    logger.info(
        f"Approval: {errata_id!r} SNOOZED by {action_by!r} "
        f"until {snooze_until.isoformat()} (queue_id={queue_id})"
    )
    return {
        "approval_id":  approval_id,
        "queue_id":     queue_id,
        "action":       "snoozed",
        "snooze_until": snooze_until.isoformat(),
    }


# ─────────────────────────────────────────────
# Snooze processing (scheduler job)
# ─────────────────────────────────────────────

def process_snoozed() -> int:
    """
    Riporta a 'pending_approval' le patch snoozed il cui snooze_until è scaduto.
    Chiamato ogni 15 minuti dallo scheduler.
    Ritorna il numero di patch ri-attivate.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor()
            # Trova queue_ids snoozed con snooze_until scaduto
            cur.execute("""
                SELECT DISTINCT pa.queue_id
                FROM patch_approvals pa
                JOIN patch_test_queue q ON pa.queue_id = q.id
                WHERE pa.action = 'snoozed'
                  AND pa.snooze_until <= NOW()
                  AND q.status = 'snoozed'
            """)
            rows = cur.fetchall()
            ids = [r["queue_id"] for r in rows if r["queue_id"]]

            if ids:
                cur.execute(
                    """UPDATE patch_test_queue
                       SET status = 'pending_approval'
                       WHERE id = ANY(%s) AND status = 'snoozed'""",
                    (ids,),
                )
                logger.info(
                    f"Approval: {len(ids)} snoozed patch(es) re-activated: {ids}"
                )

        return len(ids)

    except Exception as e:
        logger.warning(f"process_snoozed failed: {e}")
        return 0


# ─────────────────────────────────────────────
# Storico approvazioni
# ─────────────────────────────────────────────

def get_history(limit: int = 50, offset: int = 0) -> dict:
    """
    Storico azioni di approvazione recenti (tutte le azioni, non solo pending).
    Ordinato per action_at DESC.
    """
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) AS total FROM patch_approvals")
        total = cur.fetchone()["total"]

        cur.execute("""
            SELECT
                pa.id           AS approval_id,
                pa.queue_id,
                pa.errata_id,
                pa.action,
                pa.action_by,
                pa.action_at,
                pa.reason,
                pa.snooze_until,
                pa.ip_address,
                e.synopsis,
                e.severity,
                q.target_os,
                q.status        AS current_status
            FROM patch_approvals pa
            LEFT JOIN errata_cache      e ON pa.errata_id = e.errata_id
            LEFT JOIN patch_test_queue  q ON pa.queue_id  = q.id
            ORDER BY pa.action_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        items = [_serialize_row(dict(r)) for r in cur.fetchall()]

    return {"total": total, "limit": limit, "offset": offset, "items": items}
