"""
SPM Orchestrator - Test Engine

Esegue test automatici sulle patch in coda (status='queued').
Un test alla volta — mutex globale _testing.

Flusso a fasi:
  ① snapshot  — crea snapshot pre-patch via snapper (UYUNI scheduleScriptRun)
  ② patch     — applica errata via UYUNI scheduleApplyErrata
  ③ reboot    — riavvio + attesa online (solo se requires_reboot=True)
  ④ validate  — verifica delta CPU/memoria via Prometheus
  ⑤ services  — verifica servizi critici via UYUNI scheduleScriptRun (systemctl)
  ↓ (fallimento in qualsiasi fase)
  ⑥ rollback  — snapshot: snapper undochange | package: apt downgrade

Ogni fase è registrata in patch_test_phases.
Il risultato finale aggiorna patch_tests e patch_test_queue.

Rollback type:
  requires_reboot = True  → snapshot (snapper undochange, senza reboot)
  requires_reboot = False → package (reinstalla versioni precedenti)
"""

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.config import Config
from app.services.db import get_db
from app.services.uyuni_patch_client import (
    UyuniPatchClient, get_critical_services, get_test_system_for_os,
)
from app.services.prometheus_client import PrometheusClient
from app.services.notification_manager import notify_test_result

logger = logging.getLogger(__name__)

# ── Stato globale ────────────────────────────────────────────────
_testing: bool = False
_testing_lock = threading.Lock()
_last_result: Optional[dict] = None

# ── Stato batch asincroni ────────────────────────────────────────
_batches: dict = {}           # batch_id → stato corrente
_batches_lock = threading.Lock()


# ─────────────────────────────────────────────
# DB Helpers
# ─────────────────────────────────────────────

def _pick_next_queued() -> Optional[dict]:
    """
    Preleva il prossimo elemento in coda (status='queued').
    Ordinamento: priority_override DESC, success_score DESC, queued_at ASC.
    FOR UPDATE SKIP LOCKED: sicuro in caso di istanze concorrenti.
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                q.id, q.errata_id, q.target_os,
                q.success_score, q.priority_override, q.queued_at,
                COALESCE(rp.requires_reboot, FALSE) AS requires_reboot,
                COALESCE(rp.affects_kernel,  FALSE) AS affects_kernel
            FROM patch_test_queue q
            LEFT JOIN patch_risk_profile rp ON q.errata_id = rp.errata_id
            WHERE q.status = 'queued'
            ORDER BY q.priority_override DESC, q.success_score DESC, q.queued_at ASC
            LIMIT 1
            FOR UPDATE OF q SKIP LOCKED
        """)
        row = cur.fetchone()
        return dict(row) if row else None


def _set_queue_status(
    queue_id: int,
    status: str,
    test_id: int = None,
) -> None:
    """Aggiorna status in patch_test_queue. Se test_id fornito, lo collega."""
    with get_db() as conn:
        cur = conn.cursor()
        if test_id is not None:
            cur.execute(
                """UPDATE patch_test_queue
                   SET status = %s, test_id = %s, started_at = NOW()
                   WHERE id = %s""",
                (status, test_id, queue_id),
            )
        elif status in ("passed", "failed", "pending_approval"):
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


