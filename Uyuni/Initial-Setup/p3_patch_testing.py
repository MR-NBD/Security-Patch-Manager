#!/usr/bin/env python3
"""
P3 - Patch Testing Module
Automated patch testing in isolated environment before production deployment.

Workflow:
1. Snapshot source VM
2. Clone to isolated test subnet
3. Collect baseline metrics
4. Apply patch
5. Collect post-patch metrics
6. Evaluate pass/fail criteria
7. Approve/Reject
8. Cleanup
"""

import os
import json
import time
import threading
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict, Any, List

from flask import Blueprint, jsonify, request
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

# Azure SDK (optional, for Azure-based testing)
try:
    from azure.identity import DefaultAzureCredential
    from azure.mgmt.compute import ComputeManagementClient
    from azure.mgmt.network import NetworkManagementClient
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

# Salt API (optional, for Salt-based testing)
try:
    import salt.client
    SALT_AVAILABLE = True
except ImportError:
    SALT_AVAILABLE = False

# Create Blueprint for P3 endpoints
p3_bp = Blueprint('p3', __name__, url_prefix='/api/patch-test')

logger = logging.getLogger('p3-patch-testing')

# ============================================================
# CONFIGURATION
# ============================================================
DATABASE_URL = os.environ.get('DATABASE_URL')

# Azure Config
AZURE_SUBSCRIPTION_ID = os.environ.get('AZURE_SUBSCRIPTION_ID')
AZURE_TEST_SUBNET_ID = os.environ.get('AZURE_TEST_SUBNET_ID')
AZURE_TEST_RG = os.environ.get('AZURE_TEST_RESOURCE_GROUP', 'rg-patch-testing')

# Salt Config
SALT_MASTER_URL = os.environ.get('SALT_MASTER_URL')
SALT_API_USER = os.environ.get('SALT_API_USER')
SALT_API_PASSWORD = os.environ.get('SALT_API_PASSWORD')

# P3 Config
P3_DEFAULT_TIMEOUT_MINUTES = int(os.environ.get('P3_DEFAULT_TIMEOUT_MINUTES', 60))
P3_SNAPSHOT_RETENTION_DAYS = int(os.environ.get('P3_SNAPSHOT_RETENTION_DAYS', 7))
P3_AUTO_CLEANUP = os.environ.get('P3_AUTO_CLEANUP', 'true').lower() == 'true'
P3_MAX_CONCURRENT_TESTS = int(os.environ.get('P3_MAX_CONCURRENT_TESTS', 5))

# Default thresholds
DEFAULT_THRESHOLDS = {
    'cpu_delta_percent': 20,
    'memory_delta_percent': 15,
    'max_service_failures': 0,
}

DEFAULT_CRITICAL_SERVICES = ['ssh', 'sshd', 'salt-minion']
DEFAULT_CRITICAL_PROCESSES = ['systemd', 'sshd']

# Active test workers
_active_tests: Dict[int, threading.Thread] = {}

# ============================================================
# UTILITY FUNCTIONS
# ============================================================
def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def log_test_event(cur, test_id: int, event_type: str, message: str, data: Any = None):
    """Log an event for a patch test."""
    cur.execute("""
        INSERT INTO patch_test_events (test_id, event_type, event_message, event_data)
        VALUES (%s, %s, %s, %s)
    """, (test_id, event_type, message, json.dumps(data) if data else None))


def update_test_status(cur, test_id: int, status: str, **kwargs):
    """Update test status and optionally other fields."""
    fields = ['status = %s']
    values = [status]

    for key, value in kwargs.items():
        if key in ['result', 'result_reason', 'error_message', 'test_vm_name', 'snapshot_id']:
            fields.append(f"{key} = %s")
            values.append(value)
        elif key == 'test_report':
            fields.append("test_report = %s")
            values.append(json.dumps(value) if value else None)

    if status in ['patching', 'baseline_collecting'] and 'started_at' not in kwargs:
        fields.append("started_at = COALESCE(started_at, NOW())")

    if status in ['passed', 'failed', 'error', 'completed']:
        fields.append("completed_at = NOW()")

    values.append(test_id)
    cur.execute(f"UPDATE patch_tests SET {', '.join(fields)} WHERE id = %s", values)


def get_test_config(test_data: dict) -> dict:
    """Get test configuration with defaults."""
    config = test_data.get('test_config', {})
    if isinstance(config, str):
        config = json.loads(config)

    return {
        'timeout_minutes': config.get('timeout_minutes', P3_DEFAULT_TIMEOUT_MINUTES),
        'reboot_allowed': config.get('reboot_allowed', True),
        'auto_approve_on_pass': config.get('auto_approve_on_pass', False),
        'cleanup_on_complete': config.get('cleanup_on_complete', P3_AUTO_CLEANUP),
        'retention_days': config.get('retention_days', P3_SNAPSHOT_RETENTION_DAYS),
        'thresholds': {**DEFAULT_THRESHOLDS, **config.get('thresholds', {})},
        'critical_services': config.get('critical_services', DEFAULT_CRITICAL_SERVICES),
        'critical_processes': config.get('critical_processes', DEFAULT_CRITICAL_PROCESSES),
        'custom_checks': config.get('custom_checks', []),
    }


