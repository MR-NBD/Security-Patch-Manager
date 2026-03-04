"""
SPM Dashboard — API Client

Wrapper per le chiamate REST all'Orchestrator Flask.
Tutte le funzioni ritornano (data, error_str).
  data  = dict/list se successo, None se errore
  error = None se successo, stringa di errore se fallisce
"""

import os
import requests

# URL base configurabile da env; default al VM in produzione
_BASE = os.environ.get("SPM_API_URL", "http://10.172.2.22:5001")
_TIMEOUT = 15  # secondi


def _get(path: str, params: dict = None):
    try:
        r = requests.get(f"{_BASE}{path}", params=params, timeout=_TIMEOUT)
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


def _post(path: str, body: dict = None):
    try:
        r = requests.post(f"{_BASE}{path}", json=body or {}, timeout=_TIMEOUT)
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


def _delete(path: str):
    try:
        r = requests.delete(f"{_BASE}{path}", timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, f"Impossibile connettersi a {_BASE}"
    except requests.exceptions.Timeout:
        return None, "Timeout"
    except requests.exceptions.HTTPError as e:
        try:
            msg = e.response.json().get("error", str(e))
        except Exception:
            msg = str(e)
        return None, msg
    except Exception as e:
        return None, str(e)


def _patch(path: str, body: dict):
    try:
        r = requests.patch(f"{_BASE}{path}", json=body, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, f"Impossibile connettersi a {_BASE}"
    except requests.exceptions.Timeout:
        return None, "Timeout"
    except requests.exceptions.HTTPError as e:
        try:
            msg = e.response.json().get("error", str(e))
        except Exception:
            msg = str(e)
        return None, msg
    except Exception as e:
        return None, str(e)


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
    return _post("/api/v1/sync/trigger")


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


def queue_add(errata_id: str, target_os: str, priority_override: int = 0,
              created_by: str = None, notes: str = None):
    body = {
        "errata_id": errata_id,
        "target_os": target_os,
        "priority_override": priority_override,
    }
    if created_by:
        body["created_by"] = created_by
    if notes:
        body["notes"] = notes
    return _post("/api/v1/queue", body)


def queue_remove(queue_id: int):
    return _delete(f"/api/v1/queue/{queue_id}")


def queue_update(queue_id: int, priority_override: int = None, notes: str = None):
    body = {}
    if priority_override is not None:
        body["priority_override"] = priority_override
    if notes is not None:
        body["notes"] = notes
    return _patch(f"/api/v1/queue/{queue_id}", body)


# ─────────────────────────────────────────────
# Test Engine
# ─────────────────────────────────────────────

def tests_status():
    return _get("/api/v1/tests/status")


def tests_run():
    return _post("/api/v1/tests/run")


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
# Deployments
# ─────────────────────────────────────────────

def deployments_list(status=None, limit=50, offset=0):
    params = {"limit": limit, "offset": offset}
    if status:
        params["status"] = status
    return _get("/api/v1/deployments", params=params)


def deployment_detail(dep_id: int):
    return _get(f"/api/v1/deployments/{dep_id}")


def deployment_create(queue_id: int, target_systems: list, created_by: str, notes: str = None):
    body = {
        "queue_id": queue_id,
        "target_systems": target_systems,
        "created_by": created_by,
    }
    if notes:
        body["notes"] = notes
    return _post("/api/v1/deployments", body)


def deployment_rollback(dep_id: int, initiated_by: str, reason: str):
    return _post(f"/api/v1/deployments/{dep_id}/rollback", {
        "initiated_by": initiated_by,
        "reason": reason,
    })


# ─────────────────────────────────────────────
# Notifications (lettura diretta — non è un endpoint API,
# ma per ora usiamo health/detail per sapere se ci sono)
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
