"""
SPM Orchestrator - UYUNI Patch Client

Applica patch sui sistemi test tramite UYUNI XML-RPC.
Tutte le azioni UYUNI sono asincrone: schedule → action_id → polling _wait_action().

Funzioni di discovery:
  get_all_test_systems_for_os(os) → lista di tutti i sistemi nel gruppo test-{os}
  get_test_system_for_os(os)      → primo sistema (backward compat)

Metodi pubblici UyuniPatchClient:
  ping()                  → verifica sistema registrato in UYUNI (system.getDetails)
  check_disk_space()      → verifica spazio disco disponibile su / (min 500 MB)
  check_reboot_pending()  → controlla /var/run/reboot-required (Ubuntu) o needs-restarting (RHEL)
  take_snapshot()         → snapper create via scheduleScriptRun
  apply_errata()          → scheduleApplyErrata (asincrono + polling); cattura versioni pre-patch
  reboot()                → scheduleReboot (schedula, non attende)
  wait_online()           → attesa consegna reboot Salt + polling echo script fino a online
  ensure_node_exporter()  → installa/avvia node_exporter via UYUNI channels se mancante
  ensure_snapper()        → installa snapper + crea config root via UYUNI channels se mancante
  get_failed_services()   → bash check via scheduleScriptRun (systemctl is-active)
  rollback_snapshot()     → snapper undochange via scheduleScriptRun
  rollback_packages()     → apt/dnf downgrade (Ubuntu: apt-get --allow-downgrades, RHEL: dnf install)

_wait_action() polling: schedule.listCompletedSystems / listFailedSystems (scoped per action_id).
"""

import ipaddress
import logging
import time
from datetime import datetime
from typing import Optional

from app.config import Config
from app.services.uyuni_client import UyuniSession, os_from_group

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Helper: critical services
# ─────────────────────────────────────────────

_DEFAULT_SERVICES = {
    "ubuntu": ["ssh.socket", "cron", "rsyslog"],
    "rhel":   ["sshd", "crond", "rsyslog"],
}


def is_ip(value: str) -> bool:
    """Ritorna True se la stringa è un indirizzo IP valido."""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _resolve_system_info(session, s: dict, system_id: int) -> dict:
    """Estrae system_name e system_ip da un record sistema UYUNI."""
    system_name = (
        s.get("name")
        or s.get("profile_name")
        or s.get("hostname")
        or str(system_id)
    )
    if is_ip(system_name):
        system_ip = system_name
    else:
        system_ip = session.get_system_network_ip(system_id) or ""
    return {"system_id": system_id, "system_name": system_name, "system_ip": system_ip}


def get_all_test_systems_for_os(target_os: str) -> list:
    """
    Scopre TUTTI i sistemi di test per il target_os dato interrogando i gruppi
    UYUNI con prefisso 'test-'.

    Ritorna lista di {system_id, system_name, system_ip} per ogni sistema
    nel gruppo corrispondente. Lista vuota se nessun gruppo/sistema trovato.

    Usato dal test engine per eseguire il test su tutti i sistemi del gruppo.
    """
    results = []
    try:
        with UyuniSession() as session:
            groups = session.get_test_groups()
            for group in groups:
                group_name = group.get("name", "")
                if os_from_group(group_name) != target_os:
                    continue
                systems = session.get_systems_in_group(group_name)
                for s in systems:
                    system_id = s.get("id")
                    info = _resolve_system_info(session, s, system_id)
                    logger.info(
                        f"UYUNI auto-discovery: {target_os} → "
                        f"system_id={system_id} name={info['system_name']!r} "
                        f"ip={info['system_ip']!r} (group={group_name!r})"
                    )
                    results.append(info)
                break  # primo gruppo corrispondente è sufficiente
    except Exception as e:
        logger.warning(f"get_all_test_systems_for_os({target_os!r}) failed: {e}")
    return results


