"""
SPM Orchestrator - Background Poller

APScheduler job che sincronizza errata_cache da SPM-SYNC
ogni SPM_SYNC_POLL_INTERVAL minuti (default 30).

Stato globale: thread-safe, letto via get_sync_status().
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import Config
from app.services.db import get_db
import app.services.spm_sync_client as spm_client

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None

# Stato corrente (aggiornato dopo ogni run)
_state = {
    "last_sync":       None,   # datetime UTC
    "last_inserted":   0,
    "last_updated":    0,
    "last_errors":     0,
    "last_duration_s": 0.0,
    "last_error_msg":  None,
    "running":         False,
}

_BATCH = 200  # errata per richiesta a SPM-SYNC


# ─────────────────────────────────────────────
# Upsert singolo errata → errata_cache
# ─────────────────────────────────────────────

_UPSERT_SQL = """
    INSERT INTO errata_cache (
        errata_id, synopsis, description, severity,
        type, issued_date, target_os, packages,
        cves, source_url, synced_at, updated_at
    ) VALUES (
        %(errata_id)s, %(synopsis)s, %(description)s,
        %(severity)s, %(type)s, %(issued_date)s,
        %(target_os)s, %(packages)s::jsonb,
        %(cves)s, %(source_url)s, NOW(), NOW()
    )
    ON CONFLICT (errata_id) DO UPDATE SET
        synopsis     = EXCLUDED.synopsis,
        description  = EXCLUDED.description,
        severity     = EXCLUDED.severity,
        type         = EXCLUDED.type,
        issued_date  = EXCLUDED.issued_date,
        target_os    = EXCLUDED.target_os,
        packages     = EXCLUDED.packages,
        cves         = EXCLUDED.cves,
        source_url   = EXCLUDED.source_url,
        synced_at    = NOW(),
        updated_at   = NOW()
    RETURNING (xmax = 0) AS is_insert
"""


def _upsert(row: dict) -> str:
    """
    Inserisce o aggiorna una riga in errata_cache.
    Ritorna 'inserted' oppure 'updated'.
    """
    params = dict(row)
    params["packages"] = json.dumps(row.get("packages", []))

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(_UPSERT_SQL, params)
        result = cur.fetchone()

    return "inserted" if result and result["is_insert"] else "updated"


def _save_last_sync(ts: datetime) -> None:
    """Persiste timestamp ultimo sync in orchestrator_config."""
    payload = json.dumps({"timestamp": ts.isoformat()})
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO orchestrator_config
                    (key, value, description)
                VALUES
                    ('spm_sync_last_run', %s::jsonb,
                     'Ultimo sync SPM-SYNC')
                ON CONFLICT (key) DO UPDATE SET
                    value      = EXCLUDED.value,
                    updated_at = NOW()
                """,
                (payload,),
            )
    except Exception as e:
        logger.warning(f"Could not save last sync time: {e}")


# ─────────────────────────────────────────────
# Job principale
# ─────────────────────────────────────────────

