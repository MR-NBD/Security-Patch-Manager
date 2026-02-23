"""
SPM Orchestrator - Background Poller

APScheduler job che sincronizza errata_cache da UYUNI
ogni UYUNI_POLL_INTERVAL minuti (default 30).

Recupera solo le patch applicabili ai sistemi nei gruppi "test-*",
eliminando il download di decine di migliaia di errata irrilevanti.

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
from app.services import uyuni_client

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None

# Stato corrente (aggiornato dopo ogni run)
_state = {
    "last_sync":          None,   # datetime UTC
    "last_inserted":      0,
    "last_updated":       0,
    "last_errors":        0,
    "last_duration_s":    0.0,
    "last_error_msg":     None,
    "running":            False,
    "last_groups_found":  0,
}


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
                     'Ultimo sync UYUNI errata')
                ON CONFLICT (key) DO UPDATE SET
                    value      = EXCLUDED.value,
                    updated_at = NOW()
                """,
                (payload,),
            )
    except Exception as e:
        logger.warning(f"Could not save last sync time: {e}")


# ─────────────────────────────────────────────
# Build cache row da dati UYUNI
# ─────────────────────────────────────────────

def _parse_uyuni_date(date_val) -> Optional[str]:
    """
    Converte data UYUNI (datetime o string) in ISO 8601 UTC string.
    Ritorna None se non parsabile.
    """
    if not date_val:
        return None
    if isinstance(date_val, datetime):
        if date_val.tzinfo is None:
            date_val = date_val.replace(tzinfo=timezone.utc)
        return date_val.astimezone(timezone.utc).isoformat()
    if isinstance(date_val, str):
        try:
            dt = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except (ValueError, AttributeError):
            pass
    return None


def _build_cache_row(
    advisory_name: str,
    base: dict,
    details: dict,
    cves: list,
    target_os: str,
) -> dict:
    """
    Costruisce la riga errata_cache dai dati UYUNI.

    base: dict minimo da getRelevantErrata (advisory_name, advisory_type, synopsis, date)
    details: dict da errata.getDetails (description, issue_date, ecc.)
    """
    advisory_type = (
        base.get("advisory_type")
        or details.get("type", "")
    )
    synopsis = (
        base.get("synopsis")
        or details.get("synopsis", "")
    )
    description = details.get("description", "")
    issue_date = _parse_uyuni_date(
        details.get("issue_date") or base.get("date")
    )
    severity = uyuni_client._severity_from_advisory_type(advisory_type)

    return {
        "errata_id":   advisory_name,
        "synopsis":    synopsis,
        "description": description,
        "severity":    severity,
        "type":        advisory_type,
        "issued_date": issue_date,
        "target_os":   target_os,
        "packages":    [],   # fetchati on-demand al momento dell'accodamento
        "cves":        cves,
        "source_url":  None,
    }


# ─────────────────────────────────────────────
# Job principale
# ─────────────────────────────────────────────