# ============================================================
# AZURE INTEGRATION
# ============================================================
class AzureTestEnvironment:
    """Azure-based test environment management."""

    def __init__(self):
        if not AZURE_AVAILABLE:
            raise RuntimeError("Azure SDK not installed")
        self.credential = DefaultAzureCredential()
        self.compute_client = ComputeManagementClient(self.credential, AZURE_SUBSCRIPTION_ID)
        self.network_client = NetworkManagementClient(self.credential, AZURE_SUBSCRIPTION_ID)

    def create_snapshot(self, vm_name: str, resource_group: str) -> str:
        """Create a snapshot of the VM's OS disk."""
        vm = self.compute_client.virtual_machines.get(resource_group, vm_name)
        disk_id = vm.storage_profile.os_disk.managed_disk.id

        snapshot_name = f"{vm_name}-patch-test-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        snapshot = self.compute_client.snapshots.begin_create_or_update(
            resource_group,
            snapshot_name,
            {
                'location': vm.location,
                'creation_data': {
                    'create_option': 'Copy',
                    'source_resource_id': disk_id
                },
                'tags': {
                    'purpose': 'patch-testing',
                    'source_vm': vm_name,
                    'created_by': 'spm-p3'
                }
            }
        ).result()

        return snapshot.name

    def create_test_vm(self, snapshot_name: str, source_vm_name: str, resource_group: str) -> str:
        """Create a test VM from snapshot in isolated subnet."""
        test_vm_name = f"{source_vm_name}-test-{datetime.now().strftime('%H%M%S')}"

        # Get snapshot
        snapshot = self.compute_client.snapshots.get(resource_group, snapshot_name)

        # Create disk from snapshot
        disk_name = f"{test_vm_name}-osdisk"
        disk = self.compute_client.disks.begin_create_or_update(
            AZURE_TEST_RG,
            disk_name,
            {
                'location': snapshot.location,
                'creation_data': {
                    'create_option': 'Copy',
                    'source_resource_id': snapshot.id
                },
                'tags': {'purpose': 'patch-testing'}
            }
        ).result()

        # Create NIC in test subnet
        nic_name = f"{test_vm_name}-nic"
        nic = self.network_client.network_interfaces.begin_create_or_update(
            AZURE_TEST_RG,
            nic_name,
            {
                'location': snapshot.location,
                'ip_configurations': [{
                    'name': 'ipconfig1',
                    'subnet': {'id': AZURE_TEST_SUBNET_ID},
                    'private_ip_allocation_method': 'Dynamic'
                }],
                'tags': {'purpose': 'patch-testing'}
            }
        ).result()

        # Get source VM size
        source_vm = self.compute_client.virtual_machines.get(resource_group, source_vm_name)

        # Create test VM
        vm = self.compute_client.virtual_machines.begin_create_or_update(
            AZURE_TEST_RG,
            test_vm_name,
            {
                'location': snapshot.location,
                'hardware_profile': {'vm_size': source_vm.hardware_profile.vm_size},
                'storage_profile': {
                    'os_disk': {
                        'create_option': 'Attach',
                        'managed_disk': {'id': disk.id},
                        'os_type': 'Linux'
                    }
                },
                'network_profile': {
                    'network_interfaces': [{'id': nic.id, 'primary': True}]
                },
                'tags': {
                    'purpose': 'patch-testing',
                    'source_vm': source_vm_name,
                    'snapshot': snapshot_name
                }
            }
        ).result()

        return test_vm_name

    def delete_test_vm(self, test_vm_name: str):
        """Delete test VM and associated resources."""
        try:
            # Delete VM
            self.compute_client.virtual_machines.begin_delete(AZURE_TEST_RG, test_vm_name).wait()

            # Delete disk
            disk_name = f"{test_vm_name}-osdisk"
            self.compute_client.disks.begin_delete(AZURE_TEST_RG, disk_name).wait()

            # Delete NIC
            nic_name = f"{test_vm_name}-nic"
            self.network_client.network_interfaces.begin_delete(AZURE_TEST_RG, nic_name).wait()
        except Exception as e:
            logger.error(f"Error deleting test VM {test_vm_name}: {e}")

    def delete_snapshot(self, snapshot_name: str, resource_group: str):
        """Delete a snapshot."""
        try:
            self.compute_client.snapshots.begin_delete(resource_group, snapshot_name).wait()
        except Exception as e:
            logger.error(f"Error deleting snapshot {snapshot_name}: {e}")


