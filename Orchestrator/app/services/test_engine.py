"""
SPM Orchestrator - Test Engine

Esegue test automatici sulle patch in coda (status='queued').
Un test alla volta — mutex globale _testing.

Flusso a fasi:
  ① snapshot  — crea snapshot pre-patch via snapper (Salt cmd.run)
  ② patch     — applica pacchetti via Salt pkg.install
  ③ reboot    — riavvio + attesa online (solo se requires_reboot=True)
  ④ validate  — verifica delta CPU/memoria via Prometheus
  ⑤ services  — verifica servizi critici via Salt service.status
  ↓ (fallimento in qualsiasi fase)
  ⑥ rollback  — snapshot: snapper undochange | package: pkg downgrade

Ogni fase è registrata in patch_test_phases.
Il risultato finale aggiorna patch_tests e patch_test_queue.

Rollback type:
  requires_reboot = True  → snapshot (snapper undochange, senza reboot)
  requires_reboot = False → package (reinstalla versioni precedenti)
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.config import Config
from app.services.db import get_db
from app.services.salt_client import SaltSession, get_critical_services
from app.services.prometheus_client import PrometheusClient

logger = logging.getLogger(__name__)

# ── Stato globale ────────────────────────────────────────────────
_testing: bool = False
_last_result: Optional[dict] = None


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
            FOR UPDATE SKIP LOCKED
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
        elif status in ("passed", "failed", "error"):
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
    salt: SaltSession,
    system_name: str,
    errata_id: str,
) -> str:
    """
    Fase SNAPSHOT: crea snapshot pre-patch via snapper.
    Ritorna snapshot_id (numero snapper come stringa).
    Raises: RuntimeError se fallisce.
    """
    phase_id = _create_phase(test_id, "snapshot")
    try:
        desc = f"spm-pre-{errata_id}"
        raw = salt._run(
            system_name,
            "cmd.run",
            arg=[f"snapper create --description '{desc}' --print-number"],
        )
        snapshot_id = str(raw).strip()
        if not snapshot_id.isdigit():
            raise RuntimeError(f"Unexpected snapper output: {raw!r}")

        _complete_phase(phase_id, "completed", output={"snapshot_id": snapshot_id})
        _update_test_record(test_id, snapshot_id=snapshot_id)
        logger.info(f"TestEngine: snapshot #{snapshot_id} created on {system_name!r}")
        return snapshot_id

    except Exception as e:
        _complete_phase(phase_id, "failed", error=str(e))
        raise RuntimeError(f"Snapshot failed: {e}") from e


def _phase_patch(
    test_id: int,
    salt: SaltSession,
    system_name: str,
    pkg_names: list,
) -> dict:
    """
    Fase PATCH: installa/aggiorna pacchetti via Salt pkg.install.
    Ritorna {pkg_name: {old: "...", new: "..."}} per rollback package.
    Raises: RuntimeError se fallisce.
    """
    phase_id = _create_phase(test_id, "patch")
    try:
        result = salt.apply_packages(system_name, pkg_names)
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
    salt: SaltSession,
    system_name: str,
) -> None:
    """
    Fase REBOOT: riavvio controllato + attesa online.
    Raises: RuntimeError se il minion non torna online.
    """
    phase_id = _create_phase(test_id, "reboot")
    try:
        salt.reboot(system_name, wait_seconds=5)
        # Attende che il sistema avvii lo shutdown prima di polling
        time.sleep(30)
        online = salt.wait_online(
            system_name,
            timeout=Config.TEST_WAIT_AFTER_REBOOT,
        )
        if not online:
            raise RuntimeError(
                f"Minion {system_name!r} did not come back online "
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
    salt: SaltSession,
    system_name: str,
    target_os: str,
) -> None:
    """
    Fase SERVICES: verifica servizi critici post-patch.
    Raises: RuntimeError se uno o più servizi sono DOWN.
    """
    phase_id = _create_phase(test_id, "services")
    try:
        services = get_critical_services(target_os)
        failed = salt.get_failed_services(system_name, services)

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
    salt: SaltSession,
    system_name: str,
    rollback_type: str,
    snapshot_id: Optional[str],
    packages_before: dict,
) -> None:
    """
    Fase ROLLBACK: ripristina sistema allo stato pre-patch.

    rollback_type='snapshot' → snapper undochange {snapshot_id}..0
    rollback_type='package'  → reinstalla versioni precedenti via pkg.install

    Non solleva eccezioni: il fallback del rollback viene solo loggato.
    """
    phase_id = _create_phase(test_id, "rollback")
    try:
        if rollback_type == "snapshot" and snapshot_id:
            salt._run(
                system_name,
                "cmd.run",
                arg=[f"snapper undochange {snapshot_id}..0"],
            )
            logger.info(
                f"TestEngine: snapshot rollback (#{snapshot_id}) on {system_name!r}"
            )

        elif rollback_type == "package" and packages_before:
            # Reinstalla versioni precedenti: {pkg_name: {old: "version", new: "..."}}
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
                logger.info(
                    f"TestEngine: package rollback "
                    f"({len(pkgs_to_restore)} packages) on {system_name!r}"
                )
            else:
                logger.warning(
                    f"TestEngine: package rollback skipped — no 'old' versions in apply result"
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

    # Sistema di test per questo OS
    sys_info    = Config.TEST_SYSTEMS.get(target_os, {})
    system_id   = sys_info.get("system_id")
    system_name = sys_info.get("system_name", "")
    system_ip   = sys_info.get("system_ip", "")

    if not system_name:
        err = f"No test system configured for target_os={target_os!r}"
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
        with SaltSession() as salt:
            prom = PrometheusClient()

            # Verifica minion raggiungibile prima di partire
            if not salt.ping(system_name):
                raise RuntimeError(
                    f"Minion {system_name!r} not reachable via Salt API"
                )

            # ① SNAPSHOT
            snapshot_id = _phase_snapshot(test_id, salt, system_name, errata_id)

            # Baseline metriche (best-effort)
            baseline_metrics = {}
            if system_ip and prom.is_available():
                baseline_metrics = prom.get_snapshot(system_ip)
                _update_test_record(test_id, baseline_metrics=baseline_metrics)

            # ② PATCH
            try:
                apply_result = _phase_patch(test_id, salt, system_name, pkg_names)
            except RuntimeError as e:
                failure_reason = str(e)
                failure_phase  = "patch"
                _phase_rollback(
                    test_id, salt, system_name,
                    rollback_type, snapshot_id, apply_result,
                )
                rollback_done = True
                raise

            # ③ REBOOT (solo se requires_reboot)
            if requires_reboot:
                try:
                    _phase_reboot(test_id, salt, system_name)
                except RuntimeError as e:
                    failure_reason = str(e)
                    failure_phase  = "reboot"
                    _phase_rollback(
                        test_id, salt, system_name,
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
                        test_id, salt, system_name,
                        rollback_type, snapshot_id, apply_result,
                    )
                    rollback_done = True
                    raise

            # ⑤ SERVICES
            try:
                _phase_services(test_id, salt, system_name, target_os)
            except RuntimeError as e:
                failure_reason = str(e)
                failure_phase  = "services"
                _phase_rollback(
                    test_id, salt, system_name,
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

    _update_test_record(
        test_id,
        result           = final_result,
        failure_reason   = failure_reason,
        failure_phase    = failure_phase,
        rollback_performed = rollback_done,
        completed_at     = completed_at,
        duration_seconds = duration_s,
    )
    _set_queue_status(queue_id, final_result)

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
    """
    global _testing, _last_result

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
        _testing = False


def get_engine_status() -> dict:
    """Stato corrente del Test Engine (per /api/v1/tests/status)."""
    return {
        "testing":     _testing,
        "last_result": _last_result,
    }


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
