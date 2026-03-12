"""
SPM Orchestrator - Test Engine DB Helpers

Funzioni di accesso al database per il test engine.
Tutte le funzioni sono pure (nessuno stato globale) e usano
get_db() come context manager per la gestione delle connessioni.

Importato da:
  test_phases.py  — crea/aggiorna fasi e record test
  test_engine.py  — pick/update stato coda e operazioni batch DB
"""

import json
import logging
from datetime import datetime
from typing import Optional

from app.config import Config
from app.services.db import get_db

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Queue helpers
# ─────────────────────────────────────────────

def pick_next_queued() -> Optional[dict]:
    """
    Preleva il prossimo elemento in coda (status='queued' o 'retry_pending' pronto).
    Ordinamento: priority_override DESC, no-reboot prima, success_score DESC, queued_at ASC.
    FOR UPDATE OF q SKIP LOCKED: sicuro in caso di istanze concorrenti.
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                q.id, q.errata_id, q.target_os,
                q.success_score, q.priority_override, q.queued_at,
                COALESCE(rp.requires_reboot, FALSE) AS requires_reboot,
                COALESCE(rp.affects_kernel,  FALSE) AS affects_kernel,
                COALESCE(q.retry_count, 0)           AS retry_count
            FROM patch_test_queue q
            LEFT JOIN patch_risk_profile rp ON q.errata_id = rp.errata_id
            WHERE q.status = 'queued'
               OR (q.status = 'retry_pending' AND q.retry_after <= NOW())
            ORDER BY q.priority_override              DESC,
                     COALESCE(rp.requires_reboot, FALSE) ASC,
                     q.success_score                     DESC,
                     q.queued_at                         ASC
            LIMIT 1
            FOR UPDATE OF q SKIP LOCKED
        """)
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_queue_item(queue_id: int) -> Optional[dict]:
    """Legge un item dalla coda se in stato 'queued' o 'retry_pending' pronto."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                q.id, q.errata_id, q.target_os,
                q.success_score, q.priority_override, q.queued_at,
                COALESCE(rp.requires_reboot, FALSE) AS requires_reboot,
                COALESCE(rp.affects_kernel,  FALSE) AS affects_kernel,
                COALESCE(q.retry_count, 0)           AS retry_count
            FROM patch_test_queue q
            LEFT JOIN patch_risk_profile rp ON q.errata_id = rp.errata_id
            WHERE q.id = %s
              AND (q.status = 'queued'
                   OR (q.status = 'retry_pending' AND q.retry_after <= NOW()))
            """,
            (queue_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def set_queue_status(
    queue_id: int,
    status: str,
    test_id: int = None,
) -> None:
    """
    Aggiorna status in patch_test_queue.
    - 'testing': imposta started_at; se test_id fornito, aggiorna anche test_id FK.
    - stati finali ('passed','failed','pending_approval','rolled_back'): imposta
      completed_at; se test_id fornito, aggiorna anche test_id FK.
    - altri stati: aggiorna solo status.
    """
    with get_db() as conn:
        cur = conn.cursor()
        if status == "testing":
            if test_id is not None:
                cur.execute(
                    """UPDATE patch_test_queue
                       SET status = %s, test_id = %s, started_at = NOW()
                       WHERE id = %s""",
                    (status, test_id, queue_id),
                )
            else:
                cur.execute(
                    """UPDATE patch_test_queue
                       SET status = %s, started_at = NOW()
                       WHERE id = %s""",
                    (status, queue_id),
                )
        elif status in ("passed", "failed", "pending_approval", "rolled_back"):
            if test_id is not None:
                cur.execute(
                    """UPDATE patch_test_queue
                       SET status = %s, test_id = %s, completed_at = NOW()
                       WHERE id = %s""",
                    (status, test_id, queue_id),
                )
            else:
                cur.execute(
                    """UPDATE patch_test_queue
                       SET status = %s, completed_at = NOW()
                       WHERE id = %s""",
                    (status, queue_id),
                )
        else:
            cur.execute(
                "UPDATE patch_test_queue SET status = %s WHERE id = %s",
                (status, queue_id),
            )


def set_queue_retry(
    queue_id: int,
    retry_after: datetime,
    retry_count: int,
) -> None:
    """Imposta status='retry_pending', aggiorna retry_after e retry_count."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE patch_test_queue
               SET status      = 'retry_pending',
                   retry_after = %s,
                   retry_count = %s
               WHERE id = %s""",
            (retry_after, retry_count, queue_id),
        )


# ─────────────────────────────────────────────
# Test record helpers
# ─────────────────────────────────────────────

def create_test_record(
    queue_id: int,
    errata_id: str,
    system_id: Optional[int],
    system_name: str,
    system_ip: str,
    requires_reboot: bool,
) -> int:
    """Crea riga in patch_tests. Ritorna l'id generato."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO patch_tests (
                queue_id, errata_id,
                test_system_id, test_system_name, test_system_ip,
                snapshot_type, started_at, required_reboot
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
            RETURNING id
            """,
            (
                queue_id, errata_id,
                system_id, system_name, system_ip,
                Config.SNAPSHOT_TYPE, requires_reboot,
            ),
        )
        return cur.fetchone()["id"]


