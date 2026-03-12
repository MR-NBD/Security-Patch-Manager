"""
SPM Orchestrator - Test Engine Phase Executors

Implementa le singole fasi del test patch su un sistema UYUNI e la logica
di classificazione errori + retry intelligente.

Fasi (in ordine di esecuzione):
  ⓪ pre_check   — pre-flight: servizi baseline, disco (min 500 MB), reboot pendente
  ① snapshot    — crea snapshot snapper pre-patch (UYUNI scheduleScriptRun)
  ② patch       — applica errata via UYUNI scheduleApplyErrata
  ③ reboot      — scheduleReboot + wait_online + stabilizzazione post-reboot
  ④ validate    — delta CPU/MEM vs baseline Prometheus (skipped se non disponibile)
  ⑤ services    — systemctl check servizi critici (6 retry × 20s)
  ↓ rollback    — snapper undochange o package manager downgrade
  ↓ post_rollback — verifica servizi dopo rollback (best-effort)

Classificazione errori per retry intelligente:
  INFRA      → sistema offline, disco pieno, servizi già down → max 2 retry, 2h
  TRANSIENT  → timeout UYUNI/rete, reboot lento             → max 3 retry, 30min
  PATCH      → applicazione patch fallita                   → no retry
  REGRESSION → servizi down o validate fallito              → no retry

Funzioni pubbliche principali (usate da test_engine.py):
  execute_test(queue_item, on_test_created)        — orchestra il test su tutti i sistemi
  execute_test_on_system(...)                       — esegue il test su un singolo sistema
  classify_error(phase, reason)                     — classifica categoria errore
  maybe_retry(queue_id, retry_count, category)      — schedula retry se applicabile
  resolve_test_systems(target_os)                   — risolve sistemi di test per OS

Nota: questo modulo non ha stato globale. Lo stato (_testing, _batches, ecc.)
è gestito interamente in test_engine.py.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from app.config import Config
from app.services import test_db
from app.services.notification_manager import notify_test_result
from app.services.prometheus_client import PrometheusClient
from app.services.uyuni_patch_client import (
    UyuniPatchClient,
    get_all_test_systems_for_os,
    get_critical_services,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Phase executors
# ─────────────────────────────────────────────

def phase_snapshot(
    test_id: int,
    uyuni: UyuniPatchClient,
    errata_id: str,
) -> str:
    """
    Fase SNAPSHOT: crea snapshot snapper pre-patch via UYUNI scheduleScriptRun.
    Ritorna snapshot_id (numero snapper come stringa).
    Raises: RuntimeError se snapper fallisce.
    """
    phase_id = test_db.create_phase(test_id, "snapshot")
    try:
        snapshot_id = uyuni.take_snapshot(f"spm-pre-{errata_id}")
        test_db.complete_phase(phase_id, "completed", output={"snapshot_id": snapshot_id})
        test_db.update_test_record(test_id, snapshot_id=snapshot_id)
        logger.info(f"TestEngine: snapshot #{snapshot_id} created on {uyuni._system_name!r}")
        return snapshot_id
    except Exception as e:
        test_db.complete_phase(phase_id, "failed", error=str(e))
        raise RuntimeError(f"Snapshot failed: {e}") from e


def phase_patch(
    test_id: int,
    uyuni: UyuniPatchClient,
    errata_id: str,
    pkg_names: list,
) -> dict:
    """
    Fase PATCH: applica errata via UYUNI scheduleApplyErrata.
    Ritorna {pkg_name: {old: "", new: "patched"}} per compatibilità rollback package.
    Raises: RuntimeError se l'applicazione fallisce o va in timeout.
    """
    phase_id = test_db.create_phase(test_id, "patch")
    try:
        result = uyuni.apply_errata(errata_id, pkg_names)
        test_db.complete_phase(
            phase_id, "completed",
            output={"packages_applied": result, "count": len(result)},
        )
        return result if isinstance(result, dict) else {}
    except Exception as e:
        test_db.complete_phase(phase_id, "failed", error=str(e))
        raise RuntimeError(f"Patch failed: {e}") from e


def phase_reboot(
    test_id: int,
    uyuni: UyuniPatchClient,
) -> None:
    """
    Fase REBOOT: scheduleReboot + wait_online + stabilizzazione.
    Raises: RuntimeError se il sistema non torna online entro il timeout.
    """
    phase_id = test_db.create_phase(test_id, "reboot")
    try:
        uyuni.reboot()
        online = uyuni.wait_online(timeout=Config.TEST_WAIT_AFTER_REBOOT)
        if not online:
            raise RuntimeError(
                f"System {uyuni._system_name!r} did not come back online "
                f"within {Config.TEST_WAIT_AFTER_REBOOT}s"
            )
        stab = Config.TEST_REBOOT_STABILIZATION
        logger.info(
            f"TestEngine: system online — waiting {stab}s for post-reboot stabilization"
        )
        time.sleep(stab)
        test_db.complete_phase(phase_id, "completed", output={"reboot_successful": True})
        test_db.update_test_record(test_id, reboot_performed=True, reboot_successful=True)
    except Exception as e:
        test_db.complete_phase(phase_id, "failed", error=str(e))
        test_db.update_test_record(test_id, reboot_performed=True, reboot_successful=False)
        raise RuntimeError(f"Reboot failed: {e}") from e


def phase_validate(
    test_id: int,
    prom: PrometheusClient,
    system_ip: str,
    baseline: dict,
) -> None:
    """
    Fase VALIDATE: confronta metriche post-patch vs baseline Prometheus.
    Skipped senza errore se Prometheus non disponibile.
    Raises: RuntimeError se delta CPU o MEM supera la soglia configurata.
    """
    phase_id = test_db.create_phase(test_id, "validate")
    try:
        post = prom.get_snapshot(system_ip)
        evaluation = prom.evaluate_delta(baseline, post)

        test_db.update_test_record(
            test_id,
            post_patch_metrics=post,
            metrics_delta={
                "cpu_delta":    evaluation.get("cpu_delta"),
                "memory_delta": evaluation.get("memory_delta"),
            },
            metrics_evaluation=evaluation,
        )

        if evaluation.get("skipped"):
            test_db.complete_phase(phase_id, "skipped", output=evaluation)
        elif evaluation.get("passed"):
            test_db.complete_phase(phase_id, "completed", output=evaluation)
        else:
            err = (
                f"Delta exceeded threshold — "
                f"CPU Δ={evaluation.get('cpu_delta')}% "
                f"(limit={Config.TEST_CPU_DELTA}%), "
                f"MEM Δ={evaluation.get('memory_delta')}% "
                f"(limit={Config.TEST_MEMORY_DELTA}%)"
            )
            test_db.complete_phase(phase_id, "failed", error=err, output=evaluation)
            raise RuntimeError(err)

    except RuntimeError:
        raise
    except Exception as e:
        test_db.complete_phase(phase_id, "failed", error=str(e))
        raise RuntimeError(f"Validate failed: {e}") from e


def phase_services(
    test_id: int,
    uyuni: UyuniPatchClient,
    target_os: str,
) -> None:
    """
    Fase SERVICES: verifica servizi critici post-patch via systemctl script.
    Retry 6×20s per tollerare servizi in riavvio (es. openssh-server dopo patch).
    Raises: RuntimeError se uno o più servizi sono DOWN dopo tutti i tentativi.
    """
    _RETRIES    = 6
    _RETRY_WAIT = 20  # secondi tra tentativi (totale max ~2 min)

    phase_id = test_db.create_phase(test_id, "services")
    try:
        services = get_critical_services(target_os)
        failed = []

        for attempt in range(1, _RETRIES + 1):
            failed = uyuni.get_failed_services(services)
            if not failed:
                break
            if attempt < _RETRIES:
                logger.info(
                    f"TestEngine: services check attempt {attempt}/{_RETRIES} — "
                    f"DOWN: {failed} — retrying in {_RETRY_WAIT}s"
                )
                time.sleep(_RETRY_WAIT)

        test_db.update_test_record(
            test_id,
            services_baseline=services,
            services_post_patch=services,
            failed_services=failed,
        )

        if failed:
            err = f"Critical services DOWN after patch: {', '.join(failed)}"
            test_db.complete_phase(
                phase_id, "failed", error=err,
                output={"checked": services, "failed": failed},
            )
            raise RuntimeError(err)

        test_db.complete_phase(
            phase_id, "completed",
            output={"checked": services, "all_ok": True},
        )

    except RuntimeError:
        raise
    except Exception as e:
        test_db.complete_phase(phase_id, "failed", error=str(e))
        raise RuntimeError(f"Services check failed: {e}") from e


def phase_preflight(
    test_id: int,
    uyuni: UyuniPatchClient,
    target_os: str,
) -> None:
    """
    Fase PRE_CHECK: valida lo stato del sistema prima di applicare la patch.
    Controlla: servizi critici baseline, spazio disco (min 500 MB), reboot pendente.
    Raises: RuntimeError con prefisso [INFRA] se una condizione blocca il test.
    """
    phase_id = test_db.create_phase(test_id, "pre_check")
    issues = []

    try:
        services = get_critical_services(target_os)
        failed_svcs = uyuni.get_failed_services(services)
        if failed_svcs:
            issues.append(
                f"Critical services DOWN before patch: {', '.join(failed_svcs)}"
            )

        disk_ok, available_mb, disk_msg = uyuni.check_disk_space(min_mb=500)
        if not disk_ok:
            issues.append(disk_msg)

        reboot_pending, reboot_msg = uyuni.check_reboot_pending(target_os)
        if reboot_pending:
            issues.append(reboot_msg)

        output = {
            "services_checked":  services,
            "failed_services":   failed_svcs,
            "disk_available_mb": available_mb,
            "reboot_pending":    reboot_pending,
        }

        if issues:
            err = "[INFRA] Pre-flight checks failed: " + "; ".join(issues)
            test_db.complete_phase(phase_id, "failed", error=err, output=output)
            raise RuntimeError(err)

        test_db.complete_phase(phase_id, "completed", output=output)

    except RuntimeError:
        raise
    except Exception as e:
        test_db.complete_phase(phase_id, "failed", error=str(e))
        raise RuntimeError(f"[INFRA] Pre-flight check error: {e}") from e


def phase_rollback(
    test_id: int,
    uyuni: UyuniPatchClient,
    rollback_type: str,
    snapshot_id: Optional[str],
    packages_before: dict,
    target_os: str = "ubuntu",
) -> None:
    """
    Fase ROLLBACK: ripristina il sistema allo stato pre-patch.

    rollback_type='snapshot' → snapper undochange (via scheduleScriptRun)
    rollback_type='package'  → package manager downgrade (apt su Ubuntu, dnf su RHEL)

    Non solleva eccezioni: il fallimento del rollback viene loggato ma non interrompe
    il flusso principale (il test è già fallito).
    """
    phase_id = test_db.create_phase(test_id, "rollback")
    system_name = uyuni._system_name
    try:
        if rollback_type == "snapshot" and snapshot_id:
            uyuni.rollback_snapshot(snapshot_id)
            logger.info(
                f"TestEngine: snapshot rollback (#{snapshot_id}) on {system_name!r}"
            )
        elif rollback_type == "package" and packages_before:
            uyuni.rollback_packages(packages_before, target_os=target_os)
            logger.info(
                f"TestEngine: package rollback on {system_name!r} (os={target_os!r})"
            )
        else:
            logger.warning(
                f"TestEngine: rollback skipped "
                f"(type={rollback_type!r}, snapshot_id={snapshot_id!r})"
            )

        test_db.complete_phase(
            phase_id, "completed",
            output={"rollback_type": rollback_type, "snapshot_id": snapshot_id},
        )
        test_db.update_test_record(
            test_id,
            rollback_performed=True,
            rollback_type=rollback_type,
            rollback_at=datetime.now(timezone.utc),
        )

    except Exception as e:
        test_db.complete_phase(phase_id, "failed", error=str(e))
        logger.error(f"TestEngine: ROLLBACK FAILED on {system_name!r}: {e}")


def phase_verify_rollback(
    test_id: int,
    uyuni: UyuniPatchClient,
    target_os: str,
) -> None:
    """
    Fase POST_ROLLBACK: verifica servizi critici dopo il rollback.
    Best-effort: non solleva eccezioni, registra solo l'esito nella fase.
    """
    phase_id = test_db.create_phase(test_id, "post_rollback")
    try:
        services = get_critical_services(target_os)
        failed   = uyuni.get_failed_services(services)
        status   = "completed" if not failed else "failed"
        output   = {
            "services_checked":  services,
            "failed_services":   failed,
            "rollback_verified": not failed,
        }
        error = f"Services DOWN after rollback: {', '.join(failed)}" if failed else None
        test_db.complete_phase(phase_id, status, error=error, output=output)
        if failed:
            logger.warning(
                f"TestEngine: services DOWN after rollback on "
                f"{uyuni._system_name!r}: {failed}"
            )
        else:
            logger.info(
                f"TestEngine: post-rollback services OK on {uyuni._system_name!r}"
            )
    except Exception as e:
        test_db.complete_phase(phase_id, "failed", error=str(e))
        logger.warning(f"TestEngine: phase_verify_rollback error: {e}")


def rollback_and_verify(
    test_id: int,
    uyuni: UyuniPatchClient,
    rollback_type: str,
    snapshot_id: Optional[str],
    packages_before: dict,
    target_os: str,
) -> None:
    """Esegue rollback e poi verifica post-rollback (best-effort)."""
    phase_rollback(
        test_id, uyuni,
        rollback_type, snapshot_id, packages_before,
        target_os=target_os,
    )
    phase_verify_rollback(test_id, uyuni, target_os)


# ─────────────────────────────────────────────
# Error classification + retry
# ─────────────────────────────────────────────

def classify_error(
    failure_phase: Optional[str],
    failure_reason: Optional[str],
) -> str:
    """
    Classifica la categoria dell'errore per decidere il comportamento di retry.

    INFRA      → pre-flight fallito, sistema offline, disco pieno.
                 Retry dopo 2h, max 2 volte.
    TRANSIENT  → timeout UYUNI/rete, reboot lento.
                 Retry dopo 30min, max 3 volte.
    PATCH      → la patch ha causato problemi (applicazione fallita).
                 No retry: problema intrinseco della patch.
    REGRESSION → la patch ha rotto qualcosa (servizi down, validate fallito).
                 No retry: richiede analisi manuale.
    """
    phase  = (failure_phase  or "").lower()
    reason = (failure_reason or "").lower()

    if "[infra]" in reason:
        return "INFRA"

    if phase == "pre_check" or "not reachable" in reason:
        return "INFRA"

    _transient_keywords = [
        "timeout", "timed out", "connection", "xmlrpc",
        "socket", "eoferror", "http error",
    ]
    if any(kw in reason for kw in _transient_keywords):
        return "TRANSIENT"

    if phase == "reboot":
        return "TRANSIENT"

    if phase == "patch":
        return "PATCH"

    if phase in ("services", "validate"):
        return "REGRESSION"

    return "PATCH"


def maybe_retry(
    queue_id: int,
    current_retry_count: int,
    category: str,
) -> bool:
    """
    Decide se programmare un retry in base alla categoria di errore.
    Ritorna True se il retry è stato programmato, False altrimenti.

    INFRA:     max 2 retry, delay 2h
    TRANSIENT: max 3 retry, delay 30min
    PATCH/REGRESSION: no retry
    """
    now = datetime.now(timezone.utc)

    if category == "INFRA" and current_retry_count < 2:
        retry_at = now + timedelta(hours=2)
        test_db.set_queue_retry(queue_id, retry_at, current_retry_count + 1)
        logger.info(
            f"TestEngine: queue {queue_id} → retry_pending "
            f"(INFRA, attempt {current_retry_count + 1}/2, "
            f"after {retry_at.isoformat()})"
        )
        return True

    if category == "TRANSIENT" and current_retry_count < 3:
        retry_at = now + timedelta(minutes=30)
        test_db.set_queue_retry(queue_id, retry_at, current_retry_count + 1)
        logger.info(
            f"TestEngine: queue {queue_id} → retry_pending "
            f"(TRANSIENT, attempt {current_retry_count + 1}/3, "
            f"after {retry_at.isoformat()})"
        )
        return True

    return False


# ─────────────────────────────────────────────
# System resolution
# ─────────────────────────────────────────────

def resolve_test_systems(target_os: str) -> list:
    """
    Risolve tutti i sistemi di test per target_os.

    Se .env configura un system_id esplicito → usa solo quel sistema (singolo).
    Completa i dati mancanti (name/ip) tramite auto-discovery UYUNI se necessario.

    Se .env non configura nulla → usa TUTTI i sistemi nel gruppo UYUNI test-{os},
    così ogni sistema aggiunto al gruppo viene automaticamente testato.
    """
    cfg         = Config.TEST_SYSTEMS.get(target_os, {})
    system_id   = cfg.get("system_id")
    system_name = cfg.get("system_name", "")
    system_ip   = cfg.get("system_ip", "")

    if system_id:
        if not system_name or not system_ip:
            all_sys = get_all_test_systems_for_os(target_os)
            match = next((s for s in all_sys if s["system_id"] == system_id), None)
            if match:
                system_name = system_name or match["system_name"]
                system_ip   = system_ip   or match["system_ip"]
        return [{"system_id": system_id, "system_name": system_name, "system_ip": system_ip}]

    return get_all_test_systems_for_os(target_os)


# ─────────────────────────────────────────────
# Core test execution
# ─────────────────────────────────────────────

def execute_test_on_system(
    queue_id: int,
    errata_id: str,
    target_os: str,
    requires_reboot: bool,
    pkg_names: list,
    system_id: int,
    system_name: str,
    system_ip: str,
    on_test_created: Optional[Callable[[int], None]] = None,
) -> dict:
    """
    Esegue tutte le fasi del test su un singolo sistema.
    Crea e finalizza il suo record in patch_tests.
    Invia notifica al termine (sia in caso di successo che fallimento).

    on_test_created: callback(test_id) chiamato appena il test_id è noto.
    Usato da test_engine.py per aggiornare il live monitoring in Streamlit.

    Ritorna dict con: result, test_id, system_id, system_name,
                      failure_phase, failure_reason, duration_s, rollback_done.
    """
    rollback_type = "snapshot" if requires_reboot else "package"

    test_id = test_db.create_test_record(
        queue_id, errata_id, system_id, system_name, system_ip, requires_reboot,
    )

    if on_test_created:
        on_test_created(test_id)

    started_at     = datetime.now(timezone.utc)
    snapshot_id    = None
    apply_result   = {}
    failure_reason = None
    failure_phase  = None
    rollback_done  = False
    final_result   = "error"

    logger.info(
        f"TestEngine: [{system_name}] START {errata_id!r} | OS={target_os} | "
        f"reboot={requires_reboot} | packages={len(pkg_names)}"
    )

    try:
        with UyuniPatchClient(system_id, system_name) as uyuni:
            prom = PrometheusClient()

            if not uyuni.ping():
                failure_reason = (
                    f"System {system_name!r} (id={system_id}) "
                    f"not reachable via UYUNI"
                )
                failure_phase = "pre_check"
                raise RuntimeError(failure_reason)

            # ⓪ PRE-FLIGHT
            try:
                phase_preflight(test_id, uyuni, target_os)
            except RuntimeError as e:
                failure_reason = str(e)
                failure_phase  = "pre_check"
                raise

            # Assicura snapper installato (best-effort)
            snapper_ok = uyuni.ensure_snapper(target_os)
            if not snapper_ok and rollback_type == "snapshot":
                logger.info(
                    f"TestEngine: [{system_name}] snapper not available "
                    f"— switching to package rollback"
                )
                rollback_type = "package"

            # ① SNAPSHOT (best-effort, fallback a package rollback se fallisce)
            try:
                snapshot_id = phase_snapshot(test_id, uyuni, errata_id)
            except RuntimeError as e:
                logger.warning(
                    f"TestEngine: [{system_name}] snapshot failed, "
                    f"switching to package rollback: {e}"
                )
                rollback_type = "package"

            # Assicura node_exporter attivo (best-effort, per Prometheus)
            if system_ip:
                uyuni.ensure_node_exporter(target_os)

            # Baseline metriche Prometheus (best-effort)
            baseline_metrics = {}
            if system_ip and prom.is_available():
                baseline_metrics = prom.get_snapshot(system_ip)
                test_db.update_test_record(test_id, baseline_metrics=baseline_metrics)

            # ② PATCH
            try:
                apply_result = phase_patch(test_id, uyuni, errata_id, pkg_names)
            except RuntimeError as e:
                failure_reason = str(e)
                failure_phase  = "patch"
                rollback_and_verify(
                    test_id, uyuni, rollback_type, snapshot_id, apply_result,
                    target_os=target_os,
                )
                rollback_done = True
                raise

            # ③ REBOOT (solo se requires_reboot)
            if requires_reboot:
                try:
                    phase_reboot(test_id, uyuni)
                except RuntimeError as e:
                    failure_reason = str(e)
                    failure_phase  = "reboot"
                    rollback_and_verify(
                        test_id, uyuni, rollback_type, snapshot_id, apply_result,
                        target_os=target_os,
                    )
                    rollback_done = True
                    raise
            else:
                wait = Config.TEST_WAIT_AFTER_PATCH
                logger.info(
                    f"TestEngine: [{system_name}] waiting {wait}s for stabilization"
                )
                time.sleep(wait)

            # ④ VALIDATE metriche Prometheus
            if system_ip and baseline_metrics and prom.is_available():
                try:
                    phase_validate(test_id, prom, system_ip, baseline_metrics)
                except RuntimeError as e:
                    failure_reason = str(e)
                    failure_phase  = "validate"
                    rollback_and_verify(
                        test_id, uyuni, rollback_type, snapshot_id, apply_result,
                        target_os=target_os,
                    )
                    rollback_done = True
                    raise

            # ⑤ SERVICES
            try:
                phase_services(test_id, uyuni, target_os)
            except RuntimeError as e:
                failure_reason = str(e)
                failure_phase  = "services"
                rollback_and_verify(
                    test_id, uyuni, rollback_type, snapshot_id, apply_result,
                    target_os=target_os,
                )
                rollback_done = True
                raise

            # ✓ Tutte le fasi superate
            final_result = "pending_approval"

    except RuntimeError:
        final_result = "failed"
    except Exception as e:
        failure_reason = f"Unexpected error: {e}"
        failure_phase  = "unknown"
        final_result   = "error"
        logger.exception(
            f"TestEngine: [{system_name}] unexpected error for {errata_id!r}"
        )

    # Finalizza record patch_tests
    completed_at = datetime.now(timezone.utc)
    duration_s   = int((completed_at - started_at).total_seconds())
    # patch_tests.result non ammette 'pending_approval' → mappa a 'passed'
    test_result = "passed" if final_result == "pending_approval" else final_result

    test_db.update_test_record(
        test_id,
        result             = test_result,
        failure_reason     = failure_reason,
        failure_phase      = failure_phase,
        rollback_performed = rollback_done,
        completed_at       = completed_at,
        duration_seconds   = duration_s,
    )

    notify_test_result(
        test_id        = test_id,
        queue_id       = queue_id,
        errata_id      = errata_id,
        result         = final_result,
        failure_phase  = failure_phase,
        failure_reason = failure_reason,
        system_name    = system_name,
        duration_s     = duration_s,
    )

    logger.info(
        f"TestEngine: [{system_name}] END {errata_id!r} → {final_result.upper()} "
        f"({duration_s}s | rollback={rollback_done} | phase={failure_phase})"
    )

    return {
        "result":         final_result,
        "test_id":        test_id,
        "system_id":      system_id,
        "system_name":    system_name,
        "failure_phase":  failure_phase,
        "failure_reason": failure_reason,
        "duration_s":     duration_s,
        "rollback_done":  rollback_done,
    }


def execute_test(
    queue_item: dict,
    on_test_created: Optional[Callable[[int], None]] = None,
) -> dict:
    """
    Esegue il test completo per un elemento della coda.
    Se il gruppo UYUNI contiene più sistemi, testa su tutti in sequenza.
    Il risultato finale è 'pending_approval' solo se TUTTI i sistemi passano;
    se anche uno solo fallisce il risultato è 'failed' con dettaglio per sistema.

    on_test_created: callback(test_id) per il live monitoring batch (vedi test_engine.py).
    """
    queue_id        = queue_item["id"]
    errata_id       = queue_item["errata_id"]
    target_os       = queue_item["target_os"]
    requires_reboot = bool(queue_item.get("requires_reboot", False))
    retry_count     = int(queue_item.get("retry_count", 0))

    systems = resolve_test_systems(target_os)
    if not systems:
        err = (
            f"No test system found for target_os={target_os!r} — "
            f"nessun sistema nel gruppo UYUNI 'test-{target_os}*' "
            f"e nessuna configurazione in .env"
        )
        logger.error(f"TestEngine: {err}")
        return {"status": "error", "error": err, "queue_id": queue_id}

    packages  = test_db.get_packages(errata_id)
    pkg_names = [p["name"] for p in packages if p.get("name")]

    if not pkg_names:
        logger.warning(
            f"TestEngine: no packages found for {errata_id!r} — proceeding without pkg list"
        )

    logger.info(
        f"TestEngine: START {errata_id!r} | OS={target_os} | "
        f"systems={len(systems)} | reboot={requires_reboot} | packages={len(pkg_names)}"
    )

    test_db.set_queue_status(queue_id, "testing")

    per_system_results = []
    for sys_info in systems:
        result = execute_test_on_system(
            queue_id, errata_id, target_os, requires_reboot, pkg_names,
            sys_info["system_id"], sys_info["system_name"], sys_info["system_ip"],
            on_test_created=on_test_created,
        )
        per_system_results.append(result)

    # Aggrega: passed solo se TUTTI i sistemi superano
    all_passed = all(r["result"] == "pending_approval" for r in per_system_results)

    if all_passed:
        final_result   = "pending_approval"
        failure_reason = None
        failure_phase  = None
    else:
        final_result = "failed"
        failed_parts = [
            f"{r['system_name']} [{r['failure_phase']}]: {r['failure_reason']}"
            for r in per_system_results
            if r["result"] in ("failed", "error")
        ]
        failure_reason = " | ".join(failed_parts)
        first_failed   = next(
            (r for r in per_system_results if r["result"] in ("failed", "error")), None
        )
        failure_phase  = first_failed["failure_phase"] if first_failed else "unknown"

    # test_id FK → primo test fallito, o ultimo in caso di successo totale
    first_failed_result = next(
        (r for r in per_system_results if r["result"] in ("failed", "error")), None
    )
    relevant_test_id = (
        first_failed_result["test_id"] if first_failed_result
        else per_system_results[-1]["test_id"]
    )

    # patch_test_queue.chk_queue_status non ammette 'error': mappa a 'failed'
    queue_status = "failed" if final_result == "error" else final_result
    test_db.set_queue_status(queue_id, queue_status, test_id=relevant_test_id)

    if final_result in ("failed", "error"):
        error_category = classify_error(failure_phase, failure_reason)
        retried = maybe_retry(queue_id, retry_count, error_category)
        if retried:
            logger.info(
                f"TestEngine: {errata_id!r} → retry_pending "
                f"(category={error_category}, attempt {retry_count + 1})"
            )

    total_duration = sum(r["duration_s"] for r in per_system_results)
    rollback_any   = any(r["rollback_done"] for r in per_system_results)

    logger.info(
        f"TestEngine: END {errata_id!r} → {final_result.upper()} "
        f"({total_duration}s total | {len(systems)} systems | "
        f"rollback={rollback_any} | failure_phase={failure_phase})"
    )

    return {
        "status":         final_result,
        "test_id":        relevant_test_id,
        "queue_id":       queue_id,
        "errata_id":      errata_id,
        "systems_tested": len(systems),
        "per_system":     per_system_results,
        "duration_s":     total_duration,
        "rollback":       rollback_any,
        "failure_reason": failure_reason,
        "failure_phase":  failure_phase,
    }