def get_test_system_for_os(target_os: str) -> Optional[dict]:
    """
    Scopre il primo sistema di test per target_os (backward compat).
    Usa get_all_test_systems_for_os internamente.
    """
    systems = get_all_test_systems_for_os(target_os)
    return systems[0] if systems else None


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

    def __init__(
        self,
        system_id: int,
        system_name: str,
        username: str = None,
        password: str = None,
    ):
        if not system_id:
            raise ValueError(
                f"system_id obbligatorio per operazioni UYUNI patch "
                f"(system_name={system_name!r}). "
                f"Imposta TEST_SYSTEM_UBUNTU_ID / TEST_SYSTEM_RHEL_ID in .env"
            )
        self._system_id   = int(system_id)
        self._system_name = system_name
        self._username    = username  # None → UyuniSession usa Config default
        self._password    = password
        self._session: Optional[UyuniSession] = None

    def __enter__(self):
        self._session = UyuniSession(username=self._username, password=self._password)
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

        Usa schedule.listCompletedSystems / listFailedSystems (scoped al singolo
        action_id) invece di listCompletedActions / listFailedActions (globali).
        Riduce drasticamente il payload per istanze UYUNI con molte azioni storiche:
        invece di scaricare tutte le azioni completate, ottiene solo i sistemi che
        hanno completato/fallito quell'azione specifica.
        """
        deadline = time.time() + timeout_s
        logger.debug(
            f"UyuniPatchClient: waiting action {action_id} (timeout={timeout_s}s)"
        )

        while time.time() < deadline:
            time.sleep(self._POLL_INTERVAL)
            try:
                completed = self._proxy.schedule.listCompletedSystems(
                    self._key, action_id
                )
                if any(s.get("server_id") == self._system_id for s in completed):
                    logger.debug(f"UyuniPatchClient: action {action_id} completed OK")
                    return True

                failed = self._proxy.schedule.listFailedSystems(
                    self._key, action_id
                )
                if any(s.get("server_id") == self._system_id for s in failed):
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

        # Recupera output anche se l'azione è fallita (utile per diagnostica)
        output = ""
        try:
            results = self._proxy.system.getScriptResults(self._key, action_id)
            output = results[0].get("output", "") if results else ""
        except Exception as e:
            logger.warning(f"UyuniPatchClient: getScriptResults failed: {e}")

        return success, output

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

        Ritorna {pkg_name: {old: <versione_pre_patch>, new: 'patched'}}
        per abilitare il rollback package con versioni specifiche.
        Raises: RuntimeError se applicazione fallisce o timeout.
        """
        # Versioni installate PRIMA della patch (per rollback)
        old_versions: dict = {}
        try:
            all_pkgs = self._proxy.system.listPackages(
                self._key, self._system_id
            )
            pkg_names_set = set(pkg_names)
            for p in all_pkgs:
                name = p.get("name", "")
                if name in pkg_names_set:
                    # UYUNI restituisce version + release separati
                    ver  = p.get("version", "")
                    rel  = p.get("release", "")
                    old_versions[name] = f"{ver}-{rel}" if rel else ver
            logger.debug(
                f"UyuniPatchClient: captured {len(old_versions)} old versions "
                f"before applying {advisory_name!r}"
            )
        except Exception as e:
            logger.warning(
                f"UyuniPatchClient: could not get old package versions "
                f"for {advisory_name!r}: {e}"
            )

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

        return {
            name: {"old": old_versions.get(name, ""), "new": "patched"}
            for name in pkg_names
        }

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

        Attesa iniziale configurabile (TEST_REBOOT_DELIVERY_WAIT, default 60s)
        per dare tempo al minion Salt di ricevere il comando reboot da UYUNI
        (check-in intervallo tipico: 30-60s). Poi polling ogni 15s con uno
        script echo per verificare la raggiungibilità reale del sistema.

        Nota: ping() usa system.getDetails che legge il DB UYUNI — ritorna
        sempre True anche quando la VM è offline. Per questo usiamo direttamente
        _run_script (scheduleScriptRun) come test di liveness reale.
        """
        delivery_wait = Config.TEST_REBOOT_DELIVERY_WAIT
        logger.info(
            f"UyuniPatchClient: waiting {delivery_wait}s for reboot delivery "
            f"to {self._system_name!r} before polling"
        )
        time.sleep(delivery_wait)
        deadline = time.time() + timeout

        while time.time() < deadline:
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
            f"within {delivery_wait + timeout}s after reboot"
        )
        return False

    def get_failed_services(self, services: list) -> list:
        """
        Verifica servizi critici tramite systemctl (via UYUNI scheduleScriptRun).
        Ritorna lista dei servizi non attivi.
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

    def delete_snapshot(self, snapshot_id: str) -> None:
        """
        Elimina uno snapshot snapper tramite scheduleScriptRun.
        Chiamato dopo approvazione patch (snapshot non più necessario).
        Raises: RuntimeError se la cancellazione fallisce.
        """
        script = (
            "#!/bin/bash\n"
            f"snapper delete {snapshot_id}\n"
        )
        success, output = self._run_script(
            script, script_timeout=30, wait_timeout=60
        )
        if not success:
            raise RuntimeError(
                f"Snapper delete #{snapshot_id} failed "
                f"on {self._system_name!r}: {output!r}"
            )
        logger.info(
            f"UyuniPatchClient: snapshot #{snapshot_id} deleted "
            f"on {self._system_name!r}"
        )

    def ensure_node_exporter(self, target_os: str) -> bool:
        """
        Verifica che node_exporter sia installato e attivo sul sistema.
        Se manca, lo installa tramite UYUNI schedulePackageInstall
        usando i canali software gia' sincronizzati — senza intervento manuale.

        Flusso:
          1. Controlla se il servizio e' gia' attivo (check rapido via systemctl)
          2. Se non attivo, cerca il pacchetto nei canali UYUNI del sistema
          3. Se trovato nei canali: installa via schedulePackageInstall (UYUNI-native)
          4. Abilita e avvia il servizio
          5. Se non nei canali UYUNI: warning, Prometheus metrics verra' skippato

        Ritorna True se node_exporter e' operativo alla fine, False altrimenti.
        """
        _PACKAGES = {
            "ubuntu": "prometheus-node-exporter",
            "rhel":   "node_exporter",
            "debian": "prometheus-node-exporter",
        }
        _SERVICES = {
            "ubuntu": "prometheus-node-exporter",
            "rhel":   "node_exporter",
            "debian": "prometheus-node-exporter",
        }

        pkg_name = _PACKAGES.get(target_os)
        svc_name = _SERVICES.get(target_os)

        if not pkg_name or not svc_name:
            logger.warning(
                f"UyuniPatchClient: no node_exporter package known for OS {target_os!r}"
            )
            return False

        # ── 1. Il servizio e' gia' attivo? ───────────────────────────────
        ok, output = self._run_script(
            f"#!/bin/bash\nsystemctl is-active --quiet '{svc_name}' && echo active || echo inactive\n",
            script_timeout=15,
            wait_timeout=30,
        )
        if ok and "active" in (output or ""):
            logger.debug(
                f"UyuniPatchClient: node_exporter already active "
                f"on {self._system_name!r}"
            )
            return True

        logger.info(
            f"UyuniPatchClient: node_exporter not active on {self._system_name!r} "
            f"— checking UYUNI channels for {pkg_name!r}"
        )

        # ── 2. Cerca il pacchetto nei canali UYUNI del sistema ───────────
        pkg_id = None
        try:
            installable = self._proxy.system.listLatestInstallablePackages(
                self._key, self._system_id
            )
            for p in installable:
                if p.get("name") == pkg_name:
                    pkg_id = p.get("id")
                    break
        except Exception as e:
            logger.warning(
                f"UyuniPatchClient: listLatestInstallablePackages failed "
                f"on {self._system_name!r}: {e}"
            )

        if pkg_id is None:
            # Controlla se e' gia' installato ma solo il servizio non e' avviato
            try:
                installed = self._proxy.system.listPackages(self._key, self._system_id)
                already_installed = any(p.get("name") == pkg_name for p in installed)
            except Exception:
                already_installed = False

            if not already_installed:
                logger.warning(
                    f"UyuniPatchClient: {pkg_name!r} not found in UYUNI channels "
                    f"for {self._system_name!r} — Prometheus metrics will be skipped"
                )
                return False
            # Pacchetto installato ma servizio non avviato: lo avviamo
            logger.info(
                f"UyuniPatchClient: {pkg_name!r} installed but service not active "
                f"on {self._system_name!r} — enabling service"
            )
        else:
            # ── 3. Installa via UYUNI schedulePackageInstall ──────────────
            logger.info(
                f"UyuniPatchClient: installing {pkg_name!r} (id={pkg_id}) "
                f"on {self._system_name!r} via UYUNI channel"
            )
            try:
                action_ids = self._proxy.system.schedulePackageInstall(
                    self._key,
                    self._system_id,
                    [pkg_id],
                    datetime.now(),
                )
            except Exception as e:
                logger.warning(
                    f"UyuniPatchClient: schedulePackageInstall failed "
                    f"for {pkg_name!r} on {self._system_name!r}: {e}"
                )
                return False

            action_id = action_ids[0] if action_ids else None
            if not action_id:
                logger.warning(
                    f"UyuniPatchClient: schedulePackageInstall returned no action_id "
                    f"for {pkg_name!r}"
                )
                return False

            success = self._wait_action(action_id, timeout_s=300)
            if not success:
                logger.warning(
                    f"UyuniPatchClient: package install action timed out or failed "
                    f"for {pkg_name!r} on {self._system_name!r}"
                )
                return False

            logger.info(
                f"UyuniPatchClient: {pkg_name!r} installed on {self._system_name!r}"
            )

        # ── 4. Abilita e avvia il servizio ───────────────────────────────
        ok, output = self._run_script(
            f"#!/bin/bash\nsystemctl enable --now '{svc_name}'\n",
            script_timeout=30,
            wait_timeout=60,
        )
        if not ok:
            logger.warning(
                f"UyuniPatchClient: failed to enable {svc_name!r} "
                f"on {self._system_name!r}: {output!r}"
            )
            return False

        logger.info(
            f"UyuniPatchClient: node_exporter ({svc_name}) enabled and started "
            f"on {self._system_name!r}"
        )
        return True

    def ensure_snapper(self, target_os: str) -> bool:
        """
        Verifica che snapper sia installato e configurato sul sistema test.
        Se mancante: installa via UYUNI channels + inizializza config root.

        Due passi:
          1. Installa pacchetto 'snapper' se non presente (via UYUNI channels)
          2. Crea config root se non esiste: snapper -c root create-config /

        Best-effort: ritorna False se non possibile (filesystem non supportato,
        pacchetto non nei canali). Il test engine userà package rollback in questo caso.
        """
        _PACKAGE = "snapper"  # stesso nome su Ubuntu 24.04 e RHEL 9

        # ── 1. Snapper già installato? ────────────────────────────────────
        try:
            installed = self._proxy.system.listPackages(self._key, self._system_id)
            snapper_installed = any(p.get("name") == _PACKAGE for p in installed)
        except Exception as e:
            logger.warning(
                f"UyuniPatchClient: listPackages failed on {self._system_name!r}: {e}"
            )
            return False

        if not snapper_installed:
            logger.info(
                f"UyuniPatchClient: snapper not installed on {self._system_name!r} "
                f"— checking UYUNI channels"
            )
            pkg_id = None
            try:
                installable = self._proxy.system.listLatestInstallablePackages(
                    self._key, self._system_id
                )
                for p in installable:
                    if p.get("name") == _PACKAGE:
                        pkg_id = p.get("id")
                        break
            except Exception as e:
                logger.warning(
                    f"UyuniPatchClient: listLatestInstallablePackages failed "
                    f"on {self._system_name!r}: {e}"
                )

            if pkg_id is None:
                logger.warning(
                    f"UyuniPatchClient: 'snapper' not found in UYUNI channels "
                    f"for {self._system_name!r} — snapshot rollback unavailable"
                )
                return False

            logger.info(
                f"UyuniPatchClient: installing 'snapper' (id={pkg_id}) "
                f"on {self._system_name!r} via UYUNI channel"
            )
            try:
                action_ids = self._proxy.system.schedulePackageInstall(
                    self._key, self._system_id, [pkg_id], datetime.now(),
                )
            except Exception as e:
                logger.warning(
                    f"UyuniPatchClient: schedulePackageInstall('snapper') failed "
                    f"on {self._system_name!r}: {e}"
                )
                return False

            action_id = action_ids[0] if action_ids else None
            if not action_id or not self._wait_action(action_id, timeout_s=300):
                logger.warning(
                    f"UyuniPatchClient: snapper install failed or timed out "
                    f"on {self._system_name!r}"
                )
                return False

            logger.info(
                f"UyuniPatchClient: snapper installed on {self._system_name!r}"
            )

        # ── 2. Config root esiste? ────────────────────────────────────────
        ok, output = self._run_script(
            "#!/bin/bash\nsnapper list-configs 2>&1\n",
            script_timeout=15,
            wait_timeout=30,
        )
        if ok and "root" in (output or ""):
            logger.debug(
                f"UyuniPatchClient: snapper root config already present "
                f"on {self._system_name!r}"
            )
            return True

        # Crea config root (richiede filesystem supportato: btrfs o lvm-thin)
        logger.info(
            f"UyuniPatchClient: creating snapper root config on {self._system_name!r}"
        )
        ok, output = self._run_script(
            "#!/bin/bash\nsnapper -c root create-config /\n",
            script_timeout=30,
            wait_timeout=60,
        )
        if not ok:
            logger.warning(
                f"UyuniPatchClient: snapper create-config failed on {self._system_name!r} "
                f"(filesystem not supported?): {output!r}"
            )
            return False

        logger.info(
            f"UyuniPatchClient: snapper root config created on {self._system_name!r}"
        )
        return True

    def rollback_packages(self, packages_before: dict, target_os: str = "ubuntu") -> None:
        """
        Reinstalla versioni precedenti dei pacchetti via package manager nativo.

        Ubuntu/Debian: apt-get install --allow-downgrades 'pkg=version'
        RHEL/CentOS:   dnf install -y 'pkg-version' (dnf gestisce il downgrade)

        Skipped se non ci sono versioni 'old' disponibili (nessuna versione catturata
        prima della patch — es. pacchetto nuovo, non aggiornamento).

        Limitazione nota: fallisce se la versione precedente non è più disponibile
        nel repository (rimozione post-security-patch). In quel caso il rollback
        package è impossibile e va usato il rollback snapshot.
        """
        pkgs_old = {
            name: versions.get("old")
            for name, versions in packages_before.items()
            if isinstance(versions, dict) and versions.get("old")
        }
        if not pkgs_old:
            logger.warning(
                "UyuniPatchClient: package rollback skipped — no old versions captured "
                "(packages were newly installed, not upgraded)"
            )
            return

        if target_os == "rhel":
            # DNF: 'pkg-version-release' (formato RPM)
            pkg_args = " ".join(f"'{k}-{v}'" for k, v in pkgs_old.items())
            script = (
                "#!/bin/bash\n"
                f"dnf install -y {pkg_args} 2>&1\n"
            )
        else:
            # APT: 'pkg=version' (formato Debian)
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
                f"Package rollback failed on {self._system_name!r} "
                f"(os={target_os!r}): {output!r}"
            )
        logger.info(
            f"UyuniPatchClient: package rollback ({len(pkgs_old)} packages, "
            f"os={target_os!r}) done on {self._system_name!r}"
        )

    def check_disk_space(self, min_mb: int = 500) -> tuple:
        """
        Verifica spazio disco disponibile su /.
        Ritorna (ok: bool, available_mb: int, message: str).
        Best-effort: ritorna (True, 0, "") se lo script fallisce.
        """
        script = (
            "#!/bin/bash\n"
            "df -BM / | awk 'NR==2{gsub(\"M\",\"\"); print $4}'\n"
        )
        ok, output = self._run_script(script, script_timeout=10, wait_timeout=30)
        if not ok or not (output or "").strip().isdigit():
            logger.warning(
                f"UyuniPatchClient: check_disk_space script failed "
                f"on {self._system_name!r}: {output!r}"
            )
            return True, 0, ""  # best-effort: non blocca il test

        available_mb = int(output.strip())
        if available_mb < min_mb:
            msg = (
                f"Insufficient disk space: {available_mb}MB available, "
                f"{min_mb}MB required on {self._system_name!r}"
            )
            return False, available_mb, msg

        return True, available_mb, f"{available_mb}MB available"

    def check_reboot_pending(self, target_os: str) -> tuple:
        """
        Verifica se è pendente un reboot dal precedente aggiornamento.
        Ubuntu: controlla /var/run/reboot-required
        RHEL:   usa needs-restarting -r
        Ritorna (pending: bool, message: str).
        Best-effort: ritorna (False, "") se lo script fallisce.
        """
        if target_os == "rhel":
            script = (
                "#!/bin/bash\n"
                "needs-restarting -r > /dev/null 2>&1 "
                "&& echo no_reboot || echo reboot_required\n"
            )
        else:
            script = (
                "#!/bin/bash\n"
                "[ -f /var/run/reboot-required ] "
                "&& echo reboot_required || echo no_reboot\n"
            )
        ok, output = self._run_script(script, script_timeout=10, wait_timeout=30)
        if not ok:
            logger.warning(
                f"UyuniPatchClient: check_reboot_pending script failed "
                f"on {self._system_name!r}"
            )
            return False, ""  # best-effort: non blocca il test

        pending = "reboot_required" in (output or "")
        msg = f"Reboot pending on {self._system_name!r}" if pending else ""
        return pending, msg
