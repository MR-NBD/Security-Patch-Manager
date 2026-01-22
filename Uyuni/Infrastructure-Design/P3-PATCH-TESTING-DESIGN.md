# P3 - Patch Testing Design Document

## Overview

P3 implementa un sistema automatizzato di test delle patch in ambiente isolato prima del deployment in produzione.

## Workflow

```
[Errata con patch]
       ↓
┌──────────────────────────────────────────────────────────────────┐
│  1. SNAPSHOT SOURCE VM                                            │
│     - Azure: Create snapshot via Azure SDK                        │
│     - Salt: state.sls snapshot.create                            │
└───────────────────────┬──────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────────────────┐
│  2. CLONE TO SUBNET-TEST                                          │
│     - Create VM from snapshot in isolated subnet                  │
│     - Apply NSG rules (no internet, limited internal access)      │
│     - Configure monitoring agent                                  │
└───────────────────────┬──────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────────────────┐
│  3. BASELINE METRICS COLLECTION                                   │
│     - CPU, Memory, Disk I/O                                       │
│     - Network connections                                         │
│     - Running services                                            │
│     - Critical process list                                       │
└───────────────────────┬──────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────────────────┐
│  4. APPLY PATCH                                                   │
│     - Salt: state.apply patch.install                             │
│     - Wait for completion                                         │
│     - Reboot if required                                          │
└───────────────────────┬──────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────────────────┐
│  5. POST-PATCH METRICS COLLECTION                                 │
│     - Same metrics as baseline                                    │
│     - Service health check                                        │
│     - Application smoke tests                                     │
└───────────────────────┬──────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────────────────┐
│  6. EVALUATION                                                    │
│     - Compare baseline vs post-patch                              │
│     - Apply pass/fail criteria                                    │
│     - Generate test report                                        │
└───────────────────────┬──────────────────────────────────────────┘
                        ↓
              ┌─────────┴─────────┐
              ↓                   ↓
         [PASS]              [FAIL]
              ↓                   ↓
    ┌─────────────────┐   ┌─────────────────┐
    │ Auto-approve    │   │ Flag for manual │
    │ for deployment  │   │ review          │
    └────────┬────────┘   └────────┬────────┘
             ↓                     ↓
┌──────────────────────────────────────────────────────────────────┐
│  7. CLEANUP                                                       │
│     - Delete test VM                                              │
│     - Delete snapshot (optional, configurable retention)          │
│     - Archive test logs                                           │
└──────────────────────────────────────────────────────────────────┘
```

## Database Schema

### Nuove Tabelle

```sql
-- Tabella principale test patch
CREATE TABLE patch_tests (
    id SERIAL PRIMARY KEY,
    errata_id INTEGER REFERENCES errata(id),
    source_system_id INTEGER NOT NULL,       -- UYUNI system ID
    source_vm_name VARCHAR(255) NOT NULL,
    test_vm_name VARCHAR(255),
    snapshot_id VARCHAR(255),                -- Azure snapshot ID o Salt snapshot name

    -- Status tracking
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    -- pending, snapshot_creating, cloning, baseline_collecting,
    -- patching, post_metrics, evaluating, passed, failed,
    -- approved, rejected, cleanup, completed, error

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Configuration
    test_config JSONB DEFAULT '{}',
    -- {
    --   "timeout_minutes": 60,
    --   "reboot_allowed": true,
    --   "auto_approve_on_pass": false,
    --   "cleanup_on_complete": true,
    --   "retention_days": 7
    -- }

    -- Results
    result VARCHAR(20),                      -- pass, fail, error
    result_reason TEXT,
    test_report JSONB,

    -- Error handling
    error_message TEXT,
    retry_count INTEGER DEFAULT 0
);

CREATE INDEX idx_patch_tests_status ON patch_tests(status);
CREATE INDEX idx_patch_tests_errata ON patch_tests(errata_id);
CREATE INDEX idx_patch_tests_source ON patch_tests(source_system_id);

-- Metriche raccolte durante i test
CREATE TABLE patch_test_metrics (
    id SERIAL PRIMARY KEY,
    test_id INTEGER REFERENCES patch_tests(id) ON DELETE CASCADE,
    phase VARCHAR(20) NOT NULL,              -- baseline, post_patch
    collected_at TIMESTAMP DEFAULT NOW(),

    -- System metrics
    cpu_usage_avg DECIMAL(5,2),
    cpu_usage_max DECIMAL(5,2),
    memory_usage_percent DECIMAL(5,2),
    memory_used_mb INTEGER,
    disk_io_read_mbps DECIMAL(10,2),
    disk_io_write_mbps DECIMAL(10,2),

    -- Network metrics
    network_connections INTEGER,
    network_bytes_in BIGINT,
    network_bytes_out BIGINT,

    -- Service metrics
    services_running INTEGER,
    services_failed INTEGER,
    services_list JSONB,                     -- [{name, status, pid}]

    -- Process metrics
    critical_processes_ok BOOLEAN,
    processes_list JSONB,                    -- [{name, pid, cpu, mem}]

    -- Custom checks
    custom_checks JSONB                      -- [{name, result, output}]
);

CREATE INDEX idx_test_metrics_test ON patch_test_metrics(test_id);
CREATE INDEX idx_test_metrics_phase ON patch_test_metrics(phase);

-- Log eventi del test
CREATE TABLE patch_test_events (
    id SERIAL PRIMARY KEY,
    test_id INTEGER REFERENCES patch_tests(id) ON DELETE CASCADE,
    event_time TIMESTAMP DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    event_message TEXT,
    event_data JSONB
);

CREATE INDEX idx_test_events_test ON patch_test_events(test_id);
```