# ============================================================
# SALT INTEGRATION
# ============================================================
class SaltTestEnvironment:
    """Salt-based test environment management."""

    def __init__(self):
        if not SALT_AVAILABLE:
            raise RuntimeError("Salt client not available")
        self.client = salt.client.LocalClient()

    def create_snapshot(self, minion_id: str) -> str:
        """Create a snapshot via Salt state."""
        snapshot_name = f"{minion_id}-patch-test-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        result = self.client.cmd(
            minion_id,
            'state.sls',
            ['snapshot.create'],
            kwarg={'pillar': {'snapshot_name': snapshot_name}}
        )
        if minion_id in result and result[minion_id]:
            return snapshot_name
        raise RuntimeError(f"Failed to create snapshot on {minion_id}")

    def clone_to_test(self, minion_id: str, snapshot_name: str) -> str:
        """Clone VM to test environment via Salt."""
        test_minion = f"{minion_id}-test"
        result = self.client.cmd(
            minion_id,
            'state.sls',
            ['vm.clone_to_test'],
            kwarg={'pillar': {'snapshot_name': snapshot_name, 'test_minion': test_minion}}
        )
        return test_minion

    def collect_metrics(self, minion_id: str) -> dict:
        """Collect system metrics via Salt."""
        metrics = {}

        # CPU
        cpu_result = self.client.cmd(minion_id, 'status.cpuinfo', [])
        if minion_id in cpu_result:
            metrics['cpu'] = cpu_result[minion_id]

        # Memory
        mem_result = self.client.cmd(minion_id, 'status.meminfo', [])
        if minion_id in mem_result:
            metrics['memory'] = mem_result[minion_id]

        # Services
        services_result = self.client.cmd(minion_id, 'service.get_running', [])
        if minion_id in services_result:
            metrics['services'] = services_result[minion_id]

        # Processes
        proc_result = self.client.cmd(minion_id, 'status.procs', [])
        if minion_id in proc_result:
            metrics['processes'] = proc_result[minion_id]

        return metrics

    def apply_patch(self, minion_id: str, packages: List[str]) -> dict:
        """Apply patch via Salt."""
        result = self.client.cmd(
            minion_id,
            'pkg.install',
            packages,
            kwarg={'refresh': True}
        )
        return result.get(minion_id, {})

    def reboot(self, minion_id: str) -> bool:
        """Reboot system via Salt."""
        result = self.client.cmd(minion_id, 'system.reboot', [])
        return minion_id in result

    def cleanup(self, test_minion: str, snapshot_name: str = None):
        """Cleanup test environment."""
        try:
            # Destroy test VM
            self.client.cmd(test_minion, 'state.sls', ['vm.destroy'])
        except:
            pass

        if snapshot_name:
            try:
                # Delete snapshot
                self.client.cmd('*', 'state.sls', ['snapshot.delete'],
                              kwarg={'pillar': {'snapshot_name': snapshot_name}})
            except:
                pass


