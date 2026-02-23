"""
SPM Orchestrator - UYUNI XML-RPC Client

Client per recuperare errata applicabili ai sistemi nei gruppi "test-*"
direttamente da UYUNI, invece di scaricare l'intero catalogo da SPM-SYNC.
"""

import logging
import ssl
import xmlrpc.client
from contextlib import contextmanager
from typing import Optional

from app.config import Config

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Session management
# ─────────────────────────────────────────────

@contextmanager
def _session():
    """
    Context manager: apre sessione UYUNI XML-RPC, ritorna (client, key).
    Garantisce logout anche in caso di eccezione.
    """
    url = f"{Config.UYUNI_URL}/rpc/api"

    if Config.UYUNI_VERIFY_SSL:
        transport = None
    else:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        transport = xmlrpc.client.SafeTransport(context=ctx)

    client = xmlrpc.client.ServerProxy(url, transport=transport)
    key = None
    try:
        key = client.auth.login(Config.UYUNI_USER, Config.UYUNI_PASSWORD)
        yield client, key
    finally:
        if key:
            try:
                client.auth.logout(key)
            except Exception:
                pass


# ─────────────────────────────────────────────
# OS / Severity helpers
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
# Public API
# ─────────────────────────────────────────────

def get_test_groups() -> list:
    """
    Ritorna tutti i gruppi il cui nome inizia con Config.UYUNI_TEST_GROUP_PREFIX.
    Ogni dict: {id, name, description, ...}
    """
    prefix = Config.UYUNI_TEST_GROUP_PREFIX
    try:
        with _session() as (client, key):
            groups = client.systemgroup.listAllGroups(key)
        filtered = [g for g in groups if g.get("name", "").startswith(prefix)]
        logger.debug(f"UYUNI: {len(filtered)} test groups (prefix={prefix!r})")
        return filtered
    except Exception as e:
        logger.error(f"UYUNI get_test_groups failed: {e}")
        raise


def get_systems_in_group(group_name: str) -> list:
    """
    Ritorna sistemi nel gruppo. Ogni dict include almeno {id, name}.
    """
    try:
        with _session() as (client, key):
            systems = client.systemgroup.listSystems(key, group_name)
        logger.debug(
            f"UYUNI: {len(systems)} systems in group {group_name!r}"
        )
        return systems
    except Exception as e:
        logger.error(
            f"UYUNI get_systems_in_group({group_name!r}) failed: {e}"
        )
        raise


def get_relevant_errata(system_id: int) -> list:
    """
    Patch applicabili (non ancora installate) per un sistema.
    Ritorna [{id, advisory_name, advisory_type, synopsis, date}, ...]
    """
    try:
        with _session() as (client, key):
            errata = client.system.getRelevantErrata(key, system_id)
        return errata
    except Exception as e:
        logger.warning(
            f"UYUNI get_relevant_errata(system_id={system_id}) failed: {e}"
        )
        return []


def get_errata_details(advisory_name: str) -> dict:
    """
    Dettagli errata: synopsis, description, type, issue_date.
    Ritorna {} in caso di errore.
    """
    try:
        with _session() as (client, key):
            return client.errata.getDetails(key, advisory_name)
    except Exception as e:
        logger.warning(
            f"UYUNI get_errata_details({advisory_name!r}) failed: {e}"
        )
        return {}


def get_errata_cves(advisory_name: str) -> list:
    """
    Lista CVE IDs associati all'errata.
    Ritorna ['CVE-2024-1234', ...] oppure [] in caso di errore.
    """
    try:
        with _session() as (client, key):
            return client.errata.listCves(key, advisory_name)
    except Exception as e:
        logger.warning(
            f"UYUNI get_errata_cves({advisory_name!r}) failed: {e}"
        )
        return []


def get_errata_packages(advisory_name: str) -> list:
    """
    Pacchetti dell'errata.
    UYUNI ritorna {id, name, version, release, epoch, arch_label, file_size}.
    Mappato a {name, version, size_kb}.
    Ritorna [] in caso di errore.
    """
    try:
        with _session() as (client, key):
            pkgs = client.errata.listPackages(key, advisory_name)
        result = []
        for p in pkgs:
            result.append({
                "name":    p.get("name", ""),
                "version": p.get("version", ""),
                "size_kb": (p.get("file_size") or 0) // 1024,
            })
        return result
    except Exception as e:
        logger.warning(
            f"UYUNI get_errata_packages({advisory_name!r}) failed: {e}"
        )
        return []
