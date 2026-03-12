"""
SPM Orchestrator - Test Engine

Gestisce lo stato globale del motore di test, la coda dei batch asincroni
e offre l'API pubblica usata dai blueprint Flask.

Struttura del modulo:
  Stato globale     — _testing, _batches, _cancel_flags (con i rispettivi lock)
  Callback batch    — _on_test_created() per il live monitoring Streamlit
  Worker background — _run_batch_background() (thread daemon per ogni batch)
  API pubblica      — run_next_test, get_engine_status, start_batch,
                      get_batch_status, cancel_batch, init_test_scheduler

Dipendenze interne:
  test_db.py     — accesso database (funzioni pure, nessuno stato)
  test_phases.py — esecuzione fasi (snapshot, patch, reboot, validate, services)
                   e classificazione errori + retry

Flusso completo delle fasi documentato in test_phases.py.
Dettaglio DB documentato in test_db.py.
"""

import logging
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from app.services import test_db
from app.services.test_phases import execute_test
from app.services.uyuni_client import UyuniSession

logger = logging.getLogger(__name__)


# ── Stato globale ────────────────────────────────────────────────
_testing: bool = False
_testing_lock = threading.Lock()
_last_result: Optional[dict] = None

# ── Stato batch asincroni ────────────────────────────────────────
_batches: dict = {}           # batch_id → stato corrente (cache memoria)
_batches_lock = threading.Lock()
_cancel_flags: set = set()    # batch_id in questo set → cancellazione richiesta


# ─────────────────────────────────────────────
# Batch state callback (per live monitoring)
# ─────────────────────────────────────────────

def _on_test_created(batch_id: str, test_id: int) -> None:
    """
    Callback invocato da test_phases.execute_test_on_system appena il test_id è noto.
    Aggiorna current_test_id nel batch per il live view Streamlit.
    """
    with _batches_lock:
        if batch_id in _batches:
            _batches[batch_id]["current_test_id"] = test_id


# ─────────────────────────────────────────────
# Batch helpers
# ─────────────────────────────────────────────

def _parse_completed_at(ts_str: str) -> float:
    """Converte timestamp ISO string in Unix timestamp. Ritorna 0 su errore."""
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _prune_old_batches() -> None:
    """
    Rimuove batch completati da più di 24h da _batches per evitare crescita indefinita.
    Deve essere chiamata con _batches_lock già acquisito.
    """
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


def _add_batch_note(group_name: str, results: list, operator: str) -> None:
    """
    Aggiunge nota di riepilogo batch su tutti i sistemi del gruppo UYUNI.
    Best-effort: non blocca il flusso anche se fallisce.
    """
    try:
        today  = date.today().isoformat()
        passed = sum(1 for r in results if r.get("status") == "pending_approval")
        failed = sum(1 for r in results if r.get("status") in ("failed", "error"))
        total  = len(results)

        lines = [
            f"SPM Batch Test — {today} — {operator}",
            f"Gruppo: {group_name}",
            f"Totale: {total} | Superati: {passed} | Falliti: {failed}",
            "",
        ]
        for r in results:
            icon = "+" if r.get("status") == "pending_approval" else "-"
            line = (
                f"{icon} {r.get('errata_id', '?')} "
                f"[{r.get('status', '?')}] ({r.get('duration_s', '?')}s)"
            )
            if r.get("failure_phase"):
                line += f" - fase: {r['failure_phase']}"
            lines.append(line)

        subject = f"SPM Test {today} [{operator}]"
        body    = "\n".join(lines)

        with UyuniSession() as session:
            for sys in session.get_systems_in_group(group_name):
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


# ─────────────────────────────────────────────
# Batch background worker
# ─────────────────────────────────────────────

