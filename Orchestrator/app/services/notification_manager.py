"""
SPM Orchestrator - Notification Manager

Registra eventi operativi in orchestrator_notifications.
La dashboard legge le notifiche non lette (delivered=FALSE) e le mostra come banner.

Canale unico: 'dashboard' — l'audit esteso è delegato alle note UYUNI (add_note).

Evento → notifica:
  test_failure     → test FAILED/ERROR su sistema test
  pending_approval → patch superata il test, in attesa di approvazione operatore

Comportamento:
  - Scrive SEMPRE 1 riga per evento (best-effort, non solleva mai eccezioni).
  - delivered=FALSE → notifica non letta → banner nella dashboard.
  - delivered=TRUE  → marcata come letta dall'operatore.
  - 'passed' e altri risultati intermedi non generano notifiche.
"""

import logging
from typing import Optional

from app.services.db import get_db

logger = logging.getLogger(__name__)


def _write_notification(
    notification_type: str,
    subject: str,
    body: str,
    errata_id: Optional[str] = None,
    queue_id: Optional[int] = None,
    test_id: Optional[int] = None,
) -> Optional[int]:
    """Inserisce riga in orchestrator_notifications. Ritorna l'id o None su errore."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO orchestrator_notifications
                    (notification_type, errata_id, queue_id, test_id,
                     channel, recipient, subject, body, delivered)
                VALUES (%s, %s, %s, %s, 'dashboard', 'operator', %s, %s, FALSE)
                RETURNING id
                """,
                (notification_type, errata_id, queue_id, test_id, subject, body),
            )
            return cur.fetchone()["id"]
    except Exception as e:
        logger.warning(f"NotificationManager: _write_notification failed: {e}")
        return None


def notify_test_result(
    test_id: int,
    queue_id: int,
    errata_id: str,
    result: str,
    failure_phase: Optional[str],
    failure_reason: Optional[str],
    system_name: str,
    duration_s: int,
) -> None:
    """
    Registra il risultato del test in orchestrator_notifications (best-effort).

    result='failed' / 'error'  → alert di fallimento
    result='pending_approval'  → avviso approvazione da completare
    Altri risultati             → ignorati silenziosamente

    Il riepilogo completo del batch (tutte le patch testate) viene scritto
    nelle note UYUNI del gruppo tramite _add_batch_note() in test_engine.py.
    """
    try:
        if result in ("failed", "error"):
            notification_type = "test_failure"
            subject = f"[SPM] Test FAILED — {errata_id} su {system_name}"
            body = (
                f"Il test automatico per la patch {errata_id!r} è FALLITO.\n\n"
                f"Sistema  : {system_name}\n"
                f"Fase     : {failure_phase or 'unknown'}\n"
                f"Motivo   : {failure_reason or 'nessun dettaglio disponibile'}\n"
                f"Durata   : {duration_s}s\n"
                f"Test ID  : {test_id}\n"
                f"Queue ID : {queue_id}\n\n"
                f"Dettagli: GET /api/v1/tests/{test_id}"
            )

        elif result == "pending_approval":
            notification_type = "pending_approval"
            subject = f"[SPM] Patch pronta per approvazione — {errata_id}"
            body = (
                f"La patch {errata_id!r} ha superato il test automatico "
                f"ed è in attesa di approvazione.\n\n"
                f"Sistema  : {system_name}\n"
                f"Durata   : {duration_s}s\n"
                f"Test ID  : {test_id}\n"
                f"Queue ID : {queue_id}\n\n"
                f"Approvare, rifiutare o rimandare:\n"
                f"GET /api/v1/approvals/pending/{queue_id}"
            )

        else:
            return  # 'passed' e stati intermedi non generano notifiche

        notif_id = _write_notification(
            notification_type=notification_type,
            subject=subject,
            body=body,
            errata_id=errata_id,
            queue_id=queue_id,
            test_id=test_id,
        )

        logger.info(
            f"NotificationManager: {notification_type} id={notif_id} "
            f"for {errata_id!r} (test_id={test_id}, result={result!r})"
        )

    except Exception as e:
        logger.warning(f"NotificationManager: notify_test_result failed: {e}")