## API Endpoints

### POST /api/patch-test/start

Avvia un nuovo test patch.

**Request:**
```json
{
    "errata_id": 123,
    "system_id": 456,
    "config": {
        "timeout_minutes": 60,
        "reboot_allowed": true,
        "auto_approve_on_pass": false,
        "cleanup_on_complete": true,
        "custom_checks": [
            {
                "name": "nginx_running",
                "command": "systemctl is-active nginx",
                "expected_output": "active"
            }
        ]
    }
}
```

**Response:**
```json
{
    "status": "started",
    "test_id": 789,
    "estimated_duration_minutes": 45
}
```

### GET /api/patch-test/status/{test_id}

Ottiene lo stato di un test.

**Response:**
```json
{
    "test_id": 789,
    "status": "post_metrics",
    "progress_percent": 75,
    "current_phase": "Collecting post-patch metrics",
    "started_at": "2026-01-22T10:00:00Z",
    "elapsed_minutes": 34,
    "events": [
        {"time": "...", "type": "snapshot_created", "message": "..."},
        {"time": "...", "type": "clone_created", "message": "..."},
        {"time": "...", "type": "baseline_collected", "message": "..."},
        {"time": "...", "type": "patch_applied", "message": "..."}
    ]
}
```

### GET /api/patch-test/result/{test_id}

Ottiene il risultato completo di un test.

**Response:**
```json
{
    "test_id": 789,
    "status": "passed",
    "result": "pass",
    "result_reason": "All metrics within acceptable thresholds",
    "duration_minutes": 42,
    "metrics_comparison": {
        "cpu": {
            "baseline_avg": 15.2,
            "post_patch_avg": 16.1,
            "delta_percent": 5.9,
            "threshold_percent": 20,
            "status": "pass"
        },
        "memory": {
            "baseline_percent": 45.3,
            "post_patch_percent": 46.8,
            "delta_percent": 3.3,
            "threshold_percent": 15,
            "status": "pass"
        },
        "services": {
            "baseline_running": 42,
            "post_patch_running": 42,
            "failed_services": [],
            "status": "pass"
        },
        "custom_checks": {
            "nginx_running": {"status": "pass", "output": "active"},
            "db_connection": {"status": "pass", "output": "OK"}
        }
    },
    "recommendation": "auto_approve"
}
```

### POST /api/patch-test/approve/{test_id}

Approva una patch testata per il deployment.

**Response:**
```json
{
    "status": "approved",
    "test_id": 789,
    "errata_id": 123,
    "next_step": "ready_for_deployment"
}
```

### POST /api/patch-test/reject/{test_id}

Rigetta una patch dopo il test.

**Request:**
```json
{
    "reason": "Service X failed to restart after patch"
}
```

### POST /api/patch-test/cleanup/{test_id}

Forza cleanup manuale di un test.

### GET /api/patch-test/list

Lista tutti i test con filtri.

**Query params:** `status`, `errata_id`, `system_id`, `limit`, `offset`

## Pass/Fail Criteria

### Criteri Automatici (configurabili)

| Criterio | Default | Descrizione |
|----------|---------|-------------|
| CPU delta | ≤20% | Incremento CPU post-patch vs baseline |
| Memory delta | ≤15% | Incremento memoria post-patch vs baseline |
| Service failures | 0 | Servizi che falliscono dopo patch |
| Critical processes | All running | Processi critici devono essere attivi |
| Reboot success | Yes | Se reboot richiesto, VM deve tornare online |
| Custom checks | All pass | Tutti i check custom devono passare |