def _run_batch_background(
    batch_id: str,
    queue_ids: list,
    group_name: str,
    operator: str,
) -> None:
    """
    Thread worker: esegue i test del batch e aggiorna _batches + DB in tempo reale.
    Controlla _cancel_flags tra un test e l'altro: se il batch è stato cancellato
    interrompe senza avviare i test rimanenti (il test in corso completa normalmente).
    """
    global _testing, _last_result

    try:
        for qid in queue_ids:
            with _batches_lock:
                cancelled = batch_id in _cancel_flags
            if cancelled:
                logger.info(
                    f"Batch {batch_id}: cancellation requested "
                    f"— stopping after current test"
                )
                break

            row = test_db.fetch_queue_item(qid)
            if not row:
                result = {
                    "queue_id": qid,
                    "status":   "skipped",
                    "reason":   "Non trovato o non in stato queued",
                }
            else:
                with _batches_lock:
                    if batch_id in _batches:
                        _batches[batch_id]["current_errata_id"] = row["errata_id"]
                        _batches[batch_id]["current_test_id"]   = None

                # Callback che cattura batch_id dalla closure (sicuro: è un parametro
                # di funzione, non una variabile di loop)
                def _on_created(test_id: int, _bid: str = batch_id) -> None:
                    _on_test_created(_bid, test_id)

                result = execute_test(row, on_test_created=_on_created)
                _last_result = result

                with _batches_lock:
                    if batch_id in _batches:
                        _batches[batch_id]["current_errata_id"] = None
                        _batches[batch_id]["current_test_id"]   = None

            with _batches_lock:
                b = _batches[batch_id]
                b["results"].append(result)
                b["completed"] += 1
                if result.get("status") == "pending_approval":
                    b["passed"] += 1
                elif result.get("status") in ("failed", "error"):
                    b["failed"] += 1
                completed = b["completed"]
                passed    = b["passed"]
                failed    = b["failed"]
                results   = list(b["results"])

            test_db.db_update_batch(batch_id, completed, passed, failed, results)

        with _batches_lock:
            was_cancelled = batch_id in _cancel_flags
            _cancel_flags.discard(batch_id)

        final_status = "cancelled" if was_cancelled else "completed"

        if not was_cancelled:
            with _batches_lock:
                results_snapshot = list(_batches[batch_id]["results"])
            _add_batch_note(group_name, results_snapshot, operator)

        now_iso = datetime.now(timezone.utc).isoformat()
        with _batches_lock:
            _batches[batch_id]["status"]       = final_status
            _batches[batch_id]["completed_at"] = now_iso

        test_db.db_complete_batch(batch_id, final_status)

    except Exception as e:
        logger.exception(f"Batch {batch_id} background error")
        now_iso = datetime.now(timezone.utc).isoformat()
        with _batches_lock:
            _batches[batch_id]["status"]       = "error"
            _batches[batch_id]["error"]        = str(e)
            _batches[batch_id]["completed_at"] = now_iso
            _cancel_flags.discard(batch_id)
        test_db.db_complete_batch(batch_id, "error", str(e))

    finally:
        with _testing_lock:
            _testing = False


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

        item = test_db.pick_next_queued()
        if not item:
            return {"status": "skipped", "reason": "no items in queue"}

        _testing = True

    try:
        result = execute_test(item)
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

    with _batches_lock:
        _prune_old_batches()

    batch_id = uuid.uuid4().hex[:12]

    with _batches_lock:
        _batches[batch_id] = {
            "batch_id":          batch_id,
            "status":            "running",
            "group":             group_name,
            "operator":          operator,
            "total":             len(queue_ids),
            "completed":         0,
            "passed":            0,
            "failed":            0,
            "results":           [],
            "started_at":        datetime.now(timezone.utc).isoformat(),
            "completed_at":      None,
            "current_test_id":   None,
            "current_errata_id": None,
        }

    test_db.db_create_batch(batch_id, group_name, operator, len(queue_ids))

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
    """
    Ritorna lo stato corrente del batch.
    Prima dalla cache in memoria (batch attivo);
    fallback al DB per batch completati o dopo restart Flask.
    Ritorna None se non trovato né in memoria né nel DB.
    """
    with _batches_lock:
        b = _batches.get(batch_id)
        if b:
            return dict(b)
    return test_db.db_get_batch(batch_id)


def cancel_batch(batch_id: str) -> dict:
    """
    Richiede la cancellazione di un batch in esecuzione.
    Il test attualmente in corso viene completato normalmente;
    i test rimanenti vengono saltati.

    Ritorna:
      {"cancelled": True}  → flag impostato, batch si fermerà al prossimo intertest
      {"cancelled": False, "reason": "..."}  → batch non cancellabile
    """
    b = get_batch_status(batch_id)
    if not b:
        return {"cancelled": False, "reason": "batch not found"}
    if b.get("status") != "running":
        return {"cancelled": False, "reason": f"batch is already {b['status']}"}

    with _batches_lock:
        _cancel_flags.add(batch_id)

    logger.info(f"TestEngine: cancel requested for batch {batch_id}")
    return {"cancelled": True}


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
