"""
SPM Orchestrator - Notification Manager

Scrive notifiche in orchestrator_notifications e opzionalmente le invia
via email (SMTP) o webhook (HTTP POST).

Usato dal Test Engine per segnalare all'operatore:
  test_failure     → test FAILED/ERROR su sistema test
  pending_approval → patch superata il test, in attesa di approvazione

Comportamento:
  - Scrive SEMPRE 1 riga in orchestrator_notifications per evento.
  - delivered=True  → email/webhook inviati con successo (nessun banner)
  - delivered=False → canale non configurato o invio fallito → banner dashboard
  - Se email_enabled=True: invia a tutti i destinatari in una sola chiamata SMTP.
  - Se webhook_enabled=True: invia HTTP POST JSON.
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
    Invia email via SMTP a tutti i destinatari configurati in una sola chiamata.
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

    Scrive SEMPRE 1 riga in orchestrator_notifications per evento:
      - delivered=True  → email/webhook inviati OK (nessun banner dashboard)
      - delivered=False → canale assente o invio fallito → banner dashboard
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

        # ── Invio canali (best-effort) ────────────────────────────────────
        email_ok    = False
        email_err   = ""
        webhook_ok  = False
        webhook_err = ""

        if cfg.get("email_enabled", False):
            email_ok, email_err = _send_email(cfg, subject, body)
            if not email_ok:
                logger.warning(f"NotificationManager: email send failed: {email_err}")

        if cfg.get("webhook_enabled", False) and cfg.get("webhook_url"):
            webhook_ok, webhook_err = _send_webhook(cfg, notification_type, subject, body)
            if not webhook_ok:
                logger.warning(f"NotificationManager: webhook failed: {webhook_err}")

        # ── 1 record DB per evento ────────────────────────────────────────
        # Determina canale principale e se la notifica è stata consegnata.
        # delivered=False → il banner appare nella dashboard (fallback visibile).
        if cfg.get("email_enabled", False):
            channel   = "email"
            delivered = email_ok
            err_msg   = email_err if not email_ok else None
        elif cfg.get("webhook_enabled", False):
            channel   = "webhook"
            delivered = webhook_ok
            err_msg   = webhook_err if not webhook_ok else None
        else:
            channel   = "dashboard"
            delivered = False
            err_msg   = None

        recipients = cfg.get("recipients", [])
        recipient_str = ", ".join(recipients) if recipients else "operator"

        _write_notification(
            notification_type=notification_type,
            channel=channel,
            recipient=recipient_str,
            subject=subject,
            body=body,
            errata_id=errata_id,
            queue_id=queue_id,
            test_id=test_id,
            delivered=delivered,
            error_message=err_msg,
        )

        logger.info(
            f"NotificationManager: {notification_type} written "
            f"for {errata_id!r} (test_id={test_id}, result={result!r}, "
            f"channel={channel!r}, delivered={delivered})"
        )

    except Exception as e:
        logger.warning(f"NotificationManager: notify_test_result failed: {e}")