def _create_test_record(
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


def _update_test_record(test_id: int, **fields) -> None:
    """Aggiorna campi arbitrari in patch_tests. dict/list → JSONB."""
    if not fields:
        return

    jsonb_fields = {
        "baseline_metrics", "post_patch_metrics",
        "metrics_delta", "metrics_evaluation", "test_config",
        "services_baseline", "services_post_patch",  # JSONB nel DB
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
            values.append(v)  # psycopg2 converte list → text[]
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


def _create_phase(test_id: int, phase_name: str) -> int:
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


def _complete_phase(
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

def _get_packages(errata_id: str) -> list:
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
# Phase executors
# ─────────────────────────────────────────────

def _phase_snapshot(
    test_id: int,
    uyuni: UyuniPatchClient,
    errata_id: str,
) -> str:
    """
    Fase SNAPSHOT: crea snapshot pre-patch via snapper (UYUNI scheduleScriptRun).
    Ritorna snapshot_id (numero snapper come stringa).
    Raises: RuntimeError se fallisce.
    """
    phase_id = _create_phase(test_id, "snapshot")
    try:
        desc = f"spm-pre-{errata_id}"
        snapshot_id = uyuni.take_snapshot(desc)

        _complete_phase(phase_id, "completed", output={"snapshot_id": snapshot_id})
        _update_test_record(test_id, snapshot_id=snapshot_id)
        logger.info(
            f"TestEngine: snapshot #{snapshot_id} created on {uyuni._system_name!r}"
        )
        return snapshot_id

    except Exception as e:
        _complete_phase(phase_id, "failed", error=str(e))
        raise RuntimeError(f"Snapshot failed: {e}") from e


def _phase_patch(
    test_id: int,
    uyuni: UyuniPatchClient,
    errata_id: str,
    pkg_names: list,
) -> dict:
    """
    Fase PATCH: applica errata via UYUNI scheduleApplyErrata.
    Ritorna {pkg_name: {old: "", new: "patched"}} per compatibilità rollback.
    Raises: RuntimeError se fallisce.
    """
    phase_id = _create_phase(test_id, "patch")
    try:
        result = uyuni.apply_errata(errata_id, pkg_names)
        _complete_phase(
            phase_id, "completed",
            output={"packages_applied": result, "count": len(result)},
        )
        return result if isinstance(result, dict) else {}

    except Exception as e:
        _complete_phase(phase_id, "failed", error=str(e))
        raise RuntimeError(f"Patch failed: {e}") from e


def _phase_reboot(
    test_id: int,
    uyuni: UyuniPatchClient,
) -> None:
    """
    Fase REBOOT: riavvio tramite UYUNI scheduleReboot + attesa online.
    Raises: RuntimeError se il sistema non torna online.
    """
    phase_id = _create_phase(test_id, "reboot")
    try:
        uyuni.reboot()
        online = uyuni.wait_online(timeout=Config.TEST_WAIT_AFTER_REBOOT)
        if not online:
            raise RuntimeError(
                f"System {uyuni._system_name!r} did not come back online "
                f"within {Config.TEST_WAIT_AFTER_REBOOT}s"
            )
        _complete_phase(phase_id, "completed", output={"reboot_successful": True})
        _update_test_record(test_id, reboot_performed=True, reboot_successful=True)

    except Exception as e:
        _complete_phase(phase_id, "failed", error=str(e))
        _update_test_record(test_id, reboot_performed=True, reboot_successful=False)
        raise RuntimeError(f"Reboot failed: {e}") from e


def _phase_validate(
    test_id: int,
    prom: PrometheusClient,
    system_ip: str,
    baseline: dict,
) -> None:
    """
    Fase VALIDATE: confronta metriche post-patch vs baseline.
    Skipped (senza errore) se Prometheus non disponibile.
    Raises: RuntimeError se delta supera threshold.
    """
    phase_id = _create_phase(test_id, "validate")
    try:
        post = prom.get_snapshot(system_ip)
        evaluation = prom.evaluate_delta(baseline, post)

        _update_test_record(
            test_id,
            post_patch_metrics=post,
            metrics_delta={
                "cpu_delta":    evaluation.get("cpu_delta"),
                "memory_delta": evaluation.get("memory_delta"),
            },
            metrics_evaluation=evaluation,
        )

        if evaluation.get("skipped"):
            _complete_phase(phase_id, "skipped", output=evaluation)
        elif evaluation.get("passed"):
            _complete_phase(phase_id, "completed", output=evaluation)
        else:
            err = (
                f"Delta exceeded threshold — "
                f"CPU Δ={evaluation.get('cpu_delta')}% "
                f"(limit={Config.TEST_CPU_DELTA}%), "
                f"MEM Δ={evaluation.get('memory_delta')}% "
                f"(limit={Config.TEST_MEMORY_DELTA}%)"
            )
            _complete_phase(phase_id, "failed", error=err, output=evaluation)
            raise RuntimeError(err)

    except RuntimeError:
        raise
    except Exception as e:
        _complete_phase(phase_id, "failed", error=str(e))
        raise RuntimeError(f"Validate failed: {e}") from e


def _phase_services(
    test_id: int,
    uyuni: UyuniPatchClient,
    target_os: str,
) -> None:
    """
    Fase SERVICES: verifica servizi critici post-patch via systemctl script.
    Retry 6x20s per tollerare servizi in riavvio (es. openssh-server dopo patch).
    Raises: RuntimeError se uno o piu' servizi sono DOWN dopo tutti i tentativi.
    """
    _SERVICE_RETRIES    = 6
    _SERVICE_RETRY_WAIT = 20  # secondi tra tentativi (totale max ~2 min)

    phase_id = _create_phase(test_id, "services")
    try:
        services = get_critical_services(target_os)
        failed = []

        for attempt in range(1, _SERVICE_RETRIES + 1):
            failed = uyuni.get_failed_services(services)
            if not failed:
                break
            if attempt < _SERVICE_RETRIES:
                logger.info(
                    f"TestEngine: services check attempt {attempt}/{_SERVICE_RETRIES} — "
                    f"DOWN: {failed} — retrying in {_SERVICE_RETRY_WAIT}s"
                )
                time.sleep(_SERVICE_RETRY_WAIT)

        _update_test_record(
            test_id,
            services_baseline=services,
            services_post_patch=services,
            failed_services=failed,
        )

        if failed:
            err = f"Critical services DOWN after patch: {', '.join(failed)}"
            _complete_phase(
                phase_id, "failed", error=err,
                output={"checked": services, "failed": failed},
            )
            raise RuntimeError(err)

        _complete_phase(
            phase_id, "completed",
            output={"checked": services, "all_ok": True},
        )

    except RuntimeError:
        raise
    except Exception as e:
        _complete_phase(phase_id, "failed", error=str(e))
        raise RuntimeError(f"Services check failed: {e}") from e


def _phase_rollback(
    test_id: int,
    uyuni: UyuniPatchClient,
    rollback_type: str,
    snapshot_id: Optional[str],
    packages_before: dict,
) -> None:
    """
    Fase ROLLBACK: ripristina sistema allo stato pre-patch via UYUNI.

    rollback_type='snapshot' → snapper undochange (via scheduleScriptRun)
    rollback_type='package'  → apt downgrade versioni precedenti

    Non solleva eccezioni: il fallimento del rollback viene solo loggato.
    """
    phase_id = _create_phase(test_id, "rollback")
    system_name = uyuni._system_name
    try:
        if rollback_type == "snapshot" and snapshot_id:
            uyuni.rollback_snapshot(snapshot_id)
            logger.info(
                f"TestEngine: snapshot rollback (#{snapshot_id}) on {system_name!r}"
            )

        elif rollback_type == "package" and packages_before:
            uyuni.rollback_packages(packages_before)
            logger.info(
                f"TestEngine: package rollback on {system_name!r}"
            )

        else:
            logger.warning(
                f"TestEngine: rollback skipped "
                f"(type={rollback_type!r}, snapshot_id={snapshot_id!r})"
            )

        _complete_phase(
            phase_id, "completed",
            output={"rollback_type": rollback_type, "snapshot_id": snapshot_id},
        )
        _update_test_record(
            test_id,
            rollback_performed=True,
            rollback_type=rollback_type,
            rollback_at=datetime.now(timezone.utc),
        )

    except Exception as e:
        # Rollback fallito: registra ma non blocca il flusso
        _complete_phase(phase_id, "failed", error=str(e))
        logger.error(f"TestEngine: ROLLBACK FAILED on {system_name!r}: {e}")


# ─────────────────────────────────────────────
# Core test execution
# ─────────────────────────────────────────────

def _execute_test(queue_item: dict) -> dict:
    """
    Esegue il test completo per un elemento della coda.
    Gestisce il flusso a fasi con rollback automatico in caso di fallimento.
    """
    queue_id       = queue_item["id"]
    errata_id      = queue_item["errata_id"]
    target_os      = queue_item["target_os"]
    requires_reboot = bool(queue_item.get("requires_reboot", False))

    # Sistema di test: .env ha priorità, altrimenti auto-discovery da UYUNI
    cfg         = Config.TEST_SYSTEMS.get(target_os, {})
    system_id   = cfg.get("system_id")
    system_name = cfg.get("system_name", "")
    system_ip   = cfg.get("system_ip", "")

    if not system_id or not system_name or not system_ip:
        # Auto-discovery: interroga UYUNI per sistemi nel gruppo test-{os}
        # Triggered anche quando manca solo system_ip (necessario per Prometheus)
        discovered = get_test_system_for_os(target_os)
        if discovered:
            system_id   = system_id   or discovered["system_id"]
            system_name = system_name or discovered["system_name"]
            system_ip   = system_ip   or discovered["system_ip"]
        else:
            err = (
                f"No test system found for target_os={target_os!r} — "
                f"nessun sistema nel gruppo UYUNI 'test-{target_os}*' "
                f"e nessuna configurazione in .env"
            )
            logger.error(f"TestEngine: {err}")
            return {"status": "error", "error": err, "queue_id": queue_id}

    # Tipo di rollback in base al profilo rischio
    rollback_type = "snapshot" if requires_reboot else "package"

    # Pacchetti da applicare
    packages  = _get_packages(errata_id)
    pkg_names = [p["name"] for p in packages if p.get("name")]

    if not pkg_names:
        logger.warning(
            f"TestEngine: no packages found for {errata_id!r} — proceeding without pkg list"
        )

    # Crea record test e aggancia alla coda
    test_id = _create_test_record(
        queue_id, errata_id, system_id, system_name, system_ip, requires_reboot,
    )
    _set_queue_status(queue_id, "testing", test_id=test_id)

    started_at      = datetime.now(timezone.utc)
    snapshot_id     = None
    apply_result    = {}
    failure_reason  = None
    failure_phase   = None
    rollback_done   = False
    final_result    = "error"

    logger.info(
        f"TestEngine: START {errata_id!r} | OS={target_os} | "
        f"system={system_name!r} | reboot={requires_reboot} | "
        f"packages={len(pkg_names)}"
    )

    try:
        with UyuniPatchClient(system_id, system_name) as uyuni:
            prom = PrometheusClient()

            # Verifica sistema raggiungibile prima di partire
            if not uyuni.ping():
                failure_reason = (
                    f"System {system_name!r} (id={system_id}) "
                    f"not reachable via UYUNI"
                )
                failure_phase = "pre_check"
                raise RuntimeError(failure_reason)

            # ① SNAPSHOT
            # Best-effort: se snapper non disponibile (es. Ubuntu 24.04) si
            # passa automaticamente a package rollback, anche per patch kernel.
            try:
                snapshot_id = _phase_snapshot(test_id, uyuni, errata_id)
            except RuntimeError as e:
                logger.warning(
                    f"TestEngine: snapshot failed (snapper not available?), "
                    f"switching to package rollback: {e}"
                )
                rollback_type = "package"

            # Assicura node_exporter installato e attivo (via UYUNI channels)
            # Best-effort: se fallisce, le metriche Prometheus vengono saltate
            # ma il test continua normalmente.
            if system_ip:
                uyuni.ensure_node_exporter(target_os)

            # Baseline metriche (best-effort, Prometheus opzionale)
            baseline_metrics = {}
            if system_ip and prom.is_available():
                baseline_metrics = prom.get_snapshot(system_ip)
                _update_test_record(test_id, baseline_metrics=baseline_metrics)

            # ② PATCH
            try:
                apply_result = _phase_patch(test_id, uyuni, errata_id, pkg_names)
            except RuntimeError as e:
                failure_reason = str(e)
                failure_phase  = "patch"
                _phase_rollback(
                    test_id, uyuni,
                    rollback_type, snapshot_id, apply_result,
                )
                rollback_done = True
                raise

            # ③ REBOOT (solo se requires_reboot)
            if requires_reboot:
                try:
                    _phase_reboot(test_id, uyuni)
                except RuntimeError as e:
                    failure_reason = str(e)
                    failure_phase  = "reboot"
                    _phase_rollback(
                        test_id, uyuni,
                        rollback_type, snapshot_id, apply_result,
                    )
                    rollback_done = True
                    raise
            else:
                # Attesa stabilizzazione post-patch senza reboot
                wait = Config.TEST_WAIT_AFTER_PATCH
                logger.info(
                    f"TestEngine: waiting {wait}s for system to stabilize"
                )
                time.sleep(wait)

            # ④ VALIDATE metriche
            if system_ip and baseline_metrics and prom.is_available():
                try:
                    _phase_validate(test_id, prom, system_ip, baseline_metrics)
                except RuntimeError as e:
                    failure_reason = str(e)
                    failure_phase  = "validate"
                    _phase_rollback(
                        test_id, uyuni,
                        rollback_type, snapshot_id, apply_result,
                    )
                    rollback_done = True
                    raise

            # ⑤ SERVICES
            try:
                _phase_services(test_id, uyuni, target_os)
            except RuntimeError as e:
                failure_reason = str(e)
                failure_phase  = "services"
                _phase_rollback(
                    test_id, uyuni,
                    rollback_type, snapshot_id, apply_result,
                )
                rollback_done = True
                raise

            # ✓ Tutte le fasi superate → in attesa di approvazione operatore
            final_result = "pending_approval"

    except RuntimeError:
        final_result = "failed"
    except Exception as e:
        failure_reason = f"Unexpected error: {e}"
        failure_phase  = "unknown"
        final_result   = "error"
        logger.exception(f"TestEngine: unexpected error for {errata_id!r}")

    # Finalizza record test
    completed_at = datetime.now(timezone.utc)
    duration_s   = int((completed_at - started_at).total_seconds())

    # patch_tests.result ammette solo: NULL, 'passed', 'failed', 'error', 'aborted'
    # 'pending_approval' è lo status della queue, non del test record
    test_result = "passed" if final_result == "pending_approval" else final_result

    _update_test_record(
        test_id,
        result             = test_result,
        failure_reason     = failure_reason,
        failure_phase      = failure_phase,
        rollback_performed = rollback_done,
        completed_at       = completed_at,
        duration_seconds   = duration_s,
    )
    # patch_test_queue.chk_queue_status non ammette 'error': mappa a 'failed'
    queue_status = "failed" if final_result == "error" else final_result
    _set_queue_status(queue_id, queue_status)

    # Notifica operatore (best-effort: failed/error → alert, pending_approval → info)
    notify_test_result(
        test_id       = test_id,
        queue_id      = queue_id,
        errata_id     = errata_id,
        result        = final_result,
        failure_phase = failure_phase,
        failure_reason= failure_reason,
        system_name   = system_name,
        duration_s    = duration_s,
    )

    logger.info(
        f"TestEngine: END {errata_id!r} → {final_result.upper()} "
        f"({duration_s}s | rollback={rollback_done} | failure_phase={failure_phase})"
    )

    return {
        "status":         final_result,
        "test_id":        test_id,
        "queue_id":       queue_id,
        "errata_id":      errata_id,
        "duration_s":     duration_s,
        "rollback":       rollback_done,
        "failure_reason": failure_reason,
        "failure_phase":  failure_phase,
    }


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def run_next_test() -> dict:
    """
    Entry point pubblico: esegue il prossimo test in coda.
    Ritorna immediatamente se un test è già in corso o la coda è vuota.
    Thread-safe: usa _testing_lock per prevenire esecuzioni concorrenti
    (es. scheduler + trigger manuale API simultanei).
    """
    global _testing, _last_result

    with _testing_lock:
        if _testing:
            return {"status": "skipped", "reason": "test already running"}

        item = _pick_next_queued()
        if not item:
            return {"status": "skipped", "reason": "no items in queue"}

        _testing = True

    try:
        result = _execute_test(item)
        _last_result = result
        return result
    finally:
        with _testing_lock:
            _testing = False


def get_engine_status() -> dict:
    """Stato corrente del Test Engine (per /api/v1/tests/status)."""
    return {
        "testing":     _testing,
        "last_result": _last_result,
    }


def _add_batch_note(group_name: str, results: list, operator: str) -> None:
    """
    Aggiunge nota di riepilogo batch su TUTTI i sistemi del gruppo UYUNI.
    Best-effort: non blocca il flusso anche se fallisce.
    """
    from datetime import date
    from app.services.uyuni_client import UyuniSession

    try:
        today   = date.today().isoformat()
        passed  = sum(1 for r in results if r.get("status") == "pending_approval")
        failed  = sum(1 for r in results if r.get("status") in ("failed", "error"))
        total   = len(results)

        lines = [
            f"SPM Batch Test — {today} — {operator}",
            f"Gruppo: {group_name}",
            f"Totale: {total} | Superati: {passed} | Falliti: {failed}",
            "",
        ]
        for r in results:
            icon    = "+" if r.get("status") == "pending_approval" else "-"
            errata  = r.get("errata_id", "?")
            status  = r.get("status", "?")
            dur     = r.get("duration_s", "?")
            phase   = r.get("failure_phase") or ""
            line    = f"{icon} {errata} [{status}] ({dur}s)"
            if phase:
                line += f" - fase: {phase}"
            lines.append(line)

        subject = f"SPM Test {today} [{operator}]"
        body    = "\n".join(lines)

        with UyuniSession() as session:
            systems = session.get_systems_in_group(group_name)
            for sys in systems:
                sid = sys.get("id")
                if sid:
                    try:
                        session.add_note(sid, subject, body)
                        logger.info(
                            f"TestEngine: note added to system {sid} "
                            f"(group={group_name!r})"
                        )
                    except Exception as e:
                        logger.warning(
                            f"TestEngine: add_note failed for system {sid}: {e}"
                        )

    except Exception as e:
        logger.warning(f"TestEngine: _add_batch_note failed: {e}")


def _prune_old_batches() -> None:
    """Rimuove batch completati da piu' di 24h per evitare crescita indefinita di _batches.
    Deve essere chiamata dentro _batches_lock."""
    cutoff = datetime.now(timezone.utc).timestamp() - 86400
    to_delete = [
        bid for bid, b in _batches.items()
        if b.get("status") in ("completed", "error") and b.get("completed_at")
        and _parse_completed_at(b["completed_at"]) < cutoff
    ]
    for bid in to_delete:
        del _batches[bid]
    if to_delete:
        logger.debug(f"TestEngine: pruned {len(to_delete)} old batch(es) from memory")


def _parse_completed_at(ts_str: str) -> float:
    """Converte timestamp ISO string in Unix timestamp. Ritorna 0 su errore."""
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _fetch_queue_item(queue_id: int) -> Optional[dict]:
    """Legge un item dalla coda solo se ancora in stato 'queued'."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                q.id, q.errata_id, q.target_os,
                q.success_score, q.priority_override, q.queued_at,
                COALESCE(rp.requires_reboot, FALSE) AS requires_reboot,
                COALESCE(rp.affects_kernel,  FALSE) AS affects_kernel
            FROM patch_test_queue q
            LEFT JOIN patch_risk_profile rp ON q.errata_id = rp.errata_id
            WHERE q.id = %s AND q.status = 'queued'
            """,
            (queue_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _run_batch_background(
    batch_id: str,
    queue_ids: list,
    group_name: str,
    operator: str,
) -> None:
    """Thread worker: esegue i test del batch e aggiorna _batches in tempo reale."""
    global _testing, _last_result

    try:
        for qid in queue_ids:
            row = _fetch_queue_item(qid)
            if not row:
                result = {
                    "queue_id": qid,
                    "status":   "skipped",
                    "reason":   "Non trovato o non in stato queued",
                }
            else:
                result = _execute_test(row)
                _last_result = result

            with _batches_lock:
                b = _batches[batch_id]
                b["results"].append(result)
                b["completed"] += 1
                if result.get("status") == "pending_approval":
                    b["passed"] += 1
                elif result.get("status") in ("failed", "error"):
                    b["failed"] += 1

        # Nota UYUNI su tutti i sistemi del gruppo
        with _batches_lock:
            results_snapshot = list(_batches[batch_id]["results"])
        _add_batch_note(group_name, results_snapshot, operator)

        with _batches_lock:
            _batches[batch_id]["status"] = "completed"
            _batches[batch_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

    except Exception as e:
        logger.exception(f"Batch {batch_id} background error")
        with _batches_lock:
            _batches[batch_id]["status"] = "error"
            _batches[batch_id]["error"] = str(e)
            _batches[batch_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

    finally:
        with _testing_lock:
            _testing = False


def start_batch(
    queue_ids: list,
    group_name: str,
    operator: str,
) -> Optional[str]:
    """
    Avvia il batch in background. Ritorna immediatamente con batch_id.
    Ritorna None se il test engine è già occupato.
    Le operazioni UYUNI usano l'account admin da Config (.env).
    L'operatore (UPN Azure AD) è registrato nell'audit trail SPM.
    """
    global _testing

    with _testing_lock:
        if _testing:
            return None
        _testing = True

    # Cleanup batch vecchi (>24h) prima di aggiungerne uno nuovo
    with _batches_lock:
        _prune_old_batches()

    batch_id = uuid.uuid4().hex[:12]

    with _batches_lock:
        _batches[batch_id] = {
            "batch_id":    batch_id,
            "status":      "running",
            "group":       group_name,
            "operator":    operator,
            "total":       len(queue_ids),
            "completed":   0,
            "passed":      0,
            "failed":      0,
            "results":     [],
            "started_at":  datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }

    threading.Thread(
        target=_run_batch_background,
        args=(batch_id, queue_ids, group_name, operator),
        daemon=True,
        name=f"batch-{batch_id}",
    ).start()

    logger.info(
        f"Batch {batch_id} started: {len(queue_ids)} items | "
        f"group={group_name!r} | operator={operator!r}"
    )
    return batch_id


def get_batch_status(batch_id: str) -> Optional[dict]:
    """Ritorna lo stato corrente del batch, None se non trovato."""
    with _batches_lock:
        b = _batches.get(batch_id)
        return dict(b) if b else None


def init_test_scheduler(scheduler) -> None:
    """
    Aggiunge il job di polling coda all'APScheduler esistente.
    Controlla ogni 2 minuti se ci sono patch da testare.
    """
    scheduler.add_job(
        func=run_next_test,
        trigger="interval",
        minutes=2,
        id="test_engine_poll",
        name="Test Engine Poll",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    logger.info("TestEngine scheduler: polling queue every 2 minutes")
