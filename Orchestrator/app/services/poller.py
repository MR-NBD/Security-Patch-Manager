"""
SPM Orchestrator - Background Poller

APScheduler job che sincronizza errata_cache da UYUNI
ogni UYUNI_POLL_INTERVAL minuti (default 30).

Recupera solo le patch applicabili ai sistemi nei gruppi "test-*",
eliminando il download di decine di migliaia di errata irrilevanti.

Ottimizzazioni:
- Sessione singola (1 login/logout per ciclo)
- ThreadPoolExecutor per fetch parallelo di sistemi, errata e CVE
- execute_values per batch upsert in un'unica transazione DB

Stato globale: thread-safe, letto via get_sync_status().
"""

import calendar
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from psycopg2.extras import execute_values

from app.config import Config
from app.services.db import get_db
from app.services.uyuni_client import (
    UyuniSession,
    os_from_group,
    _severity_from_advisory_type,
)

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
# Date parsing
# ─────────────────────────────────────────────

def _parse_uyuni_date(date_val) -> Optional[str]:
    """
    Converte data UYUNI in ISO 8601 UTC string.

    Gestisce:
    - xmlrpc.client.DateTime  (ha .timetuple() ma non è un datetime)
    - datetime nativo
    - stringa ISO 8601
    Ritorna None se non parsabile.
    """
    if not date_val:
        return None
    # xmlrpc.client.DateTime ha .timetuple() ma non è un'istanza di datetime
    if hasattr(date_val, "timetuple") and not isinstance(date_val, datetime):
        ts = calendar.timegm(date_val.timetuple())
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
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


# ─────────────────────────────────────────────
# Build cache row (senza get_errata_details)
# ─────────────────────────────────────────────

def _build_cache_row(
    advisory_name: str,
    base: dict,
    cves: list,
    target_os: str,
) -> dict:
    """
    Costruisce la riga errata_cache dai dati UYUNI.

    base: dict da getRelevantErrata (advisory_name, advisory_type, synopsis, date)
    description = "" (fetchabile on-demand se necessario)
    """
    advisory_type = base.get("advisory_type", "")
    synopsis = base.get("synopsis", "")
    issue_date = _parse_uyuni_date(base.get("date"))
    severity = _severity_from_advisory_type(advisory_type)

    return {
        "errata_id":   advisory_name,
        "synopsis":    synopsis,
        "description": "",
        "severity":    severity,
        "type":        advisory_type,
        "issued_date": issue_date,
        "target_os":   target_os,
        "packages":    [],   # fetchati on-demand al momento dell'accodamento
        "cves":        cves,
        "source_url":  None,
    }


# ─────────────────────────────────────────────
# Batch upsert → errata_cache (execute_values)
# ─────────────────────────────────────────────

_BULK_SQL = """
    INSERT INTO errata_cache (
        errata_id, synopsis, description, severity,
        type, issued_date, target_os, packages,
        cves, source_url, synced_at, updated_at
    ) VALUES %s
    ON CONFLICT (errata_id) DO UPDATE SET
        synopsis     = EXCLUDED.synopsis,
        severity     = EXCLUDED.severity,
        type         = EXCLUDED.type,
        issued_date  = EXCLUDED.issued_date,
        target_os    = EXCLUDED.target_os,
        cves         = EXCLUDED.cves,
        source_url   = EXCLUDED.source_url,
        synced_at    = NOW(),
        updated_at   = NOW()
"""
# description non aggiornata in UPDATE: preserva descrizioni già fetchate

_TEMPLATE = "(%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, NOW(), NOW())"


def _batch_upsert(rows: list) -> tuple:
    """
    Inserisce/aggiorna righe in errata_cache in un'unica transazione.
    Ritorna (inserted, updated).
    """
    if not rows:
        return 0, 0

    ids = [r["errata_id"] for r in rows]
    values = [
        (
            r["errata_id"],
            r["synopsis"],
            r["description"],
            r["severity"],
            r["type"],
            r["issued_date"],
            r["target_os"],
            json.dumps(r.get("packages", [])),
            r["cves"],
            r["source_url"],
        )
        for r in rows
    ]

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) AS n FROM errata_cache WHERE errata_id = ANY(%s)",
            (ids,),
        )
        existing = cur.fetchone()["n"]
        execute_values(cur, _BULK_SQL, values, template=_TEMPLATE, page_size=200)

    inserted = len(rows) - existing
    updated = existing
    return inserted, updated