def update_test_record(test_id: int, **fields) -> None:
    """
    Aggiorna campi arbitrari in patch_tests.
    I campi JSONB vengono serializzati automaticamente;
    i campi TEXT[] vengono passati direttamente a psycopg2.
    """
    if not fields:
        return

    jsonb_fields = {
        "baseline_metrics", "post_patch_metrics",
        "metrics_delta", "metrics_evaluation", "test_config",
        "services_baseline", "services_post_patch",
    }
    array_fields = {
        "failed_services",  # TEXT[] nel DB
    }

    set_parts = []
    values = []

    for k, v in fields.items():
        if k in jsonb_fields:
            set_parts.append(f"{k} = %s::jsonb")
            values.append(json.dumps(v) if v is not None else None)
        elif k in array_fields:
            set_parts.append(f"{k} = %s")
            values.append(v)
        else:
            set_parts.append(f"{k} = %s")
            values.append(v)

    values.append(test_id)

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE patch_tests SET {', '.join(set_parts)} WHERE id = %s",
            values,
        )


# ─────────────────────────────────────────────
# Phase helpers
# ─────────────────────────────────────────────

def create_phase(test_id: int, phase_name: str) -> int:
    """Inserisce fase in patch_test_phases (status='in_progress'). Ritorna id."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO patch_test_phases (test_id, phase_name, status, started_at)
            VALUES (%s, %s, 'in_progress', NOW())
            RETURNING id
            """,
            (test_id, phase_name),
        )
        return cur.fetchone()["id"]


def complete_phase(
    phase_id: int,
    status: str,
    error: str = None,
    output: dict = None,
) -> None:
    """Chiude fase: imposta status, completed_at, duration, errore e output."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE patch_test_phases SET
                status           = %s,
                completed_at     = NOW(),
                duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER,
                error_message    = %s,
                output           = %s::jsonb
            WHERE id = %s
            """,
            (
                status,
                error,
                json.dumps(output) if output is not None else None,
                phase_id,
            ),
        )


# ─────────────────────────────────────────────
# Package helper
# ─────────────────────────────────────────────

def get_packages(errata_id: str) -> list:
    """
    Legge pacchetti da errata_cache.packages.
    Se vuoto (non ancora fetchati), li recupera on-demand da UYUNI.
    Ritorna [{name, version, size_kb}, ...]
    """
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
        logger.warning(f"TestEngine: DB read packages failed: {e}")

    logger.info(f"TestEngine: fetching packages for {errata_id!r} from UYUNI on-demand")
    from app.services.uyuni_client import get_errata_packages
    return get_errata_packages(errata_id)


# ─────────────────────────────────────────────
# Batch DB helpers
# ─────────────────────────────────────────────

def db_create_batch(
    batch_id: str, group_name: str, operator: str, total: int,
) -> None:
    """Crea riga in patch_test_batches."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO patch_test_batches
                    (batch_id, status, group_name, operator,
                     total, completed, passed, failed, results)
                VALUES (%s, 'running', %s, %s, %s, 0, 0, 0, '[]'::jsonb)
                """,
                (batch_id, group_name, operator, total),
            )
    except Exception as e:
        logger.warning(f"TestEngine: db_create_batch failed: {e}")


def db_update_batch(
    batch_id: str, completed: int, passed: int, failed: int, results: list,
) -> None:
    """Aggiorna progresso batch nel DB dopo ogni test."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE patch_test_batches
                SET completed = %s, passed = %s, failed = %s, results = %s::jsonb
                WHERE batch_id = %s
                """,
                (completed, passed, failed, json.dumps(results), batch_id),
            )
    except Exception as e:
        logger.warning(f"TestEngine: db_update_batch failed: {e}")


def db_complete_batch(
    batch_id: str, status: str, error: str = None,
) -> None:
    """Chiude il batch nel DB con status finale e timestamp."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE patch_test_batches
                SET status = %s, completed_at = NOW(), error_message = %s
                WHERE batch_id = %s
                """,
                (status, error, batch_id),
            )
    except Exception as e:
        logger.warning(f"TestEngine: db_complete_batch failed: {e}")


def db_get_batch(batch_id: str) -> Optional[dict]:
    """
    Legge batch dal DB. Ritorna None se non trovato.
    Usato come fallback da get_batch_status() quando il batch non è in memoria
    (es. dopo un restart Flask o per batch completati da più di 24h).
    """
    try:
        from app.utils.serializers import serialize_row
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT batch_id, status, group_name AS "group", operator,
                       total, completed, passed, failed, results,
                       started_at, completed_at, error_message AS error
                FROM patch_test_batches
                WHERE batch_id = %s
                """,
                (batch_id,),
            )
            row = cur.fetchone()
            return serialize_row(dict(row)) if row else None
    except Exception as e:
        logger.warning(f"TestEngine: db_get_batch failed: {e}")
    return None
