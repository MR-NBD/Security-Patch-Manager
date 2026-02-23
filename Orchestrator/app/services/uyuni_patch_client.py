"""
SPM Orchestrator - UYUNI Patch Client

Applica patch sui sistemi test tramite UYUNI XML-RPC.
Sostituisce Salt API con UYUNI come backend di orchestrazione:

  ping()                → verifica sistema registrato e raggiungibile
  take_snapshot()       → snapper create via scheduleScriptRun
  apply_errata()        → scheduleApplyErrata (asincrono + polling)
  reboot()              → scheduleReboot
  wait_online()         → ping ripetuto fino a sistema online
  get_failed_services() → bash check via scheduleScriptRun
  rollback_snapshot()   → snapper undochange via scheduleScriptRun
  rollback_packages()   → apt downgrade via scheduleScriptRun

Ogni azione UYUNI è asincrona: viene schedulata e ritorna un action_id.
_wait_action() fa polling su schedule.listCompleted/FailedActions fino
a completamento o timeout.
"""

import logging
import time
from datetime import datetime
from typing import Optional

from app.services.uyuni_client import UyuniSession

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Helper: critical services
# ─────────────────────────────────────────────

_DEFAULT_SERVICES = {
    "ubuntu": ["ssh", "cron", "rsyslog"],
    "rhel":   ["sshd", "crond", "rsyslog"],
}


def get_critical_services(target_os: str) -> list:
    """Servizi critici da orchestrator_config, fallback a defaults."""
    try:
        from app.services.db import get_db
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT value FROM orchestrator_config WHERE key = %s",
                (f"critical_services_{target_os}",),
            )
            row = cur.fetchone()
            if row and isinstance(row["value"], list):
                return row["value"]
    except Exception as e:
        logger.warning(f"Could not load critical_services_{target_os}: {e}")
    return list(_DEFAULT_SERVICES.get(target_os, ["ssh", "cron"]))


# ─────────────────────────────────────────────
# UyuniPatchClient
# ─────────────────────────────────────────────