def sync_errata_cache() -> dict:
    """
    Sincronizza errata da UYUNI → errata_cache (locale).

    Logica:
      1. Recupera gruppi test-* da UYUNI
      2. Per ogni gruppo → sistemi → errata applicabili
      3. Deduplica advisory_name (un errata può riguardare più sistemi)
      4. Per ogni errata unico → get details + CVEs → upsert cache

    Ritorna dict con statistiche del run.
    """
    global _state

    if _state["running"]:
        logger.warning("Sync already running, skipping")
        return {"status": "skipped", "reason": "already running"}

    _state["running"] = True
    started_at = datetime.now(timezone.utc)
    inserted = updated = errors = 0

    logger.info("UYUNI errata sync started")

    try:
        # 1. Recupera gruppi test-*
        try:
            groups = uyuni_client.get_test_groups()
        except Exception as e:
            logger.error(f"get_test_groups failed: {e}")
            _state["last_error_msg"] = str(e)
            return {"status": "error", "error": str(e)}

        _state["last_groups_found"] = len(groups)
        logger.info(
            f"UYUNI: {len(groups)} test groups found: "
            f"{[g.get('name') for g in groups]}"
        )

        if not groups:
            logger.warning(
                f"No groups with prefix "
                f"{Config.UYUNI_TEST_GROUP_PREFIX!r} found in UYUNI"
            )

        # 2. Accumula errata unici: advisory_name → {base, target_os}
        # advisory_name usato come chiave per deduplicare
        errata_map: dict = {}

        for group in groups:
            group_name = group.get("name", "")
            target_os = uyuni_client.os_from_group(group_name)

            try:
                systems = uyuni_client.get_systems_in_group(group_name)
            except Exception as e:
                logger.warning(
                    f"get_systems_in_group({group_name!r}) failed: {e}"
                )
                continue

            for system in systems:
                system_id = system.get("id")
                if not system_id:
                    continue

                errata_list = uyuni_client.get_relevant_errata(system_id)
                for e in errata_list:
                    name = e.get("advisory_name")
                    if not name or name in errata_map:
                        continue
                    errata_map[name] = {
                        "target_os": target_os,
                        "group":     group_name,
                        **e,
                    }

        logger.info(
            f"UYUNI: {len(errata_map)} unique relevant errata found"
        )

        # 3. Per ogni errata unico → dettagli + CVE → upsert
        for advisory_name, base in errata_map.items():
            try:
                details = uyuni_client.get_errata_details(advisory_name)
                cves = uyuni_client.get_errata_cves(advisory_name)
                row = _build_cache_row(
                    advisory_name,
                    base,
                    details,
                    cves,
                    base["target_os"],
                )
                outcome = _upsert(row)
                if outcome == "inserted":
                    inserted += 1
                else:
                    updated += 1
            except Exception as e:
                logger.warning(
                    f"Error processing {advisory_name!r}: {e}"
                )
                errors += 1

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
            f"UYUNI sync done: +{inserted} new, "
            f"~{updated} updated, {errors} errors "
            f"in {duration:.1f}s"
        )
        return {
            "status":           "success",
            "inserted":         inserted,
            "updated":          updated,
            "errors":           errors,
            "duration_seconds": round(duration, 1),
            "groups_found":     len(groups),
        }

    except Exception as e:
        _state["last_error_msg"] = str(e)
        logger.error(f"UYUNI sync failed: {e}")
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
        "scheduler_running":     (
            _scheduler.running if _scheduler else False
        ),
        "sync_running":          _state["running"],
        "poll_interval_minutes": Config.UYUNI_POLL_INTERVAL,
        "test_group_prefix":     Config.UYUNI_TEST_GROUP_PREFIX,
        "test_groups_found":     _state["last_groups_found"],
        "last_sync":             last.isoformat() if last else None,
        "last_inserted":         _state["last_inserted"],
        "last_updated":          _state["last_updated"],
        "last_errors":           _state["last_errors"],
        "last_duration_seconds": _state["last_duration_s"],
        "last_error":            _state["last_error_msg"],
    }


def trigger_sync() -> dict:
    """Trigger manuale del sync (per /api/v1/sync/trigger)."""
    logger.info("Manual UYUNI sync triggered via API")
    return sync_errata_cache()


# ─────────────────────────────────────────────
# Init scheduler
# ─────────────────────────────────────────────

def init_scheduler() -> None:
    """
    Avvia APScheduler con job periodico per il polling UYUNI.
    Esegue anche un sync iniziale 15 secondi dopo lo startup.
    """
    global _scheduler

    _scheduler = BackgroundScheduler(daemon=True, timezone="UTC")

    # Job periodico
    _scheduler.add_job(
        func=sync_errata_cache,
        trigger=IntervalTrigger(
            minutes=Config.UYUNI_POLL_INTERVAL
        ),
        id="uyuni_errata_poll",
        name="UYUNI Errata Poll",
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
        id="uyuni_errata_initial",
        name="UYUNI Initial Sync",
    )

    _scheduler.start()
    logger.info(
        f"Poller started: interval={Config.UYUNI_POLL_INTERVAL}m, "
        f"group_prefix={Config.UYUNI_TEST_GROUP_PREFIX!r}, "
        f"initial sync in ~15s"
    )
