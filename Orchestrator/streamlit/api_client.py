"""
SPM Dashboard — API Client

Wrapper per le chiamate REST all'Orchestrator Flask.
Tutte le funzioni ritornano (data, error_str).
  data  = dict/list se successo, None se errore
  error = None se successo, stringa di errore se fallisce

Tutte le richieste HTTP passano per _request(), che gestisce autenticazione,
timeout e conversione degli errori in stringhe leggibili.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

# URL base: default localhost perché Streamlit e Flask girano sulla stessa VM.
# Cambiare SPM_API_URL nel .env solo se Flask è su un host diverso.
_BASE = os.environ.get("SPM_API_URL", "http://localhost:5001")

# Timeout breve per operazioni veloci (health, coda, approvazioni).
# Timeout lungo per operazioni bloccanti (sync trigger, test run) che possono
# durare diversi minuti prima di rispondere.
_TIMEOUT_SHORT = 15
_TIMEOUT_LONG  = 360  # 6 min: sync ~12s in produzione, test fino a 30 min

# Chiave API condivisa con Flask (SPM_API_KEY in .env)
_API_KEY = os.environ.get("SPM_API_KEY", "")


def _auth_headers() -> dict:
    """Header base per tutte le richieste: include X-SPM-Key se configurata."""
    return {"X-SPM-Key": _API_KEY} if _API_KEY else {}


def _request(method: str, path: str, *, params=None, body=None, timeout=None):
    """
    Esegue una richiesta HTTP verso l'API Flask.
    Ritorna (data, error_str) — convenzione usata da tutte le funzioni pubbliche.
    """
    kwargs = {
        "headers": _auth_headers(),
        "timeout": timeout or _TIMEOUT_SHORT,
    }
    if params is not None:
        kwargs["params"] = params
    if body is not None:
        kwargs["json"] = body

    try:
        r = requests.request(method, f"{_BASE}{path}", **kwargs)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, f"Impossibile connettersi a {_BASE}"
    except requests.exceptions.Timeout:
        return None, "Timeout connessione"
    except requests.exceptions.HTTPError as e:
        try:
            msg = e.response.json().get("error", str(e))
        except Exception:
            msg = str(e)
        return None, msg
    except Exception as e:
        return None, str(e)


def _get(path: str, params: dict = None, timeout: int = None):
    return _request("GET", path, params=params, timeout=timeout)


def _post(path: str, body: dict = None, timeout: int = None):
    # body or {} preserva il comportamento originale: invia sempre un JSON body
    return _request("POST", path, body=body or {}, timeout=timeout)


def _delete(path: str):
    return _request("DELETE", path)


def _patch(path: str, body: dict):
    return _request("PATCH", path, body=body)


# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────

def health():
    return _get("/api/v1/health")


def health_detail():
    return _get("/api/v1/health/detail")


# ─────────────────────────────────────────────
# Sync
# ─────────────────────────────────────────────

def sync_status():
    return _get("/api/v1/sync/status")


def sync_trigger():
    # Bloccante: aspetta il completamento del sync (~12-30s in produzione)
    return _post("/api/v1/sync/trigger", timeout=_TIMEOUT_LONG)


def errata_cache_stats():
    return _get("/api/v1/errata/cache/stats")


# ─────────────────────────────────────────────
# Queue
# ─────────────────────────────────────────────

def queue_list(status=None, target_os=None, severity=None, limit=100, offset=0):
    params = {"limit": limit, "offset": offset}
    if status:
        params["status"] = status
    if target_os:
        params["target_os"] = target_os
    if severity:
        params["severity"] = severity
    return _get("/api/v1/queue", params=params)


def queue_stats():
    return _get("/api/v1/queue/stats")


def queue_item(queue_id: int):
    return _get(f"/api/v1/queue/{queue_id}")


def queue_add(errata_id: str, target_os: str,
              created_by: str = None, notes: str = None):
    body = {
        "errata_id": errata_id,
        "target_os": target_os,
    }
    if created_by:
        body["created_by"] = created_by
    if notes:
        body["notes"] = notes
    return _post("/api/v1/queue", body)


def queue_remove(queue_id: int):
    return _delete(f"/api/v1/queue/{queue_id}")


def queue_update(queue_id: int, notes: str = None):
    body = {}
    if notes is not None:
        body["notes"] = notes
    return _patch(f"/api/v1/queue/{queue_id}", body)


# ─────────────────────────────────────────────
# Test Engine
# ─────────────────────────────────────────────

def tests_status():
    return _get("/api/v1/tests/status")


def tests_run():
    # Bloccante: può durare fino a 30 min (TEST_TIMEOUT_MINUTES)
    return _post("/api/v1/tests/run", timeout=_TIMEOUT_LONG)


def test_detail(test_id: int):
    return _get(f"/api/v1/tests/{test_id}")


# ─────────────────────────────────────────────
# Approvals
# ─────────────────────────────────────────────

def approvals_pending(limit=50, offset=0):
    return _get("/api/v1/approvals/pending", params={"limit": limit, "offset": offset})


def approval_detail(queue_id: int):
    return _get(f"/api/v1/approvals/pending/{queue_id}")


def approve(queue_id: int, action_by: str, reason: str = None):
    body = {"action_by": action_by}
    if reason:
        body["reason"] = reason
    return _post(f"/api/v1/approvals/{queue_id}/approve", body)


def reject(queue_id: int, action_by: str, reason: str = None):
    body = {"action_by": action_by}
    if reason:
        body["reason"] = reason
    return _post(f"/api/v1/approvals/{queue_id}/reject", body)


def snooze(queue_id: int, action_by: str, snooze_until: str, reason: str = None):
    body = {"action_by": action_by, "snooze_until": snooze_until}
    if reason:
        body["reason"] = reason
    return _post(f"/api/v1/approvals/{queue_id}/snooze", body)


def approvals_history(limit=50, offset=0):
    return _get("/api/v1/approvals/history", params={"limit": limit, "offset": offset})


# ─────────────────────────────────────────────
# Groups (UYUNI test groups + patches per group)
# ─────────────────────────────────────────────

def orgs_list():
    return _get("/api/v1/orgs")


def groups_list(org_id: int = None):
    params = {}
    if org_id is not None:
        params["org_id"] = org_id
    return _get("/api/v1/groups", params=params)


def group_patches(group_name: str):
    return _get(f"/api/v1/groups/{group_name}/patches")


# ─────────────────────────────────────────────
# Test Batch
# ─────────────────────────────────────────────

def start_batch(queue_ids: list, group_name: str, operator: str):
    """Avvia batch in background. Ritorna {batch_id, status, total}."""
    return _post("/api/v1/tests/batch", {
        "queue_ids":  queue_ids,
        "group_name": group_name,
        "operator":   operator,
    })


def batch_status(batch_id: str):
    """Polling stato batch. Ritorna {status, completed, passed, failed, results, ...}."""
    return _get(f"/api/v1/tests/batch/{batch_id}/status")


def batch_cancel(batch_id: str):
    """Richiede cancellazione batch in esecuzione."""
    return _post(f"/api/v1/tests/batch/{batch_id}/cancel")


# ─────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────

def notifications(limit=20, mark_read=False):
    params = {"limit": limit}
    if mark_read:
        params["mark_read"] = "true"
    return _get("/api/v1/notifications", params=params)


def notifications_mark_read(ids: list = None):
    body = {"ids": ids} if ids else {}
    return _post("/api/v1/notifications/mark-read", body)


def base_url() -> str:
    return _BASE
