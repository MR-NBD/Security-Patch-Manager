"""
SPM Orchestrator - UYUNI XML-RPC Client

Client per recuperare errata applicabili ai sistemi nei gruppi "test-*"
direttamente da UYUNI, invece di scaricare l'intero catalogo da SPM-SYNC.

Ottimizzazioni:
- UyuniSession: 1 login/logout per ciclo di sync (non per call)
- Thread-safe: ogni thread crea il proprio ServerProxy via threading.local(),
  condividendo self._key (read-only dopo login)
"""

import logging
import ssl
import threading
import xmlrpc.client
from typing import Optional

from app.config import Config

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# OS / Severity helpers (module-level)
# ─────────────────────────────────────────────

def os_from_group(group_name: str) -> str:
    """Mappa nome gruppo UYUNI → target_os."""
    name = group_name.lower().removeprefix(Config.UYUNI_TEST_GROUP_PREFIX)
    if name.startswith("ubuntu"):
        return "ubuntu"
    if name.startswith("rhel") or name.startswith("centos"):
        return "rhel"
    if name.startswith("debian"):
        return "debian"
    return name.split("-")[0]  # best-effort


_ADVISORY_TYPE_SEVERITY = {
    "Security Advisory":            "Medium",   # safe default; enrich with NVD
    "Bug Fix Advisory":             "Low",
    "Product Enhancement Advisory": "Low",
}


def _severity_from_advisory_type(advisory_type: str) -> str:
    return _ADVISORY_TYPE_SEVERITY.get(advisory_type, "Unknown")


# ─────────────────────────────────────────────
# UyuniSession — thread-safe, single login/logout
# ─────────────────────────────────────────────

class UyuniSession:
    """
    Sessione UYUNI riusabile per un intero ciclo di sync.

    - 1 login/logout per ciclo (non per call)
    - Thread-safe: ogni thread ottiene il proprio ServerProxy via
      threading.local(), ma condividono self._key (read-only dopo login)

    Uso:
        with UyuniSession() as session:
            groups = session.get_test_groups()
            ...
    """

    def __init__(self):
        self._url = f"{Config.UYUNI_URL}/rpc/api"
        self._key: Optional[str] = None
        self._local = threading.local()

    def _make_proxy(self) -> xmlrpc.client.ServerProxy:
        """Crea ServerProxy rispettando Config.UYUNI_VERIFY_SSL."""
        if Config.UYUNI_VERIFY_SSL:
            transport = None
        else:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            transport = xmlrpc.client.SafeTransport(context=ctx)
        return xmlrpc.client.ServerProxy(self._url, transport=transport)

    @property
    def _proxy(self) -> xmlrpc.client.ServerProxy:
        """Lazy: crea proxy per questo thread se non esiste."""
        if not hasattr(self._local, "proxy"):
            self._local.proxy = self._make_proxy()
        return self._local.proxy

    def __enter__(self) -> "UyuniSession":
        self._key = self._proxy.auth.login(Config.UYUNI_USER, Config.UYUNI_PASSWORD)
        logger.debug("UYUNI session opened")
        return self

    def __exit__(self, *_) -> None:
        if self._key:
            try:
                self._proxy.auth.logout(self._key)
                logger.debug("UYUNI session closed")
            except Exception:
                pass
            self._key = None

    # ── API Methods ──────────────────────────────────────────────

    def get_test_groups(self) -> list:
        """Ritorna gruppi con prefisso Config.UYUNI_TEST_GROUP_PREFIX."""
        prefix = Config.UYUNI_TEST_GROUP_PREFIX
        try:
            groups = self._proxy.systemgroup.listAllGroups(self._key)
            filtered = [g for g in groups if g.get("name", "").startswith(prefix)]
            logger.debug(f"UYUNI: {len(filtered)} test groups (prefix={prefix!r})")
            return filtered
        except Exception as e:
            logger.warning(f"UYUNI get_test_groups failed: {e}")
            raise

    def get_systems_in_group(self, group_name: str) -> list:
        """Ritorna sistemi nel gruppo. Ogni dict include almeno {id, name}."""
        try:
            systems = self._proxy.systemgroup.listSystems(self._key, group_name)
            logger.debug(
                f"UYUNI: {len(systems)} systems in group {group_name!r}"
            )
            return systems
        except Exception as e:
            logger.warning(
                f"UYUNI get_systems_in_group({group_name!r}) failed: {e}"
            )
            return []

    def get_relevant_errata(self, system_id: int) -> list:
        """
        Patch applicabili (non ancora installate) per un sistema.
        Ritorna [{id, advisory_name, advisory_type, synopsis, date}, ...]
        """
        try:
            return self._proxy.system.getRelevantErrata(self._key, system_id)
        except Exception as e:
            logger.warning(
                f"UYUNI get_relevant_errata(system_id={system_id}) failed: {e}"
            )
            return []

    def get_errata_cves(self, advisory_name: str) -> list:
        """
        Lista CVE IDs associati all'errata.
        Ritorna ['CVE-2024-1234', ...] oppure [] in caso di errore.
        """
        try:
            return self._proxy.errata.listCves(self._key, advisory_name)
        except Exception as e:
            logger.warning(
                f"UYUNI get_errata_cves({advisory_name!r}) failed: {e}"
            )
            return []

    def get_errata_packages(self, advisory_name: str) -> list:
        """
        Pacchetti dell'errata.
        UYUNI ritorna {id, name, version, release, epoch, arch_label, file_size}.
        Mappato a {name, version, size_kb}.
        Ritorna [] in caso di errore.
        """
        try:
            pkgs = self._proxy.errata.listPackages(self._key, advisory_name)
            return [
                {
                    "name":    p.get("name", ""),
                    "version": p.get("version", ""),
                    "size_kb": (p.get("file_size") or 0) // 1024,
                }
                for p in pkgs
            ]
        except Exception as e:
            logger.warning(
                f"UYUNI get_errata_packages({advisory_name!r}) failed: {e}"
            )
            return []


# ─────────────────────────────────────────────
# Backward-compat one-shot wrapper (usato da queue_manager.py)
# ─────────────────────────────────────────────

def get_errata_packages(advisory_name: str) -> list:
    """One-shot wrapper — crea sessione, chiama, distrugge."""
    with UyuniSession() as s:
        return s.get_errata_packages(advisory_name)