### Risultati Possibili

- **PASS**: Tutti i criteri soddisfatti → auto-approve (se configurato) o ready for manual approval
- **FAIL**: Uno o più criteri non soddisfatti → richiede review manuale
- **ERROR**: Errore durante il test → richiede investigazione

## Integrazione con Componenti Esistenti

### Salt Integration

```python
# Comandi Salt per P3
SALT_COMMANDS = {
    'snapshot_create': 'salt-call state.sls snapshot.create',
    'snapshot_restore': 'salt-call state.sls snapshot.restore',
    'snapshot_delete': 'salt-call state.sls snapshot.delete',
    'metrics_collect': 'salt-call state.sls monitoring.collect',
    'patch_apply': 'salt-call state.apply',
    'service_check': 'salt-call service.get_running',
    'reboot': 'salt-call system.reboot',
}
```

### Azure Integration

```python
# Azure SDK per P3
from azure.mgmt.compute import ComputeManagementClient
from azure.identity import DefaultAzureCredential

def create_snapshot(vm_name, resource_group):
    credential = DefaultAzureCredential()
    compute_client = ComputeManagementClient(credential, subscription_id)

    # Get VM disk
    vm = compute_client.virtual_machines.get(resource_group, vm_name)
    disk_id = vm.storage_profile.os_disk.managed_disk.id

    # Create snapshot
    snapshot = compute_client.snapshots.begin_create_or_update(
        resource_group,
        f"{vm_name}-patch-test-{timestamp}",
        {
            'location': vm.location,
            'creation_data': {
                'create_option': 'Copy',
                'source_resource_id': disk_id
            }
        }
    )
    return snapshot.result()
```

### UYUNI Integration

```python
# Mapping sistema UYUNI → VM Azure
def get_azure_vm_for_system(uyuni_system_id):
    client, session = get_uyuni_client()
    system_details = client.system.getDetails(session, uyuni_system_id)

    # Cerca VM Azure tramite hostname o custom info
    hostname = system_details['hostname']
    custom_info = client.system.getCustomValues(session, uyuni_system_id)
    azure_vm_id = custom_info.get('azure_vm_id', None)

    return {
        'hostname': hostname,
        'azure_vm_id': azure_vm_id,
        'resource_group': custom_info.get('azure_rg'),
        'vm_name': custom_info.get('azure_vm_name', hostname)
    }
```

## Configurazione

### Environment Variables

```bash
# Azure
AZURE_SUBSCRIPTION_ID=
AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
AZURE_TEST_SUBNET_ID=

# Salt
SALT_MASTER_URL=
SALT_API_USER=
SALT_API_PASSWORD=

# P3 Config
P3_DEFAULT_TIMEOUT_MINUTES=60
P3_SNAPSHOT_RETENTION_DAYS=7
P3_AUTO_CLEANUP=true
P3_MAX_CONCURRENT_TESTS=5
```

### Test Configuration Template

```json
{
    "timeout_minutes": 60,
    "reboot_allowed": true,
    "auto_approve_on_pass": false,
    "cleanup_on_complete": true,
    "retention_days": 7,
    "thresholds": {
        "cpu_delta_percent": 20,
        "memory_delta_percent": 15,
        "max_service_failures": 0
    },
    "critical_services": [
        "ssh",
        "salt-minion"
    ],
    "critical_processes": [
        "systemd",
        "sshd"
    ],
    "custom_checks": []
}
```

## Logging e Audit

Tutti gli eventi P3 vengono tracciati per compliance:

```python
def log_test_event(test_id, event_type, message, data=None):
    cur.execute("""
        INSERT INTO patch_test_events (test_id, event_type, event_message, event_data)
        VALUES (%s, %s, %s, %s)
    """, (test_id, event_type, message, json.dumps(data) if data else None))
```

## Error Handling

### Retry Logic

- Snapshot creation: max 3 tentativi con backoff
- Clone creation: max 3 tentativi
- Metrics collection: max 2 tentativi
- Patch application: NO retry (too risky)

### Timeout Handling

Se un test supera il timeout:
1. Log timeout event
2. Set status = 'error'
3. Attempt cleanup
4. Notify administrator

### Cleanup on Failure

Anche in caso di errore, il cleanup viene sempre tentato:
1. Delete test VM (se esiste)
2. Delete snapshot (se configurato)
3. Archive logs
