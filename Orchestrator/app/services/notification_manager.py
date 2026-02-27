"""
SPM Orchestrator - Notification Manager

Scrive notifiche in orchestrator_notifications e opzionalmente le invia
via email (SMTP) o webhook (HTTP POST).

Usato dal Test Engine per segnalare all'operatore:
  test_failure     → test FAILED/ERROR su sistema test
  pending_approval → patch superata il test, in attesa di approvazione

Comportamento:
  - Scrive SEMPRE in orchestrator_notifications (delivered=False se invio
    non configurato) → la dashboard legge le notifiche non lette da qui.
  - Se email_enabled=True e recipients configurati → invia email SMTP.
  - Se webhook_enabled=True e webhook_url configurato → invia HTTP POST JSON.
  - Tutte le funzioni sono best-effort: non sollevano mai eccezioni.

Config letta da orchestrator_config['notification_config']:
  alert_on_test_failure    (bool, default True)
  alert_on_pending_approval (bool, default True)
  email_enabled            (bool, default False)
  smtp_server, smtp_port, smtp_tls, smtp_user, smtp_password
  from_address, recipients (list)
  webhook_enabled          (bool, default False)
  webhook_url, webhook_auth_header
"""

import json
import logging
import smtplib
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.services.db import get_db

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Config helper
# ─────────────────────────────────────────────

def _get_notification_config() -> dict:
    """Legge notification_config da orchestrator_config. Ritorna {} su errore."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT value FROM orchestrator_config WHERE key = 'notification_config'"
            )
            row = cur.fetchone()
            if row and isinstance(row["value"], dict):
                return row["value"]
    except Exception as e:
        logger.warning(f"NotificationManager: cannot load notification_config: {e}")
    return {}


# ─────────────────────────────────────────────
# DB write
# ─────────────────────────────────────────────

def _write_notification(
    notification_type: str,
    channel: str,
    recipient: str,
    subject: str,
    body: str,
    errata_id: Optional[str] = None,
    queue_id: Optional[int] = None,
    test_id: Optional[int] = None,
    delivered: bool = False,
    error_message: Optional[str] = None,
) -> Optional[int]:
    """Inserisce riga in orchestrator_notifications. Ritorna l'id o None su errore."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO orchestrator_notifications
                    (notification_type, errata_id, queue_id, test_id,
                     channel, recipient, subject, body,
                     delivered, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    notification_type, errata_id, queue_id, test_id,
                    channel, recipient, subject, body,
                    delivered, error_message,
                ),
            )
            return cur.fetchone()["id"]
    except Exception as e:
        logger.warning(f"NotificationManager: _write_notification failed: {e}")
        return None


# ─────────────────────────────────────────────
# Senders
# ─────────────────────────────────────────────

def _send_email(cfg: dict, subject: str, body: str) -> tuple:
    """
    Invia email via SMTP.
    Ritorna (success: bool, error_message: str).
    """
    try:
        recipients = cfg.get("recipients", [])
        if not recipients:
            return False, "no recipients configured"

        smtp_server = cfg.get("smtp_server", "")
        if not smtp_server:
            return False, "no smtp_server configured"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg.get("from_address", "spm@localhost")
        msg["To"]      = ", ".join(recipients)
        msg.attach(MIMEText(body, "plain", "utf-8"))

        port    = int(cfg.get("smtp_port", 587))
        use_tls = bool(cfg.get("smtp_tls", True))
        user    = cfg.get("smtp_user", "")
        pwd     = cfg.get("smtp_password", "")

        with smtplib.SMTP(smtp_server, port, timeout=10) as smtp:
            if use_tls:
                smtp.starttls()
            if user and pwd:
                smtp.login(user, pwd)
            smtp.sendmail(msg["From"], recipients, msg.as_string())

        return True, ""

    except Exception as e:
        return False, str(e)


def _send_webhook(cfg: dict, notification_type: str, subject: str, body: str) -> tuple:
    """
    Invia POST JSON al webhook configurato.
    Ritorna (success: bool, error_message: str).
    """
    try:
        url = cfg.get("webhook_url", "")
        if not url:
            return False, "no webhook_url configured"

        payload = json.dumps({
            "type":    notification_type,
            "subject": subject,
            "body":    body,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        auth_header = cfg.get("webhook_auth_header", "")
        if auth_header and ":" in auth_header:
            key, _, value = auth_header.partition(":")
            req.add_header(key.strip(), value.strip())

        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status < 300:
                return True, ""
            return False, f"HTTP {resp.status}"

    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

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
    Notifica l'operatore del risultato del test. Best-effort: non solleva mai.

    result='failed' / 'error'  → alert di fallimento (se alert_on_test_failure)
    result='pending_approval'  → avviso approvazione (se alert_on_pending_approval)
    Altri risultati             → ignorati silenziosamente
    """
    try:
        cfg = _get_notification_config()

        # ── Costruisce subject e body in base al risultato ────────────────
        if result in ("failed", "error"):
            if not cfg.get("alert_on_test_failure", True):
                return

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
                f"Consultare i log e verificare lo stato del sistema di test.\n"
                f"Dettagli: GET /api/v1/tests/{test_id}"
            )

        elif result == "pending_approval":
            if not cfg.get("alert_on_pending_approval", True):
                return

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
            return  # 'passed' e altri non generano notifiche

        # ── Email ─────────────────────────────────────────────────────────
        if cfg.get("email_enabled", False):
            recipients = cfg.get("recipients", [])
            if recipients:
                # Invia una sola email a tutti i destinatari, poi registra
                # una riga per destinatario (audit trail).
                ok, err = _send_email(cfg, subject, body)
                for recipient in recipients:
                    _write_notification(
                        notification_type=notification_type,
                        channel="email",
                        recipient=recipient,
                        subject=subject,
                        body=body,
                        errata_id=errata_id,
                        queue_id=queue_id,
                        test_id=test_id,
                        delivered=ok,
                        error_message=err if not ok else None,
                    )
                if not ok:
                    logger.warning(
                        f"NotificationManager: email send failed: {err}"
                    )
        else:
            # Email non configurata: scrivi solo in DB con delivered=False.
            # La dashboard legge le righe non consegnate come notifiche da mostrare.
            _write_notification(
                notification_type=notification_type,
                channel="email",
                recipient="operator",
                subject=subject,
                body=body,
                errata_id=errata_id,
                queue_id=queue_id,
                test_id=test_id,
                delivered=False,
            )

        # ── Webhook ───────────────────────────────────────────────────────
        if cfg.get("webhook_enabled", False):
            webhook_url = cfg.get("webhook_url", "")
            if webhook_url:
                ok, err = _send_webhook(cfg, notification_type, subject, body)
                _write_notification(
                    notification_type=notification_type,
                    channel="webhook",
                    recipient=webhook_url,
                    subject=subject,
                    body=body,
                    errata_id=errata_id,
                    queue_id=queue_id,
                    test_id=test_id,
                    delivered=ok,
                    error_message=err if not ok else None,
                )
                if not ok:
                    logger.warning(
                        f"NotificationManager: webhook failed: {err}"
                    )

        logger.info(
            f"NotificationManager: {notification_type} written "
            f"for {errata_id!r} (test_id={test_id}, result={result!r})"
        )

    except Exception as e:
        logger.warning(f"NotificationManager: notify_test_result failed: {e}")
