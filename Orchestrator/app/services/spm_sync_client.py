"""
SPM Orchestrator - SPM-SYNC HTTP Client

Client read-only per il polling dell'API SPM-SYNC.
Recupera errata e pacchetti per popolare errata_cache.
"""

import re
import logging
import requests
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

from app.config import Config

logger = logging.getLogger(__name__)

# Severità ordinate: indice = livello (0=più grave)
_SEVERITY_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]

# Severità da includere in base al minimo configurato
_SEVERITY_INCLUDE = {
    "Critical": {"CRITICAL"},
    "High":     {"CRITICAL", "HIGH"},
    "Medium":   {"CRITICAL", "HIGH", "MEDIUM"},
    "Low":      {"CRITICAL", "HIGH", "MEDIUM", "LOW"},
}

_CVE_RE = re.compile(r"CVE-\d{4}-\d+", re.IGNORECASE)


def _os_from_distribution(distribution: str) -> str:
    """Mappa distribution SPM-SYNC → target_os."""
    d = (distribution or "").lower()
    if d.startswith("ubuntu"):
        return "ubuntu"
    if d.startswith("debian"):
        return "debian"
    return d or "unknown"


def _normalize_severity(severity: str) -> str:
    """Converte 'CRITICAL' → 'Critical'."""
    return severity.strip().title() if severity else "Unknown"


def _parse_issued_date(date_str: str) -> Optional[datetime]:
    """
    Parsa issued_date da ISO 8601 o RFC 2822 (formato SPM-SYNC).
    Ritorna datetime UTC o None.
    """
    if not date_str:
        return None
    # ISO 8601 (e.g. "2026-02-20T13:23:45Z")
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        pass
    # RFC 2822 (e.g. "Fri, 20 Feb 2026 13:23:45 GMT")
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        pass
    return None


def _extract_cves(advisory_id: str, title: str = "") -> list:
    """
    Estrae CVE IDs da advisory_id e titolo.
    Esempio: 'DEB-CVE-2024-1234' → ['CVE-2024-1234']
    """
    found = set()
    for text in (advisory_id or "", title or ""):
        for m in _CVE_RE.findall(text):
            found.add(m.upper())
    return sorted(found)


def fetch_errata(
    min_severity: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    since_days: int = 180,
) -> tuple:
    """
    Recupera errata da SPM-SYNC con filtro severità e data.

    since_days: ignora errata più vecchi di N giorni (default 180).
    Ritorna (filtered: list, raw_count: int).
    raw_count è la dimensione della pagina grezza (usata per paginazione).
    Lancia requests.RequestException in caso di errore.
    """
    min_sev = min_severity or Config.SPM_SYNC_MIN_SEVERITY
    allowed = _SEVERITY_INCLUDE.get(
        min_sev, {"CRITICAL", "HIGH", "MEDIUM"}
    )

    # Cutoff: ignora errata più vecchi di N giorni
    cutoff = None
    if since_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    try:
        resp = requests.get(
            f"{Config.SPM_SYNC_URL}/api/errata",
            params={"limit": limit, "offset": offset},
            timeout=Config.SPM_SYNC_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"SPM-SYNC /api/errata failed: {e}")
        raise

    raw = data.get("errata", [])
    filtered = []
    for e in raw:
        if e.get("severity", "").upper() not in allowed:
            continue
        if cutoff:
            issued = _parse_issued_date(e.get("issued_date", ""))
            if issued is not None and issued < cutoff:
                continue
        filtered.append(e)

    logger.debug(
        f"SPM-SYNC offset={offset}: {len(raw)} returned, "
        f"{len(filtered)} match (min_sev={min_sev}, "
        f"since={since_days}d)"
    )
    return filtered, len(raw)


def fetch_packages(advisory_id: str) -> list:
    """
    Recupera pacchetti per un errata.

    Ritorna lista [{name, version, release}].
    Ritorna [] in caso di errore (best-effort).
    """
    try:
        resp = requests.get(
            f"{Config.SPM_SYNC_URL}/api/errata"
            f"/{advisory_id}/packages",
            timeout=Config.SPM_SYNC_TIMEOUT,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("packages", [])
    except requests.RequestException as e:
        logger.warning(
            f"SPM-SYNC /api/errata/{advisory_id}/packages: {e}"
        )
        return []


def build_cache_row(errata: dict, packages: list) -> dict:
    """
    Converte errata SPM-SYNC nel formato errata_cache.
    """
    advisory_id = errata.get("advisory_id", "")
    title = errata.get("title", "")
    issued_dt = _parse_issued_date(errata.get("issued_date", ""))
    return {
        "errata_id":   advisory_id,
        "synopsis":    title,
        "description": errata.get("description", ""),
        "severity":    _normalize_severity(errata.get("severity", "")),
        "type":        errata.get("source", ""),
        "issued_date": issued_dt.isoformat() if issued_dt else None,
        "target_os":   _os_from_distribution(
            errata.get("distribution", "")
        ),
        "packages":    packages,
        "cves":        _extract_cves(advisory_id, title),
        "source_url":  None,
    }
