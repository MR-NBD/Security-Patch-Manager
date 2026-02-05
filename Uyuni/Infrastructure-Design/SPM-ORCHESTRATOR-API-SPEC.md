# SPM Orchestrator - API Specification

**Versione:** 1.0
**Data:** 2026-02-05
**Base URL:** `http://<host>:5001/api/v1`

---

## Indice

1. [Health & Status](#1-health--status)
2. [Success Score / Risk Profile](#2-success-score--risk-profile)
3. [Test Queue](#3-test-queue)
4. [Test Execution](#4-test-execution)
5. [Approval Workflow](#5-approval-workflow)
6. [Deployment & Rollback](#6-deployment--rollback)
7. [Notifications](#7-notifications)
8. [Reports](#8-reports)
9. [Error Handling](#9-error-handling)

---

## 1. Health & Status

### GET /api/v1/health

Verifica stato del servizio e componenti collegati.

**Response 200:**
```json
{
    "status": "healthy",
    "version": "1.0.0",
    "uptime_seconds": 86400,
    "components": {
        "database": "connected",
        "prometheus": "connected",
        "uyuni": "connected",
        "salt": "connected"
    },
    "queue_stats": {
        "queued": 12,
        "testing": 1,
        "passed": 25,
        "failed": 3,
        "pending_approval": 5,
        "approved": 2
    },
    "last_sync": "2026-02-05T10:00:00Z"
}
```

**Response 503 (Unhealthy):**
```json
{
    "status": "unhealthy",
    "version": "1.0.0",
    "components": {
        "database": "connected",
        "prometheus": "error: connection refused",
        "uyuni": "connected",
        "salt": "connected"
    },
    "error": "One or more components are unhealthy"
}
```

---

## 2. Success Score / Risk Profile

### GET /api/v1/risk-profile

Lista tutti i profili di rischio calcolati.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| min_score | int | 0 | Filtra score >= valore |
| max_score | int | 100 | Filtra score <= valore |
| os | string | null | Filtra per OS ('ubuntu', 'rhel') |
| limit | int | 50 | Max risultati |
| offset | int | 0 | Offset paginazione |

**Response 200:**
```json
{
    "profiles": [
        {
            "errata_id": "USN-7234-1",
            "synopsis": "OpenSSL security update",
            "severity": "Critical",
            "success_score": 85,
            "factors": {
                "affects_kernel": false,
                "requires_reboot": false,
                "modifies_config": false,
                "dependency_count": 2,
                "package_count": 1,
                "total_size_kb": 1250
            },
            "history": {
                "times_tested": 3,
                "times_failed": 0,
                "failure_rate": 0.0
            },
            "recommendation": "Low risk - safe to test early",
            "updated_at": "2026-02-05T09:00:00Z"
        }
    ],
    "total": 156,
    "limit": 50,
    "offset": 0
}
```

### GET /api/v1/risk-profile/{errata_id}

Dettaglio profilo rischio per singolo errata.

**Response 200:**
```json
{
    "errata_id": "USN-7234-1",
    "synopsis": "OpenSSL security update",
    "severity": "Critical",
    "success_score": 85,
    "score_breakdown": {
        "base_score": 100,
        "kernel_penalty": 0,
        "reboot_penalty": 0,
        "config_penalty": 0,
        "dependency_penalty": -6,
        "size_penalty": -1,
        "history_penalty": 0,
        "bonuses": 0,
        "final_score": 85
    },
    "factors": {
        "affects_kernel": false,
        "requires_reboot": false,
        "modifies_config": false,
        "dependency_count": 2,
        "package_count": 1,
        "total_size_kb": 1250
    },
    "history": {
        "times_tested": 3,
        "times_failed": 0,
        "failure_rate": 0.0,
        "last_test_date": "2026-02-04T15:00:00Z",
        "last_test_result": "passed"
    },
    "packages": [
        {"name": "openssl", "version": "3.0.2-0ubuntu1.14", "size_kb": 850},
        {"name": "libssl3", "version": "3.0.2-0ubuntu1.14", "size_kb": 400}
    ],
    "recommendation": "Low risk - safe to test early",
    "created_at": "2026-02-01T10:00:00Z",
    "updated_at": "2026-02-05T09:00:00Z"
}
```

**Response 404:**
```json
{
    "error": "not_found",
    "message": "Risk profile not found for errata: USN-9999-1"
}
```

### POST /api/v1/risk-profile/calculate

Ricalcola Success Score per errata specificati o tutti.

**Request Body:**
```json
{
    "errata_ids": ["USN-7234-1", "USN-7235-2"],
    "force_refresh": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| errata_ids | array | no | Lista errata da calcolare (vuoto = tutti) |
| force_refresh | bool | no | Ricalcola anche se esistente (default: false) |

**Response 200:**
```json
{
    "calculated": 2,
    "updated": 2,
    "skipped": 0,
    "errors": [],
    "duration_ms": 450
}
```

**Response 200 (con errori parziali):**
```json
{
    "calculated": 2,
    "updated": 1,
    "skipped": 0,
    "errors": [
        {
            "errata_id": "USN-7235-2",
            "error": "No packages found for errata"
        }
    ],
    "duration_ms": 320
}
```

---

## 3. Test Queue

### GET /api/v1/queue

Lista coda test ordinata per priorità.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| status | string | null | Filtra per stato |
| os | string | null | Filtra per OS |
| limit | int | 50 | Max risultati |
| offset | int | 0 | Offset paginazione |

**Status values:** `queued`, `testing`, `passed`, `failed`, `needs_reboot`, `rebooting`, `pending_approval`, `approved`, `rejected`, `snoozed`, `promoting`, `prod_pending`, `prod_applied`, `completed`, `rolled_back`

**Response 200:**
```json
{
    "items": [
        {
            "id": 45,
            "errata_id": "USN-7234-1",
            "errata_synopsis": "OpenSSL security update",
            "errata_version": "1",
            "severity": "Critical",
            "success_score": 92,
            "target_os": "ubuntu",
            "status": "queued",
            "position": 1,
            "priority_override": 0,
            "queued_at": "2026-02-05T10:00:00Z",
            "started_at": null,
            "completed_at": null
        },
        {
            "id": 46,
            "errata_id": "USN-7235-2",
            "errata_synopsis": "curl vulnerability fix",
            "errata_version": "1",
            "severity": "High",
            "success_score": 88,
            "target_os": "ubuntu",
            "status": "queued",
            "position": 2,
            "priority_override": 0,
            "queued_at": "2026-02-05T10:05:00Z",
            "started_at": null,
            "completed_at": null
        }
    ],
    "total": 45,
    "by_status": {
        "queued": 12,
        "testing": 1,
        "passed": 20,
        "failed": 3,
        "pending_approval": 8,
        "approved": 1
    },
    "limit": 50,
    "offset": 0
}
```

### POST /api/v1/queue/add

Aggiunge errata alla coda test.

**Request Body:**
```json
{
    "errata_ids": ["USN-7234-1", "USN-7235-2"],
    "target_os": "ubuntu",
    "priority_override": 0
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| errata_ids | array | yes | Lista errata da accodare |
| target_os | string | yes | 'ubuntu' o 'rhel' |
| priority_override | int | no | Override priorità (0 = usa Score) |

**Response 201:**
```json
{
    "added": 2,
    "already_queued": 0,
    "items": [
        {"queue_id": 45, "errata_id": "USN-7234-1", "position": 1},
        {"queue_id": 46, "errata_id": "USN-7235-2", "position": 2}
    ]
}
```

**Response 200 (parzialmente accodato):**
```json
{
    "added": 1,
    "already_queued": 1,
    "items": [
        {"queue_id": 45, "errata_id": "USN-7234-1", "position": 1}
    ],
    "skipped": [
        {"errata_id": "USN-7235-2", "reason": "Already in queue with status: testing"}
    ]
}
```

### POST /api/v1/queue/sync

Sincronizza coda con nuovi errata dal database.

**Request Body:**
```json
{
    "auto_queue_new": true,
    "min_severity": "Medium",
    "os_filter": ["ubuntu", "rhel"],
    "exclude_already_tested": true
}
```

**Response 200:**
```json
{
    "new_errata_found": 5,
    "queued": 5,
    "skipped": 0,
    "items": [
        {"queue_id": 50, "errata_id": "USN-7240-1"},
        {"queue_id": 51, "errata_id": "USN-7241-1"}
    ]
}
```

### DELETE /api/v1/queue/{queue_id}

Rimuove item dalla coda.

**Response 200:**
```json
{
    "deleted": true,
    "queue_id": 45,
    "errata_id": "USN-7234-1"
}
```

**Response 400:**
```json
{
    "error": "cannot_delete",
    "message": "Cannot delete item with status 'testing'. Abort test first."
}
```

### PATCH /api/v1/queue/{queue_id}

Modifica priorità o stato di un item.

**Request Body:**
```json
{
    "priority_override": 100,
    "status": "queued"
}
```

**Response 200:**
```json
{
    "queue_id": 45,
    "errata_id": "USN-7234-1",
    "priority_override": 100,
    "status": "queued",
    "new_position": 1
}
```

---

## 4. Test Execution

### POST /api/v1/test/start

Avvia test per prossimo item in coda o specifico.

**Request Body:**
```json
{
    "queue_id": null,
    "target_os": "ubuntu",
    "test_config": {
        "cpu_threshold": 20,
        "memory_threshold": 15,
        "max_failed_services": 0,
        "wait_after_patch_seconds": 300,
        "wait_after_reboot_seconds": 180,
        "critical_services": ["sshd", "salt-minion"]
    }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| queue_id | int | no | ID specifico (null = prossimo in coda) |
| target_os | string | yes* | Richiesto se queue_id è null |
| test_config | object | no | Override configurazione test |

**Response 201:**
```json
{
    "test_id": 123,
    "queue_id": 45,
    "errata_id": "USN-7234-1",
    "status": "testing",
    "current_phase": "snapshot_create",
    "test_system": {
        "id": 1001,
        "name": "test-ubuntu-01",
        "ip": "10.172.3.10"
    },
    "started_at": "2026-02-05T10:30:00Z",
    "estimated_duration_minutes": 15
}
```

**Response 409:**
```json
{
    "error": "test_already_running",
    "message": "A test is already running on test-ubuntu-01",
    "current_test_id": 122,
    "current_errata": "USN-7233-1"
}
```

**Response 404:**
```json
{
    "error": "no_items_in_queue",
    "message": "No items in queue for OS: ubuntu"
}
```

### GET /api/v1/test/{test_id}

Stato dettagliato test in corso o completato.

**Response 200 (in progress):**
```json
{
    "test_id": 123,
    "queue_id": 45,
    "errata_id": "USN-7234-1",
    "status": "testing",
    "current_phase": "collecting_post_metrics",
    "progress_percent": 75,
    "phases": [
        {
            "name": "snapshot_create",
            "status": "completed",
            "started_at": "2026-02-05T10:30:00Z",
            "completed_at": "2026-02-05T10:30:12Z",
            "duration_seconds": 12
        },
        {
            "name": "baseline_collect",
            "status": "completed",
            "started_at": "2026-02-05T10:30:12Z",
            "completed_at": "2026-02-05T10:30:42Z",
            "duration_seconds": 30
        },
        {
            "name": "patch_apply",
            "status": "completed",
            "started_at": "2026-02-05T10:30:42Z",
            "completed_at": "2026-02-05T10:31:27Z",
            "duration_seconds": 45
        },
        {
            "name": "stabilization_wait",
            "status": "completed",
            "started_at": "2026-02-05T10:31:27Z",
            "completed_at": "2026-02-05T10:36:27Z",
            "duration_seconds": 300
        },
        {
            "name": "post_metrics_collect",
            "status": "in_progress",
            "started_at": "2026-02-05T10:36:27Z",
            "completed_at": null,
            "duration_seconds": null
        },
        {
            "name": "evaluation",
            "status": "pending",
            "started_at": null,
            "completed_at": null,
            "duration_seconds": null
        }
    ],
    "test_system": {
        "id": 1001,
        "name": "test-ubuntu-01",
        "ip": "10.172.3.10"
    },
    "snapshot_id": "snapper-45",
    "started_at": "2026-02-05T10:30:00Z",
    "elapsed_seconds": 400
}
```

### GET /api/v1/test/{test_id}/result

Risultato completo test (solo se completato).

**Response 200:**
```json
{
    "test_id": 123,
    "queue_id": 45,
    "errata_id": "USN-7234-1",
    "result": "passed",
    "started_at": "2026-02-05T10:30:00Z",
    "completed_at": "2026-02-05T10:37:00Z",
    "duration_seconds": 420,
    "required_reboot": false,
    "reboot_performed": false,
    "metrics": {
        "baseline": {
            "cpu_avg": 15.2,
            "cpu_max": 22.5,
            "memory_percent": 45.0,
            "load_5m": 0.8,
            "services_running": 42,
            "services_failed": 0,
            "disk_read_mbps": 2.5,
            "disk_write_mbps": 1.2
        },
        "post_patch": {
            "cpu_avg": 16.1,
            "cpu_max": 24.0,
            "memory_percent": 46.2,
            "load_5m": 0.9,
            "services_running": 42,
            "services_failed": 0,
            "disk_read_mbps": 2.8,
            "disk_write_mbps": 1.5
        },
        "delta": {
            "cpu_delta_percent": 5.9,
            "memory_delta_percent": 2.7,
            "load_delta": 0.1,
            "services_delta": 0
        },
        "thresholds": {
            "cpu_threshold": 20,
            "memory_threshold": 15,
            "max_failed_services": 0
        },
        "evaluation": {
            "cpu_check": {"status": "pass", "value": 5.9, "threshold": 20},
            "memory_check": {"status": "pass", "value": 2.7, "threshold": 15},
            "services_check": {"status": "pass", "failed": 0, "threshold": 0},
            "overall": "pass"
        }
    },
    "services": {
        "critical_services": ["sshd", "salt-minion", "nginx", "postgresql"],
        "all_healthy": true,
        "details": [
            {"name": "sshd", "before": "running", "after": "running", "pid_changed": false},
            {"name": "salt-minion", "before": "running", "after": "running", "pid_changed": false},
            {"name": "nginx", "before": "running", "after": "running", "pid_changed": true},
            {"name": "postgresql", "before": "running", "after": "running", "pid_changed": false}
        ]
    },
    "snapshot": {
        "id": "snapper-45",
        "type": "snapper",
        "created_at": "2026-02-05T10:30:10Z",
        "size_mb": 150,
        "status": "retained"
    },
    "test_config": {
        "cpu_threshold": 20,
        "memory_threshold": 15,
        "max_failed_services": 0,
        "wait_after_patch_seconds": 300
    }
}
```

**Response 200 (failed):**
```json
{
    "test_id": 124,
    "queue_id": 46,
    "errata_id": "USN-7240-1",
    "result": "failed",
    "failure_reason": "Service postgresql failed to restart after patch",
    "duration_seconds": 380,
    "required_reboot": false,
    "rollback_performed": true,
    "rollback_type": "snapshot",
    "metrics": {
        "baseline": { ... },
        "post_patch": { ... },
        "evaluation": {
            "cpu_check": {"status": "pass"},
            "memory_check": {"status": "pass"},
            "services_check": {
                "status": "fail",
                "failed": 1,
                "threshold": 0,
                "failed_services": ["postgresql"]
            },
            "overall": "fail"
        }
    }
}
```

**Response 400:**
```json
{
    "error": "test_not_complete",
    "message": "Test 123 is still in progress",
    "current_status": "testing",
    "current_phase": "patch_apply"
}
```

### POST /api/v1/test/{test_id}/abort

Interrompe test in corso e fa rollback.

**Request Body (optional):**
```json
{
    "reason": "Manual abort by operator",
    "skip_rollback": false
}
```

**Response 200:**
```json
{
    "test_id": 123,
    "status": "aborted",
    "aborted_at": "2026-02-05T10:35:00Z",
    "aborted_phase": "stabilization_wait",
    "rollback_performed": true,
    "rollback_type": "snapshot",
    "rollback_status": "completed"
}
```

---

## 5. Approval Workflow

### GET /api/v1/approvals/pending

Lista patch in attesa approvazione.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| severity | string | null | Filtra per severity |
| os | string | null | Filtra per OS |
| sort | string | "pending_since" | Ordinamento |
| limit | int | 50 | Max risultati |

**Response 200:**
```json
{
    "items": [
        {
            "queue_id": 45,
            "errata_id": "USN-7234-1",
            "synopsis": "OpenSSL security update",
            "severity": "Critical",
            "success_score": 92,
            "target_os": "ubuntu",
            "test_id": 123,
            "test_result": "passed",
            "test_duration_seconds": 420,
            "tested_at": "2026-02-05T11:00:00Z",
            "metrics_summary": {
                "cpu_delta": "+5.9%",
                "memory_delta": "+2.7%",
                "services_ok": true,
                "reboot_required": false
            },
            "pending_since": "2026-02-05T11:00:00Z",
            "days_pending": 0,
            "packages": [
                {"name": "openssl", "version": "3.0.2-0ubuntu1.14"},
                {"name": "libssl3", "version": "3.0.2-0ubuntu1.14"}
            ],
            "cves": ["CVE-2026-1234", "CVE-2026-1235"]
        }
    ],
    "total": 8,
    "by_severity": {
        "Critical": 2,
        "High": 4,
        "Medium": 2,
        "Low": 0
    }
}
```

### POST /api/v1/approvals/{queue_id}/approve

Approva patch per produzione.

**Request Body:**
```json
{
    "approved_by": "operator@example.com",
    "reason": "Test passed, approved for production",
    "schedule_deployment": true,
    "deployment_window": "2026-02-06T02:00:00Z",
    "target_systems": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| approved_by | string | yes | Email/username operatore |
| reason | string | no | Motivo approvazione |
| schedule_deployment | bool | no | Crea deployment automatico |
| deployment_window | datetime | no | Quando deployare |
| target_systems | array | no | IDs sistemi (null = tutti prod) |

**Response 200:**
```json
{
    "approval_id": 78,
    "queue_id": 45,
    "errata_id": "USN-7234-1",
    "action": "approved",
    "approved_by": "operator@example.com",
    "approved_at": "2026-02-05T14:00:00Z",
    "deployment": {
        "deployment_id": 34,
        "status": "scheduled",
        "scheduled_at": "2026-02-06T02:00:00Z",
        "target_systems_count": 15
    }
}
```

### POST /api/v1/approvals/{queue_id}/reject

Rifiuta patch.

**Request Body:**
```json
{
    "rejected_by": "operator@example.com",
    "reason": "Not applicable to our environment - we don't use this component"
}
```

**Response 200:**
```json
{
    "approval_id": 79,
    "queue_id": 46,
    "errata_id": "USN-7235-2",
    "action": "rejected",
    "rejected_by": "operator@example.com",
    "rejected_at": "2026-02-05T14:05:00Z",
    "reason": "Not applicable to our environment"
}
```

### POST /api/v1/approvals/{queue_id}/snooze

Posticipa decisione.

**Request Body:**
```json
{
    "snoozed_by": "operator@example.com",
    "snooze_days": 7,
    "reason": "Waiting for vendor clarification on compatibility"
}
```

**Response 200:**
```json
{
    "approval_id": 80,
    "queue_id": 47,
    "errata_id": "USN-7236-1",
    "action": "snoozed",
    "snoozed_by": "operator@example.com",
    "snoozed_at": "2026-02-05T14:10:00Z",
    "snooze_until": "2026-02-12T14:10:00Z",
    "reason": "Waiting for vendor clarification"
}
```

### POST /api/v1/approvals/batch

Approva/Rifiuta multiple patch.

**Request Body:**
```json
{
    "action": "approve",
    "queue_ids": [45, 46, 47],
    "approved_by": "operator@example.com",
    "reason": "Batch approval - all tests passed, standard security patches",
    "schedule_deployment": true,
    "deployment_window": "2026-02-06T02:00:00Z"
}
```

**Response 200:**
```json
{
    "processed": 3,
    "succeeded": 3,
    "failed": 0,
    "results": [
        {"queue_id": 45, "approval_id": 81, "status": "approved"},
        {"queue_id": 46, "approval_id": 82, "status": "approved"},
        {"queue_id": 47, "approval_id": 83, "status": "approved"}
    ],
    "deployment": {
        "deployment_id": 35,
        "status": "scheduled",
        "scheduled_at": "2026-02-06T02:00:00Z",
        "errata_count": 3
    }
}
```

---

## 6. Deployment & Rollback

### GET /api/v1/deployments

Lista deployments.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| status | string | null | Filtra per stato |
| from_date | datetime | null | Data inizio |
| to_date | datetime | null | Data fine |
| limit | int | 50 | Max risultati |

**Response 200:**
```json
{
    "items": [
        {
            "deployment_id": 34,
            "errata_ids": ["USN-7234-1"],
            "status": "completed",
            "scheduled_at": "2026-02-06T02:00:00Z",
            "started_at": "2026-02-06T02:00:05Z",
            "completed_at": "2026-02-06T02:15:00Z",
            "total_systems": 15,
            "systems_succeeded": 15,
            "systems_failed": 0,
            "rollback_performed": false
        }
    ],
    "total": 28
}
```

### GET /api/v1/deployments/{deployment_id}

Stato dettagliato deployment.

**Response 200:**
```json
{
    "deployment_id": 34,
    "approval_id": 78,
    "errata_id": "USN-7234-1",
    "errata_synopsis": "OpenSSL security update",
    "status": "in_progress",
    "scheduled_at": "2026-02-06T02:00:00Z",
    "started_at": "2026-02-06T02:00:05Z",
    "completed_at": null,
    "target_systems": 15,
    "progress": {
        "completed": 10,
        "in_progress": 2,
        "pending": 3,
        "failed": 0
    },
    "systems": [
        {
            "id": 2001,
            "name": "prod-web-01",
            "ip": "10.172.4.10",
            "status": "completed",
            "started_at": "2026-02-06T02:00:05Z",
            "completed_at": "2026-02-06T02:02:30Z",
            "reboot_required": false
        },
        {
            "id": 2002,
            "name": "prod-web-02",
            "ip": "10.172.4.11",
            "status": "completed",
            "started_at": "2026-02-06T02:02:30Z",
            "completed_at": "2026-02-06T02:05:00Z",
            "reboot_required": false
        },
        {
            "id": 2003,
            "name": "prod-app-01",
            "ip": "10.172.4.20",
            "status": "in_progress",
            "started_at": "2026-02-06T02:10:00Z",
            "completed_at": null,
            "current_action": "Applying patch"
        }
    ],
    "estimated_completion": "2026-02-06T02:20:00Z"
}
```

### POST /api/v1/deployments/{deployment_id}/start

Avvia deployment manualmente (se schedulato).

**Response 200:**
```json
{
    "deployment_id": 34,
    "status": "in_progress",
    "started_at": "2026-02-06T02:00:05Z",
    "message": "Deployment started"
}
```

### POST /api/v1/rollback

Avvia rollback.

**Request Body:**
```json
{
    "deployment_id": 34,
    "rollback_type": "package",
    "target_systems": [2001, 2002],
    "reason": "Service X not responding after patch",
    "initiated_by": "operator@example.com"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| deployment_id | int | yes* | ID deployment (o errata_id) |
| errata_id | string | yes* | Errata da rollback |
| rollback_type | string | yes | 'package' o 'system' |
| target_systems | array | no | IDs sistemi (null = tutti affected) |
| reason | string | yes | Motivo rollback |
| initiated_by | string | yes | Chi ha richiesto |

**Response 201:**
```json
{
    "rollback_id": 12,
    "deployment_id": 34,
    "errata_id": "USN-7234-1",
    "rollback_type": "package",
    "status": "in_progress",
    "target_systems": 2,
    "started_at": "2026-02-06T14:00:00Z",
    "initiated_by": "operator@example.com",
    "reason": "Service X not responding after patch"
}
```

### GET /api/v1/rollback/{rollback_id}

Stato rollback.

**Response 200:**
```json
{
    "rollback_id": 12,
    "deployment_id": 34,
    "errata_id": "USN-7234-1",
    "rollback_type": "package",
    "status": "completed",
    "target_systems": 2,
    "started_at": "2026-02-06T14:00:00Z",
    "completed_at": "2026-02-06T14:05:00Z",
    "duration_seconds": 300,
    "systems_succeeded": 2,
    "systems_failed": 0,
    "results": [
        {
            "system_id": 2001,
            "system_name": "prod-web-01",
            "status": "completed",
            "packages_rolled_back": ["openssl", "libssl3"],
            "previous_versions": {
                "openssl": "3.0.2-0ubuntu1.14",
                "libssl3": "3.0.2-0ubuntu1.14"
            },
            "restored_versions": {
                "openssl": "3.0.2-0ubuntu1.13",
                "libssl3": "3.0.2-0ubuntu1.13"
            }
        }
    ]
}
```

---

## 7. Notifications

### GET /api/v1/notifications/config

Configurazione corrente notifiche.

**Response 200:**
```json
{
    "email": {
        "enabled": true,
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "smtp_tls": true,
        "from_address": "spm@example.com",
        "recipients": ["ops@example.com", "security@example.com"],
        "digest_enabled": true,
        "digest_time": "08:00",
        "alert_on_failure": true,
        "alert_on_pending": true
    },
    "webhook": {
        "enabled": false,
        "url": null,
        "auth_header": null,
        "events": ["test_failed", "pending_approval", "prod_failed"]
    }
}
```

### PUT /api/v1/notifications/config

Aggiorna configurazione.

**Request Body:**
```json
{
    "email": {
        "enabled": true,
        "recipients": ["ops@example.com", "security@example.com", "manager@example.com"],
        "digest_time": "09:00"
    },
    "webhook": {
        "enabled": true,
        "url": "https://hooks.example.com/spm",
        "auth_header": "Bearer xxx"
    }
}
```

**Response 200:**
```json
{
    "updated": true,
    "config": { ... }
}
```

### POST /api/v1/notifications/test

Invia notifica di test.

**Request Body:**
```json
{
    "channel": "email",
    "recipient": "test@example.com"
}
```

**Response 200:**
```json
{
    "sent": true,
    "channel": "email",
    "recipient": "test@example.com",
    "message_id": "abc123"
}
```

---

## 8. Reports

### GET /api/v1/reports/summary

Report riepilogativo.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| from_date | date | 30 days ago | Data inizio |
| to_date | date | today | Data fine |

**Response 200:**
```json
{
    "period": {
        "from": "2026-01-06",
        "to": "2026-02-05"
    },
    "patches": {
        "synced": 156,
        "tested": 145,
        "passed": 138,
        "failed": 7,
        "pass_rate": 95.2,
        "approved": 130,
        "rejected": 5,
        "snoozed": 3,
        "deployed": 125,
        "pending_approval": 8,
        "avg_approval_time_hours": 12.5
    },
    "by_severity": {
        "Critical": {"synced": 25, "deployed": 24, "pending": 1},
        "High": {"synced": 45, "deployed": 42, "pending": 3},
        "Medium": {"synced": 60, "deployed": 45, "pending": 3},
        "Low": {"synced": 26, "deployed": 14, "pending": 1}
    },
    "systems": {
        "test_systems": 2,
        "prod_systems": 15,
        "fully_patched": 12,
        "partially_patched": 2,
        "pending_patches": 1
    },
    "rollbacks": {
        "total": 2,
        "package_level": 2,
        "system_level": 0,
        "rollback_rate": 1.6
    },
    "test_metrics": {
        "total_tests": 145,
        "avg_duration_seconds": 420,
        "tests_requiring_reboot": 12,
        "auto_retry_count": 3
    }
}
```

### GET /api/v1/reports/compliance

Report compliance.

**Response 200:**
```json
{
    "generated_at": "2026-02-05T15:00:00Z",
    "overall_compliance": 87.5,
    "by_severity": {
        "critical": {
            "total_patches": 25,
            "applied": 24,
            "pending": 1,
            "rejected": 0,
            "compliance_percent": 96.0,
            "oldest_pending_days": 2
        },
        "high": {
            "total_patches": 45,
            "applied": 42,
            "pending": 2,
            "rejected": 1,
            "compliance_percent": 93.3,
            "oldest_pending_days": 5
        },
        "medium": { ... },
        "low": { ... }
    },
    "by_system": [
        {
            "system_id": 2001,
            "system_name": "prod-web-01",
            "os": "ubuntu",
            "total_applicable": 30,
            "applied": 28,
            "pending": 2,
            "compliance_percent": 93.3,
            "pending_critical": 0,
            "pending_high": 1,
            "last_patched": "2026-02-04T02:15:00Z"
        }
    ],
    "pending_patches": [
        {
            "errata_id": "USN-7250-1",
            "severity": "Critical",
            "synopsis": "Kernel security update",
            "days_pending": 2,
            "status": "pending_approval",
            "affected_systems": 15
        }
    ],
    "sla_status": {
        "critical_sla_days": 7,
        "critical_compliant": true,
        "high_sla_days": 14,
        "high_compliant": true,
        "medium_sla_days": 30,
        "medium_compliant": true
    }
}
```

---

## 9. Error Handling

### Standard Error Response

Tutti gli errori seguono questo formato:

```json
{
    "error": "error_code",
    "message": "Human readable message",
    "details": { ... },
    "timestamp": "2026-02-05T15:00:00Z",
    "request_id": "abc-123-def"
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `not_found` | 404 | Risorsa non trovata |
| `validation_error` | 400 | Validazione input fallita |
| `conflict` | 409 | Conflitto (es. test già in corso) |
| `test_already_running` | 409 | Un test è già in esecuzione |
| `cannot_delete` | 400 | Impossibile eliminare risorsa |
| `test_not_complete` | 400 | Test ancora in corso |
| `no_items_in_queue` | 404 | Coda vuota |
| `unauthorized` | 401 | Non autenticato |
| `forbidden` | 403 | Non autorizzato |
| `internal_error` | 500 | Errore interno |
| `service_unavailable` | 503 | Servizio non disponibile |
| `prometheus_error` | 502 | Errore comunicazione Prometheus |
| `uyuni_error` | 502 | Errore comunicazione UYUNI |
| `salt_error` | 502 | Errore comunicazione Salt |

### Validation Error Example

```json
{
    "error": "validation_error",
    "message": "Invalid request body",
    "details": {
        "fields": {
            "target_os": "Must be 'ubuntu' or 'rhel'",
            "errata_ids": "Must contain at least one errata ID"
        }
    },
    "timestamp": "2026-02-05T15:00:00Z"
}
```

---

## Appendix: Authentication

*Nota: L'autenticazione può essere implementata in fase successiva. Opzioni consigliate:*

- **API Key**: Header `X-API-Key` per automazione
- **JWT**: Per dashboard Streamlit con login
- **mTLS**: Per comunicazione tra servizi

---

## Changelog

| Versione | Data | Modifiche |
|----------|------|-----------|
| 1.0 | 2026-02-05 | Specifica iniziale |