def sync_errata_cache() -> dict:
    """
    Sincronizza errata da SPM-SYNC → errata_cache (locale).

    Paginazione: BATCH errata per volta fino all'esaurimento.
    Per ogni errata recupera anche i pacchetti (best-effort).
    Ritorna dict con statistiche del run.
    """
    global _state

    if _state["running"]:
        logger.warning("Sync already running, skipping")
        return {"status": "skipped", "reason": "already running"}

    _state["running"] = True
    started_at = datetime.now(timezone.utc)
    inserted = updated = errors = 0
    offset = 0

    logger.info("SPM-SYNC poll started")

    try:
        while True:
            try:
                batch, raw_count = spm_client.fetch_errata(
                    min_severity=Config.SPM_SYNC_MIN_SEVERITY,
                    limit=_BATCH,
                    offset=offset,
                )
            except Exception as e:
                logger.error(f"fetch_errata failed: {e}")
                _state["last_error_msg"] = str(e)
                break

            if raw_count == 0:
                break

            for errata in batch:
                advisory_id = errata.get("advisory_id")
                if not advisory_id:
                    continue
                try:
                    # Packages fetched on-demand at queue time,
                    # not here (87k errata × N+1 = hours)
                    row = spm_client.build_cache_row(errata, [])
                    outcome = _upsert(row)
                    if outcome == "inserted":
                        inserted += 1
                    else:
                        updated += 1
                except Exception as e:
                    logger.warning(
                        f"Error processing {advisory_id}: {e}"
                    )
                    errors += 1

            # Use raw_count (not filtered) to decide if there are more pages
            if raw_count < _BATCH:
                break
            offset += _BATCH

        duration = (
            datetime.now(timezone.utc) - started_at
        ).total_seconds()

        now = datetime.now(timezone.utc)
        _state.update({
            "last_sync":       now,
            "last_inserted":   inserted,
            "last_updated":    updated,
            "last_errors":     errors,
            "last_duration_s": round(duration, 1),
            "last_error_msg":  None,
        })
        _save_last_sync(now)

        logger.info(
            f"SPM-SYNC poll done: +{inserted} new, "
            f"~{updated} updated, {errors} errors "
            f"in {duration:.1f}s"
        )
        return {
            "status":           "success",
            "inserted":         inserted,
            "updated":          updated,
            "errors":           errors,
            "duration_seconds": round(duration, 1),
        }

    except Exception as e:
        _state["last_error_msg"] = str(e)
        logger.error(f"SPM-SYNC poll failed: {e}")
        return {"status": "error", "error": str(e)}

    finally:
        _state["running"] = False


# ─────────────────────────────────────────────
# API: stato e trigger manuale
# ─────────────────────────────────────────────

def get_sync_status() -> dict:
    """Ritorna stato corrente del poller (per /api/v1/sync/status)."""
    last = _state["last_sync"]
    return {
        "scheduler_running":    (
            _scheduler.running if _scheduler else False
        ),
        "sync_running":         _state["running"],
        "poll_interval_minutes": Config.SPM_SYNC_POLL_INTERVAL,
        "min_severity":         Config.SPM_SYNC_MIN_SEVERITY,
        "last_sync":            last.isoformat() if last else None,
        "last_inserted":        _state["last_inserted"],
        "last_updated":         _state["last_updated"],
        "last_errors":          _state["last_errors"],
        "last_duration_seconds": _state["last_duration_s"],
        "last_error":           _state["last_error_msg"],
    }


def trigger_sync() -> dict:
    """Trigger manuale del sync (per /api/v1/sync/trigger)."""
    logger.info("Manual SPM-SYNC sync triggered via API")
    return sync_errata_cache()


# ─────────────────────────────────────────────
# Init scheduler
# ─────────────────────────────────────────────

def init_scheduler() -> None:
    """
    Avvia APScheduler con job periodico per il polling.
    Esegue anche un sync iniziale 15 secondi dopo lo startup.
    """
    global _scheduler

    _scheduler = BackgroundScheduler(daemon=True, timezone="UTC")

    # Job periodico
    _scheduler.add_job(
        func=sync_errata_cache,
        trigger=IntervalTrigger(
            minutes=Config.SPM_SYNC_POLL_INTERVAL
        ),
        id="spm_sync_poll",
        name="SPM-SYNC Errata Poll",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    # Sync iniziale dopo 15s (non blocca lo startup Flask)
    _scheduler.add_job(
        func=sync_errata_cache,
        trigger="date",
        run_date=datetime.now(timezone.utc).replace(
            second=datetime.now(timezone.utc).second + 15
        ),
        id="spm_sync_initial",
        name="SPM-SYNC Initial Sync",
    )

    _scheduler.start()
    logger.info(
        f"Poller started: interval={Config.SPM_SYNC_POLL_INTERVAL}m, "
        f"min_severity={Config.SPM_SYNC_MIN_SEVERITY}, "
        f"initial sync in ~15s"
    )