class UyuniPatchClient:
    """
    Client per applicare patch su sistemi test tramite UYUNI XML-RPC.

    Uso come context manager:
        with UyuniPatchClient(system_id, system_name) as uyuni:
            if uyuni.ping():
                snap = uyuni.take_snapshot("spm-pre-USN-7412-2")
                uyuni.apply_errata("USN-7412-2", pkg_names)
    """

    _POLL_INTERVAL = 10  # secondi tra polling azioni UYUNI

    def __init__(self, system_id: int, system_name: str):
        if not system_id:
            raise ValueError(
                f"system_id obbligatorio per operazioni UYUNI patch "
                f"(system_name={system_name!r}). "
                f"Imposta TEST_SYSTEM_UBUNTU_ID / TEST_SYSTEM_RHEL_ID in .env"
            )
        self._system_id   = int(system_id)
        self._system_name = system_name
        self._session: Optional[UyuniSession] = None

    def __enter__(self):
        self._session = UyuniSession()
        self._session.__enter__()
        return self

    def __exit__(self, *args):
        if self._session:
            self._session.__exit__(*args)
            self._session = None

    # ── Shortcuts ────────────────────────────────────────────────────

    @property
    def _key(self) -> str:
        return self._session._key

    @property
    def _proxy(self):
        return self._session._proxy

    # ── Action polling ───────────────────────────────────────────────

    def _wait_action(self, action_id: int, timeout_s: int = 600) -> bool:
        """
        Attende completamento azione UYUNI tramite polling.
        Ritorna True=success, False=failed/timeout.
        """
        deadline = time.time() + timeout_s
        logger.debug(
            f"UyuniPatchClient: waiting action {action_id} (timeout={timeout_s}s)"
        )

        while time.time() < deadline:
            time.sleep(self._POLL_INTERVAL)
            try:
                completed = self._proxy.schedule.listCompletedActions(self._key)
                if any(a.get("id") == action_id for a in completed):
                    logger.debug(f"UyuniPatchClient: action {action_id} completed OK")
                    return True

                failed = self._proxy.schedule.listFailedActions(self._key)
                if any(a.get("id") == action_id for a in failed):
                    logger.warning(f"UyuniPatchClient: action {action_id} FAILED")
                    return False

            except Exception as e:
                logger.warning(
                    f"UyuniPatchClient: polling error for action {action_id}: {e}"
                )

        logger.error(
            f"UyuniPatchClient: action {action_id} timed out after {timeout_s}s"
        )
        return False

    # ── Script helper ─────────────────────────────────────────────────

    def _run_script(
        self,
        script: str,
        script_timeout: int = 60,
        wait_timeout: int = 120,
    ) -> tuple:
        """
        Esegue uno script bash tramite system.scheduleScriptRun.
        Ritorna (success: bool, output: str).
        """
        try:
            action_id = self._proxy.system.scheduleScriptRun(
                self._key,
                self._system_id,
                "root",          # username
                "root",          # groupname
                script_timeout,  # timeout esecuzione script (secondi)
                script,
                datetime.now(),
            )
        except Exception as e:
            logger.error(
                f"UyuniPatchClient: scheduleScriptRun failed "
                f"on {self._system_name!r}: {e}"
            )
            return False, str(e)

        success = self._wait_action(action_id, timeout_s=wait_timeout)
        if not success:
            return False, ""

        try:
            results = self._proxy.system.getScriptResults(self._key, action_id)
            output = results[0].get("output", "") if results else ""
            return True, output
        except Exception as e:
            logger.warning(f"UyuniPatchClient: getScriptResults failed: {e}")
            return True, ""  # Azione completata, output non disponibile

    # ── Public interface ──────────────────────────────────────────────

    def ping(self) -> bool:
        """
        Verifica che il sistema sia registrato e raggiungibile in UYUNI.
        """
        try:
            info = self._proxy.system.getDetails(self._key, self._system_id)
            return bool(info)
        except Exception as e:
            logger.warning(
                f"UyuniPatchClient: ping({self._system_name!r}) failed: {e}"
            )
            return False

    def take_snapshot(self, description: str) -> str:
        """
        Crea snapshot snapper pre-patch tramite scheduleScriptRun.
        Ritorna snapshot_id (stringa numerica).
        Raises: RuntimeError se snapper fallisce.
        """
        script = (
            "#!/bin/bash\n"
            f"snapper create --description '{description}' --print-number\n"
        )
        success, output = self._run_script(
            script, script_timeout=30, wait_timeout=60
        )
        snapshot_id = (output or "").strip()

        if not success or not snapshot_id.isdigit():
            raise RuntimeError(
                f"Snapper create failed on {self._system_name!r} "
                f"(output={output!r})"
            )
        return snapshot_id

    def apply_errata(self, advisory_name: str, pkg_names: list) -> dict:
        """
        Applica errata tramite system.scheduleApplyErrata.
        Polling fino a completamento (timeout 30 min).

        Ritorna {pkg_name: {old: '', new: 'patched'}} per compatibilità
        con il meccanismo di rollback package del test engine.
        Raises: RuntimeError se applicazione fallisce o timeout.
        """
        # Ottieni ID numerico dall'advisory name (es. "USN-7412-2")
        try:
            details = self._proxy.errata.getDetails(self._key, advisory_name)
            errata_num_id = details["id"]
        except Exception as e:
            raise RuntimeError(
                f"Cannot get errata numeric ID for {advisory_name!r}: {e}"
            ) from e

        # Schedula applicazione
        try:
            action_ids = self._proxy.system.scheduleApplyErrata(
                self._key,
                self._system_id,
                [errata_num_id],
                datetime.now(),
            )
        except Exception as e:
            raise RuntimeError(
                f"scheduleApplyErrata failed for {advisory_name!r}: {e}"
            ) from e

        action_id = action_ids[0] if action_ids else None
        if not action_id:
            raise RuntimeError(
                f"scheduleApplyErrata returned no action ID for {advisory_name!r}"
            )

        logger.info(
            f"UyuniPatchClient: errata {advisory_name!r} scheduled "
            f"(action={action_id}) on {self._system_name!r}"
        )

        # Attende completamento (timeout 30 min per patch grandi)
        success = self._wait_action(action_id, timeout_s=1800)
        if not success:
            raise RuntimeError(
                f"Errata {advisory_name!r} application failed or timed out "
                f"on {self._system_name!r} (action={action_id})"
            )

        logger.info(
            f"UyuniPatchClient: errata {advisory_name!r} applied "
            f"({len(pkg_names)} packages) on {self._system_name!r}"
        )

        # Rollback package non disponibile senza versioni precedenti:
        # il rollback userà lo snapshot quando possibile.
        return {name: {"old": "", "new": "patched"} for name in pkg_names}

    def reboot(self) -> None:
        """
        Schedula riavvio tramite system.scheduleReboot.
        Non attende: usa wait_online() dopo.
        Raises: RuntimeError se la schedulazione fallisce.
        """
        try:
            self._proxy.system.scheduleReboot(
                self._key,
                self._system_id,
                datetime.now(),
            )
            logger.info(
                f"UyuniPatchClient: reboot scheduled for {self._system_name!r}"
            )
        except Exception as e:
            raise RuntimeError(
                f"scheduleReboot failed for {self._system_name!r}: {e}"
            ) from e

    def wait_online(self, timeout: int = 300) -> bool:
        """
        Attende che il sistema torni online dopo il reboot.
        Prima attesa fissa 30s (shutdown), poi polling ogni 15s.
        """
        time.sleep(30)
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self.ping():
                # Conferma con un echo script minimo
                ok, _ = self._run_script(
                    "#!/bin/bash\necho online",
                    script_timeout=10,
                    wait_timeout=30,
                )
                if ok:
                    logger.info(
                        f"UyuniPatchClient: {self._system_name!r} is back online"
                    )
                    return True
            time.sleep(15)

        logger.error(
            f"UyuniPatchClient: {self._system_name!r} did not come back "
            f"within {timeout}s after reboot"
        )
        return False

    def get_failed_services(self, system_name: str, services: list) -> list:
        """
        Verifica servizi critici tramite systemctl.
        Ritorna lista servizi non attivi.

        Nota: il parametro system_name è ignorato (mantenuto per compatibilità
              con l'interfaccia salt_client originale).
        """
        if not services:
            return []

        # Script: controlla ogni servizio, stampa quelli non attivi
        lines = ["#!/bin/bash"]
        for svc in services:
            lines.append(
                f"systemctl is-active --quiet '{svc}' 2>/dev/null "
                f"|| echo '{svc}'"
            )
        script = "\n".join(lines) + "\n"

        success, output = self._run_script(
            script, script_timeout=30, wait_timeout=60
        )
        if not success:
            logger.warning(
                f"UyuniPatchClient: service check script failed "
                f"on {self._system_name!r}"
            )
            return []

        return [s.strip() for s in (output or "").splitlines() if s.strip()]

    def rollback_snapshot(self, snapshot_id: str) -> None:
        """
        Esegue rollback tramite snapper undochange {snapshot_id}..0.
        Raises: RuntimeError se il rollback fallisce.
        """
        script = (
            "#!/bin/bash\n"
            f"snapper undochange {snapshot_id}..0\n"
        )
        success, output = self._run_script(
            script, script_timeout=120, wait_timeout=300
        )
        if not success:
            raise RuntimeError(
                f"Snapshot rollback #{snapshot_id} failed "
                f"on {self._system_name!r}: {output!r}"
            )
        logger.info(
            f"UyuniPatchClient: snapshot rollback #{snapshot_id} "
            f"done on {self._system_name!r}"
        )

    def rollback_packages(self, packages_before: dict) -> None:
        """
        Reinstalla versioni precedenti dei pacchetti (Ubuntu/Debian).
        Skipped se non ci sono versioni 'old' disponibili.
        """
        pkgs_old = {
            name: versions.get("old")
            for name, versions in packages_before.items()
            if isinstance(versions, dict) and versions.get("old")
        }
        if not pkgs_old:
            logger.warning(
                "UyuniPatchClient: package rollback skipped — no old versions"
            )
            return

        pkg_args = " ".join(f"'{k}={v}'" for k, v in pkgs_old.items())
        script = (
            "#!/bin/bash\n"
            "export DEBIAN_FRONTEND=noninteractive\n"
            f"apt-get install --allow-downgrades -y {pkg_args} 2>&1\n"
        )
        success, output = self._run_script(
            script, script_timeout=180, wait_timeout=300
        )
        if not success:
            raise RuntimeError(
                f"Package rollback failed on {self._system_name!r}: {output!r}"
            )
        logger.info(
            f"UyuniPatchClient: package rollback ({len(pkgs_old)} packages) "
            f"done on {self._system_name!r}"
        )