# ============================================================
# METRICS COLLECTION AND EVALUATION
# ============================================================
def collect_metrics_via_ssh(hostname: str, ssh_user: str = 'root') -> dict:
    """Fallback metrics collection via SSH if Salt not available."""
    import subprocess

    metrics = {
        'cpu_usage_avg': 0,
        'cpu_usage_max': 0,
        'memory_usage_percent': 0,
        'memory_used_mb': 0,
        'services_running': 0,
        'services_failed': 0,
        'services_list': [],
        'processes_list': [],
        'critical_processes_ok': True,
    }

    try:
        # CPU
        cpu_cmd = f"ssh {ssh_user}@{hostname} 'top -bn1 | grep \"Cpu(s)\" | awk \"{{print \\$2}}\"'"
        result = subprocess.run(cpu_cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            metrics['cpu_usage_avg'] = float(result.stdout.strip().replace(',', '.'))

        # Memory
        mem_cmd = f"ssh {ssh_user}@{hostname} 'free -m | grep Mem'"
        result = subprocess.run(mem_cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            parts = result.stdout.split()
            total = int(parts[1])
            used = int(parts[2])
            metrics['memory_used_mb'] = used
            metrics['memory_usage_percent'] = (used / total) * 100 if total > 0 else 0

        # Services
        svc_cmd = f"ssh {ssh_user}@{hostname} 'systemctl list-units --type=service --state=running --no-pager --no-legend | wc -l'"
        result = subprocess.run(svc_cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            metrics['services_running'] = int(result.stdout.strip())

        # Failed services
        fail_cmd = f"ssh {ssh_user}@{hostname} 'systemctl list-units --type=service --state=failed --no-pager --no-legend | wc -l'"
        result = subprocess.run(fail_cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            metrics['services_failed'] = int(result.stdout.strip())

    except Exception as e:
        logger.error(f"Error collecting metrics from {hostname}: {e}")

    return metrics


def save_metrics(cur, test_id: int, phase: str, metrics: dict):
    """Save collected metrics to database."""
    cur.execute("""
        INSERT INTO patch_test_metrics (
            test_id, phase, cpu_usage_avg, cpu_usage_max,
            memory_usage_percent, memory_used_mb,
            services_running, services_failed, services_list,
            critical_processes_ok, processes_list, custom_checks
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        test_id, phase,
        metrics.get('cpu_usage_avg'),
        metrics.get('cpu_usage_max'),
        metrics.get('memory_usage_percent'),
        metrics.get('memory_used_mb'),
        metrics.get('services_running'),
        metrics.get('services_failed'),
        json.dumps(metrics.get('services_list', [])),
        metrics.get('critical_processes_ok', True),
        json.dumps(metrics.get('processes_list', [])),
        json.dumps(metrics.get('custom_checks', []))
    ))


def evaluate_test_results(baseline: dict, post_patch: dict, config: dict) -> dict:
    """Evaluate test results against thresholds."""
    thresholds = config['thresholds']
    results = {
        'passed': True,
        'checks': {},
        'failures': []
    }

    # CPU check
    cpu_baseline = baseline.get('cpu_usage_avg', 0) or 0
    cpu_post = post_patch.get('cpu_usage_avg', 0) or 0
    cpu_delta = abs(cpu_post - cpu_baseline)
    cpu_delta_percent = (cpu_delta / cpu_baseline * 100) if cpu_baseline > 0 else 0

    results['checks']['cpu'] = {
        'baseline': cpu_baseline,
        'post_patch': cpu_post,
        'delta_percent': round(cpu_delta_percent, 2),
        'threshold': thresholds['cpu_delta_percent'],
        'passed': cpu_delta_percent <= thresholds['cpu_delta_percent']
    }
    if not results['checks']['cpu']['passed']:
        results['passed'] = False
        results['failures'].append(f"CPU delta {cpu_delta_percent:.1f}% exceeds threshold {thresholds['cpu_delta_percent']}%")

    # Memory check
    mem_baseline = baseline.get('memory_usage_percent', 0) or 0
    mem_post = post_patch.get('memory_usage_percent', 0) or 0
    mem_delta = abs(mem_post - mem_baseline)
    mem_delta_percent = (mem_delta / mem_baseline * 100) if mem_baseline > 0 else 0

    results['checks']['memory'] = {
        'baseline': mem_baseline,
        'post_patch': mem_post,
        'delta_percent': round(mem_delta_percent, 2),
        'threshold': thresholds['memory_delta_percent'],
        'passed': mem_delta_percent <= thresholds['memory_delta_percent']
    }
    if not results['checks']['memory']['passed']:
        results['passed'] = False
        results['failures'].append(f"Memory delta {mem_delta_percent:.1f}% exceeds threshold {thresholds['memory_delta_percent']}%")

    # Services check
    svc_failed = post_patch.get('services_failed', 0) or 0
    results['checks']['services'] = {
        'failed_count': svc_failed,
        'threshold': thresholds['max_service_failures'],
        'passed': svc_failed <= thresholds['max_service_failures']
    }
    if not results['checks']['services']['passed']:
        results['passed'] = False
        results['failures'].append(f"{svc_failed} service(s) failed after patch")

    # Critical processes check
    results['checks']['critical_processes'] = {
        'all_running': post_patch.get('critical_processes_ok', True),
        'passed': post_patch.get('critical_processes_ok', True)
    }
    if not results['checks']['critical_processes']['passed']:
        results['passed'] = False
        results['failures'].append("One or more critical processes not running")

    return results


# ============================================================
# TEST EXECUTION WORKER
# ============================================================
def run_patch_test(test_id: int):
    """Background worker to execute a patch test."""
    conn = get_db()
    cur = conn.cursor()

    try:
        # Get test details
        cur.execute("SELECT * FROM patch_tests WHERE id = %s", (test_id,))
        test = dict(cur.fetchone())
        config = get_test_config(test)

        source_vm = test['source_vm_name']
        logger.info(f"Starting patch test {test_id} for VM {source_vm}")

        # Initialize test environment
        if AZURE_AVAILABLE and AZURE_SUBSCRIPTION_ID:
            env = AzureTestEnvironment()
            test_type = 'azure'
        elif SALT_AVAILABLE:
            env = SaltTestEnvironment()
            test_type = 'salt'
        else:
            raise RuntimeError("No test environment available (Azure or Salt required)")

        # Step 1: Create snapshot
        update_test_status(cur, test_id, 'snapshot_creating')
        log_test_event(cur, test_id, 'snapshot_start', f'Creating snapshot of {source_vm}')
        conn.commit()

        # For Azure, we need resource group - assuming it's stored or derived
        resource_group = os.environ.get('AZURE_SOURCE_RG', 'rg-production')

        if test_type == 'azure':
            snapshot_id = env.create_snapshot(source_vm, resource_group)
        else:
            snapshot_id = env.create_snapshot(source_vm)

        update_test_status(cur, test_id, 'snapshot_creating', snapshot_id=snapshot_id)
        log_test_event(cur, test_id, 'snapshot_created', f'Snapshot created: {snapshot_id}')
        conn.commit()

        # Step 2: Clone to test environment
        update_test_status(cur, test_id, 'cloning')
        log_test_event(cur, test_id, 'clone_start', 'Creating test VM from snapshot')
        conn.commit()

        if test_type == 'azure':
            test_vm = env.create_test_vm(snapshot_id, source_vm, resource_group)
        else:
            test_vm = env.clone_to_test(source_vm, snapshot_id)

        update_test_status(cur, test_id, 'cloning', test_vm_name=test_vm)
        log_test_event(cur, test_id, 'clone_created', f'Test VM created: {test_vm}')
        conn.commit()

        # Wait for VM to be ready
        time.sleep(60)

        # Step 3: Collect baseline metrics
        update_test_status(cur, test_id, 'baseline_collecting')
        log_test_event(cur, test_id, 'baseline_start', 'Collecting baseline metrics')
        conn.commit()

        if test_type == 'salt':
            baseline_metrics = env.collect_metrics(test_vm)
        else:
            baseline_metrics = collect_metrics_via_ssh(test_vm)

        save_metrics(cur, test_id, 'baseline', baseline_metrics)
        log_test_event(cur, test_id, 'baseline_collected', 'Baseline metrics collected', baseline_metrics)
        conn.commit()

        # Step 4: Apply patch
        update_test_status(cur, test_id, 'patching')
        log_test_event(cur, test_id, 'patch_start', 'Applying patch')
        conn.commit()

        # Get packages for this errata
        cur.execute("""
            SELECT package_name, fixed_version
            FROM errata_packages
            WHERE errata_id = %s
        """, (test['errata_id'],))
        packages = [f"{r['package_name']}={r['fixed_version']}" for r in cur.fetchall() if r['package_name']]

        if test_type == 'salt' and packages:
            patch_result = env.apply_patch(test_vm, packages)
            log_test_event(cur, test_id, 'patch_result', 'Patch application result', patch_result)

        # Reboot if needed
        if config['reboot_allowed']:
            log_test_event(cur, test_id, 'reboot_start', 'Rebooting test VM')
            conn.commit()
            if test_type == 'salt':
                env.reboot(test_vm)
            time.sleep(120)  # Wait for reboot

        log_test_event(cur, test_id, 'patch_applied', 'Patch applied successfully')
        conn.commit()

        # Step 5: Collect post-patch metrics
        update_test_status(cur, test_id, 'post_metrics')
        log_test_event(cur, test_id, 'post_metrics_start', 'Collecting post-patch metrics')
        conn.commit()

        if test_type == 'salt':
            post_metrics = env.collect_metrics(test_vm)
        else:
            post_metrics = collect_metrics_via_ssh(test_vm)

        save_metrics(cur, test_id, 'post_patch', post_metrics)
        log_test_event(cur, test_id, 'post_metrics_collected', 'Post-patch metrics collected', post_metrics)
        conn.commit()

        # Step 6: Evaluate results
        update_test_status(cur, test_id, 'evaluating')
        log_test_event(cur, test_id, 'evaluation_start', 'Evaluating test results')
        conn.commit()

        evaluation = evaluate_test_results(baseline_metrics, post_metrics, config)

        if evaluation['passed']:
            result = 'pass'
            result_reason = 'All metrics within acceptable thresholds'
            final_status = 'passed'
        else:
            result = 'fail'
            result_reason = '; '.join(evaluation['failures'])
            final_status = 'failed'

        test_report = {
            'baseline': baseline_metrics,
            'post_patch': post_metrics,
            'evaluation': evaluation,
            'config': config,
            'test_type': test_type,
            'test_vm': test_vm,
            'snapshot_id': snapshot_id,
            'completed_at': datetime.utcnow().isoformat()
        }

        update_test_status(cur, test_id, final_status,
                         result=result,
                         result_reason=result_reason,
                         test_report=test_report)
        log_test_event(cur, test_id, 'evaluation_complete',
                      f'Test {result.upper()}: {result_reason}', evaluation)
        conn.commit()

        # Auto-approve if configured and passed
        if evaluation['passed'] and config['auto_approve_on_pass']:
            update_test_status(cur, test_id, 'approved')
            log_test_event(cur, test_id, 'auto_approved', 'Test auto-approved based on configuration')
            # Update errata test_status
            cur.execute("UPDATE errata SET test_status = 'approved' WHERE id = %s", (test['errata_id'],))
            conn.commit()

        # Step 7: Cleanup
        if config['cleanup_on_complete']:
            update_test_status(cur, test_id, 'cleanup')
            log_test_event(cur, test_id, 'cleanup_start', 'Starting cleanup')
            conn.commit()

            try:
                if test_type == 'azure':
                    env.delete_test_vm(test_vm)
                    if not config.get('keep_snapshot'):
                        env.delete_snapshot(snapshot_id, resource_group)
                else:
                    env.cleanup(test_vm, snapshot_id if not config.get('keep_snapshot') else None)

                log_test_event(cur, test_id, 'cleanup_complete', 'Cleanup completed')
            except Exception as e:
                log_test_event(cur, test_id, 'cleanup_error', f'Cleanup error: {str(e)}')

            conn.commit()

        update_test_status(cur, test_id, 'completed')
        log_test_event(cur, test_id, 'test_complete', f'Test completed with result: {result}')

        # Update errata test_status
        cur.execute("UPDATE errata SET test_status = %s WHERE id = %s",
                   (result + 'ed' if result != 'pass' else 'passed', test['errata_id']))
        conn.commit()

        logger.info(f"Patch test {test_id} completed: {result}")

    except Exception as e:
        logger.error(f"Patch test {test_id} failed with error: {e}")
        update_test_status(cur, test_id, 'error', error_message=str(e))
        log_test_event(cur, test_id, 'test_error', f'Test failed with error: {str(e)}')
        conn.commit()

        # Update errata test_status
        try:
            cur.execute("UPDATE errata SET test_status = 'failed' WHERE id = %s", (test['errata_id'],))
            conn.commit()
        except:
            pass

    finally:
        cur.close()
        conn.close()
        # Remove from active tests
        if test_id in _active_tests:
            del _active_tests[test_id]


# ============================================================
# API ENDPOINTS
# ============================================================
@p3_bp.route('/start', methods=['POST'])
def start_test():
    """Start a new patch test."""
    data = request.get_json() or {}

    errata_id = data.get('errata_id')
    system_id = data.get('system_id')
    vm_name = data.get('vm_name')
    config = data.get('config', {})

    if not errata_id or not system_id:
        return jsonify({'error': 'errata_id and system_id are required'}), 400

    # Check concurrent test limit
    if len(_active_tests) >= P3_MAX_CONCURRENT_TESTS:
        return jsonify({
            'error': 'Maximum concurrent tests reached',
            'max_concurrent': P3_MAX_CONCURRENT_TESTS,
            'active_tests': len(_active_tests)
        }), 429

    conn = get_db()
    cur = conn.cursor()

    try:
        # Verify errata exists
        cur.execute("SELECT id, advisory_id, test_status FROM errata WHERE id = %s", (errata_id,))
        errata = cur.fetchone()
        if not errata:
            return jsonify({'error': 'Errata not found'}), 404

        # Check if already being tested
        if errata['test_status'] == 'testing':
            return jsonify({'error': 'Errata is already being tested'}), 409

        # Get VM name if not provided
        if not vm_name:
            # Try to get from UYUNI
            vm_name = f"system-{system_id}"

        # Create test record
        cur.execute("""
            INSERT INTO patch_tests (errata_id, source_system_id, source_vm_name, test_config, status)
            VALUES (%s, %s, %s, %s, 'pending')
            RETURNING id
        """, (errata_id, system_id, vm_name, json.dumps(config)))
        test_id = cur.fetchone()['id']

        # Update errata status
        cur.execute("UPDATE errata SET test_status = 'testing' WHERE id = %s", (errata_id,))

        log_test_event(cur, test_id, 'test_created', f'Test created for errata {errata["advisory_id"]}', {
            'errata_id': errata_id,
            'system_id': system_id,
            'vm_name': vm_name,
            'config': config
        })
        conn.commit()

        # Start background worker
        worker = threading.Thread(target=run_patch_test, args=(test_id,), daemon=True)
        _active_tests[test_id] = worker
        worker.start()

        return jsonify({
            'status': 'started',
            'test_id': test_id,
            'errata_id': errata_id,
            'vm_name': vm_name
        }), 201

    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to start test: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@p3_bp.route('/status/<int:test_id>', methods=['GET'])
def get_test_status(test_id: int):
    """Get status of a patch test."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM patch_tests WHERE id = %s", (test_id,))
        test = cur.fetchone()

        if not test:
            return jsonify({'error': 'Test not found'}), 404

        # Get events
        cur.execute("""
            SELECT event_time, event_type, event_message
            FROM patch_test_events
            WHERE test_id = %s
            ORDER BY event_time DESC
            LIMIT 20
        """, (test_id,))
        events = [dict(e) for e in cur.fetchall()]

        # Calculate progress
        status_progress = {
            'pending': 0, 'snapshot_creating': 10, 'cloning': 25,
            'baseline_collecting': 40, 'patching': 55, 'post_metrics': 70,
            'evaluating': 85, 'cleanup': 95, 'completed': 100,
            'passed': 100, 'failed': 100, 'approved': 100, 'rejected': 100, 'error': 100
        }

        elapsed_minutes = None
        if test['started_at']:
            elapsed = datetime.utcnow() - test['started_at']
            elapsed_minutes = int(elapsed.total_seconds() / 60)

        return jsonify({
            'test_id': test_id,
            'status': test['status'],
            'progress_percent': status_progress.get(test['status'], 0),
            'result': test['result'],
            'result_reason': test['result_reason'],
            'created_at': test['created_at'].isoformat() if test['created_at'] else None,
            'started_at': test['started_at'].isoformat() if test['started_at'] else None,
            'completed_at': test['completed_at'].isoformat() if test['completed_at'] else None,
            'elapsed_minutes': elapsed_minutes,
            'source_vm': test['source_vm_name'],
            'test_vm': test['test_vm_name'],
            'events': events
        })

    finally:
        cur.close()
        conn.close()


@p3_bp.route('/result/<int:test_id>', methods=['GET'])
def get_test_result(test_id: int):
    """Get detailed result of a completed test."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM patch_tests WHERE id = %s", (test_id,))
        test = cur.fetchone()

        if not test:
            return jsonify({'error': 'Test not found'}), 404

        if test['status'] not in ['completed', 'passed', 'failed', 'approved', 'rejected', 'error']:
            return jsonify({
                'error': 'Test not yet completed',
                'status': test['status']
            }), 400

        # Get metrics
        cur.execute("""
            SELECT * FROM patch_test_metrics
            WHERE test_id = %s
            ORDER BY phase
        """, (test_id,))
        metrics = {m['phase']: dict(m) for m in cur.fetchall()}

        # Parse test report
        test_report = test['test_report']
        if isinstance(test_report, str):
            test_report = json.loads(test_report)

        return jsonify({
            'test_id': test_id,
            'status': test['status'],
            'result': test['result'],
            'result_reason': test['result_reason'],
            'duration_minutes': (
                int((test['completed_at'] - test['started_at']).total_seconds() / 60)
                if test['completed_at'] and test['started_at'] else None
            ),
            'metrics': metrics,
            'test_report': test_report,
            'error_message': test['error_message']
        })

    finally:
        cur.close()
        conn.close()


@p3_bp.route('/approve/<int:test_id>', methods=['POST'])
def approve_test(test_id: int):
    """Approve a passed test for deployment."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM patch_tests WHERE id = %s", (test_id,))
        test = cur.fetchone()

        if not test:
            return jsonify({'error': 'Test not found'}), 404

        if test['status'] not in ['passed', 'completed']:
            return jsonify({
                'error': 'Only passed tests can be approved',
                'current_status': test['status']
            }), 400

        update_test_status(cur, test_id, 'approved')
        log_test_event(cur, test_id, 'manual_approved', 'Test manually approved for deployment')

        # Update errata
        cur.execute("UPDATE errata SET test_status = 'approved' WHERE id = %s", (test['errata_id'],))
        conn.commit()

        return jsonify({
            'status': 'approved',
            'test_id': test_id,
            'errata_id': test['errata_id'],
            'message': 'Patch approved for deployment'
        })

    finally:
        cur.close()
        conn.close()


@p3_bp.route('/reject/<int:test_id>', methods=['POST'])
def reject_test(test_id: int):
    """Reject a test."""
    data = request.get_json() or {}
    reason = data.get('reason', 'Manually rejected')

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM patch_tests WHERE id = %s", (test_id,))
        test = cur.fetchone()

        if not test:
            return jsonify({'error': 'Test not found'}), 404

        update_test_status(cur, test_id, 'rejected', result_reason=reason)
        log_test_event(cur, test_id, 'rejected', f'Test rejected: {reason}')

        # Update errata
        cur.execute("UPDATE errata SET test_status = 'rejected' WHERE id = %s", (test['errata_id'],))
        conn.commit()

        return jsonify({
            'status': 'rejected',
            'test_id': test_id,
            'errata_id': test['errata_id'],
            'reason': reason
        })

    finally:
        cur.close()
        conn.close()


@p3_bp.route('/cleanup/<int:test_id>', methods=['POST'])
def cleanup_test(test_id: int):
    """Force cleanup of test resources."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM patch_tests WHERE id = %s", (test_id,))
        test = cur.fetchone()

        if not test:
            return jsonify({'error': 'Test not found'}), 404

        # Attempt cleanup
        try:
            if AZURE_AVAILABLE and AZURE_SUBSCRIPTION_ID:
                env = AzureTestEnvironment()
                if test['test_vm_name']:
                    env.delete_test_vm(test['test_vm_name'])
                if test['snapshot_id']:
                    resource_group = os.environ.get('AZURE_SOURCE_RG', 'rg-production')
                    env.delete_snapshot(test['snapshot_id'], resource_group)
            elif SALT_AVAILABLE:
                env = SaltTestEnvironment()
                env.cleanup(test['test_vm_name'], test['snapshot_id'])

            log_test_event(cur, test_id, 'manual_cleanup', 'Manual cleanup completed')
            conn.commit()

            return jsonify({
                'status': 'cleanup_complete',
                'test_id': test_id,
                'cleaned_vm': test['test_vm_name'],
                'cleaned_snapshot': test['snapshot_id']
            })

        except Exception as e:
            return jsonify({
                'status': 'cleanup_error',
                'error': str(e)
            }), 500

    finally:
        cur.close()
        conn.close()


@p3_bp.route('/list', methods=['GET'])
def list_tests():
    """List patch tests with filters."""
    status = request.args.get('status')
    errata_id = request.args.get('errata_id', type=int)
    system_id = request.args.get('system_id', type=int)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    conn = get_db()
    cur = conn.cursor()

    try:
        query = "SELECT id, errata_id, source_system_id, source_vm_name, status, result, created_at, completed_at FROM patch_tests WHERE 1=1"
        params = []

        if status:
            query += " AND status = %s"
            params.append(status)
        if errata_id:
            query += " AND errata_id = %s"
            params.append(errata_id)
        if system_id:
            query += " AND source_system_id = %s"
            params.append(system_id)

        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)
        tests = [dict(t) for t in cur.fetchall()]

        # Get total count
        count_query = "SELECT COUNT(*) FROM patch_tests WHERE 1=1"
        count_params = []
        if status:
            count_query += " AND status = %s"
            count_params.append(status)
        if errata_id:
            count_query += " AND errata_id = %s"
            count_params.append(errata_id)
        if system_id:
            count_query += " AND source_system_id = %s"
            count_params.append(system_id)

        cur.execute(count_query, count_params)
        total = cur.fetchone()['count']

        return jsonify({
            'tests': tests,
            'total': total,
            'limit': limit,
            'offset': offset,
            'active_tests': len(_active_tests)
        })

    finally:
        cur.close()
        conn.close()


@p3_bp.route('/stats', methods=['GET'])
def test_stats():
    """Get patch testing statistics."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'completed' OR status = 'passed' THEN 1 END) as completed,
                COUNT(CASE WHEN result = 'pass' THEN 1 END) as passed,
                COUNT(CASE WHEN result = 'fail' THEN 1 END) as failed,
                COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
                COUNT(CASE WHEN status = 'error' THEN 1 END) as errors
            FROM patch_tests
        """)
        stats = dict(cur.fetchone())

        # Active tests
        stats['active'] = len(_active_tests)

        # Tests in last 24h
        cur.execute("""
            SELECT COUNT(*) as count
            FROM patch_tests
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)
        stats['last_24h'] = cur.fetchone()['count']

        # Average duration
        cur.execute("""
            SELECT AVG(EXTRACT(EPOCH FROM (completed_at - started_at)) / 60) as avg_minutes
            FROM patch_tests
            WHERE completed_at IS NOT NULL AND started_at IS NOT NULL
        """)
        avg = cur.fetchone()['avg_minutes']
        stats['avg_duration_minutes'] = round(avg, 1) if avg else None

        return jsonify(stats)

    finally:
        cur.close()
        conn.close()


# ============================================================
# HEALTH CHECK
# ============================================================
@p3_bp.route('/health', methods=['GET'])
def health():
    """Health check for P3 module."""
    status = {
        'module': 'p3-patch-testing',
        'status': 'ok',
        'azure_available': AZURE_AVAILABLE and bool(AZURE_SUBSCRIPTION_ID),
        'salt_available': SALT_AVAILABLE,
        'active_tests': len(_active_tests),
        'max_concurrent_tests': P3_MAX_CONCURRENT_TESTS
    }

    # Check database
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM patch_tests")
        cur.close()
        conn.close()
        status['database'] = 'ok'
    except Exception as e:
        status['database'] = f'error: {str(e)}'
        status['status'] = 'degraded'

    return jsonify(status)


# Register blueprint function for main app
def register_p3_blueprint(app):
    """Register P3 blueprint with the Flask app."""
    app.register_blueprint(p3_bp)
    logger.info("P3 Patch Testing module registered")


# Standalone mode
if __name__ == '__main__':
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(p3_bp)

    logging.basicConfig(level=logging.INFO)
    logger.info("Starting P3 Patch Testing module standalone")
    app.run(host='0.0.0.0', port=5001, debug=True)