# ─────────────────────────────────────────────
# Persist last sync timestamp
# ─────────────────────────────────────────────

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
# Job principale (ottimizzato)
# ─────────────────────────────────────────────

def sync_errata_cache() -> dict:
    """
    Sincronizza errata da UYUNI → errata_cache (locale).

    Flusso ottimizzato:
      ① Una sessione UYUNI (1 login/logout totale)
      ② Fetch gruppi test-* → sistemi per gruppo (parallelo)
      ③ Fetch errata per sistema (parallelo) → dedup in errata_map
      ④ Fetch CVEs (parallelo, solo Security Advisory)
      ⑤ Build righe cache
      ⑥ Batch upsert in un'unica transazione DB
    """
    global _state

    if _state["running"]:
        logger.warning("Sync already running, skipping")
        return {"status": "skipped", "reason": "already running"}

    _state["running"] = True
    started_at = datetime.now(timezone.utc)
    workers = Config.UYUNI_SYNC_WORKERS

    logger.info("UYUNI errata sync started (optimized)")

    try:
        with UyuniSession() as session:

            # ① Recupera gruppi test-*
            try:
                groups = session.get_test_groups()
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

            # ② Fetch sistemi per gruppo (parallelo)
            def _fetch_systems(group):
                group_name = group.get("name", "")
                target_os = os_from_group(group_name)
                systems = session.get_systems_in_group(group_name)
                return group_name, target_os, systems

            group_systems: dict = {}  # group_name → (systems, target_os)
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(_fetch_systems, g): g for g in groups}
                for fut in as_completed(futs):
                    try:
                        gname, tos, syss = fut.result()
                        group_systems[gname] = (syss, tos)
                    except Exception as e:
                        logger.warning(f"get_systems_in_group failed: {e}")

            # ③ Fetch errata per sistema (parallelo) → dedup
            all_system_tasks = []
            for _gname, (systems, target_os) in group_systems.items():
                for sys in systems:
                    sid = sys.get("id")
                    if sid:
                        all_system_tasks.append((sid, target_os))

            def _fetch_errata(sid_tos):
                sid, tos = sid_tos
                return tos, session.get_relevant_errata(sid)

            errata_map: dict = {}  # advisory_name → {base, target_os, ...}
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(_fetch_errata, t): t for t in all_system_tasks}
                for fut in as_completed(futs):
                    try:
                        tos, errata_list = fut.result()
                        for e in errata_list:
                            name = e.get("advisory_name")
                            if name and name not in errata_map:
                                errata_map[name] = {"target_os": tos, **e}
                    except Exception as e:
                        logger.warning(f"get_relevant_errata failed: {e}")

            logger.info(
                f"UYUNI: {len(errata_map)} unique relevant errata found"
            )

            # ④ Fetch CVEs (parallelo, solo Security Advisory)
            security_names = [
                name for name, base in errata_map.items()
                if base.get("advisory_type", "") == "Security Advisory"
            ]

            def _fetch_cves(advisory_name):
                return advisory_name, session.get_errata_cves(advisory_name)

            cves_map: dict = {}  # advisory_name → ['CVE-...', ...]
            with ThreadPoolExecutor(max_workers=workers * 2) as ex:
                futs = {ex.submit(_fetch_cves, n): n for n in security_names}
                for fut in as_completed(futs):
                    try:
                        name, cves = fut.result()
                        cves_map[name] = cves
                    except Exception as e:
                        logger.warning(f"get_errata_cves failed: {e}")

        # Sessione chiusa (logout avvenuto)

        # ⑤ Build rows
        rows = []
        for advisory_name, base in errata_map.items():
            cves = cves_map.get(advisory_name, [])
            row = _build_cache_row(advisory_name, base, cves, base["target_os"])
            rows.append(row)

        # ⑥ Batch upsert
        inserted, updated = _batch_upsert(rows)

        duration = (datetime.now(timezone.utc) - started_at).total_seconds()
        now = datetime.now(timezone.utc)

        _state.update({
            "last_sync":       now,
            "last_inserted":   inserted,
            "last_updated":    updated,
            "last_errors":     0,
            "last_duration_s": round(duration, 1),
            "last_error_msg":  None,
        })
        _save_last_sync(now)

        logger.info(
            f"UYUNI sync done: +{inserted} new, "
            f"~{updated} updated in {duration:.1f}s"
        )
        return {
            "status":           "success",
            "inserted":         inserted,
            "updated":          updated,
            "errors":           0,
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
        f"workers={Config.UYUNI_SYNC_WORKERS}, "
        f"initial sync in ~15s"
    )
