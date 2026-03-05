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


def severity_from_advisory_type(advisory_type: str) -> str:
    return _ADVISORY_TYPE_SEVERITY.get(advisory_type, "Unknown")


# ─────────────────────────────────────────────
# SSL helper (condiviso con health.py)
# ─────────────────────────────────────────────

def make_uyuni_ssl_context():
    """
    Crea SSL context per connessioni UYUNI XML-RPC.
    Rispetta Config.UYUNI_VERIFY_SSL: se False, disabilita verifica certificato.
    Ritorna None se SSL verification è abilitata (usa default di sistema).
    """
    if Config.UYUNI_VERIFY_SSL:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ─────────────────────────────────────────────
# UyuniSession — thread-safe, single login/logout
# ─────────────────────────────────────────────

class UyuniSession:
    """
    Sessione UYUNI riusabile per un intero ciclo di sync.

    - 1 login/logout per ciclo (non per call)
    - Thread-safe: ogni thread ottiene il proprio ServerProxy via
      threading.local(), ma condividono self._key (read-only dopo login)
    - Supporta credenziali operatore (username/password opzionali;
      default: Config.UYUNI_USER / Config.UYUNI_PASSWORD)

    Uso:
        with UyuniSession() as session:
            groups = session.get_test_groups()

        with UyuniSession(username="op@asl06.org", password="...") as session:
            session.add_note(system_id, subject, body)
    """

    def __init__(self, username: str = None, password: str = None):
        self._url      = f"{Config.UYUNI_URL}/rpc/api"
        self._username = username or Config.UYUNI_USER
        self._password = password or Config.UYUNI_PASSWORD
        self._key: Optional[str] = None
        self._local = threading.local()

    @staticmethod
    def validate_credentials(username: str, password: str) -> bool:
        """
        Verifica credenziali UYUNI/AD: tenta auth.login + logout immediato.
        Ritorna True se valide, False altrimenti.
        """
        try:
            with UyuniSession(username=username, password=password):
                pass
            logger.debug(f"UYUNI: credentials valid for {username!r}")
            return True
        except Exception as e:
            logger.debug(f"UYUNI: credential validation failed for {username!r}: {e}")
            return False

    def _make_proxy(self) -> xmlrpc.client.ServerProxy:
        """Crea ServerProxy rispettando Config.UYUNI_VERIFY_SSL."""
        ctx = make_uyuni_ssl_context()
        transport = xmlrpc.client.SafeTransport(context=ctx) if ctx else None
        return xmlrpc.client.ServerProxy(self._url, transport=transport)

    @property
    def _proxy(self) -> xmlrpc.client.ServerProxy:
        """Lazy: crea proxy per questo thread se non esiste."""
        if not hasattr(self._local, "proxy"):
            self._local.proxy = self._make_proxy()
        return self._local.proxy

    def __enter__(self) -> "UyuniSession":
        self._key = self._proxy.auth.login(self._username, self._password)
        logger.debug(f"UYUNI session opened (user={self._username!r})")
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

    def get_system_network_ip(self, system_id: int) -> Optional[str]:
        """
        Ritorna l'IP primario del sistema tramite system.getNetwork.
        Usato da get_test_system_for_os() quando il nome del sistema non è un IP.
        Ritorna None in caso di errore o IP non disponibile.
        """
        try:
            info = self._proxy.system.getNetwork(self._key, system_id)
            ip = info.get("ip") or info.get("ip4") or info.get("ipv4")
            if ip and ip not in ("127.0.0.1", "::1", ""):
                logger.debug(f"UYUNI getNetwork({system_id}): ip={ip!r}")
                return ip
        except Exception as e:
            logger.debug(f"UYUNI get_system_network_ip({system_id}) failed: {e}")
        return None

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

    def add_note(self, system_id: int, subject: str, body: str) -> None:
        """
        Aggiunge nota persistente a un sistema UYUNI (system.addNote).
        Solo gli amministratori possono eliminare le note → audit trail robusto.
        Raises: Exception se la chiamata UYUNI fallisce.
        """
        try:
            self._proxy.system.addNote(self._key, system_id, subject, body)
            logger.debug(f"UYUNI: note added to system {system_id}")
        except Exception as e:
            logger.warning(f"UYUNI add_note(system_id={system_id}) failed: {e}")
            raise

    def get_current_org(self) -> dict:
        """
        Ritorna l'organizzazione dell'utente corrente.
        Chiama user.getDetails() + org.getDetails() per ottenere id e nome.
        """
        try:
            user_details = self._proxy.user.getDetails(self._key, self._username)
            org_id = user_details.get("org_id", 1)
            try:
                org_details = self._proxy.org.getDetails(self._key, org_id)
                org_name = org_details.get("name", f"Org {org_id}")
            except Exception:
                org_name = f"Org {org_id}"
            return {"org_id": org_id, "org_name": org_name}
        except Exception as e:
            logger.warning(f"UYUNI get_current_org failed: {e}")
            return {"org_id": None, "org_name": ""}

    def list_orgs(self) -> list:
        """
        Ritorna tutte le organizzazioni UYUNI visibili all'account corrente.
        Richiede ruolo satellite admin per vedere tutte le org.
        Ritorna [{org_id, org_name}, ...].
        """
        try:
            orgs = self._proxy.org.listOrgs(self._key)
            return [
                {"org_id": o.get("id"), "org_name": o.get("name", f"Org {o.get('id')}")}
                for o in orgs
            ]
        except Exception as e:
            logger.warning(f"UYUNI list_orgs failed: {e}")
            # Fallback: ritorna solo l'org corrente
            return [self.get_current_org()]

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
